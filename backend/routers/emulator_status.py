from __future__ import annotations

import os
import socket
import subprocess
from typing import Optional, Tuple

from fastapi import APIRouter

from backend.services.audit_log import append_pause_event

router = APIRouter(prefix="/api/local/emulator", tags=["emulator-status"])


def _list_processes() -> list[tuple[str, int]]:
    """Return list of (image_name_lower, pid) using Windows tasklist.

    On non-Windows, returns empty list.
    """
    if not os.name == "nt":
        return []
    try:
        out = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True)
    except Exception:
        return []
    rows: list[tuple[str, int]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2:
            name = (parts[0] or "").lower()
            try:
                pid = int((parts[1] or "0"))
            except Exception:
                pid = 0
            rows.append((name, pid))
    return rows


def _detect_emulator() -> tuple[str, Optional[int]]:
    """Detect a known emulator by process image name.

    Returns (emulator_name, pid) with emulator_name in {'retroarch','mame','unknown'}
    """
    procs = _list_processes()
    # RetroArch
    for name, pid in procs:
        if name == "retroarch.exe" or name == "retroarch":
            return "retroarch", pid
    # MAME
    for name, pid in procs:
        if name in {"mame.exe", "mame64.exe", "mame"}:
            return "mame", pid
    return "unknown", None


def _retroarch_paused_udp(host: str = None, port: int = None) -> Optional[bool]:
    """Best-effort RetroArch paused status via UDP network_cmd.

    If environment RA_NETWORK_CMD_ENABLE is not true, returns None.
    Attempts a simple STATUS query (implementation-dependent). If not supported,
    returns None and the caller should treat paused as False.
    """
    enabled = (os.getenv("RA_NETWORK_CMD_ENABLE", "false").lower() in {"1", "true", "yes"})
    if not enabled:
        return None
    host = host or os.getenv("RA_NETWORK_CMD_HOST", "127.0.0.1")
    try:
        port = int(port or int(os.getenv("RA_NETWORK_CMD_PORT", "55355")))
    except Exception:
        port = 55355
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        # Try a generic status probe; many builds ignore unknown commands, so guard errors.
        probe = b"GET_STATUS"
        sock.sendto(probe, (host, port))
        # Non-blocking best-effort receive
        try:
            data, _ = sock.recvfrom(1024)
            text = (data or b"").decode("utf-8", errors="ignore").lower()
            if "paused" in text:
                # crude parse, treat presence as paused indicator
                return True
            if "running" in text:
                return False
        except Exception:
            pass
        return None
    except Exception:
        return None


def _window_title_from_pid(pid: Optional[int]) -> Optional[str]:
    if not pid or os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        titles: list[str] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            _pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid))
            if _pid.value == pid and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    titles.append(buf.value)
            return True

        user32.EnumWindows(_enum_cb, 0)
        return titles[0] if titles else None
    except Exception:
        return None


@router.get("/status")
async def emulator_status():
    emu, pid = _detect_emulator()
    paused = False
    if emu == "retroarch":
        st = _retroarch_paused_udp()
        if st is not None:
            paused = bool(st)
    title = _window_title_from_pid(pid)
    result = {
        "emulator": emu,
        "paused": bool(paused),
        "pid": pid,
        "window_title": title or "",
    }
    append_pause_event(emu, "status", "ok")
    return result

