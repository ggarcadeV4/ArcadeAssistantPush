"""FastAPI router for Dewey profiles."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
from typing import Any, Deque, DefaultDict, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field

from backend.services.dewey.service import (
    DeweyService,
    ProfileCreate,
    ProfileData,
    ProfileUpdate,
    get_dewey_service,
)
from backend.services.drive_a_ai_client import SecureAIClient
from backend.services.policies import require_scope

router = APIRouter(prefix="/api/local/dewey", tags=["dewey"])
logger = logging.getLogger(__name__)


class SimpleRateLimiter:
    """In-memory limiter to guard Dewey profile writes."""

    def __init__(self, times: int, seconds: int) -> None:
        self.times = times
        self.seconds = seconds
        self._hits: DefaultDict[str, Deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> None:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > self.seconds:
            window.popleft()
        if len(window) >= self.times:
            reset_in = self.seconds - (now - window[0])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {int(reset_in)}s.",
            )
        window.append(now)


CREATE_LIMITER = SimpleRateLimiter(times=5, seconds=60)
UPDATE_LIMITER = SimpleRateLimiter(times=10, seconds=60)


def _extract_gemini_text(result: Dict[str, Any]) -> str:
    """Extract text from Gemini API response."""
    # Gemini format: candidates[0].content.parts[0].text
    candidates = result.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ]
        if text_parts:
            return "\n".join(text_parts).strip()

    # Fallback: try Anthropic-style format (in case of proxy normalization)
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

    # Last resort: check for message.content or response
    message = result.get("message")
    if isinstance(message, dict):
        nested = message.get("content")
        if isinstance(nested, str):
            return nested.strip()

    response_text = result.get("response")
    if isinstance(response_text, str):
        return response_text.strip()

    return ""


def _call_gemini(
    messages: List[Dict[str, str]],
    *,
    model: str = "gemini-2.0-flash",
    max_tokens: int = 260,
    temperature: float = 0.4,
    panel: str = "dewey",
) -> str:
    client = SecureAIClient()
    result = client.call_gemini(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        panel=panel,
    )
    reply = _extract_gemini_text(result)
    if not reply:
        raise ValueError("Gemini proxy returned an empty Dewey response")
    return reply


@router.get("/profiles/{user_id}", response_model=ProfileData)
async def get_profile(user_id: str, service: DeweyService = Depends(get_dewey_service)):
    profile = await asyncio.to_thread(service.get_profile, user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/profiles", response_model=ProfileData, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: ProfileCreate, service: DeweyService = Depends(get_dewey_service)):
    CREATE_LIMITER.hit(payload.user_id)
    return await asyncio.to_thread(service.create_profile, payload)


@router.put("/profiles/{user_id}", response_model=ProfileData)
async def update_profile(
    user_id: str,
    payload: ProfileUpdate,
    service: DeweyService = Depends(get_dewey_service),
):
    UPDATE_LIMITER.hit(user_id)
    return await asyncio.to_thread(service.update_profile, user_id, payload)


# ============================================================================
# CHAT ENDPOINT
# ============================================================================

# ============================================================================
# TRIVIA ENDPOINTS
# ============================================================================

# Paths
TRIVIA_DB_PATH = os.path.join(os.path.dirname(__file__), "../../frontend/src/panels/dewey/trivia/triviaDatabase.json")
PROFILES_ROOT = os.getenv("AA_DRIVE_ROOT", "A:") + "/Arcade Assistant/profiles"


# Models
class TriviaQuestion(BaseModel):
    id: str
    category: List[str]
    difficulty: str
    question: str
    choices: List[str]
    correct_index: int
    metadata: dict


class TriviaStats(BaseModel):
    profile_id: str
    preferred_category: Optional[str] = "mixed"
    preferred_difficulty: Optional[str] = "medium"
    lifetime: dict
    recent_sessions: List[dict]


class SaveStatsRequest(BaseModel):
    profile_id: str
    session_data: dict


class HandoffRequest(BaseModel):
    target: str
    summary: str
    timestamp: str


def get_collection_sample(count: int = 20) -> List[Dict[str, Any]]:
    """
    Return a randomized sample of real LaunchBox games.

    Prefers played games (play_count > 0). Falls back to the general library
    if too few played titles are available. Returns an empty list on any cache
    or parser failure so callers can degrade gracefully.
    """
    try:
        from backend.services import launchbox_cache
        from backend.services.launchbox_parser import parser

        cache_stats = parser.get_cache_stats()
        if cache_stats.get("is_mock_data"):
            return []

        raw_games = launchbox_cache.get_games()
    except Exception as exc:
        logger.warning("Failed to load LaunchBox cache for Dewey collection trivia: %s", exc)
        return []

    if not raw_games:
        return []

    normalized_games: List[Dict[str, Any]] = []
    for game in raw_games:
        title = getattr(game, "title", None)
        platform = getattr(game, "platform", None)
        genre = getattr(game, "genre", None)
        year = getattr(game, "year", None)

        if not title or not platform:
            continue

        normalized_games.append({
            "title": title,
            "genre": genre or "Unknown",
            "platform": platform,
            "year": year,
            "developer": getattr(game, "developer", None) or "",
            "publisher": getattr(game, "publisher", None) or "",
            "play_count": int(getattr(game, "play_count", 0) or 0),
        })

    if not normalized_games:
        return []

    played_games = [game for game in normalized_games if game.get("play_count", 0) > 0]
    sample_pool = played_games if len(played_games) >= count else normalized_games

    if len(sample_pool) <= count:
        shuffled = list(sample_pool)
        random.shuffle(shuffled)
        return shuffled

    return random.sample(sample_pool, count)


def _extract_json_block(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty AI response while generating collection trivia")

    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced_match:
        raw = fenced_match.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end + 1])

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end + 1])

    raise ValueError("Collection trivia generator returned invalid JSON")


def _normalize_collection_questions(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("questions", [])
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("Collection trivia payload must be a JSON array or object with questions")

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items[:10], start=1):
        if not isinstance(item, dict):
            continue

        question_text = str(item.get("question", "")).strip()
        options = item.get("options", [])
        answer = str(item.get("answer", "")).strip()
        difficulty = str(item.get("difficulty", "medium")).strip().lower() or "medium"
        game_title = str(item.get("game_title", "")).strip()

        if not question_text or len(options) != 4 or not answer:
            continue

        normalized_options = [str(option).strip() for option in options]
        try:
            correct_index = normalized_options.index(answer)
        except ValueError:
            letter_match = re.fullmatch(r"([A-D])(?:[).:\s].*)?", answer, re.IGNORECASE)
            if letter_match:
                correct_index = ord(letter_match.group(1).upper()) - ord("A")
            else:
                continue

        if correct_index < 0 or correct_index >= len(normalized_options):
            continue

        if difficulty not in {"easy", "medium", "hard"}:
            difficulty = "medium"

        normalized.append({
            "id": f"collection_dynamic_{index:03d}",
            "category": ["collection"],
            "difficulty": difficulty,
            "question": question_text,
            "choices": normalized_options,
            "correct_index": correct_index,
            "metadata": {
                "game_title": game_title,
                "generated": True,
            },
        })

    if len(normalized) != 10:
        raise ValueError(f"Expected 10 collection questions, got {len(normalized)}")

    return normalized


def _build_collection_trivia_prompt(sample_games: List[Dict[str, Any]]) -> str:
    sample_blob = json.dumps(sample_games, indent=2, ensure_ascii=False)
    return (
        "You are generating Arcade Assistant trivia for Dewey's 'Your Collection' mode.\n"
        "Use ONLY the games in the provided LaunchBox sample.\n"
        "Do NOT invent games, sequels, platforms, or facts outside this list.\n"
        "Generate exactly 10 multiple-choice trivia questions.\n"
        "Question mix must include release year, developer, sequel, platform-original, "
        "genre classification, and hardware milestone style questions where the sample supports them.\n"
        "Across the 10 questions, target a difficulty split of roughly 3 easy, 4 medium, 3 hard.\n"
        "Every question must be specifically about a title present in the sample.\n"
        "Return ONLY valid JSON.\n"
        "JSON format:\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "question": "string",\n'
        '      "options": ["A", "B", "C", "D"],\n'
        '      "answer": "must exactly match one option",\n'
        '      "difficulty": "easy|medium|hard",\n'
        '      "game_title": "title from sample"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "LaunchBox sample:\n"
        f"{sample_blob}"
    )


# Utility Functions
def load_trivia_database() -> List[dict]:
    """Load trivia questions from JSON database"""
    try:
        with open(TRIVIA_DB_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("questions", [])
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Trivia database not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid trivia database format")


def get_tendency_file_path(profile_id: str) -> str:
    """Get the path to a profile's tendency file"""
    return os.path.join(PROFILES_ROOT, profile_id, "tendencies.json")


def load_tendencies(profile_id: str) -> dict:
    """Load tendencies.json for a profile"""
    file_path = get_tendency_file_path(profile_id)

    if not os.path.exists(file_path):
        # Return default structure if file doesn't exist
        return {
            "profile_id": profile_id,
            "dewey": {
                "tournament_history": [],
                "trivia_stats": {
                    "preferred_category": "mixed",
                    "preferred_difficulty": "medium",
                    "lifetime": {
                        "total_questions": 0,
                        "total_correct": 0,
                        "best_score": 0,
                        "best_streak": 0
                    },
                    "recent_sessions": []
                }
            }
        }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid tendency file for profile {profile_id}")


def save_tendencies(profile_id: str, tendencies: dict):
    """Save tendencies.json for a profile"""
    file_path = get_tendency_file_path(profile_id)

    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Update metadata
    if "meta" not in tendencies:
        tendencies["meta"] = {}
    tendencies["meta"]["version"] = 1
    tendencies["meta"]["last_modified"] = datetime.utcnow().isoformat() + "Z"

    # Write file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(tendencies, f, indent=2, ensure_ascii=False)


@router.get("/trivia/questions")
async def get_trivia_questions(
    category: Optional[str] = "mixed",
    difficulty: Optional[str] = None,
    limit: int = 10
):
    """
    Get trivia questions filtered by category and difficulty

    - **category**: arcade, console, genre, decade, mixed (default: mixed)
    - **difficulty**: easy, medium, hard (optional - returns all if not specified)
    - **limit**: number of questions to return (default: 10)
    """
    questions = load_trivia_database()

    # Filter by category
    if category != "mixed":
        questions = [q for q in questions if category in q.get("category", [])]

    # Filter by difficulty
    if difficulty:
        questions = [q for q in questions if q.get("difficulty") == difficulty]

    # Shuffle and limit
    random.shuffle(questions)
    questions = questions[:limit]

    if not questions:
        raise HTTPException(status_code=404, detail="No questions found matching criteria")

    return {
        "questions": questions,
        "count": len(questions),
        "filters": {
            "category": category,
            "difficulty": difficulty
        }
    }


@router.get("/trivia/collection-questions")
async def get_collection_questions(limit: int = 10):
    """
    Get trivia questions based on LaunchBox collection

    TODO: Integrate with LaunchBox parser to generate questions like:
    - "Which year was [game in your collection] released?"
    - "What platform is [game] on?"
    - "What genre is [game]?"

    For now, returns placeholder questions tagged as 'collection'
    """
    # TODO: Import launchbox_parser and generate dynamic questions
    # from backend.services.launchbox_parser import get_game_cache

    return {
        "questions": [],
        "count": 0,
        "note": "LaunchBox integration coming soon - will generate questions from your game collection"
    }


@router.get("/trivia/stats/{profile_id}")
async def get_trivia_stats(profile_id: str):
    """
    Get trivia statistics for a profile
    """
    tendencies = load_tendencies(profile_id)

    trivia_stats = tendencies.get("dewey", {}).get("trivia_stats", {
        "preferred_category": "mixed",
        "preferred_difficulty": "medium",
        "lifetime": {
            "total_questions": 0,
            "total_correct": 0,
            "best_score": 0,
            "best_streak": 0
        },
        "recent_sessions": []
    })

    return {
        "profile_id": profile_id,
        "stats": trivia_stats
    }


@router.post("/trivia/save-stats")
async def save_trivia_stats(
    request: SaveStatsRequest,
    x_device_id: Optional[str] = Header(None)
):
    """
    Save trivia session stats to tendency file

    Expected session_data format:
    {
        "category": "arcade",
        "difficulty": "medium",
        "questions_answered": 10,
        "correct_answers": 7,
        "score": 1400,
        "best_streak": 4,
        "timestamp": "ISO 8601 timestamp"
    }
    """
    tendencies = load_tendencies(request.profile_id)

    # Ensure dewey namespace exists
    if "dewey" not in tendencies:
        tendencies["dewey"] = {
            "tournament_history": [],
            "trivia_stats": {
                "preferred_category": "mixed",
                "preferred_difficulty": "medium",
                "lifetime": {
                    "total_questions": 0,
                    "total_correct": 0,
                    "best_score": 0,
                    "best_streak": 0
                },
                "recent_sessions": []
            }
        }

    trivia_stats = tendencies["dewey"].get("trivia_stats", {})

    # Update preferred settings
    session = request.session_data
    trivia_stats["preferred_category"] = session.get("category", "mixed")
    trivia_stats["preferred_difficulty"] = session.get("difficulty", "medium")

    # Update lifetime stats
    lifetime = trivia_stats.get("lifetime", {
        "total_questions": 0,
        "total_correct": 0,
        "best_score": 0,
        "best_streak": 0
    })

    lifetime["total_questions"] += session.get("questions_answered", 0)
    lifetime["total_correct"] += session.get("correct_answers", 0)
    lifetime["best_score"] = max(lifetime.get("best_score", 0), session.get("score", 0))
    lifetime["best_streak"] = max(lifetime.get("best_streak", 0), session.get("best_streak", 0))

    trivia_stats["lifetime"] = lifetime

    # Add to recent sessions (keep last 10)
    recent = trivia_stats.get("recent_sessions", [])
    recent.append({
        **session,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    trivia_stats["recent_sessions"] = recent[-10:]  # Keep only last 10 sessions

    # Save back to tendencies
    tendencies["dewey"]["trivia_stats"] = trivia_stats
    save_tendencies(request.profile_id, tendencies)

    return {
        "success": True,
        "profile_id": request.profile_id,
        "updated_stats": trivia_stats,
        "device_id": x_device_id
    }


@router.post("/handoff")
async def save_handoff(
    handoff: HandoffRequest,
    request: Request
):
    """
    Save Dewey handoff JSON to target panel directory
    """
    drive_root = Path(request.app.state.drive_root)
    target_dir = drive_root / "handoff" / handoff.target

    # Create directory if needed
    target_dir.mkdir(parents=True, exist_ok=True)

    # Write handoff.json
    handoff_file = target_dir / "handoff.json"
    with open(handoff_file, 'w', encoding='utf-8') as f:
        json.dump({
            "target": handoff.target,
            "summary": handoff.summary,
            "timestamp": handoff.timestamp
        }, f, indent=2, ensure_ascii=False)

    return {"status": "ok"}


@router.get("/handoff/{target}")
async def get_handoff(
    target: str,
    request: Request
):
    """
    Read Dewey handoff JSON from target panel directory
    """
    drive_root = Path(request.app.state.drive_root)
    handoff_path = drive_root / "handoff" / target / "handoff.json"

    # Return None if file doesn't exist
    if not handoff_path.exists():
        return {"handoff": None}

    # Load and return JSON
    try:
        with open(handoff_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"handoff": data}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid handoff JSON for target {target}")


# ============================================================================
# AUTO-TRIVIA GENERATION FROM NEWS
# ============================================================================

from backend.services.dewey.trivia_generator import (
    generate_trivia_from_headline,
    generate_trivia_with_ai,
    get_fresh_trivia,
    add_generated_questions,
    get_generation_stats,
)


@router.get("/trivia/fresh")
async def get_fresh_trivia_questions(limit: int = 10):
    """
    Get fresh trivia questions generated from recent gaming news.
    
    These questions are auto-generated and expire after 30 days
    to keep content current and relevant.
    """
    questions = get_fresh_trivia(limit)
    stats = get_generation_stats()
    
    return {
        "questions": questions,
        "count": len(questions),
        "pool_size": stats["total_questions"],
        "last_generated": stats["last_generated"]
    }


@router.post("/trivia/generate")
async def generate_trivia_from_news(
    request: Request,
    limit: int = 5
):
    """
    Generate new trivia questions from recent gaming news headlines.
    
    This fetches the latest headlines and creates trivia questions.
    Questions are stored and will expire after 30 days.
    
    Requires news headlines to be available (gaming_news router).
    """
    try:
        # Fetch recent headlines
        from backend.routers.gaming_news import fetch_all_headlines
        headlines = await fetch_all_headlines()
        
        if not headlines:
            return {
                "success": False,
                "error": "No headlines available",
                "generated": 0
            }
        
        # Generate questions from headlines
        generated = []
        for h in headlines[:limit * 2]:  # Process more to get enough valid ones
            q = generate_trivia_from_headline(
                h.get('title', ''),
                h.get('summary', ''),
                h.get('source', 'Unknown'),
                h.get('categories', [])
            )
            if q:
                generated.append(q)
            if len(generated) >= limit:
                break
        
        # Add to pool
        added = add_generated_questions(generated)
        stats = get_generation_stats()
        
        return {
            "success": True,
            "generated": len(generated),
            "added_to_pool": added,
            "pool_size": stats["total_questions"],
            "sample": generated[:3] if generated else []
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trivia generation failed: {str(e)}")


@router.post("/trivia/generate-ai")
async def generate_trivia_with_ai_endpoint(
    request: Request,
    limit: int = 5
):
    """
    Generate trivia questions using AI from recent gaming news.
    
    This uses Claude to create more sophisticated, engaging questions.
    Requires AI client to be configured.
    """
    try:
        # Fetch recent headlines
        from backend.routers.gaming_news import fetch_all_headlines
        headlines = await fetch_all_headlines()
        
        if not headlines:
            return {
                "success": False,
                "error": "No headlines available",
                "generated": 0
            }
        
        # Try AI generation
        generated = await generate_trivia_with_ai(headlines[:10])
        
        if generated:
            added = add_generated_questions(generated)
            stats = get_generation_stats()
            
            return {
                "success": True,
                "method": "ai",
                "generated": len(generated),
                "added_to_pool": added,
                "pool_size": stats["total_questions"],
                "sample": generated[:3]
            }
        else:
            # Fall back to pattern-based
            generated = []
            for h in headlines[:limit * 2]:
                q = generate_trivia_from_headline(
                    h.get('title', ''),
                    h.get('summary', ''),
                    h.get('source', 'Unknown'),
                    h.get('categories', [])
                )
                if q:
                    generated.append(q)
                if len(generated) >= limit:
                    break
            
            added = add_generated_questions(generated)
            stats = get_generation_stats()
            
            return {
                "success": True,
                "method": "pattern",
                "note": "AI unavailable, used pattern-based generation",
                "generated": len(generated),
                "added_to_pool": added,
                "pool_size": stats["total_questions"]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI trivia generation failed: {str(e)}")


@router.get("/trivia/generation-stats")
async def get_trivia_generation_stats():
    """
    Get statistics about auto-generated trivia.
    """
    return get_generation_stats()


# ============================================================================
# AUTO-TRIVIA SCHEDULER (Self-Updating Engine)
# ============================================================================

from backend.services.dewey.trivia_scheduler import get_trivia_scheduler


@router.get("/trivia/scheduler/status")
async def get_scheduler_status():
    """
    Get the auto-trivia scheduler status.
    
    The scheduler automatically generates fresh trivia from gaming news
    on a configurable schedule (default: daily).
    """
    scheduler = get_trivia_scheduler()
    return scheduler.get_status()


@router.post("/trivia/scheduler/run")
async def run_scheduler_now():
    """
    Manually trigger trivia generation immediately.
    
    Useful for testing or when you want fresh trivia right now.
    """
    scheduler = get_trivia_scheduler()
    result = await scheduler.run_now()
    return {
        "triggered": True,
        "result": result,
        "status": scheduler.get_status()
    }


@router.post("/trivia/scheduler/configure")
async def configure_scheduler(
    interval_hours: Optional[int] = None,
    questions_per_run: Optional[int] = None,
    enabled: Optional[bool] = None
):
    """
    Configure the auto-trivia scheduler.
    
    Args:
        interval_hours: Hours between auto-generation runs (default: 24)
        questions_per_run: Number of questions to generate each run (default: 10)
        enabled: Enable/disable the scheduler
    
    Example:
        POST /trivia/scheduler/configure?interval_hours=12&questions_per_run=15
    """
    scheduler = get_trivia_scheduler()
    return scheduler.configure(
        interval_hours=interval_hours,
        questions_per_run=questions_per_run,
        enabled=enabled
    )


@router.post("/trivia/scheduler/start")
async def start_scheduler():
    """Start the auto-trivia scheduler."""
    scheduler = get_trivia_scheduler()
    scheduler.start()
    return {"status": "started", "scheduler": scheduler.get_status()}


@router.post("/trivia/scheduler/stop")
async def stop_scheduler():
    """Stop the auto-trivia scheduler."""
    scheduler = get_trivia_scheduler()
    scheduler.stop()
    return {"status": "stopped", "scheduler": scheduler.get_status()}
