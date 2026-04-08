"""Dedicated Dewey chat router using prompt files and Gemini proxy."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.drive_a_ai_client import SecureAIClient
from backend.services.dewey.trivia_generator import generate_collection_trivia
from backend.services.policies import require_scope

DEWEY_MEDIA_TOOL = [
    {
        "name": "show_game_media",
        "description": "Call this when the user is asking about a specific game and you want to display images or video for it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "game_title": {
                    "type": "string",
                    "description": "The exact or closest matching title of the game from the arcade library."
                },
                "media_type": {
                    "type": "string",
                    "enum": [
                        "Arcade - Cabinet",
                        "Arcade - Marquee",
                        "Arcade - Control Panel",
                        "Arcade - Controls Information",
                        "Screenshot - Gameplay",
                        "Screenshot - Game Title",
                        "Screenshot - Game Over",
                        "Screenshot - High Scores",
                        "Clear Logo",
                        "Box - Front",
                        "Fanart - Background",
                        "Advertisement Flyer - Front"
                    ],
                    "description": "The type of image to show. Use 'Screenshot - Gameplay' for questions about what a game looks like or how it plays. Use 'Arcade - Cabinet' for questions about the physical cabinet. Use 'Arcade - Marquee' for the marquee or signage. Use 'Clear Logo' for game identity or logo. Use 'Box - Front' for box art. Use 'Fanart - Background' for atmospheric visuals. Use 'Advertisement Flyer - Front' for promotional art. Use 'Screenshot - Game Title' for title screens."
                }
            },
            "required": ["game_title"]
        }
    }
]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local/dewey", tags=["dewey-chat"])
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- Dewey image index (loaded once, cached in memory) ---
_DEWEY_IMAGE_INDEX_PATH = _PROJECT_ROOT / "backend" / "data" / "dewey_image_index.json"
_LIBRARY_ROOTS = (
    "Dewey Images Artwork for Arcade Assistant General Questions/",
    "LaunchBox/Images/",
)
_MEDIA_TYPE_ALIASES = {
    "advertisement flyer front": "advertisement flyer front",
    "arcade cabinet": "arcade cabinet",
    "arcade control panel": "arcade control panel",
    "arcade controls information": "arcade controls information",
    "arcade marquee": "arcade marquee",
    "box": "box front",
    "box front": "box front",
    "cabinet": "arcade cabinet",
    "clear logo": "clear logo",
    "control panel": "arcade control panel",
    "controls information": "arcade controls information",
    "default": "box front",
    "fanart": "fanart background",
    "fanart background": "fanart background",
    "flyer": "advertisement flyer front",
    "game over": "screenshot game over",
    "game title": "screenshot game title",
    "gameplay": "screenshot gameplay",
    "high scores": "screenshot high scores",
    "logo": "clear logo",
    "marquee": "arcade marquee",
    "screenshot": "screenshot game title",
    "screenshot game over": "screenshot game over",
    "screenshot game title": "screenshot game title",
    "screenshot gameplay": "screenshot gameplay",
    "screenshot high scores": "screenshot high scores",
    "video": "screenshot gameplay",
}


def _normalize_image_title(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_media_type_key(media_type: str) -> str:
    normalized = _normalize_image_title(media_type)
    return _MEDIA_TYPE_ALIASES.get(normalized, normalized)


def _load_dewey_image_index() -> Dict[tuple[str, str], str]:
    try:
        with _DEWEY_IMAGE_INDEX_PATH.open("r", encoding="utf-8") as handle:
            raw_index = json.load(handle)
    except FileNotFoundError:
        logger.warning("[Dewey] Image index not found at %s", _DEWEY_IMAGE_INDEX_PATH)
        return {}
    except Exception as exc:
        logger.warning("[Dewey] Could not load image index: %s", exc)
        return {}

    if not isinstance(raw_index, list):
        logger.warning("[Dewey] Image index has unexpected shape: %s", type(raw_index).__name__)
        return {}

    index: Dict[tuple[str, str], str] = {}
    for entry in raw_index:
        if not isinstance(entry, dict):
            continue
        normalized_title = _normalize_image_title(str(entry.get("game_title") or ""))
        normalized_media_type = _normalize_media_type_key(str(entry.get("image_type") or ""))
        relative_path = str(entry.get("relative_path") or "").replace("\\", "/").strip()
        if not normalized_title or not normalized_media_type or not relative_path:
            continue
        index.setdefault((normalized_title, normalized_media_type), _strip_library_root(relative_path))
    return index


def _strip_library_root(rel: str) -> str:
    for root in _LIBRARY_ROOTS:
        if rel.startswith(root):
            return rel[len(root):]
    return rel


_DEWEY_IMAGE_INDEX = _load_dewey_image_index()

_prompt_cache: Dict[str, str] = {}
_knowledge_cache: Dict[str, str] = {}
_lb_game_cache: Optional[List[Dict[str, Any]]] = None
_lb_cache_loaded: bool = False
_lb_variant_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
_lb_variant_patterns: Optional[List[tuple[str, str, re.Pattern[str]]]] = None
_MAX_HISTORY_MESSAGES = 12
_DEFAULT_PREFERENCE_SUMMARY = "No saved preferences yet - ask quick follow-ups to learn their tastes."
_NEWS_KEYWORDS = [
    "news", "headlines", "announcement", "latest", "recent",
    "gaming news", "whats new", "what's new", "happening in gaming",
]
_TRIVIA_DB_PATH = _PROJECT_ROOT / "frontend" / "src" / "panels" / "dewey" / "trivia" / "triviaDatabase.json"
_STATIC_COLLECTION_FALLBACK = [
    {
        "id": "collection_static_001",
        "category": ["collection"],
        "difficulty": "easy",
        "question": "What term usually describes the first commercially released home version of a game?",
        "choices": ["Launch edition", "Original release", "Beta port", "Collector remix"],
        "correct_index": 1,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_002",
        "category": ["collection"],
        "difficulty": "easy",
        "question": "Which metadata field tells you who created the game studio behind a title?",
        "choices": ["Developer", "Platform", "Region", "Playlist"],
        "correct_index": 0,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_003",
        "category": ["collection"],
        "difficulty": "medium",
        "question": "If a game is listed under 'Fighting', what kind of genre tag is that?",
        "choices": ["Platform", "Genre", "Publisher", "Region"],
        "correct_index": 1,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_004",
        "category": ["collection"],
        "difficulty": "medium",
        "question": "Which field is most useful for grouping a library by hardware family such as Genesis or SNES?",
        "choices": ["Developer", "Platform", "Publisher", "Release status"],
        "correct_index": 1,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_005",
        "category": ["collection"],
        "difficulty": "hard",
        "question": "Which piece of metadata best helps identify when a game first arrived on the market?",
        "choices": ["Genre", "Release year", "Publisher region", "Cabinet ID"],
        "correct_index": 1,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_006",
        "category": ["collection"],
        "difficulty": "easy",
        "question": "A title sorted under multiple hardware families is usually distinguished by which field first?",
        "choices": ["Platform", "Difficulty", "Cover art", "Play time"],
        "correct_index": 0,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_007",
        "category": ["collection"],
        "difficulty": "medium",
        "question": "Which metadata field usually names the company that financed and distributed a game?",
        "choices": ["Publisher", "Genre", "Platform", "Playlist"],
        "correct_index": 0,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_008",
        "category": ["collection"],
        "difficulty": "medium",
        "question": "What is the clearest way to separate a 1980s release from a 2000s release in a library list?",
        "choices": ["Release year", "Developer name", "Platform icon", "Sort title"],
        "correct_index": 0,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_009",
        "category": ["collection"],
        "difficulty": "hard",
        "question": "If two versions of a game share a title, which field most reliably distinguishes the hardware-specific entry?",
        "choices": ["Genre", "Platform", "Difficulty", "Question count"],
        "correct_index": 1,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
    {
        "id": "collection_static_010",
        "category": ["collection"],
        "difficulty": "easy",
        "question": "Which library field helps group racers, shooters, and platformers into their gameplay families?",
        "choices": ["Genre", "Publisher", "Region", "Year imported"],
        "correct_index": 0,
        "metadata": {"game_title": "Collection Fallback", "generated": False},
    },
]
_UNCERTAINTY_MARKERS: List[str] = [
    "i'm not sure",
    "i don't know",
    "i cannot confirm",
    "i'm uncertain",
    "i don't have information",
    "i cannot verify",
    "my knowledge may be",
    "i'm not certain",
    "i may be wrong",
    "you may want to verify",
    "i don't have specific",
    "i lack information",
]
_PLATFORM_HINT_ALIASES: Dict[str, List[str]] = {
    "Arcade MAME": ["arcade mame", "mame", "arcade"],
    "Arcade": ["arcade"],
    "Atari 2600": ["atari 2600", "2600", "atari vcs"],
    "Atari 7800": ["atari 7800", "7800"],
    "ColecoVision": ["colecovision", "coleco vision"],
    "Nintendo Entertainment System": ["nintendo entertainment system", "nes"],
    "Nintendo Game Boy": ["nintendo game boy", "game boy", "gameboy", "gb"],
    "Nintendo Game Boy Color": ["nintendo game boy color", "game boy color", "gameboy color", "gbc"],
    "Nintendo Game Boy Advance": ["nintendo game boy advance", "game boy advance", "gameboy advance", "gba"],
    "Nintendo 64": ["nintendo 64", "n64"],
    "Sega Genesis": ["sega genesis", "genesis", "mega drive"],
    "Sony Playstation": ["sony playstation", "playstation", "ps1", "psx"],
    "Sony Playstation 2": ["sony playstation 2", "playstation 2", "ps2"],
    "Sony Playstation 3": ["sony playstation 3", "playstation 3", "ps3"],
}


def _get_lb_games() -> List[Dict[str, Any]]:
    """Load and cache launchbox_games.json on first call."""
    global _lb_game_cache, _lb_cache_loaded
    if _lb_cache_loaded:
        return _lb_game_cache or []
    _lb_cache_loaded = True
    try:
        cache_path = _launchbox_cache_path()
        if not cache_path or not cache_path.exists():
            return []
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _lb_game_cache = raw if isinstance(raw, list) else []
    except Exception:
        _lb_game_cache = []
    return _lb_game_cache or []


def _normalize_variant_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())).strip()


def _platform_priority(platform: str) -> int:
    normalized = _normalize_variant_key(platform)
    if normalized == "arcade mame":
        return 500
    if normalized == "arcade":
        return 450
    if normalized == "daphne":
        return 400
    if "mame" in normalized:
        return 350
    return 100


def _load_variant_catalog() -> tuple[Dict[str, List[Dict[str, Any]]], List[tuple[str, str, re.Pattern[str]]]]:
    global _lb_variant_cache, _lb_variant_patterns
    if _lb_variant_cache is not None and _lb_variant_patterns is not None:
        return _lb_variant_cache, _lb_variant_patterns

    catalog: Dict[str, List[Dict[str, Any]]] = {}
    patterns: List[tuple[str, str, re.Pattern[str]]] = []
    for game in _load_launchbox_games():
        title = str(game.get("title") or "").strip()
        platform = str(game.get("platform") or "").strip()
        normalized_title = _normalize_variant_key(title)
        if not title or not platform or not normalized_title:
            continue

        variants = catalog.setdefault(normalized_title, [])
        duplicate = any(
            _normalize_variant_key(item.get("platform", "")) == _normalize_variant_key(platform)
            for item in variants
        )
        if duplicate:
            continue

        variants.append(
            {
                "title": title,
                "platform": platform,
                "developer": str(game.get("developer") or "").strip(),
                "publisher": str(game.get("publisher") or "").strip(),
                "genre": str(game.get("genre") or "").strip(),
                "release_year": game.get("release_year") or game.get("year"),
            }
        )

    for normalized_title, variants in catalog.items():
        variants.sort(
            key=lambda item: (
                -_platform_priority(str(item.get("platform") or "")),
                str(item.get("platform") or ""),
            )
        )
        display_title = str(variants[0].get("title") or "").strip()
        escaped = re.escape(normalized_title)
        patterns.append((normalized_title, display_title, re.compile(rf"(?:^|\b){escaped}(?:\b|$)")))

    patterns.sort(key=lambda item: len(item[0]), reverse=True)
    _lb_variant_cache = catalog
    _lb_variant_patterns = patterns
    return catalog, patterns


def _detect_preferred_platform(message: str) -> str:
    normalized_message = _normalize_variant_key(message)
    if not normalized_message:
        return ""

    best_platform = ""
    best_score = -1
    for platform, aliases in _PLATFORM_HINT_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_variant_key(alias)
            if not normalized_alias:
                continue
            if re.search(rf"(?:^|\b){re.escape(normalized_alias)}(?:\b|$)", normalized_message):
                score = len(normalized_alias.split()) * 100 + _platform_priority(platform)
                if score > best_score:
                    best_platform = platform
                    best_score = score
    return best_platform


def _select_variant_for_platform(variants: List[Dict[str, Any]], preferred_platform: str) -> Optional[Dict[str, Any]]:
    preferred_key = _normalize_variant_key(preferred_platform)
    if not preferred_key:
        return None

    for variant in variants:
        platform = str(variant.get("platform") or "")
        platform_key = _normalize_variant_key(platform)
        if platform_key == preferred_key or preferred_key in platform_key or platform_key in preferred_key:
            return variant
    return None


def _find_variant_title(message: str) -> tuple[str, List[Dict[str, Any]]]:
    catalog, patterns = _load_variant_catalog()
    normalized_message = _normalize_variant_key(message)
    if not normalized_message:
        return "", []

    for normalized_title, _, pattern in patterns:
        if pattern.search(normalized_message):
            return normalized_title, catalog.get(normalized_title, [])
    return "", []


def _normalize_active_subject(active_subject: Optional["DeweyActiveSubject"]) -> Dict[str, str]:
    if active_subject is None:
        return {"title": "", "platform": "", "visual_intent": ""}

    return {
        "title": str(active_subject.title or "").strip(),
        "platform": str(active_subject.platform or "").strip(),
        "visual_intent": str(active_subject.visual_intent or "").strip(),
    }


def _build_active_subject_context(active_subject: Optional["DeweyActiveSubject"]) -> str:
    normalized = _normalize_active_subject(active_subject)
    title = normalized["title"]
    platform = normalized["platform"]
    visual_intent = normalized["visual_intent"]
    if not title and not platform and not visual_intent:
        return ""

    lines = ["\n\n=== ACTIVE SUBJECT ==="]
    if title:
        lines.append(f"Active game from conversation state: {title}")
    if platform:
        lines.append(f"Active platform from conversation state: {platform}")
    if visual_intent:
        lines.append(f"Active visual intent from conversation state: {visual_intent}")
    lines.append(
        "Use this as the default referent for short follow-up questions unless the user clearly switches to a different game or platform."
    )
    lines.append("=== END ACTIVE SUBJECT ===\n")
    return "\n".join(lines)


def _build_variant_context(
    user_message: str,
    history: List["DeweyChatTurn"],
    active_subject: Optional["DeweyActiveSubject"] = None,
) -> str:
    normalized_title, variants = _find_variant_title(user_message)
    normalized_active_subject = _normalize_active_subject(active_subject)

    if not variants and normalized_active_subject["title"]:
        catalog, _ = _load_variant_catalog()
        normalized_title = _normalize_variant_key(normalized_active_subject["title"])
        variants = catalog.get(normalized_title, [])

    if not variants:
        for turn in reversed((history or [])[-_MAX_HISTORY_MESSAGES:]):
            prior_text = _html_to_plain_text(turn.content if turn.content is not None else (turn.text or ""))
            normalized_title, variants = _find_variant_title(prior_text)
            if variants:
                break

    if not variants or len(variants) < 2:
        return ""

    preferred_platform = _detect_preferred_platform(user_message)
    if not preferred_platform:
        preferred_platform = normalized_active_subject["platform"]
    preferred_variant = _select_variant_for_platform(variants, preferred_platform) if preferred_platform else None
    if preferred_variant is None:
        preferred_variant = variants[0]
        preferred_platform = str(preferred_variant.get("platform") or "")

    title_label = str(preferred_variant.get("title") or variants[0].get("title") or "").strip()
    available_platforms = ", ".join(str(variant.get("platform") or "").strip() for variant in variants if variant.get("platform"))

    return (
        "\n\n=== VARIANT CONTEXT ===\n"
        f"Detected multi-platform title: {title_label}\n"
        f"Preferred variant for this request: {preferred_platform}\n"
        f"Available variants in the library: {available_platforms}\n"
        "Treat the preferred variant as the active game for this response. "
        "Only discuss another version if the user explicitly asks to compare versions.\n"
        "=== END VARIANT CONTEXT ===\n"
    )


def _resolve_local_image(
    game_title: str,
    media_type: str = "default"
) -> Optional[str]:
    """
    Look up game art in the pre-built image index and return
    a single gateway URL or None.
    """
    if not game_title or game_title.lower() in (
        "null", "none", "", "unknown"
    ):
        return None

    normalized_title = _normalize_image_title(game_title)
    normalized_media_type = _normalize_media_type_key(media_type)
    if not normalized_title or not normalized_media_type:
        return None

    relative_path = _DEWEY_IMAGE_INDEX.get((normalized_title, normalized_media_type))
    if not relative_path:
        return None

    return f"http://127.0.0.1:8787/api/launchbox/image/{quote(relative_path, safe='/')}"


def _parse_media_tag(
    reply: str,
) -> tuple[str, str, str]:
    """
    Extract [MEDIA:{...}] tag from Dewey's reply.
    Returns (clean_reply, game_title, media_type).
    clean_reply has the tag stripped.
    game_title and media_type are empty strings if no tag found.
    """
    import re
    pattern = r"\[MEDIA:\s*(\{[^]]*\})\s*\]"
    match = re.search(pattern, reply, re.DOTALL)
    if not match:
        return reply, "", ""
    tag_json = match.group(1)
    clean = (reply[:match.start()] +
             reply[match.end():]).strip()
    try:
        data = json.loads(tag_json)
        game = str(data.get("game") or "").strip()
        mtype = str(data.get("type") or "default").strip()
        return clean, game, mtype
    except Exception:
        return reply, "", ""


def _extract_tool_call(
    reply: str, tool_name: str
) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(reply)
        if isinstance(data, dict):
            calls = data.get("functionCall") or data.get("function_call")
            if calls and calls.get("name") == tool_name:
                args = calls.get("args", {})
                args["clean_reply"] = data.get("text", "")
                return args
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _dewey_chat_max_tokens() -> int:
    raw = os.getenv("DEWEY_CHAT_MAX_TOKENS", "300")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 300
    return max(128, min(512, value))


class DeweyChatTurn(BaseModel):
    role: str
    content: Optional[str] = None
    text: Optional[str] = None


class DeweyActiveSubject(BaseModel):
    title: Optional[str] = None
    platform: Optional[str] = None
    visual_intent: Optional[str] = None


class DeweyChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    user_name: Optional[str] = "Guest"
    preference_summary: Optional[str] = None
    conversation_history: List[DeweyChatTurn] = Field(default_factory=list)
    active_subject: Optional[DeweyActiveSubject] = None


class DeweyInterpretRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_history: List[DeweyChatTurn] = Field(default_factory=list)
    active_subject: Optional[DeweyActiveSubject] = None


class CollectionTriviaRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=20)


def _project_root() -> Path:
    return _PROJECT_ROOT


def _load_static_collection_questions(count: int = 10) -> List[Dict[str, Any]]:
    try:
        if _TRIVIA_DB_PATH.exists():
            data = json.loads(_TRIVIA_DB_PATH.read_text(encoding="utf-8"))
            questions = [
                item
                for item in data.get("questions", [])
                if isinstance(item, dict) and "collection" in item.get("category", [])
            ]
            if questions:
                return questions[:count]
    except Exception as exc:
        logger.warning("Failed to load static collection trivia from trivia database: %s", exc)

    return [dict(item) for item in _STATIC_COLLECTION_FALLBACK[:count]]


def _launchbox_cache_path() -> Optional[Path]:
    drive_root = os.getenv("AA_DRIVE_ROOT")
    if not drive_root:
        logger.warning("AA_DRIVE_ROOT is not set; using static fallback for collection trivia")
        return None
    return Path(drive_root) / ".aa" / "launchbox_games.json"


def _load_launchbox_games() -> List[Dict[str, Any]]:
    cache_path = _launchbox_cache_path()
    if cache_path is None or not cache_path.exists():
        logger.warning("LaunchBox cache missing for collection trivia: %s", cache_path)
        return []

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read LaunchBox cache for collection trivia: %s", exc)
        return []

    raw_games: Any
    if isinstance(payload, dict):
        raw_games = payload.get("games", [])
    elif isinstance(payload, list):
        raw_games = payload
    else:
        raw_games = []

    if not isinstance(raw_games, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for game in raw_games:
        if not isinstance(game, dict):
            continue
        title = str(game.get("title") or "").strip()
        if not title:
            continue
        normalized.append(
            {
                "title": title,
                "platform": str(game.get("platform") or "Unknown platform").strip(),
                "developer": str(game.get("developer") or "Unknown developer").strip(),
                "publisher": str(game.get("publisher") or "Unknown publisher").strip(),
                "release_year": game.get("release_year") or game.get("year"),
                "genre": str(game.get("genre") or "Unknown genre").strip(),
            }
        )

    return normalized


def _normalize_collection_questions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        options = item.get("options") or []
        answer = str(item.get("correct_answer") or "").strip()
        difficulty = str(item.get("difficulty") or "medium").strip().lower() or "medium"
        game_title = str(item.get("game_title") or "").strip()
        normalized_options = [str(option).strip() for option in options]

        if not question or len(normalized_options) != 4 or answer not in normalized_options:
            continue

        questions.append(
            {
                "id": f"collection_dynamic_{index:03d}",
                "category": ["collection"],
                "difficulty": difficulty if difficulty in {"easy", "medium", "hard"} else "medium",
                "question": question,
                "choices": normalized_options,
                "correct_index": normalized_options.index(answer),
                "metadata": {
                    "game_title": game_title,
                    "generated": True,
                },
            }
        )
    return questions


def _candidate_paths(filename: str, extension: str) -> List[Path]:
    prompt_root = _project_root() / "prompts"
    drive_root = Path(os.getenv("AA_DRIVE_ROOT", str(_project_root())))
    return [
        prompt_root / f"{filename}.{extension}",
        drive_root / "prompts" / f"{filename}.{extension}",
    ]


def _load_knowledge() -> str:
    if "dewey" in _knowledge_cache:
        return _knowledge_cache["dewey"]

    for candidate in _candidate_paths("dewey_knowledge", "md"):
        if candidate.exists():
            _knowledge_cache["dewey"] = candidate.read_text(encoding="utf-8").strip()
            return _knowledge_cache["dewey"]

    raise FileNotFoundError("Prompt file not found: dewey_knowledge.md")


def _load_prompt() -> str:
    if "dewey" in _prompt_cache:
        return _prompt_cache["dewey"]

    for candidate in _candidate_paths("dewey", "prompt"):
        if candidate.exists():
            _prompt_cache["dewey"] = candidate.read_text(encoding="utf-8").strip()
            return _prompt_cache["dewey"]

    raise FileNotFoundError("Prompt file not found: dewey.prompt")


def _html_to_plain_text(value: str = "") -> str:
    if not value:
        return ""
    return (
        value.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("&nbsp;", " ")
        .replace("\r", "")
        .strip()
    )


def _extract_json_object(value: str) -> Dict[str, Any]:
    raw = str(value or "").strip()
    if not raw:
        return {}

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    snippet = raw[start:end + 1]
    try:
        parsed = json.loads(snippet)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _render_system_prompt(user_name: str, preference_summary: str) -> str:
    template = _load_prompt()
    knowledge = _load_knowledge()
    rendered = (
        template
        .replace("{{user_name}}", user_name or "Guest")
        .replace("{{preference_summary}}", preference_summary or _DEFAULT_PREFERENCE_SUMMARY)
    )
    if knowledge:
        rendered += "\n\n--- KNOWLEDGE BASE ---\n" + knowledge
    return rendered


def _is_news_query(message: str) -> bool:
    lower = (message or "").lower()
    return any(keyword in lower for keyword in _NEWS_KEYWORDS)


async def _build_news_context(message: str) -> str:
    if not _is_news_query(message):
        return ""

    try:
        from backend.routers.gaming_news import fetch_all_headlines

        headlines = await fetch_all_headlines()
        if not headlines:
            return ""

        headlines_summary = "\n".join(
            f"{index + 1}. {headline.get('source', 'Unknown')}: "
            f"\"{headline.get('title', '')}\" "
            f"({headline.get('published_relative', 'Unknown')})"
            for index, headline in enumerate(headlines[:10])
        )

        return (
            "\n\n=== CURRENT GAMING HEADLINES (Real-time RSS) ===\n"
            f"{headlines_summary}\n"
            "=== END HEADLINES ===\n\n"
            "Reference these actual headlines when discussing gaming news. "
            "Be specific about sources and recency."
        )
    except Exception as exc:  # pragma: no cover - fail open
        logger.warning("Failed to load Dewey news context: %s", exc)
        return ""


def _build_messages(*, history: List[DeweyChatTurn], system_prompt: str, user_text: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    for turn in (history or [])[-_MAX_HISTORY_MESSAGES:]:
        content = _html_to_plain_text(turn.content if turn.content is not None else (turn.text or ""))
        if not content:
            continue
        role = "assistant" if turn.role in {"assistant", "dewey"} else "user"
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": _html_to_plain_text(user_text)})
    return messages


def _build_interpretation_messages(
    *,
    user_text: str,
    history: List[DeweyChatTurn],
    active_subject: Optional[DeweyActiveSubject],
) -> List[Dict[str, str]]:
    normalized_active_subject = _normalize_active_subject(active_subject)
    recent_turns: List[str] = []
    for turn in (history or [])[-6:]:
        content = _html_to_plain_text(turn.content if turn.content is not None else (turn.text or ""))
        if not content:
            continue
        label = "Assistant" if turn.role in {"assistant", "dewey"} else "User"
        recent_turns.append(f"{label}: {content}")

    history_block = "\n".join(recent_turns) or "None"
    active_title = normalized_active_subject["title"] or "None"
    active_platform = normalized_active_subject["platform"] or "None"
    active_visual_intent = normalized_active_subject["visual_intent"] or "None"

    system_prompt = (
        "You normalize Dewey arcade requests before deterministic media lookup.\n"
        "Return ONLY strict JSON. No markdown, no commentary.\n"
        "Allowed keys: normalized_query, title, platform, visual_intent, use_active_subject, confidence.\n"
        "Allowed visual_intent values: gameplay, title screen, cabinet, marquee, controls, box art, logo, fanart, flyer, visual, none.\n"
        "Rules:\n"
        "- Prefer the active subject when the user says things like that, it, those, this version, what about, screen capture, screenshot, screen shot, or screen grab.\n"
        "- Treat screenshot-like phrasing as gameplay unless the user clearly asked for a title screen.\n"
        "- Normalize speech-to-text drift when strongly implied by the message or conversation, but do not invent an unrelated game title.\n"
        "- Without an active subject, prefer the base title that was actually implied by the user's words. Do not add prefixes or sequel markers like Ms., Super, Jr., Deluxe, II, or 3 unless the user or conversation clearly indicated them.\n"
        "- If unsure about title or platform, leave them blank and keep normalized_query close to the user's wording.\n"
        "- normalized_query should be a concise search phrase for deterministic media lookup.\n"
        "- confidence must be one of high, medium, low.\n"
        "- use_active_subject must be true when the current request should inherit the active subject.\n"
    )
    user_prompt = (
        f"Current message: {user_text.strip()}\n"
        f"Active title: {active_title}\n"
        f"Active platform: {active_platform}\n"
        f"Active visual intent: {active_visual_intent}\n"
        f"Recent conversation:\n{history_block}\n\n"
        'Return JSON like: {"normalized_query":"show me gameplay screenshots of Ms. Pac-Man arcade","title":"Ms. Pac-Man","platform":"Arcade","visual_intent":"gameplay","use_active_subject":true,"confidence":"high"}'
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _interpret_dewey_request(
    *,
    user_text: str,
    history: List[DeweyChatTurn],
    active_subject: Optional[DeweyActiveSubject],
) -> Dict[str, Any]:
    default_query = _html_to_plain_text(user_text).strip()
    default_subject = _normalize_active_subject(active_subject)
    default = {
        "normalized_query": default_query,
        "title": "",
        "platform": "",
        "visual_intent": "none",
        "use_active_subject": bool(default_subject["title"]),
        "confidence": "low",
    }

    if not default_query:
        return default

    try:
        messages = _build_interpretation_messages(
            user_text=default_query,
            history=history,
            active_subject=active_subject,
        )
        raw = _call_gemini_custom(messages, max_tokens=256, temperature=0.1)
        parsed = _extract_json_object(raw)
    except Exception as exc:
        logger.warning("[Dewey] Intent interpretation failed: %s", exc)
        return default

    allowed_visual_intents = {
        "gameplay",
        "title screen",
        "cabinet",
        "marquee",
        "controls",
        "box art",
        "logo",
        "fanart",
        "flyer",
        "visual",
        "none",
    }
    allowed_confidence = {"high", "medium", "low"}

    normalized_query = str(parsed.get("normalized_query") or default_query).strip() or default_query
    title = str(parsed.get("title") or "").strip()
    platform = str(parsed.get("platform") or "").strip()
    visual_intent = str(parsed.get("visual_intent") or "none").strip().lower()
    if visual_intent not in allowed_visual_intents:
        visual_intent = "none"

    confidence = str(parsed.get("confidence") or "low").strip().lower()
    if confidence not in allowed_confidence:
        confidence = "low"

    use_active_subject = bool(parsed.get("use_active_subject"))

    return {
        "normalized_query": normalized_query,
        "title": title,
        "platform": platform,
        "visual_intent": visual_intent,
        "use_active_subject": use_active_subject,
        "confidence": confidence,
    }


def _extract_ai_text(result: Dict) -> str:
    """Extract text from Gemini or Anthropic-style response."""
    # Gemini format: candidates[0].content.parts[0].text
    candidates = result.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = (candidates[0].get("content") or {}).get("parts", [])
        if isinstance(parts, list) and parts:
            text = parts[0].get("text", "")
            if text:
                return text.strip()

    # Gemini proxy normalized format: text field
    if result.get("text"):
        return str(result["text"]).strip()

    # Anthropic format fallback: content[].text
    content = result.get("content")
    if isinstance(content, list):
        text_parts = [
            str(block.get("text", "")).strip()
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in text_parts if part).strip()

    if isinstance(content, str):
        return content.strip()

    response_text = result.get("response")
    if isinstance(response_text, str):
        return response_text.strip()

    return ""


def _call_gemini(messages: List[Dict[str, str]]) -> str:
    client = SecureAIClient()
    result = client.call_gemini(
        messages=messages,
        model=os.getenv("DEWEY_GEMINI_MODEL", "gemini-2.0-flash"),
        max_tokens=_dewey_chat_max_tokens(),
        temperature=0.7,
        panel="dewey",
    )
    reply = _extract_ai_text(result)
    if not reply:
        raise ValueError("Gemini proxy returned an empty Dewey response")
    return reply


def _call_gemini_custom(
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 256,
    temperature: float = 0.1,
) -> str:
    client = SecureAIClient()
    result = client.call_gemini(
        messages=messages,
        model=os.getenv("DEWEY_GEMINI_MODEL", "gemini-2.0-flash"),
        max_tokens=max_tokens,
        temperature=temperature,
        panel="dewey",
    )
    reply = _extract_ai_text(result)
    if not reply:
        raise ValueError("Gemini proxy returned an empty Dewey response")
    return reply


def _call_gemini_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> str:
    client = SecureAIClient()
    result = client.call_gemini(
        messages=messages,
        model=os.getenv("DEWEY_GEMINI_MODEL", "gemini-2.0-flash"),
        max_tokens=1024,
        temperature=0.7,
        panel="dewey",
        tools=tools,
    )
    # Check for tool_use in Claude-format response
    content = result.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return json.dumps({
                    "functionCall": {
                        "name": block.get("name", ""),
                        "args": block.get("input", {})
                    },
                    "text": "".join(
                        b.get("text", "") for b in content
                        if b.get("type") == "text"
                    )
                })
    return _extract_ai_text(result) or ""


async def _call_gemini_grounded(
    messages: List[Dict[str, Any]],
) -> str:
    """
    Retry a Gemini call with Google Search grounding enabled.
    Routes through SecureAIClient -> Supabase gemini-proxy.
    Used when the initial reply contains uncertainty markers.
    """
    try:
        grounded = await asyncio.to_thread(
            _call_gemini_with_tools,
            messages,
            [{"google_search": {}}],
        )
        if grounded:
            logger.info(
                "[dewey] Grounded reply received (%d chars)",
                len(grounded),
            )
        return grounded
    except Exception as exc:
        logger.warning(
            "[dewey] Grounded call failed: %s", exc
        )
        return ""


async def _stream_sse(
    reply: str,
    chunk_size: int = 160,
    gallery_images: Optional[List[str]] = None,
):
    for start in range(0, len(reply), chunk_size):
        chunk = reply[start:start + chunk_size]
        yield f"data: {json.dumps({'delta': chunk})}\n\n"
        await asyncio.sleep(0)
    done: Dict[str, Any] = {"done": True}
    if gallery_images:
        done["gallery_images"] = gallery_images
    yield f"data: {json.dumps(done)}\n\n"


@router.post("/trivia/collection")
async def dewey_collection_trivia(request: Request, payload: CollectionTriviaRequest):
    require_scope(request, "state")

    requested_count = payload.count or 10
    launchbox_games = _load_launchbox_games()
    if not launchbox_games:
        logger.warning("Collection trivia falling back to static questions because LaunchBox cache is unavailable")
        fallback = _load_static_collection_questions(requested_count)
        return {
            "questions": fallback,
            "count": len(fallback),
            "source": "static_fallback",
        }

    try:
        generated = await asyncio.to_thread(generate_collection_trivia, launchbox_games, requested_count)
    except Exception as exc:
        logger.warning("Collection trivia generation failed; using static fallback: %s", exc)
        generated = []

    questions = _normalize_collection_questions(generated)
    if len(questions) < requested_count:
        logger.warning(
            "Collection trivia returned %s/%s AI questions; topping up with static fallback",
            len(questions),
            requested_count,
        )
        fallback = _load_static_collection_questions(requested_count)
        used_ids = {question["id"] for question in questions}
        for item in fallback:
            if len(questions) >= requested_count:
                break
            if item.get("id") in used_ids:
                continue
            questions.append(item)
            used_ids.add(item.get("id"))

    return {
        "questions": questions[:requested_count],
        "count": min(len(questions), requested_count),
        "source": "launchbox_ai" if generated else "static_fallback",
    }


@router.post("/interpret")
async def dewey_interpret(request: Request, payload: DeweyInterpretRequest):
    require_scope(request, "state")

    result = await asyncio.to_thread(
        _interpret_dewey_request,
        user_text=payload.message.strip(),
        history=payload.conversation_history,
        active_subject=payload.active_subject,
    )
    return result


@router.post("/chat")
async def dewey_chat(request: Request, payload: DeweyChatRequest):
    require_scope(request, "state")

    user_name = (payload.user_name or "Guest").strip() or "Guest"
    preference_summary = (payload.preference_summary or "").strip() or _DEFAULT_PREFERENCE_SUMMARY
    user_message = payload.message.strip()

    try:
        system_prompt = _render_system_prompt(user_name, preference_summary)
        active_subject_context = _build_active_subject_context(payload.active_subject)
        if active_subject_context:
            system_prompt += active_subject_context
        variant_context = _build_variant_context(
            user_message,
            payload.conversation_history,
            payload.active_subject,
        )
        if variant_context:
            system_prompt += variant_context
        news_context = await _build_news_context(user_message)
        if news_context:
            system_prompt += news_context
        messages = _build_messages(
            history=payload.conversation_history,
            system_prompt=system_prompt,
            user_text=user_message,
        )
        reply = await asyncio.to_thread(
            _call_gemini_with_tools, messages, DEWEY_MEDIA_TOOL
        )

        # Google Search grounding fallback
        reply_lower = reply.lower()
        if any(
            marker in reply_lower
            for marker in _UNCERTAINTY_MARKERS
        ):
            logger.info(
                "[dewey] Uncertainty detected - "
                "retrying with Google Search grounding"
            )
            grounded = await _call_gemini_grounded(messages)
            if grounded:
                reply = grounded
        # End Google Search grounding fallback

        # Structured tool-use image enrichment
        gallery_images: List[str] = []
        try:
            tool_result = _extract_tool_call(reply, "show_game_media")
            if tool_result:
                reply = tool_result.get("clean_reply", reply)
                game_title = tool_result.get("game_title", "")
                media_type = tool_result.get("media_type", "any")
                if game_title:
                    image_url = _resolve_local_image(game_title, media_type)
                    gallery_images = [image_url] if image_url else []
            else:
                # Fallback: legacy tag parse for backward compatibility
                clean_reply, game_title, media_type = _parse_media_tag(reply)
                if game_title:
                    reply = clean_reply
                    image_url = _resolve_local_image(game_title, media_type)
                    gallery_images = [image_url] if image_url else []
        except Exception:
            pass
        # End structured tool-use image enrichment
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Dewey chat failed")
        raise HTTPException(status_code=500, detail=f"Dewey chat failed: {exc}") from exc


    return StreamingResponse(
        _stream_sse(reply, gallery_images=gallery_images),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
