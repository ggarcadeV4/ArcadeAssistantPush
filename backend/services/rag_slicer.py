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
from typing import Dict, Iterable, Optional

from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)
PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts"

# Persona -> Section Tag routing table
PERSONA_SECTION_MAP: Dict[str, str] = {
    # Launch / frontend
    "launchbox": "## LAUNCH_PROTOCOL",
    "lora": "## LAUNCH_PROTOCOL",
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
            self._factory_dir: Optional[Path] = None
        else:
            drive_root = get_drive_root(context="rag_slicer")
            self._kb_dir = drive_root / ".aa" / "state" / "knowledge_base"
            self._factory_dir = PROMPT_ROOT

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
        tags = self._persona_tags(persona)
        if not tags:
            logger.debug("No section mapping for persona '%s'", persona)
            return ""

        md_file = self._find_knowledge_file(emulator_name)
        if md_file is None:
            return ""

        try:
            content = md_file.read_text(encoding="utf-8-sig")
        except Exception as exc:
            logger.warning(
                "Failed to read knowledge file %s: %s", md_file.name, exc
            )
            return ""

        for tag in tags:
            section = self._extract_section_optional(content, tag)
            if section is not None:
                return section
        return ""

    def get_section(self, emulator_name: str, section_tag: str) -> str:
        """
        Return a specific section from an emulator knowledge file.

        Args:
            emulator_name: e.g. "sega_model_2"
            section_tag:   e.g. "CONTROLLER_CONFIG" or "## CONTROLLER_CONFIG"

        Returns:
            The extracted section body or "" if the file or section is missing.
        """
        md_file = self._find_knowledge_file(emulator_name)
        if md_file is None:
            return ""

        try:
            content = md_file.read_text(encoding="utf-8-sig")
        except Exception as exc:
            logger.warning(
                "Failed to read knowledge file %s: %s", md_file.name, exc
            )
            return ""

        return self._extract_section(content, self._normalize_tag(section_tag))

    def list_available_emulators(self) -> list[str]:
        """Return basenames (without .md) of all knowledge files."""
        emulators = set()
        for base_dir in self._iter_candidate_dirs():
            if not base_dir.is_dir():
                continue
            for file_path in base_dir.glob("*.md"):
                if not file_path.name.startswith("."):
                    emulators.add(file_path.stem)
        return sorted(emulators)

    def _find_knowledge_file(self, emulator_name: str) -> Optional[Path]:
        """Case-insensitive lookup for {emulator_name}.md."""
        target = emulator_name.lower()

        for base_dir in self._iter_candidate_dirs():
            if not base_dir.is_dir():
                continue

            exact = base_dir / f"{emulator_name}.md"
            if exact.is_file():
                return exact

            for candidate in base_dir.iterdir():
                if candidate.suffix.lower() == ".md" and candidate.stem.lower() == target:
                    return candidate

        return None

    def _iter_candidate_dirs(self) -> Iterable[Path]:
        yield self._kb_dir
        if self._factory_dir and self._factory_dir != self._kb_dir:
            yield self._factory_dir

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        cleaned = (tag or "").strip()
        if not cleaned:
            return ""
        if cleaned.startswith("##"):
            cleaned = cleaned[2:].strip()
        return f"## {cleaned}"

    @classmethod
    def _persona_tags(cls, persona: str) -> list[str]:
        tag = PERSONA_SECTION_MAP.get(persona.lower())
        if not tag:
            return []

        normalized = cls._normalize_tag(tag)
        if persona.lower() in {"launchbox", "lora"}:
            return [normalized, "## LAUNCH"]
        return [normalized]

    @staticmethod
    def _extract_section(content: str, tag: str) -> str:
        """
        Extract the text body under *tag* (e.g. '## GUN_CONFIG').
        Returns the content between the tag header and the next ## header
        (or end-of-file), stripped of leading/trailing whitespace.
        Returns "" if the tag is not found.
        """
        section = RAGSlicer._extract_section_optional(content, tag)
        return section if section is not None else ""

    @staticmethod
    def _extract_section_optional(content: str, tag: str) -> Optional[str]:
        normalized_tag = RAGSlicer._normalize_tag(tag)
        if not normalized_tag:
            return None

        for match in _SECTION_RE.finditer(content):
            section_text = match.group(1)
            first_line = section_text.split("\n", 1)[0].strip()
            if first_line.upper().startswith(normalized_tag.upper()):
                parts = section_text.split("\n", 1)
                if len(parts) > 1:
                    return parts[1].strip()
                return ""

        return None

