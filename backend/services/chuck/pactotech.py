"""Helpers for integrating Pacto Tech encoder boards with Controller Chuck.

Provides VID/PID constants, board detection helpers, and translation utilities
for converting Pacto Tech specific mapping data into the standard Mapping
Dictionary structure used across the backend.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .detection import (
    BoardDetectionError,
    BoardInfo,
    get_detection_service,
)

logger = logging.getLogger(__name__)


class PactoTechBoard:
    """Utility wrapper for Pacto Tech encoder boards."""

    VID = "0x1234"  # Placeholder - replace with vendor provided VID
    PID = "0x5678"  # Placeholder - replace with vendor provided PID
    BOARD_TYPE = "pactotech"
    MAPPING_FILE = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "board_mappings"
        / "pactotech.json"
    )

    def __init__(self) -> None:
        self._keycode_cache: Optional[Dict[str, int]] = None

    @classmethod
    def matches(cls, vid: Optional[str], pid: Optional[str], name: Optional[str] = None) -> bool:
        """Return True if the supplied identifiers look like a Pacto Tech board."""
        vid_norm = cls._normalize_vid_pid(vid)
        pid_norm = cls._normalize_vid_pid(pid)
        matches_vid_pid = (
            vid_norm == cls._normalize_vid_pid(cls.VID)
            and pid_norm == cls._normalize_vid_pid(cls.PID)
        )
        matches_name = bool(name and "pacto" in name.lower())
        return matches_vid_pid or matches_name

    def detect(
        self,
        *,
        use_cache: bool = True,
        timeout: float = 2.0,
    ) -> Optional[BoardInfo]:
        """Detect a connected Pacto Tech board via the shared detection service."""
        service = get_detection_service()
        try:
            board = service.detect_board(self.VID, self.PID, use_cache=use_cache, timeout=timeout)
            logger.info("Detected Pacto Tech board: %s (%s)", board.name, board.vid_pid)
            return board
        except BoardDetectionError as exc:
            logger.debug("Pacto Tech board not detected: %s", exc)
            return None

    def translate_pin_mapping(self, pacto_mapping: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Convert a Pacto Tech layout payload into the Mapping Dictionary format.

        The Pacto firmware emits layouts as either:
          * {'assignments': [{'control': 'p1.button1', 'keycode': 'F1'} ...]}
          * {'mappings': {'p1.button1': {'keycode': 'F1', 'type': 'button'}}}
          * Or a bare dict using control -> keycode pairs
        """
        assignments = pacto_mapping.get("assignments")
        if assignments is None:
            assignments = pacto_mapping.get("mappings")
        if assignments is None:
            assignments = pacto_mapping

        standard: Dict[str, Dict[str, Any]] = {}
        keycode_map = self.get_keycode_map()

        for control_key, payload in self._iter_assignments(assignments):
            if not control_key:
                continue

            raw_keycode, control_type, label = self._extract_assignment_metadata(control_key, payload)
            if not raw_keycode:
                logger.debug("Skipping %s - missing keycode payload", control_key)
                continue

            normalized_keycode = self._normalize_keycode(raw_keycode)
            if normalized_keycode not in keycode_map:
                logger.warning(
                    "Pacto Tech mapping references unknown keycode '%s' for %s",
                    raw_keycode,
                    control_key,
                )
                continue

            standard[control_key] = {
                "pin": keycode_map[normalized_keycode],
                "type": control_type or self._infer_control_type(control_key),
                "label": label or control_key.replace(".", " ").title(),
                "source": "pactotech",
            }

        return standard

    def get_keycode_map(self) -> Dict[str, int]:
        """Return the cached keycode-to-pin mapping."""
        if self._keycode_cache is not None:
            return self._keycode_cache

        data: Dict[str, Any] = {}
        try:
            with open(self.MAPPING_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle) or {}
        except FileNotFoundError:
            logger.error("Pacto Tech mapping file missing: %s", self.MAPPING_FILE)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", self.MAPPING_FILE, exc)

        normalized: Dict[str, int] = {}
        for keycode, pin in data.items():
            normalized_key = self._normalize_keycode(keycode)
            try:
                normalized[normalized_key] = int(pin)
            except (ValueError, TypeError):
                logger.warning("Ignoring non-integer pin for %s: %r", keycode, pin)

        self._keycode_cache = normalized
        logger.info("Loaded %d Pacto Tech key mappings", len(normalized))
        return normalized

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_vid_pid(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.lower().replace("0x", "").strip().zfill(4)

    @staticmethod
    def _normalize_keycode(value: str) -> str:
        token = value.strip().lower()
        if token.startswith("key_"):
            token = token[4:]
        return token.replace(" ", "_")

    @staticmethod
    def _infer_control_type(control_key: str) -> str:
        lowered = control_key.lower()
        if ".up" in lowered or ".down" in lowered or ".left" in lowered or ".right" in lowered:
            return "joystick"
        if ".coin" in lowered:
            return "coin"
        if ".start" in lowered:
            return "start"
        return "button"

    @staticmethod
    def _iter_assignments(assignments: Any) -> Iterable[Tuple[str, Any]]:
        if isinstance(assignments, list):
            for entry in assignments:
                if not isinstance(entry, dict):
                    continue
                control = entry.get("control") or entry.get("key") or entry.get("name")
                if control:
                    yield control, entry
        elif isinstance(assignments, dict):
            for control, payload in assignments.items():
                yield control, payload

    @staticmethod
    def _extract_assignment_metadata(
        control_key: str,
        payload: Any,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if isinstance(payload, dict):
            keycode = payload.get("keycode") or payload.get("code") or payload.get("key")
            control_type = payload.get("type")
            label = payload.get("label")
        else:
            keycode = payload
            control_type = None
            label = None
        return keycode, control_type, label


__all__ = ["PactoTechBoard"]
