"""
Encoder State Manager - Tracks Pactech board mode baseline and drift detection.

This module manages:
- Baseline mode (keyboard/xinput/dinput) captured during calibration
- Current mode detection from recent inputs
- Mode drift detection when the board silently changes modes
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Valid encoder modes
ENCODER_MODES = ("keyboard", "xinput", "dinput", "unknown")

# Default state when no calibration exists
DEFAULT_STATE = {
    "baseline_mode": None,
    "baseline_captured_at": None,
    "last_detected_mode": None,
    "last_input_at": None,
    "mode_mismatch_count": 0,
    "needs_recalibration": False,
    "calibration_history": [],
}


class EncoderStateManager:
    """Manages encoder mode baseline and drift detection.
    
    Persists state to `.aa/state/controller/encoder_state.json`.
    Tracks:
      - baseline_mode: The mode captured during calibration
      - last_detected_mode: The mode inferred from the most recent input
      - mode_mismatch_count: Consecutive inputs that don't match baseline
      - needs_recalibration: True if mode drift detected
    """
    
    MISMATCH_THRESHOLD = 3  # Trigger recalibration warning after this many mismatches
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
        self._state_file = drive_root / ".aa" / "state" / "controller" / "encoder_state.json"
        self._state: Dict[str, Any] = {}
        self._lock = Lock()
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from disk or initialize with defaults."""
        with self._lock:
            if self._state_file.exists():
                try:
                    with open(self._state_file, "r", encoding="utf-8") as f:
                        self._state = json.load(f)
                    # Ensure all keys exist
                    for key, default_value in DEFAULT_STATE.items():
                        if key not in self._state:
                            self._state[key] = default_value
                    logger.debug("Loaded encoder state from %s", self._state_file)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to load encoder state, using defaults: %s", e)
                    self._state = dict(DEFAULT_STATE)
            else:
                self._state = dict(DEFAULT_STATE)
    
    def _save_state(self) -> None:
        """Persist state to disk."""
        with self._lock:
            try:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._state_file, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2)
                logger.debug("Saved encoder state to %s", self._state_file)
            except OSError as e:
                logger.error("Failed to save encoder state: %s", e)
    
    @property
    def baseline_mode(self) -> Optional[str]:
        """The calibrated baseline mode."""
        return self._state.get("baseline_mode")
    
    @property
    def last_detected_mode(self) -> Optional[str]:
        """Mode detected from most recent input."""
        return self._state.get("last_detected_mode")
    
    @property
    def needs_recalibration(self) -> bool:
        """True if mode drift was detected."""
        return self._state.get("needs_recalibration", False)
    
    @property
    def mode_match(self) -> bool:
        """True if current mode matches baseline."""
        if not self.baseline_mode or not self.last_detected_mode:
            return True  # No baseline set, assume OK
        return self.baseline_mode == self.last_detected_mode
    
    def get_state(self) -> Dict[str, Any]:
        """Return current state for API response."""
        return {
            "baseline_mode": self.baseline_mode,
            "baseline_captured_at": self._state.get("baseline_captured_at"),
            "current_mode": self.last_detected_mode,
            "last_input_at": self._state.get("last_input_at"),
            "mode_match": self.mode_match,
            "needs_recalibration": self.needs_recalibration,
            "mismatch_count": self._state.get("mode_mismatch_count", 0),
        }
    
    def capture_baseline(self, mode: str, keycode: str = "") -> Dict[str, Any]:
        """Capture current mode as the baseline.
        
        Called during calibration when user presses a button.
        
        Args:
            mode: The detected mode (keyboard/xinput/dinput)
            keycode: The keycode that was captured (for logging)
            
        Returns:
            Updated state dict
        """
        now = datetime.utcnow().isoformat()
        
        with self._lock:
            # Save previous baseline to history
            if self.baseline_mode:
                history = self._state.get("calibration_history", [])
                history.append({
                    "mode": self.baseline_mode,
                    "replaced_at": now,
                    "replaced_by": mode,
                })
                # Keep only last 10 entries
                self._state["calibration_history"] = history[-10:]
            
            self._state["baseline_mode"] = mode
            self._state["baseline_captured_at"] = now
            self._state["last_detected_mode"] = mode
            self._state["last_input_at"] = now
            self._state["mode_mismatch_count"] = 0
            self._state["needs_recalibration"] = False
        
        self._save_state()
        logger.info("Encoder baseline captured: mode=%s, keycode=%s", mode, keycode)
        
        return self.get_state()
    
    def record_input(self, detected_mode: str) -> Dict[str, Any]:
        """Record an input and check for mode drift.
        
        Called after each input is captured to compare against baseline.
        
        Args:
            detected_mode: The mode inferred from this input's keycode
            
        Returns:
            Dict with mode_match and needs_recalibration flags
        """
        now = datetime.utcnow().isoformat()
        
        with self._lock:
            self._state["last_detected_mode"] = detected_mode
            self._state["last_input_at"] = now
            
            # Check for mode mismatch
            if self.baseline_mode and detected_mode != self.baseline_mode:
                self._state["mode_mismatch_count"] = self._state.get("mode_mismatch_count", 0) + 1
                
                if self._state["mode_mismatch_count"] >= self.MISMATCH_THRESHOLD:
                    self._state["needs_recalibration"] = True
                    logger.warning(
                        "Mode drift detected: baseline=%s, current=%s, mismatches=%d",
                        self.baseline_mode,
                        detected_mode,
                        self._state["mode_mismatch_count"],
                    )
            else:
                # Reset mismatch count on matching input
                self._state["mode_mismatch_count"] = 0
        
        self._save_state()
        
        return {
            "mode_match": self.mode_match,
            "needs_recalibration": self.needs_recalibration,
            "baseline_mode": self.baseline_mode,
            "detected_mode": detected_mode,
        }
    
    def clear_recalibration_flag(self) -> None:
        """Clear the recalibration needed flag (after user recalibrates)."""
        with self._lock:
            self._state["needs_recalibration"] = False
            self._state["mode_mismatch_count"] = 0
        self._save_state()
    
    def reset(self) -> None:
        """Reset state to defaults (clear baseline)."""
        with self._lock:
            self._state = dict(DEFAULT_STATE)
        self._save_state()
        logger.info("Encoder state reset to defaults")


# Module-level singleton instance (initialized when needed)
_encoder_state_manager: Optional[EncoderStateManager] = None
_encoder_state_lock = Lock()


def get_encoder_state_manager(drive_root: Path) -> EncoderStateManager:
    """Get or create the encoder state manager singleton."""
    global _encoder_state_manager
    with _encoder_state_lock:
        if _encoder_state_manager is None:
            _encoder_state_manager = EncoderStateManager(drive_root)
        return _encoder_state_manager
