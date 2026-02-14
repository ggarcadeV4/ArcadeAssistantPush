"""LED hardware service for HID device detection and control."""
import os
import threading
import time
import logging
from typing import Dict, List, Tuple, Optional, Callable, Any

try:
    import hid
except ImportError:
    hid = None  # Graceful fallback for development

logger = logging.getLogger('led_hardware')

# Device definitions with VID/PID pairs
DEVICE_SPECS = {
    (0xFAFA, 0x00F0): {"name": "LED-Wiz", "ports": 32},
    (0xD209, 0x1500): {"name": "Pac-LED64", "ports": 64},
    (0xFAFA, 0x00F7): {"name": "GroovyGameGear", "ports": 96},
    (0xD209, 0x1401): {"name": "Ultimarc", "ports": 48}
}


class LEDHardwareService:
    """Singleton service for LED hardware detection and control."""

    _instance: Optional['LEDHardwareService'] = None

    def __new__(cls) -> 'LEDHardwareService':
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the LED hardware service."""
        if self._initialized:
            return

        self._initialized = True
        self._devices: Dict[int, dict] = {}
        self._device_lock = threading.Lock()
        self._event_callbacks: Dict[str, List[Callable]] = {
            "led_hardware_change": [],
            "led_preview_update": []
        }
        self._mock_mode = os.getenv('MOCK_HARDWARE', '').lower() in ('true', '1')
        self._hotplug_thread: Optional[threading.Thread] = None
        self._running = False

        # Initialize devices and start hotplug monitor in background thread
        # This prevents import-time blocking if HID enumeration hangs
        self._init_thread = threading.Thread(target=self._async_init, daemon=True)
        self._init_thread.start()

    def _async_init(self):
        """Perform initialization in background."""
        # Check for explicit disable flag (default to True to fix boot hang)
        if os.getenv('AA_DISABLE_NATIVE_LED', '1') == '1':
            logger.info("Native LED hardware detection disabled by AA_DISABLE_NATIVE_LED (using mock mode)")
            self._mock_mode = True
            with self._device_lock:
                self._devices[0] = {
                    "id": 0,
                    "name": "Virtual LED Device (Safe Mode)",
                    "ports": 32,
                    "vid": 0,
                    "pid": 0,
                    "path": b"mock"
                }
            return

        logger.debug("Starting async LED hardware initialization...")
        self._detect_devices()
        self._start_hotplug_monitor()
        logger.debug("Async LED hardware initialization complete")

    def _detect_devices(self) -> None:
        """Detect connected LED devices via HID."""
        with self._device_lock:
            old_devices = set(self._devices.keys())
            self._devices.clear()

            if self._mock_mode or hid is None:
                # Mock mode: provide virtual device
                self._devices[0] = {
                    "id": 0,
                    "name": "Virtual LED Device",
                    "ports": 32,
                    "vid": 0,
                    "pid": 0,
                    "path": b"mock"
                }
                logger.info("Mock mode enabled - using virtual device")
            else:
                # Real hardware detection
                try:
                    device_id = 1
                    for device_info in hid.enumerate():
                        vid_pid = (device_info['vendor_id'], device_info['product_id'])
                        if vid_pid in DEVICE_SPECS:
                            spec = DEVICE_SPECS[vid_pid]
                            self._devices[device_id] = {
                                "id": device_id,
                                "name": spec["name"],
                                "ports": spec["ports"],
                                "vid": device_info['vendor_id'],
                                "pid": device_info['product_id'],
                                "path": device_info['path']
                            }
                            device_id += 1
                            logger.info(f"Detected {spec['name']} at {device_info['path']}")

                    if not self._devices:
                        # No devices found - use virtual device
                        self._devices[0] = {
                            "id": 0,
                            "name": "Virtual LED Device",
                            "ports": 32,
                            "vid": 0,
                            "pid": 0,
                            "path": b"mock"
                        }
                        logger.info("No physical devices found - using virtual device")

                except Exception as e:
                    logger.error(f"HID enumeration failed: {e}")
                    # Fallback to virtual device on error
                    self._devices[0] = {
                        "id": 0,
                        "name": "Virtual LED Device",
                        "ports": 32,
                        "vid": 0,
                        "pid": 0,
                        "path": b"mock"
                    }

            # Check if device list changed
            new_devices = set(self._devices.keys())
            if old_devices != new_devices:
                self._emit("led_hardware_change", {"devices": self.get_devices()})

    def _start_hotplug_monitor(self) -> None:
        """Start background thread for USB hotplug detection."""
        if self._hotplug_thread is None or not self._hotplug_thread.is_alive():
            self._running = True
            self._hotplug_thread = threading.Thread(target=self._monitor_devices, daemon=True)
            self._hotplug_thread.start()

    def _monitor_devices(self) -> None:
        """Background thread to detect USB hotplug events."""
        while self._running:
            time.sleep(5)
            self._detect_devices()

    def get_devices(self) -> List[dict]:
        """Get list of detected LED devices."""
        with self._device_lock:
            return list(self._devices.values())

    def write_port(self, device_id: int, port: int, rgb: Tuple[int, int, int]) -> bool:
        """Write RGB values to a specific port."""
        # Validate inputs
        with self._device_lock:
            device = self._devices.get(device_id)
            if not device:
                logger.error(f"Device {device_id} not found")
                return False

            if not (1 <= port <= device['ports']):
                logger.error(f"Port {port} out of range for {device['name']} (1-{device['ports']})")
                return False

            r, g, b = rgb
            if not all(0 <= v <= 255 for v in [r, g, b]):
                logger.error(f"RGB values must be 0-255, got {rgb}")
                return False

        # Emit preview update for frontend
        color_hex = f"#{r:02x}{g:02x}{b:02x}"
        self._emit("led_preview_update", {"device_id": device_id, "port": port, "color": color_hex})

        # Handle mock mode
        if device['path'] == b"mock":
            logger.info(f"[MOCK] Device {device_id} Port {port} → RGB{rgb}")
            return True

        # Write to real hardware
        try:
            dev = hid.device()
            dev.open_path(device['path'])

            # LED-Wiz protocol: [0x00, port, r, g, b]
            data = [0x00, port, r, g, b]
            dev.write(data)
            dev.close()

            logger.debug(f"Wrote RGB{rgb} to device {device_id} port {port}")
            return True

        except Exception as e:
            logger.error(f"Failed to write to device {device_id}: {e}")
            return False

    def register_callback(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event in self._event_callbacks:
            self._event_callbacks[event].append(callback)

    def _emit(self, event: str, data: dict) -> None:
        """Emit an event to all registered callbacks."""
        for callback in self._event_callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    def shutdown(self) -> None:
        """Shutdown the service cleanly."""
        self._running = False
        if self._hotplug_thread:
            self._hotplug_thread.join(timeout=1)


# Module-level singleton instance
led_service = LEDHardwareService()

# Public API exports
get_devices = led_service.get_devices
write_port = led_service.write_port
register_callback = led_service.register_callback