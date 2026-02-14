"""Encoder hint resolution from known_encoders.json."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "known_encoders.json"

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_hint_table() -> Dict[str, Dict[str, Any]]:
    if not DATA_PATH.exists():
        logger.debug("known_encoders.json missing at %s", DATA_PATH)
        return {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse %s: %s", DATA_PATH, exc)
        return {}

    hints: Dict[str, Dict[str, Any]] = {}
    for item in payload or []:
        vid = str(item.get("vid") or "").lower()
        pid = str(item.get("pid") or "").lower()
        if not vid or not pid:
            continue
        if not vid.startswith("0x"):
            vid = f"0x{int(vid, 16):04x}"
        if not pid.startswith("0x"):
            pid = f"0x{int(pid, 16):04x}"
        hints[f"{vid}:{pid}"] = item
    return hints


def enrich_with_hints(device: Dict[str, Any]) -> Dict[str, Any]:
    hints = _load_hint_table()
    vid = (device.get("vid") or "").lower()
    pid = (device.get("pid") or "").lower()
    if vid and pid and not vid.startswith("0x"):
        vid = f"0x{vid}"
    if vid and pid and not pid.startswith("0x"):
        pid = f"0x{pid}"
    hint = hints.get(f"{vid}:{pid}")
    if not hint:
        return device

    enriched = dict(device)
    enriched["hint"] = {
        "family": hint.get("family"),
        "vendor": hint.get("vendor") or device.get("manufacturer"),
        "product_name": hint.get("product_name") or device.get("product"),
        "confidence": hint.get("confidence"),
        "notes": hint.get("notes"),
    }
    if hint.get("spoof_xinput"):
        enriched.setdefault("diagnostics", []).append("xinput_spoof_possible")
    return enriched


__all__ = ["enrich_with_hints"]
