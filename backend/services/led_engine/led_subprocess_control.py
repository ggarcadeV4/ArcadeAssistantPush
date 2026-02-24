"""LED Control via Subprocess - Uses external helper for reliable LED control.

Since Python 64-bit + ctypes + ledwiz64.dll isn't working reliably,
this module uses subprocess to call external tools that work.

Options:
1. Call SimpleLEDTest.exe via SendMessage (AutoHotKey or similar)
2. Use a small 32-bit Python script 
3. Call LEDBlinky directly
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from backend.constants.paths import Paths

logger = logging.getLogger("led_engine.subprocess_control")

# Lazy resolution — Paths.Tools.LEDBlinky.root() requires AA_DRIVE_ROOT,
# which may not be set at import time, so we defer until first use.
_cached_blinky_root: Optional[Path] = None


def _blinky_root() -> Path:
    """Resolve and cache the LEDBlinky root path on first call."""
    global _cached_blinky_root
    if _cached_blinky_root is None:
        _cached_blinky_root = Paths.Tools.LEDBlinky.root()
    return _cached_blinky_root


class LEDSubprocessControl:
    """Control LEDs via subprocess calls to 32-bit helper."""
    
    CHANNEL_COUNT = 32
    
    def __init__(self):
        self.device_id = "fafa:00f0"
        self.channel_count = self.CHANNEL_COUNT
        self._helper_path: Optional[Path] = None
        
    def _get_helper_script(self) -> str:
        """Generate a Python 32-bit script that controls the LED."""
        blinky_root = str(_blinky_root()).replace('\\', '\\\\')
        return f'''
import ctypes
import sys
import os

os.chdir(r"{blinky_root}")
dll = ctypes.CDLL("ledwiz.dll")
dll.LWZ_REGISTER(None, None)

command = sys.argv[1] if len(sys.argv) > 1 else "all_on"
channel = int(sys.argv[2]) if len(sys.argv) > 2 else 0

if command == "all_on":
    dll.LWZ_SBA(1, 255, 255, 255, 255, 2, 0, 0)
    brightness = (ctypes.c_ubyte * 32)(*[49]*32)
    dll.LWZ_PBA(1, brightness)
elif command == "all_off":
    dll.LWZ_SBA(1, 0, 0, 0, 0, 2, 0, 0)
elif command == "channel_on":
    bank = [0, 0, 0, 0]
    bank_idx = channel // 8
    bit_idx = channel % 8
    bank[bank_idx] = 1 << bit_idx
    dll.LWZ_SBA(1, bank[0], bank[1], bank[2], bank[3], 2, 0, 0)
    brightness = (ctypes.c_ubyte * 32)(*[0]*32)
    brightness[channel] = 49
    dll.LWZ_PBA(1, brightness)
elif command == "channel_off":
    dll.LWZ_SBA(1, 0, 0, 0, 0, 2, 0, 0)
    
print(f"Done: {{command}}")
'''
    
    async def all_on(self) -> bool:
        """Turn all LEDs on."""
        return await self._call_helper("all_on")
    
    async def all_off(self) -> bool:
        """Turn all LEDs off."""
        return await self._call_helper("all_off")
    
    async def channel_on(self, channel: int, brightness: int = 49) -> bool:
        """Turn a single channel on."""
        return await self._call_helper("channel_on", channel)
    
    async def channel_off(self, channel: int) -> bool:
        """Turn a single channel off."""
        return await self._call_helper("channel_off", channel)
    
    async def _call_helper(self, command: str, channel: int = 0) -> bool:
        """Call the LED helper via subprocess."""
        script = self._get_helper_script()
        
        # Write temp script to LEDBlinky directory
        temp_script = _blinky_root() / "led_helper_temp.py"
        temp_script.write_text(script)
        
        try:
            # Try to find 32-bit Python (common locations)
            python32_paths = [
                "C:/Python310-32/python.exe",  # Common 32-bit install
                "C:/Python39-32/python.exe",
                "C:/Python38-32/python.exe",
                "py -3.10-32",  # py launcher
                "py -3-32",
            ]
            
            # For now, use current Python - may work if we're in 32-bit mode
            python_cmd = sys.executable
            
            result = await asyncio.to_thread(
                subprocess.run,
                [python_cmd, str(temp_script), command, str(channel)],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(_blinky_root())
            )
            
            if result.returncode == 0:
                logger.info(f"LED command succeeded: {command} {channel}")
                return True
            else:
                logger.error(f"LED command failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"LED subprocess call failed: {e}")
            return False


# Quick test
if __name__ == "__main__":
    import asyncio
    
    async def test():
        ctrl = LEDSubprocessControl()
        print("Testing all_on...")
        await ctrl.all_on()
        await asyncio.sleep(2)
        print("Testing all_off...")
        await ctrl.all_off()
        
    asyncio.run(test())
