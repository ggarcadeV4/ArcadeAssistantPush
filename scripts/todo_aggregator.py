"""Fast TODO aggregator grouped by panel with P0 surfacing."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Tuple

P0_PATTERN = re.compile(r"(supabase|env|p0)", re.IGNORECASE)
EXCLUDED_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build"}
PANEL_HINTS = {
    "dewey": "Panel 2",
    "launchbox": "Panel 1",
    "scorekeeper": "Panel 3",
    "voice": "Panel 4",
    "controller": "Panel 5",
    "wizard": "Panel 6",
    "led": "Panel 7",
    "gunner": "Panel 8",
    "doc": "Panel 9",
}


def detect_panel(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    for part in reversed(parts):
        for hint, panel in PANEL_HINTS.items():
            if hint in part:
                return panel
    return "other"


def walk_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            if name.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".md")):
                yield Path(dirpath) / name


def aggregate_todos(root_dir: Path) -> Dict[str, List[Tuple[str, str, str]]]:
    groups: DefaultDict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for file_path in walk_files(root_dir):
        panel = detect_panel(file_path.parent)
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for idx, line in enumerate(handle, 1):
                    if "TODO" not in line:
                        continue
                    priority = "P0" if P0_PATTERN.search(line) else "P2"
                    groups[panel].append((priority, f"{file_path}:{idx}", line.strip()))
        except UnicodeDecodeError:
            continue
    return groups


def write_report(groups: Dict[str, List[Tuple[str, str, str]]], output: Path) -> None:
    lines: List[str] = ["# TODO Debt Overview", ""]
    for panel, todos in sorted(groups.items()):
        lines.append(f"## {panel}")
        if not todos:
            lines.append("- None ✅")
            continue
        todos.sort(key=lambda item: item[0])
        for priority, location, text in todos:
            lines.append(f"- {priority} | {location} | {text}")
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    start = time.perf_counter()
    root = Path.cwd()
    groups = aggregate_todos(root)
    report_path = root / "docs" / "TODO.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(groups, report_path)
    duration = time.perf_counter() - start
    print(f"Aggregated {sum(len(v) for v in groups.values())} TODOs in {duration:.2f}s -> {report_path}")


if __name__ == "__main__":
    main()
