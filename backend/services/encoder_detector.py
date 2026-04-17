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
    Detect arcade encoder boards via WMI XInput-topology scan.

    Groups present XInput nodes by USB hub parent and infers the logical
    board identity from the node count per hub:
      - 2 nodes on a hub → ``Pacto Tech 2000T`` (2-player)
      - 4+ nodes on a hub → ``Pacto Tech 4000T`` (4-player)
      - any other count (1, 3, 5, ...) → ``Standalone XInput`` (single
        Xbox-style controller or unrecognised topology)

    This is the canonical, side-effect-free Chuck topology helper. The
    canonical board lane (``usb_detector.detect_usb_devices`` →
    ``detect_arcade_boards``) calls this and merges the result into the
    same canonical board list it already returns, so the live Chuck panel
    receives a topology-enriched ``name`` and ``board_type`` instead of a
    generic spoofed-XInput entry.

    Returns:
        List of canonical board dictionaries with the same shape as
        ``usb_detector._build_device_info`` plus the topology fields
        ``board_type``, ``players``, ``parent_hub``, ``xinput_nodes``.
        Returns ``[]`` on any WMI failure (never raises) so callers in
        the canonical lane can degrade gracefully when ``wmi`` is missing.
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
                board_type = "Pacto_2000T"
                players = 2
            elif count >= 4:
                board_name = "Pacto Tech 4000T"
                board_type = "Pacto_4000T"
                players = 4
            else:
                # 1 node or 3 nodes — a single XInput controller or an
                # unrecognised hub layout. Surface it as Standalone_XInput
                # so the canonical lane still emits a topology-enriched
                # identity instead of a generic spoofed encoder entry.
                # (Mirrors services/chuck/input_detector.detect_pacto_topology.)
                board_name = "Standalone XInput Controller"
                board_type = "Standalone_XInput"
                players = count
                logger.debug(
                    "Hub %s has %d XInput nodes — Standalone_XInput",
                    hub_key, count,
                )

            results.append({
                # vid_pid uses the canonical "vvvv:pppp" lowercase format
                # (no 0x prefix) so it dedupes against usb_detector entries.
                "vid": "0x045e",
                "pid": "0x028e",
                "vid_pid": "045e:028e",
                "name": board_name,
                "vendor": "Pacto Tech",
                "type": "keyboard_encoder",
                # Topology-enriched identity fields (additive — older
                # consumers ignore them; the live Chuck board pill picks
                # up the richer name today, the GUI can opt into the
                # rest later without any backend churn).
                "board_type": board_type,
                "players": players,
                "parent_hub": hub_key,
                "xinput_nodes": count,
                "detected": True,
                "known": True,
                "source": "encoder_detector_topology",
            })
            logger.info(
                "Detected %s (%d players, hub=%s) via WMI topology scan",
                board_name, players, hub_key,
            )

        return results

    except Exception as exc:
        logger.warning("WMI encoder board scan failed: %s", exc)
        return []
