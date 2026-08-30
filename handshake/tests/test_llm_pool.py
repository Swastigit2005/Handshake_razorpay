"""The key pool: rotate on a spent daily quota, stop only when all are spent."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from handshake.buyers.llm import (  # noqa: E402
    LLMBudgetExhausted, LLMDecider, _parse_decision, _quota_scope,
    _retry_after_seconds)
from handshake.config import RunConfig  # noqa: E402

TPD = ("Rate limit reached for model `x` in organization `org_1` service tier "
       "`on_demand` on tokens per day (TPD): Limit 200000, Used 199896, "
       "Requested 470. Please try again in 2m38.112s.")
TPM = ("Rate limit reached on tokens per minute (TPM). "
       "Please try again in 4.5s")


class Persona:
    budget, cap, posture = 5000, 4000, "strict"


VIEW = {"title": "In-Ear Monitors", "price": 2499,
        "attributes": {"driver_mm": 12}, "policy": {"structured": True}}
REQUIRED = ["driver_mm", "codec_support"]


class FakeMessage:
    def __init__(self, content):
        self.content = content
        self.reasoning = None


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content, tokens=120):
        self.choices = [FakeChoice(content)]
        self.usage = types.SimpleNamespace(total_tokens=tokens)


class FakeClient:
    """Raises `error` for the first `fail_times` calls, then answers."""

    def __init__(self, error=None, fail_times=0, answer='{"proceed": false}'):
        self.error, self.remaining, self.answer = error, fail_times, answer
        self.calls = 0
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise RuntimeError(self.error)
        return FakeResponse(self.answer)


def _clear(monkeypatch):
    """No stray key from a real .env may join a pool a test controls."""
    for name in ("HS_LLM_API_KEY", "HS_LLM_MODELS", "HS_LLM_PROVIDER", "HS_LLM_BASE_URL"):
        monkeypatch.setenv(name, "")
    for n in range(2, 10):
        monkeypatch.setenv(f"HS_LLM_API_KEY_{n}", "")


def _pool(monkeypatch, n=3):
    _clear(monkeypatch)
    monkeypatch.setenv("HS_LLM_API_KEYS", ",".join(f"gsk_key{i}aaaaaaaaaa" for i in range(n)))
    monkeypatch.setenv("HS_LLM_MODEL", "openai/gpt-oss-20b")
    decider = LLMDecider(RunConfig())
    for endpoint in decider.endpoints:
        endpoint.client = FakeClient()
        endpoint.exhausted = False
        endpoint.error = ""
    return decider


# ---------------- classification ----------------

def test_daily_and_minute_quotas_are_told_apart():
    assert _quota_scope(TPD) == "day"
    assert _quota_scope(TPM) == "minute"
    assert round(_retry_after_seconds(TPD), 1) == 158.1
    assert _retry_after_seconds(TPM) == 4.5


# ---------------- pool behaviour ----------------

def test_three_keys_are_configured_in_order(monkeypatch):
    decider = _pool(monkeypatch, 3)
    assert len(decider.endpoints) == 3
    assert [e.label for e in decider.endpoints] == ["key1", "key2", "key3"]
    assert decider.available()


def test_a_spent_key_rotates_to_the_next(monkeypatch):
    decider = _pool(monkeypatch, 3)
    decider.endpoints[0].client = FakeClient(error=TPD, fail_times=99)

    assert decider.decide(Persona(), VIEW, REQUIRED) is False
    assert decider.endpoints[0].exhausted, "the spent key must be retired"
    assert decider.rotations == 1
    assert decider.endpoints[1].calls >= 1, "the next key must have served it"
    assert decider.failures == 0, "a rotation is not a decision failure"


def test_all_keys_spent_raises_rather_than_falling_back(monkeypatch):
    decider = _pool(monkeypatch, 3)
    for endpoint in decider.endpoints:
        endpoint.client = FakeClient(error=TPD, fail_times=99)

    with pytest.raises(LLMBudgetExhausted) as excinfo:
        decider.decide(Persona(), VIEW, REQUIRED)
    assert "3 key(s)" in str(excinfo.value)
    assert not decider.available()


def test_per_minute_limit_waits_instead_of_burning_a_key(monkeypatch):
    decider = _pool(monkeypatch, 2)
    decider.endpoints[0].client = FakeClient(error=TPM, fail_times=1)
    slept = []
    monkeypatch.setattr("handshake.buyers.llm.time.sleep", slept.append)

    assert decider.decide(Persona(), VIEW, REQUIRED) is False
    assert slept and slept[0] == pytest.approx(5.0)
    assert not decider.endpoints[0].exhausted, "a per-minute pause must not retire a key"
    assert decider.rotations == 0


def test_an_invalid_key_is_retired_not_retried(monkeypatch):
    decider = _pool(monkeypatch, 2)
    decider.endpoints[0].client = FakeClient(
        error="Error code: 401 - invalid api key", fail_times=99)

    assert decider.decide(Persona(), VIEW, REQUIRED) is False
    assert decider.endpoints[0].exhausted
    assert "rejected" in decider.endpoints[0].error


def test_tokens_are_attributed_per_key(monkeypatch):
    decider = _pool(monkeypatch, 2)
    decider.decide(Persona(), VIEW, REQUIRED)
    decider.decide(Persona(), VIEW, REQUIRED)
    assert decider.endpoints[0].tokens == 240
    assert decider.tokens == 240
    assert decider.endpoints[1].tokens == 0


def test_mixed_model_pool_is_reported(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HS_LLM_API_KEYS", "gsk_aaaaaaaaaaaa,sk-ant-bbbbbbbbbbbb")
    monkeypatch.setenv("HS_LLM_MODELS", "openai/gpt-oss-20b,claude-3-5-haiku-latest")
    decider = LLMDecider(RunConfig())
    assert [e.model for e in decider.endpoints] == [
        "openai/gpt-oss-20b", "claude-3-5-haiku-latest"]
    assert [e.provider for e in decider.endpoints] == [
        "openai_compatible", "anthropic"]


def test_prompt_stays_small(monkeypatch):
    """The compact prompt is what keeps a batch inside a daily quota."""
    decider = _pool(monkeypatch, 1)
    sent = {}

    def capture(**kwargs):
        sent["prompt"] = kwargs["messages"][0]["content"]
        return FakeResponse('{"proceed": true}')

    decider.endpoints[0].client.chat.completions.create = capture
    decider.decide(Persona(), VIEW, REQUIRED)
    assert len(sent["prompt"]) < 700, "prompt has grown; the quota maths no longer holds"
    assert "codec_support" in sent["prompt"], "the missing attribute must be stated"


def test_parser_handles_what_models_actually_return():
    assert _parse_decision('{"proceed": false}') is False
    assert _parse_decision('```json\n{"proceed": true}\n```') is True
    assert _parse_decision('Sure. {"proceed": false} — codec missing.') is False
    assert _parse_decision('proceed: true') is True
    assert _parse_decision('') is None


def test_a_rejected_json_schema_is_retried_without_it(monkeypatch):
    """Groq returns json_validate_failed when the model emits nothing under
    response_format. Dropping the parameter must save the decision."""
    decider = _pool(monkeypatch, 1)
    seen = []

    def create(**kwargs):
        seen.append("response_format" in kwargs)
        if "response_format" in kwargs:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': \"Failed to validate JSON. "
                "Please adjust your prompt.\", 'code': 'json_validate_failed'}}")
        return FakeResponse('{"proceed": true}')

    decider.endpoints[0].client.chat.completions.create = create
    assert decider.decide(Persona(), VIEW, REQUIRED) is True
    assert True in seen and False in seen, "it must try with, then without"
    assert decider.failures == 0
