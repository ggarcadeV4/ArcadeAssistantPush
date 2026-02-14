"""Tests for Controller Chuck AI Service

Tests the Claude client fallback mechanism, mock client behavior,
and AI context building for controller troubleshooting.

Target coverage: >85%
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

from backend.services.chuck.ai import (
    ControllerAIService,
    ControllerAIError,
    _load_claude_client,
    _create_mock_claude_client,
    AIContext,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_drive_root(tmp_path):
    """Create a temporary drive root with config structure."""
    config_dir = tmp_path / "config" / "mappings"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create sample controls.json
    controls = {
        "version": "1.0",
        "modified_by": "test",
        "last_modified": "2025-01-01T00:00:00Z",
        "board": {"vid": "d209", "pid": "0501"},
        "mappings": {
            "p1.button1": {"pin": 1, "label": "Button 1"},
            "p1.button2": {"pin": 2, "label": "Button 2"},
            "p1.button3": {"pin": None, "label": "Button 3"},  # Unmapped
        },
    }
    (config_dir / "controls.json").write_text(json.dumps(controls))

    return tmp_path


@pytest.fixture
def mock_detection_service():
    """Mock detection service."""
    service = Mock()
    service.detect_board = Mock(
        return_value=Mock(
            detected=True, to_dict=lambda: {"vid": "d209", "pid": "0501", "detected": True}
        )
    )
    return service


@pytest.fixture
def mock_diagnostics_service():
    """Mock diagnostics service."""
    service = Mock()
    service.get_event_history = Mock(return_value=[])
    service.health_checks = {}
    return service


# =============================================================================
# Tests: Claude Client Loading
# =============================================================================


def test_load_claude_client_fallback_to_mock():
    """Test that _load_claude_client falls back to mock when real client unavailable."""
    # Should not raise; should return mock module
    client = _load_claude_client()

    assert hasattr(client, "call_claude_with_system")
    assert callable(client.call_claude_with_system)


def test_create_mock_claude_client():
    """Test mock Claude client creation."""
    mock_client = _create_mock_claude_client()

    assert hasattr(mock_client, "call_claude_with_system")

    # Test basic response
    payload = json.dumps({"user_message": "help", "context": {}})
    response = mock_client.call_claude_with_system(payload, "system_prompt")

    assert isinstance(response, str)
    assert len(response) > 0
    assert "help" in response.lower() or "controller" in response.lower()


def test_mock_claude_client_connection_issue():
    """Test mock client handles connection questions."""
    mock_client = _create_mock_claude_client()

    payload = json.dumps({"user_message": "board not detected", "context": {}})
    response = mock_client.call_claude_with_system(payload, "")

    assert "connection" in response.lower() or "usb" in response.lower()
    assert "cable" in response.lower()


def test_mock_claude_client_mapping_question():
    """Test mock client handles mapping questions."""
    mock_client = _create_mock_claude_client()

    context = {"mapping_summary": {"unmapped_inputs": 3}}
    payload = json.dumps({"user_message": "how do I map buttons?", "context": context})
    response = mock_client.call_claude_with_system(payload, "")

    assert "mapping" in response.lower() or "pin" in response.lower()
    assert "3" in response  # Should mention unmapped count


def test_mock_claude_client_invalid_json():
    """Test mock client handles invalid JSON gracefully."""
    mock_client = _create_mock_claude_client()

    response = mock_client.call_claude_with_system("not valid json", "")

    assert isinstance(response, str)
    assert "offline" in response.lower() or "trouble" in response.lower()


# =============================================================================
# Tests: ControllerAIService
# =============================================================================


def test_controller_ai_service_initialization():
    """Test service initializes with defaults."""
    service = ControllerAIService()

    assert service._llm_client is not None
    assert service._max_history >= 2


def test_controller_ai_service_custom_llm():
    """Test service accepts custom LLM client."""

    def custom_llm(payload: str, system_prompt: str) -> str:
        return "custom response"

    service = ControllerAIService(llm_client=custom_llm)
    response = service._llm_client("test", "prompt")

    assert response == "custom response"


def test_chat_empty_message_raises_error():
    """Test chat with empty message raises ControllerAIError."""
    service = ControllerAIService()

    with pytest.raises(ControllerAIError, match="Message cannot be empty"):
        service.chat("", Path("/tmp"))


def test_chat_successful(mock_drive_root, mock_detection_service, mock_diagnostics_service):
    """Test successful chat interaction."""

    def mock_llm(payload: str, system_prompt: str) -> str:
        return "This is a helpful response about controllers."

    service = ControllerAIService(
        detection_service=mock_detection_service,
        diagnostics_service=mock_diagnostics_service,
        llm_client=mock_llm,
    )

    result = service.chat("How do I map buttons?", mock_drive_root, device_id="test-device")

    assert result["reply"] == "This is a helpful response about controllers."
    assert "context" in result
    assert "history" in result
    assert len(result["history"]) == 2  # User + assistant


def test_chat_llm_returns_empty(mock_drive_root):
    """Test chat handles empty LLM response."""

    def empty_llm(payload: str, system_prompt: str) -> str:
        return ""

    service = ControllerAIService(llm_client=empty_llm)

    result = service.chat("test", mock_drive_root)

    assert "not seeing anything" in result["reply"].lower()


def test_chat_history_management(mock_drive_root):
    """Test chat history is managed with max_history limit."""

    def echo_llm(payload: str, system_prompt: str) -> str:
        data = json.loads(payload)
        return f"Echo: {data['user_message']}"

    service = ControllerAIService(llm_client=echo_llm, max_history=4)

    # Send multiple messages
    for i in range(5):
        service.chat(f"Message {i}", mock_drive_root, device_id="test")

    history = service._history["test"]

    # Should only keep last 4 messages (2 turns)
    assert len(history) == 4


def test_build_context_with_unmapped_inputs(mock_drive_root, mock_detection_service):
    """Test context building includes unmapped input hints."""
    service = ControllerAIService(detection_service=mock_detection_service)

    context = service.build_context(mock_drive_root)

    assert context.mapping_summary["unmapped_inputs"] == 1  # Button 3 is unmapped
    assert len(context.hints) > 0


def test_build_context_missing_mapping_file(tmp_path):
    """Test context building when mapping file doesn't exist."""
    service = ControllerAIService()

    context = service.build_context(tmp_path)

    assert context.mapping_summary["status"] == "missing"


@patch("backend.services.chuck.ai.detect_controllers")
def test_build_context_usb_permission_error(mock_detect, mock_drive_root):
    """Test context building handles USB permission errors gracefully."""
    from backend.services.usb_detector import USBPermissionError

    mock_detect.side_effect = USBPermissionError("Permission denied")

    service = ControllerAIService()
    context = service.build_context(mock_drive_root)

    assert any("permission" in hint.lower() for hint in context.hints)


def test_health_check():
    """Test AI service health check."""
    service = ControllerAIService()

    health = service.health()

    assert "provider" in health
    assert "services" in health
    assert "supports_actions" in health
    assert health["supports_actions"] is True


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_health_check_with_api_key():
    """Test health check reports API key configuration."""
    service = ControllerAIService()

    health = service.health()

    assert health["provider"]["configured"] is True


# =============================================================================
# Tests: AIContext
# =============================================================================


def test_ai_context_creation():
    """Test AIContext dataclass creation."""
    context = AIContext(
        mapping_summary={"status": "loaded"},
        board_status={"detected": True},
        handheld_devices=[],
        diagnostics={},
        hints=["Test hint"],
    )

    assert context.mapping_summary["status"] == "loaded"
    assert context.board_status["detected"] is True


def test_ai_context_to_dict():
    """Test AIContext serialization."""
    context = AIContext()

    data = context.to_dict()

    assert "timestamp" in data
    assert "mapping_summary" in data
    assert "board_status" in data
    assert "hints" in data


# =============================================================================
# Tests: Integration
# =============================================================================


def test_full_chat_flow_with_mock_client(mock_drive_root):
    """Test complete chat flow using mock Claude client (offline mode)."""
    # Use default initialization (will use mock client)
    service = ControllerAIService()

    # Chat about USB connection issue
    result = service.chat(
        "My board is not being detected", mock_drive_root, device_id="integration-test"
    )

    assert result["reply"]
    assert "usb" in result["reply"].lower() or "connection" in result["reply"].lower()


def test_persona_selection():
    """Test system prompt persona selection."""
    service = ControllerAIService()

    # Chuck persona (default)
    chuck_prompt = service._resolve_prompt("controller", None)
    assert "Chuck" in chuck_prompt or "Brooklyn" in chuck_prompt

    # Wizard persona
    wizard_prompt = service._resolve_prompt("controller", {"persona": "wizard"})
    assert "Wiz" in wizard_prompt or "wizard" in wizard_prompt.lower()


# =============================================================================
# Edge Cases
# =============================================================================


def test_chat_with_malformed_mapping_json(tmp_path):
    """Test chat handles malformed mapping JSON gracefully."""
    config_dir = tmp_path / "config" / "mappings"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "controls.json").write_text("not valid json {{{")

    service = ControllerAIService()
    context = service.build_context(tmp_path)

    assert context.mapping_summary["status"] == "unreadable"
    assert "error" in context.mapping_summary


def test_multiple_device_histories():
    """Test service maintains separate histories per device."""

    def counter_llm(payload: str, system_prompt: str) -> str:
        return "Response"

    service = ControllerAIService(llm_client=counter_llm)

    service.chat("Message 1", Path("/tmp"), device_id="device-a")
    service.chat("Message 2", Path("/tmp"), device_id="device-b")

    assert len(service._history["device-a"]) == 2
    assert len(service._history["device-b"]) == 2
    assert service._history["device-a"] != service._history["device-b"]
