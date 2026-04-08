"""Arcade OS — FastAPI server wrapping the existing agent loop.

Serves the GUI and exposes WebSocket + REST endpoints.
Each WebSocket connection gets its own AgentState (thread-safe by design).

Phase 2: Persona system — REST CRUD for personas + WebSocket injection.
Phase 3: Voice I/O — STT transcription + ElevenLabs TTS streaming.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── Ensure project root is on sys.path ─────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Load .env file (lightweight, no extra dependency) ──────────────────────
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:  # don't override existing env vars
                os.environ[key] = value
    print(f"[Arcade OS] Loaded .env ({_env_file})")

import db
from config import load_config
from providers import PROVIDERS, get_api_key

# ── Default system prompt for the GUI ──────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = """You are Arcade OS, a helpful AI assistant running locally on the user's machine.
You are part of a personal business operating system. Be concise, friendly, and action-oriented.
When the user asks you to do something, do it. When they ask a question, answer it directly.
You have access to tools for reading/writing files, running commands, and searching the web."""

# ── Lazy agent imports (avoids crashing server if tools fail to load) ──────

_agent_loaded = False
_agent_error = None

def _ensure_agent():
    """Lazy-load agent module — so server starts even if agent has import issues."""
    global _agent_loaded, _agent_error
    if _agent_loaded:
        return _agent_error is None
    try:
        global agent_run, TextChunk, ThinkingChunk, ToolStart, ToolEnd, TurnDone, PermissionRequest, AgentState
        from agent import (
            AgentState, run as agent_run,
            TextChunk, ThinkingChunk, ToolStart, ToolEnd, TurnDone, PermissionRequest,
        )
        _agent_loaded = True
        print("[Arcade OS] Agent module loaded successfully")
        return True
    except Exception as e:
        _agent_loaded = True
        _agent_error = str(e)
        print(f"[Arcade OS] WARNING: Agent failed to load: {e}")
        traceback.print_exc()
        return False

# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook."""
    # Initialize DB singleton on startup
    await db.get_db()
    print(f"[Arcade OS] Database ready at {db.DB_PATH}")

    # Try to load agent now (but don't crash if it fails)
    _ensure_agent()

    print("[Arcade OS] Server running — open http://127.0.0.1:8765")
    yield
    # Clean shutdown
    await db.close_db()
    print("[Arcade OS] Shutting down.")


app = FastAPI(title="Arcade OS", lifespan=lifespan)

# ── Static files (Stitch exports = the GUI) ────────────────────────────────
STITCH_DIR = PROJECT_ROOT / "stitch_exports"

app.mount("/stitch_exports", StaticFiles(directory=str(STITCH_DIR)), name="stitch")

@app.get("/")
async def index():
    """Serve the unified shell as the root page."""
    return FileResponse(str(STITCH_DIR / "session1_unified_shell.html"))


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Check server + Ollama + agent status."""
    cfg = load_config()
    configured_model = cfg.get("model", "ollama/gemma4")

    # Check if Ollama is reachable
    ollama_ok = False
    ollama_models = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                ollama_ok = True
                data = resp.json()
                ollama_models = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass

    # Resolve which model will actually be used
    resolved_model = await _resolve_model(configured_model) if ollama_ok else configured_model

    return {
        "status": "ok",
        "model": resolved_model,
        "configured_model": configured_model,
        "ollama_connected": ollama_ok,
        "ollama_models": ollama_models,
        "agent_loaded": _agent_error is None if _agent_loaded else "pending",
        "agent_error": _agent_error,
    }


@app.get("/api/models")
async def list_models():
    """Return all available models across every configured provider."""
    cfg = load_config()
    all_models = []

    # ── Ollama: live-query for actually-running models ──────────────────
    ollama_live = await _get_ollama_models()
    for m in ollama_live:
        all_models.append({"id": f"ollama/{m}", "name": m, "provider": "ollama"})

    # ── Cloud / local providers: surface if API key is present ─────────
    _SKIP = {"ollama", "lmstudio", "custom"}  # handled separately
    for prov_name, prov_cfg in PROVIDERS.items():
        if prov_name in _SKIP:
            continue
        key = get_api_key(prov_name, cfg)
        if not key:
            continue  # No key → don't show these models
        for model_name in prov_cfg.get("models", []):
            all_models.append({
                "id":       f"{prov_name}/{model_name}",
                "name":     model_name,
                "provider": prov_name,
            })

    return {"models": all_models}


# ── Model Diagnostics ─────────────────────────────────────────────────────

@app.get("/api/test-models")
async def test_models():
    """Ping each configured cloud provider to verify API keys and model access.

    Returns a per-model status report: ok, error message, and response time.
    Ollama models are skipped (tested via /api/health instead).
    """
    import time as _time
    cfg = load_config()
    results = []

    _SKIP = {"ollama", "lmstudio", "custom"}

    for prov_name, prov_cfg in PROVIDERS.items():
        if prov_name in _SKIP:
            continue
        key = get_api_key(prov_name, cfg)
        if not key:
            # No API key → mark all models as skipped
            for model_name in prov_cfg.get("models", []):
                results.append({
                    "model": f"{prov_name}/{model_name}",
                    "provider": prov_name,
                    "status": "skipped",
                    "reason": f"No API key (set {prov_cfg.get('api_key_env', 'N/A')})",
                    "ms": 0,
                })
            continue

        # Test ONE model per provider (the first in the list) to save time/cost
        test_model = prov_cfg["models"][0] if prov_cfg.get("models") else None
        if not test_model:
            continue

        base_url = prov_cfg.get("base_url", "https://api.openai.com/v1")
        t0 = _time.time()
        try:
            if prov_cfg["type"] == "anthropic":
                import anthropic as _ant
                client = _ant.Anthropic(api_key=key)
                resp = client.messages.create(
                    model=test_model,
                    max_tokens=5,
                    messages=[{"role": "user", "content": "hi"}],
                )
                status = "ok"
                reason = f"responded: {resp.content[0].text[:30] if resp.content else '(empty)'}"
            else:
                from openai import OpenAI
                client = OpenAI(api_key=key, base_url=base_url)
                resp = client.chat.completions.create(
                    model=test_model,
                    max_tokens=5,
                    messages=[{"role": "user", "content": "hi"}],
                    stream=False,
                )
                reply = resp.choices[0].message.content if resp.choices else "(empty)"
                status = "ok"
                reason = f"responded: {reply[:30] if reply else '(empty)'}"
        except Exception as e:
            status = "error"
            reason = f"{type(e).__name__}: {str(e)[:200]}"

        elapsed = int((_time.time() - t0) * 1000)

        # Record the tested model
        results.append({
            "model": f"{prov_name}/{test_model}",
            "provider": prov_name,
            "status": status,
            "reason": reason,
            "ms": elapsed,
        })

        # If the first model worked, mark the rest as "available" without testing
        # If it failed, mark them as "likely_error"
        for other in prov_cfg["models"][1:]:
            results.append({
                "model": f"{prov_name}/{other}",
                "provider": prov_name,
                "status": "available" if status == "ok" else "likely_error",
                "reason": "same provider" if status == "ok" else f"provider test failed: {reason[:100]}",
                "ms": 0,
            })

    return {"results": results}


# ── Conversations REST ────────────────────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations():
    convs = await db.list_conversations()
    return convs


@app.post("/api/conversations")
async def create_conversation():
    conv = await db.create_conversation()
    return conv


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    conv = await db.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)
    messages = await db.get_messages(conv_id)
    return {"conversation": conv, "messages": messages}


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    deleted = await db.delete_conversation(conv_id)
    if not deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"deleted": True}


# ── Personas REST ──────────────────────────────────────────────────────────

@app.get("/api/personas")
async def api_list_personas():
    """Return all active personas."""
    personas = await db.list_personas(active_only=True)
    return {"personas": personas}


@app.get("/api/personas/{persona_id}")
async def api_get_persona(persona_id: int):
    """Return a single persona by ID."""
    persona = await db.get_persona(persona_id)
    if not persona:
        return JSONResponse({"error": "Persona not found"}, status_code=404)
    return persona


@app.post("/api/personas")
async def api_create_persona(request: Request):
    """Create a custom persona."""
    body = await request.json()
    # Validate required fields
    required = ["name", "role", "system_prompt"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return JSONResponse(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status_code=400,
        )
    try:
        persona = await db.create_persona(
            name=body["name"],
            role=body["role"],
            system_prompt=body["system_prompt"],
            avatar=body.get("avatar", "\U0001f916"),
            description=body.get("description", ""),
            model=body.get("model"),
            voice_id=body.get("voice_id"),
            color=body.get("color", "#00c896"),
        )
        return JSONResponse(persona, status_code=201)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.put("/api/personas/{persona_id}")
async def api_update_persona(persona_id: int, request: Request):
    """Update persona fields. Only provided non-null fields are applied."""
    body = await request.json()
    # Filter to only known persona fields
    allowed = {"name", "role", "avatar", "description", "system_prompt",
               "model", "voice_id", "color", "is_active"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        return JSONResponse({"error": "No valid fields to update"}, status_code=400)
    updated = await db.update_persona(persona_id, **updates)
    if not updated:
        return JSONResponse({"error": "Persona not found"}, status_code=404)
    # Return the refreshed persona
    persona = await db.get_persona(persona_id)
    return persona


@app.delete("/api/personas/{persona_id}")
async def api_delete_persona(persona_id: int):
    """Delete a persona. Conversations using it will have persona_id set to NULL."""
    deleted = await db.delete_persona(persona_id)
    if not deleted:
        return JSONResponse({"error": "Persona not found"}, status_code=404)
    return {"deleted": True}


# ── Voice I/O helpers ──────────────────────────────────────────────────────

# Map content-types to file extensions for OpenAI Whisper API
_AUDIO_EXT_MAP = {
    "audio/webm": ".webm",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
}


def _transcribe_encoded_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Transcribe encoded audio (WebM, MP3, etc.) via the OpenAI Whisper API.

    The OpenAI Whisper API accepts encoded audio natively — no need to
    decode to raw PCM first.  Falls back to writing a temp file for
    local backends if the API key is not available.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Encoded audio (WebM/MP3) requires OPENAI_API_KEY for cloud transcription. "
            "Upload WAV for local STT backends."
        )

    import io
    from openai import OpenAI

    # Determine proper file extension
    ext = _AUDIO_EXT_MAP.get(content_type, "")
    if not ext:
        for suffix in (".webm", ".mp3", ".ogg", ".m4a", ".mp4", ".wav"):
            if filename.endswith(suffix):
                ext = suffix
                break
        else:
            ext = ".webm"  # safe default for browser audio

    client = OpenAI(api_key=api_key)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=(f"audio{ext}", io.BytesIO(audio_bytes), content_type or "audio/webm"),
    )
    return transcript.text.strip()


# ── Voice I/O REST ─────────────────────────────────────────────────────────────

@app.post("/api/voice/transcribe")
async def api_voice_transcribe(file: UploadFile = File(...)):
    """Transcribe an audio file (WAV/WebM/MP3) to text via the STT engine.

    Accepts: multipart/form-data with a single file field.
    Returns: {"text": "transcribed text"}

    Audio format handling:
      - WAV files: extracts raw PCM and routes to local Whisper backends
      - WebM/MP3/other: routes to OpenAI Whisper API (accepts encoded audio)
      - Raw PCM: passed directly to local Whisper backends
    """
    try:
        from voice.stt import transcribe as stt_transcribe, check_stt_availability
    except ImportError as e:
        return JSONResponse(
            {"error": f"STT module not available: {e}"},
            status_code=503,
        )

    stt_ok, stt_reason = check_stt_availability()
    if not stt_ok:
        return JSONResponse(
            {"error": f"No STT backend available: {stt_reason}"},
            status_code=503,
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        return JSONResponse({"error": "Empty audio file"}, status_code=400)

    content_type = file.content_type or ""
    filename = file.filename or "audio.bin"
    print(f"[Voice] Transcribing {len(audio_bytes)} bytes ({filename}, type={content_type})")

    try:
        # Determine if this is raw PCM (from recorder.py) or encoded audio (from browser)
        is_wav = audio_bytes[:4] == b"RIFF"
        is_encoded = content_type in (
            "audio/webm", "audio/mp3", "audio/mpeg", "audio/ogg",
            "audio/mp4", "audio/x-m4a",
        ) or filename.endswith((".webm", ".mp3", ".ogg", ".m4a", ".mp4"))

        if is_wav:
            # WAV: strip header (44 bytes) to get raw PCM, pass to local backends
            pcm_data = audio_bytes[44:] if len(audio_bytes) > 44 else audio_bytes
            text = await asyncio.to_thread(stt_transcribe, pcm_data)
        elif is_encoded:
            # Encoded audio from browser: use OpenAI Whisper API (handles encoded formats)
            text = await asyncio.to_thread(
                _transcribe_encoded_audio, audio_bytes, filename, content_type
            )
        else:
            # Assume raw PCM
            text = await asyncio.to_thread(stt_transcribe, audio_bytes)

        print(f'[Voice] Transcription result: "{text[:100]}"')
        return {"text": text}
    except Exception as e:
        print(f"[Voice] STT Error: {e}")
        return JSONResponse(
            {"error": f"Transcription failed: {type(e).__name__}: {e}"},
            status_code=500,
        )


@app.post("/api/voice/speak")
async def api_voice_speak(request: Request):
    """Generate TTS audio for the given text.

    Accepts JSON: {"text": "Hello", "persona_id": 1}
    Returns: streaming audio/mpeg (MP3)

    Voice resolution order:
      1. persona_id -> persona.voice_id from database
      2. request body voice_id override
      3. config default_voice_id
    """
    try:
        from voice.tts import speak_stream
    except ImportError as e:
        return JSONResponse(
            {"error": f"TTS module not available: {e}"},
            status_code=503,
        )

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)

    # Resolve API key
    cfg = load_config()
    api_key = cfg.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return JSONResponse(
            {"error": "ElevenLabs API key not configured. Set ELEVENLABS_API_KEY in .env."},
            status_code=503,
        )

    # Check master TTS switch
    if not cfg.get("tts_enabled", True):
        return JSONResponse(
            {"error": "TTS is disabled in configuration."},
            status_code=503,
        )

    # Resolve voice_id: persona -> body override -> config default
    voice_id = cfg.get("default_voice_id", "pNInz6obpgDQGcFmaJgB")

    persona_id = body.get("persona_id")
    if persona_id:
        try:
            persona = await db.get_persona(int(persona_id))
            if persona and persona.get("voice_id"):
                voice_id = persona["voice_id"]
                print(f"[Voice] Using persona voice: {persona['name']} -> {voice_id}")
        except Exception as e:
            print(f"[Voice] Warning: Could not resolve persona {persona_id}: {e}")

    # Allow explicit voice_id override in the request body
    if body.get("voice_id"):
        voice_id = body["voice_id"]

    print(f'[Voice] TTS: "{text[:80]}..." -> voice_id={voice_id}')

    return StreamingResponse(
        speak_stream(text, voice_id, api_key),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache",
        },
    )


@app.get("/api/voice/voices")
async def api_voice_list_voices():
    """List available ElevenLabs voices."""
    try:
        from voice.tts import get_voices
    except ImportError as e:
        return JSONResponse(
            {"error": f"TTS module not available: {e}"},
            status_code=503,
        )

    cfg = load_config()
    api_key = cfg.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return JSONResponse(
            {"error": "ElevenLabs API key not configured."},
            status_code=503,
        )

    voices = await get_voices(api_key)
    return {"voices": voices}


@app.get("/api/voice/status")
async def api_voice_status():
    """Check voice I/O availability (STT + TTS)."""
    cfg = load_config()
    result = {
        "tts_enabled": cfg.get("tts_enabled", True),
        "tts_available": False,
        "tts_detail": "",
        "stt_available": False,
        "stt_detail": "",
    }

    # TTS check
    try:
        from voice.tts import test_connection
        api_key = cfg.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY", "")
        if api_key:
            tts_status = await test_connection(api_key)
            result["tts_available"] = tts_status["ok"]
            result["tts_detail"] = tts_status["detail"]
        else:
            result["tts_detail"] = "No ElevenLabs API key configured"
    except ImportError:
        result["tts_detail"] = "TTS module not installed"

    # STT check
    try:
        from voice.stt import check_stt_availability, get_stt_backend_name
        stt_ok, stt_reason = check_stt_availability()
        result["stt_available"] = stt_ok
        result["stt_detail"] = get_stt_backend_name() if stt_ok else (stt_reason or "Unknown error")
    except ImportError:
        result["stt_detail"] = "STT module not installed"

    return result


# ── Model Auto-Detection ───────────────────────────────────────────────────

# Preferred models in fallback order
_MODEL_PREFERENCES = ["gemma4", "gemma3", "phi4-mini", "llama3.2", "qwen2.5-coder", "mistral"]

async def _get_ollama_models() -> list[str]:
    """Query Ollama for available models."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []

async def _resolve_model(configured_model: str) -> str:
    """
    If the configured model is available in Ollama, use it.
    Otherwise, find the best available model from the preference list.
    Non-Ollama models (gemini/, openai/, etc.) are returned as-is.
    """
    # Non-Ollama models don't need resolution
    if not configured_model.startswith("ollama/"):
        return configured_model

    short_name = configured_model.replace("ollama/", "")
    available = await _get_ollama_models()

    if not available:
        print(f"[Model] WARNING: Ollama not reachable, using configured model: {configured_model}")
        return configured_model

    print(f"[Model] Ollama has: {', '.join(available)}")

    # Check if configured model is available (exact or prefix match)
    for m in available:
        if m == short_name or m.startswith(short_name.split(":")[0]):
            resolved = f"ollama/{m}"
            if resolved != configured_model:
                print(f"[Model] Resolved {configured_model} -> {resolved}")
            return resolved

    # Configured model not found — try preference list
    for pref in _MODEL_PREFERENCES:
        for m in available:
            if m.startswith(pref):
                print(f"[Model] {short_name} not found, falling back to: ollama/{m}")
                return f"ollama/{m}"

    # Last resort: use whatever is first available
    if available:
        fallback = f"ollama/{available[0]}"
        print(f"[Model] Using first available model: {fallback}")
        return fallback

    print(f"[Model] No models found in Ollama! Using configured: {configured_model}")
    return configured_model


# ── WebSocket Chat ─────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.

    Client sends:  {"conversation_id": "...", "message": "..."}
    Server sends:  {"type": "text_chunk"|"tool_start"|"tool_end"|"turn_done"|"done"|"error", "data": ...}
    """
    await websocket.accept()
    print("[WS] Client connected")

    # Check if agent is available
    if not _ensure_agent():
        await websocket.send_json({
            "type": "error",
            "data": f"Agent module failed to load: {_agent_error}"
        })
        await websocket.close()
        return

    # Each connection gets its own state — thread safety per the build plan
    agent_state = AgentState()
    cfg = load_config()
    _history_loaded = False  # Flag: only hydrate from DB once per WS connection

    # Use the model from config (user's preference)
    if "model" not in cfg:
        cfg["model"] = "ollama/gemma4"

    # Auto-detect: if configured model isn't available, fall back to what Ollama has
    cfg["model"] = await _resolve_model(cfg["model"])

    # Set permission mode to accept-all for GUI (approval gates come in Phase 6)
    cfg["permission_mode"] = "accept-all"

    print(f"[WS] Using model: {cfg['model']}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "data": "Invalid JSON"})
                continue

            user_message = payload.get("message", "").strip()
            conv_id = payload.get("conversation_id")
            model_override = payload.get("model")  # Per-message model switch
            persona_id = payload.get("persona_id")  # Phase 2: persona injection

            if not user_message:
                await websocket.send_json({"type": "error", "data": "Empty message"})
                continue

            # ── Phase 2: Persona Resolution ────────────────────────────────
            # Resolve the active system prompt and model using the priority chain:
            #   Model:  payload.model > persona.model > cfg.model (global config)
            #   Prompt: persona.system_prompt > DEFAULT_SYSTEM_PROMPT
            active_system_prompt = DEFAULT_SYSTEM_PROMPT
            persona_model = None

            if persona_id:
                try:
                    # Persist the persona binding to this conversation
                    if conv_id:
                        await db.update_conversation_persona(conv_id, persona_id)

                    persona = await db.get_persona(persona_id)
                    if persona:
                        active_system_prompt = persona.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
                        persona_model = persona.get("model")  # May be None
                        print(f"[WS] Persona active: {persona.get('avatar', '')} {persona.get('name', 'Unknown')}")
                    else:
                        print(f"[WS] WARNING: persona_id={persona_id} not found, using default prompt")
                except Exception as e:
                    print(f"[WS] WARNING: Persona lookup failed: {e}")

            # ── Slice 2: Memory Injection ──────────────────────────────────
            # On the first message of this WS connection, hydrate AgentState
            # with prior conversation history from the database so the AI
            # has full context of previous turns.
            if conv_id and not _history_loaded:
                try:
                    db_messages = await db.get_messages(conv_id)
                    if db_messages:
                        agent_state.messages = [
                            {"role": msg["role"], "content": msg["content"]}
                            for msg in db_messages
                        ]
                        print(f"[WS] Hydrated {len(db_messages)} messages from conv {conv_id}")
                except Exception as e:
                    print(f"[WS] WARNING: Failed to load history: {e}")
                _history_loaded = True

            # ── Model Priority Chain ───────────────────────────────────────
            # Priority: Manual user selection > Persona default > Global config
            if model_override and model_override != cfg["model"]:
                cfg["model"] = model_override
                print(f"[WS] Model override (user): {cfg['model']}")
                # Reset agent state for new model (different context)
                agent_state = AgentState()
                _history_loaded = False  # Re-hydrate on next message if model switches
            elif persona_model and persona_model != cfg["model"]:
                cfg["model"] = persona_model
                print(f"[WS] Model override (persona): {cfg['model']}")

            print(f"[WS] User message ({cfg['model']}): {user_message[:80]}...")

            # Persist user message
            if conv_id:
                await db.add_message(conv_id, "user", user_message)
                conv = await db.get_conversation(conv_id)
                if conv and conv["title"] == "New Chat":
                    title = user_message[:60] + ("..." if len(user_message) > 60 else "")
                    await db.update_conversation_title(conv_id, title)

            # ── Stream agent response via threaded queue ───────────────────
            loop = asyncio.get_running_loop()
            event_queue: asyncio.Queue = asyncio.Queue()

            def _threaded_agent():
                """Run the synchronous agent generator in a background thread."""
                try:
                    print(f"[Agent] Starting generation with model {cfg['model']}...")
                    event_count = 0
                    for event in agent_run(
                        user_message=user_message,
                        state=agent_state,
                        config=cfg,
                        system_prompt=active_system_prompt,
                    ):
                        event_count += 1
                        asyncio.run_coroutine_threadsafe(
                            event_queue.put(event), loop
                        ).result(timeout=10)  # Block until queued
                    print(f"[Agent] Generation complete — {event_count} events")
                except Exception as e:
                    tb = traceback.format_exc()
                    print(f"[Agent] ERROR in generation:\n{tb}")
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(("ERROR", f"{type(e).__name__}: {e}")), loop
                    ).result(timeout=10)
                finally:
                    # Always signal completion
                    asyncio.run_coroutine_threadsafe(
                        event_queue.put(None), loop
                    ).result(timeout=10)

            # Start agent in background thread
            loop.run_in_executor(None, _threaded_agent)

            # Consume events from queue and send to WebSocket
            full_text = ""
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=120)
                    except asyncio.TimeoutError:
                        print("[WS] Agent timeout — no events for 120s")
                        await websocket.send_json({
                            "type": "error",
                            "data": "Response timed out. Is your AI model running? Check that Ollama is started."
                        })
                        break

                    if event is None:
                        break  # Agent finished

                    if isinstance(event, tuple) and len(event) == 2 and event[0] == "ERROR":
                        await websocket.send_json({"type": "error", "data": event[1]})
                        break

                    if isinstance(event, TextChunk):
                        full_text += event.text
                        await websocket.send_json({
                            "type": "text_chunk", "data": event.text
                        })

                    elif isinstance(event, ThinkingChunk):
                        await websocket.send_json({
                            "type": "thinking", "data": event.text
                        })

                    elif isinstance(event, ToolStart):
                        # Safely serialize inputs
                        try:
                            inputs_safe = json.loads(json.dumps(event.inputs, default=str))
                        except Exception:
                            inputs_safe = {"raw": str(event.inputs)}
                        await websocket.send_json({
                            "type": "tool_start",
                            "data": {"name": event.name, "inputs": inputs_safe}
                        })

                    elif isinstance(event, ToolEnd):
                        result_str = str(event.result)[:500]
                        await websocket.send_json({
                            "type": "tool_end",
                            "data": {
                                "name": event.name,
                                "result": result_str,
                                "permitted": event.permitted,
                            }
                        })

                    elif isinstance(event, TurnDone):
                        await websocket.send_json({
                            "type": "turn_done",
                            "data": {
                                "input_tokens": event.input_tokens,
                                "output_tokens": event.output_tokens,
                            }
                        })

                    elif isinstance(event, PermissionRequest):
                        event.granted = True
                        await websocket.send_json({
                            "type": "permission",
                            "data": {"description": event.description, "auto_approved": True}
                        })

            except Exception as e:
                tb = traceback.format_exc()
                print(f"[WS] Stream error: {tb}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "data": f"Stream error: {type(e).__name__}: {e}"
                    })
                except Exception:
                    pass

            # Persist assistant response
            if full_text and conv_id:
                await db.add_message(conv_id, "assistant", full_text)

            # Send completion signal
            try:
                await websocket.send_json({
                    "type": "done",
                    "data": {"full_text": full_text}
                })
            except Exception:
                pass

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        traceback.print_exc()


# ── Run directly ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    print(f"[Arcade OS] Starting on http://127.0.0.1:{port}")
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
