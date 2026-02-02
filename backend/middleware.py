from __future__ import annotations

import json
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class DeviceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        device_id = request.headers.get("x-device-id")

        # Fallback to env
        if not device_id:
            device_id = (os.getenv("AA_DEVICE_ID", "") or "").strip()

        # Fallback to Drive A device_id.txt then manifest
        if not device_id:
            try:
                drive_root = getattr(request.app.state, "drive_root", None)
                if drive_root:
                    # device_id.txt has priority
                    txt = drive_root / ".aa" / "device_id.txt"
                    if txt.exists():
                        device_id = (txt.read_text(encoding="utf-8").strip() or "")
                    # legacy/structured manifests
                    for name in ("cabinet_manifest.json", "manifest.json"):
                        p = drive_root / ".aa" / name
                        if p.exists():
                            data = json.loads(p.read_text(encoding="utf-8"))
                            device_id = (data.get("device_id") or data.get("id") or "").strip()
                            if device_id:
                                break
            except Exception:
                # Silent fallback; Supabase is optional
                pass

        request.state.device_id = device_id or ""
        response: Response = await call_next(request)
        # Echo header for visibility (non-invasive)
        if device_id and "x-device-id" not in response.headers:
            response.headers["x-device-id"] = device_id
        return response
