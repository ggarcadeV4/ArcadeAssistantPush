"""LED-Wiz DLL wrapper using ctypes.

⚠️ DEPRECATED - Use LEDBlinky CLI instead! ⚠️

This module was an attempt to directly call the LEDWiz.dll using ctypes.
However, we discovered that the DLL requires GUI context or special 
initialization that console applications cannot provide.

NEW APPROACH (2026-01):
    Use LEDBlinky.exe command-line interface via subprocess:
    
    import subprocess
    subprocess.run(["C:\\LEDBlinky\\LEDBlinky.exe", "14", "1,48"])
    
    This works because:
    1. LEDBlinky.exe handles the DLL initialization properly
    2. Command 14 = Set Port, format: port,intensity (0-48)
    
See: implementation_plan.md for full integration details.

OLD DOCUMENTATION (for reference):
The DLL provides:
- LWZ_REGISTER: Register with the DLL (required before use)
- LWZ_SBA: Set Bank Address (turn outputs ON/OFF)
- LWZ_PBA: Profile Brightness Address (set brightness levels)
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger("led_engine.ledwiz_dll")


class LEDWizDLL:
    """Wrapper for the official LEDWiz.dll."""
    
    CHANNEL_COUNT = 32
    MAX_BRIGHTNESS = 49  # LED-Wiz uses 1-49, where 49 is full on
    
    def __init__(self, device_id: int = 1):
        """Initialize the wrapper.
        
        Args:
            device_id: LED-Wiz device number (1-16). Most setups use 1.
        """
        self.device_id = device_id
        self._dll: Optional[ctypes.CDLL] = None
        self._registered = False
        
    def load(self) -> bool:
        """Load the LEDWiz.dll and register with it.
        
        Returns:
            True if loaded successfully, False otherwise.
        """
        # Try multiple possible locations for the DLL
        # Note: We need the 64-bit DLL (ledwiz64.dll) for 64-bit Python
        search_paths = [
            Path("C:/LEDBlinky/LWCloneU2/ledwiz64.dll"),  # 64-bit version (preferred)
            Path("C:/LEDBlinky/LWCloneU2/ledwiz.dll"),    # 32-bit version from LWCloneU2
            Path("LEDWiz64.dll"),
            Path("ledwiz64.dll"),
            Path("LEDWiz.dll"),
            Path("ledwiz.dll"),
            Path("C:/LEDBlinky/LEDWiz64.dll"),
            Path("C:/LEDBlinky/LEDWiz.dll"),
            Path("C:/LEDBlinky/ledwiz.dll"),
            Path(os.environ.get("LEDBLINKY_PATH", "")) / "ledwiz64.dll",
        ]
        
        for dll_path in search_paths:
            if dll_path.exists():
                try:
                    # LWCloneU2 uses cdecl calling convention, not stdcall!
                    self._dll = ctypes.CDLL(str(dll_path))
                    logger.info(f"Loaded LEDWiz DLL (cdecl) from: {dll_path}")
                    break
                except OSError as e:
                    logger.debug(f"Failed to load {dll_path}: {e}")
                    continue
        
        if self._dll is None:
            logger.error("Could not find or load LEDWiz.dll")
            return False
        
        # Set up function signatures
        try:
            # LWZ_REGISTER(hwnd, callback) - returns device count
            self._dll.LWZ_REGISTER.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self._dll.LWZ_REGISTER.restype = ctypes.c_int
            
            # LWZ_SBA(id, bank0, bank1, bank2, bank3, speed, unused1, unused2)
            self._dll.LWZ_SBA.argtypes = [
                ctypes.c_int,  # id
                ctypes.c_int,  # bank0 (outputs 1-8)
                ctypes.c_int,  # bank1 (outputs 9-16)
                ctypes.c_int,  # bank2 (outputs 17-24)
                ctypes.c_int,  # bank3 (outputs 25-32)
                ctypes.c_int,  # globalPulseSpeed (1-7)
                ctypes.c_int,  # unused
                ctypes.c_int,  # unused
            ]
            self._dll.LWZ_SBA.restype = None
            
            # LWZ_PBA(id, brightness_array)
            self._dll.LWZ_PBA.argtypes = [
                ctypes.c_int,  # id
                ctypes.POINTER(ctypes.c_ubyte),  # brightness[32]
            ]
            self._dll.LWZ_PBA.restype = None
            
        except AttributeError as e:
            logger.error(f"DLL missing required functions: {e}")
            self._dll = None
            return False
        
        # Register with the DLL
        try:
            device_count = self._dll.LWZ_REGISTER(None, None)
            self._registered = True
            logger.info(f"Registered with LEDWiz.dll, detected {device_count} device(s)")
            return True
        except Exception as e:
            logger.error(f"Failed to register with DLL: {e}")
            return False
    
    def is_loaded(self) -> bool:
        """Check if DLL is loaded and registered."""
        return self._dll is not None and self._registered
    
    def sba(self, bank0: int, bank1: int, bank2: int, bank3: int, speed: int = 2) -> None:
        """Send SBA command (Set Bank Address - controls ON/OFF state).
        
        Args:
            bank0-3: Bitmasks for outputs 1-8, 9-16, 17-24, 25-32
            speed: Global pulse speed (1-7, default 2)
        """
        if not self.is_loaded():
            logger.warning("DLL not loaded, skipping SBA command")
            return
        
        self._dll.LWZ_SBA(self.device_id, bank0, bank1, bank2, bank3, speed, 0, 0)
        logger.debug(f"SBA: banks=[{bank0},{bank1},{bank2},{bank3}] speed={speed}")
    
    def pba(self, brightness: Sequence[int]) -> None:
        """Send PBA command (Profile Brightness Address - sets brightness levels).
        
        Args:
            brightness: Array of 32 brightness values (1-49)
        """
        if not self.is_loaded():
            logger.warning("DLL not loaded, skipping PBA command")
            return
        
        # Create ctypes array
        brightness_list = list(brightness)[:self.CHANNEL_COUNT]
        brightness_list.extend([0] * (self.CHANNEL_COUNT - len(brightness_list)))
        
        # Clamp values to valid range
        brightness_list = [max(0, min(self.MAX_BRIGHTNESS, v)) for v in brightness_list]
        
        arr = (ctypes.c_ubyte * self.CHANNEL_COUNT)(*brightness_list)
        self._dll.LWZ_PBA(self.device_id, arr)
        logger.debug(f"PBA: first 8 = {brightness_list[:8]}")
    
    def all_on(self, brightness: int = 49) -> None:
        """Turn all 32 outputs ON at specified brightness.
        
        Args:
            brightness: Brightness level (1-49, default 49 = max)
        """
        # Turn all outputs ON
        self.sba(255, 255, 255, 255, 2)
        
        # Set all to specified brightness
        brightness_arr = [brightness] * self.CHANNEL_COUNT
        self.pba(brightness_arr)
        logger.info("All outputs ON at brightness %d", brightness)
    
    def all_off(self) -> None:
        """Turn all 32 outputs OFF."""
        self.sba(0, 0, 0, 0, 2)
        logger.info("All outputs OFF")
    
    def channel_on(self, channel: int, brightness: int = 49) -> None:
        """Turn a single channel ON.
        
        Args:
            channel: Channel number (0-31)
            brightness: Brightness level (1-49)
        """
        if channel < 0 or channel >= self.CHANNEL_COUNT:
            logger.warning(f"Channel {channel} out of range")
            return
        
        # Calculate bank bitmasks
        bank0 = bank1 = bank2 = bank3 = 0
        if channel < 8:
            bank0 = 1 << channel
        elif channel < 16:
            bank1 = 1 << (channel - 8)
        elif channel < 24:
            bank2 = 1 << (channel - 16)
        else:
            bank3 = 1 << (channel - 24)
        
        # Turn on the channel
        self.sba(bank0, bank1, bank2, bank3, 2)
        
        # Set brightness for that channel
        brightness_arr = [0] * self.CHANNEL_COUNT
        brightness_arr[channel] = brightness
        self.pba(brightness_arr)
        logger.info(f"Channel {channel} ON at brightness {brightness}")
    
    def channel_off(self, channel: int) -> None:
        """Turn a single channel OFF.
        
        Args:
            channel: Channel number (0-31)
        """
        # Just turn all off (simplest approach for single channel)
        self.sba(0, 0, 0, 0, 2)
        logger.info(f"Channel {channel} OFF")
    
    def set_channels(self, frame: Sequence[int]) -> None:
        """Set all channels to specified brightness levels.
        
        This is the main method used by the LED engine.
        
        Args:
            frame: Array of 32 brightness values (0-48)
        """
        # Build SBA bitmasks (which outputs are ON)
        bank0 = bank1 = bank2 = bank3 = 0
        for i, val in enumerate(frame[:32]):
            if val > 0:
                if i < 8:
                    bank0 |= (1 << i)
                elif i < 16:
                    bank1 |= (1 << (i - 8))
                elif i < 24:
                    bank2 |= (1 << (i - 16))
                else:
                    bank3 |= (1 << (i - 24))
        
        # Turn on the appropriate outputs
        self.sba(bank0, bank1, bank2, bank3, 2)
        
        # Set brightness levels (convert 0-48 to 1-49 for non-zero values)
        brightness_arr = []
        for v in frame[:32]:
            if v > 0:
                brightness_arr.append(min(49, max(1, v)))
            else:
                brightness_arr.append(0)
        brightness_arr.extend([0] * (self.CHANNEL_COUNT - len(brightness_arr)))
        
        self.pba(brightness_arr)


# Global singleton instance
_dll_instance: Optional[LEDWizDLL] = None


def get_ledwiz_dll() -> LEDWizDLL:
    """Get the global LEDWiz DLL wrapper instance."""
    global _dll_instance
    if _dll_instance is None:
        _dll_instance = LEDWizDLL()
        _dll_instance.load()
    return _dll_instance


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    dll = LEDWizDLL()
    if dll.load():
        print("DLL loaded successfully!")
        print("Testing all_on...")
        dll.all_on()
        import time
        time.sleep(2)
        print("Testing all_off...")
        dll.all_off()
    else:
        print("Failed to load DLL")
