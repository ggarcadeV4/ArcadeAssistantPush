#!/usr/bin/env python3
"""
Wire RetroArch MAME per-game configs to per-ROM bezel overlays.

This script scans `A:\Emulators\RetroArch\config\MAME\` for per-game config
files, derives likely ROM shortnames from each config filename, and rewrites
matching configs to point at `overlays/ArcadeBezels/<rom>.cfg`.

Usage:
    python scripts/wire_mame_bezels.py --dry-run
    python scripts/wire_mame_bezels.py
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


AA_DRIVE_ROOT = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\"))
RETROARCH_ROOT = AA_DRIVE_ROOT / "Emulators" / "RetroArch"
MAME_CONFIG_DIR = RETROARCH_ROOT / "config" / "MAME"
ARCADE_BEZELS_DIR = RETROARCH_ROOT / "overlays" / "ArcadeBezels"
FALLBACK_OVERLAY = "A:/Emulators/RetroArch/overlays/MAME-Horizontal.cfg"
TARGET_OVERLAY_PREFIX = "A:/Emulators/RetroArch/overlays/ArcadeBezels"
REPORT_PATH = Path(r"A:\Arcade Assistant Local\logs\bezel_wiring_report.txt")


@dataclass
class ProcessResult:
    rom_name: str
    matched: bool
    matched_overlay: str | None = None
    modified: bool = False


def derive_candidates(file_name: str) -> list[str]:
    """Derive likely MAME shortname candidates from a config filename."""
    stem = Path(file_name).stem
    base = re.sub(r"\s*\([^)]*\)", "", stem).strip().lower()
    hyphenated = base.replace(" ", "")
    no_hyphen = hyphenated.replace("-", "")

    candidates: list[str] = []
    for candidate in (hyphenated, no_hyphen):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def find_matching_overlay(cfg_path: Path) -> str | None:
    """Return the matching ArcadeBezels overlay stem if found."""
    for candidate in derive_candidates(cfg_path.name):
        overlay_cfg = ARCADE_BEZELS_DIR / f"{candidate}.cfg"
        if overlay_cfg.exists():
            return candidate
    return None


def detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def rewrite_overlay_settings(text: str, overlay_stem: str) -> tuple[str, bool]:
    """
    Rewrite or append overlay settings.

    Returns the updated text and whether content changed.
    """
    newline = detect_newline(text)
    lines = text.splitlines()
    target_overlay = f'input_overlay = "{TARGET_OVERLAY_PREFIX}/{overlay_stem}.cfg"'
    target_enable = 'input_overlay_enable = "true"'

    overlay_idx = None
    enable_idx = None

    for idx, line in enumerate(lines):
        if re.match(r"^\s*input_overlay\s*=", line):
            if overlay_idx is None:
                overlay_idx = idx
        elif re.match(r"^\s*input_overlay_enable\s*=", line):
            if enable_idx is None:
                enable_idx = idx

    changed = False

    if overlay_idx is not None:
        if lines[overlay_idx] != target_overlay:
            lines[overlay_idx] = target_overlay
            changed = True
    else:
        lines.append(target_overlay)
        changed = True

    if enable_idx is not None:
        if lines[enable_idx] != target_enable:
            lines[enable_idx] = target_enable
            changed = True
    else:
        lines.append(target_enable)
        changed = True

    updated = newline.join(lines)
    if text.endswith(("\n", "\r\n")):
        updated += newline

    return updated, changed


def ensure_backup(cfg_path: Path) -> Path:
    """Create a sibling backup file before modification if it does not exist."""
    backup_path = cfg_path.with_name(cfg_path.name + ".bezel_backup")
    if not backup_path.exists():
        shutil.copy2(cfg_path, backup_path)
    return backup_path


def process_config(cfg_path: Path, dry_run: bool) -> ProcessResult:
    rom_name = cfg_path.stem
    overlay_stem = find_matching_overlay(cfg_path)
    if overlay_stem is None:
        return ProcessResult(rom_name=rom_name, matched=False)

    original_text = cfg_path.read_text(encoding="utf-8", errors="replace")
    updated_text, changed = rewrite_overlay_settings(original_text, overlay_stem)

    if changed and not dry_run:
        ensure_backup(cfg_path)
        cfg_path.write_text(updated_text, encoding="utf-8")

    return ProcessResult(
        rom_name=rom_name,
        matched=True,
        matched_overlay=overlay_stem,
        modified=changed,
    )


def write_report(
    results: list[ProcessResult],
    dry_run: bool,
    report_path: Path = REPORT_PATH,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    processed = len(results)
    matched = sum(1 for result in results if result.matched)
    unmatched = [result.rom_name for result in results if not result.matched]
    modified = [result for result in results if result.modified]

    lines = [
        "MAME Bezel Wiring Report",
        "========================",
        f"Mode: {'DRY RUN' if dry_run else 'APPLY'}",
        f"Config directory: {MAME_CONFIG_DIR}",
        f"Overlay directory: {ARCADE_BEZELS_DIR}",
        "",
        f"Total CFGs processed: {processed}",
        f"Total matched (bezel found and wired): {matched}",
        f"Total unmatched (left on fallback): {len(unmatched)}",
        f"Total {'would be modified' if dry_run else 'modified'}: {len(modified)}",
        "",
        f"Files {'that would be modified' if dry_run else 'modified'}:",
    ]

    if modified:
        for result in modified:
            lines.append(f"- {result.rom_name}.cfg -> {result.matched_overlay}.cfg")
    else:
        lines.append("- none")

    lines.extend(["", "Unmatched ROM names:"])
    if unmatched:
        for rom_name in unmatched:
            lines.append(f"- {rom_name}")
    else:
        lines.append("- none")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_paths() -> None:
    missing = [
        path
        for path in (MAME_CONFIG_DIR, ARCADE_BEZELS_DIR)
        if not path.exists()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Required path(s) missing: {joined}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wire RetroArch MAME per-game configs to ArcadeBezels overlays."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matches and mismatches without editing RetroArch config files.",
    )
    args = parser.parse_args()

    validate_paths()

    results: list[ProcessResult] = []
    cfg_files = sorted(MAME_CONFIG_DIR.glob("*.cfg"))

    for cfg_path in cfg_files:
        result = process_config(cfg_path, dry_run=args.dry_run)
        results.append(result)
        if args.dry_run:
            if result.matched:
                action = "would update" if result.modified else "already correct"
                print(f"MATCH    {cfg_path.name} -> {result.matched_overlay}.cfg ({action})")
            else:
                print(f"NO MATCH {cfg_path.name} -> fallback stays {FALLBACK_OVERLAY}")

    write_report(results, dry_run=args.dry_run)

    processed = len(results)
    matched = sum(1 for result in results if result.matched)
    unmatched = processed - matched
    modified = sum(1 for result in results if result.modified)

    print()
    print(f"Processed: {processed}")
    print(f"Matched:   {matched}")
    print(f"Unmatched: {unmatched}")
    print(f"{'Would modify' if args.dry_run else 'Modified'}: {modified}")
    print(f"Report:    {REPORT_PATH}")

    if args.dry_run:
        print("Dry run complete. No RetroArch config files were changed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
