from fastapi import APIRouter, Request
from typing import Any

# Import existing handlers to delegate
from . import health as health_router
from . import frontend_log as frontend_log_router

router = APIRouter()


@router.get("/api/health")
async def api_health_alias(request: Request):
    """Compatibility alias for /health -> /api/health"""
    return await health_router.health_check(request)


@router.get("/api/local/health")
async def api_local_health_alias(request: Request):
    """Compatibility alias for /api/local/health -> /api/health (Golden Drive acceptance)"""
    return await health_router.health_check(request)


@router.post("/api/frontend/log")
async def api_frontend_log_alias(request: Request):
    """Compatibility alias for /frontend/log -> /api/frontend/log"""
    # Be lenient: accept empty body or any payload
    try:
        body: Any = await request.json()
    except Exception:
        try:
            raw = await request.body()
            body = raw.decode('utf-8', errors='ignore') if raw else None
        except Exception:
            body = None
    return await frontend_log_router.frontend_log(request, body)
