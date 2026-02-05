"""
LED-Wiz Direct HID Driver using Windows ctypes
Part of: Phase 5 Blinky Gem Pivot

This driver uses Windows setupapi and hid.dll directly via ctypes,
avoiding the need for node-hid or compiled C++ binaries.

Can run as a daemon (--daemon) listening on named pipe, or be imported as a module.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import argparse
import logging
import time
import threading
from typing import List, Dict, Optional, Sequence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [LEDWizDirect] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ledwiz_direct")

# =============================================================================
# Windows API Constants
# =============================================================================

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3

# LED-Wiz VID/PIDs
LEDWIZ_VID = 0xFAFA
LEDWIZ_PID_MIN = 0x00F0  # Unit 1
LEDWIZ_PID_MAX = 0x00FF  # Unit 16

# =============================================================================
# BRIGHTNESS CONFIGURATION
# =============================================================================

# MAX_BRIGHTNESS_MODE: When True, any non-zero brightness value becomes 48 (max)
# This makes LEDs "pop" on camera and ensures maximum visual impact
MAX_BRIGHTNESS_MODE = True
MAX_BRIGHTNESS_VALUE = 48

# =============================================================================
# Windows API Structures
# =============================================================================

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]

class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),  # Variable length
    ]

class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.DWORD),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]

# =============================================================================
# Windows API Functions
# =============================================================================

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# HidD_GetHidGuid
hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetHidGuid.restype = None

# HidD_GetAttributes
hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wintypes.BOOL

# SetupDiGetClassDevs
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD
]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

# SetupDiEnumDeviceInterfaces
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

# SetupDiGetDeviceInterfaceDetailW
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

# SetupDiDestroyDeviceInfoList
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

# CreateFileW
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
]
kernel32.CreateFileW.restype = wintypes.HANDLE

# WriteFile
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
]
kernel32.WriteFile.restype = wintypes.BOOL

# CloseHandle
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

# =============================================================================
# LED-Wiz Board Class
# =============================================================================

class LEDWizBoard:
    """Represents a single LED-Wiz board."""
    
    def __init__(self, path: str, unit_id: int, pid: int):
        self.path = path
        self.unit_id = unit_id  # 1-based
        self.pid = pid
        self.handle: Optional[int] = None
        self._lock = threading.Lock()
        self.channel_count = 32
        self._last_frame = [0] * 32
    
    def open(self) -> bool:
        """Open device handle for writing."""
        if self.handle is not None:
            return True
        
        handle = kernel32.CreateFileW(
            self.path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        
        if handle == INVALID_HANDLE_VALUE:
            logger.error(f"Failed to open device Unit {self.unit_id}: error {ctypes.get_last_error()}")
            return False
        
        self.handle = handle
        logger.info(f"Opened LED-Wiz Unit {self.unit_id} (PID: 0x{self.pid:04X})")
        return True
    
    def close(self):
        """Close device handle."""
        if self.handle is not None:
            kernel32.CloseHandle(self.handle)
            self.handle = None
    
    def write_report(self, report: bytes) -> bool:
        """Write a 9-byte HID report."""
        if self.handle is None:
            if not self.open():
                return False
        
        with self._lock:
            written = wintypes.DWORD(0)
            result = kernel32.WriteFile(
                self.handle,
                report,
                len(report),
                ctypes.byref(written),
                None
            )
            return bool(result)
    
    def send_sba(self, bank0: int, bank1: int, bank2: int, bank3: int, speed: int = 2) -> bool:
        """Send SBA (Set Bank Address) command."""
        report = bytes([0x00, bank0, bank1, bank2, bank3, speed, 0, 0, 0])
        return self.write_report(report)
    
    def send_pba_chunk(self, chunk_idx: int, brightness: List[int]) -> bool:
        """Send PBA (Profile Brightness Address) chunk."""
        marker = 0x40 + chunk_idx
        clamped = [max(0, min(48, int(b))) for b in brightness[:8]]
        
        # Apply MAX_BRIGHTNESS_MODE: any non-zero value becomes max (48)
        if MAX_BRIGHTNESS_MODE:
            clamped = [MAX_BRIGHTNESS_VALUE if b > 0 else 0 for b in clamped]
        
        while len(clamped) < 8:
            clamped.append(0)
        report = bytes([0x00, marker] + clamped)
        return self.write_report(report)
    
    def set_channels(self, frame: Sequence[int]) -> bool:
        """Write a full 32-channel brightness frame."""
        frame_list = list(frame[:32])
        while len(frame_list) < 32:
            frame_list.append(0)
        
        # Build bank bitmasks
        bank0 = bank1 = bank2 = bank3 = 0
        for i, val in enumerate(frame_list):
            if val > 0:
                if i < 8:
                    bank0 |= (1 << i)
                elif i < 16:
                    bank1 |= (1 << (i - 8))
                elif i < 24:
                    bank2 |= (1 << (i - 16))
                else:
                    bank3 |= (1 << (i - 24))
        
        # Send SBA
        if not self.send_sba(bank0, bank1, bank2, bank3):
            return False
        
        # Send 4 PBA chunks
        for chunk_idx in range(4):
            start = chunk_idx * 8
            chunk = frame_list[start:start + 8]
            if not self.send_pba_chunk(chunk_idx, chunk):
                return False
        
        self._last_frame = frame_list
        return True
    
    def all_off(self) -> bool:
        """Turn all LEDs off."""
        return self.send_sba(0, 0, 0, 0, 2)

# =============================================================================
# Discovery Functions
# =============================================================================

def discover_boards() -> List[LEDWizBoard]:
    """Enumerate all connected LED-Wiz boards."""
    boards: List[LEDWizBoard] = []
    
    # Get HID GUID
    hid_guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(hid_guid))
    
    # Get device info set
    device_info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(hid_guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    
    if device_info_set == INVALID_HANDLE_VALUE:
        logger.error("Failed to get device info set")
        return boards
    
    try:
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        
        index = 0
        while setupapi.SetupDiEnumDeviceInterfaces(
            device_info_set
            , None, ctypes.byref(hid_guid), index, ctypes.byref(interface_data)
        ):
            index += 1
            
            # Get required buffer size
            required_size = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                device_info_set, ctypes.byref(interface_data),
                None, 0, ctypes.byref(required_size), None
            )
            
            if required_size.value == 0:
                continue
            
            # Allocate buffer for detail data
            buffer_size = required_size.value
            buffer = ctypes.create_string_buffer(buffer_size)
            detail_data = ctypes.cast(buffer, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
            # Set cbSize for the structure (not the buffer)
            if ctypes.sizeof(ctypes.c_void_p) == 8:
                detail_data.contents.cbSize = 8  # 64-bit
            else:
                detail_data.contents.cbSize = 6  # 32-bit
            
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                device_info_set, ctypes.byref(interface_data),
                buffer, buffer_size, None, None
            ):
                continue
            
            # Extract device path (starts at offset 4)
            path_offset = ctypes.sizeof(wintypes.DWORD)
            path = ctypes.wstring_at(ctypes.addressof(buffer) + path_offset)
            
            # Open device to check VID/PID
            handle = kernel32.CreateFileW(
                path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None
            )
            
            if handle == INVALID_HANDLE_VALUE:
                continue
            
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                
                if hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                    vid = attrs.VendorID
                    pid = attrs.ProductID
                    
                    # Check if it's an LED-Wiz
                    if vid == LEDWIZ_VID and LEDWIZ_PID_MIN <= pid <= LEDWIZ_PID_MAX:
                        unit_id = pid - LEDWIZ_PID_MIN + 1  # 1-16
                        board = LEDWizBoard(path, unit_id, pid)
                        boards.append(board)
                        logger.info(f"Found LED-Wiz Unit {unit_id} (VID:0x{vid:04X} PID:0x{pid:04X})")
            finally:
                kernel32.CloseHandle(handle)
        
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(device_info_set)
    
    boards.sort(key=lambda b: b.unit_id)
    return boards

# =============================================================================
# Named Pipe Daemon Mode
# =============================================================================

PIPE_NAME = r"\\.\pipe\ArcadeLED"

def run_daemon():
    """Run as a named pipe daemon for IPC."""
    logger.info("Starting LED-Wiz Direct Daemon...")
    
    boards = discover_boards()
    if not boards:
        logger.warning("No LED-Wiz boards found initially. Will retry on command.")
    else:
        logger.info(f"Discovered {len(boards)} LED-Wiz board(s)")
        for b in boards:
            b.open()
    
    # Create named pipe server
    while True:
        try:
            # Create the named pipe
            pipe_handle = kernel32.CreateNamedPipeW(
                PIPE_NAME,
                0x00000003,  # PIPE_ACCESS_DUPLEX
                0x00000004 | 0x00000002 | 0x00000000,  # PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT
                255,  # Unlimited instances
                1024, 1024, 0, None
            )
            
            if pipe_handle == INVALID_HANDLE_VALUE:
                logger.error(f"Failed to create named pipe: {ctypes.get_last_error()}")
                time.sleep(5)
                continue
            
            logger.info("Waiting for client connection...")
            
            # Connect to client
            kernel32.ConnectNamedPipe(pipe_handle, None)
            logger.info("Client connected.")
            
            # Read commands
            buffer = ctypes.create_string_buffer(1024)
            bytes_read = wintypes.DWORD(0)
            leftover = ""
            
            while True:
                result = kernel32.ReadFile(
                    pipe_handle, buffer, 1024, ctypes.byref(bytes_read), None
                )
                
                if not result or bytes_read.value == 0:
                    break
                
                data = leftover + buffer.raw[:bytes_read.value].decode('utf-8', errors='ignore')
                leftover = ""
                
                while '\n' in data:
                    line, data = data.split('\n', 1)
                    line = line.strip()
                    if line:
                        handle_command(line, boards)
                
                leftover = data
            
            logger.info("Client disconnected.")
            kernel32.CloseHandle(pipe_handle)
            
        except Exception as e:
            logger.error(f"Daemon error: {e}")
            time.sleep(1)

# Add CreateNamedPipeW
kernel32.CreateNamedPipeW = kernel32.CreateNamedPipeW
kernel32.CreateNamedPipeW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
]
kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL

kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
]
kernel32.ReadFile.restype = wintypes.BOOL

def handle_command(cmd: str, boards: List[LEDWizBoard]):
    """Handle a command from the named pipe."""
    parts = cmd.split()
    if not parts:
        return
    
    action = parts[0].upper()
    
    if action == "SBA" and len(parts) >= 7:
        board_id = int(parts[1])
        b0, b1, b2, b3, speed = map(int, parts[2:7])
        board = next((b for b in boards if b.unit_id == board_id), None)
        if board:
            board.send_sba(b0, b1, b2, b3, speed)
    
    elif action == "PBA_CHUNK" and len(parts) >= 11:
        board_id = int(parts[1])
        chunk = int(parts[2])
        brightness = list(map(int, parts[3:11]))
        board = next((b for b in boards if b.unit_id == board_id), None)
        if board:
            board.send_pba_chunk(chunk, brightness)
    
    elif action == "SET_CHANNELS" and len(parts) >= 34:
        board_id = int(parts[1])
        frame = list(map(int, parts[2:34]))
        board = next((b for b in boards if b.unit_id == board_id), None)
        if board:
            board.set_channels(frame)
    
    elif action == "ALL_OFF":
        for board in boards:
            board.all_off()
    
    elif action == "DISCOVER":
        boards.clear()
        new_boards = discover_boards()
        boards.extend(new_boards)
        for b in boards:
            b.open()
        logger.info(f"Rediscovered {len(boards)} board(s)")

# =============================================================================
# Direct Test Mode
# =============================================================================

def test_boards():
    """Test all discovered boards with a quick LED flash."""
    logger.info("=== LED-Wiz Direct Test ===")
    boards = discover_boards()
    
    if not boards:
        logger.error("No LED-Wiz boards found!")
        return False
    
    logger.info(f"Found {len(boards)} board(s)")
    
    for board in boards:
        logger.info(f"Testing Unit {board.unit_id}...")
        if not board.open():
            logger.error(f"  Failed to open Unit {board.unit_id}")
            continue
        
        # Flash all LEDs on
        logger.info(f"  Turning all LEDs ON...")
        frame = [48] * 32  # Full brightness
        board.set_channels(frame)
        time.sleep(0.5)
        
        # Turn off
        logger.info(f"  Turning all LEDs OFF...")
        board.all_off()
        time.sleep(0.2)
        
        board.close()
        logger.info(f"  Unit {board.unit_id} OK!")
    
    return True

# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="LED-Wiz Direct HID Driver")
    parser.add_argument("--daemon", action="store_true", help="Run as named pipe daemon")
    parser.add_argument("--test", action="store_true", help="Test all boards with LED flash")
    parser.add_argument("--discover", action="store_true", help="Discover and list boards")
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon()
    elif args.test:
        success = test_boards()
        sys.exit(0 if success else 1)
    elif args.discover:
        boards = discover_boards()
        if boards:
            print(f"Found {len(boards)} LED-Wiz board(s):")
            for b in boards:
                print(f"  Unit {b.unit_id}: PID=0x{b.pid:04X}")
        else:
            print("No LED-Wiz boards found.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
