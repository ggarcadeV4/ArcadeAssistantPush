from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.constants.a_drive_paths import LaunchBoxPaths, LB_PLATFORMS_GLOB
from backend.services.launchbox_parser import parser

_lock = threading.RLock()
_last_loaded_at: float = 0.0
_last_signature: str = ""
_debounce_timer: Optional[threading.Timer] = None
_debounce_until: float = 0.0


def _iter_platform_xmls() -> List[Path]:
    """Return sorted list of platform XML file Paths.

    Prefer LaunchBoxPaths API; fall back to glob string if needed.
    """
    try:
        files = LaunchBoxPaths.get_platform_xml_files()
        if files:
            return sorted(files)
    except Exception:
        pass
    # Fallback: LB_PLATFORMS_GLOB may be absolute; use glob from pathlib
    try:
        # Path().glob with absolute patterns on Windows can be unreliable; use glob module instead
        import glob

        return sorted(Path(p) for p in glob.glob(LB_PLATFORMS_GLOB))
    except Exception:
        return []


def _compute_signature() -> str:
    """Hash filenames + sizes + mtimes for all platform XMLs."""
    h = hashlib.sha1()
    for p in _iter_platform_xmls():
        try:
            st = p.stat()
            h.update(str(p).encode("utf-8", errors="ignore"))
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime)).encode())
        except Exception:
            # Ignore inaccessible files
            continue
    return h.hexdigest()


def status() -> Dict[str, Any]:
    with _lock:
        # Size derived from parser cache
        size = 0
        try:
            size = len(parser.get_all_games())
        except Exception:
            size = 0
        return {
            "size": size,
            "last_loaded_at": int(_last_loaded_at),
            "signature": _last_signature,
        }


def _reload_from_xml_unconditional() -> None:
    """Force a full XML parse, bypassing disk cache."""
    # The parser exposes internal methods; safe to call here within our own process
    try:
        parser._parse_all_platforms()  # type: ignore[attr-defined]
        # Persist a fresh disk cache for faster subsequent startups
        from backend.constants.a_drive_paths import is_on_a_drive

        if is_on_a_drive():
            try:
                parser._save_parser_cache_to_disk()  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        # As a fallback, attempt normal initialize (may use disk cache)
        try:
            parser.initialize()
        except Exception:
            pass


def force_reload() -> Dict[str, Any]:
    """Reload from XML unconditionally."""
    global _last_loaded_at, _last_signature
    with _lock:
        _reload_from_xml_unconditional()
        _last_loaded_at = time.time()
        _last_signature = _compute_signature()
        return status()


def _do_reload_after_debounce(expected_sig: Optional[str] = None) -> None:
    global _debounce_timer, _debounce_until, _last_signature, _last_loaded_at
    with _lock:
        try:
            _debounce_timer = None
            _debounce_until = 0.0
            # If an expected signature was passed and current matches, proceed; if not, compute again
            current_sig = _compute_signature()
            if expected_sig and current_sig != expected_sig:
                # Files changed again during debounce window; proceed anyway
                pass
            _reload_from_xml_unconditional()
            _last_loaded_at = time.time()
            _last_signature = _compute_signature()
        except Exception:
            # Never raise from background
            pass


def revalidate() -> Dict[str, Any]:
    """Reload only if underlying XML signature changed."""
    global _last_loaded_at, _last_signature
    with _lock:
        before = {"signature": _last_signature, "size": len(parser.get_all_games() or [])}
        sig = _compute_signature()
        if sig != _last_signature:
            # Manual revalidate: perform immediate reload to satisfy acceptance criteria
            _reload_from_xml_unconditional()
            _last_loaded_at = time.time()
            _last_signature = _compute_signature()
            after = status()
            return {"before": before, "after": after, "reloaded": True}

        after = status()
        return {"before": before, "after": after, "reloaded": False}


def get_games() -> List[Any]:
    """Return cached games, initializing if necessary."""
    with _lock:
        # Ensure parser is initialized at least once
        try:
            games = parser.get_all_games()
        except Exception:
            games = []
        if not games:
            _reload_from_xml_unconditional()
            games = parser.get_all_games() or []
        return list(games)


def _schedule_debounced_reload(sig: str) -> None:
    """Schedule a debounced reload for background watcher events."""
    global _debounce_timer, _debounce_until
    now = time.time()
    try:
        debounce_secs = int(os.getenv("AA_LB_DEBOUNCE_SECS", "10"))
    except Exception:
        debounce_secs = 10
    # Respect minimum reload cadence as a backstop
    try:
        min_reload_secs = int(os.getenv("AA_LB_MIN_RELOAD_SECS", "10"))
    except Exception:
        min_reload_secs = 10
    earliest = _last_loaded_at + max(0, min_reload_secs)
    delay = max(debounce_secs, int(max(0, earliest - now)))

    if _debounce_timer is not None:
        # Already scheduled; let existing timer fire
        return

    _debounce_until = now + delay
    t = threading.Timer(delay, _do_reload_after_debounce, kwargs={"expected_sig": sig})
    t.daemon = True
    t.start()
    globals()["_debounce_timer"] = t


def _auto_revalidate_loop(poll_secs: int) -> None:
    last_sig = None
    while True:
        try:
            sig = _compute_signature()
            if last_sig is None:
                # Initialize module state to current signature on first loop
                with _lock:
                    global _last_signature
                    _last_signature = sig
                last_sig = sig
            elif sig != last_sig:
                _schedule_debounced_reload(sig)
                last_sig = sig
        except Exception:
            # Never crash the thread; just continue polling
            pass
        time.sleep(max(1, poll_secs))


def start_auto_revalidate_if_enabled() -> None:
    """Start background poller when AA_LB_AUTO_REVALIDATE is enabled."""
    enabled = (os.getenv("AA_LB_AUTO_REVALIDATE", "0").lower() in {"1", "true", "yes"})
    if not enabled:
        return
    try:
        poll_secs = int(os.getenv("AA_LB_POLL_SECS", "10"))
    except Exception:
        poll_secs = 10
    t = threading.Thread(target=_auto_revalidate_loop, args=(poll_secs,), daemon=True)
    t.start()
