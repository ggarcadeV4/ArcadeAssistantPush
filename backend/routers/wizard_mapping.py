"""Wizard & Mapping Router ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â high-level virtual mapping logic.

Extracted from the monolithic controller.py during Phase 2 (Persona Split).
Contains learn wizard, click-to-map, encoder state, wiring wizard,
player identity, genre profiles, and MAME per-game fix endpoints.

Mounted at: /api/local/controller  (same prefix ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â no frontend URL changes)
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.backup import create_backup
from .chuck_hardware import get_input_detection_service, get_latest_event
from ..services.chuck.input_detector import InputDetectionService, InputEvent, detect_input_mode
from ..services.chuck.encoder_state import get_encoder_state_manager
from ..services.console_wizard_manager import ConsoleWizardManager
from ..services.controller_baseline import get_cascade_preference, update_controller_baseline
from ..services.gamepad_detector import get_profile_details
from ..services.controller_cascade import enqueue_cascade_job, run_cascade_job
from ..services.mame_config_generator import (
    MAMEConfigError,
    generate_mame_config,
    validate_mame_config,
)
from ..services.mame_pergame_generator import (
    save_pergame_config,
    get_genre_for_rom,
    get_supported_fighting_games,
)
from ..services.teknoparrot_config_generator import (
    build_canonical_mapping,
    apply_tp_config,
    is_game_supported,
    TPInputMode,
)
from ..services.policies import is_allowed_file, require_scope
from ..services import audit_log
from ..services import player_identity
from ..services.controller_shared import (
    ensure_writes_allowed,
    wizard_session_key,
    default_control_type,
    get_next_step,
    log_controller_change,
    serialize_input_event,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_learn_mode_latest_key: Optional[str] = None
_learn_wizard_state: Dict[str, Any] = {}
_wizard_states: Dict[str, Dict[str, Any]] = {}
_click_to_map_latest_input: Optional[Dict[str, Any]] = None
_click_to_map_lock = Lock()

# ---------------------------------------------------------------------------
# Wizard sequences
# ---------------------------------------------------------------------------

P1_WIZARD_SEQUENCE = [
    "p1.up", "p1.down", "p1.left", "p1.right",
    "p1.button1", "p1.button2", "p1.button3", "p1.button4",
    "p1.button5", "p1.button6", "p1.button7", "p1.button8",
    "p1.start", "p1.coin",
]
P2_WIZARD_SEQUENCE = [
    "p2.up", "p2.down", "p2.left", "p2.right",
    "p2.button1", "p2.button2", "p2.button3", "p2.button4",
    "p2.button5", "p2.button6", "p2.start", "p2.coin",
]
P3_WIZARD_SEQUENCE = [
    "p3.up", "p3.down", "p3.left", "p3.right",
    "p3.button1", "p3.button2", "p3.button3", "p3.button4",
    "p3.button5", "p3.button6", "p3.start", "p3.coin",
]
P4_WIZARD_SEQUENCE = [
    "p4.up", "p4.down", "p4.left", "p4.right",
    "p4.button1", "p4.button2", "p4.button3", "p4.button4",
    "p4.button5", "p4.button6", "p4.start", "p4.coin",
]
DEFAULT_WIZARD_SEQUENCE = (
    P1_WIZARD_SEQUENCE + P2_WIZARD_SEQUENCE +
    P3_WIZARD_SEQUENCE + P4_WIZARD_SEQUENCE
)


def build_wizard_sequence(players: int = 2, buttons: int = 6) -> List[str]:
    sequence = []
    for p in range(1, min(players, 4) + 1):
        sequence.extend([f"p{p}.up", f"p{p}.down", f"p{p}.left", f"p{p}.right"])
        for b in range(1, min(buttons, 10) + 1):
            sequence.append(f"p{p}.button{b}")
        sequence.extend([f"p{p}.start", f"p{p}.coin"])
    return sequence


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SingleMappingRequest(BaseModel):
    controlKey: str = Field(..., description="Control key, e.g., 'p1.up', 'p2.button3'")
    keycode: str = Field(..., description="Keycode to assign")
    source: Optional[str] = Field(default="keyboard")


class ClearMappingRequest(BaseModel):
    controlKey: str = Field(..., description="Control key to clear")


class EncoderModeRequest(BaseModel):
    mode: str = Field(..., description="Encoder mode: 'keyboard', 'xinput', or 'dinput'")


class EncoderCaptureRequest(BaseModel):
    keycode: str = Field(..., description="The captured keycode to set baseline from")


class ManualKeyRequest(BaseModel):
    keycode: str = Field(..., description="The keycode to assign")


class LearnMappingRequest(BaseModel):
    control_key: str = Field(..., description="Control to map, e.g., p1.button1")
    keycode: str = Field(..., description="Key code captured, e.g., KEY_F1")


class InputDetectionRequest(BaseModel):
    keycode: str


class WizardCapture(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Wizard session identifier")
    button_name: Optional[str] = Field(default=None, description="Target control key, e.g. p1.button1")
    input_event: Optional[Dict[str, Any]] = Field(default=None, description="Serialized physical input event")
    rollback: bool = Field(default=False, description="Undo the most recent wizard capture")
    skip: bool = Field(default=False, description="Mark the current control as intentionally skipped")
    control_key: Optional[str] = Field(default=None, description="Legacy mapping key, e.g., p1.button1")
    pin: Optional[int] = Field(default=None, ge=0)
    control_type: Optional[str] = Field(default=None)


class WizardStartRequest(BaseModel):
    player_mode: str = Field(default="4p", description="Visual layout mode: 2p or 4p")


class WizardCommitRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Wizard session identifier")


def build_visual_wizard_sequence(player_mode: str = "4p") -> List[str]:
    """Match the visual overlay layout: P1/P2 are 8-button, P3/P4 are 4-button."""
    normalized = (player_mode or "4p").strip().lower()
    sequence: List[str] = []

    def _extend_player(player_num: int, button_count: int) -> None:
        prefix = f"p{player_num}"
        sequence.extend([
            f"{prefix}.up",
            f"{prefix}.down",
            f"{prefix}.left",
            f"{prefix}.right",
        ])
        for button_num in range(1, button_count + 1):
            sequence.append(f"{prefix}.button{button_num}")
        sequence.extend([f"{prefix}.start", f"{prefix}.coin"])

    if normalized == "2p":
        _extend_player(1, 8)
        _extend_player(2, 8)
        return sequence

    _extend_player(3, 4)
    _extend_player(4, 4)
    _extend_player(1, 8)
    _extend_player(2, 8)
    return sequence


class MappingUpdate(BaseModel):
    mappings: Dict[str, Any]


class PlayerIdentityResponse(BaseModel):
    status: str
    bindings: Dict[str, int]
    calibrated_at: Optional[str] = None


class MAMEFixRequest(BaseModel):
    rom_name: str
    genre: Optional[str] = None
    issue_description: Optional[str] = None


# ---------------------------------------------------------------------------
# Control display name helpers
# ---------------------------------------------------------------------------

CONTROL_DISPLAY_NAMES = {
    f"p{p}.{c}": f"Player {p} {c.replace('button', 'Button ').capitalize()}"
    for p in range(1, 5)
    for c in ["up", "down", "left", "right", "start", "coin"] +
             [f"button{b}" for b in range(1, 11)]
}


def get_control_display_name(control_key: str) -> str:
    if not control_key or "." not in control_key:
        return control_key
    parts = control_key.split(".", 1)
    player_num = parts[0].replace("p", "Player ")
    control_name = parts[1]
    if control_name.startswith("button"):
        btn_num = control_name.replace("button", "")
        return f"{player_num} Button {btn_num}"
    return f"{player_num} {control_name.capitalize()}"


GAMEPAD_PREFERENCE_ALIASES: Dict[str, tuple[str, ...]] = {
    "p1.up": ("up",),
    "p1.down": ("down",),
    "p1.left": ("left",),
    "p1.right": ("right",),
    "p1.button1": ("a",),
    "p1.button2": ("b",),
    "p1.button3": ("x",),
    "p1.button4": ("y",),
    "p1.button5": ("lb", "l"),
    "p1.button6": ("rb", "r"),
    "p1.button7": ("lt", "l2", "zl"),
    "p1.button8": ("rt", "r2", "zr"),
    "p1.coin": ("back", "select", "minus", "share"),
    "p1.start": ("start", "plus", "options"),
    "p1.l3": ("ls", "l3"),
    "p1.r3": ("rs", "r3"),
}

GAMEPAD_AXIS_BINDINGS: Dict[str, List[tuple[str, str]]] = {
    "left_stick_x": [("p1.lstick_left", "-"), ("p1.lstick_right", "+")],
    "left_stick_y": [("p1.lstick_up", "-"), ("p1.lstick_down", "+")],
    "right_stick_x": [
        ("p1.rstick_left", "-"),
        ("p1.rstick_right", "+"),
        ("p1.cstick_left", "-"),
        ("p1.cstick_right", "+"),
    ],
    "right_stick_y": [
        ("p1.rstick_up", "-"),
        ("p1.rstick_down", "+"),
        ("p1.cstick_up", "-"),
        ("p1.cstick_down", "+"),
    ],
}


def _gamepad_preferences_path(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "controller" / "gamepad_preferences.json"


def _load_gamepad_preferences(drive_root: Path) -> Optional[Dict[str, Any]]:
    path = _gamepad_preferences_path(drive_root)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("Failed to load gamepad preferences from %s: %s", path, exc)
        return None


def _normalize_gamepad_mapping_keys(mappings: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in mappings.items():
        normalized[str(key).strip().lower()] = value
    return normalized


def _build_gamepad_controls_from_preferences(
    preferences: Dict[str, Any], profile: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    normalized_mappings = _normalize_gamepad_mapping_keys(preferences.get("mappings") or {})
    controls: Dict[str, Dict[str, Any]] = {}

    for control_key, aliases in GAMEPAD_PREFERENCE_ALIASES.items():
        for alias in aliases:
            if alias not in normalized_mappings:
                continue
            value = normalized_mappings[alias]
            if value in (None, ""):
                break
            controls[control_key] = {
                "pin": str(value),
                "type": "button",
                "source": "gamepad_preferences",
            }
            break

    axes = profile.get("axes") or {}
    for axis_name, bindings in GAMEPAD_AXIS_BINDINGS.items():
        axis_data = axes.get(axis_name)
        if not isinstance(axis_data, dict):
            continue
        axis_index = axis_data.get("index")
        if axis_index is None:
            continue
        for control_key, direction in bindings:
            controls[control_key] = {
                "pin": f"{direction}{axis_index}",
                "type": "axis",
                "source": "gamepad_preferences",
            }

    return controls


def _build_gamepad_retroarch_mapping(
    preferences: Dict[str, Any], profile: Dict[str, Any]
) -> Dict[str, Any]:
    retroarch_defaults = profile.get("retroarch_defaults") or {}
    mapping: Dict[str, Any] = {
        key: value
        for key, value in retroarch_defaults.items()
        if value not in (None, "")
    }

    axes = profile.get("axes") or {}
    deadzone = preferences.get("deadzone")
    if not isinstance(deadzone, (int, float)):
        left_axis = axes.get("left_stick_x") or {}
        deadzone = left_axis.get("deadzone")

    if isinstance(deadzone, (int, float)):
        if "left_stick_x" in axes or "left_stick_y" in axes:
            mapping["input_player1_analog_dpad_mode"] = "0"
            mapping["input_player1_l_x_deadzone"] = str(deadzone)
            mapping["input_player1_l_y_deadzone"] = str(deadzone)
        if "right_stick_x" in axes or "right_stick_y" in axes:
            mapping["input_player1_r_x_deadzone"] = str(deadzone)
            mapping["input_player1_r_y_deadzone"] = str(deadzone)

    return mapping


def _sync_gamepad_preferences_to_cascade_state(
    drive_root: Path,
    manifest: Dict[str, Any],
    *,
    backup: bool = False,
) -> Optional[Dict[str, Any]]:
    preferences = _load_gamepad_preferences(drive_root)
    if not preferences:
        return None

    profile_id = str(preferences.get("profile_id") or "").strip()
    if not profile_id:
        logger.debug("[WizardMapping] Gamepad preference sync skipped: missing_profile_id")
        return None

    profile = get_profile_details(profile_id)
    if not profile:
        logger.debug("[WizardMapping] Gamepad preference sync skipped: unknown_profile (%s)", profile_id)
        return None

    controls = _build_gamepad_controls_from_preferences(preferences, profile)
    if not controls:
        logger.debug("[WizardMapping] Gamepad preference sync skipped: no_controls (%s)", profile_id)
        return None

    try:
        manager = ConsoleWizardManager(drive_root, manifest or {})
        emulator_updates: Dict[str, Any] = {}
        for info in manager.discovery.discover_emulators(console_only=True):
            if info.type == "retroarch":
                mapping = _build_gamepad_retroarch_mapping(preferences, profile)
            else:
                mapping = manager._build_mapping_for_emulator(info.type, controls)
            if not mapping:
                continue
            emulator_updates[info.type] = {
                "mapping": mapping,
                "status": "pending",
                "message": "Loaded from saved gamepad preferences",
                "last_job_id": None,
            }

        if not emulator_updates:
            logger.debug("[WizardMapping] Gamepad preference sync skipped: no_supported_emulators")
            return {
                "profile_id": profile_id,
                "controls_count": len(controls),
                "emulators_synced": 0,
            }

        update_controller_baseline(
            drive_root,
            {"emulators": emulator_updates},
            backup=backup,
        )
        return {
            "profile_id": profile_id,
            "controls_count": len(controls),
            "emulators_synced": len(emulator_updates),
        }
    except Exception as exc:
        logger.warning("[WizardMapping] Gamepad preference sync failed: %s", exc)
        return None

# ============================================================================
# Learn Mode Endpoints
# ============================================================================

@router.post("/input/learn/start")
async def start_learn_mode(request: Request):
    """Enable learn mode - captures ALL key presses."""
    require_scope(request, "state")
    global _learn_mode_latest_key
    _learn_mode_latest_key = None
    service = get_input_detection_service(request)
    service.set_learn_mode(True)

    def capture_raw_key(keycode: str) -> None:
        global _learn_mode_latest_key
        _learn_mode_latest_key = keycode
        logger.info("Learn mode captured: %s", keycode)

    service._raw_handlers.clear()
    service.register_raw_handler(capture_raw_key)
    service.start_listening()
    return {"status": "learning", "message": "Learn mode enabled. Press any button on your encoder."}


@router.post("/input/learn/stop")
async def stop_learn_mode(request: Request):
    require_scope(request, "state")
    service = get_input_detection_service(request)
    if service is not None:
        service.set_learn_mode(False)
        service._raw_handlers.clear()
    return {"status": "stopped", "message": "Learn mode disabled."}


@router.get("/input/learn/latest")
async def get_learn_mode_latest(request: Request):
    require_scope(request, "state")
    return {"status": "captured" if _learn_mode_latest_key else "waiting", "keycode": _learn_mode_latest_key}


@router.post("/input/learn/clear")
async def clear_learn_mode_capture(request: Request):
    require_scope(request, "state")
    global _learn_mode_latest_key
    _learn_mode_latest_key = None
    return {"status": "cleared"}


@router.post("/input/learn/save")
async def save_learned_mapping(request: Request, payload: LearnMappingRequest):
    """Save a learned key-to-control mapping to controls.json."""
    require_scope(request, "config")
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"

    if not mapping_file.exists():
        raise HTTPException(status_code=404, detail="Mapping file not found")

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read mapping: {exc}")

    if "mappings" not in data:
        data["mappings"] = {}

    key_name = payload.keycode.upper().replace("KEY_", "").lower()
    if payload.control_key not in data["mappings"]:
        data["mappings"][payload.control_key] = {}
    data["mappings"][payload.control_key]["keycode"] = payload.keycode
    data["mappings"][payload.control_key]["key_name"] = key_name

    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {exc}")

    audit_log.append({
        "scope": "config", "action": "learn_mapping",
        "control_key": payload.control_key, "keycode": payload.keycode,
        "device_id": request.headers.get("x-device-id", "unknown"),
    })
    return {"status": "saved", "control_key": payload.control_key, "keycode": payload.keycode,
            "message": f"Mapped {payload.control_key} to {payload.keycode}"}


# ============================================================================
# Learn Wizard Endpoints
# ============================================================================

@router.post("/learn-wizard/start")
async def start_learn_wizard(
    request: Request,
    player: Optional[int] = None,
    players: Optional[int] = None,
    buttons: Optional[int] = None,
    auto_advance: bool = True,
):
    """Start the voice-guided learn wizard."""
    require_scope(request, "state")
    global _learn_wizard_state, _learn_mode_latest_key

    drive_root: Path = request.app.state.drive_root

    if players is not None and buttons is not None:
        sequence = build_wizard_sequence(players=players, buttons=buttons)
        player_label = f"{players} players, {buttons} buttons each"
    elif player == 1:
        sequence = list(P1_WIZARD_SEQUENCE)
        player_label = "Player 1"
    elif player == 2:
        sequence = list(P2_WIZARD_SEQUENCE)
        player_label = "Player 2"
    elif player == 3:
        sequence = list(P3_WIZARD_SEQUENCE)
        player_label = "Player 3"
    elif player == 4:
        sequence = list(P4_WIZARD_SEQUENCE)
        player_label = "Player 4"
    else:
        sequence = build_wizard_sequence(players=2, buttons=6)
        player_label = "all players"

    encoder_manager = get_encoder_state_manager(drive_root)
    encoder_state = encoder_manager.get_state()
    mode_warning = None
    if encoder_state.get("needs_recalibration"):
        mode_warning = (
            f"Encoder may have switched modes. "
            f"Baseline was {encoder_state.get('baseline_mode')}, "
            f"but recent inputs look like {encoder_state.get('current_mode')}."
        )
        logger.warning("[LearnWizard] %s", mode_warning)

    _learn_wizard_state = {
        "sequence": sequence, "player": player, "players": players,
        "buttons": buttons, "auto_advance": auto_advance,
        "current_index": 0, "captures": {},
        "started_at": datetime.utcnow().isoformat(),
        "encoder_mode": encoder_state.get("baseline_mode"),
    }
    _learn_mode_latest_key = None

    # Auto-detect encoder board
    detected_board = None
    detected_mode = None
    try:
        from ..services.usb_detector import detect_arcade_boards
        boards = detect_arcade_boards()
        for board in boards:
            vendor = board.get("vendor", "").lower()
            if "pacto" in vendor or "paxco" in vendor:
                detected_board, detected_mode = board, "xinput"
                break
            elif "ultimarc" in vendor:
                detected_board, detected_mode = board, "keyboard"
                break
        if not detected_board and boards:
            detected_board = boards[0]
    except Exception as e:
        logger.warning(f"[LearnWizard] Could not auto-detect encoder board: {e}")

    service = get_input_detection_service(request)
    service.set_learn_mode(True)

    def capture_wizard_input(keycode: str) -> None:
        if "TRIGGER" in keycode:
            return
        global _learn_mode_latest_key
        _learn_mode_latest_key = keycode
        logger.info("[LearnWizard] Captured input: %s", keycode)

    service._raw_handlers.clear()
    service.register_raw_handler(capture_wizard_input)
    service.start_listening()

    first_control = sequence[0] if sequence else "p1.up"
    display_name = get_control_display_name(first_control)
    chuck_prompt = f"Let's map your controls! Press {display_name}."
    if detected_board:
        board_name = detected_board.get("name", "encoder board")
        chuck_prompt = f"Detected {board_name}! Press {display_name}."

    return {
        "status": "started", "current_control": first_control, "current_index": 0,
        "total_controls": len(sequence), "auto_advance": auto_advance,
        "players": players, "buttons": buttons, "chuck_prompt": chuck_prompt,
        "display_name": display_name, "mode_warning": mode_warning,
        "encoder_mode": encoder_state.get("baseline_mode"),
        "detected_board": detected_board.get("name") if detected_board else None,
        "detected_mode": detected_mode, "dual_mode_enabled": True,
    }


@router.get("/learn-wizard/status")
async def get_learn_wizard_status(request: Request):
    require_scope(request, "state")
    if not _learn_wizard_state:
        return {"status": "not_started"}

    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    drive_root: Path = request.app.state.drive_root
    encoder_manager = get_encoder_state_manager(drive_root)
    encoder_state = encoder_manager.get_state()
    mode_warning = None
    if encoder_state.get("needs_recalibration"):
        mode_warning = f"Mode drift detected! Baseline was {encoder_state.get('baseline_mode')}, current looks like {encoder_state.get('current_mode')}."

    if current_index >= len(sequence):
        return {"status": "complete", "captures": _learn_wizard_state.get("captures", {}),
                "chuck_prompt": "All done! Your controls are mapped. Ready to save?",
                "encoder_mode": encoder_state.get("baseline_mode"), "mode_warning": mode_warning}

    current_control = sequence[current_index]
    display_name = CONTROL_DISPLAY_NAMES.get(current_control, current_control)
    return {
        "status": "waiting", "current_control": current_control,
        "current_index": current_index, "total_controls": len(sequence),
        "captured_key": _learn_mode_latest_key, "captures": _learn_wizard_state.get("captures", {}),
        "display_name": display_name, "encoder_mode": encoder_state.get("baseline_mode"),
        "mode_match": encoder_state.get("mode_match"), "mode_warning": mode_warning,
    }


@router.post("/learn-wizard/confirm")
async def confirm_learn_wizard_capture(request: Request):
    require_scope(request, "state")
    global _learn_mode_latest_key
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")
    if not _learn_mode_latest_key:
        return {"status": "no_capture", "chuck_prompt": "I didn't catch that. Press the button again."}

    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    if current_index >= len(sequence):
        return {"status": "complete"}

    current_control = sequence[current_index]
    _learn_wizard_state["captures"][current_control] = {
        "keycode": _learn_mode_latest_key,
        "key_name": _learn_mode_latest_key.upper().replace("KEY_", "").lower(),
    }
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None

    if current_index + 1 >= len(sequence):
        return {"status": "complete", "captures": _learn_wizard_state.get("captures", {}),
                "chuck_prompt": "Perfect! All controls are mapped. Say 'save' or click Save to apply."}

    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    return {"status": "next", "captured": current_control, "next_control": next_control,
            "current_index": current_index + 1, "total_controls": len(sequence),
            "chuck_prompt": f"Got it! Now, which button is {next_display}? Press it now.", "display_name": next_display}


@router.post("/learn-wizard/set-key")
async def set_learn_wizard_key(request: Request, payload: ManualKeyRequest):
    require_scope(request, "state")
    global _learn_mode_latest_key
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")

    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    if current_index >= len(sequence):
        return {"status": "complete"}

    current_control = sequence[current_index]
    keycode = payload.keycode.strip().upper()
    if not keycode.startswith("KEY_"):
        keycode = f"KEY_{keycode}"

    _learn_wizard_state["captures"][current_control] = {
        "keycode": keycode, "key_name": keycode.replace("KEY_", "").lower(),
    }
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None

    if current_index + 1 >= len(sequence):
        return {"status": "complete", "captures": _learn_wizard_state.get("captures", {}),
                "chuck_prompt": "Perfect! All controls are mapped. Ready to save!"}

    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    return {"status": "next", "captured": current_control, "keycode": keycode,
            "next_control": next_control, "current_index": current_index + 1,
            "total_controls": len(sequence),
            "chuck_prompt": f"Got it! Next up: {next_display}. What key is that?", "display_name": next_display}


@router.post("/learn-wizard/skip")
async def skip_learn_wizard_control(request: Request):
    require_scope(request, "state")
    global _learn_mode_latest_key
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")

    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])
    _learn_wizard_state["current_index"] = current_index + 1
    _learn_mode_latest_key = None

    if current_index + 1 >= len(sequence):
        return {"status": "complete", "captures": _learn_wizard_state.get("captures", {}),
                "chuck_prompt": "All done! Click Save when you're ready."}

    next_control = sequence[current_index + 1]
    next_display = CONTROL_DISPLAY_NAMES.get(next_control, next_control)
    return {"status": "skipped", "next_control": next_control,
            "chuck_prompt": f"Skipped. Next: {next_display}.", "display_name": next_display}


@router.post("/learn-wizard/undo")
async def undo_learn_wizard_capture(request: Request):
    require_scope(request, "state")
    global _learn_mode_latest_key
    if not _learn_wizard_state:
        raise HTTPException(status_code=400, detail="Wizard not started")

    current_index = _learn_wizard_state.get("current_index", 0)
    sequence = _learn_wizard_state.get("sequence", [])

    if current_index <= 0:
        first_control = sequence[0] if sequence else "p1.up"
        display_name = CONTROL_DISPLAY_NAMES.get(first_control, first_control)
        return {"status": "at_start", "current_control": first_control,
                "chuck_prompt": f"Already at the first control. Which button is {display_name}?",
                "display_name": display_name}

    _learn_wizard_state["current_index"] = current_index - 1
    previous_control = sequence[current_index - 1]
    _learn_wizard_state.get("captures", {}).pop(previous_control, None)
    _learn_mode_latest_key = None

    previous_display = CONTROL_DISPLAY_NAMES.get(previous_control, previous_control)
    return {"status": "undone", "current_control": previous_control,
            "current_index": current_index - 1, "total_controls": len(sequence),
            "chuck_prompt": f"Okay, back to {previous_display}.", "display_name": previous_display,
            "captures": _learn_wizard_state.get("captures", {})}


@router.post("/learn-wizard/stop")
async def stop_learn_wizard(request: Request):
    require_scope(request, "state")
    global _learn_wizard_state
    service = get_input_detection_service(request)
    if service is not None:
        service.set_learn_mode(False)
        service._raw_handlers.clear()
        service.stop_listening()
    _learn_wizard_state = {}
    return {"status": "stopped", "chuck_prompt": "Wizard cancelled. No changes saved."}


@router.post("/learn-wizard/save")
async def save_learn_wizard(request: Request, background_tasks: BackgroundTasks):
    """Save all captured mappings and trigger cascade."""
    require_scope(request, "config")
    ensure_writes_allowed(request)
    if not _learn_wizard_state or not _learn_wizard_state.get("captures"):
        raise HTTPException(status_code=400, detail="No captures to save")

    drive_root: Path = request.app.state.drive_root
    manifest = request.app.state.manifest
    mapping_file = drive_root / "config" / "mappings" / "controls.json"

    backup_path = None
    if mapping_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    if "mappings" not in data:
        data["mappings"] = {}

    controls_mapped = []
    for control_key, capture in _learn_wizard_state["captures"].items():
        if control_key not in data["mappings"]:
            data["mappings"][control_key] = {}
        data["mappings"][control_key]["keycode"] = capture["keycode"]
        data["mappings"][control_key]["key_name"] = capture["key_name"]
        controls_mapped.append(control_key)

    data["last_modified"] = datetime.now().isoformat()
    data["modified_by"] = request.headers.get("x-device-id", "learn_wizard")

    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")

    await log_controller_change(request, drive_root, "learn_wizard_save",
        {"controls_mapped": controls_mapped, "count": len(controls_mapped)}, backup_path)

    service = get_input_detection_service(request)
    if service is not None:
        service.set_learn_mode(False)
        service._raw_handlers.clear()
        service.stop_listening()

    # MAME config write
    mame_config_result = _write_mame_config(drive_root, manifest, data, controls_mapped)
    # TeknoParrot config write
    teknoparrot_results = _write_teknoparrot_configs(drive_root, manifest, data)

    gamepad_sync_result = _sync_gamepad_preferences_to_cascade_state(
        drive_root,
        manifest,
        backup=getattr(request.app.state, "backup_on_write", False),
    )

    # Cascade
    cascade_preference = get_cascade_preference(drive_root)
    if cascade_preference == "auto":
        requested_by = request.headers.get("x-device-id", "learn_wizard")
        backup_on_write = getattr(request.app.state, "backup_on_write", False)
        cascade_job = enqueue_cascade_job(drive_root, requested_by=requested_by,
            metadata={"source": "learn_wizard", "controls_mapped": controls_mapped}, backup=backup_on_write)
        background_tasks.add_task(run_cascade_job, drive_root, manifest,
            cascade_job["job_id"], backup=backup_on_write)

    response = {"status": "saved", "controls_mapped": len(controls_mapped),
                "backup_path": str(backup_path) if backup_path else None,
                "cascade_preference": cascade_preference}
    if gamepad_sync_result:
        response["gamepad_preferences_sync"] = gamepad_sync_result
    if mame_config_result:
        response["mame_config"] = mame_config_result
    if teknoparrot_results:
        tp_success = sum(1 for r in teknoparrot_results if r.get("status") == "success")
        response["teknoparrot_config"] = {"profiles_updated": tp_success,
            "total_attempted": len(teknoparrot_results), "details": teknoparrot_results[:5]}

    mame_ok = mame_config_result and mame_config_result.get("status") == "success"
    tp_ok = teknoparrot_results and any(r.get("status") == "success" for r in teknoparrot_results)
    if mame_ok and tp_ok:
        response["chuck_prompt"] = f"Done! Saved {len(controls_mapped)} controls. Updated MAME and TeknoParrot!"
    elif mame_ok:
        response["chuck_prompt"] = f"Done! Saved {len(controls_mapped)} controls and updated MAME config."
    elif tp_ok:
        response["chuck_prompt"] = f"Done! Saved {len(controls_mapped)} controls and updated TeknoParrot."
    else:
        response["chuck_prompt"] = f"Done! Saved {len(controls_mapped)} controls."
    return response


def _write_mame_config(drive_root, manifest, data, controls_mapped):
    try:
        mame_config_path = drive_root / "Emulators" / "MAME" / "cfg" / "default.cfg"
        sanctioned_paths = manifest.get("sanctioned_paths", [])
        if not is_allowed_file(mame_config_path, drive_root, sanctioned_paths):
            return {"status": "path_not_allowed", "path": str(mame_config_path)}
        xml_content = generate_mame_config(data)
        validation_errors = validate_mame_config(xml_content)
        if validation_errors:
            return {"status": "validation_failed", "errors": validation_errors[:3]}
        mame_config_path.parent.mkdir(parents=True, exist_ok=True)
        if mame_config_path.exists():
            create_backup(mame_config_path, drive_root)
        with open(mame_config_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        return {"status": "success", "path": str(mame_config_path.relative_to(drive_root)), "controls": len(controls_mapped)}
    except MAMEConfigError as e:
        return {"status": "generation_failed", "error": str(e)}
    except Exception as e:
        return {"status": "write_failed", "error": str(e)}


def _write_teknoparrot_configs(drive_root, manifest, data):
    results = []
    try:
        tp_profiles_dir = drive_root / "Emulators" / "TeknoParrot" / "UserProfiles"
        sanctioned_paths = manifest.get("sanctioned_paths", [])
        if not tp_profiles_dir.exists() or not is_allowed_file(tp_profiles_dir, drive_root, sanctioned_paths):
            return results
        panel_mappings = data.get("mappings", {})
        for profile_path in tp_profiles_dir.glob("*.xml"):
            if is_game_supported(profile_path.name):
                canonical = build_canonical_mapping(profile_path.name, panel_mappings, player=1, input_mode=TPInputMode.XINPUT)
                if canonical:
                    result = apply_tp_config(profile_path, canonical, drive_root, backup=True)
                    results.append({"profile": profile_path.name, "status": "success" if result.success else "failed",
                                    **({"changes": result.changes_applied} if result.success else {"error": result.error})})
    except Exception as e:
        results = [{"status": "error", "error": str(e)}]
    return results


# ============================================================================
# Click-to-Map Single Control
# ============================================================================

@router.post("/mapping/set")
async def set_single_mapping(request: Request, payload: SingleMappingRequest):
    require_scope(request, "config")
    ensure_writes_allowed(request)
    control_key, keycode, source = payload.controlKey, payload.keycode, payload.source or "keyboard"
    if "." not in control_key:
        raise HTTPException(status_code=400, detail=f"Invalid control key format: {control_key}")

    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    backup_path = None
    if mapping_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)

    try:
        data = json.load(open(mapping_file, "r", encoding="utf-8")) if mapping_file.exists() else {"version": 1, "board": {}, "mappings": {}}
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    if "mappings" not in data:
        data["mappings"] = {}

    duplicate_control = next((k for k, v in data["mappings"].items() if k != control_key and v.get("keycode") == keycode), None)
    data["mappings"][control_key] = {"keycode": keycode, "key_name": keycode.replace("KEY_", "").replace("GAMEPAD_", "").lower(),
                                     "source": source, "mapped_at": datetime.now().isoformat()}
    data["last_modified"] = datetime.now().isoformat()
    data["modified_by"] = request.headers.get("x-device-id", "click_to_map")

    try:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {exc}")

    await log_controller_change(request, drive_root, "single_mapping_set",
        {"control_key": control_key, "keycode": keycode, "source": source}, backup_path)

    response = {"status": "saved", "controlKey": control_key, "keycode": keycode, "source": source}
    if duplicate_control:
        response["warning"] = f"Note: {keycode} was also assigned to {duplicate_control}"
        response["duplicate_control"] = duplicate_control
    return response


@router.post("/mapping/clear")
async def clear_single_mapping(request: Request, payload: ClearMappingRequest):
    require_scope(request, "config")
    ensure_writes_allowed(request)
    control_key = payload.controlKey
    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    if not mapping_file.exists():
        return {"status": "no_file", "controlKey": control_key}

    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"status": "parse_error", "controlKey": control_key}

    if "mappings" not in data or control_key not in data["mappings"]:
        return {"status": "not_found", "controlKey": control_key}

    backup_path = None
    if getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)

    old_mapping = data["mappings"].pop(control_key, None)
    data["last_modified"] = datetime.now().isoformat()
    try:
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")

    return {"status": "cleared", "controlKey": control_key,
            "previous_keycode": old_mapping.get("keycode") if old_mapping else None}


# ============================================================================
# Encoder Mode / State
# ============================================================================

@router.post("/encoder-mode")
async def set_encoder_mode(request: Request, payload: EncoderModeRequest):
    require_scope(request, "config")
    mode = payload.mode.lower()
    if mode not in ("keyboard", "xinput", "dinput"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    try:
        data = json.load(open(mapping_file, "r", encoding="utf-8")) if mapping_file.exists() else {"version": 1, "board": {}, "mappings": {}}
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}

    data["encoder_mode"] = mode
    data["last_modified"] = datetime.now().isoformat()
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"status": "saved", "encoder_mode": mode}


@router.get("/encoder-state")
async def get_encoder_state(request: Request):
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    return get_encoder_state_manager(drive_root).get_state()


@router.post("/encoder-state/calibrate")
async def calibrate_encoder_baseline(request: Request):
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    manager = get_encoder_state_manager(drive_root)
    return {"status": "ready", "message": "Start learn mode, press any button, then call /encoder-state/capture.",
            "current_baseline": manager.baseline_mode}


@router.post("/encoder-state/capture")
async def capture_encoder_baseline(request: Request, payload: EncoderCaptureRequest):
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    mode = detect_input_mode(payload.keycode)
    manager = get_encoder_state_manager(drive_root)
    state = manager.capture_baseline(mode, payload.keycode)
    return {"status": "captured", "keycode": payload.keycode, "detected_mode": mode,
            "chuck_prompt": f"Got it! Your encoder is in {mode} mode.", **state}


@router.post("/encoder-state/reset")
async def reset_encoder_state(request: Request):
    require_scope(request, "state")
    get_encoder_state_manager(request.app.state.drive_root).reset()
    return {"status": "reset", "message": "Encoder state reset.",
            "chuck_prompt": "Encoder baseline cleared. Run calibration again when ready."}


# ============================================================================
# Wiring Wizard
# ============================================================================

def _resolve_wizard_session_id(request: Request, session_id: Optional[str] = None) -> str:
    return (session_id or wizard_session_key(request)).strip()


def _get_wizard_state(request: Request, session_id: Optional[str] = None) -> Dict[str, Any]:
    resolved = _resolve_wizard_session_id(request, session_id)
    state = _wizard_states.get(resolved)
    if not state:
        raise HTTPException(status_code=404, detail="Wizard not started")
    return state


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, path)


def _wizard_capture_entry(button_name: str, input_event: Dict[str, Any], control_type: Optional[str] = None) -> Dict[str, Any]:
    pin = input_event.get("pin")
    # In learn mode, pin might be 0 for unmapped keys. We should still allow it if keycode is present.
    keycode = input_event.get("keycode")
    if pin is None and keycode is None:
        raise HTTPException(status_code=400, detail="input_event.pin or keycode is required")

    mapping_type = control_type or default_control_type(button_name)
    return {
        "pin": int(pin) if pin is not None else 0,
        "type": mapping_type,
        "keycode": keycode,
        "source_id": input_event.get("source_id"),
        "captured_at": datetime.utcnow().isoformat(),
    }

@router.post("/wizard/start")
async def start_wiring_wizard(
    request: Request,
    payload: WizardStartRequest = WizardStartRequest(),
):
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    existing_identity = player_identity.load_bindings(drive_root)
    session_id = str(uuid4())
    sequence = build_visual_wizard_sequence(payload.player_mode)

    service = get_input_detection_service(request)
    service.set_learn_mode(True)
    service.start_listening()

    _wizard_states[session_id] = {
        "session_id": session_id,
        "player_mode": payload.player_mode,
        "captures": {},
        "capture_order": [],
        "sequence": sequence,
        "started_at": datetime.utcnow().isoformat(),
        "identity": existing_identity.get("bindings", {}),
        "identity_status": existing_identity.get("status", "unbound"),
        "identity_pending": None,
    }
    return {
        "status": "started",
        "session_id": session_id,
        "buttons": sequence,
        "next_button": sequence[0] if sequence else None,
        "next": sequence[0] if sequence else None,
        "identity_status": existing_identity.get("status", "unbound"),
        "progress": 0,
        "total": len(sequence),
    }


@router.post("/wizard/next-step")
async def wizard_next_step(request: Request, payload: WizardCommitRequest = WizardCommitRequest()):
    require_scope(request, "state")
    state = _get_wizard_state(request, payload.session_id)
    next_button = get_next_step(state)
    return {
        "session_id": state.get("session_id") or _resolve_wizard_session_id(request, payload.session_id),
        "next": next_button,
        "next_button": next_button,
        "progress": len(state.get("captures", {})),
        "total": len(state.get("sequence", [])),
    }


@router.post("/wizard/capture")
async def wizard_capture(request: Request, capture: WizardCapture):
    require_scope(request, "state")
    session_id = _resolve_wizard_session_id(request, capture.session_id)
    state = _get_wizard_state(request, session_id)

    if capture.rollback:
        history = state.get("capture_order", [])
        if not history:
            return {
                "status": "idle",
                "session_id": session_id,
                "next_button": get_next_step(state),
                "progress": len(state.get("captures", {})),
                "total": len(state.get("sequence", [])),
            }
        rolled_back = history.pop()
        state.get("captures", {}).pop(rolled_back, None)
        return {
            "status": "rolled_back",
            "session_id": session_id,
            "button_name": rolled_back,
            "next_button": rolled_back,
            "progress": len(state.get("captures", {})),
            "total": len(state.get("sequence", [])),
        }

    button_name = (capture.button_name or capture.control_key or "").strip()
    if not button_name:
        raise HTTPException(status_code=400, detail="button_name is required")
    if button_name not in state["sequence"]:
        raise HTTPException(status_code=400, detail="Control not part of wizard sequence")

    if capture.skip:
        entry = {
            "skipped": True,
            "captured_at": datetime.utcnow().isoformat(),
        }
    elif capture.input_event:
        entry = _wizard_capture_entry(button_name, capture.input_event, capture.control_type)
    else:
        if capture.pin is None:
            raise HTTPException(status_code=400, detail="input_event or pin is required")
        entry = {
            "pin": int(capture.pin),
            "type": capture.control_type or default_control_type(button_name),
            "captured_at": datetime.utcnow().isoformat(),
        }

    state["captures"][button_name] = entry
    history = state.setdefault("capture_order", [])
    if button_name in history:
        history.remove(button_name)
    history.append(button_name)

    next_button = get_next_step(state)
    if next_button is None:
        return {
            "status": "complete",
            "session_id": session_id,
            "button_name": button_name,
            "captures": state.get("captures", {}),
            "progress": len(state.get("captures", {})),
            "total": len(state.get("sequence", [])),
        }

    return {
        "status": "captured",
        "session_id": session_id,
        "button_name": button_name,
        "next_button": next_button,
        "next": next_button,
        "progress": len(state.get("captures", {})),
        "total": len(state.get("sequence", [])),
    }


@router.post("/wizard/preview")
async def wizard_preview(request: Request, payload: WizardCommitRequest = WizardCommitRequest()):
    """Preview wiring wizard captures before applying."""
    require_scope(request, "state")
    state = _get_wizard_state(request, payload.session_id)
    if not state["captures"]:
        return {"status": "empty"}

    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    existing: Dict[str, Any] = {}
    if mapping_file.exists():
        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                existing = json.load(f).get("mappings", {})
        except Exception:
            pass

    changes: List[Dict[str, Any]] = []
    for key, capture in state["captures"].items():
        old = existing.get(key, {})
        changes.append({
            "control_key": key,
            "new": capture,
            "old": old if old else None,
            "action": "update" if old else "add",
        })
    return {
        "status": "preview",
        "session_id": state.get("session_id") or _resolve_wizard_session_id(request, payload.session_id),
        "changes": changes,
        "total": len(changes),
    }


@router.post("/wizard/commit")
@router.post("/wizard/apply")
async def wizard_apply(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: WizardCommitRequest = WizardCommitRequest(),
):
    """Apply wiring wizard captures to controls.json."""
    require_scope(request, "config")
    ensure_writes_allowed(request)
    session_id = _resolve_wizard_session_id(request, payload.session_id)
    state = _get_wizard_state(request, session_id)
    if not state["captures"]:
        raise HTTPException(status_code=400, detail="No captures to apply")

    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"

    backup_path = None
    if mapping_file.exists() and getattr(request.app.state, "backup_on_write", True):
        backup_path = create_backup(mapping_file, drive_root)

    try:
        data = json.load(open(mapping_file, "r", encoding="utf-8")) if mapping_file.exists() else {"version": 1, "board": {}, "mappings": {}}
    except Exception:
        data = {"version": 1, "board": {}, "mappings": {}}
    if "mappings" not in data:
        data["mappings"] = {}

    for key, capture in state["captures"].items():
        if capture.get("skipped"):
            continue
        data["mappings"][key] = capture

    data["last_modified"] = datetime.now().isoformat()
    data["modified_by"] = request.headers.get("x-device-id", "wiring_wizard")

    try:
        _write_json_atomic(mapping_file, data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")

    await log_controller_change(request, drive_root, "wiring_wizard_apply",
        {"controls": list(state["captures"].keys()), "count": len(state["captures"])}, backup_path)

    gamepad_sync_result = _sync_gamepad_preferences_to_cascade_state(
        drive_root,
        request.app.state.manifest,
        backup=getattr(request.app.state, "backup_on_write", False),
    )

    # Trigger cascade if auto
    cascade_preference = get_cascade_preference(drive_root)
    cascade_result: Dict[str, Any] = {
        "preference": cascade_preference,
        "triggered": False,
    }
    if cascade_preference == "auto":
        requested_by = request.headers.get("x-device-id", "wiring_wizard")
        backup_on_write = getattr(request.app.state, "backup_on_write", False)
        cascade_job = enqueue_cascade_job(drive_root, requested_by=requested_by,
            metadata={"source": "wiring_wizard"}, backup=backup_on_write)
        background_tasks.add_task(run_cascade_job, drive_root,
            request.app.state.manifest, cascade_job["job_id"], backup=backup_on_write)
        cascade_result = {
            "preference": cascade_preference,
            "triggered": True,
            "job_id": cascade_job.get("job_id"),
        }

    applied_count = len(state.get("captures", {}))
    _wizard_states.pop(session_id, None)
    response = {"status": "committed", "controls_mapped": applied_count,
            "backup_path": str(backup_path) if backup_path else None,
            "cascade_preference": cascade_preference,
            "cascade_result": cascade_result,
            "file": str(mapping_file)}
    if gamepad_sync_result:
        response["gamepad_preferences_sync"] = gamepad_sync_result
    return response


@router.post("/wizard/cancel")
async def wizard_cancel(request: Request, payload: WizardCommitRequest = WizardCommitRequest()):
    require_scope(request, "state")
    session_id = _resolve_wizard_session_id(request, payload.session_id)
    _wizard_states.pop(session_id, None)
    return {
        "status": "cancelled",
        "session_id": session_id,
        "message": "Wizard cancelled. No changes were written.",
    }


# ============================================================================
# Player Identity Calibration
# ============================================================================

@router.get("/wizard/identity", response_model=PlayerIdentityResponse)
async def get_player_identity(request: Request):
    require_scope(request, "state")
    drive_root: Path = request.app.state.drive_root
    data = player_identity.load_bindings(drive_root)
    return PlayerIdentityResponse(status=data.get("status", "unbound"),
        bindings=data.get("bindings", {}), calibrated_at=data.get("calibrated_at"))


@router.post("/wizard/identity/bind")
async def bind_player_identity(request: Request, player: int):
    require_scope(request, "state")
    if player < 1 or player > 4:
        raise HTTPException(status_code=400, detail="Player must be 1-4")
    session_key = wizard_session_key(request)
    state = _wizard_states.get(session_key)
    if not state:
        drive_root: Path = request.app.state.drive_root
        existing = player_identity.load_bindings(drive_root)
        state = {"captures": {}, "sequence": [], "started_at": datetime.utcnow().isoformat(),
                 "identity": existing.get("bindings", {}), "identity_status": existing.get("status", "unbound"),
                 "identity_pending": None}
        _wizard_states[session_key] = state
    state["identity_pending"] = player
    get_input_detection_service(request).start_listening()
    return {"status": "awaiting_input", "message": f"Press any button at Player {player} station", "player": player}


@router.post("/wizard/identity/capture")
async def capture_player_identity(request: Request):
    require_scope(request, "state")
    state = _wizard_states.get(wizard_session_key(request))
    if not state:
        raise HTTPException(status_code=400, detail="No wizard session active")
    pending_player = state.get("identity_pending")
    if pending_player is None:
        raise HTTPException(status_code=400, detail="No identity bind pending.")

    latest_event = get_latest_event()
    if latest_event is None:
        raise HTTPException(status_code=400, detail="No input detected.")
    source_id = latest_event.source_id or "unknown"
    state.setdefault("identity", {})[source_id] = pending_player
    state["identity_pending"] = None
    state["identity_status"] = "pending_apply"
    return {"status": "captured", "source_id": source_id, "player": pending_player,
            "bindings": state["identity"], "message": f"Bound {source_id} to Player {pending_player}"}


@router.post("/wizard/identity/apply")
async def apply_player_identity(request: Request):
    require_scope(request, "config")
    state = _wizard_states.get(wizard_session_key(request))
    if not state:
        raise HTTPException(status_code=400, detail="No wizard session active")
    bindings = state.get("identity", {})
    if not bindings:
        raise HTTPException(status_code=400, detail="No identity bindings to apply")
    backup_path = player_identity.save_bindings(request.app.state.drive_root, bindings)
    state["identity_status"] = "bound"
    return {"status": "applied", "bindings": bindings,
            "backup_path": str(backup_path) if backup_path else None,
            "message": f"Applied {len(bindings)} identity binding(s)"}


@router.post("/wizard/identity/reset")
async def reset_player_identity(request: Request):
    require_scope(request, "config")
    drive_root: Path = request.app.state.drive_root
    backup_path = player_identity.reset_bindings(drive_root)
    state = _wizard_states.get(wizard_session_key(request))
    if state:
        state["identity"] = {}
        state["identity_status"] = "unbound"
        state["identity_pending"] = None
    return {"status": "reset", "backup_path": str(backup_path) if backup_path else None,
            "message": "Identity bindings reset."}


# ============================================================================
# Click-to-Map Input Detection (pygame-based)
# ============================================================================

@router.get("/input-detect")
async def get_captured_input(request: Request):
    with _click_to_map_lock:
        if _click_to_map_latest_input:
            return _click_to_map_latest_input
    return {"captured_key": None, "source": None, "timestamp": None}


@router.post("/input-detect/clear")
async def clear_captured_input(request: Request):
    global _click_to_map_latest_input
    with _click_to_map_lock:
        _click_to_map_latest_input = None
    return {"status": "cleared"}


@router.post("/input-detect/start")
async def start_click_to_map_detection(request: Request):
    global _click_to_map_latest_input

    def capture_handler(keycode: str):
        global _click_to_map_latest_input
        with _click_to_map_lock:
            _click_to_map_latest_input = {"captured_key": keycode, "source": detect_input_mode(keycode), "timestamp": time.time()}

    service = get_input_detection_service(request)
    service.set_learn_mode(True)
    service.register_raw_handler(capture_handler)
    service.start_listening()

    with _click_to_map_lock:
        _click_to_map_latest_input = None
    return {"status": "started", "message": "Input detection started for click-to-map"}


@router.post("/input-detect/stop")
async def stop_click_to_map_detection(request: Request):
    global _click_to_map_latest_input
    service = get_input_detection_service(request)
    if service:
        service.set_learn_mode(False)
    with _click_to_map_lock:
        _click_to_map_latest_input = None
    return {"status": "stopped", "message": "Input detection stopped"}


# ============================================================================
# Genre Profile Endpoints
# ============================================================================

@router.get("/genre-profiles")
async def list_genre_profiles(request: Request) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    profiles = service.list_profiles()
    genre_map = service.get_all_matching_genres()
    return {"status": "success", "profile_count": len(profiles), "profiles": profiles, "genre_mappings": genre_map}


@router.get("/genre-profiles/{profile_key}")
async def get_genre_profile(request: Request, profile_key: str) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    service = get_genre_profile_service(request.app.state.drive_root)
    profile = service.get_profile(profile_key)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Genre profile '{profile_key}' not found")
    return {"status": "success", "profile_key": profile_key, "profile": profile}


@router.get("/genre-profiles/match/genre/{genre}")
async def get_profile_for_genre(request: Request, genre: str) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    service = get_genre_profile_service(request.app.state.drive_root)
    profile_key, profile = service.get_profile_for_genre(genre)
    return {"status": "success", "genre_searched": genre, "profile_key": profile_key, "profile": profile,
            "match_type": "exact" if profile_key != "default" else "default"}


@router.get("/genre-profiles/match/game")
async def get_profile_for_game(request: Request, game_id: Optional[str] = None, game_title: Optional[str] = None,
                                genre: Optional[str] = None, platform: Optional[str] = None) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    service = get_genre_profile_service(request.app.state.drive_root)
    profile_key, profile = service.get_profile_for_game(game_id=game_id, game_title=game_title, genre=genre, platform=platform)
    return {"status": "success", "game_id": game_id, "game_title": game_title, "genre_provided": genre,
            "platform": platform, "profile_key": profile_key, "profile": profile}


@router.get("/genre-profiles/{profile_key}/emulator/{emulator}")
async def get_emulator_mappings_for_profile(request: Request, profile_key: str, emulator: str) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    drive_root: Path = request.app.state.drive_root
    service = get_genre_profile_service(drive_root)
    controls_path = drive_root / "config" / "mappings" / "controls.json"
    base_controls: Dict[str, Any] = {}
    if controls_path.exists():
        try:
            base_controls = json.load(open(controls_path, "r", encoding="utf-8")).get("mappings", {})
        except Exception:
            pass
    mappings = service.get_emulator_mappings(emulator, profile_key, base_controls)
    if mappings is None:
        raise HTTPException(status_code=404, detail=f"No emulator mappings for '{emulator}' in '{profile_key}'")
    return {"status": "success", "profile_key": profile_key, "emulator": emulator, "mappings": mappings}


@router.get("/genre-profiles/{profile_key}/led")
async def get_led_profile_for_genre(request: Request, profile_key: str) -> Dict[str, Any]:
    from ..services.genre_profile_service import get_genre_profile_service
    service = get_genre_profile_service(request.app.state.drive_root)
    led_profile = service.get_led_profile(profile_key)
    if not led_profile:
        raise HTTPException(status_code=404, detail=f"No LED profile for '{profile_key}'")
    return {"status": "success", "profile_key": profile_key, "led_profile": led_profile}


# ============================================================================
# MAME Per-Game Config Fix
# ============================================================================

@router.post("/mame-fix")
async def fix_mame_game_config(request: Request, payload: MAMEFixRequest):
    drive_root: Path = request.app.state.drive_root
    rom_name = payload.rom_name.lower().replace(".zip", "").replace(".7z", "")
    detected_genre = get_genre_for_rom(rom_name)
    genre = payload.genre or detected_genre

    mame_cfg_dir = drive_root / "Emulators" / "MAME" / "cfg"
    if not is_allowed_file(mame_cfg_dir / f"{rom_name}.cfg", drive_root,
                           request.app.state.manifest.get("sanctioned_paths", [])):
        raise HTTPException(status_code=403, detail="MAME cfg directory not in sanctioned paths")

    try:
        cfg_path = save_pergame_config(rom_name=rom_name, cfg_dir=mame_cfg_dir, genre=genre, backup=True)
        genre_desc = {"fighting": "6-button fighting game", "racing": "racing game",
                      "shooter": "shooter", "default": "arcade game"}.get(genre, "arcade game")
        return {"status": "success", "rom_name": rom_name, "genre": genre, "genre_detected": detected_genre,
                "cfg_path": str(cfg_path),
                "chuck_prompt": f"Done! Created config for {rom_name} as a {genre_desc}. Restart and try again!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate config: {str(e)}")


@router.get("/mame-fix/fighting-games")
async def list_supported_fighting_games(request: Request):
    games = get_supported_fighting_games()
    return {"status": "success", "count": len(games), "games": games,
            "chuck_prompt": f"I know {len(games)} fighting games. Tell me which one needs fixing!"}
