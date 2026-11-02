"""The /v1 HTTP surface a merchant integrates against.

Authentication: `Authorization: Bearer hsk_live_…` (or `X-Handshake-Key`). Keys
are stored as SHA-256 hashes and shown once, at creation or rotation.
Administration (`/v1/merchants`, the global kill switch) needs `HS_ADMIN_TOKEN`.

Every error is `{"error": {"type": …, "message": …}}` with a meaningful status.
Every response carries `X-Request-Id`. Ingest is idempotent on `event_id`, so a
client may retry a batch it is unsure was received.
"""

import hmac
import os
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..taxonomy import CAUSES, INTERVENTIONS, RULES
from . import pipeline, store, webhooks
from .events import TYPES, InvalidEvent, describe

router = APIRouter(prefix="/v1", tags=["live"])

MAX_BODY = 2 * 1024 * 1024


class APIError(Exception):
    def __init__(self, status, type_, message):
        self.status, self.type, self.message = status, type_, message


def error_response(status, type_, message):
    return JSONResponse({"error": {"type": type_, "message": message}}, status_code=status)


# ------------------------------------------------------------ rate limit ---

class Bucket:
    """Token bucket per merchant. In-process; behind several replicas, put the
    limit at the load balancer instead."""

    def __init__(self, rate, burst):
        self.rate, self.burst = rate, burst
        self.state = {}
        self.lock = threading.Lock()

    def take(self, key, cost=1):
        now = time.monotonic()
        with self.lock:
            tokens, last = self.state.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < cost:
                self.state[key] = (tokens, now)
                return False, (cost - tokens) / self.rate
            self.state[key] = (tokens - cost, now)
            return True, 0.0


LIMITER = Bucket(float(os.environ.get("HS_RATE_PER_SEC", "200")),
                 float(os.environ.get("HS_RATE_BURST", "1000")))


# ------------------------------------------------------------------ auth ---

def _key_from(authorization, x_handshake_key):
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return x_handshake_key.strip()


def merchant_auth(request: Request, authorization: str = Header(default=""),
                  x_handshake_key: str = Header(default="")):
    key = _key_from(authorization, x_handshake_key)
    if not key:
        raise APIError(401, "authentication_error",
                       "send your API key as 'Authorization: Bearer hsk_…'")
    merchant = store.merchant_by_key(key)
    if merchant is None:
        raise APIError(401, "authentication_error", "unknown or revoked API key")
    request.state.merchant_id = merchant["merchant_id"]      # for the access log
    ok, wait = LIMITER.take(merchant["merchant_id"])
    if not ok:
        raise APIError(429, "rate_limited", f"slow down; retry in {wait:.2f}s")
    length = request.headers.get("content-length")
    if length and int(length) > MAX_BODY:
        raise APIError(413, "payload_too_large", f"request bodies are capped at {MAX_BODY} bytes")
    return merchant


def admin_auth(authorization: str = Header(default=""), x_admin_token: str = Header(default="")):
    token = os.environ.get("HS_ADMIN_TOKEN", "")
    given = _key_from(authorization, x_admin_token)
    if not token:
        raise APIError(403, "forbidden", "administration is disabled: set HS_ADMIN_TOKEN")
    if not hmac.compare_digest(given, token):
        raise APIError(401, "authentication_error", "invalid admin token")
    return True


# --------------------------------------------------------------- schemas ---

class MerchantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    webhook_url: str = ""
    sandbox: bool = False
    settings: Dict[str, Any] = {}
    policy: Dict[str, Any] = {}


class MerchantPatch(BaseModel):
    name: Optional[str] = None
    webhook_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class EventBatch(BaseModel):
    events: List[Dict[str, Any]]


class CatalogPut(BaseModel):
    products: List[Dict[str, Any]]


class SchemaPut(BaseModel):
    schema_: Dict[str, List[str]] = Field(..., alias="schema")


class PolicyPatch(BaseModel):
    max_reoffers_per_session: Optional[int] = Field(None, ge=0, le=10)
    max_interventions_per_buyer_24h: Optional[int] = Field(None, ge=0, le=50)
    concession_ceiling_pct: Optional[float] = Field(None, ge=0, le=0.5)
    gross_margin_pct: Optional[float] = Field(None, gt=0, le=1)
    cost_machine_inr: Optional[float] = Field(None, ge=0)
    cost_human_inr: Optional[float] = Field(None, ge=0)
    abuse_window_abandonments: Optional[int] = Field(None, ge=1, le=100)
    max_mandate_retries: Optional[int] = Field(None, ge=0, le=10)
    quiet_hours: Optional[List[int]] = None
    confidence_threshold: Optional[float] = Field(None, ge=0, le=1)
    kill_switch: Optional[bool] = None
    price_lock_ttl_minutes: Optional[int] = Field(None, ge=1, le=1440)


class KillSwitch(BaseModel):
    on: bool


# -------------------------------------------------------------- merchants ---

@router.post("/merchants", status_code=201)
def create_merchant(body: MerchantCreate, _: bool = Depends(admin_auth)):
    merchant, key = store.create_merchant(body.name, body.webhook_url, body.policy,
                                          body.settings, body.sandbox)
    return {"merchant": store.public_merchant(merchant), "api_key": key,
            "note": "Store the API key now. Handshake keeps only its hash."}


@router.get("/me")
def me(merchant=Depends(merchant_auth)):
    return store.public_merchant(merchant)


@router.patch("/me")
def patch_me(body: MerchantPatch, merchant=Depends(merchant_auth)):
    settings = None
    if body.settings is not None:
        settings = {**(merchant["settings"] or {}), **body.settings}
    m = store.update_merchant(merchant["merchant_id"], name=body.name,
                              webhook_url=body.webhook_url, settings=settings)
    return store.public_merchant(m)


@router.post("/me/rotate-key")
def rotate(merchant=Depends(merchant_auth)):
    return {"api_key": store.rotate_key(merchant["merchant_id"]),
            "note": "The previous key stopped working just now."}


# ----------------------------------------------------------------- policy ---

def _policy_view(merchant):
    cfg = pipeline.policy_for(merchant)
    return {"policy": {k: getattr(cfg, k) for k in vars(cfg)},
            "global_kill_switch": pipeline.global_kill_switch(),
            "rules": RULES}


@router.get("/policy")
def get_policy(merchant=Depends(merchant_auth)):
    return _policy_view(merchant)


@router.patch("/policy")
def patch_policy(body: PolicyPatch, merchant=Depends(merchant_auth)):
    dump = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    changes = {k: v for k, v in dump.items() if v is not None}
    if "quiet_hours" in changes and len(changes["quiet_hours"]) != 2:
        raise APIError(422, "invalid_request", "quiet_hours is [start_hour, end_hour]")
    policy = {**(merchant["policy"] or {}), **changes}
    m = store.update_merchant(merchant["merchant_id"], policy=policy)
    store.ledger_append(m["merchant_id"], None, "operator", "policy_changed",
                        trigger={"changes": changes})
    return _policy_view(m)


@router.post("/admin/killswitch")
def global_kill(body: KillSwitch, _: bool = Depends(admin_auth)):
    return {"global_kill_switch": pipeline.global_kill_switch(body.on)}


# ----------------------------------------------------------------- ingest ---

@router.post("/events")
def ingest(body: EventBatch, merchant=Depends(merchant_auth)):
    try:
        result = pipeline.ingest(merchant, body.events)
    except InvalidEvent as exc:
        raise APIError(422, "invalid_request", str(exc))
    if body.events and not result["accepted"] and not result["duplicates"]:
        return JSONResponse({"error": {"type": "invalid_events",
                                       "message": "no event in the batch was valid"},
                             **result}, status_code=422)
    return result


@router.put("/catalog")
def put_catalog(body: CatalogPut, merchant=Depends(merchant_auth)):
    bad = [i for i, p in enumerate(body.products) if not p.get("sku")]
    if bad:
        raise APIError(422, "invalid_request", f"products at {bad[:5]} have no sku")
    return {"stored": store.put_catalog(merchant["merchant_id"], body.products)}


@router.get("/catalog")
def get_catalog(merchant=Depends(merchant_auth)):
    return {"products": store.catalog(merchant["merchant_id"])}


@router.put("/schema")
def put_schema(body: SchemaPut, merchant=Depends(merchant_auth)):
    return {"schema": store.put_schema(merchant["merchant_id"], body.schema_)}


@router.get("/schema")
def get_schema(merchant=Depends(merchant_auth)):
    return {"schema": store.get_schema(merchant["merchant_id"])}


# --------------------------------------------------------------- journeys ---

def _summary(j):
    dg = j.get("diagnosis") or {}
    vd = j.get("verdict") or {}
    return {"journey_id": j["journey_id"], "agent_id": j["agent_id"],
            "checkout_id": j["checkout_id"], "status": j["status"], "stage": j["stage"],
            "sku": j["sku"], "basket_value": j["basket_value"],
            "recovered_value": j["recovered_value"], "opened_at": j["opened_at"],
            "last_event_at": j["last_event_at"], "close_reason": j["close_reason"],
            "cause": dg.get("cause"), "cause_name": dg.get("name"),
            "confidence": dg.get("confidence"), "explanation": dg.get("explanation"),
            "intervention": vd.get("intervention_id") or None,
            "binding_rule": vd.get("binding_rule") or None}


@router.get("/journeys")
def journeys(status: str = "", limit: int = 50, offset: int = 0,
             merchant=Depends(merchant_auth)):
    rows = store.list_journeys(merchant["merchant_id"], status or None,
                               max(1, min(limit, 500)), max(0, offset))
    return {"journeys": [_summary(j) for j in rows]}


def _journey_or_404(merchant, journey_id):
    j = store.get_journey(merchant["merchant_id"], journey_id)
    if j is None:
        jid = store.journey_by_checkout(merchant["merchant_id"], journey_id)
        j = store.get_journey(merchant["merchant_id"], jid) if jid else None
    if j is None:
        raise APIError(404, "not_found", f"no journey or checkout {journey_id!r}")
    return j


@router.get("/journeys/{journey_id}")
def journey(journey_id: str, merchant=Depends(merchant_auth)):
    mid = merchant["merchant_id"]
    j = _journey_or_404(merchant, journey_id)
    events = store.journey_events(mid, j["journey_id"])
    for ev in events:
        ev["summary"] = describe(ev)
    return {**_summary(j), "diagnosis": j["diagnosis"], "verdict": j["verdict"],
            "directive": j["directive"], "concession": j["concession"],
            "attempts": j["attempts"], "events": events,
            "reoffer": store.get_reoffer(mid, j["journey_id"], mark_fetched=False),
            "ledger": store.ledger(mid, j["journey_id"]),
            "webhooks": store.deliveries(mid, j["journey_id"])}


@router.post("/journeys/{journey_id}/close")
def force_close(journey_id: str, merchant=Depends(merchant_auth)):
    j = _journey_or_404(merchant, journey_id)
    if j["status"] != "open":
        raise APIError(409, "conflict", f"journey is {j['status']}, not open")
    return _summary(pipeline.close(merchant, j["journey_id"], "closed_by_merchant"))


@router.post("/journeys/{journey_id}/decline")
def principal_declined(journey_id: str, merchant=Depends(merchant_auth)):
    """The human principal said no. Rule R-03 makes that permanent for this agent."""
    j = _journey_or_404(merchant, journey_id)
    store.record_decline(merchant["merchant_id"], j["agent_id"])
    store.update_journey(merchant["merchant_id"], j["journey_id"], status="lost")
    store.ledger_append(merchant["merchant_id"], j["journey_id"], "principal", "declined",
                        outcome={"rule": "R-03"})
    return {"declined": True, "agent_id": j["agent_id"]}


@router.get("/reoffers/{ref}")
def reoffer(ref: str, merchant=Depends(merchant_auth)):
    """What the agent should be told. `ref` is a journey id or a checkout id.
    The merchant serves this to the agent from its own re-offer endpoint."""
    j = _journey_or_404(merchant, ref)
    offer = store.get_reoffer(merchant["merchant_id"], j["journey_id"])
    if offer is None or offer.get("expired") or j["status"] not in ("recovering",):
        return JSONResponse({"pending": False, "journey_id": j["journey_id"],
                             "status": j["status"]}, status_code=404)
    return {"pending": True, "journey_id": j["journey_id"], "offer": offer}


# ---------------------------------------------------------------- reading ---

@router.get("/metrics")
def metrics(since: float = 0.0, merchant=Depends(merchant_auth)):
    out = store.metrics(merchant["merchant_id"], since)
    for cause, row in out["by_cause"].items():
        row["name"] = CAUSES[cause].name if cause in CAUSES else "unclassified"
    out["refusals"] = {k: {"count": v, "rule": RULES.get(k, "")}
                       for k, v in sorted(out["refusals"].items())}
    out["interventions"] = {k: {"count": v, "name": INTERVENTIONS[k].name}
                            for k, v in sorted(out["interventions"].items())
                            if k in INTERVENTIONS}
    return out


@router.get("/ledger")
def ledger(journey_id: str = "", limit: int = 500, merchant=Depends(merchant_auth)):
    return {"entries": store.ledger(merchant["merchant_id"], journey_id or None,
                                    max(1, min(limit, 5000)))}


@router.get("/ledger/verify")
def ledger_verify(merchant=Depends(merchant_auth)):
    return store.verify_ledger(merchant["merchant_id"])


@router.get("/webhooks/deliveries")
def webhook_deliveries(limit: int = 50, merchant=Depends(merchant_auth)):
    return {"deliveries": store.deliveries(merchant["merchant_id"], limit=max(1, min(limit, 500)))}


@router.post("/webhooks/test")
def webhook_test(merchant=Depends(merchant_auth)):
    did = webhooks.emit(merchant, "", "ping", {"message": "Handshake webhook test"})
    return {"queued": did, "webhook_url": merchant["webhook_url"] or None}


@router.get("/taxonomy")
def taxonomy():
    """The closed vocabulary every diagnosis and verdict draws from. No auth."""
    return {"event_types": list(TYPES),
            "causes": {k: {"family": c.family.value, "name": c.name, "signal": c.signal,
                           "interventions": list(c.interventions)} for k, c in CAUSES.items()},
            "interventions": {k: {"name": i.name, "mechanism": i.mechanism,
                                  "concedes_margin": i.concedes_margin,
                                  "touches_human": i.touches_human, "rung": i.rung}
                              for k, i in INTERVENTIONS.items()},
            "rules": RULES}


def install(app):
    """Mount the router and its error handling on an existing FastAPI app."""

    @app.exception_handler(APIError)
    async def _api_error(_request, exc):
        return error_response(exc.status, exc.type, exc.message)

    app.include_router(router)
