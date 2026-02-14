import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.chuck.ai import (
    ControllerAIError,
    get_controller_ai_service,
)
from ..services.chuck.detection import (
    get_detection_service,
    BoardNotFoundError,
    BoardDetectionError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ControllerAIChatRequest(BaseModel):
    """Payload for controller AI chat."""

    message: str
    panel_state: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


@router.post("/chat")
async def controller_ai_chat(request: Request, payload: ControllerAIChatRequest):
    """Chat endpoint for Controller Chuck persona."""
    service = get_controller_ai_service()
    drive_root = request.app.state.drive_root
    device_id = payload.session_id or request.headers.get("x-device-id", "unknown")
    panel = request.headers.get("x-panel", "controller")

    try:
        result = service.chat(
            message=payload.message,
            drive_root=drive_root,
            device_id=device_id,
            panel=panel,
            extra_context=payload.panel_state,
        )
        return result
    except ControllerAIError as exc:
        logger.warning("Controller AI error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # pragma: no cover - unexpected errors logged for triage
        logger.exception("Controller AI unexpected failure")
        raise HTTPException(status_code=500, detail="Controller AI failed") from exc


@router.get("/events")
async def controller_ai_events(request: Request):
    """Server-Sent Events stream for controller detection updates."""
    detection_service = get_detection_service()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    def handler(event):
        try:
            data = event.to_dict()
            loop.call_soon_threadsafe(queue.put_nowait, data)
        except Exception as exc:  # pragma: no cover - handler failures are non-critical
            logger.debug("Failed to queue detection event: %s", exc)

    detection_service.register_event_handler(handler)

    drive_root: Path = request.app.state.drive_root
    mapping_file = drive_root / "config" / "mappings" / "controls.json"
    boards: list[tuple[str, str]] = []
    poll_task: Optional[asyncio.Task] = None

    if mapping_file.exists():
        try:
            mapping_data = json.loads(mapping_file.read_text(encoding="utf-8"))
            board = mapping_data.get("board") or {}
            vid = board.get("vid")
            pid = board.get("pid")
            if vid and pid:
                boards.append((vid, pid))
                try:
                    board_info = detection_service.detect_board(vid, pid, use_cache=True)
                    queue.put_nowait(
                        {
                            "event_type": "status",
                            "timestamp": datetime.utcnow().timestamp(),
                            "board": board_info.to_dict(),
                        }
                    )
                except BoardNotFoundError:
                    queue.put_nowait(
                        {
                            "event_type": "status",
                            "timestamp": datetime.utcnow().timestamp(),
                            "board": {"vid": vid, "pid": pid, "detected": False},
                        }
                    )
                except BoardDetectionError as exc:
                    queue.put_nowait(
                        {
                            "event_type": "status",
                            "timestamp": datetime.utcnow().timestamp(),
                            "board": {"vid": vid, "pid": pid, "detected": False, "error": str(exc)},
                        }
                    )
        except Exception as exc:  # pragma: no cover - mapping parse errors logged
            logger.warning("Failed to read controller mapping for events: %s", exc)

    if boards and not getattr(detection_service, "_polling_active", False):
        poll_task = asyncio.create_task(detection_service.start_polling(boards))

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            detection_service.unregister_event_handler(handler)
            if poll_task:
                detection_service.stop_polling()
                poll_task.cancel()
                with suppress(asyncio.CancelledError):
                    await poll_task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/health")
async def controller_ai_health():
    """Return AI readiness diagnostics."""
    service = get_controller_ai_service()
    return service.health()
