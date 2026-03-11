from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

try:  # pragma: no cover - optional dependency
    from pynput import keyboard
except Exception:  # pragma: no cover - gracefully degrade when unavailable
    keyboard = None  # type: ignore

# HEADLESS MODE: Required for running as a backend service without display
# Must be set BEFORE pygame import
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

try:  # pragma: no cover - pygame for XInput gamepad detection (better Windows support)
    import pygame
    pygame.init()
    pygame.joystick.init()
except Exception:  # pragma: no cover
    pygame = None  # type: ignore


if TYPE_CHECKING:
    from .encoder_state import EncoderStateManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InputEvent:
    """Represents a single detected encoder input event."""

    timestamp: float
    keycode: str
    pin: int
    control_key: str
    player: int
    control_type: str
    source_id: str = ""  # Board type identifier for player identity calibration
    input_mode: str = "keyboard"  # keyboard, xinput, or dinput
    device_id: int = 1  # MAME-compatible 1-based device index (pygame JS0 -> device_id=1)


# XInput Trigger-to-Button mapping for MAME compatibility
# Xbox triggers are axes 4 & 5, but MAME treats them as buttons 7 & 8
TRIGGER_TO_BUTTON = {
    "TRIGGER_0": "BUTTON7",  # Left Trigger (LT) -> Button 7
    "TRIGGER_1": "BUTTON8",  # Right Trigger (RT) -> Button 8
}


# Encoder mode detection
ENCODER_MODES = {
    "keyboard": "Keyboard Mode - sends keystrokes",
    "xinput": "XInput Mode - Xbox controller emulation",
    "dinput": "DirectInput Mode - Generic gamepad",
    "unknown": "Unknown mode",
}



def detect_input_mode(keycode: str) -> str:
    """Detect encoder mode from a captured keycode/input.
    
    Returns: "keyboard", "xinput", "dinput", or "unknown"
    """
    if not keycode:
        return "unknown"
    
    kc = keycode.lower()
    
    # Keyboard mode indicators
    if kc.startswith("key_") or kc.startswith("shift") or kc.startswith("ctrl"):
        return "keyboard"
    if any(kc.startswith(p) for p in ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"]):
        return "keyboard"
    if kc in ["up", "down", "left", "right", "enter", "space", "escape", "tab"]:
        return "keyboard"
    
    # XInput mode indicators (Xbox controller)
    if "axis" in kc or "stick" in kc:
        return "xinput"
    if kc.startswith("btn_") and any(x in kc for x in ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "start", "back", "guide"]):
        return "xinput"
    if "dpad" in kc or "trigger" in kc or "bumper" in kc:
        return "xinput"
    
    # DirectInput mode indicators (generic gamepad)
    if kc.startswith("button") or kc.startswith("btn"):
        # DirectInput uses numbered buttons (button0, button1, etc.)
        return "dinput"
    if "hat" in kc or "pov" in kc:
        return "dinput"
    
    # Function keys often used by keyboard-mode encoders
    if kc.startswith("f") and kc[1:].isdigit():
        return "keyboard"
    
    return "unknown"


_KEY_ALIAS_MAP: Dict[str, str] = {
    "ctrl_l": "left_ctrl",
    "ctrl": "left_ctrl",
    "ctrl_r": "right_ctrl",
    "shift_l": "left_shift",
    "shift_r": "right_shift",
    "alt_l": "left_alt",
    "alt_r": "right_alt",
    "return": "enter",
    "carriage_return": "enter",
    "esc": "escape",
    "del": "delete",
    "decimal": ".",
}

_MAPPING_DIR = Path(__file__).resolve().parents[2] / "data" / "board_mappings"


class InputDetectionService:
    """Captures keyboard and gamepad events from encoder boards and emits structured events."""

    def __init__(self, board_type: str, drive_root: Path) -> None:
        self.board_type = (board_type or "generic").lower()
        self.drive_root = Path(drive_root)
        self._handlers: Set[Callable[[InputEvent], None]] = set()
        self._raw_handlers: Set[Callable[[str], None]] = set()  # Learn mode handlers
        self._listener: Optional["keyboard.Listener"] = None
        self._gamepad_thread: Optional[threading.Thread] = None
        self._gamepad_stop_event = threading.Event()
        self._gamepad_ready_event: Optional[threading.Event] = None  # Signals when gamepad init done
        self._listener_lock = threading.Lock()
        self._keycode_to_pin = self._load_mapping()
        self._learn_mode = False  # When True, capture ALL keys
        self._encoder_state_manager: Optional["EncoderStateManager"] = None
    
    def set_encoder_state_manager(self, manager: "EncoderStateManager") -> None:
        """Set the encoder state manager for mode drift detection."""
        self._encoder_state_manager = manager

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def start_listening(self) -> None:
        """Begin listening for encoder keyboard AND gamepad events."""
        with self._listener_lock:
            # Start keyboard listener if pynput available
            if keyboard is not None:
                if self._listener is None:
                    self._listener = keyboard.Listener(on_press=self._handle_key_press)
                    self._listener.daemon = True
                    self._listener.start()
                    print(f"=" * 60)
                    print(f"[InputDetector] KEYBOARD LISTENER STARTED for {self.board_type}")
                    print(f"[InputDetector] Learn mode: {self._learn_mode}")
                    print(f"[InputDetector] Raw handlers: {len(self._raw_handlers)}")
                    print(f"=" * 60, flush=True)
                    logger.info("Keyboard detection started for board type %s", self.board_type)
                else:
                    print(f"[InputDetector] Keyboard listener already running for {self.board_type}")
            else:
                print("[InputDetector] pynput not installed - keyboard detection disabled")
            
            # Start gamepad listener if pygame available
            if pygame is not None:
                if self._gamepad_thread is None or not self._gamepad_thread.is_alive():
                    self._gamepad_stop_event.clear()
                    self._gamepad_ready_event = threading.Event()  # Signal when ready
                    self._gamepad_thread = threading.Thread(
                        target=self._gamepad_listener_loop,
                        daemon=True,
                        name="GamepadListener"
                    )
                    self._gamepad_thread.start()

                    # Wait for gamepad initialization to complete
                    # This fixes "first axis input lost" bug where joystick directions
                    # don't register until after first button press
                    if self._gamepad_ready_event.wait(timeout=2.0):
                        joystick_count = pygame.joystick.get_count()
                        print(f"[InputDetector] Gamepad listener ready for {self.board_type} ({joystick_count} gamepads)")
                        logger.info("Gamepad detection started for board type %s (%d gamepads)", self.board_type, joystick_count)
                    else:
                        print(f"[InputDetector] Gamepad initialization timed out, but continuing")
                        logger.warning("Gamepad initialization timeout for board type %s", self.board_type)
            else:
                print("[InputDetector] pygame not installed - gamepad detection disabled")

    def stop_listening(self) -> None:
        """Stop listening for keyboard and gamepad events."""
        with self._listener_lock:
            # Stop keyboard listener
            if self._listener is not None:
                self._listener.stop()
                self._listener = None
                logger.info("Keyboard detection stopped.")
            
            # Stop gamepad listener
            if self._gamepad_thread is not None and self._gamepad_thread.is_alive():
                self._gamepad_stop_event.set()
                self._gamepad_thread.join(timeout=1.0)
                self._gamepad_thread = None
                logger.info("Gamepad detection stopped.")

    def register_handler(self, handler: Callable[[InputEvent], None]) -> None:
        """Register a callback to be invoked when an input event is detected."""
        self._handlers.add(handler)

    def unregister_handler(self, handler: Callable[[InputEvent], None]) -> None:
        """Remove a previously registered callback handler."""
        self._handlers.discard(handler)

    def set_learn_mode(self, enabled: bool) -> None:
        """Enable or disable learn mode (captures all keys, not just mapped ones)."""
        self._learn_mode = enabled
        logger.info("Learn mode %s", "enabled" if enabled else "disabled")

    def register_raw_handler(self, handler: Callable[[str], None]) -> None:
        """Register a callback for raw key codes (used in learn mode)."""
        self._raw_handlers.add(handler)

    def unregister_raw_handler(self, handler: Callable[[str], None]) -> None:
        """Remove a raw key handler."""
        self._raw_handlers.discard(handler)

    def on_input_detected(
        self,
        keycode: str,
        identity_bindings: Optional[Dict[str, int]] = None,
    ) -> InputEvent:
        """Convert a keycode into an InputEvent and notify observers.
        
        Args:
            keycode: The detected keycode string.
            identity_bindings: Optional map of source_id -> player number for calibrated identity.
        """
        lookup_name = self._canonical_name_from_display(keycode)
        pin = self._keycode_to_pin.get(lookup_name)
        if pin is None:
            raise KeyError(f"Keycode '{lookup_name}' not mapped for board {self.board_type}")

        # Use identity binding if available, otherwise fall back to pin-based inference
        player = resolve_player_with_identity(pin, self.board_type, identity_bindings)
        _, control_key, control_type = _infer_control_from_pin(pin)
        
        event = InputEvent(
            timestamp=time.time(),
            keycode=keycode,
            pin=pin,
            control_key=control_key,
            player=player,
            control_type=control_type,
            source_id=self.board_type,
        )
        self._emit_event(event)
        return event

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _gamepad_listener_loop(self) -> None:
        """Background thread that polls gamepad/XInput events using pygame."""
        if pygame is None:
            return
        
        print(f"[InputDetector] Gamepad listener thread started (pygame)")
        
        # Initialize all joysticks
        joysticks = []
        for i in range(pygame.joystick.get_count()):
            try:
                js = pygame.joystick.Joystick(i)
                js.init()
                joysticks.append(js)
                print(f"[InputDetector] Initialized joystick {i}: {js.get_name()}")
            except Exception as e:
                print(f"[InputDetector] Failed to init joystick {i}: {e}")
        
        # Track previous button/axis/hat states to detect changes
        prev_buttons = {i: [False] * js.get_numbuttons() for i, js in enumerate(joysticks)}
        prev_axes = {i: [0.0] * js.get_numaxes() for i, js in enumerate(joysticks)}
        prev_hats = {i: [(0, 0)] * max(1, js.get_numhats()) for i, js in enumerate(joysticks)}
        AXIS_THRESHOLD = 0.5  # Threshold for axis to count as pressed
        
        # Signal that initialization is complete - fixes "first input lost" bug
        if hasattr(self, '_gamepad_ready_event') and self._gamepad_ready_event:
            self._gamepad_ready_event.set()
            print(f"[InputDetector] Gamepad initialization complete - ready to capture inputs")
        
        while not self._gamepad_stop_event.is_set():
            try:
                # Process pygame events (required for joystick state updates)
                pygame.event.pump()
                
                for js_idx, js in enumerate(joysticks):
                    # Check buttons
                    for btn_idx in range(js.get_numbuttons()):
                        pressed = js.get_button(btn_idx)
                        was_pressed = prev_buttons[js_idx][btn_idx]
                        
                        if pressed and not was_pressed:
                            # Button just pressed
                            display_code = f"BTN_{btn_idx}_JS{js_idx}"
                            print(f"[InputDetector] Gamepad button: {display_code}")
                            self._handle_gamepad_input(display_code)
                        
                        prev_buttons[js_idx][btn_idx] = pressed
                    
                    # Check axes (for joystick directions)
                    # Note: Xbox triggers (axes 4 & 5) rest at -1.0, so we detect CHANGES
                    for axis_idx in range(js.get_numaxes()):
                        value = js.get_axis(axis_idx)
                        prev_value = prev_axes[js_idx][axis_idx]
                        
                        # Skip if this axis hasn't changed significantly
                        axis_delta = abs(value - prev_value)
                        if axis_delta < 0.3:
                            prev_axes[js_idx][axis_idx] = value
                            continue
                        
                        # Detect meaningful axis movement (joystick pushed to a direction)
                        # For regular axes (0-3): detect movement from center
                        # For triggers (4-5): detect movement from rest position (-1.0)
                        is_trigger = axis_idx >= 4
                        
                        if is_trigger:
                            # Triggers: rest at -1.0, pressed moves toward +1.0
                            if value > -0.5 and prev_value <= -0.5:
                                display_code = f"TRIGGER_{axis_idx - 4}_JS{js_idx}"
                                print(f"[InputDetector] Gamepad trigger: {display_code}")
                                self._handle_gamepad_input(display_code)
                        else:
                            # Joystick axes: detect significant movement from center
                            if abs(value) > AXIS_THRESHOLD and abs(prev_value) <= AXIS_THRESHOLD:
                                direction = "+" if value > 0 else "-"
                                display_code = f"AXIS_{axis_idx}{direction}_JS{js_idx}"
                                print(f"[InputDetector] Gamepad axis: {display_code}")
                                self._handle_gamepad_input(display_code)
                        
                        prev_axes[js_idx][axis_idx] = value
                    
                    # Check HATs (D-pad) - critical for arcade encoder D-pads!
                    for hat_idx in range(js.get_numhats()):
                        hat = js.get_hat(hat_idx)
                        prev_hat = prev_hats[js_idx][hat_idx] if hat_idx < len(prev_hats[js_idx]) else (0, 0)
                        
                        if hat != prev_hat:
                            # Hat state changed - decode direction
                            x, y = hat
                            display_code = None
                            
                            if y == 1:
                                display_code = f"DPAD_UP_JS{js_idx}"
                            elif y == -1:
                                display_code = f"DPAD_DOWN_JS{js_idx}"
                            elif x == -1:
                                display_code = f"DPAD_LEFT_JS{js_idx}"
                            elif x == 1:
                                display_code = f"DPAD_RIGHT_JS{js_idx}"
                            # Note: (0, 0) means released - we don't emit that
                            
                            if display_code:
                                print(f"[InputDetector] Gamepad HAT/D-pad: {display_code}")
                                self._handle_gamepad_input(display_code)
                            
                            # Update state
                            if hat_idx < len(prev_hats[js_idx]):
                                prev_hats[js_idx][hat_idx] = hat
                
                time.sleep(0.01)  # 100Hz polling rate
                
            except Exception as e:
                logger.debug("Gamepad poll error: %s", e)
                time.sleep(0.1)
        
        print(f"[InputDetector] Gamepad listener thread stopped")
    
    def _handle_gamepad_input(self, display_code: str) -> None:
        """Handle a captured gamepad input."""
        # In learn mode, emit to raw handlers
        if self._learn_mode:
            print(f"[InputDetector] Learn mode captured gamepad: {display_code}")
            logger.info("Learn mode captured gamepad: %s", display_code)

            # Record mode (this is XInput)
            if self._encoder_state_manager:
                self._encoder_state_manager.record_input("xinput")

            for handler in list(self._raw_handlers):
                try:
                    handler(display_code)
                except Exception:
                    logger.exception("Raw handler raised an exception")
            return  # Don't process through normal mapping in learn mode

        # Normal mode: look up gamepad input in mapping and emit event
        lookup_name = self._canonical_name_from_display(display_code)
        pin = self._keycode_to_pin.get(lookup_name)
        if pin is None:
            logger.debug("Gamepad input %s (lookup=%s) not mapped; ignoring.", display_code, lookup_name)
            return

        try:
            self.on_input_detected(display_code)
        except Exception:
            logger.exception("Failed to process gamepad event %s", display_code)

    def _emit_event(self, event: InputEvent) -> None:
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:  # pragma: no cover - handler failures should not stop detection
                logger.exception("Input handler %r raised an exception", handler)

    def _handle_key_press(self, key: "keyboard.Key | keyboard.KeyCode") -> None:
        print(f"[InputDetector] Raw key event: {key}")  # DEBUG
        try:
            display_code, lookup_name = self._normalize_key_event(key)
        except ValueError:
            return

        # In learn mode, emit raw key code to all raw handlers
        if self._learn_mode:
            print(f"[InputDetector] Learn mode captured: {display_code}")  # DEBUG
            logger.info("Learn mode captured key: %s", display_code)
            
            # Track mode for drift detection
            detected_mode = detect_input_mode(display_code)
            if self._encoder_state_manager:
                drift_info = self._encoder_state_manager.record_input(detected_mode)
                if drift_info.get("needs_recalibration"):
                    logger.warning(
                        "Mode drift detected! Baseline=%s, Current=%s", 
                        drift_info.get("baseline_mode"),
                        drift_info.get("detected_mode")
                    )
            
            for handler in list(self._raw_handlers):
                try:
                    handler(display_code)
                except Exception:
                    logger.exception("Raw handler %r raised an exception", handler)
            return  # Don't process through normal mapping in learn mode

        pin = self._keycode_to_pin.get(lookup_name)
        if pin is None:
            logger.debug("Key %s (lookup=%s) not mapped; ignoring.", display_code, lookup_name)
            return

        try:
            self.on_input_detected(display_code)
        except Exception:
            logger.exception("Failed to process key event %s", display_code)

    def _load_mapping(self) -> Dict[str, int]:
        mapping_path = _MAPPING_DIR / f"{self.board_type}.json"
        if not mapping_path.exists():
            logger.warning(
                "Board mapping for '%s' not found; falling back to generic mapping.",
                self.board_type,
            )
            mapping_path = _MAPPING_DIR / "generic.json"

        try:
            with open(mapping_path, "r", encoding="utf-8") as handle:
                data = json.load(handle) or {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load board mapping %s: %s", mapping_path, exc)
            data = {}

        normalized = {}
        for key, value in data.items():
            try:
                normalized[self._canonicalize_name(key)] = int(value)
            except (ValueError, TypeError):
                logger.debug("Skipping non-integer mapping entry: %s=%s", key, value)
        logger.info(
            "Loaded %d key mappings for board '%s' from %s",
            len(normalized),
            self.board_type,
            mapping_path,
        )
        return normalized

    def _normalize_key_event(
        self,
        key: "keyboard.Key | keyboard.KeyCode",
    ) -> Tuple[str, str]:
        """Return display code and lookup name from a pynput key event."""
        raw_name: Optional[str] = None

        if keyboard and isinstance(key, keyboard.KeyCode):
            raw_name = key.char

        if not raw_name:
            try:
                raw_name = key.name  # type: ignore[attr-defined]
            except AttributeError:
                raw_name = str(key)

        if not raw_name:
            raise ValueError("Unable to determine key name")

        cleaned = raw_name.replace("Key.", "").strip().lower()
        canonical_name = self._canonicalize_name(cleaned)
        display_code = f"KEY_{canonical_name.upper().replace(' ', '_')}"
        return display_code, canonical_name

    def _canonicalize_name(self, name: str) -> str:
        name = name.lower()
        name = name.replace(" ", "_")
        if name.startswith("key_"):
            name = name[4:]
        return _KEY_ALIAS_MAP.get(name, name)

    def _canonical_name_from_display(self, keycode: str) -> str:
        token = keycode.upper().replace("KEY_", "")
        token = token.lower()
        return self._canonicalize_name(token)

def resolve_player_with_identity(
    pin: int,
    source_id: str,
    identity_bindings: Optional[Dict[str, int]] = None,
) -> int:
    """Return logical player number, using identity bindings if available.
    
    Args:
        pin: The detected pin number.
        source_id: Board type or device identifier.
        identity_bindings: Optional map of source_id -> player number.
    
    Returns:
        Player number (1-4), using calibrated identity if bound, else pin-based.
    """
    if identity_bindings and source_id in identity_bindings:
        return identity_bindings[source_id]
    # Fallback to existing pin-based inference
    player, _, _ = _infer_control_from_pin(pin)
    return player


def _infer_control_from_pin(pin: int) -> Tuple[int, str, str]:
    """Derive player/control metadata from a mapped pin number."""
    if pin <= 0:
        return 0, "unknown", "unknown"

    player_index = (pin - 1) // 14
    if player_index < 0 or player_index > 3:
        return 0, "unknown", "unknown"

    player = player_index + 1
    slot = ((pin - 1) % 14) + 1

    if slot == 1:
        return player, f"p{player}.up", "joystick"
    if slot == 2:
        return player, f"p{player}.down", "joystick"
    if slot == 3:
        return player, f"p{player}.left", "joystick"
    if slot == 4:
        return player, f"p{player}.right", "joystick"
    if 5 <= slot <= 12:
        button_num = slot - 4
        return player, f"p{player}.button{button_num}", "button"
    if slot == 13:
        return player, f"p{player}.coin", "coin"
    if slot == 14:
        return player, f"p{player}.start", "start"

    return player, "unknown", "unknown"

