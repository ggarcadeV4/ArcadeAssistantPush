import os
import subprocess
import logging
import time
import threading
from typing import List, Sequence, Optional

logger = logging.getLogger("led_engine.shim")

# =============================================================================
# CINEMA CALIBRATION CONFIGURATION
# =============================================================================

# LED-Wiz PWM Range: 0 = Off, 1-48 = Steady brightness, 49+ = STROBE (NEVER USE!)
PWM_MIN = 0
PWM_MAX = 48

# Gamma 2.5 Correction - Pre-calculated lookup table for perceptually smooth fades
# Human eyes perceive brightness logarithmically, not linearly
GAMMA = 2.5
GAMMA_TABLE = [int(round(pow(i / 48, GAMMA) * 48)) for i in range(49)]

# Electric Ice Color Scaling - Balance colors to match weaker green channel
# Green appears dimmest on camera, so we scale R and B down to match
SCALE_RED = 0.65    # Red LEDs are voltage-dominant
SCALE_GREEN = 1.0   # Green is the anchor (weakest)
SCALE_BLUE = 0.75   # Blue LEDs are luminous-dominant

# Port Trim - Per-port brightness adjustments (placeholder for calibration wizard)
# Format: { port_index: trim_multiplier } where 1.0 = no adjustment
# Example: { 5: 0.8 } would reduce port 5 brightness by 20%
PORT_TRIM: dict[int, float] = {}


def apply_gamma(value: int) -> int:
    """Apply gamma correction using pre-calculated lookup table."""
    if value <= 0:
        return 0
    if value >= 48:
        return 48
    return GAMMA_TABLE[value]


def normalize_brightness(value: int, color: str = 'green', port_index: Optional[int] = None) -> int:
    """
    Full Cinema Calibration pipeline: Input -> Scale -> Gamma -> Trim -> PWM(0-48)
    
    Args:
        value: Input brightness (0-255 or 0-48)
        color: 'red', 'green', or 'blue' for color scaling
        port_index: Optional port index for per-port trim adjustment
    
    Returns:
        Calibrated PWM value (0-48)
    """
    # Step 1: Normalize input to 0-48 range (handle both 0-255 and 0-48 inputs)
    if value > 48:
        base_pwm = int((value / 255) * 48)
    else:
        base_pwm = int(value)
    
    # Step 2: Apply color scaling
    if color == 'red':
        scaled = base_pwm * SCALE_RED
    elif color == 'blue':
        scaled = base_pwm * SCALE_BLUE
    else:  # green or unknown
        scaled = base_pwm * SCALE_GREEN
    
    # Step 3: Apply gamma correction
    gamma_corrected = apply_gamma(int(scaled))
    
    # Step 4: Apply per-port trim (if configured)
    if port_index is not None and port_index in PORT_TRIM:
        trimmed = int(gamma_corrected * PORT_TRIM[port_index])
    else:
        trimmed = gamma_corrected
    
    # Step 5: Final clamp to safe PWM range
    return max(PWM_MIN, min(PWM_MAX, trimmed))

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

    def set_channels(self, board_id: int, frame: Sequence[int], color_map: Optional[List[str]] = None):
        """
        Sends SBA and PBA commands for a full frame with Cinema Calibration.
        
        Args:
            board_id: 1-based board ID
            frame: List of 32 brightness values (0-255 or 0-48)
            color_map: Optional list of 32 color strings ('red', 'green', 'blue')
                      If not provided, defaults to 'green' for all ports
        """
        # Default color map if not provided
        if color_map is None:
            color_map = ['green'] * 32
        
        # Global port offset for this board (board 1 = ports 0-31, board 2 = 32-63, etc.)
        port_offset = (board_id - 1) * 32
        
        # Apply Cinema Calibration to entire frame
        calibrated_frame = []
        for i, val in enumerate(frame[:32]):
            color = color_map[i] if i < len(color_map) else 'green'
            global_port = port_offset + i
            calibrated_val = normalize_brightness(val, color=color, port_index=global_port)
            calibrated_frame.append(calibrated_val)
        
        # Pad to 32 if needed
        while len(calibrated_frame) < 32:
            calibrated_frame.append(0)

        # 1. SBA Command - build bank masks from calibrated values
        bank0 = bank1 = bank2 = bank3 = 0
        for i, val in enumerate(calibrated_frame):
            if val > 0:
                if i < 8: bank0 |= (1 << i)
                elif i < 16: bank1 |= (1 << (i - 8))
                elif i < 24: bank2 |= (1 << (i - 16))
                else: bank3 |= (1 << (i - 24))

        sba_cmd = f"SBA {board_id} {bank0} {bank1} {bank2} {bank3} 2"
        self.send_command(sba_cmd)

        # 2. PBA Commands (4 chunks of 8 ports each)
        for chunk_idx in range(4):
            start = chunk_idx * 8
            chunk = calibrated_frame[start:start+8]
            
            pba_vals = " ".join(map(str, chunk))
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
