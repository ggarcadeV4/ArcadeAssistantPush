"""Shared Pacto / XInput identity rules — single source of truth.

The "Pacto encoder boards spoof an Xbox/XInput VID/PID" reality used to be
encoded across four files: ``usb_detector``, ``routers/chuck_hardware``,
``routers/wizard_mapping``, and ``services/chuck/ai``. They drifted in subtle
ways (one missed ``pactotech``, another missed ``paxco``, normalization
rounded differently). This module is the only place those rules live now.

Adding a new Pacto SKU
----------------------
1. Add its VID/PID to ``SPOOFED_XINPUT_VID_PIDS`` if it spoofs XInput, or
   ignore this step if it has its own native USB descriptor.
2. Add the lowercase identity token prefix to ``PACTO_TOKEN_PREFIXES`` if
   the new SKU's product string introduces a new family token.
3. Add the model code to ``PACTO_XINPUT_BOARD_TYPES`` if the input detection
   service should fall back to the generic XInput capture path for it.
4. Extend ``detect_pacto_model`` with a new model-string branch.

Sibling location (``services/pacto_identity.py``) is intentional — placing
this inside the ``chuck`` package would create an import cycle with
``services/chuck/detection.py``, which already imports from ``usb_detector``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Iterable, Optional


# ---------------------------------------------------------------------------
# Identity tables — single source of truth
# ---------------------------------------------------------------------------

# VID/PID pairs that present as XInput descriptors but are actually Pacto
# encoder boards. Stored as normalized "vvvv:pppp" lowercase strings.
SPOOFED_XINPUT_VID_PIDS: FrozenSet[str] = frozenset({
    "045e:028e",  # Xbox 360 wired XInput descriptor
    "045e:02ea",  # Xbox One XInput descriptor
})

# Token prefixes used to identify a Pacto board from product/manufacturer
# strings. Token-prefix matching avoids false positives like "compactor"
# while still catching ``pacto``, ``pactotech``, ``pacto-tech``,
# ``pacto_2000t``, ``paxco``, etc.
PACTO_TOKEN_PREFIXES: FrozenSet[str] = frozenset({
    "pacto",     # covers pacto, pactotech, pacto_2000t, pacto-tech, ...
    "paxco",     # legacy alias seen in older firmware product strings
    "pacdrive",  # legacy Ultimarc PacDrive identifier still present in
                 # older saved controls.json files; was previously only
                 # recognized by wizard_mapping, missing from chuck/ai
                 # and usb_detector — Wave 2 unifies the set.
})

# board_type values whose input capture must run through the generic XInput
# path, NOT the PactoTech keyboard-mode driver.
PACTO_XINPUT_BOARD_TYPES: FrozenSet[str] = frozenset({
    "pacto_2000t",
    "pacto_4000t",
    "standalone_xinput",
})

# Fields scanned when building a board's identity haystack for token search.
_IDENTITY_FIELDS = (
    "name",
    "board_name",
    "board_type",
    "vendor",
    "manufacturer",
    "manufacturer_string",
    "product_string",
)

_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_vid_pid(vid: Any, pid: Any) -> Optional[str]:
    """Canonical VID/PID pair: lowercase 4-digit hex, colon-separated.

    Returns ``None`` if either component is missing or cannot be cleaned.
    """
    if not vid or not pid:
        return None
    v = str(vid).lower().replace("0x", "").strip()
    p = str(pid).lower().replace("0x", "").strip()
    if not v or not p:
        return None
    return f"{v.zfill(4)}:{p.zfill(4)}"


# ---------------------------------------------------------------------------
# Identity matching
# ---------------------------------------------------------------------------

def build_identity_haystack(board: Dict[str, Any]) -> str:
    """Lowercase concatenation of identity-bearing fields for token search."""
    if not isinstance(board, dict):
        return ""
    return " ".join(str(board.get(key) or "") for key in _IDENTITY_FIELDS).lower()


def _tokenize(haystack: str) -> Iterable[str]:
    return (token for token in _TOKEN_SPLIT_RE.split(haystack) if token)


def looks_like_pacto(board: Dict[str, Any]) -> bool:
    """True if any identity field token matches a Pacto family prefix.

    Token-prefix matching prevents flat substring false positives like
    "compactor" or "subpacton".
    """
    haystack = build_identity_haystack(board)
    if not haystack:
        return False
    for token in _tokenize(haystack):
        for prefix in PACTO_TOKEN_PREFIXES:
            if token.startswith(prefix):
                return True
    return False


def is_pacto_name(name: Optional[str]) -> bool:
    """True if a friendly board name carries a Pacto family token.

    Lighter-weight variant of :func:`looks_like_pacto` for code paths that
    only have a single string instead of a full board dict.
    """
    if not name:
        return False
    for token in _tokenize(name.lower()):
        for prefix in PACTO_TOKEN_PREFIXES:
            if token.startswith(prefix):
                return True
    return False


def is_spoofed_xinput_vid_pid(vid: Any, pid: Any) -> bool:
    """True if the raw VID/PID is in the spoofed XInput set."""
    return normalize_vid_pid(vid, pid) in SPOOFED_XINPUT_VID_PIDS


def is_spoofed_xinput_pacto(name: Optional[str], vid: Any, pid: Any) -> bool:
    """True when a board has been promoted to a Pacto name AND its raw
    VID/PID is the XInput spoof set. Used to subordinate the Microsoft
    descriptor under the friendly Pacto name in operator-facing surfaces.
    """
    if not is_spoofed_xinput_vid_pid(vid, pid):
        return False
    return is_pacto_name(name)


def is_pacto_xinput_board_type(board_type: Optional[str]) -> bool:
    """True if a saved ``board_type`` belongs to the Pacto-XInput set."""
    if not board_type:
        return False
    return str(board_type).lower() in PACTO_XINPUT_BOARD_TYPES


def detect_pacto_model(board: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Identify the Pacto board model from product string tokens.

    Returns a dict with ``name``, ``vendor``, ``board_type``, and (when
    known) ``players`` if a Pacto model is recognized, otherwise ``None``.
    Used by ``usb_detector._apply_arcade_identity_hints`` to promote spoofed
    XInput descriptors into their real Pacto identity. The board dict need
    not have a Pacto identity token already — promotion can fire on either
    a token match OR a spoofed-VID/PID match.
    """
    haystack = build_identity_haystack(board)
    has_pacto_token = looks_like_pacto(board)
    has_spoofed_vid = is_spoofed_xinput_vid_pid(board.get("vid"), board.get("pid"))
    if not (has_pacto_token or has_spoofed_vid):
        return None

    if "4000t" in haystack:
        return {
            "name": "Pacto Tech 4000T",
            "vendor": "Pacto Tech",
            "board_type": "Pacto_4000T",
            "players": 4,
        }
    if "2000t" in haystack:
        return {
            "name": "Pacto Tech 2000T",
            "vendor": "Pacto Tech",
            "board_type": "Pacto_2000T",
            "players": 2,
        }
    if has_pacto_token:
        return {
            "name": "Pacto Tech XInput Encoder",
            "vendor": "Pacto Tech",
            "board_type": "Standalone_XInput",
        }
    return None
