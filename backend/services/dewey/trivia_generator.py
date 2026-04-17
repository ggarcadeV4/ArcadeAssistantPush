"""
Auto Trivia Generator for Dewey
Generates fresh trivia questions from gaming news headlines using AI.
Questions are tagged with expiration dates to stay relevant.
"""

import json
import logging
import os
import hashlib
import random
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.constants.drive_root import get_drive_root
from backend.services.drive_a_ai_client import SecureAIClient

logger = logging.getLogger(__name__)

# Path for generated trivia storage
GENERATED_TRIVIA_PATH = (
    get_drive_root(allow_cwd_fallback=True, context="trivia_generator")
    / "state"
    / "dewey"
    / "generated_trivia.json"
)

# How long generated trivia questions stay valid (days)
TRIVIA_EXPIRY_DAYS = 30

# Maximum questions to keep in the pool
MAX_GENERATED_QUESTIONS = 100
_COLLECTION_CATEGORY = "Your Collection"
_COLLECTION_DIFFICULTIES = ("easy", "medium", "hard")


def _load_generated_trivia() -> Dict[str, Any]:
    """Load the generated trivia database."""
    GENERATED_TRIVIA_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if not GENERATED_TRIVIA_PATH.exists():
        return {
            "questions": [],
            "last_generated": None,
            "total_generated": 0
        }
    
    try:
        with open(GENERATED_TRIVIA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.warning("Corrupt generated trivia file; recreating.")
        return {
            "questions": [],
            "last_generated": None,
            "total_generated": 0
        }


def _save_generated_trivia(data: Dict[str, Any]) -> None:
    """Save the generated trivia database."""
    GENERATED_TRIVIA_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(GENERATED_TRIVIA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _generate_question_id(headline: str) -> str:
    """Generate a unique ID for a question based on headline."""
    return f"news_{hashlib.md5(headline.encode()).hexdigest()[:12]}"


def _extract_anthropic_text(result: Dict[str, Any]) -> str:
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

    message = result.get("message")
    if isinstance(message, dict):
        nested = message.get("content")
        if isinstance(nested, str):
            return nested.strip()
        if isinstance(nested, list):
            text_parts = [
                str(block.get("text", "")).strip()
                for block in nested
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(part for part in text_parts if part).strip()

    response_text = result.get("response")
    if isinstance(response_text, str):
        return response_text.strip()

    return ""


def _extract_json_payload(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty AI response while generating collection trivia")

    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced_match:
        raw = fenced_match.group(1).strip()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Collection trivia generator returned invalid JSON")
        payload = json.loads(raw[start:end + 1])

    if not isinstance(payload, dict):
        raise ValueError("Collection trivia generator must return a JSON object")
    return payload


def _normalize_release_year(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _normalize_collection_game(game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(game, dict):
        return None

    title = str(game.get("title") or "").strip()
    if not title:
        return None

    platform = str(game.get("platform") or "Unknown platform").strip()
    developer = str(game.get("developer") or "Unknown developer").strip()
    publisher = str(game.get("publisher") or "Unknown publisher").strip()
    genre = str(game.get("genre") or "Unknown genre").strip()
    release_year = _normalize_release_year(
        game.get("release_year") or game.get("year") or game.get("releaseYear")
    )

    return {
        "title": title,
        "platform": platform,
        "developer": developer,
        "publisher": publisher,
        "genre": genre,
        "release_year": release_year,
    }


def _weighted_collection_sample(games: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    normalized_games = [item for item in (_normalize_collection_game(game) for game in games) if item]
    if not normalized_games or count <= 0:
        return []

    platform_counts = Counter(game["platform"] for game in normalized_games)
    developer_counts = Counter(game["developer"] for game in normalized_games)
    publisher_counts = Counter(game["publisher"] for game in normalized_games)
    genre_counts = Counter(game["genre"] for game in normalized_games)

    weighted_pool = []
    for game in normalized_games:
        weight = 1.0
        weight += 2.0 / platform_counts[game["platform"]]
        weight += 2.0 / developer_counts[game["developer"]]
        weight += 1.5 / publisher_counts[game["publisher"]]
        weight += 1.5 / genre_counts[game["genre"]]
        weighted_pool.append({"game": game, "weight": max(weight, 0.1)})

    selected: List[Dict[str, Any]] = []
    target = min(count, len(weighted_pool))
    while weighted_pool and len(selected) < target:
        weights = [item["weight"] for item in weighted_pool]
        index = random.choices(range(len(weighted_pool)), weights=weights, k=1)[0]
        selected.append(weighted_pool.pop(index)["game"])

    return selected


def _build_collection_question_prompt(game: Dict[str, Any]) -> str:
    release_year = game.get("release_year")
    release_text = str(release_year) if release_year else "Unknown"
    game_blob = json.dumps(
        {
            "title": game.get("title"),
            "platform": game.get("platform"),
            "developer": game.get("developer"),
            "publisher": game.get("publisher"),
            "release_year": release_text,
            "genre": game.get("genre"),
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        "Generate exactly one multiple-choice trivia question for Dewey's 'Your Collection' category.\n"
        "Use only the game metadata below. Do not invent sequels, platforms, studios, or dates.\n"
        "The question may focus on the title, release year, developer, publisher, genre, platform, or a safe gameplay-style fact that is broadly associated with the game.\n"
        "Return JSON only in this exact format:\n"
        "{\n"
        '  "question": "string",\n'
        '  "options": ["A", "B", "C", "D"],\n'
        '  "correct_answer": "must exactly match one option",\n'
        '  "difficulty": "easy|medium|hard",\n'
        '  "category": "Your Collection",\n'
        '  "game_title": "exact title"\n'
        "}\n\n"
        "Game metadata:\n"
        f"{game_blob}\n"
    )


def _normalize_collection_question(item: Dict[str, Any], fallback_game: Dict[str, Any]) -> Dict[str, Any]:
    question = str(item.get("question") or "").strip()
    options = item.get("options")
    correct_answer = str(item.get("correct_answer") or "").strip()
    difficulty = str(item.get("difficulty") or "medium").strip().lower()
    game_title = str(item.get("game_title") or fallback_game.get("title") or "").strip()

    if not question:
        raise ValueError("Collection trivia response omitted question text")
    if not isinstance(options, list) or len(options) != 4:
        raise ValueError("Collection trivia response must include four options")

    normalized_options = [str(option).strip() for option in options]
    if not correct_answer or correct_answer not in normalized_options:
        raise ValueError("Collection trivia response returned an invalid correct_answer")
    if difficulty not in _COLLECTION_DIFFICULTIES:
        difficulty = "medium"

    return {
        "question": question,
        "options": normalized_options,
        "correct_answer": correct_answer,
        "difficulty": difficulty,
        "category": _COLLECTION_CATEGORY,
        "game_title": game_title or fallback_game.get("title", ""),
    }


def _generate_single_collection_question(client: SecureAIClient, game: Dict[str, Any]) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an exacting arcade trivia writer. "
                "Return valid JSON only, with no markdown or commentary."
            ),
        },
        {
            "role": "user",
            "content": _build_collection_question_prompt(game),
        },
    ]
    result = client.call_anthropic(
        messages=messages,
        model=os.getenv("DEWEY_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        max_tokens=400,
        temperature=0.4,
        panel="dewey",
    )
    reply = _extract_anthropic_text(result)
    payload = _extract_json_payload(reply)
    return _normalize_collection_question(payload, game)


def generate_collection_trivia(game_list: list[dict], count: int = 10) -> list[dict]:
    """
    Generate collection-specific trivia using one Anthropic call per question.

    Args:
        game_list: LaunchBox game dicts with title/platform/developer/publisher/release_year/genre data.
        count: Number of questions to generate.

    Returns:
        A list of collection trivia question dicts.
    """
    if not game_list or count <= 0:
        return []

    candidates = _weighted_collection_sample(game_list, max(count * 2, count))
    if not candidates:
        return []

    client = SecureAIClient()
    generated: List[Dict[str, Any]] = []

    for game in candidates:
        if len(generated) >= count:
            break
        try:
            generated.append(_generate_single_collection_question(client, game))
        except Exception as exc:
            logger.warning("Collection trivia generation failed for '%s': %s", game.get("title"), exc)

    return generated


def _prune_expired_questions(questions: List[Dict]) -> List[Dict]:
    """Remove expired questions from the pool."""
    now = datetime.now(timezone.utc)
    valid = []
    
    for q in questions:
        expires = q.get("expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                if exp_dt > now:
                    valid.append(q)
            except:
                valid.append(q)  # Keep if can't parse
        else:
            valid.append(q)
    
    return valid


def generate_trivia_from_headline(
    headline: str,
    summary: str,
    source: str,
    categories: List[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate a trivia question from a news headline.
    
    This creates a simple fill-in-the-blank or factual question
    without requiring external AI calls (for offline operation).
    
    For more sophisticated questions, use generate_trivia_with_ai().
    """
    if not headline or len(headline) < 20:
        return None
    
    # Simple pattern-based question generation
    question_id = _generate_question_id(headline)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=TRIVIA_EXPIRY_DAYS)
    
    # Extract potential answers from headline
    # This is a simplified version - AI would do better
    words = headline.split()
    
    # Look for game titles (usually capitalized multi-word phrases)
    potential_games = []
    current_phrase = []
    for word in words:
        if word[0].isupper() and word.lower() not in ['the', 'a', 'an', 'in', 'on', 'for', 'to', 'is', 'are', 'has', 'new', 'first', 'last']:
            current_phrase.append(word)
        else:
            if len(current_phrase) >= 1:
                potential_games.append(' '.join(current_phrase))
            current_phrase = []
    if current_phrase:
        potential_games.append(' '.join(current_phrase))
    
    # Filter to likely game titles (2+ words or known patterns)
    game_candidates = [g for g in potential_games if len(g.split()) >= 2 or len(g) > 5]
    
    if not game_candidates:
        return None
    
    # Create question about the headline
    correct_answer = game_candidates[0]
    
    # Generate decoy answers (these would be better with AI)
    decoys = ["Elden Ring", "Zelda", "Final Fantasy XVI", "Cyberpunk 2077", 
              "Baldur's Gate 3", "Starfield", "Spider-Man 2", "Hogwarts Legacy"]
    decoys = [d for d in decoys if d.lower() != correct_answer.lower()][:3]
    
    if len(decoys) < 3:
        return None
    
    # Randomize answer position
    import random
    choices = decoys + [correct_answer]
    random.shuffle(choices)
    correct_index = choices.index(correct_answer)
    
    # Create the question
    masked_headline = headline.replace(correct_answer, "______")
    
    return {
        "id": question_id,
        "category": ["news", "current"] + (categories or []),
        "difficulty": "medium",
        "question": f"Recent headline: '{masked_headline}' - What game is this about?",
        "choices": choices,
        "correct_index": correct_index,
        "metadata": {
            "source": source,
            "original_headline": headline,
            "generated_at": now.isoformat(),
            "type": "news_generated"
        },
        "expires_at": expires.isoformat()
    }


async def generate_trivia_with_ai(
    headlines: List[Dict[str, Any]],
    ai_client = None
) -> List[Dict[str, Any]]:
    """
    Generate trivia questions from headlines using AI.
    
    Args:
        headlines: List of headline dicts with 'title', 'summary', 'source'
        ai_client: Optional AI client for generation
    
    Returns:
        List of generated trivia questions
    """
    if not ai_client:
        # Try to import the AI client
        try:
            from ..drive_a_ai_client import chat_completion
        except ImportError:
            logger.warning("AI client not available for trivia generation")
            # Fall back to pattern-based generation
            questions = []
            for h in headlines[:10]:
                q = generate_trivia_from_headline(
                    h.get('title', ''),
                    h.get('summary', ''),
                    h.get('source', 'Unknown'),
                    h.get('categories', [])
                )
                if q:
                    questions.append(q)
            return questions
    
    # Build prompt for AI
    headlines_text = "\n".join([
        f"- {h['title']} (Source: {h['source']})"
        for h in headlines[:10]
    ])
    
    prompt = f"""Generate 5 trivia questions based on these recent gaming news headlines:

{headlines_text}

For each question, provide:
1. A clear, fun question that tests gaming knowledge
2. Four multiple choice answers (A, B, C, D)
3. The correct answer letter
4. Difficulty (easy/medium/hard)

Format each as JSON:
{{
  "question": "...",
  "choices": ["A", "B", "C", "D"],
  "correct_index": 0-3,
  "difficulty": "easy|medium|hard",
  "source_headline": "original headline this came from"
}}

Return as a JSON array of questions."""

    try:
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="claude-3-haiku-20240307"  # Fast, cheap model for generation
        )
        
        # Parse AI response
        content = response.get('content', '')
        
        # Try to extract JSON array from response
        import re
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            questions_raw = json.loads(json_match.group())
            
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=TRIVIA_EXPIRY_DAYS)
            
            questions = []
            for i, q in enumerate(questions_raw):
                questions.append({
                    "id": f"ai_news_{now.strftime('%Y%m%d')}_{i:03d}",
                    "category": ["news", "current", "ai_generated"],
                    "difficulty": q.get('difficulty', 'medium'),
                    "question": q['question'],
                    "choices": q['choices'],
                    "correct_index": q['correct_index'],
                    "metadata": {
                        "source_headline": q.get('source_headline', ''),
                        "generated_at": now.isoformat(),
                        "type": "ai_generated"
                    },
                    "expires_at": expires.isoformat()
                })
            
            return questions
    except Exception as e:
        logger.error(f"AI trivia generation failed: {e}")
    
    return []


def get_fresh_trivia(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get fresh/generated trivia questions.
    
    Args:
        limit: Maximum questions to return
    
    Returns:
        List of valid (non-expired) generated questions
    """
    data = _load_generated_trivia()
    questions = _prune_expired_questions(data.get("questions", []))
    
    # Save pruned list back
    data["questions"] = questions
    _save_generated_trivia(data)
    
    # Return random selection
    import random
    if len(questions) > limit:
        return random.sample(questions, limit)
    return questions


def add_generated_questions(questions: List[Dict[str, Any]]) -> int:
    """
    Add newly generated questions to the pool.
    
    Args:
        questions: List of question dicts to add
    
    Returns:
        Number of questions actually added (excluding duplicates)
    """
    data = _load_generated_trivia()
    existing_ids = {q['id'] for q in data.get("questions", [])}
    
    added = 0
    for q in questions:
        if q['id'] not in existing_ids:
            data["questions"].append(q)
            existing_ids.add(q['id'])
            added += 1
    
    # Prune expired and limit total
    data["questions"] = _prune_expired_questions(data["questions"])
    if len(data["questions"]) > MAX_GENERATED_QUESTIONS:
        # Keep most recent
        data["questions"] = sorted(
            data["questions"],
            key=lambda x: x.get("metadata", {}).get("generated_at", ""),
            reverse=True
        )[:MAX_GENERATED_QUESTIONS]
    
    data["last_generated"] = datetime.now(timezone.utc).isoformat()
    data["total_generated"] = data.get("total_generated", 0) + added
    
    _save_generated_trivia(data)
    
    return added


def get_generation_stats() -> Dict[str, Any]:
    """Get statistics about generated trivia."""
    data = _load_generated_trivia()
    questions = data.get("questions", [])
    
    # Count by type
    by_type = {}
    for q in questions:
        qtype = q.get("metadata", {}).get("type", "unknown")
        by_type[qtype] = by_type.get(qtype, 0) + 1
    
    return {
        "total_questions": len(questions),
        "total_ever_generated": data.get("total_generated", 0),
        "last_generated": data.get("last_generated"),
        "by_type": by_type,
        "expiry_days": TRIVIA_EXPIRY_DAYS,
        "max_pool_size": MAX_GENERATED_QUESTIONS
    }
