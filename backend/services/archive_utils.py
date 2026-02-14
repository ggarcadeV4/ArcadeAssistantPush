from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import tempfile
import gzip

from backend.constants.runtime_paths import aa_tmp_dir
from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)


ARCHIVE_EXTS = {".zip", ".7z", ".gz"}
PS2_IMAGE_EXTS = {".iso", ".bin", ".cue", ".img", ".chd"}
ALT_EXTS = [".iso", ".cue", ".bin", ".img", ".chd", ".7z", ".zip", ".gz"]


def _is_archive(p: Path) -> bool:
    try:
        return p.suffix.lower() in ARCHIVE_EXTS
    except Exception:
        return False


def _first_ps2_image_in(folder: Path) -> Optional[Path]:
    """Choose .iso first, else any supported image. If multiple, choose largest.

    Checks top-level first, then falls back to recursive search.
    """
    try:
        candidates: List[Path] = []
        for ext in [".iso", ".cue", ".bin", ".img", ".chd"]:
            candidates.extend(folder.glob(f"*{ext}"))
        if not candidates:
            for ext in [".iso", ".cue", ".bin", ".img", ".chd"]:
                candidates.extend(folder.rglob(f"*{ext}"))
        if not candidates:
            return None
        iso_first = [p for p in candidates if p.suffix.lower() == ".iso"]
        if iso_first:
            return iso_first[0]
        return max(candidates, key=lambda p: p.stat().st_size if p.exists() else 0)
    except Exception:
        return None


def _extract_zip(archive: Path, out_dir: Path) -> bool:
    try:
        with zipfile.ZipFile(archive, 'r') as zf:
            zf.extractall(out_dir)
        return True
    except Exception as e:
        logger.error("Failed to extract zip %s: %s", archive, e)
        return False


def _find_7z_exe() -> Optional[Path]:
    """Find a 7-Zip CLI executable via env var, PATH, or drive-relative Tools folder."""
    # 1. Check env var first (SEVEN_ZIP_PATH)
    env_path = os.environ.get("SEVEN_ZIP_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    
    # 2. Check PATH via shutil.which (drive-letter agnostic)
    for name in ("7z", "7z.exe", "7zz", "7za"):
        w = shutil.which(name)
        if w and Path(w).exists():
            return Path(w)
    
    # 3. Check drive-relative Tools folder (Golden Drive compliant)
    try:
        drive_root = get_drive_root(allow_cwd_fallback=True)
        tools_7z = drive_root / "Tools" / "7zip" / "7z.exe"
        if tools_7z.exists():
            return tools_7z
    except Exception:
        pass
    
    return None


def _extract_7z(archive: Path, out_dir: Path) -> bool:
    """Extract a 7z file using py7zr if available; otherwise shell out to 7z/7zz."""
    # Try py7zr first
    try:
        import py7zr  # type: ignore
        try:
            with py7zr.SevenZipFile(archive, mode='r') as z:
                z.extractall(path=out_dir)
            return True
        except Exception as e:
            logger.warning("py7zr failed to extract %s: %s", archive, e)
    except Exception:
        logger.debug("py7zr not installed; falling back to 7z executable if available")

    # Fallback to 7z if present
    seven = _find_7z_exe()
    if not seven:
        logger.warning("No 7z tool available for %s (install py7zr or 7-Zip)", archive)
        return False
    try:
        cmd = [str(seven), "x", "-y", f"-o{str(out_dir)}", str(archive)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.error("7z extraction failed for %s: %s", archive, e)
        return False


def prepare_ps2_image(rom_path: Path) -> tuple[Optional[Path], Optional[callable]]:
    """If rom_path is an archive (.zip/.7z), extract to a temp dir and return (image_path, cleanup).

    Returns (None, None) when no extraction performed or on failure.
    """
    try:
        p = Path(rom_path)
    except Exception:
        return None, None

    if not _is_archive(p):
        return None, None

    # Create a run-specific directory under AA temp
    base = aa_tmp_dir()
    # Per-run subfolder (rom stem helps clarity)
    run_dir = base / (p.stem or "ps2")
    # Ensure unique if exists
    idx = 1
    candidate = run_dir
    while candidate.exists() and idx < 1000:
        candidate = base / f"{p.stem}-{idx}"
        idx += 1
    out_dir = candidate
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = False
    ext = p.suffix.lower()
    if ext == ".zip":
        ok = _extract_zip(p, out_dir)
    elif ext == ".7z":
        ok = _extract_7z(p, out_dir)

    if not ok:
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass
        return None, None

    img = _first_ps2_image_in(out_dir)
    if not img:
        logger.warning("No disc image found after extraction: %s", out_dir)
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass
        return None, None

    def _cleanup():
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
            logger.info("Cleaned extracted temp: %s", out_dir)
        except Exception as e:
            logger.warning("Failed to cleanup temp %s: %s", out_dir, e)

    return img, _cleanup


@dataclass
class ExtractResult:
    extracted_path: Optional[Path]
    temp_root: Optional[Path]
    used_tool: Optional[str]


def extract_if_archive(rom_path: Path, tmp_base: Path) -> ExtractResult:
    """
    If rom_path is an archive (.7z/.zip), extract into a temp dir under tmp_base
    and return the contained PS2 image path. Otherwise, return original path.
    """
    try:
        p = Path(rom_path)
    except Exception:
        return ExtractResult(None, None, None)

    if not _is_archive(p):
        return ExtractResult(p, None, None)

    # Create unique subdir under tmp_base
    run_dir = tmp_base / (p.stem or "ps2")
    i = 1
    while run_dir.exists() and i < 1000:
        run_dir = tmp_base / f"{p.stem}-{i}"
        i += 1
    run_dir.mkdir(parents=True, exist_ok=True)

    used = None
    ok = False
    ext = p.suffix.lower()
    if ext == ".zip":
        ok = _extract_zip(p, run_dir)
        used = "zipfile" if ok else None
    elif ext == ".7z":
        # Prefer 7z CLI first
        seven = _find_7z_exe()
        if seven:
            try:
                cmd = [str(seven), "x", "-y", str(p), f"-o{str(run_dir)}"]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(f"7z extraction failed ({proc.returncode}): {proc.stderr.strip()[:200]}")
                ok = True
                used = seven.name
            except Exception as e:
                logger.error("7z extraction failed for %s: %s", p, e)
                ok = False
        if not ok:
            # Fallback to py7zr if available
            try:
                import py7zr  # type: ignore
                with py7zr.SevenZipFile(p, mode='r') as z:
                    z.extractall(path=run_dir)
                ok = True
                used = "py7zr"
            except Exception as e:
                raise RuntimeError(f".7z extraction requires 7z.exe in PATH or optional py7zr: {e}")
    elif ext == ".gz":
        # Stream-decompress .gz to ISO
        try:
            safe_stem = p.stem.replace(" ", "_")
            out_iso = run_dir / (p.stem + ".iso")
            with gzip.open(p, "rb") as fin, open(out_iso, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            ok = True
            used = "gzip"
        except Exception as e:
            logger.error("gzip extraction failed for %s: %s", p, e)
            ok = False

    if not ok:
        try:
            shutil.rmtree(run_dir, ignore_errors=True)
        except Exception:
            pass
        return ExtractResult(None, None, None)

    img = _first_ps2_image_in(run_dir)
    if not img:
        logger.warning("No disc image found after extraction: %s", run_dir)
        try:
            shutil.rmtree(run_dir, ignore_errors=True)
        except Exception:
            pass
        return ExtractResult(None, None, None)

    return ExtractResult(img, run_dir, used)


def resolve_rom_path(requested: Path) -> Tuple[Optional[Path], Optional[str]]:
    """
    If 'requested' exists, return (requested, 'exact').
    Else try same directory, same stem, any ALT_EXTS (priority by order; ties: largest size).
    Returns (path, 'resolved') or (None, 'missing').
    """
    try:
        if requested.exists():
            return requested, "exact"
        parent = requested.parent
        stem = requested.stem
        if not parent.exists():
            return None, "missing"
        candidates: List[Path] = []
        for ext in ALT_EXTS:
            candidates.extend(parent.glob(f"{stem}{ext}"))
        if not candidates:
            return None, "missing"
        # prefer .iso, else largest
        iso_first = [p for p in candidates if p.suffix.lower() == ".iso"]
        if iso_first:
            return iso_first[0], "resolved"
        best = max(candidates, key=lambda pp: pp.stat().st_size if pp.exists() else 0)
        return best, "resolved"
    except Exception:
        return None, "missing"
