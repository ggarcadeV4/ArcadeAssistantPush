"""
Hotkey Manager Service
Detects global hotkey presses (default: A key) for overlay activation
Requires admin privileges on Windows
"""

import os
import time
import asyncio
import keyboard
from typing import Callable, List, Optional
import logging

logger = logging.getLogger(__name__)


class HotkeyManager:
    """Manages global hotkey detection with suppression and debounce"""

    def __init__(self):
        self.hotkey = os.getenv("HOTKEY_OVERLAY", "F9").lower()
        self.trigger = os.getenv("HOTKEY_TRIGGER", "release").lower()
        # Opt-in method flag; default preserves existing behavior
        # keyevent (default): on_press_key/on_release_key
        # addhotkey: keyboard.add_hotkey (recommended for single-key triggers)
        # dual: register both methods (debounced)
        self.method = os.getenv("HOTKEY_METHOD", "keyevent").lower()
        self.suppress = os.getenv("HOTKEY_SUPPRESS", "false").lower() in {"1", "true", "yes"}
        self.debounce_ms = int(os.getenv("HOTKEY_DEBOUNCE_MS", "250"))
        self.is_active = False
        self.callbacks: List[Callable] = []
        self._last_event_ms = 0
        self._event_loop = None  # Store reference to event loop
        self._hotkey_handle = None  # Handle for add_hotkey (if used)

        logger.info(
            f"HotkeyManager initialized: key={self.hotkey.upper()}, "
            f"trigger={self.trigger}, method={self.method}, suppress={self.suppress}, "
            f"debounce={self.debounce_ms}ms"
        )

    def register_callback(self, callback: Callable):
        """Register async callback for hotkey press."""
        if callback in self.callbacks:
            logger.info(f"Hotkey callback already registered: {callback.__name__}")
            return
        self.callbacks.append(callback)
        logger.info(f"Registered hotkey callback: {callback.__name__}")

    async def start(self):
        """Start listening for hotkey presses."""
        if self.is_active:
            logger.info(f"[Hotkey] Listener already active for {self.hotkey.upper()} - skipping duplicate start")
            return

        try:
            # Store reference to current event loop
            self._event_loop = asyncio.get_running_loop()

            # add_hotkey path (opt-in)
            if self.method in {"addhotkey", "dual"}:
                try:
                    self._hotkey_handle = keyboard.add_hotkey(
                        self.hotkey,
                        lambda: self._on_hotkey_event(None),
                        suppress=self.suppress,
                    )
                    logger.info(
                        f"[Hotkey] add_hotkey registered for {self.hotkey.upper()} (suppress={self.suppress})"
                    )
                except Exception as e:
                    logger.error(f"add_hotkey registration failed: {e}")
                    if self.method == "addhotkey":
                        raise

            # keyevent path (default)
            if self.method in {"keyevent", "dual"}:
                if self.trigger == "release":
                    keyboard.on_release_key(
                        self.hotkey,
                        self._on_hotkey_event,
                        suppress=self.suppress,
                    )
                else:
                    keyboard.on_press_key(
                        self.hotkey,
                        self._on_hotkey_event,
                        suppress=self.suppress,
                    )

            self.is_active = True
            logger.info(
                f"[Hotkey] Listening for {self.hotkey.upper()} key presses "
                f"(trigger={self.trigger}, method={self.method}, suppress={self.suppress})"
            )
        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}")
            logger.error("Make sure backend is running with administrator privileges")
            raise

    def _on_hotkey_event(self, event):
        """Handle hotkey press with debounce"""
        now = int(time.time() * 1000)

        # Debounce check
        if now - self._last_event_ms < self.debounce_ms:
            return

        self._last_event_ms = now

        # Also print directly to stdout to ensure visibility even if logger filters INFO
        try:
            print(f"[Hotkey] {self.hotkey.upper()} pressed — triggering callbacks", flush=True)
        except Exception:
            pass

        logger.info(f"[Hotkey] {self.hotkey.upper()} pressed – triggering callbacks")

        # Execute all callbacks
        for callback in self.callbacks:
            if asyncio.iscoroutinefunction(callback):
                # Schedule async callback in a thread-safe way using stored event loop
                if self._event_loop and self._event_loop.is_running():
                    asyncio.run_coroutine_threadsafe(callback(), self._event_loop)
                else:
                    logger.error("No event loop available to run async callback")
            else:
                callback()

    def stop(self):
        """Stop listening for hotkey presses."""
        if not self.is_active:
            return

        try:
            # Remove add_hotkey handler if present
            if self._hotkey_handle is not None:
                try:
                    keyboard.remove_hotkey(self._hotkey_handle)
                except Exception as e:
                    logger.error(f"Error removing add_hotkey handler: {e}")
                finally:
                    self._hotkey_handle = None

            # Unhook keyevent listener (safe if not registered)
            try:
                keyboard.unhook_key(self.hotkey)
            except Exception:
                pass

            self.is_active = False
            logger.info(f"[Hotkey] Stopped listening for {self.hotkey.upper()}")
        except Exception as e:
            logger.error(f"Error stopping hotkey listener: {e}")


# Global singleton instance
_hotkey_manager: Optional[HotkeyManager] = None


def get_hotkey_manager() -> HotkeyManager:
    """Get or create the global hotkey manager instance"""
    global _hotkey_manager
    if _hotkey_manager is None:
        _hotkey_manager = HotkeyManager()
    return _hotkey_manager
