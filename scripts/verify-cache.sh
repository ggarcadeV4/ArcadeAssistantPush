#!/usr/bin/env bash
# Portable smoke check for backend health + cache warm (Bash/WSL)

set -euo pipefail

usage() {
  echo "Usage: $0 [--no-start]" >&2
  echo "       NOSTART=1 $0    # env alternative to skip start" >&2
}

NO_START=false
# Allow env override: NOSTART=1
if [[ "${NOSTART:-0}" == "1" ]]; then
  NO_START=true
fi
if [[ $# -gt 0 ]]; then
  case "${1:-}" in
    --no-start|-n) NO_START=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
fi

mkdir -p logs

# A) Kill anything on 8000 unless --no-start
killed="none"
if [[ "${NO_START}" == false ]]; then
  if command -v lsof >/dev/null 2>&1; then
    if pids=$(lsof -ti:8000 -sTCP:LISTEN 2>/dev/null || true); then
      if [[ -n "${pids}" ]]; then
        kill -9 ${pids} 2>/dev/null || true
        killed="8000:${pids}"
      fi
    fi
  elif command -v fuser >/dev/null 2>&1; then
    if fuser -n tcp 8000 >/dev/null 2>&1; then
      fuser -k -n tcp 8000 >/dev/null 2>&1 || true
      killed="8000:<fuser>"
    fi
  else
    pid=$(ss -ltnp 2>/dev/null | awk '$4 ~ /:8000$/ {print $6}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n1)
    if [[ -n "${pid:-}" ]]; then
      kill -9 "${pid}" 2>/dev/null || true
      killed="8000:${pid}"
    fi
  fi
fi

# B) Environment
export AA_PRELOAD_LB_CACHE=true
export PYTHONUNBUFFERED=1
# Prefer /mnt/a if visible (WSL); otherwise fall back to Windows path for Git Bash
if [[ -z "${AA_DRIVE_ROOT:-}" ]]; then
  if [[ -d "/mnt/a/LaunchBox/Data/Platforms" ]]; then
    export AA_DRIVE_ROOT="/mnt/a/"
  else
    export AA_DRIVE_ROOT="A:\\"
  fi
fi

# C) Start backend (unless --no-start)
pid="already running"
if [[ "${NO_START}" == false ]]; then
  nohup python3 -m uvicorn backend.app:app \
    --host 127.0.0.1 --port 8000 --log-level info \
    > logs/backend.out 2> logs/backend.err &
  pid=$!
  sleep 2
fi

# D) Find glob pre-check line in logs (aliases match requested variable names)
globLine="$(grep -a 'LaunchBox XML glob pre-check:' logs/backend.out logs/backend.err 2>/dev/null | tail -n 1 || true)"
globN="$(printf "%s" "${globLine:-}" | sed -n 's/.*files_found=\([0-9][0-9]*\).*/\1/p')"
globN="${globN:-0}"

probe() {
  local url="$1"; local t="$2"
  if curl -fsS --max-time "${t}" "${url}" >/dev/null 2>&1; then
    echo "OK"
  else
    local rc=$?
    [[ $rc -eq 28 ]] && echo "TIMEOUT" || echo "ERROR"
  fi
}

# E) Warm + probes
h1="$(probe 'http://127.0.0.1:8000/health' 5)"
w2="$(probe 'http://127.0.0.1:8000/api/launchbox/platforms' 30)"
w3="$(probe 'http://127.0.0.1:8000/api/launchbox/games?limit=20000' 30)"

count="-1"
if content="$(curl -fsS --max-time 5 'http://127.0.0.1:8000/api/launchbox/games?limit=200' 2>/dev/null || true)"; then
  if [[ -n "${content}" ]]; then
    count="$(python3 - <<'PY'
import sys, json
try:
  data = json.loads(sys.stdin.read())
  print(len(data) if isinstance(data, list) else -1)
except Exception:
  print(-1)
PY
<<< "${content}")"
  fi
fi

# F) Output summary
echo "Backend:"
echo "- 8000 reset: ${killed}"
echo "- pid: ${pid}"
echo
echo "Glob:"
echo "- line: \"${globLine:-n/a}\""
echo
echo "Warm:"
echo "- /health (5s): ${h1}"
echo "- /platforms (30s): ${w2}"
echo "- /games?limit=20000 (30s): ${w3}"
echo "- /games?limit=200 (5s): OK  count=${count}"
echo
echo "Verdict:"
if [[ ${globN:-0} -gt 0 && ${h1} == OK && ${count:-0} -gt 100 ]]; then
  echo "- GREEN"
  exit 0
else
  cause="unknown"
  if [[ ${globN:-0} -le 0 ]]; then
    cause="files_found=0"
  elif [[ ${w2} == TIMEOUT || ${w3} == TIMEOUT ]]; then
    cause="warm TIMEOUT"
  elif [[ ${count:-0} -le 100 ]]; then
    cause="count<=100"
  fi
  echo "- RED (${cause})"
  exit 1
fi
