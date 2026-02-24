"""
LED Blinky Service - Hardware Control via LEDBlinky.exe CLI

This service wraps the LEDBlinky.exe command-line interface for LED control.
All hardware I/O goes through this service layer to avoid blocking the event loop.

Architecture:
- Uses deterministic A: drive paths via Paths.Tools.LEDBlinky
- Runs subprocess calls asynchronously via asyncio.create_subprocess_exec
- Sets cwd to LEDBlinky folder so it finds its config files
- Provides debounced "Game Selected" to prevent process spam during scrolling

CLI Reference (LEDBlinky.exe):
- Command 1: FE Start -> LEDBlinky.exe 1
- Command 2: FE Quit -> LEDBlinky.exe 2
- Command 4: Game Stop -> LEDBlinky.exe 4
- Command 5: Screensaver/All Off -> LEDBlinky.exe 5
- Command 14: Set Port -> LEDBlinky.exe 14 port,intensity
- Command 15: Set Game (light controls only) -> LEDBlinky.exe 15 rom [emulator]
- Game Start: LEDBlinky.exe <rom> [emulator]
- Animation: LEDBlinky.exe animation.lwax
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from backend.constants.paths import Paths

logger = logging.getLogger(__name__)


class BlinkyProcessManager:
    """
    Singleton manager for LEDBlinky.exe process control with debouncing.
    
    Handles the "Blinky Bridge" pattern:
    - Accepts events from WebSocket/API endpoints
    - Throttles rapid "Game Selected" events during UI scrolling
    - Fires subprocess calls to LEDBlinky.exe
    """
    
    _instance: Optional['BlinkyProcessManager'] = None
    _lock = threading.Lock()
    
    # Debounce settings
    DEBOUNCE_MS = 250  # 250ms debounce for game selection
    
    def __new__(cls) -> 'BlinkyProcessManager':
        """Singleton pattern - only one manager per process."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the process manager (only runs once due to singleton)."""
        if self._initialized:
            return
        
        self._initialized = True
        self._debounce_task: Optional[asyncio.Task] = None
        self._pending_game: Optional[tuple[str, str]] = None  # (rom, emulator)
        self._current_game: Optional[str] = None
        self._is_running = False
        self._config_migrated = False
        self._config_errors: list[str] = []
        
        # P0: Auto-migrate Settings.ini paths on startup
        self._migrate_settings_ini()
        
        logger.info("[BlinkyProcessManager] Initialized (singleton)")
    
    def _migrate_settings_ini(self) -> None:
        """
        P0 Priority: Migrate Settings.ini paths to current drive root.
        
        LEDBlinky stores absolute paths like Colors_ini=C:\\LEDBlinky\\colors.ini.
        This method reads the INI, detects any path values pointing to a different
        drive or directory, and rewrites them to match Paths.Tools.LEDBlinky.root().
        Creates a backup before modifying.
        """
        settings_path = self.working_directory / "Settings.ini"
        
        if not settings_path.exists():
            logger.warning(f"[BlinkyProcessManager] Settings.ini not found at {settings_path}")
            self._config_errors.append("Settings.ini not found")
            return
        
        try:
            import configparser
            import re
            
            correct_root = str(Paths.Tools.LEDBlinky.root())
            correct_root_bs = correct_root.replace("/", "\\")  # Backslash variant
            correct_root_fs = correct_root.replace("\\", "/")  # Forward-slash variant
            
            content = settings_path.read_text(encoding='utf-8', errors='replace')
            
            # Detect any drive-letter paths that DON'T already point to the correct root
            # Pattern matches C:\...\LEDBlinky, D:\LEDBlinky, etc.
            drive_path_pattern = re.compile(
                r'[A-Za-z]:[/\\](?:[^=\r\n]*[/\\])?LEDBlinky(?=[/\\]|$)',
                re.IGNORECASE
            )
            
            stale_paths = [
                m.group() for m in drive_path_pattern.finditer(content)
                if not m.group().replace("/", "\\").lower().startswith(correct_root_bs.lower())
            ]
            
            if not stale_paths:
                logger.debug("[BlinkyProcessManager] Settings.ini paths already correct")
                self._config_migrated = True
                return
            
            # Create backup before modifying
            backup_path = settings_path.with_suffix('.ini.bak')
            if not backup_path.exists():
                backup_path.write_text(content, encoding='utf-8')
                logger.info(f"[BlinkyProcessManager] Backed up Settings.ini to {backup_path}")
            
            # Replace all stale LEDBlinky root paths with correct root
            new_content = content
            for stale in sorted(set(stale_paths), key=len, reverse=True):
                # Determine if stale path used forward or back slashes
                if "/" in stale:
                    new_content = new_content.replace(stale, correct_root_fs)
                else:
                    new_content = new_content.replace(stale, correct_root_bs)
            
            if new_content != content:
                settings_path.write_text(new_content, encoding='utf-8')
                logger.info(
                    f"[BlinkyProcessManager] Migrated Settings.ini paths to {correct_root} "
                    f"(fixed {len(stale_paths)} stale reference(s))"
                )
                self._config_migrated = True
            else:
                logger.debug("[BlinkyProcessManager] No path changes needed in Settings.ini")
                self._config_migrated = True
                
        except Exception as e:
            error_msg = f"Failed to migrate Settings.ini: {e}"
            logger.error(f"[BlinkyProcessManager] {error_msg}")
            self._config_errors.append(error_msg)
    
    @classmethod
    def get_instance(cls) -> 'BlinkyProcessManager':
        """Get the singleton instance."""
        return cls()
    
    @property
    def executable_path(self) -> Path:
        """Get the deterministic path to LEDBlinky.exe."""
        return Paths.Tools.LEDBlinky.executable()
    
    @property
    def working_directory(self) -> Path:
        """Get the LEDBlinky folder for cwd."""
        return self.executable_path.parent
    
    @property
    def is_available(self) -> bool:
        """Check if LEDBlinky.exe exists."""
        return self.executable_path.exists()
    
    async def _run_cli(
        self, 
        *args: str, 
        timeout: float = 5.0
    ) -> tuple[bool, str]:
        """
        Run LEDBlinky.exe with the given arguments.
        
        Always runs with cwd set to the LEDBlinky folder so it finds configs.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        exe_path = self.executable_path
        cwd = self.working_directory
        
        if not exe_path.exists():
            error_msg = f"LEDBlinky.exe not found at {exe_path}"
            logger.error(f"[BlinkyProcessManager] {error_msg}")
            return False, error_msg
        
        cmd = [str(exe_path), *args]
        logger.debug(f"[BlinkyProcessManager] Running: {' '.join(cmd)} (cwd={cwd})")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd)  # CRITICAL: Set working directory
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            if process.returncode == 0:
                logger.debug(f"[BlinkyProcessManager] Command succeeded")
                return True, "OK"
            else:
                error = stderr.decode() if stderr else f"Exit code {process.returncode}"
                logger.warning(f"[BlinkyProcessManager] Command failed: {error}")
                return False, error
                
        except asyncio.TimeoutError:
            logger.error(f"[BlinkyProcessManager] Command timed out after {timeout}s")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"[BlinkyProcessManager] Command error: {e}")
            return False, str(e)
    
    # =========================================================================
    # SYSTEM EVENTS (No Debounce)
    # =========================================================================
    
    async def system_start(self) -> Dict[str, Any]:
        """
        System/Frontend Start event (Command 1).
        Called when Arcade Assistant loads.
        """
        logger.info("[BlinkyProcessManager] System Start (FE mode)")
        success, message = await self._run_cli("1")
        self._is_running = True
        return {"success": success, "event": "system_start", "message": message}
    
    async def system_quit(self) -> Dict[str, Any]:
        """
        System/Frontend Quit event (Command 2).
        Called when Arcade Assistant exits.
        """
        logger.info("[BlinkyProcessManager] System Quit")
        success, message = await self._run_cli("2")
        self._is_running = False
        return {"success": success, "event": "system_quit", "message": message}
    
    async def game_stop(self) -> Dict[str, Any]:
        """
        Game Stop event (Command 4).
        Called when returning from a game to the frontend.
        """
        logger.info("[BlinkyProcessManager] Game Stop")
        success, message = await self._run_cli("4")
        self._current_game = None
        return {"success": success, "event": "game_stop", "message": message}
    
    async def all_off(self) -> Dict[str, Any]:
        """
        Screensaver/All LEDs Off (Command 5).
        """
        logger.info("[BlinkyProcessManager] All Off")
        success, message = await self._run_cli("5")
        return {"success": success, "event": "all_off", "message": message}
    
    # =========================================================================
    # GAME SELECTION (Debounced)
    # =========================================================================
    
    async def game_selected(
        self, 
        rom: str, 
        emulator: str = "MAME"
    ) -> Dict[str, Any]:
        """
        Game Selected event - DEBOUNCED.
        
        Called when user scrolls/hovers over a game in the UI.
        Uses a 250ms debounce timer to avoid process spam.
        
        Flow:
        1. User scrolls to Game A -> Timer starts
        2. User scrolls to Game B (100ms later) -> Cancel timer, restart
        3. User pauses on Game B -> Timer expires -> Fire CLI command
        """
        logger.debug(f"[BlinkyProcessManager] Game selected: {rom} ({emulator}) - debouncing")
        
        # Store the pending game
        self._pending_game = (rom, emulator)
        
        # Cancel any existing debounce timer
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            try:
                await self._debounce_task
            except asyncio.CancelledError:
                pass
        
        # Start new debounce timer
        self._debounce_task = asyncio.create_task(
            self._debounced_game_select()
        )
        
        return {
            "success": True,
            "event": "game_selected",
            "rom": rom,
            "emulator": emulator,
            "status": "debouncing",
            "debounce_ms": self.DEBOUNCE_MS
        }
    
    async def _debounced_game_select(self):
        """Internal: Execute the game select after debounce period."""
        try:
            await asyncio.sleep(self.DEBOUNCE_MS / 1000.0)
            
            if self._pending_game:
                rom, emulator = self._pending_game
                logger.info(f"[BlinkyProcessManager] Debounce fired: {rom} ({emulator})")
                
                # Command 15: Set Game (light controls only, no speech/animation)
                success, message = await self._run_cli("15", rom, emulator)
                
                if success:
                    self._current_game = rom
                    
        except asyncio.CancelledError:
            logger.debug("[BlinkyProcessManager] Debounce cancelled (user still scrolling)")
    
    # =========================================================================
    # GAME LAUNCH (Immediate, No Debounce)
    # =========================================================================
    
    async def game_launch(
        self, 
        rom: str, 
        emulator: str = "MAME"
    ) -> Dict[str, Any]:
        """
        Game Launch event - IMMEDIATE (no debounce).
        
        Called when a game is actually being launched.
        Triggers full LEDBlinky game start (lighting + optional speech/animation).
        """
        logger.info(f"[BlinkyProcessManager] Game Launch: {rom} ({emulator})")
        
        # Cancel any pending debounce
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            self._pending_game = None
        
        # Fire immediately with rom and emulator
        success, message = await self._run_cli(rom, emulator)
        
        if success:
            self._current_game = rom
        
        return {
            "success": success,
            "event": "game_launch",
            "rom": rom,
            "emulator": emulator,
            "message": message
        }
    
    # =========================================================================
    # ANIMATIONS
    # =========================================================================
    
    async def play_animation(
        self, 
        animation_name: str,
        single_loop: bool = False
    ) -> Dict[str, Any]:
        """
        Play an LED animation (.lwax file).
        """
        logger.info(f"[BlinkyProcessManager] Play animation: {animation_name}")
        
        args = [animation_name]
        if single_loop:
            args.append("S")  # SingleLoop option
        
        success, message = await self._run_cli(*args)
        return {
            "success": success,
            "event": "animation_play",
            "animation": animation_name,
            "message": message
        }
    
    async def stop_animation(self) -> Dict[str, Any]:
        """
        Stop the current animation (Command 11).
        """
        logger.info("[BlinkyProcessManager] Stop animation")
        success, message = await self._run_cli("11")
        return {"success": success, "event": "animation_stop", "message": message}
    
    # =========================================================================
    # DIRECT PORT CONTROL
    # =========================================================================
    
    async def set_port(
        self, 
        port: int, 
        intensity: int = 48
    ) -> Dict[str, Any]:
        """
        Set a specific LED port intensity (Command 14).
        
        Args:
            port: Port number (1-based)
            intensity: 0-48 (0=off, 48=max)
        """
        intensity = max(0, min(48, intensity))
        logger.debug(f"[BlinkyProcessManager] Set port {port} -> {intensity}")
        
        success, message = await self._run_cli("14", f"{port},{intensity}")
        return {
            "success": success,
            "event": "set_port",
            "port": port,
            "intensity": intensity,
            "message": message
        }
    
    async def flash_port(
        self,
        port: int,
        intensity: int = 48,
        duration_ms: int = 500
    ) -> Dict[str, Any]:
        """
        Flash a port briefly then turn it off.
        """
        result = await self.set_port(port, intensity)
        
        if result["success"]:
            async def _auto_off():
                await asyncio.sleep(duration_ms / 1000.0)
                await self.set_port(port, 0)
            
            asyncio.create_task(_auto_off())
            result["duration_ms"] = duration_ms
        
        return result
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current manager status including config migration info."""
        return {
            "available": self.is_available,
            "executable_path": str(self.executable_path),
            "working_directory": str(self.working_directory),
            "is_running": self._is_running,
            "current_game": self._current_game,
            "has_pending_selection": self._pending_game is not None,
            "debounce_ms": self.DEBOUNCE_MS,
            "config_migrated": self._config_migrated,
            "config_errors": self._config_errors
        }


# =============================================================================
# LEGACY COMPATIBILITY: BlinkyService
# =============================================================================
# Keep the original class name for backwards compatibility with existing code

class BlinkyService:
    """
    Legacy wrapper for backwards compatibility.
    Delegates to BlinkyProcessManager singleton.
    """
    
    MIN_INTENSITY = 0
    MAX_INTENSITY = 48
    
    @classmethod
    def _manager(cls) -> BlinkyProcessManager:
        return BlinkyProcessManager.get_instance()
    
    @classmethod
    def get_executable_path(cls) -> Path:
        return cls._manager().executable_path
    
    @classmethod
    def is_available(cls) -> bool:
        return cls._manager().is_available
    
    @classmethod
    async def flash_port(cls, port: int, intensity: int = 48, duration_ms: int = 500) -> dict:
        return await cls._manager().flash_port(port, intensity, duration_ms)
    
    @classmethod
    async def all_off(cls) -> dict:
        return await cls._manager().all_off()
    
    @classmethod
    async def set_game(cls, game_name: str) -> dict:
        return await cls._manager().game_launch(game_name)
    
    @classmethod
    async def test_all_ports(cls, port_count: int = 32, delay_ms: int = 100) -> dict:
        manager = cls._manager()
        results = []
        
        for port in range(1, port_count + 1):
            result = await manager.flash_port(port, intensity=48, duration_ms=delay_ms)
            results.append(result)
            await asyncio.sleep(delay_ms / 1000.0)
        
        await manager.all_off()
        
        return {
            "success": all(r["success"] for r in results),
            "ports_tested": port_count,
            "results": results
        }
    
    @classmethod
    def get_status(cls) -> dict:
        return cls._manager().get_status()
