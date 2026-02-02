"""
LED Calibration Service - 4-Player Port Mapping Wizard

This service manages the calibration wizard session where:
1. System blinks each LED port in sequence
2. User clicks the corresponding button in the GUI
3. Mapping is saved to JSON for physical-to-logical translation

Architecture:
- Singleton session pattern (one wizard at a time)
- Async background task for continuous blinking (non-blocking)
- Pydantic models for strict data validation
- Atomic file writes per A: Drive Strategy
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field

from backend.constants.paths import Paths
from backend.services.blinky_service import BlinkyService

logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class LEDMappingEntry(BaseModel):
    """A single port-to-button mapping."""
    logical_id: str  # e.g., "p1.b1", "p2.start"
    description: str = ""  # Optional human-readable description
    device_id: str = ""  # Which LED-Wiz board (e.g., "fafa:00f0")
    mapped_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CalibrationSession(BaseModel):
    """State of an active calibration wizard session."""
    is_active: bool = False
    token: str = ""
    current_port: int = 1
    total_ports: int = 96  # 3 boards × 32 ports
    player_count: int = 4  # 4-player support
    mappings: Dict[str, LEDMappingEntry] = {}  # Key is port number as string
    started_at: str = ""
    skipped_ports: list = []


class CalibrationStatus(BaseModel):
    """Response model for calibration status."""
    is_active: bool
    current_port: int
    total_ports: int
    mapped_count: int
    skipped_count: int
    progress_percent: float


# =============================================================================
# CALIBRATION SERVICE
# =============================================================================

class LEDCalibrationService:
    """
    Singleton service for managing LED calibration wizard sessions.
    
    Uses asyncio background tasks to continuously blink the current port
    without blocking the FastAPI event loop.
    """
    
    _session: CalibrationSession = CalibrationSession()
    _blink_task: Optional[asyncio.Task] = None
    
    # Mapping file path following A: Drive Strategy
    @classmethod
    def _mapping_file_path(cls) -> Path:
        """Get the path for the LED port mapping JSON file."""
        return Paths.drive_root() / ".aa" / "config" / "led_port_mapping.json"
    
    @classmethod
    def get_status(cls) -> CalibrationStatus:
        """Get current calibration session status."""
        return CalibrationStatus(
            is_active=cls._session.is_active,
            current_port=cls._session.current_port,
            total_ports=cls._session.total_ports,
            mapped_count=len(cls._session.mappings),
            skipped_count=len(cls._session.skipped_ports),
            progress_percent=round(
                (cls._session.current_port - 1) / cls._session.total_ports * 100, 1
            ) if cls._session.total_ports > 0 else 0
        )
    
    @classmethod
    async def start_wizard(cls, total_ports: int = 96, player_count: int = 4) -> CalibrationSession:
        """
        Start a new calibration wizard session.
        
        Resets any existing session and begins blinking port 1.
        """
        # Cancel any existing session
        await cls._stop_blinking()
        
        # Initialize new session
        import uuid
        cls._session = CalibrationSession(
            is_active=True,
            token=str(uuid.uuid4()),
            current_port=1,
            total_ports=total_ports,
            player_count=player_count,
            mappings={},
            started_at=datetime.now().isoformat(),
            skipped_ports=[]
        )
        
        logger.info(f"[Calibration] Started wizard: {total_ports} ports, {player_count} players")
        
        # Start blinking first port
        await cls._start_blinking(1)
        
        return cls._session
    
    @classmethod
    async def confirm_mapping(cls, logical_id: str, description: str = "") -> CalibrationSession:
        """
        User confirmed which button corresponds to the current blinking port.
        
        Records the mapping and advances to the next port.
        """
        if not cls._session.is_active:
            raise ValueError("No active calibration session")
        
        port = cls._session.current_port
        port_str = str(port)
        
        # Record the mapping
        cls._session.mappings[port_str] = LEDMappingEntry(
            logical_id=logical_id,
            description=description or f"Mapped via wizard"
        )
        
        logger.info(f"[Calibration] Port {port} -> {logical_id}")
        
        # Stop current blink
        await cls._stop_blinking()
        
        # Advance to next port
        cls._session.current_port += 1
        
        # Check if done
        if cls._session.current_port > cls._session.total_ports:
            await cls.finish()
            return cls._session
        
        # Start blinking next port
        await cls._start_blinking(cls._session.current_port)
        
        return cls._session
    
    @classmethod
    async def skip_port(cls) -> CalibrationSession:
        """
        Skip the current port (e.g., if no LED visible or broken).
        """
        if not cls._session.is_active:
            raise ValueError("No active calibration session")
        
        port = cls._session.current_port
        cls._session.skipped_ports.append(port)
        
        logger.info(f"[Calibration] Skipped port {port}")
        
        # Stop current blink
        await cls._stop_blinking()
        
        # Advance to next port
        cls._session.current_port += 1
        
        # Check if done
        if cls._session.current_port > cls._session.total_ports:
            await cls.finish()
            return cls._session
        
        # Start blinking next port
        await cls._start_blinking(cls._session.current_port)
        
        return cls._session
    
    @classmethod
    async def finish(cls) -> dict:
        """
        Finish the calibration wizard and save mappings to JSON.
        """
        await cls._stop_blinking()
        cls._session.is_active = False
        
        # Prepare output
        output = {
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "session_started": cls._session.started_at,
            "total_ports": cls._session.total_ports,
            "player_count": cls._session.player_count,
            "mappings": {
                k: v.dict() for k, v in cls._session.mappings.items()
            },
            "skipped_ports": cls._session.skipped_ports
        }
        
        # Save to file (atomic write pattern)
        save_path = cls._mapping_file_path()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file first, then rename (atomic)
        temp_path = save_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        temp_path.replace(save_path)
        
        logger.info(f"[Calibration] Saved {len(cls._session.mappings)} mappings to {save_path}")
        
        # Auto-translate to LEDBlinky format (Phase 2: JSON → XML)
        translate_result = None
        try:
            from backend.services.led_blinky_translator import LEDBlinkyTranslator
            translate_result = LEDBlinkyTranslator.translate()
            if translate_result.get("success"):
                logger.info(f"[Calibration] Auto-translated to LEDBlinkyInputMap.xml")
            else:
                logger.warning(f"[Calibration] Translation failed: {translate_result.get('error')}")
        except Exception as e:
            logger.error(f"[Calibration] Translation error: {e}")
            translate_result = {"success": False, "error": str(e)}
        
        return {
            "status": "complete",
            "mapped_count": len(cls._session.mappings),
            "skipped_count": len(cls._session.skipped_ports),
            "file_path": str(save_path),
            "translation": translate_result
        }
    
    @classmethod
    async def cancel(cls) -> dict:
        """Cancel the current calibration session without saving."""
        await cls._stop_blinking()
        cls._session.is_active = False
        logger.info("[Calibration] Session cancelled")
        return {"status": "cancelled"}
    
    # =========================================================================
    # PRIVATE ASYNC HELPERS
    # =========================================================================
    
    @classmethod
    async def _start_blinking(cls, port: int):
        """Start a non-blocking background task to pulse the LED."""
        if cls._blink_task and not cls._blink_task.done():
            cls._blink_task.cancel()
            try:
                await cls._blink_task
            except asyncio.CancelledError:
                pass
        
        # Create background blink loop
        cls._blink_task = asyncio.create_task(cls._blink_loop(port))
        logger.debug(f"[Calibration] Started blinking port {port}")
    
    @classmethod
    async def _stop_blinking(cls):
        """Stop the current blink loop and turn off the LED."""
        if cls._blink_task and not cls._blink_task.done():
            cls._blink_task.cancel()
            try:
                await cls._blink_task
            except asyncio.CancelledError:
                pass
        cls._blink_task = None
        
        # Ensure LED is off
        await BlinkyService.all_off()
    
    @classmethod
    async def _blink_loop(cls, port: int):
        """
        Continuously pulse the LED at the given port until cancelled.
        
        Uses BlinkyService.flash_port() which already handles the on/off cycle.
        """
        try:
            while True:
                # Flash the port (turns on, waits, turns off)
                await BlinkyService.flash_port(
                    port=port,
                    intensity=48,  # Max brightness for visibility
                    duration_ms=400
                )
                # Small pause between flashes
                await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            # Clean exit when cancelled
            pass
        except Exception as e:
            logger.error(f"[Calibration] Blink loop error: {e}")
