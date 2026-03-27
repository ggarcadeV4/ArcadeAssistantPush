"""Dedicated Dewey chat router using prompt files and Gemini proxy."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.drive_a_ai_client import SecureAIClient
from backend.services.dewey.trivia_generator import generate_collection_trivia
from backend.services.policies import require_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local/dewey", tags=["dewey-chat"])
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_prompt_cache: Dict[str, str] = {}
_knowledge_cache: Dict[str, str] = {}
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


class DeweyChatTurn(BaseModel):
    role: str
    content: Optional[str] = None
    text: Optional[str] = None


class DeweyChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    user_name: Optional[str] = "Guest"
    preference_summary: Optional[str] = None
    conversation_history: List[DeweyChatTurn] = Field(default_factory=list)


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
        max_tokens=1024,
        temperature=0.7,
        panel="dewey",
    )
    reply = _extract_ai_text(result)
    if not reply:
        raise ValueError("Gemini proxy returned an empty Dewey response")
    return reply


async def _stream_sse(reply: str, chunk_size: int = 160):
    for start in range(0, len(reply), chunk_size):
        chunk = reply[start:start + chunk_size]
        yield f"data: {json.dumps({'delta': chunk})}\n\n"
        await asyncio.sleep(0)
    yield "data: {\"done\":true}\n\n"


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


@router.post("/chat")
async def dewey_chat(request: Request, payload: DeweyChatRequest):
    require_scope(request, "state")

    user_name = (payload.user_name or "Guest").strip() or "Guest"
    preference_summary = (payload.preference_summary or "").strip() or _DEFAULT_PREFERENCE_SUMMARY
    user_message = payload.message.strip()

    try:
        system_prompt = _render_system_prompt(user_name, preference_summary)
        news_context = await _build_news_context(user_message)
        if news_context:
            system_prompt += news_context
        messages = _build_messages(
            history=payload.conversation_history,
            system_prompt=system_prompt,
            user_text=user_message,
        )
        reply = await asyncio.to_thread(_call_gemini, messages)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Dewey chat failed")
        raise HTTPException(status_code=500, detail=f"Dewey chat failed: {exc}") from exc

    return StreamingResponse(
        _stream_sse(reply),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
