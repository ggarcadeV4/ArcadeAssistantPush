from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional

from backend.services.console_wizard_manager import ConsoleWizardManager
from backend.services.policies import require_scope

router = APIRouter(prefix="/local/console_wizard", tags=["console-wizard"])


def _manager(request: Request) -> ConsoleWizardManager:
    drive_root = getattr(request.app.state, "drive_root", None)
    manifest = getattr(request.app.state, "manifest", {}) or {}
    if drive_root is None:
        raise HTTPException(status_code=500, detail="drive_root missing from app state")

    # Ensure manifest has sanctioned_paths to prevent initialization errors
    if "sanctioned_paths" not in manifest:
        manifest["sanctioned_paths"] = [
            "config/mappings",
            "config/mame",
            "config/retroarch",
            "config/controllers",
            "configs",
            "state",
            "backups",
            "logs",
            "emulators"
        ]

    return ConsoleWizardManager(drive_root, manifest)


class EmulatorFilter(BaseModel):
    emulators: Optional[List[str]] = Field(
        default=None, description="Subset of emulator IDs to target"
    )


class GenerateConfigsRequest(EmulatorFilter):
    dry_run: bool = True


class RestoreRequest(BaseModel):
    dry_run: bool = False


class SyncRequest(EmulatorFilter):
    force: bool = False
    dry_run: bool = False


class ChuckStatusResponse(BaseModel):
    currentMappingHash: str
    lastSyncedHash: Optional[str]
    isOutOfSync: bool

class ConfigContentsResponse(BaseModel):
    emulator: str
    current_file: Optional[str]
    defaults_file: Optional[str]
    current_text: str
    defaults_text: str
    current_truncated: bool = False
    defaults_truncated: bool = False


@router.get("/emulators")
async def list_emulators(request: Request):
    """Return the discovered console emulator inventory (CW-01)."""
    require_scope(request, "state")
    manager = _manager(request)
    return {"emulators": manager.list_emulators()}


@router.post("/generate-configs")
async def generate_configs(
    request: Request,
    payload: GenerateConfigsRequest = Body(default_factory=GenerateConfigsRequest),
):
    """Generate current Console Wizard configs for each emulator (CW-03)."""
    require_scope(request, "config" if not payload.dry_run else "state")
    manager = _manager(request)
    device_id = request.headers.get("x-device-id")
    results = manager.generate_configs(
        payload.emulators, dry_run=payload.dry_run, log_action="generate_configs", device_id=device_id
    )
    return {"dry_run": payload.dry_run, "results": results}


@router.post("/set-defaults")
async def set_defaults(
    request: Request,
    payload: EmulatorFilter = Body(default_factory=EmulatorFilter),
):
    """Snapshot the current configs into defaults (CW-04)."""
    require_scope(request, "config")
    manager = _manager(request)
    results = manager.snapshot_defaults(payload.emulators)
    return {"results": results}


@router.get("/health")
async def health(request: Request):
    """Compare defaults vs current configs and return per-emulator status (CW-05)."""
    require_scope(request, "state")
    manager = _manager(request)
    return {"status": manager.health()}


@router.post("/restore/{emulator}")
async def restore_emulator(
    emulator: str,
    request: Request,
    payload: RestoreRequest = Body(default_factory=RestoreRequest),
):
    """Restore a single emulator from defaults (CW-06)."""
    require_scope(request, "config" if not payload.dry_run else "state")
    manager = _manager(request)
    result = manager.restore_emulator(emulator, dry_run=payload.dry_run)
    return result


@router.post("/restore-all")
async def restore_all(
    request: Request,
    payload: RestoreRequest = Body(default_factory=RestoreRequest),
):
    """Restore all emulators from defaults (CW-07)."""
    require_scope(request, "config" if not payload.dry_run else "state")
    manager = _manager(request)
    results = manager.restore_all(dry_run=payload.dry_run)
    return {"dry_run": payload.dry_run, "results": results}


@router.post("/sync-from-chuck")
async def sync_from_chuck(
    request: Request,
    payload: SyncRequest = Body(default_factory=SyncRequest),
):
    """Detect controls.json changes and regenerate configs (CW-08/CW-09)."""
    require_scope(request, "config" if not payload.dry_run else "state")
    manager = _manager(request)
    device_id = request.headers.get("x-device-id")
    result = manager.sync_from_chuck(payload.emulators, force=payload.force, dry_run=payload.dry_run, device_id=device_id)
    return result


@router.get("/status/chuck", response_model=ChuckStatusResponse)
async def chuck_status(request: Request):
    """Check if Console Wizard is in sync with Controller Chuck mappings (CW-10)."""
    require_scope(request, "state")
    try:
        manager = _manager(request)
        status = manager.get_chuck_status()
        return status
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load Chuck status: {str(exc)}"
        )


@router.get("/config/{emulator}", response_model=ConfigContentsResponse)
async def read_config_files(emulator: str, request: Request):
    """Return current/default config contents for an emulator (read-only)."""
    require_scope(request, "state")
    manager = _manager(request)
    try:
        return manager.get_config_contents(emulator)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read configs: {exc}")


# ── WIZ AI Chat ───────────────────────────────────────────────────────────────

class WizChatTurn(BaseModel):
    role: str
    content: str


class WizChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[WizChatTurn] = Field(default_factory=list)
    isDiagnosisMode: bool = False
    extraContext: Optional[dict] = None


class WizChatResponse(BaseModel):
    reply: str
    isDiagnosisMode: bool


@router.post("/chat")
async def wiz_chat(request: Request, payload: WizChatRequest):
    """
    Send a message to Wiz AI and get a reply (CW-AI-01).
    In Diagnosis Mode the ---DIAGNOSIS--- prompt variant is loaded automatically.
    """
    require_scope(request, "state")

    try:
        from backend.services.wiz.ai import wizard_ai_chat

        history = [{"role": t.role, "content": t.content} for t in payload.history]
        reply = await wizard_ai_chat(
            payload.message,
            history,
            is_diagnosis_mode=payload.isDiagnosisMode,
            extra_context=payload.extraContext,
        )
        return WizChatResponse(reply=reply, isDiagnosisMode=payload.isDiagnosisMode)

    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Wiz AI error: {exc}")

