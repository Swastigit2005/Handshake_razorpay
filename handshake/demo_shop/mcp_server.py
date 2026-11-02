"""An MCP endpoint for the demo store, so a real third-party agent can shop it.

Add `https://<host>/mcp` as a remote MCP server in Claude (claude.ai custom
connector, Claude Desktop, or `claude mcp add --transport http shop <url>`) or
any MCP client, then ask it to buy something. The agent's reasoning stays in
its own conversation; the store sees only the tool calls it makes, as HTTP; and
Handshake sees only what the store's SDK middleware reports. That is the honest
test: Handshake has to explain an agent nobody on this project wrote.

Implements the Streamable HTTP transport's request/response mode: JSON-RPC 2.0
over POST, JSON replies, a session id issued on `initialize`. It offers no
server-initiated stream (GET returns 405), which the specification allows.
"""

import threading
import time
import uuid

from .. import __version__
from .tools import TOOLS, StoreSession, as_text

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "You are connected to Kaveri Home & Tech, an Indian online store selling kitchen "
    "appliances, audio gear and laptop accessories. Prices are in INR before 18% GST. "
    "To buy: search or get a product, create_checkout (declare your user's spending cap), "
    "refresh_checkout to confirm the final total, then pay. If you decide not to buy, "
    "you may call check_for_offer: the store sometimes fixes a problem and comes back.")

SESSIONS = {}
_lock = threading.Lock()
MAX_SESSIONS = 500
SESSION_TTL = 6 * 3600


DEMO_STORE = {"prefix": "/shop/acp", "name": "kaveri-home-tech",
              "title": "Kaveri Home & Tech (demo store)", "instructions": INSTRUCTIONS}


def _session(sid, client_name, base_url, shop=DEMO_STORE):
    with _lock:
        now = time.time()
        for old in [k for k, v in SESSIONS.items() if now - v["seen"] > SESSION_TTL]:
            SESSIONS.pop(old, None)
        if len(SESSIONS) >= MAX_SESSIONS:
            SESSIONS.pop(min(SESSIONS, key=lambda k: SESSIONS[k]["seen"]), None)
        s = SESSIONS.get(sid)
        if s is None:
            label = "".join(c for c in (client_name or "mcp").lower() if c.isalnum())[:16] or "mcp"
            s = {"store": StoreSession(base_url, f"{label}_{sid[:8]}", prefix=shop["prefix"]),
                 "client": client_name, "shop": shop["name"], "created": now, "calls": []}
            SESSIONS[sid] = s
        s["seen"] = now
        return s


def _result(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(message, sid, base_url, shop=DEMO_STORE):
    """One JSON-RPC message → (reply or None, session id to return). `shop`
    chooses which store the agent is connected to."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "invalid JSON-RPC request"), sid
    method, rid, params = message.get("method"), message.get("id"), message.get("params") or {}
    if rid is None:                                    # a notification: no reply
        return None, sid

    if method == "initialize":
        sid = uuid.uuid4().hex
        client = (params.get("clientInfo") or {}).get("name", "mcp")
        _session(sid, client, base_url, shop)
        asked = params.get("protocolVersion")
        return _result(rid, {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": shop["name"], "title": shop["title"], "version": __version__},
            "instructions": shop["instructions"]}), sid
    if method == "ping":
        return _result(rid, {}), sid
    if method == "tools/list":
        return _result(rid, {"tools": [{"name": t["name"], "description": t["description"],
                                        "inputSchema": t["input_schema"]} for t in TOOLS]}), sid
    if method == "tools/call":
        if not sid:
            sid = uuid.uuid4().hex                     # tolerate clients that skip the header
        s = _session(sid, "mcp", base_url, shop)
        name = params.get("name")
        if name not in {t["name"] for t in TOOLS}:
            return _error(rid, -32602, f"unknown tool {name!r}"), sid
        out = s["store"].call(name, params.get("arguments") or {})
        s["calls"].append({"t": time.time(), "tool": name})
        failed = "error" in out and len(out) == 1
        return _result(rid, {"content": [{"type": "text", "text": as_text(out)}],
                             "isError": failed}), sid
    return _error(rid, -32601, f"method not found: {method}"), sid
