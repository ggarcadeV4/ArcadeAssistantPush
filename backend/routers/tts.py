"""
TTS Router — bridges frontend speak() to ElevenLabs via Supabase Edge Function proxy.

POST /api/voice/tts
Body: { text, voice_profile, voice_id, model_id }
Returns: audio/mpeg stream
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["tts"])

# ── Voice Profile → ElevenLabs Voice ID Mapping ──────────────────────────────
# Reads from environment variables first (set in .env), falls back to defaults.
# IDs can be verified at: https://elevenlabs.io/voice-lab
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # ElevenLabs "Rachel" default

def _get_voice_profiles() -> dict:
    return {
        "dewey":   os.getenv("DEWEY_VOICE_ID",  "pNInz6obpgDQGcFmaJgB"),
        "lora":    os.getenv("LORA_VOICE_ID",    "EXAVITQu4vr4xnSDxMaL"),
        "blinky":  os.getenv("BLINKY_VOICE_ID",  "DTKMou8ccj1ZaWGBiotd"),
        "chuck":   os.getenv("CHUCK_VOICE_ID",   DEFAULT_VOICE),   # Needs correct ID
        "wiz":     os.getenv("WIZ_VOICE_ID",     "CwhRBWXzGAHq8TQ4Fs17"),
        "vicky":   os.getenv("VICKY_VOICE_ID",   DEFAULT_VOICE),   # Needs correct ID
        "gunner":  os.getenv("GUNNER_VOICE_ID",  DEFAULT_VOICE),   # Needs correct ID
        "doc":     os.getenv("DOC_VOICE_ID",     DEFAULT_VOICE),   # Needs correct ID
        "sam":     os.getenv("SAM_VOICE_ID",     DEFAULT_VOICE),   # Needs correct ID
    }


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_profile: Optional[str] = None
    voice_id: Optional[str] = None
    model_id: Optional[str] = None


@router.post("/tts")
async def text_to_speech(request: Request, payload: TTSRequest):
    """
    Convert text to speech via ElevenLabs (proxied through Supabase Edge Function).

    Priority:
    1. Explicit voice_id (direct ElevenLabs ID)
    2. voice_profile mapping (e.g., 'chuck' → 'f5HLTX707KIM4SzJYzSz')
    3. Default voice
    """
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not service_key:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set — TTS unavailable")
        raise HTTPException(
            status_code=501,
            detail="TTS not configured (missing Supabase credentials)"
        )

    # Resolve voice ID
    resolved_voice_id = payload.voice_id
    if not resolved_voice_id and payload.voice_profile:
        resolved_voice_id = _get_voice_profiles().get(payload.voice_profile.lower())
        if not resolved_voice_id:
            logger.warning("Unknown voice_profile '%s', using default", payload.voice_profile)

    if not resolved_voice_id:
        resolved_voice_id = "EXAVITQu4vr4xnSDxMaL"  # Default ElevenLabs voice

    model_id = payload.model_id or "eleven_monolingual_v1"

    # Build request to Supabase Edge Function
    proxy_url = f"{supabase_url}/functions/v1/elevenlabs-proxy"

    proxy_payload = {
        "text": payload.text,
        "voice_id": resolved_voice_id,
        "model_id": model_id,
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                proxy_url,
                json=proxy_payload,
                headers={
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="ElevenLabs daily quota exceeded")

        if response.status_code != 200:
            logger.error(
                "ElevenLabs proxy error: %s — %s",
                response.status_code,
                response.text[:200],
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"ElevenLabs proxy returned {response.status_code}",
            )

        # Return audio bytes directly
        content_type = response.headers.get("content-type", "audio/mpeg")
        return Response(
            content=response.content,
            media_type=content_type,
            headers={"Cache-Control": "no-cache"},
        )

    except httpx.HTTPError as exc:
        logger.error("TTS proxy request failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"TTS proxy error: {exc}")
    except ImportError:
        raise HTTPException(status_code=501, detail="httpx not installed — TTS unavailable")
