#!/usr/bin/env bash
# Live operator console — the demo surface.
set -e
cd "$(dirname "$0")"
python3 -m uvicorn handshake.server.app:app --host 127.0.0.1 --port "${1:-8000}" --log-level warning
