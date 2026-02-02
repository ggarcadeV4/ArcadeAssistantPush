"""
Emulator control endpoints (MVP: RetroArch via network command UDP)

Enable RetroArch network commands in retroarch.cfg:
  network_cmd_enable = "true"
  network_cmd_port = "55355"

Env overrides (optional):
  RA_NETWORK_CMD_ENABLE=true|false
  RA_NETWORK_CMD_HOST=127.0.0.1
  RA_NETWORK_CMD_PORT=55355
"""

from fastapi import APIRouter
from pydantic import BaseModel
import os
import socket
import time

router = APIRouter(prefix="/api/local/emulator", tags=["emulator"])

from backend.services.audit_log import append_pause_event


class PauseRequest(BaseModel):
    emulator: str | None = None


class SaveStateRequest(BaseModel):
    emulator: str | None = None
    slot: int | None = None  # reserved; RetroArch uses current slot for SAVE_STATE


def _ra_send(cmd: str) -> dict:
    enabled = os.getenv("RA_NETWORK_CMD_ENABLE", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        return {"ok": False, "error": "retroarch_network_cmd_disabled"}
    host = os.getenv("RA_NETWORK_CMD_HOST", "127.0.0.1")
    port = int(os.getenv("RA_NETWORK_CMD_PORT", "55355"))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sent = sock.sendto(cmd.encode("utf-8"), (host, port))
        sock.close()
        return {"ok": True, "bytes": sent, "host": host, "port": port, "cmd": cmd}
    except Exception as e:
        return {"ok": False, "error": f"send_failed: {e}", "host": host, "port": port, "cmd": cmd}


@router.post("/pause_toggle")
async def pause_toggle(_: PauseRequest | None = None):
    """Toggle pause in the active emulator (MVP: RetroArch)."""
    res = _ra_send("PAUSE_TOGGLE")
    status = "ok" if res.get("ok") else "error"
    try:
        append_pause_event("retroarch", "pause_toggle", status, res.get("error") or "")
    except Exception:
        pass
    return {"status": status, "method": "retroarch_network_cmd", "details": res, "timestamp": time.time()}


@router.post("/set_slot")
async def set_slot(req: dict = None):
    """Set the active save state slot in RetroArch (0-9)."""
    slot = 0
    if req and "slot" in req:
        slot = max(0, min(9, int(req["slot"])))  # Clamp to 0-9
    
    # RetroArch command: STATE_SLOT <n>
    res = _ra_send(f"STATE_SLOT {slot}")
    status = "ok" if res.get("ok") else "error"
    try:
        append_pause_event("retroarch", "set_slot", status, f"slot={slot}")
    except Exception:
        pass
    return {"status": status, "slot": slot, "method": "retroarch_network_cmd", "details": res, "timestamp": time.time()}


@router.post("/save_state")
async def save_state(_: SaveStateRequest | None = None):
    """Save state in the active emulator (MVP: RetroArch)."""
    res = _ra_send("SAVE_STATE")
    status = "ok" if res.get("ok") else "error"
    try:
        append_pause_event("retroarch", "save", status, res.get("error") or "")
    except Exception:
        pass
    return {"status": status, "method": "retroarch_network_cmd", "details": res, "timestamp": time.time()}


@router.post("/load_state")
async def load_state(_: SaveStateRequest | None = None):
    """Load state in the active emulator (MVP: RetroArch)."""
    res = _ra_send("LOAD_STATE")
    status = "ok" if res.get("ok") else "error"
    try:
        append_pause_event("retroarch", "load", status, res.get("error") or "")
    except Exception:
        pass
    return {"status": status, "method": "retroarch_network_cmd", "details": res, "timestamp": time.time()}


# -----------------------------------------------------------------------------
# Minimal MAME endpoints under /api/local/emulator/mame/* (Windows only)
# -----------------------------------------------------------------------------

@router.post("/mame/pause_toggle")
async def mame_pause_toggle():
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "mame" in title:
                    target_hwnd = hwnd
                    return False
            return True

        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "mame_window_not_found"}

        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        VK_P = 0x50
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_P, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_P, 0, KEYEVENTF_KEYUP, 0)
        try:
            append_pause_event("mame", "pause_toggle", "ok", "")
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        try:
            append_pause_event("mame", "pause_toggle", "error", str(e))
        except Exception:
            pass
        return {"ok": False, "error": str(e)}


@router.post("/mame/save_state")
async def mame_save_state():
    """Save state in MAME (Shift+F7)."""
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "mame" in title:
                    target_hwnd = hwnd
                    return False
            return True
        
        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "mame_window_not_found"}
        
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        # MAME: Shift+F7 to save state
        VK_SHIFT = 0x10
        VK_F7 = 0x76
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_F7, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_F7, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        try:
            append_pause_event("mame", "save_state", "ok", "")
        except Exception:
            pass
        return {"ok": True, "status": "ok"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/mame/load_state")
async def mame_load_state():
    """Load state in MAME (F7)."""
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "mame" in title:
                    target_hwnd = hwnd
                    return False
            return True
        
        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "mame_window_not_found"}
        
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        # MAME: F7 to load state
        VK_F7 = 0x76
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_F7, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_F7, 0, KEYEVENTF_KEYUP, 0)
        try:
            append_pause_event("mame", "load_state", "ok", "")
        except Exception:
            pass
        return {"ok": True, "status": "ok"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# PCSX2 Endpoints (PS2)
# Default hotkeys: F1 = save, F3 = load, F9 = toggle frame limiter
# -----------------------------------------------------------------------------

def _send_key_to_window(window_title_contains: str, vk_code: int, shift: bool = False):
    """Helper to send a keypress to a window by partial title match."""
    if os.name != "nt":
        return {"ok": False, "error": "windows_only"}
    import ctypes
    from ctypes import wintypes
    
    user32 = ctypes.windll.user32
    target_hwnd = wintypes.HWND(0)
    search_term = window_title_contains.lower()
    
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, lparam):
        nonlocal target_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = (buf.value or "").lower()
            if search_term in title:
                target_hwnd = hwnd
                return False
        return True
    
    user32.EnumWindows(_enum_cb, 0)
    if not target_hwnd:
        return {"ok": False, "error": f"window_not_found:{window_title_contains}"}
    
    user32.SetForegroundWindow(target_hwnd)
    time.sleep(0.05)
    
    VK_SHIFT = 0x10
    KEYEVENTF_KEYUP = 0x0002
    
    if shift:
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
        time.sleep(0.02)
    
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    
    if shift:
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
    
    return {"ok": True}


@router.post("/pcsx2/pause_toggle")
async def pcsx2_pause_toggle():
    """Toggle pause in PCSX2 (F9 or ESC)."""
    try:
        # PCSX2-qt uses ESC for pause menu
        res = _send_key_to_window("pcsx2", 0x1B)  # VK_ESCAPE
        status = "ok" if res.get("ok") else "error"
        try:
            append_pause_event("pcsx2", "pause_toggle", status, res.get("error", ""))
        except Exception:
            pass
        return {"status": status, **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/pcsx2/save_state")
async def pcsx2_save_state():
    """Save state in PCSX2 (F1)."""
    try:
        res = _send_key_to_window("pcsx2", 0x70)  # VK_F1
        try:
            append_pause_event("pcsx2", "save_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/pcsx2/load_state")
async def pcsx2_load_state():
    """Load state in PCSX2 (F3)."""
    try:
        res = _send_key_to_window("pcsx2", 0x72)  # VK_F3
        try:
            append_pause_event("pcsx2", "load_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Dolphin Endpoints (GameCube/Wii)
# Default hotkeys: F1 = save, F2 = load, F10 = toggle fullscreen
# -----------------------------------------------------------------------------

@router.post("/dolphin/pause_toggle")
async def dolphin_pause_toggle():
    """Toggle pause in Dolphin (F10 or P)."""
    try:
        res = _send_key_to_window("dolphin", 0x50)  # VK_P (pause)
        try:
            append_pause_event("dolphin", "pause_toggle", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/dolphin/save_state")
async def dolphin_save_state():
    """Save state in Dolphin (F1)."""
    try:
        res = _send_key_to_window("dolphin", 0x70)  # VK_F1
        try:
            append_pause_event("dolphin", "save_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/dolphin/load_state")
async def dolphin_load_state():
    """Load state in Dolphin (F2)."""
    try:
        res = _send_key_to_window("dolphin", 0x71)  # VK_F2
        try:
            append_pause_event("dolphin", "load_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# DuckStation Endpoints (PS1)
# Default hotkeys: F1 = save, F2 = load, Space = pause
# -----------------------------------------------------------------------------

@router.post("/duckstation/pause_toggle")
async def duckstation_pause_toggle():
    """Toggle pause in DuckStation (Space)."""
    try:
        res = _send_key_to_window("duckstation", 0x20)  # VK_SPACE
        try:
            append_pause_event("duckstation", "pause_toggle", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/duckstation/save_state")
async def duckstation_save_state():
    """Save state in DuckStation (F1)."""
    try:
        res = _send_key_to_window("duckstation", 0x70)  # VK_F1
        try:
            append_pause_event("duckstation", "save_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/duckstation/load_state")
async def duckstation_load_state():
    """Load state in DuckStation (F2)."""
    try:
        res = _send_key_to_window("duckstation", 0x71)  # VK_F2
        try:
            append_pause_event("duckstation", "load_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# RPCS3 Endpoints (PS3)
# Default hotkeys: Ctrl+S = save, Ctrl+L = load, Ctrl+P = pause
# -----------------------------------------------------------------------------

@router.post("/rpcs3/pause_toggle")
async def rpcs3_pause_toggle():
    """Toggle pause in RPCS3 (Ctrl+P)."""
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "rpcs3" in title:
                    target_hwnd = hwnd
                    return False
            return True
        
        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "rpcs3_window_not_found"}
        
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        
        VK_CONTROL = 0x11
        VK_P = 0x50
        KEYEVENTF_KEYUP = 0x0002
        
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_P, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_P, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        
        try:
            append_pause_event("rpcs3", "pause_toggle", "ok", "")
        except Exception:
            pass
        return {"ok": True, "status": "ok"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/rpcs3/save_state")
async def rpcs3_save_state():
    """Save state in RPCS3 (Ctrl+S)."""
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "rpcs3" in title:
                    target_hwnd = hwnd
                    return False
            return True
        
        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "rpcs3_window_not_found"}
        
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        
        VK_CONTROL = 0x11
        VK_S = 0x53
        KEYEVENTF_KEYUP = 0x0002
        
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_S, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_S, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        
        try:
            append_pause_event("rpcs3", "save_state", "ok", "")
        except Exception:
            pass
        return {"ok": True, "status": "ok"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/rpcs3/load_state")
async def rpcs3_load_state():
    """Load state in RPCS3 (Ctrl+L)."""
    try:
        if os.name != "nt":
            return {"ok": False, "error": "windows_only"}
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        target_hwnd = wintypes.HWND(0)
        
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").lower()
                if "rpcs3" in title:
                    target_hwnd = hwnd
                    return False
            return True
        
        user32.EnumWindows(_enum_cb, 0)
        if not target_hwnd:
            return {"ok": False, "error": "rpcs3_window_not_found"}
        
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)
        
        VK_CONTROL = 0x11
        VK_L = 0x4C
        KEYEVENTF_KEYUP = 0x0002
        
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_L, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        
        try:
            append_pause_event("rpcs3", "load_state", "ok", "")
        except Exception:
            pass
        return {"ok": True, "status": "ok"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Redream Endpoints (Dreamcast)
# Default hotkeys: F5 = save, F8 = load
# -----------------------------------------------------------------------------

@router.post("/redream/save_state")
async def redream_save_state():
    """Save state in Redream (F5)."""
    try:
        res = _send_key_to_window("redream", 0x74)  # VK_F5
        try:
            append_pause_event("redream", "save_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/redream/load_state")
async def redream_load_state():
    """Load state in Redream (F8)."""
    try:
        res = _send_key_to_window("redream", 0x77)  # VK_F8
        try:
            append_pause_event("redream", "load_state", "ok" if res.get("ok") else "error", "")
        except Exception:
            pass
        return {"status": "ok" if res.get("ok") else "error", **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Emulator Status & Hotkey Endpoints
# -----------------------------------------------------------------------------

# Track currently detected emulator (set by launch flow)
_current_emulator = {"name": "unknown", "paused": False}


@router.get("/status")
async def get_emulator_status():
    """Get status of current emulator (for pause menu overlay)."""
    return {
        "emulator": _current_emulator.get("name", "unknown"),
        "paused": _current_emulator.get("paused", False),
        "timestamp": time.time()
    }


@router.post("/status")
async def set_emulator_status(req: dict = None):
    """Update emulator status (called by launch flow)."""
    global _current_emulator
    if req:
        if "emulator" in req:
            _current_emulator["name"] = req["emulator"]
        if "paused" in req:
            _current_emulator["paused"] = req["paused"]
    return {"status": "ok", "current": _current_emulator}


# Hotkey pressed endpoint (called by AHK global hotkey script)
@router.post("/exit")
async def exit_emulator(req: dict = None):
    """Exit the current emulator/game.
    
    Sends QUIT command to RetroArch or closes MAME window.
    """
    emulator = (req or {}).get("emulator", "unknown")
    
    if emulator == "retroarch":
        # RetroArch: QUIT command
        res = _ra_send("QUIT")
        status = "ok" if res.get("ok") else "error"
        try:
            append_pause_event("retroarch", "exit", status, "")
        except Exception:
            pass
        return {"status": status, "method": "retroarch_quit", "details": res}
    
    elif emulator == "mame":
        # MAME: Send ESC key to quit
        try:
            if os.name != "nt":
                return {"ok": False, "error": "windows_only"}
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            target_hwnd = wintypes.HWND(0)
            
            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _enum_cb(hwnd, lparam):
                nonlocal target_hwnd
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = (buf.value or "").lower()
                    if "mame" in title:
                        target_hwnd = hwnd
                        return False
                return True
            
            user32.EnumWindows(_enum_cb, 0)
            if not target_hwnd:
                return {"ok": False, "error": "mame_window_not_found"}
            
            user32.SetForegroundWindow(target_hwnd)
            time.sleep(0.05)
            VK_ESCAPE = 0x1B
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
            try:
                append_pause_event("mame", "exit", "ok", "")
            except Exception:
                pass
            return {"ok": True, "method": "mame_escape"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    else:
        # Generic: try to kill common emulator processes
        try:
            import subprocess
            emulators_to_kill = [
                "retroarch.exe", "mame.exe", "pcsx2-qt.exe", "rpcs3.exe",
                "Dolphin.exe", "Cemu.exe", "yuzu.exe", "redream.exe"
            ]
            for emu_exe in emulators_to_kill:
                subprocess.run(["taskkill", "/IM", emu_exe, "/F"], 
                             capture_output=True, timeout=2)
            return {"ok": True, "method": "taskkill"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


@router.post("/hotkey/pause")
async def hotkey_pause_pressed(req: dict = None):
    """Handle global hotkey press for pause menu.
    
    This endpoint is called by the aa_pause_overlay.ahk script
    when F1 (or configured hotkey) is pressed.
    """
    global _current_emulator
    
    # Toggle paused state
    _current_emulator["paused"] = not _current_emulator.get("paused", False)
    
    # Log the event
    try:
        append_pause_event(
            _current_emulator.get("name", "unknown"),
            "hotkey_pause",
            "ok",
            f"paused={_current_emulator['paused']}"
        )
    except Exception:
        pass
    
    return {
        "status": "ok",
        "action": "pause_pressed",
        "emulator": _current_emulator.get("name", "unknown"),
        "paused": _current_emulator.get("paused", False),
        "timestamp": time.time()
    }
