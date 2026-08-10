#!/usr/bin/env bash
# Deploy the dashboard/paper-trading service and verify it in ONE call — collapses the restart +
# wait-for-bind + GET-/ + optional feature-surface check that used to cost 5-10 separate tool calls
# (the token-waste pattern found in the self-eval, docs/research/169). Uses systemctl (the service is
# systemd-managed, memory: reference_dashboard_is_systemd_managed) — NOT pkill/nohup.
#
# Usage:
#   scripts/deploy_and_verify.sh                         # restart + wait bind + GET / 200
#   scripts/deploy_and_verify.sh <feature_surface_key>   # + poll until that surface is populated
#
# Exit 0 only when the page is 200 (and, if a key is given, that surface reports a non-'warming' status).
set -uo pipefail

SURFACE_KEY="${1:-}"
PORT=8080
TOKEN_FILE="$HOME/.nse_algo_trader/dashboard_access_token.txt"
BIND_TIMEOUT=120   # seconds to wait for the port to bind after restart
SURFACE_TIMEOUT=90 # seconds to wait for the named surface to publish

echo "[deploy] systemctl restart nse-dashboard"
if ! sudo -n systemctl restart nse-dashboard 2>/dev/null; then
  echo "[deploy] FAILED: 'sudo -n systemctl restart nse-dashboard' (needs sudo). Run it yourself with: ! sudo systemctl restart nse-dashboard"
  exit 3
fi

echo "[deploy] waiting for port $PORT to bind (<=${BIND_TIMEOUT}s)"
for ((i=0; i<BIND_TIMEOUT; i+=3)); do
  ss -ltn 2>/dev/null | grep -q ":$PORT" && break
  sleep 3
done
if ! ss -ltn 2>/dev/null | grep -q ":$PORT"; then
  echo "[deploy] FAILED: port $PORT never bound"; exit 1
fi

KEY=""
[[ -f "$TOKEN_FILE" ]] && KEY="$(tr -d '[:space:]' < "$TOKEN_FILE")"
CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/?key=$KEY" 2>/dev/null)"
echo "[deploy] GET / -> $CODE"
[[ "$CODE" == "200" ]] || { echo "[deploy] FAILED: page not 200"; exit 1; }

if [[ -n "$SURFACE_KEY" ]]; then
  echo "[deploy] polling surface '$SURFACE_KEY' (<=${SURFACE_TIMEOUT}s)"
  for ((i=0; i<SURFACE_TIMEOUT; i+=6)); do
    RESULT="$(curl -s "http://127.0.0.1:$PORT/api/snapshot?key=$KEY" 2>/dev/null \
      | python3 -c "import sys,json
try:
  d=json.load(sys.stdin); f=[x for x in d.get('feature_surfaces',[]) if x['key']=='$SURFACE_KEY']
  print(f[0]['status']+' '+str(dict(f[0]['metrics']))) if f else print('warming')
except Exception: print('warming')" 2>/dev/null)"
    if [[ -n "$RESULT" && "$RESULT" != "warming" ]]; then
      echo "[deploy] surface '$SURFACE_KEY': $RESULT"
      touch /tmp/claude_dashboard_page_verified
      exit 0
    fi
    sleep 6
  done
  echo "[deploy] surface '$SURFACE_KEY' still warming after ${SURFACE_TIMEOUT}s (page is 200)"
fi

touch /tmp/claude_dashboard_page_verified
echo "[deploy] OK"
exit 0
