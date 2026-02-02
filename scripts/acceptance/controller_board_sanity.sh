#!/usr/bin/env bash
set -euo pipefail

FASTAPI_URL=${FASTAPI_URL:-http://localhost:8000}
DEVICE_ID=${DEVICE_ID:-"USB\\VID_1209&PID_2000"}

curl -sS \
  -H "x-device-id: ${DEVICE_ID}" \
  -H "x-scope: state" \
  -H "x-panel: controller" \
  "${FASTAPI_URL}/api/local/controller/board/sanity"
