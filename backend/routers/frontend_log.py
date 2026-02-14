from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime
from typing import Any
import json

router = APIRouter()

@router.post("/log")
async def frontend_log(request: Request, body: Any = Body(default=None)):
    try:
        drive_root = request.app.state.drive_root
        logs_dir = drive_root / ".aa" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "frontend_errors.jsonl"

        device = request.headers.get("x-device-id", "")
        panel = request.headers.get("x-panel", "")

        # Fallback: attempt to parse body if not provided by FastAPI
        if body is None:
            try:
                body = await request.json()
            except Exception:
                try:
                    raw = await request.body()
                    body = raw.decode('utf-8', errors='ignore') if raw else None
                except Exception:
                    body = None

        record = {
            "timestamp": datetime.now().isoformat(),
            "device": device,
            "panel": panel,
            "event": "frontend_log",
            "details": body,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return JSONResponse(status_code=200, content={"ok": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
