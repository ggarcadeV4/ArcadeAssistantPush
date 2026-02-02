#!/usr/bin/env bash
# Portable gateway smoke: validates gateway health, backend passthrough, and launchbox proxy

set -euo pipefail

usage(){ echo "Usage: $0 [--no-start]" >&2; }

NO_START=false
if [[ "${NOSTART:-0}" == "1" ]]; then NO_START=true; fi
if [[ $# -gt 0 ]]; then
  case "${1:-}" in
    --no-start|-n) NO_START=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
fi

mkdir -p logs

# Kill 8787 unless no-start
killed="none"
if [[ "$NO_START" == false ]]; then
  if command -v lsof >/dev/null 2>&1; then
    if pids=$(lsof -ti:8787 -sTCP:LISTEN 2>/dev/null || true); then
      if [[ -n "$pids" ]]; then kill -9 $pids 2>/dev/null || true; killed="8787:$pids"; fi
    fi
  elif command -v fuser >/dev/null 2>&1; then
    if fuser -n tcp 8787 >/dev/null 2>&1; then fuser -k -n tcp 8787 >/dev/null 2>&1 || true; killed="8787:<fuser>"; fi
  fi
fi

# Ensure FASTAPI_URL
export FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:8000}"

# Start gateway unless no-start
pid="already running"
if [[ "$NO_START" == false ]]; then
  nohup node gateway/server.js > logs/gateway.out 2> logs/gateway.err &
  pid=$!
  sleep 2
fi

probe(){ curl -fsS --max-time "$2" "$1" >/dev/null 2>&1 && echo PASS || echo FAIL; }
snip(){ printf '%s' "$(echo "$1" | tr -d '\n' | sed -E 's/[[:space:]]+/ /g' | cut -c1-120)"; }

gw_body="$(curl -fsS --max-time 5 http://127.0.0.1:8787/api/health 2>/dev/null || true)"; gw_stat="$( [[ -n "$gw_body" ]] && echo PASS || echo FAIL )"
pt_body="$(curl -fsS --max-time 5 http://127.0.0.1:8787/api/local/health 2>/dev/null || true)"; pt_stat="$( [[ -n "$pt_body" ]] && echo PASS || echo FAIL )"

lb_json="$(curl -fsS --max-time 5 'http://127.0.0.1:8787/api/launchbox/games?limit=10' 2>/dev/null || true)"
lb_count="-1"
if [[ -n "$lb_json" ]]; then
  lb_count="$(python3 - <<'PY'
import sys,json
try:
  d=json.loads(sys.stdin.read() or '[]')
  print(len(d) if isinstance(d,list) else -1)
except Exception:
  print(-1)
PY
<<< "$lb_json")"
fi

echo "Gateway:"
echo "- /api/health: $gw_stat $(snip "$gw_body")"
echo
echo "Passthrough:"
echo "- /api/local/health: $pt_stat $(snip "$pt_body")"
echo
echo "LaunchBox:"
echo "- /api/launchbox/games?limit=10: $( [[ $lb_count -ge 0 ]] && echo PASS || echo FAIL )  count=$lb_count"
echo
echo "Meta:"
echo "- 8787 reset: $killed"
echo "- pid: $pid"
echo
echo "Verdict:"
if [[ "$gw_stat" == PASS && "$pt_stat" == PASS && ${lb_count:-0} -ge 1 ]]; then
  echo "- GREEN"
  exit 0
else
  cause="unknown"
  if [[ "$gw_stat" != PASS ]]; then cause="gateway health"; fi
  if [[ "$pt_stat" != PASS ]]; then cause="passthrough health"; fi
  if [[ ${lb_count:-0} -lt 1 ]]; then cause="launchbox count<=0"; fi
  echo "- RED ($cause)"
  exit 1
fi

