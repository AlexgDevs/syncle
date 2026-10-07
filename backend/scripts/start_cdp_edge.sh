#!/usr/bin/env bash
# Start an Edge instance exposing a CDP debugging endpoint (ADR-004).
#
# Ozon rejects plain HTTP clients with a JS bot challenge, so
# src/modules/analytics/parsers/cdp.py performs its requests inside a
# real browser connected over CDP (OZON_CDP_URL, default
# http://127.0.0.1:9336).
#
# Notes:
#   - A regular (non-headless) window is required: Ozon answers HTTP 403
#     to headless user agents.
#   - A dedicated --user-data-dir is required: Chromium-based browsers
#     do not enable the debugging port on the default profile. This
#     profile also keeps the Ozon cookies warm (a cold profile may
#     answer 403 until it is warmed up).
#   - The script is idempotent: it exits immediately when the endpoint
#     is already reachable.
#
# Usage (from backend/):
#   bash scripts/start_cdp_edge.sh
#
# Environment:
#   CDP_PORT          debugging port (default: 9336)
#   EDGE_CDP_PROFILE  browser profile directory

set -euo pipefail

CDP_PORT="${CDP_PORT:-9336}"
CDP_URL="http://127.0.0.1:${CDP_PORT}/json/version"

if [ -n "${EDGE_CDP_PROFILE:-}" ]; then
  PROFILE_DIR="$EDGE_CDP_PROFILE"
elif [ -n "${LOCALAPPDATA:-}" ]; then
  PROFILE_DIR="$LOCALAPPDATA/Temp/opencode/edge-cdp"
else
  echo "LOCALAPPDATA is not set; export EDGE_CDP_PROFILE explicitly." >&2
  exit 1
fi

cdp_alive() {
  curl -fsS --max-time 2 "$CDP_URL" >/dev/null 2>&1
}

if cdp_alive; then
  echo "CDP already up: $CDP_URL"
  exit 0
fi

EDGE=""
for candidate in \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  "/c/Program Files/Microsoft/Edge/Application/msedge.exe"
do
  if [ -f "$candidate" ]; then
    EDGE="$candidate"
    break
  fi
done
if [ -z "$EDGE" ]; then
  echo "msedge.exe not found in Program Files." >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"
"$EDGE" \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$(cygpath -w "$PROFILE_DIR")" \
  --no-first-run \
  about:blank >/dev/null 2>&1 &

echo "Starting Edge (profile: $PROFILE_DIR) ..."
for _ in $(seq 1 30); do
  if cdp_alive; then
    echo "CDP ready: $CDP_URL"
    exit 0
  fi
  sleep 0.5
done
echo "CDP endpoint did not come up on port $CDP_PORT." >&2
exit 1
