from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_DRIVE_ROOT = Path(r"W:\Arcade Assistant Master Build")
IMAGE_LIBRARY_NAME = "Dewey Images Artwork for Arcade Assistant General Questions"
OUTPUT_JSON = Path(
    r"W:\Arcade Assistant Master Build\Arcade Assistant Local\backend\data\dewey_image_index.json"
)
OUTPUT_SUMMARY = Path(
    r"W:\Arcade Assistant Master Build\Arcade Assistant Local\backend\data\dewey_image_index_summary.md"
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _drive_root() -> Path:
    raw = os.environ.get("AA_DRIVE_ROOT", "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DRIVE_ROOT


def _normalize_game_title(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"-\d+$", "", stem).strip()


def _build_entry(image_root: Path, file_path: Path, drive_root: Path) -> Dict[str, str]:
    relative_to_library = file_path.relative_to(image_root)
    parts = relative_to_library.parts
    if len(parts) < 3:
        return None

    filename = file_path.name
    platform = parts[0]
    image_type = parts[1]
    region = parts[2] if len(parts) > 3 else ""
    relative_path = file_path.relative_to(drive_root).as_posix()

    return {
        "platform": platform,
        "image_type": image_type,
        "region": region,
        "filename": filename,
        "game_title": _normalize_game_title(filename),
        "relative_path": relative_path,
    }


def _scan_images(image_root: Path, drive_root: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for file_path in image_root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        entry = _build_entry(image_root, file_path, drive_root)
        if entry is not None:
            entries.append(entry)

    entries.sort(
        key=lambda item: (
            item["platform"].lower(),
            item["image_type"].lower(),
            item["region"].lower(),
            item["game_title"].lower(),
            item["filename"].lower(),
        )
    )
    return entries


def _format_counter(counter: Counter[str], heading: str) -> List[str]:
    lines = [f"## {heading}", ""]
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower())):
        lines.append(f"- {key}: {count}")
    if len(lines) == 2:
        lines.append("- None: 0")
    lines.append("")
    return lines


def _build_summary(entries: List[Dict[str, str]]) -> str:
    platform_counts = Counter(entry["platform"] for entry in entries)
    image_type_counts = Counter(entry["image_type"] for entry in entries)
    unique_titles = len({entry["game_title"] for entry in entries if entry["game_title"]})
    examples = entries[:10]

    lines = [
        "# Dewey Image Index Summary",
        "",
        f"- Total image count: {len(entries)}",
        f"- Total unique game titles found: {unique_titles}",
        "",
    ]
    lines.extend(_format_counter(platform_counts, "Breakdown by Platform"))
    lines.extend(_format_counter(image_type_counts, "Breakdown by Image Type"))
    lines.append("## Example Entries")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(examples, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    drive_root = _drive_root()
    image_root = drive_root / IMAGE_LIBRARY_NAME

    if not image_root.exists():
        raise FileNotFoundError(f"Image library not found: {image_root}")

    entries = _scan_images(image_root, drive_root)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)

    summary = _build_summary(entries)
    OUTPUT_SUMMARY.write_text(summary, encoding="utf-8")

    print(f"Indexed {len(entries)} images from {image_root}")
    print(f"Wrote JSON: {OUTPUT_JSON}")
    print(f"Wrote summary: {OUTPUT_SUMMARY}")


if __name__ == "__main__":
    main()
