import os
import subprocess
import logging
import time
import threading
from typing import List, Sequence

logger = logging.getLogger("led_engine.shim")

# =============================================================================
# CINEMA CALIBRATION LOGIC (The Intelligence Layer)
# =============================================================================
SCALE_RED = 0.65
SCALE_GREEN = 1.0
SCALE_BLUE = 0.75
GAMMA = 2.5
PORT_TRIM = {}  # Per-port calibration (e.g., {port_id: multiplier})

# Pre-calculated Gamma 2.5 Table (Input 0-255 -> Output PWM 0-48)
GAMMA_TABLE = [
    max(0, min(48, int(pow(i / 255.0, GAMMA) * 48.0)))
    for i in range(256)
]

def normalize_brightness(r, g, b):
    """
    Applies color scaling and gamma correction to an RGB triplet.
    Returns a triplet of perfected PWM values (0-48).
    """
    r_val = GAMMA_TABLE[max(0, min(255, int(r * SCALE_RED)))]
    g_val = GAMMA_TABLE[max(0, min(255, int(g * SCALE_GREEN)))]
    b_val = GAMMA_TABLE[max(0, min(255, int(b * SCALE_BLUE)))]
    return (r_val, g_val, b_val)

class LEDWizShimClient:
    """Python client for the C++ LED-Wiz Shim Daemon."""

    PIPE_NAME = r"\\.\pipe\ArcadeLED"
    DAEMON_EXE = "ledwiz_daemon.exe"

    def __init__(self):
        self._pipe_handle = None
        self._daemon_path = os.path.join(os.path.dirname(__file__), self.DAEMON_EXE)
        self._lock = threading.Lock()

    def ensure_daemon_running(self):
        """Starts the daemon if it's not already running."""
        if os.name != 'nt':
            logger.warning("Shim daemon only supports Windows.")
            return False

        # Check if daemon is already running (simple check by attempting to connect)
        if self._check_pipe_exists():
            return True

        if not os.path.exists(self._daemon_path):
            logger.error(f"Daemon executable not found at {self._daemon_path}")
            return False

        try:
            logger.info(f"Starting LED-Wiz daemon: {self._daemon_path}")
            subprocess.Popen([self._daemon_path], creationflags=subprocess.CREATE_NO_WINDOW)
            # Give it a second to start
            time.sleep(1.0)
            return self._check_pipe_exists()
        except Exception as e:
            logger.error(f"Failed to start daemon: {e}")
            return False

    def _check_pipe_exists(self):
        try:
            # On Windows, we use a different way to check if pipe exists
            if os.name == 'nt':
                # WaitNamedPipe returns True if pipe exists, with a tiny timeout
                import ctypes
                return ctypes.windll.kernel32.WaitNamedPipeW(self.PIPE_NAME, 1)
            return os.path.exists(self.PIPE_NAME)
        except Exception:
            return False

    def connect(self):
        """Connects to the named pipe."""
        if os.name != 'nt':
            return False

        self.ensure_daemon_running()

        try:
            # We use open() with 'w' for the named pipe
            self._pipe_handle = open(self.PIPE_NAME, 'w', buffering=1)
            logger.info("Connected to LED-Wiz Shim Pipe.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to pipe: {e}")
            self._pipe_handle = None
            return False

    def send_command(self, cmd: str):
        """Sends a raw command string to the daemon."""
        with self._lock:
            if not self._pipe_handle:
                if not self.connect():
                    return False

            try:
                self._pipe_handle.write(cmd + "\n")
                self._pipe_handle.flush()
                return True
            except Exception as e:
                logger.error(f"Error writing to pipe: {e}")
                self._pipe_handle = None
                return False

    def set_channels(self, board_id: int, frame: Sequence[int]):
        """Sends SBA and PBA commands for a full frame."""
        # board_id is 1-based

        # 1. SBA Command (ON/OFF state)
        bank0 = bank1 = bank2 = bank3 = 0
        for i, val in enumerate(frame[:32]):
            if val > 0:
                if i < 8: bank0 |= (1 << i)
                elif i < 16: bank1 |= (1 << (i - 8))
                elif i < 24: bank2 |= (1 << (i - 16))
                else: bank3 |= (1 << (i - 24))

        sba_cmd = f"SBA {board_id} {bank0} {bank1} {bank2} {bank3} 2"
        self.send_command(sba_cmd)

        # 2. PBA Commands (4 chunks of 8 ports)
        for chunk_idx in range(4):
            start = chunk_idx * 8
            chunk = frame[start:start+8]

            # Apply Cinema Calibration (Port Trim + Gamma 2.5 Table)
            perfected = []
            for i, v in enumerate(chunk):
                # Calculate global port ID (1-based)
                port_id = (board_id - 1) * 32 + (chunk_idx * 8) + i + 1

                # 1. Apply per-port trim
                trimmed_val = int(v * PORT_TRIM.get(port_id, 1.0))

                # 2. Apply Gamma Correction (0-255 -> 0-48 PWM)
                perfected_val = GAMMA_TABLE[max(0, min(255, trimmed_val))]
                perfected.append(perfected_val)

            while len(perfected) < 8:
                perfected.append(0)

            pba_vals = " ".join(map(str, perfected))
            pba_cmd = f"PBA_CHUNK {board_id} {chunk_idx} {pba_vals}"
            self.send_command(pba_cmd)

    def all_off(self):
        self.send_command("ALL_OFF")

    def discover(self):
        self.send_command("DISCOVER")

# Global instance
_shim_client = None

def get_shim_client():
    global _shim_client
    if _shim_client is None:
        _shim_client = LEDWizShimClient()
    return _shim_client
