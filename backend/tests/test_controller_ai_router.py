import asyncio
import json
import os
import sys
import time

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import app  # type: ignore  # noqa: E402
from backend.services.chuck.ai import ControllerAIError  # type: ignore  # noqa: E402
from backend.services.chuck.detection import BoardInfo, BoardStatus  # type: ignore  # noqa: E402
import backend.routers.controller_ai as controller_ai_module  # type: ignore  # noqa: E402


class FakeAIService:
    def __init__(self, reply: str = "ok"):
        self.reply = reply

    def chat(self, message, drive_root, device_id="unknown", panel="controller", extra_context=None):
        return {"reply": self.reply, "history": [], "context": {}}

    def health(self):
        return {"provider": {"configured": True}}


class ErrorAIService(FakeAIService):
    def chat(self, *args, **kwargs):
        raise ControllerAIError("AI offline")


class StubDetectionService:
    def __init__(self):
        self.handlers = []
        self._polling_active = False

    def register_event_handler(self, handler):
        self.handlers.append(handler)

    def unregister_event_handler(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    def detect_board(self, vid, pid, use_cache=True):
        return BoardInfo(
            vid=vid,
            pid=pid,
            vid_pid=f"{vid}:{pid}",
            name="Test Encoder",
            manufacturer="Test",
            product_string="Wizard Board",
            manufacturer_string="Arcade Labs",
            detected=True,
            status=BoardStatus.CONNECTED,
            detection_time=0.01,
            error=None,
        )

    async def start_polling(self, boards):
        self._polling_active = True
        while self._polling_active:
            await asyncio.sleep(0.1)

    def stop_polling(self):
        self._polling_active = False

def test_controller_ai_chat_route(monkeypatch, tmp_path):
    fake_service = FakeAIService("Here to help!")
    monkeypatch.setattr(
        controller_ai_module, "get_controller_ai_service", lambda: fake_service
    )
    client = TestClient(app)
    app.state.drive_root = tmp_path

    resp = client.post("/api/ai/controller/chat", json={"message": "Hello Chuck"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Here to help!"


def test_controller_ai_chat_error(monkeypatch, tmp_path):
    fake_service = ErrorAIService()
    monkeypatch.setattr(
        controller_ai_module, "get_controller_ai_service", lambda: fake_service
    )
    client = TestClient(app)
    app.state.drive_root = tmp_path

    resp = client.post("/api/ai/controller/chat", json={"message": "test"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "AI offline"


def test_controller_ai_health(monkeypatch):
    fake_service = FakeAIService()
    monkeypatch.setattr(
        controller_ai_module, "get_controller_ai_service", lambda: fake_service
    )
    client = TestClient(app)

    resp = client.get("/api/ai/controller/health")

    assert resp.status_code == 200
    assert resp.json()["provider"]["configured"] is True


def test_controller_ai_events_stream(monkeypatch, tmp_path):
    detection_service = StubDetectionService()
    monkeypatch.setattr(
        controller_ai_module, "get_detection_service", lambda: detection_service
    )
    monkeypatch.setattr(
        controller_ai_module, "get_controller_ai_service", lambda: FakeAIService()
    )

    mapping_dir = tmp_path / "config" / "mappings"
    mapping_dir.mkdir(parents=True)
    (mapping_dir / "controls.json").write_text(
        json.dumps(
            {
                "version": 1,
                "board": {"vid": "045e", "pid": "028e", "name": "Test Encoder"},
                "mappings": {},
            }
        ),
        encoding="utf-8",
    )

    app.state.drive_root = tmp_path

    client = TestClient(app)

    with client.stream("GET", "/api/ai/controller/events") as stream:
        for line in stream.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = json.loads(line.split("data: ", 1)[1])
            assert payload["event_type"] == "status"
            assert payload["board"]["detected"] is True
            break
