from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, root_validator
from pathlib import Path
from typing import Any, Dict, Optional
import json
from datetime import datetime

from ..services.led_mapping_service import LEDMappingService
from ..services.policies import require_scope

router = APIRouter()

class LEDMapping(BaseModel):
    scope: str = Field(default="game")
    game: Optional[str] = None
    profile_name: Optional[str] = None
    buttons: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    animation: Optional[str] = None
    dry_run: Optional[bool] = None
    mapping: Optional[Dict[str, Any]] = None  # Legacy field

    @root_validator(pre=True)
    def prefer_buttons_field(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not values.get("buttons") and isinstance(values.get("mapping"), dict):
            values["buttons"] = values["mapping"]
        return values

    @root_validator(skip_on_failure=True)
    def validate_scope_and_buttons(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        scope = str(values.get("scope", "game")).strip().lower()
        if scope not in {"default", "game", "shared", "profile"}:
            raise ValueError(f"Invalid scope: {scope}")
        values["scope"] = scope

        buttons = values.get("buttons") or {}
        if not isinstance(buttons, dict) or not buttons:
            raise ValueError("buttons payload cannot be empty")

        metadata = values.get("metadata")
        if metadata is None or not isinstance(metadata, dict):
            values["metadata"] = {}

        if scope == "game" and not (values.get("game") or values.get("profile_name")):
            raise ValueError("game is required when scope='game' without profile_name")
        return values

    def resolved_profile_name(self) -> str:
        if self.profile_name and self.profile_name.strip():
            return self.profile_name.strip()
        if self.scope == "default":
            return "default"
        if self.scope == "game" and self.game:
            return self.game
        return "profile"

    def to_profile_payload(self) -> Dict[str, Any]:
        return {
            "profile_name": self.resolved_profile_name(),
            "scope": self.scope,
            "game": self.game,
            "metadata": self.metadata,
            "animation": self.animation,
            "buttons": self.buttons,
        }

# Utility functions
def get_ledblinky_dir(drive_root: Path) -> Path:
    """Get the LED Blinky config directory"""
    return drive_root / "configs" / "ledblinky" / "profiles"

def get_profile_file(drive_root: Path, scope: str, game: Optional[str] = None) -> Path:
    """Get LED profile file path

    Args:
        drive_root: Root directory
        scope: "default" or "game"
        game: Game name (required if scope="game")

    Returns:
        Path to profile JSON file
    """
    profiles_dir = get_ledblinky_dir(drive_root)

    if scope == "default":
        return profiles_dir / "default.json"
    elif scope == "game":
        if not game:
            raise ValueError("Game name required for game-specific profile")
        # Sanitize game name for filename
        safe_game = game.replace("/", "_").replace("\\", "_")
        return profiles_dir / f"{safe_game}.json"
    else:
        raise ValueError(f"Invalid scope: {scope}. Must be 'default' or 'game'")


def _mapping_service_from_request(request: Request) -> LEDMappingService:
    return LEDMappingService(request.app.state.drive_root, request.app.state.manifest)


def log_led_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    """Log LED action to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "led" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
    panel = request.headers.get('x-panel', 'unknown') if hasattr(request, 'headers') else 'unknown'

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "led_blinky",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + "\n")

# Routes
@router.post("/mapping/preview")
async def preview_led_mapping(request: Request, mapping_data: LEDMapping):
    """Preview LED mapping changes."""
    try:
        service = _mapping_service_from_request(request)
        preview_result = service.preview(mapping_data.to_profile_payload())
        preview = preview_result.response

        log_led_change(
            request,
            request.app.state.drive_root,
            "mapping_preview",
            {
                "scope": preview["scope"],
                "game": preview.get("game"),
                "profile_name": preview["profile_name"],
                "target_file": preview["target_file"],
                "has_changes": preview["has_changes"],
                "missing_buttons": preview["missing_buttons"],
            },
        )
        return preview

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/mapping/apply")
async def apply_led_mapping(request: Request, mapping_data: LEDMapping):
    """Apply LED mapping changes."""
    try:
        require_scope(request, "config")
        service = _mapping_service_from_request(request)
        profile_payload = mapping_data.to_profile_payload()
        preview_result = service.preview(profile_payload)
        preview = preview_result.response

        if preview["missing_buttons"]:
            raise HTTPException(
                status_code=400,
                detail={"missing_buttons": preview["missing_buttons"]},
            )

        dry_default = getattr(request.app.state, "dry_run_default", True)
        dry_run = mapping_data.dry_run if mapping_data.dry_run is not None else dry_default
        backup_on_write = getattr(request.app.state, "backup_on_write", True)
        result = service.apply(
            profile_payload,
            dry_run=dry_run,
            backup_on_write=backup_on_write,
            preview=preview_result,
        )

        backup_value = result.get("backup_path")
        backup_path = (
            (request.app.state.drive_root / backup_value)
            if backup_value
            else None
        )

        log_led_change(
            request,
            request.app.state.drive_root,
            "mapping_apply",
            {
                "scope": preview["scope"],
                "game": preview.get("game"),
                "profile_name": preview["profile_name"],
                "target_file": preview["target_file"],
                "has_changes": preview["has_changes"],
                "status": result["status"],
            },
            backup_path,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profiles")
async def list_led_profiles(request: Request):
    """List all LED profiles"""
    try:
        drive_root = request.app.state.drive_root
        profiles_dir = get_ledblinky_dir(drive_root)

        if not profiles_dir.exists():
            return {
                "profiles": [],
                "count": 0
            }

        # List all JSON files
        profiles = []
        for profile_file in profiles_dir.glob("*.json"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                scope = "default" if profile_file.name == "default.json" else "game"
                game = profile_file.stem if profile_file.name != "default.json" else None
                mapping_keys: list[str] = []
                profile_name = profile_file.stem
                metadata: Dict[str, Any] = {}

                if isinstance(data, dict):
                    buttons = data.get("buttons")
                    if isinstance(buttons, dict):
                        mapping_keys = list(buttons.keys())
                    else:
                        mapping_keys = list(data.keys())

                    stored_scope = data.get("scope")
                    if isinstance(stored_scope, str) and stored_scope:
                        scope = stored_scope

                    stored_game = data.get("game")
                    if isinstance(stored_game, str) and stored_game:
                        game = stored_game

                    profile_name = data.get("profile_name") or profile_name
                    metadata_field = data.get("metadata")
                    if isinstance(metadata_field, dict):
                        metadata = metadata_field

                profiles.append({
                    "filename": profile_file.name,
                    "scope": scope,
                    "game": None if scope == "default" else game,
                    "profile_name": profile_name,
                    "mapping_keys": mapping_keys,
                    "metadata": metadata
                })
            except Exception as e:
                # Skip invalid files
                print(f"Warning: Could not read profile {profile_file}: {e}")
                continue

        return {
            "profiles": profiles,
            "count": len(profiles)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profiles/{profile_name}")
async def get_led_profile(request: Request, profile_name: str):
    """Get specific LED profile"""
    try:
        drive_root = request.app.state.drive_root
        profiles_dir = get_ledblinky_dir(drive_root)
        profile_file = profiles_dir / f"{profile_name}.json"

        if not profile_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Profile not found: {profile_name}"
            )

        with open(profile_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        scope = "default" if profile_name == "default" else "game"
        game = profile_name if profile_name != "default" else None
        if isinstance(data, dict):
            stored_scope = data.get("scope")
            if isinstance(stored_scope, str) and stored_scope:
                scope = stored_scope
            stored_game = data.get("game")
            if isinstance(stored_game, str) and stored_game:
                game = stored_game

        metadata = data.get("metadata") if isinstance(data, dict) and isinstance(data.get("metadata"), dict) else {}
        profile_value = data.get("profile_name") if isinstance(data, dict) else profile_name

        return {
            "filename": profile_file.name,
            "scope": scope,
            "game": None if scope == "default" else game,
            "profile_name": profile_value,
            "metadata": metadata,
            "mapping": data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
