#!/usr/bin/env bash
set -euo pipefail

export AA_DRIVE_ROOT=/mnt/a
export FASTAPI_URL=http://localhost:8000

echo "Starting FastAPI (8000)"
(uvicorn backend.app:app --port 8000 >/dev/null 2>&1 &)
sleep 2

echo "Starting Gateway (8787)"
(node gateway/server.js >/dev/null 2>&1 &)
sleep 2

echo "Starting Frontend (Vite dev)"
(cd frontend && npm run dev &)

echo "Running smoke checks"
./scripts/smoke_bash.sh || exit $?

echo
echo "=============================================================="
echo "WSL NOTICE: USB gamepad/encoder detection is limited in WSL."
echo "- Install libusb:    sudo apt-get install -y libusb-1.0-0"
echo "- Enable usbipd:     (Windows Admin) winget install usbipd"
echo "                     usbipd wsl list; usbipd wsl attach --busid <BUSID>"
echo "- For best results, run backend on Windows: start-gui.bat"
echo "=============================================================="
