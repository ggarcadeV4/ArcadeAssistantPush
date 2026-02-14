from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import platform

from ..services.diffs import compute_diff, has_changes
from ..services.backup import create_backup
from ..services.policies import require_scope, is_allowed_file
from ..constants.a_drive_paths import LaunchBoxPaths, is_on_a_drive

router = APIRouter(prefix="/api/drive-map")


class DriveMapPreview(BaseModel):
    # Reserved for future filters (e.g., shallow scan)
    shallow: Optional[bool] = True


def _host_env() -> str:
    sysname = platform.system().lower()
    if sysname == "windows":
        return "windows"
    if sysname == "linux":
        # Best-effort WSL check
        try:
            rel = platform.release().lower()
            if "microsoft" in rel:
                return "wsl"
        except Exception:
            pass
        return "linux"
    return sysname


def _list_dirs(p: Path) -> List[str]:
    try:
        if not p.exists() or not p.is_dir():
            return []
        return sorted([d.name for d in p.iterdir() if d.is_dir()])
    except Exception:
        return []


def _list_files(p: Path, pattern: str = "*.exe") -> List[str]:
    try:
        if not p.exists():
            return []
        return sorted([f.name for f in p.glob(pattern) if f.is_file()])
    except Exception:
        return []


def _unify_path(p: Path) -> str:
    """Return a normalized string like A:/path with forward slashes.
    Falls back to str(p) if drive letter unknown.
    """
    s = str(p)
    return s.replace("\\", "/")


def _pick_primary_exe(dir_path: Path) -> Optional[Path]:
    try:
        exe_files = list(dir_path.rglob("*.exe"))
        if not exe_files:
            return None
        # Prefer well-known names first
        preferred = [
            "retroarch.exe", "mame.exe", "pcsx2.exe", "rpcs3.exe", "dolphin.exe",
            "duckstation.exe", "ppsspp.exe", "redream.exe", "xemu.exe"
        ]
        for name in preferred:
            for f in exe_files:
                if f.name.lower() == name:
                    return f
        # Fallback: largest exe
        exe_files.sort(key=lambda f: f.stat().st_size if f.exists() else 0, reverse=True)
        return exe_files[0]
    except Exception:
        return None


def _parse_libretro_info(info_file: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    try:
        with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"')
                data[k] = v
    except Exception:
        return {}

    # supported_extensions is pipe-separated
    exts = [e.strip().lower() for e in data.get("supported_extensions", "").split("|") if e.strip()]
    firmware_count = 0
    try:
        firmware_count = int(data.get("firmware_count", "0").strip() or "0")
    except Exception:
        firmware_count = 0

    firmware: List[str] = []
    for i in range(firmware_count):
        key = f"firmware{i}_path"
        if key in data and data[key]:
            firmware.append(data[key])

    return {
        "zip": "zip" in exts,
        "firmware": firmware,
    }


def build_drive_map() -> Dict[str, Any]:
    """Construct a static drive map snapshot in the requested shape."""
    lb = LaunchBoxPaths

    # LaunchBox platforms (by filename in Data/Platforms)
    platform_files = lb.get_platform_xml_files()
    lb_platforms = [pf.stem for pf in platform_files] if platform_files else []

    # Gather emulator directories from fixed roots
    roots = [lb.LAUNCHBOX_ROOT / "Emulators", lb.EMULATORS_ROOT]
    seen: set[str] = set()
    emulators_arr: List[Dict[str, Any]] = []

    for root in roots:
        if not root.exists():
            continue
        for d in sorted([p for p in root.iterdir() if p.is_dir()]):
            name = d.name
            if name in seen:
                continue
            seen.add(name)

            exe = _pick_primary_exe(d)
            exe_str = _unify_path(exe) if exe else None
            etype = "retroarch" if ("retroarch" in name.lower() or (exe and exe.name.lower() == "retroarch.exe")) else "native"

            entry: Dict[str, Any] = {
                "name": name,
                "exe": exe_str,
                "type": etype,
            }

            if etype == "retroarch":
                cores_dir = d / "cores"
                info_dir = d / "info"
                cores = _list_files(cores_dir, pattern="*libretro*.dll")
                # Map info files to {zip, firmware}
                info_map: Dict[str, Any] = {}
                for info_file in (list(info_dir.glob("*.info")) if info_dir.exists() else []):
                    key = info_file.stem
                    # Normalize key like stella2014_libretro -> stella2014
                    key = key.replace("_libretro", "").replace("-libretro", "").replace("libretro", "")
                    info_map[key] = _parse_libretro_info(info_file)

                entry.update({
                    "cores": cores,
                    "info": info_map,
                })
            else:
                # Minimal supports skeleton (ext list optional; lightgun_profile default false)
                supports: Dict[str, Any] = {"ext": [], "lightgun_profile": False}
                lname = name.lower()
                if "pcsx2" in lname:
                    supports["ext"] = ["bin", "cue", "iso", "chd", "gz"]
                elif "mame" in lname:
                    supports["ext"] = ["zip", "7z"]
                elif "rpcs3" in lname:
                    supports["ext"] = ["iso", "pkg"]
                elif "dolphin" in lname:
                    supports["ext"] = ["iso", "wbfs", "gcm", "ciso", "rvz"]
                entry["supports"] = supports

            emulators_arr.append(entry)

    # ROM roots (as array of paths)
    rom_roots = []
    rom_roots.append(_unify_path(Path(lb.AA_DRIVE_ROOT) / "Console ROMs"))
    rom_roots.append(_unify_path(lb.ROMS_ROOT))

    status = lb.get_status_message()

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "host": _host_env(),
        "is_on_a_drive": is_on_a_drive(),
        "status": status,
        "emulators": emulators_arr,
        "rom_roots": rom_roots,
        "lb_platforms": lb_platforms,
        "lightgun_panels": ["Light Guns"],
    }


def _target_file(drive_root: Path) -> Path:
    return drive_root / "configs" / "drive-map.json"


def _log_change(request: Request, drive_root: Path, action: str, details: Dict[str, Any], backup_path: Optional[Path] = None):
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    device = request.headers.get('x-device-id', 'unknown') if hasattr(request, 'headers') else 'unknown'
    panel = request.headers.get('x-panel', 'unknown') if hasattr(request, 'headers') else 'unknown'
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scope": "drive_map",
        "action": action,
        "details": details,
        "backup_path": str(backup_path) if backup_path else None,
        "device": device,
        "panel": panel,
    }
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")


@router.get("")
async def get_drive_map(request: Request):
    """Return the current configs/drive-map.json if it exists."""
    try:
        drive_root = request.app.state.drive_root
        target = _target_file(drive_root)
        if not target.exists():
            return {"exists": False, "mapping": None}
        with open(target, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"exists": True, "mapping": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_drive_map(request: Request, params: DriveMapPreview):
    try:
        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        # Sanctioned area check
        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        # Build mapping
        mapping = build_drive_map()
        new_content = json.dumps(mapping, indent=2)

        # Current content
        current_content = ""
        if target.exists():
            with open(target, 'r', encoding='utf-8') as f:
                current_content = f.read()

        diff = compute_diff(current_content, new_content, target.name)

        return {
            "target_file": f"configs/{target.name}",
            "has_changes": has_changes(current_content, new_content),
            "diff": diff,
            "mapping": mapping,
            "file_exists": target.exists(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply")
async def apply_drive_map(request: Request, params: DriveMapPreview):
    try:
        # Validate scope header
        require_scope(request, "config")

        drive_root = request.app.state.drive_root
        manifest = request.app.state.manifest
        target = _target_file(drive_root)

        # Sanctioned area check
        if not is_allowed_file(target, drive_root, manifest["sanctioned_paths"]):
            raise HTTPException(status_code=403, detail=f"Target not sanctioned: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)

        # Build mapping and content
        mapping = build_drive_map()
        new_content = json.dumps(mapping, indent=2)

        # Current content (for diff & backup)
        current_content = ""
        if target.exists():
            with open(target, 'r', encoding='utf-8') as f:
                current_content = f.read()

        if not has_changes(current_content, new_content):
            return {
                "status": "no_changes",
                "target_file": f"configs/{target.name}",
                "backup_path": None
            }

        backup_path = None
        if target.exists() and request.app.state.backup_on_write:
            backup_path = create_backup(target, drive_root)

        with open(target, 'w', encoding='utf-8') as f:
            f.write(new_content)

        _log_change(request, drive_root, "apply", {"target": str(target)}, backup_path)

        return {
            "status": "applied",
            "target_file": f"configs/{target.name}",
            "backup_path": str(backup_path) if backup_path else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
async def scan_and_apply(request: Request, params: DriveMapPreview):
    """Alias that regenerates and writes drive-map.json (apply)."""
    return await apply_drive_map(request, params)
