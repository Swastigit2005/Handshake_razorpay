"""Payment adapter.

Two backends behind one interface:

  sim       deterministic local simulator, no network, reason codes shaped like
            a real gateway's. Used for reproducible batches.
  razorpay  Razorpay test mode via the official SDK. Selected with
            HS_PAYMENTS=razorpay and test credentials in the environment.

No production credentials are ever accepted: the razorpay backend refuses a
key id that does not carry the test prefix.
"""

import os
import time
import uuid


class PaymentError(Exception):
    pass


class Result:
    def __init__(self, ok, ref="", reason_code="", raw=None):
        self.ok = ok
        self.ref = ref
        self.reason_code = reason_code
        self.raw = raw or {}

    def as_dict(self):
        return {"ok": self.ok, "ref": self.ref, "reason_code": self.reason_code}


class SimBackend:
    name = "sim"

    def __init__(self, rng):
        self.rng = rng

    def charge(self, amount_inr, instrument, forced_reason=None):
        if forced_reason:
            return Result(False, ref=f"pay_sim_{uuid.uuid4().hex[:12]}",
                          reason_code=forced_reason)
        if instrument.get("state") == "expired":
            return Result(False, reason_code="instrument_declined")
        return Result(True, ref=f"pay_sim_{uuid.uuid4().hex[:12]}")

    def refund(self, ref, amount_inr):
        return Result(True, ref=f"rfnd_sim_{uuid.uuid4().hex[:12]}")


class RazorpayBackend:
    name = "razorpay"

    def __init__(self, key_id, key_secret):
        if not key_id or not key_secret:
            raise PaymentError("Razorpay backend selected but credentials are absent")
        if not key_id.startswith("rzp_test_"):
            raise PaymentError("refusing a non test-mode key id")
        import razorpay  # imported lazily so the sim path has no dependency
        self.client = razorpay.Client(auth=(key_id, key_secret))
        # Pace calls so a long batch does not trip test-mode rate limits.
        self.min_interval = float(os.environ.get("HS_RZP_MIN_INTERVAL", "0.12"))
        self._last_call = 0.0
        self.throttled = 0

    def charge(self, amount_inr, instrument, forced_reason=None):
        try:
            order = self._create_with_retry(int(round(amount_inr * 100)))
        except Exception as exc:
            # An unreachable gateway is not a declined payment. Reporting it as
            # one would put a fabricated failure into the batch, so stop.
            raise PaymentError(
                f"Razorpay test mode is unreachable ({type(exc).__name__}: {exc}). "
                "Run `python3 preflight.py` to diagnose. No batch was produced."
            ) from exc
        if forced_reason:
            # The fault is a merchant-side condition; the order stands unpaid.
            return Result(False, ref=order["id"], reason_code=forced_reason, raw=order)
        return Result(True, ref=order["id"], raw=order)

    def _create_with_retry(self, amount_paise, attempts=4):
        """Test mode is rate limited. A 429 is a throttle, not a failure, so it
        is waited out rather than turned into a fabricated decline."""
        delay = self.min_interval
        last = None
        for attempt in range(attempts):
            if self.min_interval:
                since = time.monotonic() - self._last_call
                if since < self.min_interval:
                    time.sleep(self.min_interval - since)
            try:
                self._last_call = time.monotonic()
                return self.client.order.create({
                    "amount": amount_paise, "currency": "INR", "payment_capture": 1})
            except Exception as exc:
                last = exc
                text = str(exc).lower()
                throttled = ("429" in text or "rate limit" in text
                             or "too many requests" in text)
                if not throttled or attempt == attempts - 1:
                    raise
                self.throttled += 1
                time.sleep(max(delay, 0.5) * (2 ** attempt))
        raise last

    def refund(self, ref, amount_inr):
        return Result(True, ref=f"rfnd_{ref}")


def preflight(backend):
    """Prove the backend can transact before a batch commits to it."""
    if backend.name != "razorpay":
        return True, ""
    try:
        backend.charge(100.0, {"type": "card_token", "state": "active"})
        return True, ""
    except Exception as exc:
        return False, str(exc)


def build_backend(cfg, rng):
    if cfg.payments_backend == "razorpay":
        return RazorpayBackend(cfg.razorpay_key_id, cfg.razorpay_key_secret)
    return SimBackend(rng)
