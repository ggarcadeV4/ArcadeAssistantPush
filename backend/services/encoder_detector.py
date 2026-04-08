"""
encoder_detector.py
WMI-based arcade encoder board detection for Windows.
Detects Pacto Tech 2000T and 4000T boards by counting XInput child nodes
grouped by USB hub parent. Never uses pyusb — WMI only.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

XBOX_VID = "VID_045E"
XBOX_PID = "PID_028E"


def detect_encoder_boards() -> List[Dict[str, Any]]:
    """
    Detect Pacto Tech 2000T and 4000T encoder boards via WMI topology scan.
    Groups XInput nodes by USB hub parent:
      2 nodes = Pacto 2000T (2-player)
      4 nodes = Pacto 4000T (4-player)
    Returns empty list on any WMI failure — never raises.
    """
    try:
        import wmi  # type: ignore
    except ImportError:
        logger.warning("wmi library not available — encoder board detection skipped")
        return []

    try:
        c = wmi.WMI()
        xinput_nodes = [
            d for d in c.Win32_PnPEntity()
            if d.DeviceID
            and XBOX_VID in d.DeviceID
            and XBOX_PID in d.DeviceID
        ]

        hub_groups: Dict[str, list] = defaultdict(list)
        for node in xinput_nodes:
            parts = node.DeviceID.split("\\")
            parent_key = "\\".join(parts[:-1]) if len(parts) > 1 else node.DeviceID
            hub_groups[parent_key].append(node)

        results = []
        for hub_key, nodes in hub_groups.items():
            count = len(nodes)
            if count == 2:
                board_name = "Pacto Tech 2000T"
                players = 2
            elif count >= 4:
                board_name = "Pacto Tech 4000T"
                players = 4
            else:
                logger.debug(
                    "Hub %s has %d XInput nodes — not a recognized Pacto config",
                    hub_key, count
                )
                continue

            results.append({
                "vid": "0x045e",
                "pid": "0x028e",
                "vid_pid": "0x045e:0x028e",
                "name": board_name,
                "vendor": "Pacto Tech",
                "type": "keyboard_encoder",
                "players": players,
                "detected": True,
                "known": True,
            })
            logger.info("Detected %s (%d players) via WMI hub scan", board_name, players)

        return results

    except Exception as exc:
        logger.warning("WMI encoder board scan failed: %s", exc)
        return []
