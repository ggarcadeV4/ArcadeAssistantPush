"""Discover installed emulators under A:/emulators using the emulator registry."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .emulator_registry import EmulatorPattern, EmulatorRegistry

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60.0

# Base emulator types for health monitoring.
# Variant types (e.g. "mame_gamepad", "retroarch_4x3") are auto-included
# because the filter uses prefix matching against these base names.
_MONITORED_BASE_TYPES = {
    # Console emulators
    "retroarch",
    "dolphin",
    "pcsx2",
    "rpcs3",
    "cemu",
    "citra",
    "yuzu",
    "ppsspp",
    "duckstation",
    "xenia",
    "vita3k",
    "cxbx",
    "mesen",
    "snes9x",
    "epsxe",
    "redream",
    # Arcade & specialty emulators (included for full health monitoring)
    "mame",
    "teknoparrot",
    "model2",
    "supermodel",
    "flycast",
    "demul",
    "hypseus",
}


def _is_monitored_type(emulator_type: str) -> bool:
    """Check if an emulator type (including variants) should be monitored.

    Matches both base types ('mame') and derived variant types ('mame_gamepad')
    using prefix matching against _MONITORED_BASE_TYPES.
    """
    emu_lower = emulator_type.lower()
    for base in _MONITORED_BASE_TYPES:
        if emu_lower == base or emu_lower.startswith(base + "_"):
            return True
    return False


# Backwards-compat alias used by tests
CONSOLE_EMULATOR_TYPES = _MONITORED_BASE_TYPES


@dataclass
class EmulatorInfo:
    """Discovered emulator metadata."""

    name: str
    type: str
    path: Path
    executable: Optional[Path]
    config_path: Optional[Path]
    config_format: str
    enabled: bool = True
    priority: int = 50


class EmulatorDiscoveryService:
    """Service that scans the drive for installed emulators."""

    def __init__(self, drive_root: Path, manifest: Dict[str, Any]) -> None:
        self.drive_root = Path(drive_root)
        self.manifest = manifest or {}
        self.registry = EmulatorRegistry()
        self._cache: Optional[List[EmulatorInfo]] = None
        self._cache_ts: float = 0.0

    def discover_emulators(self, console_only: bool = False) -> List[EmulatorInfo]:
        """Scan multiple emulator directories and return emulator info, honoring cache.

        Args:
            console_only: If True, filter to only console emulators (exclude MAME, arcade, lightgun emulators).
        """
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) < CACHE_TTL_SECONDS:
            logger.debug(
                "Returning cached emulator discovery results (%d entries)",
                len(self._cache),
            )
            cached_results = list(self._cache)
            if console_only:
                cached_results = [info for info in cached_results if _is_monitored_type(info.type)]
            return cached_results

        # Search multiple emulator directories.
        # All paths are derived from self.drive_root (set via AA_DRIVE_ROOT env)
        # so the same code runs on any drive letter without modification.
        project_parent = self.drive_root.parent
        emulator_roots = [
            # Paths relative to drive_root (AA_DRIVE_ROOT — the project folder)
            self.drive_root / "emulators",
            # Paths relative to project parent (sibling directories)
            project_parent / "Emulators",
            project_parent / "Gun Build" / "Emulators",
            project_parent / "LaunchBox" / "Emulators",
        ]
        
        # Also check user Documents for PCSX2-qt configs
        import os
        user_docs = Path(os.path.expanduser("~")) / "Documents"
        if (user_docs / "PCSX2").exists():
            # PCSX2-qt stores configs in user Documents, register it specially
            self._register_user_profile_emulator("pcsx2", user_docs / "PCSX2")

        discovered: List[EmulatorInfo] = []
        # Track seen (type, path) to avoid re-adding exact same install
        seen_paths: set = set()

        for emulator_root in emulator_roots:
            if not emulator_root.exists():
                logger.debug("Emulator root not found: %s", emulator_root)
                continue

            try:
                candidates = sorted(
                    (child for child in emulator_root.iterdir() if child.is_dir()),
                    key=lambda path: path.name.lower(),
                )
            except OSError as exc:
                logger.warning("Failed to enumerate emulator root %s: %s", emulator_root, exc)
                continue

            for emulator_dir in candidates:
                # Skip if we already processed this exact path
                resolved = emulator_dir.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                emulator_type = self.identify_emulator_type(emulator_dir)
                if not emulator_type:
                    continue

                pattern = self.registry.get_pattern(emulator_type)
                if not pattern:
                    logger.debug("No registry pattern found for emulator type '%s'", emulator_type)
                    continue

                # Detect variant suffix from folder name (e.g. "Gamepad", "G-Con45")
                # so that "MAME" and "MAME Gamepad" are distinct entries.
                variant_type, variant_name = self._detect_variant(
                    emulator_dir.name, emulator_type, pattern.display_name
                )

                info = EmulatorInfo(
                    name=variant_name,
                    type=variant_type,
                    path=emulator_dir,
                    executable=self._match_executable(emulator_dir, pattern),
                    config_path=self._resolve_config_path(emulator_dir, pattern),
                    config_format=pattern.config_format,
                    enabled=True,
                    priority=pattern.priority,
                )
                discovered.append(info)
                logger.info("Discovered emulator %s (%s) at %s", variant_name, variant_type, emulator_dir)

        merged = self.merge_with_manifest(discovered)
        merged.sort(key=lambda info: (info.priority, info.name.lower()))

        self._cache = list(merged)
        self._cache_ts = now
        logger.debug("Emulator discovery found %d total entries", len(merged))

        if console_only:
            merged = [info for info in merged if _is_monitored_type(info.type)]
            logger.debug("Filtered to %d console-only emulators", len(merged))

        return list(merged)

    def identify_emulator_type(self, emulator_dir: Path) -> Optional[str]:
        """Identify emulator type based on executable names in the directory."""
        executable_index = self._build_executable_index()
        executables = self._list_executables(emulator_dir)

        for exe in executables:
            emulator_type = executable_index.get(exe.name.lower())
            if emulator_type:
                logger.info(
                    "Identified emulator directory %s as %s via %s",
                    emulator_dir.name,
                    emulator_type,
                    exe.name,
                )
                return emulator_type

        logger.info("Unknown emulator directory (no matching executables): %s", emulator_dir)
        return None

    def merge_with_manifest(self, discovered: List[EmulatorInfo]) -> List[EmulatorInfo]:
        """Merge discovered emulators with manifest overrides."""
        manifest_entries = self.manifest.get("emulators")
        if not isinstance(manifest_entries, dict):
            return discovered

        merged: Dict[str, EmulatorInfo] = {info.type: info for info in discovered}

        for emulator_type, overrides in manifest_entries.items():
            if not isinstance(overrides, dict):
                continue

            info = merged.get(emulator_type)
            if info is None:
                pattern = self.registry.get_pattern(emulator_type)
                name = str(
                    overrides.get("name")
                    or overrides.get("title")
                    or (pattern.display_name if pattern else emulator_type)
                )
                path = (
                    self._resolve_path(
                        overrides.get("path")
                        or overrides.get("directory")
                        or overrides.get("root")
                    )
                    or (self.drive_root / "emulators" / emulator_type)
                )
                executable = self._resolve_path(overrides.get("exe") or overrides.get("executable"))
                config_override = (
                    overrides.get("config_path")
                    or overrides.get("config")
                    or overrides.get("cfg")
                    or overrides.get("ini")
                )
                config_path = (
                    self._resolve_path(config_override)
                    if config_override
                    else self._resolve_config_path(path, pattern)
                    if pattern
                    else None
                )
                config_format = str(
                    overrides.get("config_format")
                    or (pattern.config_format if pattern else "ini")
                )
                enabled = bool(overrides.get("enabled")) if "enabled" in overrides else True
                priority_value = overrides.get("priority")
                priority = self._coerce_priority(priority_value, pattern)

                info = EmulatorInfo(
                    name=name,
                    type=emulator_type,
                    path=path,
                    executable=executable,
                    config_path=config_path,
                    config_format=config_format,
                    enabled=enabled,
                    priority=priority,
                )
                merged[emulator_type] = info
                logger.info("Manifest adds emulator entry for %s at %s", emulator_type, path)
                continue

            if "exe" in overrides or "executable" in overrides:
                exe_value = overrides.get("exe") or overrides.get("executable")
                resolved_exe = self._resolve_path(exe_value)
                if resolved_exe is not None:
                    info.executable = resolved_exe

            if any(key in overrides for key in ("config_path", "config", "cfg", "ini")):
                config_value = (
                    overrides.get("config_path")
                    or overrides.get("config")
                    or overrides.get("cfg")
                    or overrides.get("ini")
                )
                resolved_config = self._resolve_path(config_value)
                if resolved_config is not None:
                    info.config_path = resolved_config

            if "enabled" in overrides:
                info.enabled = bool(overrides.get("enabled"))

            if "priority" in overrides:
                try:
                    info.priority = int(overrides.get("priority"))
                except (TypeError, ValueError):
                    logger.warning("Invalid priority override for %s", emulator_type)

            if "name" in overrides or "title" in overrides:
                info.name = str(overrides.get("name") or overrides.get("title") or info.name)

            if "config_format" in overrides:
                info.config_format = str(overrides.get("config_format"))

        return list(merged.values())

    def invalidate_cache(self) -> None:
        """Invalidate the discovery cache."""
        self._cache = None
        self._cache_ts = 0.0
        logger.debug("Emulator discovery cache invalidated")

    # ── Variant detection ──────────────────────────────────────────────
    # Known folder-name suffixes that indicate a distinct emulator variant.
    # Each variant gets its own type ID so it isn't merged with the base install.
    _VARIANT_SUFFIXES = [
        ("Gamepad",   "gamepad",  "(Gamepad)"),
        ("G-Con45",   "gcon45",   "(G-Con45)"),
        ("TC",        "tc",       "(Time Crisis)"),
        ("4x3",       "4x3",      "(4:3)"),
        ("Win64",     "win64",    "(Win64)"),
        (".945",      "945",      "(v0.945)"),
        ("LE3",       "le3",      "(LE3)"),
        ("Latest",    "latest",   "(Latest)"),
        ("Eden",      "eden",     "(Eden)"),
        ("5.0",       "50",       "(5.0)"),
        ("BraveFF",   "braveff",  "(BraveFF)"),
        ("Silent Scope", "silentscope", "(Silent Scope)"),
        ("VC3",       "vc3",      "(VC3)"),
    ]

    @staticmethod
    def _detect_variant(
        folder_name: str,
        base_type: str,
        base_display_name: str,
    ) -> tuple:
        """Detect if a folder represents a variant (e.g. 'MAME Gamepad').

        Returns (variant_type, variant_display_name).  If no variant suffix
        is found, returns the originals unchanged.
        """
        for suffix, type_tag, label in EmulatorDiscoveryService._VARIANT_SUFFIXES:
            if suffix.lower() in folder_name.lower() and suffix.lower() not in base_type.lower():
                variant_type = f"{base_type}_{type_tag}"
                variant_name = f"{base_display_name} {label}"
                return variant_type, variant_name
        return base_type, base_display_name

    def _register_user_profile_emulator(self, emulator_type: str, config_dir: Path) -> None:
        """Register an emulator that stores configs in user profile (e.g., Documents folder).
        
        This handles emulators like PCSX2-qt that don't store configs in the emulator folder.
        """
        if not hasattr(self, "_user_profile_emulators"):
            self._user_profile_emulators: Dict[str, Path] = {}
        self._user_profile_emulators[emulator_type] = config_dir
        logger.info("Registered user-profile emulator %s at %s", emulator_type, config_dir)

    def _build_executable_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for pattern in self.registry.get_all_patterns().values():
            for exe_name in pattern.executable_patterns:
                index[Path(exe_name).name.lower()] = pattern.type
        return index

    def _list_executables(self, emulator_dir: Path) -> List[Path]:
        try:
            return [
                child
                for child in emulator_dir.iterdir()
                if child.is_file() and child.suffix.lower() == ".exe"
            ]
        except OSError as exc:
            logger.warning("Failed to list executables in %s: %s", emulator_dir, exc)
            return []

    def _match_executable(self, emulator_dir: Path, pattern: EmulatorPattern) -> Optional[Path]:
        executables = self._list_executables(emulator_dir)
        pattern_names = {Path(name).name.lower() for name in pattern.executable_patterns}

        for exe in executables:
            if exe.name.lower() in pattern_names:
                return exe

        for candidate in pattern.executable_patterns:
            candidate_path = emulator_dir / candidate
            if candidate_path.exists():
                return candidate_path

        return None

    def _resolve_config_path(
        self,
        emulator_dir: Path,
        pattern: Optional[EmulatorPattern],
    ) -> Optional[Path]:
        if not pattern or not pattern.config_path_pattern:
            return None
        config_path = emulator_dir / Path(pattern.config_path_pattern)
        return config_path

    def _resolve_path(self, value: Optional[Any]) -> Optional[Path]:
        if not value:
            return None
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = self.drive_root / candidate
        return candidate

    def _coerce_priority(
        self,
        value: Optional[Any],
        pattern: Optional[EmulatorPattern],
    ) -> int:
        if isinstance(value, int):
            return value
        try:
            if isinstance(value, str):
                return int(value.strip())
        except (TypeError, ValueError):
            pass
        return pattern.priority if pattern else 50
