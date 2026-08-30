"""Model backend for the buyer fleet, with a rotating pool of API keys.

One free-tier key does not cover a 500-session batch. This module accepts
several keys, uses one until its daily quota is gone, then moves to the next.
Only when every key is spent does it raise, because a batch that quietly
finishes on the heuristic is attributable to neither backend.

Keys may belong to different providers — a Groq key, an OpenAI key and an
Anthropic key form a valid chain. Each key resolves its own provider and model,
and the run report records how many decisions each one made.

Configuration (any of these, combined and de-duplicated in order):

    HS_LLM_API_KEYS=key1,key2,key3
    HS_LLM_API_KEY=key1
    HS_LLM_API_KEY_2=key2      (…_3, …_4, up to _9)

    HS_LLM_MODELS=model1,model2,model3    # aligned to the key order
    HS_LLM_MODEL=model                    # one model for every key
"""

import json
import os
import re
import time


class LLMBudgetExhausted(RuntimeError):
    """Every key's per-day quota is gone. Waiting will not help within this
    run, and continuing would mix model and heuristic decisions in one batch."""


# ---------------------------------------------------------------- parsing ---

_TRUE = ('"proceed": true', "'proceed': true", "proceed=true", "proceed: true")
_FALSE = ('"proceed": false', "'proceed': false", "proceed=false", "proceed: false")


def _parse_decision(text):
    """Pull a boolean out of whatever came back: raw JSON, a fenced block,
    JSON buried in prose, or a plain sentence."""
    if not text:
        return None
    stripped = text.strip()
    for fence in ("```json", "```"):
        if stripped.startswith(fence):
            stripped = stripped[len(fence):].removesuffix("```").strip()
    match = re.search(r"\{[^{}]*\}", stripped, re.S)
    if match:
        try:
            value = json.loads(match.group(0)).get("proceed")
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("true", "yes", "1")
        except (json.JSONDecodeError, AttributeError):
            pass
    low = stripped.lower().replace(" ", "")
    for needle in _TRUE:
        if needle.replace(" ", "") in low:
            return True
    for needle in _FALSE:
        if needle.replace(" ", "") in low:
            return False
    if low in ("true", "false"):
        return low == "true"
    return None


# ------------------------------------------------------------ rate limits ---

def _retry_after_seconds(message):
    """Providers state the wait in the error. Use theirs, not a guess."""
    match = re.search(r"try again in\s+([0-9.]+)m([0-9.]+)s", message)
    if match:
        return float(match.group(1)) * 60 + float(match.group(2))
    match = re.search(r"try again in\s+([0-9.]+)s", message)
    return float(match.group(1)) if match else None


def _quota_scope(message):
    """Per-day quotas end this key's usefulness; per-minute quotas are a pause."""
    low = message.lower()
    if "per day" in low or "(tpd)" in low or "(rpd)" in low or "daily" in low:
        return "day"
    return "minute"


def _is_rate_limit(message):
    low = message.lower()
    return "rate_limit" in low or "429" in low or "rate limit" in low


def _is_auth_error(message):
    low = message.lower()
    return ("401" in low or "invalid api key" in low or "authentication" in low
            or "invalid_api_key" in low)


# --------------------------------------------------------------- endpoint ---

class Endpoint:
    """One key, its provider, its model, and what it has spent."""

    def __init__(self, key, provider, base_url, model, index):
        self.key = key
        self.provider = provider
        self.base_url = base_url
        self.model = model
        self.index = index
        self.client = None
        self.calls = 0
        self.failures = 0
        self.tokens = 0
        self.exhausted = False
        self.error = ""

    @property
    def label(self):
        return f"key{self.index + 1}"

    @property
    def masked(self):
        return (self.key[:7] + "…" + self.key[-4:]) if len(self.key) > 12 else "set"

    def describe(self):
        where = f" @ {self.base_url}" if self.base_url else ""
        return f"{self.label} {self.provider}{where} · {self.model}"

    def connect(self):
        if self.client is not None:
            return True
        try:
            if self.provider == "anthropic":
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.key)
            else:
                import openai
                kwargs = {"api_key": self.key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self.client = openai.OpenAI(**kwargs)
            return True
        except ImportError as exc:
            need = "anthropic" if self.provider == "anthropic" else "openai"
            self.error = f"{exc}. Install the client: pip install {need}"
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        self.exhausted = True
        return False

    def as_dict(self):
        return {"key": self.label, "provider": self.provider, "model": self.model,
                "calls": self.calls, "failures": self.failures,
                "tokens": self.tokens, "exhausted": self.exhausted,
                "error": self.error}


# --------------------------------------------------------------- decider ----

class LLMDecider:
    """Delegates the proceed/abandon judgement to a real model, across a pool
    of keys. Failures are counted and surfaced, never silently swallowed."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.endpoints = [Endpoint(key, provider, base, model, i)
                          for i, (key, provider, base, model)
                          in enumerate(cfg.llm_endpoints())]
        self.cursor = 0
        self.calls = 0
        self.failures = 0
        self.tokens = 0
        self.last_tokens = 0
        self.last_error = "" if self.endpoints else "no API key configured"
        self.last_raw = ""
        self.rotations = 0
        self.waits = 0
        self.max_tokens = int(os.environ.get("HS_LLM_MAX_TOKENS", "512"))
        self.max_wait = float(os.environ.get("HS_LLM_MAX_WAIT", "75"))
        self.max_waits = int(os.environ.get("HS_LLM_MAX_WAITS", "20"))
        for endpoint in self.endpoints:
            endpoint.connect()

    # ---- pool state ----

    @property
    def live(self):
        return [e for e in self.endpoints if e.client and not e.exhausted]

    def available(self):
        return bool(self.live)

    def current(self):
        while self.cursor < len(self.endpoints):
            endpoint = self.endpoints[self.cursor]
            if endpoint.client and not endpoint.exhausted:
                return endpoint
            self.cursor += 1
        return None

    def describe(self):
        if not self.endpoints:
            return "no keys"
        models = sorted({e.model for e in self.endpoints})
        providers = sorted({e.provider for e in self.endpoints})
        return (f"{len(self.endpoints)} key(s) · {'/'.join(providers)} · "
                f"{'/'.join(models)}")

    def models_used(self):
        return sorted({e.model for e in self.endpoints if e.calls > e.failures})

    def pool_state(self):
        return [e.as_dict() for e in self.endpoints]

    # ---- one decision ----

    def decide(self, persona, view, required):
        # Send the decision inputs, not the whole record. A 2 KB product dump
        # across a 500-session batch is what exhausts a daily token quota.
        attributes = view.get("attributes", {})
        compact = {
            "title": view.get("title"),
            "price_inr": view.get("price"),
            "stated": attributes,
            "missing": [a for a in required if a not in attributes],
            "policy_machine_readable": bool(view.get("policy", {}).get("structured", True)),
        }
        prompt = (
            f"Shopping agent. Budget {persona.budget}, cap {persona.cap} INR. "
            f"Posture {persona.posture} (strict=refuse on any missing detail; "
            f"balanced=need stated attributes; permissive=proceed unless clearly wrong).\n"
            f"{json.dumps(compact, separators=(',', ':'))}\n"
            'Proceed to checkout? JSON only: {"proceed":true} or {"proceed":false}'
        )
        self.calls += 1
        try:
            text = self._complete(prompt)
            answer = _parse_decision(text)
            if answer is None:
                raise ValueError(
                    "no decision found in the model reply: "
                    + (repr(text[:200]) if text else "empty response "
                       "(a reasoning model may have spent the whole token budget "
                       "on reasoning — raise HS_LLM_MAX_TOKENS or lower the effort)"))
            return answer
        except LLMBudgetExhausted:
            raise
        except Exception as exc:
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None  # falls back to the heuristic, and is counted

    # ---- transport ----

    def _call(self, endpoint, prompt, extra):
        if endpoint.provider == "anthropic":
            msg = endpoint.client.messages.create(
                model=endpoint.model, max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}])
            usage = getattr(msg, "usage", None)
            spent = ((getattr(usage, "input_tokens", 0) or 0)
                     + (getattr(usage, "output_tokens", 0) or 0)) if usage else 0
            text = "".join(getattr(b, "text", "") for b in msg.content)
        else:
            msg = endpoint.client.chat.completions.create(
                model=endpoint.model, max_tokens=self.max_tokens, temperature=0,
                messages=[{"role": "user", "content": prompt}], **extra)
            usage = getattr(msg, "usage", None)
            spent = (getattr(usage, "total_tokens", 0) or 0) if usage else 0
            choice = msg.choices[0].message
            text = (choice.content or "").strip()
            if not text:
                text = (getattr(choice, "reasoning", None)
                        or getattr(choice, "reasoning_content", None) or "").strip()
        endpoint.tokens += spent
        self.tokens += spent
        self.last_tokens = spent
        return text

    def _complete(self, prompt):
        """One completion. Drops parameters a provider rejects, waits out a
        per-minute limit, and rotates to the next key on a per-day limit."""
        attempts = [
            {"response_format": {"type": "json_object"},
             "extra_body": {"reasoning_effort": "low"}},
            {"extra_body": {"reasoning_effort": "low"}},
            {"response_format": {"type": "json_object"}},
            {},
        ]
        last = None
        while True:
            endpoint = self.current()
            if endpoint is None:
                spent = ", ".join(f"{e.label}: {e.tokens} tokens" for e in self.endpoints)
                raise LLMBudgetExhausted(
                    f"all {len(self.endpoints)} key(s) are spent or unusable ({spent}). "
                    f"Last error: {last or self.last_error}")

            for extra in (attempts if endpoint.provider != "anthropic" else [{}]) * 2:
                try:
                    endpoint.calls += 1
                    text = self._call(endpoint, prompt, extra)
                    if text:
                        self.last_raw = text
                        return text
                    last = ValueError("empty content")
                except Exception as exc:
                    message = str(exc)
                    endpoint.failures += 1
                    if _is_auth_error(message):
                        endpoint.exhausted = True
                        endpoint.error = f"rejected: {message[:160]}"
                        last = exc
                        break
                    if _is_rate_limit(message):
                        if _quota_scope(message) == "day":
                            endpoint.exhausted = True
                            endpoint.error = "daily quota spent"
                            self.rotations += 1
                            last = exc
                            break
                        wait = _retry_after_seconds(message)
                        if (wait is not None and wait <= self.max_wait
                                and self.waits < self.max_waits):
                            self.waits += 1
                            time.sleep(wait + 0.5)
                            continue
                        # a long per-minute wait is treated like a spent key so
                        # the batch keeps moving on another one
                        if len(self.live) > 1:
                            endpoint.exhausted = True
                            endpoint.error = f"throttled beyond {self.max_wait}s"
                            self.rotations += 1
                            last = exc
                            break
                        raise
                    last = exc
                    # Some providers reject a parameter, or accept it and then
                    # fail to satisfy it (an empty completion under
                    # response_format=json_object). Both mean: drop the
                    # parameter and try again, rather than lose the decision.
                    recoverable = ("reasoning_effort", "response_format",
                                   "json_validate_failed", "failed to validate json")
                    if not any(t in message.lower() for t in recoverable):
                        raise
            else:
                # every parameter combination failed without a rotation signal
                raise last if last else ValueError("no response")
