#!/bin/sh
# Started by the SessionStart hook each time you run `claude`.
# Launches the krakeeb server in the background if it isn't already running,
# and returns immediately either way. The server stops itself once no Claude
# Code session has been alive for KRAKEEB_IDLE_MIN minutes (default 10).
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${KRAKEEB_PORT:-8765}"
DATA="${KRAKEEB_DATA_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/krakeeb}"

if curl -s -m 1 "http://127.0.0.1:$PORT/api/ping" 2>/dev/null | grep -q '"app":"krakeeb"'; then
  exit 0
fi

PY="$(command -v python3 || echo /usr/bin/python3)"
mkdir -p "$DATA"
# Detach fully so the server outlives the session that launched it.
nohup "$PY" "$DIR/server.py" >> "$DATA/server.log" 2>&1 < /dev/null &
exit 0
