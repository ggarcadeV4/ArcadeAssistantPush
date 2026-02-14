"""PactoTech board sanity scanning utilities.

Provides hardware-aware diagnostics that Controller Chuck can use when a user
asks, "Chuck, what's wrong with my board?"  The scanner attempts to:

* Detect the currently connected encoder (model + VID/PID)
* Read mode flags (turbo, analog, etc.) from HID feature reports when possible
* Detect dual-mode conflicts such as analog + turbo simultaneously enabled
* Look for ghost pulses / instability in recent pin samples
* Produce a structured report that downstream routes can relay verbatim while
  also summarising the key findings for the persona.

All I/O is best-effort – absence of HID support or missing hardware should
result in a graceful, explainable failure instead of an exception.  The module
is written so unit tests can inject mock detection services, HID transports,
and pin samplers without talking to a real encoder.

HID transactions may take OS-level timeout durations (commonly 5–10 seconds).
Callers should enforce HTTP or gateway-level timeouts of ~30 seconds so a
blocked HID read does not stall the entire route indefinitely.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .chuck.detection import (
    BoardDetectionError,
    BoardInfo,
    BoardNotFoundError,
    get_detection_service,
)
from .device_scanner import scan_devices

try:  # Optional hardware dependency
    import hid  # type: ignore
except Exception:  # pragma: no cover - not all CI hosts have hidapi
    hid = None  # type: ignore

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class ModeFlags:
    """Mode flag snapshot fetched from HID Feature Reports or inference."""

    turbo: bool = False
    analog: bool = False
    twinstick: bool = False
    xinput: bool = False
    player_count: int = 2
    raw_bits: Optional[List[int]] = None
    source: str = "inferred"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turbo": self.turbo,
            "analog": self.analog,
            "twinstick": self.twinstick,
            "xinput": self.xinput,
            "player_count": self.player_count,
            "raw_bits": self.raw_bits,
            "source": self.source,
        }


@dataclass
class Issue:
    """Structured issue description for downstream personas."""

    type: str
    severity: str
    description: str
    detected_at: dt.datetime = field(default_factory=lambda: dt.datetime.utcnow())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class PinStability:
    """Stores ghost-pulse heuristics for LED or visual confirmation."""

    status: str = "unknown"  # stable, unstable, critical, unknown
    sample_window_ms: int = 0
    transitions: int = 0
    ghost_pulses: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "status": self.status,
            "sample_window_ms": self.sample_window_ms,
            "transitions": self.transitions,
            "ghost_pulses": self.ghost_pulses,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class SanityReport:
    """Response object returned to Chuck's tool layer."""

    board_detected: bool
    board_info: Optional[BoardInfo]
    firmware_version: Optional[str]
    mode_flags: ModeFlags
    issues_detected: List[Issue]
    pin_stability: PinStability
    ghost_pulses_detected: bool
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "board_detected": self.board_detected,
            "board_info": self.board_info.to_dict() if self.board_info else None,
            "firmware_version": self.firmware_version,
            "mode_flags": self.mode_flags.to_dict(),
            "issues_detected": [issue.to_dict() for issue in self.issues_detected],
            "pin_stability": self.pin_stability.to_dict(),
            "ghost_pulses_detected": self.ghost_pulses_detected,
            "recommendations": self.recommendations,
        }


# --------------------------------------------------------------------------- #
# HID transport wrapper
# --------------------------------------------------------------------------- #


class HIDTransport:
    """Lightweight HID wrapper used by the scanner.

    All operations are best-effort: if hidapi is missing or a call blocks,
    methods fall back to graceful failure so HTTP callers can time out on
    their own rather than hanging indefinitely.
    """

    MODE_FLAG_FEATURE_ID = 0x07
    MODE_FLAG_REPORT_LEN = 8

    def __init__(self, driver: Optional[Any] = None):
        self._driver = driver if driver is not None else hid

    def enumerate_devices(self) -> List[Dict[str, Any]]:
        if not self._driver:
            return []
        try:
            return list(self._driver.enumerate())
        except Exception as exc:  # pragma: no cover - hardware required
            logger.debug("HID enumeration failed: %s", exc)
            return []

    def read_feature_report(
        self,
        device_info: Dict[str, Any],
        report_id: int = None,
        report_len: int = None,
    ) -> Optional[List[int]]:
        """Read a feature report from the supplied device."""
        if not self._driver:
            return None

        feature_id = report_id or self.MODE_FLAG_FEATURE_ID
        payload_len = report_len or self.MODE_FLAG_REPORT_LEN

        try:
            device = self._driver.device()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - hardware required
            logger.debug("HID device construction failed: %s", exc)
            return None

        try:
            path = device_info.get("path")
            if path:
                device.open_path(path)  # type: ignore[attr-defined]
            else:
                vid = device_info.get("vendor_id")
                pid = device_info.get("product_id")
                if vid is None or pid is None:
                    return None
                device.open(int(vid), int(pid))  # type: ignore[attr-defined]

            data = device.get_feature_report(feature_id, payload_len)
            if isinstance(data, (bytes, bytearray)):
                return list(data)
            return list(data or [])
        except Exception as exc:  # pragma: no cover - hardware required
            logger.debug("Failed to read HID feature report: %s", exc)
            return None
        finally:
            try:
                device.close()
            except Exception:  # pragma: no cover - best effort
                pass


# --------------------------------------------------------------------------- #
# BoardSanityScanner
# --------------------------------------------------------------------------- #


PACTO_KEYWORDS = ("pacto", "pacto tech", "pactotech")
USB_ID_PATTERN = re.compile(r"vid[_:-]?([0-9a-f]{4}).*pid[_:-]?([0-9a-f]{4})", re.I)
COLON_ID_PATTERN = re.compile(r"([0-9a-f]{4}):([0-9a-f]{4})", re.I)


class BoardSanityScanner:
    """Primary worker that assembles a SanityReport.

    The scanner prefers real HID telemetry but gracefully downgrades to detection
    heuristics when devices are unavailable or time out.
    """

    def __init__(
        self,
        device_id: Optional[str],
        *,
        detection_service: Optional[Any] = None,
        hid_transport: Optional[HIDTransport] = None,
        pin_sampler: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        mode_reader: Optional[Callable[[Optional[BoardInfo]], ModeFlags]] = None,
        now: Optional[Callable[[], dt.datetime]] = None,
    ):
        self.device_id = device_id
        self._detection_service = detection_service or get_detection_service()
        self._hid = hid_transport or HIDTransport()
        self._pin_sampler = pin_sampler
        self._custom_mode_reader = mode_reader
        self._now = now or dt.datetime.utcnow

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def scan(self) -> SanityReport:
        board_info = self._detect_board_model()
        firmware_version = self._read_firmware_version(board_info)
        mode_flags = self._resolve_mode_flags(board_info)
        pin_stability = self._evaluate_pin_stability()
        issues = self._collect_issues(board_info, mode_flags, pin_stability, firmware_version)
        recommendations = self._build_recommendations(issues, firmware_version, pin_stability)

        report = SanityReport(
            board_detected=bool(board_info and board_info.detected),
            board_info=board_info,
            firmware_version=firmware_version,
            mode_flags=mode_flags,
            issues_detected=issues,
            pin_stability=pin_stability,
            ghost_pulses_detected=pin_stability.ghost_pulses > 0,
            recommendations=recommendations,
        )
        return report

    # ------------------------------------------------------------------ #
    # Detection helpers
    # ------------------------------------------------------------------ #
    def _detect_board_model(self) -> Optional[BoardInfo]:
        vid, pid = self._extract_vid_pid(self.device_id)
        if vid and pid:
            try:
                board = self._detection_service.detect_board(vid, pid, use_cache=False)
                return board
            except BoardNotFoundError:
                logger.debug("Board %s:%s not detected via detection service", vid, pid)
            except BoardDetectionError as exc:
                logger.debug("Board detection error for %s:%s - %s", vid, pid, exc)

        # Fall back to raw HID / USB enumeration
        for device in scan_devices():
            if self._looks_like_pacto(device):
                return BoardInfo(
                    vid=(device.get("vid") or "").replace("0x", ""),
                    pid=(device.get("pid") or "").replace("0x", ""),
                    vid_pid=self._format_vid_pid(device.get("vid"), device.get("pid")),
                    name=device.get("product") or "PactoTech Encoder",
                    manufacturer=device.get("manufacturer") or "PactoTech",
                    product_string=device.get("product"),
                    manufacturer_string=device.get("manufacturer"),
                )

        return None

    def _resolve_mode_flags(self, board_info: Optional[BoardInfo]) -> ModeFlags:
        if self._custom_mode_reader:
            return self._custom_mode_reader(board_info)

        hid_info = self._locate_hid_device(board_info)
        if hid_info:
            raw = self._hid.read_feature_report(hid_info)
            if raw:
                return self._decode_mode_flags(raw, source="hid")

        return self._infer_mode_flags(board_info)

    def _evaluate_pin_stability(self) -> PinStability:
        if not self._pin_sampler:
            return PinStability(status="unknown")

        samples = self._pin_sampler() or []
        if not samples:
            return PinStability(status="unknown")

        timestamps = [
            float(event.get("timestamp_ms") or 0) for event in samples if "timestamp_ms" in event
        ]
        if timestamps:
            window_ms = int(max(timestamps) - min(timestamps))
        else:
            window_ms = 0

        ghost_pulses = sum(1 for event in samples if event.get("ghost") or event.get("type") == "ghost")
        transitions = len(samples)

        status = "stable"
        if ghost_pulses:
            ratio = ghost_pulses / max(1, transitions)
            if ratio >= 0.3 or ghost_pulses >= 5:
                status = "critical"
            else:
                status = "unstable"

        return PinStability(
            status=status,
            sample_window_ms=window_ms,
            transitions=transitions,
            ghost_pulses=ghost_pulses,
            details={"sampled_controls": sorted({event.get("control") for event in samples if event.get("control")})},
        )

    # ------------------------------------------------------------------ #
    # Issue + recommendation helpers
    # ------------------------------------------------------------------ #
    def _collect_issues(
        self,
        board_info: Optional[BoardInfo],
        mode_flags: ModeFlags,
        pin_stability: PinStability,
        firmware_version: Optional[str],
    ) -> List[Issue]:
        issues: List[Issue] = []

        if not board_info:
            issues.append(
                Issue(
                    type="board_not_detected",
                    severity="high",
                    description="No PactoTech board was detected on USB/HID busses.",
                )
            )

        if mode_flags.analog and mode_flags.turbo:
            issues.append(
                Issue(
                    type="dual_mode_conflict",
                    severity="high",
                    description="Analog and Turbo were simultaneously enabled (known dual-mode conflict).",
                    metadata={"flags": mode_flags.to_dict()},
                )
            )

        if pin_stability.status in {"unstable", "critical"}:
            issues.append(
                Issue(
                    type="pin_instability",
                    severity="high" if pin_stability.status == "critical" else "medium",
                    description=f"Detected {pin_stability.ghost_pulses} ghost pulses across "
                    f"{pin_stability.transitions} samples.",
                    metadata={"pin_stability": pin_stability.to_dict()},
                )
            )

        if not firmware_version or firmware_version == "unknown":
            issues.append(
                Issue(
                    type="firmware_unknown",
                    severity="low",
                    description="Firmware version could not be determined from USB descriptors.",
                )
            )

        return issues

    def _build_recommendations(
        self,
        issues: Iterable[Issue],
        firmware_version: Optional[str],
        pin_stability: PinStability,
    ) -> List[str]:
        recs: List[str] = []
        issue_types = {issue.type for issue in issues}

        if "board_not_detected" in issue_types:
            recs.append("Check the USB cable, ensure the encoder is powered, and rerun the scan.")
        if "dual_mode_conflict" in issue_types:
            recs.append("Disable either analog or turbo (software controlled via repair endpoint).")
        if "pin_instability" in issue_types:
            recs.append("Inspect wiring for floating grounds; rerun Teach Chuck after wiring fixes.")
        if "firmware_unknown" in issue_types:
            recs.append("Capture firmware metadata via the firmware preview route before flashing.")
        if not recs:
            status = "stable" if pin_stability.status == "stable" else "unknown"
            healthy_msg = "Board looks healthy and ready for mapping." if status == "stable" else \
                "Board appears connected; run mapping recovery if controls still misbehave."
            recs.append(healthy_msg)
        if firmware_version and firmware_version != "unknown":
            recs.append(f"Current firmware version: {firmware_version}")
        return recs

    # ------------------------------------------------------------------ #
    # Low-level helpers
    # ------------------------------------------------------------------ #
    def _read_firmware_version(self, board_info: Optional[BoardInfo]) -> Optional[str]:
        if not board_info:
            return None

        for candidate in (
            getattr(board_info, "product_string", None),
            getattr(board_info, "name", None),
        ):
            if candidate:
                match = re.search(r"(?:fw|firmware)[\\s:_-]*v?(\\d+[\\.\\d+]*)", candidate, re.I)
                if match:
                    return match.group(1)
        return "unknown"

    def _locate_hid_device(self, board_info: Optional[BoardInfo]) -> Optional[Dict[str, Any]]:
        devices = self._hid.enumerate_devices()
        if not devices:
            return None

        for device in devices:
            path = device.get("path")
            vid = self._normalize_hex(device.get("vendor_id"))
            pid = self._normalize_hex(device.get("product_id"))
            if self.device_id and path and self.device_id.lower() in str(path).lower():
                return device
            if board_info and vid and pid:
                if vid.endswith(board_info.vid[-4:]) and pid.endswith(board_info.pid[-4:]):
                    return device
        return None

    @staticmethod
    def _decode_mode_flags(raw: Sequence[int], *, source: str) -> ModeFlags:
        if not raw:
            return ModeFlags(source="unknown")

        byte0 = raw[0]
        byte1 = raw[1] if len(raw) > 1 else 0

        turbo = bool(byte0 & 0x01)
        analog = bool(byte0 & 0x02)
        twinstick = bool(byte0 & 0x04)
        xinput = bool(byte1 & 0x01)
        player_bits = (byte1 >> 1) & 0x03
        player_count = {0: 2, 1: 4, 2: 1}.get(player_bits, 2)

        return ModeFlags(
            turbo=turbo,
            analog=analog,
            twinstick=twinstick,
            xinput=xinput,
            player_count=player_count,
            raw_bits=list(raw),
            source=source,
        )

    def _infer_mode_flags(self, board_info: Optional[BoardInfo]) -> ModeFlags:
        name = (board_info.name if board_info else "") or ""
        turbo = "turbo" in name.lower()
        analog = "analog" in name.lower()
        players = 4 if "4000" in name else 2
        return ModeFlags(
            turbo=turbo,
            analog=analog,
            player_count=players,
            source="inferred",
        )

    @staticmethod
    def _looks_like_pacto(device: Dict[str, Any]) -> bool:
        product = (device.get("product") or "").lower()
        manufacturer = (device.get("manufacturer") or "").lower()
        device_id = (device.get("device_id") or "").lower()

        for keyword in PACTO_KEYWORDS:
            lowered = keyword.lower()
            if lowered in product or lowered in manufacturer or lowered in device_id:
                return True
        return False

    @staticmethod
    def _format_vid_pid(vid: Optional[str], pid: Optional[str]) -> str:
        vid_clean = (vid or "").lower().replace("0x", "").zfill(4)
        pid_clean = (pid or "").lower().replace("0x", "").zfill(4)
        return f"{vid_clean}:{pid_clean}"

    @classmethod
    def _extract_vid_pid(cls, device_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not device_id:
            return None, None
        device_id = device_id.strip()

        usb_match = USB_ID_PATTERN.search(device_id)
        if usb_match:
            vid, pid = usb_match.groups()
            return vid.lower(), pid.lower()

        colon_match = COLON_ID_PATTERN.search(device_id)
        if colon_match:
            vid, pid = colon_match.groups()
            return vid.lower(), pid.lower()

        return None, None

    @staticmethod
    def _normalize_hex(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().lower().replace("0x", "")
            if not value:
                return None
            return f"0x{value.zfill(4)}"
        try:
            return f"0x{int(value):04x}"
        except (ValueError, TypeError):
            return None


__all__ = [
    "BoardSanityScanner",
    "SanityReport",
    "ModeFlags",
    "PinStability",
    "Issue",
    "HIDTransport",
]
