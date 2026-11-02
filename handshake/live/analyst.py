"""The analyst: a language model that reads a trace nobody wrote a rule for.

The deterministic detectors recognise thirteen known signatures and two general
ones. Real agents will stop for reasons outside all of them. When the detectors
cannot explain a stop with confidence, the analyst is asked the same question a
merchant would ask a sharp colleague: here is everything my server saw, here is
what I sell — why did this agent leave, and what could I offer it?

Constraints, all enforced in code rather than requested in the prompt:

  - it sees only the merchant-side trace and catalogue, as the detectors do
  - it must cite event numbers; citations that don't exist are dropped, and a
    hypothesis with no valid citation is discarded
  - it may map to a known cause or name a new one (family N3)
  - its score is capped at NOVEL_CAP, below R-10's threshold: a model can
    explain and draft, never move money. A person approves.

Uses the same key pool as the model buyers (HS_LLM_API_KEYS; Anthropic, OpenAI,
Groq or any OpenAI-compatible endpoint). With no key, it is simply absent and
the system behaves exactly as before. HS_ANALYST=0 turns it off.
"""

import json
import logging
import os
import re
import threading

from ..taxonomy import CAUSES
from .detectors import NOVEL_CAP, Hypothesis, current_sku

log = logging.getLogger("handshake.analyst")

PROMPT = """You are diagnosing an abandoned purchase for an online shop. An AI shopping agent,
acting for a human, browsed and/or started checkout, then stopped without paying. The
agent never says why. Below is everything the shop's server recorded, in order, and the
shop's catalogue for the agent's category.

Your job: work out the most likely reason the agent stopped, citing the events that show
it, and draft one concrete thing the shop could offer the agent so it completes the
purchase. Be specific to this trace. If the evidence is weak, say so with a low confidence.

Known causes (use one of these ids if it fits, otherwise use "NOVEL"):
{causes}

TRACE (event number · type · HTTP status · request → response):
{trace}

CATALOGUE (same category; source-of-truth records):
{catalogue}

Reply with ONE JSON object and nothing else:
{{"cause": "<known id or NOVEL>",
  "label": "<short_snake_case_name_for_the_reason>",
  "explanation": "<2 sentences to the shop owner, plain words, what happened and why>",
  "evidence": [<event numbers that support it>],
  "confidence": <0.0 to 1.0>,
  "proposal": {{"action": "alternative_product" | "alternate_instrument" | "retry" | "information",
                "sku": "<catalogue sku, only for alternative_product>",
                "message": "<what the shop tells the agent, one or two sentences>",
                "merchant_change": "<what the shop should fix on its side>"}}}}
"""

_ACTIONS = {"alternative_product", "alternate_instrument", "retry", "information"}
_lock = threading.Lock()
_decider = None


def enabled():
    return os.environ.get("HS_ANALYST", "1").lower() not in ("0", "false", "no")


def _client():
    """Shared, lazily built model client. None when no key is configured."""
    global _decider
    if not enabled():
        return None
    with _lock:
        if _decider is None:
            from ..buyers.llm import LLMDecider
            from ..config import RunConfig
            decider = LLMDecider(RunConfig())
            decider.max_tokens = int(os.environ.get("HS_ANALYST_MAX_TOKENS", "900"))
            _decider = decider
    return _decider if _decider.available() else None


def available():
    try:
        return _client() is not None
    except Exception:
        return False


def _short(value, limit=420):
    text = json.dumps(value, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "…"


def render_prompt(events, catalogue):
    causes = "\n".join(f"  {k}: {c.name.replace('_', ' ')} — {c.signal}"
                       for k, c in CAUSES.items() if c.family.value != "N")
    lines = []
    for e in events:
        lines.append(f"  {e['seq']} · {e['type']} · {e['http_status']} · "
                     f"{_short(e.get('request') or {}, 200)} → {_short(e.get('response') or {})}")
    cat = "\n".join(f"  {_short({k: p.get(k) for k in ('sku', 'title', 'price', 'stock', 'attributes', 'policy', 'fulfilment')}, 380)}"
                    for p in catalogue[:12])
    return PROMPT.format(causes=causes, trace="\n".join(lines), catalogue=cat or "  (none synced)")


def parse(text, events, catalogue):
    """Validate a model reply into a Hypothesis, or None. Never trusts the model:
    every field is checked against the trace and the catalogue."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        raw = json.loads(match.group(0))
    except ValueError:
        return None
    seqs = {e["seq"]: e for e in events}
    cited = []
    for n in raw.get("evidence") or []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if n in seqs and n not in cited:
            cited.append(n)
    if not cited:
        return None                         # an explanation with no evidence is a guess
    cause = str(raw.get("cause") or "NOVEL").upper()
    if cause not in CAUSES or CAUSES[cause].family.value == "N":
        cause = "N3"
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    score = round(min(NOVEL_CAP, max(0.0, confidence) * NOVEL_CAP), 2)
    label = re.sub(r"[^a-z0-9_]+", "_", str(raw.get("label") or "unlabelled").lower())[:48]
    explanation = str(raw.get("explanation") or "").strip()[:600]
    if not explanation:
        return None

    proposal = raw.get("proposal") or {}
    action = str(proposal.get("action") or "information")
    if action not in _ACTIONS:
        action = "information"
    skus = {p.get("sku") for p in catalogue}
    sku = proposal.get("sku")
    if action == "alternative_product" and sku not in skus:
        action, sku = "information", None   # the model may not invent a product
    clean = {"action": action, "message": str(proposal.get("message") or "")[:400],
             "merchant_change": str(proposal.get("merchant_change") or "")[:400],
             "source": "analyst"}
    if action == "alternative_product":
        clean["sku"] = sku
    if not clean["message"]:
        clean = None

    h = Hypothesis(cause, score, explanation,
                   [{"event": n, "type": seqs[n]["type"], "what": "cited by the analyst"}
                    for n in cited],
                   {"label": label, "model_confidence": confidence, "method": "analyst",
                    "proposal": clean, "sku": current_sku_from(events)})
    return h


def current_sku_from(events):
    from .detectors import Trace
    return current_sku(Trace(events))


def review(events, catalogue, complete=None):
    """Ask the model. `complete(prompt) -> text` is injectable for tests. Returns
    a Hypothesis or None; any failure is logged and returns None, because the
    analyst is an aid and must never stop a diagnosis from being recorded."""
    try:
        if complete is None:
            client = _client()
            if client is None:
                return None
            complete = client._complete
        text = complete(render_prompt(events, catalogue))
        return parse(text, events, catalogue)
    except Exception as exc:
        log.warning("analyst unavailable for this journey: %s", exc)
        return None


__all__ = ["available", "review", "parse", "render_prompt"]
