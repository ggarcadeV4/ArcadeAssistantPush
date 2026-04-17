from __future__ import annotations

import configparser
import logging
import os
import re
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PCSX2_RESOURCES = _REPO_ROOT / "LaunchBox" / "Emulators" / "PCSX2" / "resources"
_REDUMP_DB = _PCSX2_RESOURCES / "RedumpDatabase.yaml"
_GAMEINDEX_DB = _PCSX2_RESOURCES / "GameIndex.yaml"


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _stem_without_extensions(path_value: str) -> str:
    raw = Path(str(path_value).replace("\\", "/")).name
    stem = raw
    while True:
        next_stem = Path(stem).stem
        if next_stem == stem:
            return stem
        stem = next_stem


def _candidate_titles(game: Any) -> List[str]:
    candidates: List[str] = []
    for key in ("application_path", "rom_path"):
        value = getattr(game, key, None)
        if value:
            stem = _stem_without_extensions(str(value)).strip()
            if stem:
                candidates.append(stem)
    title = (getattr(game, "title", None) or "").strip()
    if title:
        candidates.append(title)

    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        norm = _normalize_text(candidate)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(candidate)
    return deduped


def _region_terms(game: Any) -> List[str]:
    region = _normalize_text(getattr(game, "region", "") or "")
    if not region:
        return []

    aliases = {
        "north america": ["usa", "canada", "north america"],
        "united states": ["usa", "canada", "north america"],
        "usa": ["usa", "canada", "north america"],
        "europe": ["europe", "pal"],
        "japan": ["japan", "ntsc j"],
        "world": ["world"],
    }
    return aliases.get(region, [region])


@lru_cache(maxsize=1)
def _load_redump_entries() -> List[Dict[str, str]]:
    if not _REDUMP_DB.exists():
        return []

    entries: List[Dict[str, str]] = []
    current_name: Optional[str] = None
    current_serial: Optional[str] = None

    for raw_line in _REDUMP_DB.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if line.startswith("- hashes:"):
            if current_name and current_serial:
                entries.append({"name": current_name, "serial": current_serial})
            current_name = None
            current_serial = None
            continue
        if line.startswith("name: "):
            current_name = line.split(":", 1)[1].strip().strip("'\"")
            continue
        if line.startswith("serial: "):
            current_serial = line.split(":", 1)[1].strip().strip("'\"")

    if current_name and current_serial:
        entries.append({"name": current_name, "serial": current_serial})

    return entries


@lru_cache(maxsize=1)
def _load_gameindex_names() -> Dict[str, str]:
    if not _GAMEINDEX_DB.exists():
        return {}

    results: Dict[str, str] = {}
    current_serial: Optional[str] = None
    for raw_line in _GAMEINDEX_DB.read_text(encoding="utf-8", errors="ignore").splitlines():
        serial_match = re.match(r"^([A-Z0-9-]+):\s*$", raw_line)
        if serial_match:
            current_serial = serial_match.group(1)
            continue
        if current_serial:
            name_match = re.match(r'^\s+name:\s+"?(.*?)"?\s*$', raw_line)
            if name_match:
                results[current_serial] = name_match.group(1).strip()
                current_serial = None
    return results


def resolve_game_serial(game: Any) -> Optional[str]:
    candidates = _candidate_titles(game)
    if not candidates:
        return None

    normalized_candidates = [(_normalize_text(c), c) for c in candidates]
    region_terms = _region_terms(game)

    best_serial: Optional[str] = None
    best_score = -1

    for entry in _load_redump_entries():
        entry_name = entry.get("name", "")
        entry_norm = _normalize_text(entry_name)
        if not entry_norm:
            continue

        for candidate_norm, _ in normalized_candidates:
            score = -1
            if candidate_norm == entry_norm:
                score = 100
            elif entry_norm.startswith(candidate_norm):
                score = 90
            elif candidate_norm in entry_norm:
                score = 80
            elif entry_norm in candidate_norm:
                score = 70

            if score < 0:
                continue

            if region_terms and any(term in entry_norm for term in region_terms):
                score += 5

            if score > best_score:
                best_score = score
                best_serial = entry.get("serial")

    if best_serial:
        return best_serial

    gameindex_names = _load_gameindex_names()
    for candidate_norm, _ in normalized_candidates:
        exact_matches = [
            serial for serial, name in gameindex_names.items()
            if _normalize_text(name) == candidate_norm
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]

    return None


def get_pcsx2_user_root(exe_path: Optional[str] = None) -> Path:
    candidates: List[Path] = []

    for env_name in ("PCSX2_USER_PATH", "PCSX2_SETTINGS_DIR"):
        env_value = (os.getenv(env_name, "") or "").strip()
        if env_value:
            candidates.append(Path(env_value))

    user_profile = (os.getenv("USERPROFILE", "") or "").strip()
    if user_profile:
        candidates.append(Path(user_profile) / "Documents" / "PCSX2")

    home = Path.home()
    candidates.append(home / "Documents" / "PCSX2")

    if exe_path:
        candidates.append(Path(str(exe_path)).parent)

    for candidate in candidates:
        if (candidate / "inis" / "PCSX2.ini").exists() or (candidate / "gamesettings").exists():
            return candidate

    return candidates[0]


def kill_running_pcsx2(timeout_s: float = 5.0) -> bool:
    killed = False
    for image_name in ("pcsx2-qt.exe", "pcsx2.exe"):
        for taskkill in ("taskkill.exe", "taskkill"):
            try:
                result = subprocess.run(
                    [taskkill, "/IM", image_name, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.debug("PCSX2 preflight taskkill failed for %s: %s", image_name, exc)
                break

            output = f"{result.stdout}\n{result.stderr}".lower()
            if result.returncode == 0 or "success" in output:
                killed = True
            break

    deadline = time.time() + max(0.5, timeout_s)
    while time.time() < deadline:
        if not _pcsx2_is_running():
            return killed
        time.sleep(0.2)

    return killed


def _pcsx2_is_running() -> bool:
    for tasklist in ("tasklist.exe", "tasklist"):
        try:
            result = subprocess.run(
                [tasklist, "/FI", "IMAGENAME eq pcsx2-qt.exe"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.debug("PCSX2 preflight tasklist failed: %s", exc)
            return False

        output = f"{result.stdout}\n{result.stderr}".lower()
        return "pcsx2-qt.exe" in output

    return False


def write_upscale_override(game: Any, exe_path: Optional[str], upscale_multiplier: int = 2) -> Optional[Path]:
    serial = resolve_game_serial(game)
    if not serial:
        logger.warning("PCSX2 preflight could not resolve serial for '%s'", getattr(game, "title", "unknown"))
        return None

    user_root = get_pcsx2_user_root(exe_path)
    settings_dir = user_root / "gamesettings"
    settings_dir.mkdir(parents=True, exist_ok=True)

    target = settings_dir / f"{serial}.ini"
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str

    if target.exists():
        config.read(target, encoding="utf-8")

    if not config.has_section("EmuCore/GS"):
        config.add_section("EmuCore/GS")

    config.set("EmuCore/GS", "upscale_multiplier", str(upscale_multiplier))

    with target.open("w", encoding="utf-8") as handle:
        config.write(handle)

    logger.info(
        "PCSX2 preflight wrote per-game upscale override: game='%s' serial=%s path=%s multiplier=%s",
        getattr(game, "title", "unknown"),
        serial,
        target,
        upscale_multiplier,
    )
    return target
