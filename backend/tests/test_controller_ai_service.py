import json
import os
import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.chuck.ai import ControllerAIService, ControllerAIError  # type: ignore  # noqa: E402
from backend.services.chuck.detection import BoardInfo, BoardStatus  # type: ignore  # noqa: E402


class StubDetectionService:
    def __init__(self, board: BoardInfo):
        self._board = board

    def detect_board(self, vid: str, pid: str, use_cache: bool = True) -> BoardInfo:
        return self._board


class StubDiagnosticsService:
    def __init__(self):
        self.health_checks = {}

    def get_event_history(self, limit: int = 10):
        return []


@pytest.fixture
def drive_root(tmp_path: Path) -> Path:
    mappings_dir = tmp_path / "config" / "mappings"
    mappings_dir.mkdir(parents=True)
    mapping = {
        "version": 1,
        "board": {"vid": "045e", "pid": "028e", "name": "Test Encoder"},
        "mappings": {
            "p1.button1": {"pin": 1, "label": "Button 1"},
            "p1.button2": {"pin": "", "label": "Button 2"},
            "p2.button1": {"pin": 5, "label": "Button 1"},
        },
        "last_modified": "2025-10-29T03:00:00",
        "modified_by": "unit-test",
    }
    (mappings_dir / "controls.json").write_text(json.dumps(mapping), encoding="utf-8")
    return tmp_path


@pytest.fixture
def detection_service() -> StubDetectionService:
    board = BoardInfo(
        vid="045e",
        pid="028e",
        vid_pid="045e:028e",
        name="Test Encoder",
        manufacturer="Test Manufacturer",
        product_string="Encoder 2000",
        manufacturer_string="Arcade Labs",
        detected=True,
        status=BoardStatus.CONNECTED,
        detection_time=0.05,
        error=None,
    )
    return StubDetectionService(board)


@pytest.fixture
def diagnostics_service() -> StubDiagnosticsService:
    return StubDiagnosticsService()


def test_build_context_collects_mapping_and_devices(
    drive_root, detection_service, diagnostics_service, monkeypatch
):
    monkeypatch.setattr(
        "backend.services.chuck.ai.detect_controllers",
        lambda use_cache=True: [
            {"name": "Xbox Pad", "manufacturer": "Microsoft", "detected": True}
        ],
    )

    service = ControllerAIService(
        detection_service=detection_service,
        diagnostics_service=diagnostics_service,
        llm_client=lambda payload, system: "ok",
    )

    context = service.build_context(drive_root).to_dict()

    assert context["mapping_summary"]["unmapped_inputs"] == 1
    assert context["board_status"]["detected"] is True
    assert context["handheld_devices"][0]["name"] == "Xbox Pad"


def test_chat_returns_reply_with_history(
    drive_root, detection_service, diagnostics_service, monkeypatch
):
    monkeypatch.setattr(
        "backend.services.chuck.ai.detect_controllers", lambda use_cache=True: []
    )

    service = ControllerAIService(
        detection_service=detection_service,
        diagnostics_service=diagnostics_service,
        llm_client=lambda payload, system: "All set! Wiring looks good.",
        max_history=4,
    )

    result = service.chat(
        "Check my wiring plan", drive_root, device_id="test-device", panel="controller"
    )

    assert "All set!" in result["reply"]
    assert len(result["history"]) == 2
    assert result["history"][0]["role"] == "user"
    assert result["history"][1]["role"] == "assistant"


def test_chat_raises_for_empty_message(drive_root, detection_service):
    service = ControllerAIService(
        detection_service=detection_service,
        llm_client=lambda payload, system: "noop",
    )

    with pytest.raises(ControllerAIError):
        service.chat("", drive_root)


def test_prompts_switch_for_wizard_persona(
    drive_root, detection_service, diagnostics_service, monkeypatch
):
    captured_prompts: List[str] = []

    def fake_llm(payload: str, prompt: str) -> str:
        captured_prompts.append(prompt)
        return "Response"

    service = ControllerAIService(
        detection_service=detection_service,
        diagnostics_service=diagnostics_service,
        llm_client=fake_llm,
    )

    service.chat("Status update", drive_root, device_id="device-chuck", panel="controller")
    service.chat(
        "Need guidance",
        drive_root,
        device_id="device-wiz",
        panel="console-wizard",
        extra_context={"persona": "wizard"},
    )

    assert len(captured_prompts) == 2
    assert captured_prompts[0] != captured_prompts[1]
