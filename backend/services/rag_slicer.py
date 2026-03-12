"""
RAG Context Map - Section Slicer.
ARCHITECTURE:
  One master markdown file per emulator lives in the knowledge_base directory.
  Each file contains multiple ## TAG sections (e.g. ## CONTROLLER_CONFIG, ## GUN_CONFIG).
  The slicer extracts ONLY the section relevant to the requesting AI persona.
  This physically prevents cross-domain hallucinations.
Usage:
    slicer = RAGSlicer()
    chunk = slicer.get_persona_slice("MAME", "chuck")
    # Returns only the ## CONTROLLER_CONFIG section from MAME.md
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional


logger = logging.getLogger(__name__)

# Persona -> Section Tag routing table
PERSONA_SECTION_MAP: Dict[str, str] = {
    # Launch / frontend
    "launchbox": "## LAUNCH",
    "lora": "## LAUNCH",
    # Routing / search
    "dewey": "## ROUTING_VOCAB",
    # Score tracking
    "scorekeeper": "## SCORE_TRACKING",
    "sam": "## SCORE_TRACKING",
    # Voice
    "voice": "## VOICE_VOCABULARY",
    "vicky": "## VOICE_VOCABULARY",
    # Controller mapping
    "chuck": "## CONTROLLER_CONFIG",
    "controller-chuck": "## CONTROLLER_CONFIG",
    "console_wizard": "## CONTROLLER_CONFIG",
    "controller-wizard": "## CONTROLLER_CONFIG",
    # LED
    "blinky": "## LED_PROFILE",
    "led": "## LED_PROFILE",
    # Light gun
    "gunner": "## GUN_CONFIG",
    # Health / diagnostics
    "doc": "## HEALTH_CHECK",
}

# Pre-compiled regex: matches a ## header line and captures everything
# until the next ## header or end-of-file.
_SECTION_RE = re.compile(
    r"^(## \S+.*?)(?=\n## |\Z)",
    re.MULTILINE | re.DOTALL,
)


class RAGSlicer:
    """
    Extracts persona-specific sections from per-emulator master markdown files.
    Knowledge base directory: A:\\.aa\\state\\knowledge_base\\
    File naming:             {EMULATOR_NAME}.md  (case-insensitive lookup)
    """

    def __init__(self, knowledge_dir: Optional[Path] = None) -> None:
        if knowledge_dir is not None:
            self._kb_dir = knowledge_dir
        else:
            drive_root = Path(os.getenv("AA_DRIVE_ROOT", "."))
            self._kb_dir = drive_root / ".aa" / "state" / "knowledge_base"

    def get_persona_slice(self, emulator_name: str, persona: str) -> str:
        """
        Return the markdown section relevant to *persona* from the
        master knowledge file for *emulator_name*.

        Args:
            emulator_name: e.g. "MAME", "RetroArch", "Dolphin"
            persona:       e.g. "chuck", "gunner", "dewey"

        Returns:
            The extracted section text (without the ## header line itself),
            or "" if the file doesn't exist, the persona is unknown,
            or the requested section tag is not found in the file.
        """
        tag = PERSONA_SECTION_MAP.get(persona.lower())
        if not tag:
            logger.debug("No section mapping for persona '%s'", persona)
            return ""

        md_file = self._find_knowledge_file(emulator_name)
        if md_file is None:
            return ""

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(
                "Failed to read knowledge file %s: %s", md_file.name, exc
            )
            return ""

        return self._extract_section(content, tag)

    def list_available_emulators(self) -> list[str]:
        """Return basenames (without .md) of all knowledge files."""
        if not self._kb_dir.is_dir():
            return []

        return sorted(
            f.stem for f in self._kb_dir.glob("*.md")
            if not f.name.startswith(".")
        )

    def _find_knowledge_file(self, emulator_name: str) -> Optional[Path]:
        """Case-insensitive lookup for {emulator_name}.md."""
        if not self._kb_dir.is_dir():
            return None

        exact = self._kb_dir / f"{emulator_name}.md"
        if exact.is_file():
            return exact

        target = emulator_name.lower()
        for candidate in self._kb_dir.iterdir():
            if candidate.suffix.lower() == ".md" and candidate.stem.lower() == target:
                return candidate

        return None

    @staticmethod
    def _extract_section(content: str, tag: str) -> str:
        """
        Extract the text body under *tag* (e.g. '## GUN_CONFIG').
        Returns the content between the tag header and the next ## header
        (or end-of-file), stripped of leading/trailing whitespace.
        Returns "" if the tag is not found.
        """
        for match in _SECTION_RE.finditer(content):
            section_text = match.group(1)
            first_line = section_text.split("\n", 1)[0].strip()
            if first_line.upper().startswith(tag.upper()):
                parts = section_text.split("\n", 1)
                if len(parts) > 1:
                    return parts[1].strip()
                return ""

        return ""
