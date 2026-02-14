#!/usr/bin/env bash
# Simple smoke test harness for Controller Chuck / PactoTech stack.

set -u

DEVICE_ID="${DEVICE_ID:-CAB-0001}"
PANEL="${PANEL:-controller}"
BASE="${BASE:-http://localhost:8787/api/local/controller/board}"

echo "=== PactoTech Smoke Test (Controller Chuck) ==="
echo "Device ID: ${DEVICE_ID}"
echo ""

maybe_pretty_print() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  else
    cat
  fi
}

request() {
  local label="$1"
  shift
  echo "${label}"
  curl -s "$@" | maybe_pretty_print
  echo ""
  echo "----"
}

request "[1] Board Sanity..." \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: state" \
  -H "x-panel: ${PANEL}" \
  "${BASE}/sanity"

request "[2] Repair (Dry Run)..." \
  -X POST \
  -H "content-type: application/json" \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: config" \
  -H "x-panel: ${PANEL}" \
  "${BASE}/repair" \
  -d '{"actions":["disable_turbo","disable_analog","soft_reset"],"dry_run":true}'

request "[3] Firmware Preview (Stub)..." \
  -X POST \
  -H "content-type: application/json" \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: config" \
  -H "x-panel: ${PANEL}" \
  "${BASE}/firmware/preview" \
  -d '{"firmware_file":"firmware/PactoTech_2000T_Firmware_STM32F103VBT6_20250112.bin"}'

request "[4] Mapping Recovery Preview..." \
  -X POST \
  -H "content-type: application/json" \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: config" \
  -H "x-panel: ${PANEL}" \
  "${BASE}/mapping/recover" \
  -d '{"duration_ms":30000}'

request "[5] Mapping Apply (Dry Run)..." \
  -X POST \
  -H "content-type: application/json" \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: config" \
  -H "x-panel: ${PANEL}" \
  "${BASE}/mapping/apply" \
  -d '{"mapping":{"mappings":{"p1.button1":{"pin":4,"type":"button"}}},"dry_run":true}'

echo "Smoke test completed. Review output above for any failures."
