from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.services.cabinet_identity import load_cabinet_identity


class DeviceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        device_id = request.headers.get("x-device-id") or ""

        if not device_id:
            try:
                drive_root = getattr(request.app.state, "drive_root", None)
                identity = load_cabinet_identity(drive_root)
                device_id = identity.device_id or ""
            except Exception:
                device_id = ""

        request.state.device_id = device_id or ""
        response: Response = await call_next(request)
        if device_id and "x-device-id" not in response.headers:
            response.headers["x-device-id"] = device_id
        return response
