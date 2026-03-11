"""
Activity guard to decide whether overlay events should be acted on.

MVP strategy (Windows-first, cross-platform safe):
- If OVERLAY_REQUIRE_EMULATOR=true (default), only allow overlay when a known
  emulator process is running. We detect by scanning the process list via
  platform-appropriate built-ins (no external deps).
  - Windows: tasklist
  - Others: ps -A (best-effort)

Env:
  OVERLAY_REQUIRE_EMULATOR=true|false
  OVERLAY_EMULATOR_PROCESSES=retroarch.exe;mame.exe;pcsx2.exe;dolphin.exe;redream.exe;rpcs3.exe;tekno*;supermodel.exe;model2.exe;duckstation*.exe
"""

from __future__ import annotations

import os
import sys
import subprocess


def _default_emulator_names() -> list[str]:
    return [
        # Frontends (allow overlay in launcher UI too)
        "bigbox.exe", "bigbox",
        "launchbox.exe", "launchbox",
        # Retro
        "retroarch.exe", "retroarch",
        # Arcade
        "mame.exe", "mame64.exe", "mame",
        "supermodel.exe", "model2.exe",
        # Consoles
        "pcsx2.exe", "pcsx2-qtx64-avx2.exe", "pcsx2",
        "duckstation.exe", "duckstation-qt-x64-ReleaseLTCG.exe", "duckstation",
        "dolphin.exe", "dolphin-emu",
        "redream.exe", "redream",
        "rpcs3.exe", "rpcs3",
        # TeknoParrot
        "teknoparrotui.exe", "teknoparrot.exe",
    ]


def _parse_proc_list(output: str) -> list[str]:
    names: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # tasklist CSV or table; ps output; take first token-like segment
        if ',' in line and '"' in line:
            # CSV from tasklist /FO CSV: first field is image name
            try:
                # naive CSV split safe enough for our simple case
                parts = [p.strip().strip('"') for p in line.split(',')]
                if parts:
                    names.append(parts[0].lower())
                    continue
            except Exception:
                pass
        # fallback: whitespace split
        token = line.split()[0]
        names.append(token.lower())
    return names


def _list_process_names() -> list[str]:
    try:
        if sys.platform.startswith('win'):
            # Prefer CSV for robust parsing
            out = subprocess.check_output([
                'tasklist', '/FO', 'CSV', '/NH'
            ], stderr=subprocess.DEVNULL, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return _parse_proc_list(out)
        else:
            out = subprocess.check_output(['ps', '-A'], stderr=subprocess.DEVNULL, text=True)
            return _parse_proc_list(out)
    except Exception:
        return []


import time as _time

# Cache to avoid calling tasklist on every F9 press
_cached_process_names: list[str] = []
_cache_expires_at: float = 0.0
_CACHE_TTL_SECONDS = 3.0


def _list_process_names_cached() -> list[str]:
    """Return process names, using a 3s cache to avoid repeated subprocess calls."""
    global _cached_process_names, _cache_expires_at
    now = _time.monotonic()
    if now < _cache_expires_at:
        return _cached_process_names
    _cached_process_names = _list_process_names()
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return _cached_process_names


def overlay_allowed_now() -> bool:
    """Return True if overlay should activate at this moment."""
    require = os.getenv('OVERLAY_REQUIRE_EMULATOR', 'true').lower() in {'1', 'true', 'yes'}
    if not require:
        return True

    configured = os.getenv('OVERLAY_EMULATOR_PROCESSES', '')
    names = [n.strip().lower() for n in configured.split(';') if n.strip()] or _default_emulator_names()

    running = set(_list_process_names_cached())
    for n in names:
        # simple wildcard support for tekno*
        if n.endswith('*'):
            prefix = n[:-1]
            if any(p.startswith(prefix) for p in running):
                return True
        else:
            if n in running:
                return True
    return False

