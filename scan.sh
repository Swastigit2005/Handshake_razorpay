#!/usr/bin/env bash
# Agent-Readiness scan — prevention rather than recovery.
set -e
cd "$(dirname "$0")"
python3 -m handshake.readiness.run --sessions "${1:-300}"
