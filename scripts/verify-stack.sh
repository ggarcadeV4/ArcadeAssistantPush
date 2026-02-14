#!/usr/bin/env bash
# Combined smoke: runs verify-cache then verify-gateway and prints a single verdict

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

run_step(){
  local label="$1"; shift
  echo "[stack] running: $label"
  if "$@" | tee "logs/smoke.${label}.out"; then
    echo "${label}:GREEN"
  else
    echo "${label}:RED"
  fi
}

cache_cmd=(bash scripts/verify-cache.sh)
gateway_cmd=(bash scripts/verify-gateway.sh)
if [[ "$NO_START" == true ]]; then
  cache_cmd=(bash scripts/verify-cache.sh --no-start)
  gateway_cmd=(bash scripts/verify-gateway.sh --no-start)
fi

cache_status=$(run_step cache "${cache_cmd[@]}" | tail -n1)
gw_status=$(run_step gateway "${gateway_cmd[@]}" | tail -n1)

cache_state=${cache_status#*:}
gw_state=${gw_status#*:}

echo
echo "Stack Smoke:"
echo "- cache:   $cache_state"
echo "- gateway: $gw_state"
echo
echo "Verdict:"
if [[ "$cache_state" == GREEN && "$gw_state" == GREEN ]]; then
  echo "- GREEN"
  exit 0
else
  echo "- RED"
  exit 1
fi

