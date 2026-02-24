"""Diagnostics endpoints for controller teach flows."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .chuck_hardware import get_latest_input_event

router = APIRouter()


@router.get("/controller/diagnostics/next-event")
async def diagnostics_next_event(request: Request):
    """Proxy to controller input event endpoint."""
    return await get_latest_input_event(request)
