#!/usr/bin/env bash
# Run a recovery batch. Everything works offline with no API keys.
set -e
cd "$(dirname "$0")"
python3 -m handshake.experiments.run --sessions "${1:-500}"
