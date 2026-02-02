"""
MODULE B: CONTROLLER WIZARD - WebSocket Input Stream
Role: Real-time input visualization for "What am I pressing?"
Governance: Integrates with existing InputDetectionService (pygame-based)
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pathlib import Path
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wizard", tags=["Controller Wizard"])

# Import the existing InputDetectionService from chuck
# This uses pygame for superior Windows XInput support (not the 'inputs' library)
from backend.services.chuck.input_detector import InputDetectionService, InputEvent


@router.websocket("/listen")
async def websocket_input_stream(websocket: WebSocket):
    """
    Real-time stream of inputs for the Frontend Wizard.
    Visualizes "What am I pressing?" with zero-latency feedback.
    
    Protocol:
    - Client connects via WebSocket
    - Server streams normalized input events as JSON
    - Client displays visual feedback (button lights up)
    
    Message format:
    {
        "type": "joy",
        "device_type": "gamepad", 
        "code": "BTN_0_JS0",
        "player": 1,
        "control_key": "p1.button1",
        "timestamp": 1234567890.123
    }
    """
    await websocket.accept()
    logger.info("Wizard WebSocket connected")
    
    # Create async queue for thread-safe communication
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    
    # Bridge sync callback to async queue
    def on_input(event: InputEvent):
        """Convert InputEvent to dict and push to async queue."""
        # Extract pygame device index from keycode (e.g., "BTN_0_JS0" -> 0)
        # Convert to MAME's 1-based indexing: JS0 -> device_id=1
        js_idx = 0
        if "_JS" in event.keycode:
            try:
                js_idx = int(event.keycode.split("_JS")[-1])
            except ValueError:
                pass
        
        data = {
            "type": "joy" if event.input_mode in ("xinput", "dinput") else "key",
            "device_type": event.input_mode,
            "code": event.keycode,
            "player": event.player,
            "control_key": event.control_key,
            "control_type": event.control_type,
            "pin": event.pin,
            "device_id": js_idx + 1,  # MAME uses 1-based indexing (JS0 -> 1)
            "timestamp": event.timestamp,
        }
        loop.call_soon_threadsafe(queue.put_nowait, data)
    
    # Get drive root from environment (A: Drive Strategy)
    drive_root = Path(os.getenv("AA_DRIVE_ROOT", r"A:\Arcade Assistant Local"))
    
    # Create and start detection service in Learn Mode
    # Learn mode captures ALL inputs, not just mapped ones
    detector = InputDetectionService(board_type="generic", drive_root=drive_root)
    detector.set_learn_mode(True)
    detector.register_handler(on_input)
    detector.start_listening()
    
    try:
        while True:
            # Wait for input from queue with timeout for keepalive
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping", "timestamp": asyncio.get_event_loop().time()})
                
    except WebSocketDisconnect:
        logger.info("Wizard WebSocket disconnected by client")
    except Exception as e:
        logger.error(f"Wizard WebSocket error: {e}")
    finally:
        detector.stop_listening()
        detector.unregister_handler(on_input)
        logger.info("Wizard input detection stopped")


@router.get("/status")
async def get_wizard_status():
    """
    Check if the wizard input detection system is available.
    
    Returns:
        Status indicating pygame/input detection availability
    """
    try:
        import pygame
        pygame_available = True
        joystick_count = pygame.joystick.get_count()
    except Exception:
        pygame_available = False
        joystick_count = 0
    
    try:
        from pynput import keyboard
        pynput_available = True
    except Exception:
        pynput_available = False
    
    return {
        "status": "ready" if (pygame_available or pynput_available) else "degraded",
        "pygame_available": pygame_available,
        "pynput_available": pynput_available,
        "joystick_count": joystick_count,
        "message": "Wizard ready for input detection" if pygame_available else "Install pygame for gamepad support"
    }


# =============================================================================
# MODULE B.3: Save Bridge - Connect WebSocket to MAME Config Writer
# =============================================================================

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import json

from backend.services.mame_config_generator import MameConfigWriter, MAMEConfigError


# Pydantic Models for Strict Schema Validation
class BoardInfo(BaseModel):
    """Board/encoder hardware info."""
    vid: str = Field(..., description="Vendor ID (hex string)")
    pid: str = Field(..., description="Product ID (hex string)")
    name: str = Field(default="Unknown", description="Human-readable name")
    detected: bool = Field(default=False, description="Whether board was detected at runtime")
    modes: Optional[Dict[str, bool]] = Field(default=None, description="Board mode flags")


class ControlMapping(BaseModel):
    """Single control mapping entry."""
    pin: int = Field(..., ge=1, le=128, description="Physical pin number (1-128)")
    type: str = Field(..., description="Control type: button, joystick, coin, start")
    label: str = Field(default="", description="Human-readable label")
    keycode: Optional[str] = Field(default=None, description="Captured keycode from Learn Wizard")


class ControlsJsonSchema(BaseModel):
    """
    Strict schema for controls.json.
    This is the 'Rosetta Stone' between hardware and MAME config.
    """
    version: str = Field(default="1.0", description="Schema version")
    comment: Optional[str] = Field(default=None, description="Optional comment")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of creation")
    last_modified: Optional[str] = Field(default=None, description="ISO timestamp of last modification")
    modified_by: Optional[str] = Field(default="wizard", description="Agent/user that made changes")
    encoder_mode: Optional[str] = Field(default="xinput", description="Encoder mode: xinput, keyboard, dinput")
    board: Optional[BoardInfo] = Field(default=None, description="Board hardware info")
    mappings: Dict[str, ControlMapping] = Field(..., description="Control key to mapping")

    class Config:
        extra = "allow"  # Allow additional fields for forward compatibility


class SaveWizardRequest(BaseModel):
    """Request body for POST /api/wizard/save."""
    controls: ControlsJsonSchema = Field(..., description="Full controls.json structure")
    generate_mame_config: bool = Field(default=True, description="If True, also generate MAME default.cfg")


class SaveWizardResponse(BaseModel):
    """Response from POST /api/wizard/save."""
    status: str
    controls_path: str
    mame_config_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.post("/save", response_model=SaveWizardResponse)
async def save_wizard_mappings(request: SaveWizardRequest):
    """
    Save controls.json and optionally generate MAME config.
    
    This is the 'Save Bridge' connecting the Frontend Wizard to the MAME Config Writer.
    
    Flow:
    1. Validate incoming JSON with Pydantic (strict schema)
    2. Save to A:\Arcade Assistant Local\config\mappings\controls.json
    3. Immediately call MameConfigWriter.write() to generate default.cfg
    4. Return success/fail status
    
    Governance:
    - Safety First: MameConfigWriter creates backup before writing
    - A: Drive Strategy: All paths are absolute A: drive paths
    - No OR Logic: MAME config has single bindings per control
    """
    # Path constants (A: Drive Strategy)
    controls_path = Path(r"A:\Arcade Assistant Local\config\mappings\controls.json")
    
    try:
        # 1. Prepare the controls.json data
        controls_dict = request.controls.model_dump(exclude_none=True)
        
        # Add/update metadata
        controls_dict["last_modified"] = datetime.now().isoformat()
        controls_dict["modified_by"] = "wizard"
        
        # Convert ControlMapping objects to dicts
        if "mappings" in controls_dict:
            for key, mapping in controls_dict["mappings"].items():
                if hasattr(mapping, "model_dump"):
                    controls_dict["mappings"][key] = mapping.model_dump(exclude_none=True)
        
        # 2. Save controls.json
        controls_path.parent.mkdir(parents=True, exist_ok=True)
        with open(controls_path, "w", encoding="utf-8") as f:
            json.dump(controls_dict, f, indent=2)
        
        logger.info(f"Saved controls.json: {controls_path}")
        
        # 3. Generate MAME config if requested
        mame_result = None
        if request.generate_mame_config:
            try:
                writer = MameConfigWriter(controls_json_path=controls_path)
                mame_result = writer.write(create_backup=True)
                logger.info(f"Generated MAME config: {mame_result}")
            except MAMEConfigError as e:
                logger.error(f"MAME config generation failed: {e}")
                return SaveWizardResponse(
                    status="partial",
                    controls_path=str(controls_path),
                    mame_config_result=None,
                    error=f"controls.json saved, but MAME config failed: {str(e)}"
                )
        
        return SaveWizardResponse(
            status="success",
            controls_path=str(controls_path),
            mame_config_result=mame_result,
            error=None
        )
        
    except Exception as e:
        logger.error(f"Wizard save failed: {e}")
        return SaveWizardResponse(
            status="error",
            controls_path=str(controls_path),
            mame_config_result=None,
            error=str(e)
        )


@router.get("/controls")
async def get_current_controls():
    """
    Read the current controls.json file.
    
    Returns the current mappings so the frontend can pre-populate the wizard.
    """
    controls_path = Path(r"A:\Arcade Assistant Local\config\mappings\controls.json")
    
    if not controls_path.exists():
        return {
            "status": "not_found",
            "controls": None,
            "message": "No controls.json found. Run the wizard to create one."
        }
    
    try:
        with open(controls_path, "r", encoding="utf-8") as f:
            controls = json.load(f)
        
        return {
            "status": "ok",
            "controls": controls,
            "path": str(controls_path)
        }
    except Exception as e:
        return {
            "status": "error",
            "controls": None,
            "message": str(e)
        }

