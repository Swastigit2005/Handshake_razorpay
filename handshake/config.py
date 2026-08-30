"""Runtime configuration and adapter switches.

Every simulated component is named here so that the README, the console and the
pitch can state honestly which parts are real and which are stand-ins.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv():
    """Read a .env file from the project root. No dependency, no overwrite of
    variables already set in the real environment."""
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        path = base / ".env"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return str(path)
    return ""


DOTENV_PATH = _load_dotenv()


def _env(name, default):
    return os.environ.get(name, default)


@dataclass
class PolicyConfig:
    max_reoffers_per_session: int = 2          # R-01
    max_interventions_per_buyer_24h: int = 3   # R-02
    concession_ceiling_pct: float = 0.08       # R-04, share of basket value
    gross_margin_pct: float = 0.22             # used by R-04 and R-05
    cost_machine_inr: float = 1.5              # R-05, cost of a machine re-offer
    cost_human_inr: float = 25.0               # R-05, cost of a human escalation
    intervention_cost_inr: float = 4.0         # blended, used in reporting
    abuse_window_abandonments: int = 3         # R-06
    max_mandate_retries: int = 2               # R-08
    quiet_hours: tuple = (21, 9)               # R-09, local hours [start, end)
    confidence_threshold: float = 0.70         # R-10
    kill_switch: bool = False                  # R-11
    price_lock_ttl_minutes: int = 15


@dataclass
class RunConfig:
    seed: int = 20260830
    batch_size: int = 500
    fault_incidence: float = 0.55
    # Demo only: put every session in the treatment arm. Never set this
    # for a measured run — it removes the control the lift depends on.
    force_treatment: bool = False
    treatment_share: float = 0.5

    # Adapters. "sim" is deterministic and offline; "razorpay" hits test mode.
    payments_backend: str = field(default_factory=lambda: _env("HS_PAYMENTS", "sim"))
    # "heuristic" is an offline decision policy; "llm" uses a real model.
    buyer_backend: str = field(default_factory=lambda: _env("HS_BUYERS", "heuristic"))

    razorpay_key_id: str = field(default_factory=lambda: _env("RAZORPAY_KEY_ID", ""))
    razorpay_key_secret: str = field(default_factory=lambda: _env("RAZORPAY_KEY_SECRET", ""))
    llm_api_key: str = field(default_factory=lambda: _env("HS_LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: _env("HS_LLM_MODEL", ""))
    llm_provider: str = field(default_factory=lambda: _env("HS_LLM_PROVIDER", ""))
    llm_base_url: str = field(default_factory=lambda: _env("HS_LLM_BASE_URL", ""))

    def llm_keys(self):
        """Ordered, de-duplicated key pool from every supported variable."""
        keys = []
        for raw in (_env("HS_LLM_API_KEYS", "").replace(" ", ",").split(",")):
            if raw.strip():
                keys.append(raw.strip())
        if self.llm_api_key:
            keys.append(self.llm_api_key)
        for n in range(2, 10):
            extra = _env(f"HS_LLM_API_KEY_{n}", "")
            if extra.strip():
                keys.append(extra.strip())
        seen, ordered = set(), []
        for key in keys:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        return ordered

    def resolve_key(self, key):
        """Provider and base URL for one key. Anything OpenAI-compatible —
        Groq, Together, OpenRouter, a local server — uses the openai client."""
        provider = self.llm_provider.lower()
        base = self.llm_base_url
        if not provider:
            if key.startswith("sk-ant-"):
                provider = "anthropic"
            elif key.startswith("gsk_"):
                provider, base = "openai_compatible", base or "https://api.groq.com/openai/v1"
            else:
                provider = "openai"
        if provider == "groq":
            provider, base = "openai_compatible", base or "https://api.groq.com/openai/v1"
        return provider, (base or None)

    def default_model(self, provider):
        if self.llm_model:
            return self.llm_model
        return "claude-3-5-haiku-latest" if provider == "anthropic" else "gpt-4o-mini"

    def llm_endpoints(self):
        """(key, provider, base_url, model) per key, in fallback order."""
        models = [m.strip() for m in _env("HS_LLM_MODELS", "").split(",") if m.strip()]
        out = []
        for i, key in enumerate(self.llm_keys()):
            provider, base = self.resolve_key(key)
            model = models[i] if i < len(models) else self.default_model(provider)
            out.append((key, provider, base, model))
        return out

    def resolved_llm(self):
        """Provider and base URL of the first key (kept for compatibility)."""
        keys = self.llm_keys()
        return self.resolve_key(keys[0]) if keys else (self.llm_provider or "openai", None)

    policy: PolicyConfig = field(default_factory=PolicyConfig)

    def simulated_components(self):
        out = []
        if self.payments_backend == "sim":
            out.append("payments (local simulator, no Razorpay call)")
        if self.buyer_backend == "heuristic":
            out.append("buyer agents (deterministic decision policy, not an LLM)")
        out.append("delegated spending caps (Reserve Pay not available to developers)")
        out.append("catalogue, mandates and buyers (synthetic)")
        return out
