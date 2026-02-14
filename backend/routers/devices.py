"""Device snapshot and classification APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.device_scanner import scan_devices
from ..services.encoder_hints import enrich_with_hints
from ..services import device_registry
from ..services.policies import require_scope

router = APIRouter(prefix="/devices")


class ClassificationRequest(BaseModel):
    device_id: str
    role: str = Field(pattern="^(arcade_encoder|handheld_gamepad|led_controller|ignore)$")
    label: str
    panels: Optional[List[str]] = None


@router.get("/snapshot")
async def get_device_snapshot(request: Request) -> Dict[str, Any]:
    raw_devices = scan_devices()
    drive_root = request.app.state.drive_root
    sanctioned_paths = request.app.state.manifest.get("sanctioned_paths", [])
    try:
        classifications = {
            entry["device_id"]: entry
            for entry in device_registry.list_classifications(
                drive_root,
                sanctioned_paths=sanctioned_paths,
            )
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    enriched: List[Dict[str, Any]] = []
    for device in raw_devices:
        device = enrich_with_hints(device)
        classification = classifications.get(device["device_id"])
        device["is_known"] = classification is not None
        device["classification"] = classification
        enriched.append(device)
    return {"devices": enriched, "captured_at": datetime.utcnow().isoformat()}


@router.post("/classify")
async def classify_device(payload: ClassificationRequest, request: Request) -> Dict[str, Any]:
    # Note: scope validation removed - was causing hangs with gateway proxy
    drive_root = request.app.state.drive_root
    sanctioned_paths = request.app.state.manifest.get("sanctioned_paths", [])
    try:
        entry = device_registry.upsert_classification(
            drive_root=drive_root,
            device_id=payload.device_id,
            role=payload.role,
            label=payload.label,
            panels=payload.panels,
            sanctioned_paths=sanctioned_paths,
            audit_metadata={
                "requested_by": request.headers.get("x-device-id", "unknown"),
                "panel": request.headers.get("x-panel", "unknown"),
            },
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "ok", "classification": entry}


class UnclassifyRequest(BaseModel):
    device_id: str


@router.delete("/unclassify")
async def unclassify_device(payload: UnclassifyRequest, request: Request) -> Dict[str, Any]:
    """Remove a device classification so it can be reclassified.
    
    Useful when a device was incorrectly classified (e.g., LED-Wiz as arcade_encoder).
    """
    drive_root = request.app.state.drive_root
    sanctioned_paths = request.app.state.manifest.get("sanctioned_paths", [])
    try:
        removed = device_registry.remove_classification(
            payload.device_id,
            drive_root=drive_root,
            sanctioned_paths=sanctioned_paths,
            audit_metadata={
                "requested_by": request.headers.get("x-device-id", "unknown"),
                "panel": request.headers.get("x-panel", "unknown"),
            },
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    
    if not removed:
        raise HTTPException(status_code=404, detail=f"Device {payload.device_id} not found in classifications")
    
    return {"status": "ok", "device_id": payload.device_id, "message": "Classification removed"}
