"""Text-to-Speech (TTS) engine for Arcade OS — ElevenLabs streaming.

Provides async streaming TTS via the ElevenLabs v1 API.
Each persona has a unique voice_id stored in the database; this module
is voice_id-agnostic — the caller (server.py) resolves the correct ID.

Backend priority:
  1. ElevenLabs API (cloud, high-quality, streaming)
  2. (Future) pyttsx3 offline fallback

All audio is returned as chunked audio/mpeg (MP3) bytes.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger("arcade_os.tts")

# ── Constants ─────────────────────────────────────────────────────────────

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_turbo_v2_5"          # low-latency, high-quality
CHUNK_SIZE = 4096                             # bytes per yield

DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
}


# ── Availability ──────────────────────────────────────────────────────────

def check_tts_availability(api_key: Optional[str] = None) -> tuple[bool, str | None]:
    """Return (available, reason_if_not).

    Checks whether an ElevenLabs API key is present.
    Does NOT make a network call — use test_connection() for that.
    """
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if key:
        return True, None
    return False, (
        "No ElevenLabs API key configured.\n"
        "Set ELEVENLABS_API_KEY in your .env file or config.json."
    )


# ── Connection test ───────────────────────────────────────────────────────

async def test_connection(api_key: str) -> dict:
    """Ping ElevenLabs /user endpoint to validate the API key.

    Returns a dict with 'ok' (bool) and 'detail' (str).
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{ELEVENLABS_BASE}/user",
                headers={"xi-api-key": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                tier = data.get("subscription", {}).get("tier", "unknown")
                chars_left = data.get("subscription", {}).get("character_count", "?")
                chars_limit = data.get("subscription", {}).get("character_limit", "?")
                return {
                    "ok": True,
                    "detail": f"Connected — tier={tier}, chars={chars_left}/{chars_limit}",
                }
            else:
                return {
                    "ok": False,
                    "detail": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


# ── List voices ───────────────────────────────────────────────────────────

async def get_voices(api_key: str) -> list[dict]:
    """Fetch available voices from ElevenLabs.

    Returns a list of dicts with 'voice_id', 'name', and 'labels'.
    Returns an empty list on failure (graceful degradation).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ELEVENLABS_BASE}/voices",
                headers={"xi-api-key": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "voice_id": v["voice_id"],
                        "name": v.get("name", "Unknown"),
                        "labels": v.get("labels", {}),
                        "preview_url": v.get("preview_url"),
                    }
                    for v in data.get("voices", [])
                ]
            else:
                logger.warning("[TTS] Failed to fetch voices: HTTP %d", resp.status_code)
                return []
    except Exception as e:
        logger.warning("[TTS] Failed to fetch voices: %s", e)
        return []


# ── Streaming TTS ─────────────────────────────────────────────────────────

async def speak_stream(
    text: str,
    voice_id: str,
    api_key: str,
    *,
    model_id: str = DEFAULT_MODEL,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> AsyncGenerator[bytes, None]:
    """Stream TTS audio from ElevenLabs as chunked MP3 bytes.

    Args:
        text:             The text to synthesize.
        voice_id:         ElevenLabs voice ID.
        api_key:          ElevenLabs API key.
        model_id:         TTS model (default: eleven_turbo_v2_5).
        stability:        Voice stability (0.0-1.0).
        similarity_boost: Voice similarity boost (0.0-1.0).

    Yields:
        Raw MP3 audio bytes in chunks.

    On failure, logs a warning and yields nothing (does not crash).
    """
    if not api_key:
        logger.warning("[TTS] No API key — skipping speech generation")
        return

    if not text or not text.strip():
        logger.warning("[TTS] Empty text — skipping speech generation")
        return

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(
                        "[TTS] ElevenLabs returned HTTP %d: %s",
                        resp.status_code,
                        body.decode("utf-8", errors="replace")[:300],
                    )
                    return

                async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                    yield chunk

    except httpx.TimeoutException:
        logger.error("[TTS] ElevenLabs request timed out for voice_id=%s", voice_id)
    except httpx.ConnectError as e:
        logger.error("[TTS] Cannot connect to ElevenLabs: %s", e)
    except Exception as e:
        logger.error("[TTS] Unexpected error during streaming: %s: %s", type(e).__name__, e)


# ── Non-streaming convenience ─────────────────────────────────────────────

async def speak(
    text: str,
    voice_id: str,
    api_key: str,
    **kwargs,
) -> bytes:
    """Generate TTS audio and return the full MP3 as bytes.

    Convenience wrapper around speak_stream() for callers that
    need the complete buffer (e.g., for caching or saving to disk).
    """
    chunks = []
    async for chunk in speak_stream(text, voice_id, api_key, **kwargs):
        chunks.append(chunk)
    return b"".join(chunks)
