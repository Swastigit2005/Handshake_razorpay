"""Session recorder (component C3).

Captures every request and response crossing the merchant boundary, derives the
terminal state, and computes the at-risk basket value. Read-only: the recorder
never influences behaviour.
"""

import time
from dataclasses import dataclass, field

from ..taxonomy import Terminal


@dataclass
class Event:
    seq: int
    type: str
    request: dict
    response: dict
    http_status: int
    latency_ms: float
    ts: float

    def as_dict(self):
        return {
            "event_id": f"ev_{self.seq}",
            "seq": self.seq,
            "type": self.type,
            "request": self.request,
            "response": self.response,
            "http_status": self.http_status,
            "latency_ms": round(self.latency_ms, 2),
            "ts": self.ts,
        }


@dataclass
class Trace:
    session_id: str
    buyer_id: str
    persona: str
    arm: str
    spend_cap: float
    injected_fault: str = ""          # ground truth, never read by diagnosis
    events: list = field(default_factory=list)
    terminal_state: str = ""
    basket: list = field(default_factory=list)
    basket_value: float = 0.0
    at_risk_value: float = 0.0
    converted_value: float = 0.0
    abandon_note: str = ""
    created_at: float = field(default_factory=time.time)
    closed_at: float = 0.0

    _seq: int = 0

    def event(self, type_, request, response, http_status=200, latency_ms=0.0):
        self._seq += 1
        ev = Event(self._seq, type_, request, response, http_status, latency_ms, time.time())
        self.events.append(ev)
        return ev

    def last(self, type_):
        for ev in reversed(self.events):
            if ev.type == type_:
                return ev
        return None

    def all_of(self, type_):
        return [ev for ev in self.events if ev.type == type_]

    def close(self, state, value=0.0, note=""):
        self.terminal_state = state
        self.closed_at = time.time()
        self.abandon_note = note
        if state == Terminal.CONVERTED:
            self.converted_value = value
            self.at_risk_value = 0.0
        else:
            self.at_risk_value = value
        return self

    def as_dict(self):
        return {
            "session_id": self.session_id,
            "buyer_id": self.buyer_id,
            "persona": self.persona,
            "arm": self.arm,
            "spend_cap": self.spend_cap,
            "injected_fault": self.injected_fault,
            "terminal_state": self.terminal_state,
            "basket": self.basket,
            "basket_value": round(self.basket_value, 2),
            "at_risk_value": round(self.at_risk_value, 2),
            "converted_value": round(self.converted_value, 2),
            "abandon_note": self.abandon_note,
            "events": [e.as_dict() for e in self.events],
        }
