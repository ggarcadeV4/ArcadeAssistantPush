"""Controller Chuck AI Service.

Provides persona-aware AI responses for the controller mapping panels by
collecting live device state, mapping details, and recent diagnostics.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from backend.constants.drive_root import get_drive_root

from .detection import (
    get_detection_service,
    BoardDetectionError,
    BoardNotFoundError,
    BoardDetectionService,
    BoardInfo,
)
from .diagnostics import (
    get_diagnostics_service,
    DiagnosticsService,
    DiagnosticEvent,
    DiagnosticLevel,
)
from ..gamepad_detector import detect_controllers, GamepadDetectionError
from ..pacto_identity import (
    is_spoofed_xinput_vid_pid,
    looks_like_pacto,
    normalize_vid_pid,
)
from ..usb_detector import USBPermissionError, USBBackendError, detect_arcade_boards

logger = logging.getLogger(__name__)

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
PROMPT_FILES = {
    "controller-chuck": PROMPT_ROOT / "controller_chuck.prompt",
    "controller-wizard": PROMPT_ROOT / "controller_wizard.prompt",
}
KNOWLEDGE_FILES = {
    "controller-chuck": PROMPT_ROOT / "chuck_knowledge.md",
    "controller-wizard": PROMPT_ROOT / "wiz_knowledge.md",
}
DEFAULT_PROMPTS = {
    "controller-chuck": """You are Chuck, the Brooklyn-born controller mapping maestro for the Arcade Assistant.
- Always speak like a friendly arcade technician.
- Focus strictly on controller hardware, encoder boards, button mappings, diagnostics, and wiring questions.
- Explain next steps clearly. When you suggest changes, remind the user to preview or apply via the panel controls.
- If information is missing, ask clarifying questions before assuming.
- When hardware is disconnected or permissions are blocked, walk through step-by-step recovery.
""",
    "controller-wizard": """You are Wiz, the Console Wizardâ€”an ancient guide who helps apprentices configure handheld controllers.
- Use whimsical, encouraging language with a dash of mysticism.
- Provide clear, step-by-step instructions for detection, profile selection, and configuration.
- Encourage patience and celebrate progress; avoid technical jargon without explanation.
- If data is missing, politely request it before proceeding.
""",
}


def _load_prompt_text(key: str) -> str:
    file_path = PROMPT_FILES.get(key)
    try:
        if file_path and file_path.exists():
            return file_path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # pragma: no cover - prompt load failure is non-critical
        logger.warning("Failed to load %s prompt: %s", key, exc)
    return DEFAULT_PROMPTS.get(key, DEFAULT_PROMPTS["controller-chuck"]).strip()
def _load_local_knowledge(persona_key: str) -> str:
    """Load factory knowledge + any OTA patches. Read fresh every call (no caching)."""
    knowledge_parts = []

    factory_file = KNOWLEDGE_FILES.get(
        persona_key,
        PROMPT_ROOT / f"{persona_key.replace('-', '_')}_knowledge.md",
    )
    try:
        if factory_file.exists():
            knowledge_parts.append(factory_file.read_text(encoding="utf-8").strip())
    except Exception as exc:
        logger.warning("Failed to load factory knowledge (%s): %s", factory_file.name, exc)

    drive_root = get_drive_root(allow_cwd_fallback=True, context="chuck_ai_knowledge")
    patch_dir = drive_root / ".aa" / "state" / "knowledge_base"
    patch_prefix = persona_key.replace("-", "_") + "_patch_"
    try:
        patch_dir.mkdir(parents=True, exist_ok=True)
        if patch_dir.is_dir():
            for patch_file in sorted(patch_dir.glob(f"{patch_prefix}*.md")):
                try:
                    knowledge_parts.append(patch_file.read_text(encoding="utf-8").strip())
                except Exception as exc:
                    logger.warning("Failed to read knowledge patch %s: %s", patch_file.name, exc)
    except Exception as exc:
        logger.warning("Failed to scan knowledge_base directory: %s", exc)

    knowledge_parts = [part for part in knowledge_parts if part]
    if not knowledge_parts:
        return ""
    return "\n\n---KNOWLEDGE BASE---\n\n" + "\n\n---\n\n".join(knowledge_parts)


def _load_claude_client():
    """Dynamically load the shared Claude client with fallback to mock.

    Tries to load the real Claude client from services/+ai/claude_client.py.
    If that fails (missing dependencies, module not found), returns a mock
    client that provides offline responses from prompt templates.

    Returns:
        Module with call_claude_with_system function

    Raises:
        ControllerAIError: Only when both real and mock clients fail
    """
    client_path = Path(__file__).resolve().parents[3] / "services" / "+ai" / "claude_client.py"

    # Try loading the real Claude client first
    try:
        spec = importlib_util.spec_from_file_location("controller_ai_claude_client", client_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Claude client spec unavailable")

        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify the module has the required function
        if not hasattr(module, "call_claude_with_system"):
            raise AttributeError("Claude client missing call_claude_with_system")

        logger.info("Claude client loaded successfully from services/+ai")
        return module

    except (SyntaxError, ModuleNotFoundError, FileNotFoundError, ImportError, AttributeError, RuntimeError) as exc:
        logger.warning(f"Claude client unavailable ({exc.__class__.__name__}), using fallback mock")

        # Try Gateway client (HTTP bridge to Node.js)
        try:
            return _create_gateway_claude_client()
        except Exception as gw_exc:
            logger.warning(f"Gateway client unavailable: {gw_exc}")

        # Return a mock module with offline responses
        return _create_mock_claude_client()


def _create_gateway_claude_client():
    """Create a client that bridges to the Gateway's AI endpoint.

    This allows the backend to use the same Supabase/AI infrastructure
    as the frontend, without needing local API keys or direct access.
    """
    import types
    import urllib.request
    import urllib.error

    GATEWAY_URL = "http://127.0.0.1:8787/api/ai/chat"

    def gateway_call_claude(payload: str, system_prompt: str = "") -> str:
        """Call Gateway AI endpoint via HTTP."""
        try:
            # Parse payload to reconstruct messages
            data = json.loads(payload)
            user_msg = data.get("user_message", "")
            
            # Construct Gateway-compatible payload
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_msg})

            # Add context if present
            context = data.get("context")
            if context:
                # Append context as a developer note to the user message
                context_str = json.dumps(context, indent=2)
                messages[-1]["content"] += f"\n\n[Context Data]:\n{context_str}"

            req_body = {
                "provider": "gemini",  # Gemini 2.0 Flash (Golden Drive PRIMARY)
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024
            }

            req = urllib.request.Request(
                GATEWAY_URL,
                data=json.dumps(req_body).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "x-scope": "state"  # Required by Gateway
                }
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError(f"Gateway returned status {response.status}")
                
                resp_data = json.loads(response.read().decode('utf-8'))
                # Gateway returns standard Anthropic/OpenAI format
                # We need to extract the content string
                content = resp_data.get("content") or resp_data.get("message", {}).get("content")
                
                if isinstance(content, list):
                    # Handle block content (Anthropic)
                    text = ""
                    for block in content:
                        if block.get("type") == "text":
                            text += block.get("text", "")
                    return text
                
                return str(content) if content else ""

        except Exception as e:
            logger.error(f"Gateway AI call failed: {e}")
            # Re-raise to trigger fallback to mock
            raise

    # Create module-like object
    gateway_module = types.ModuleType("gateway_claude_client")
    gateway_module.call_claude_with_system = gateway_call_claude
    
    logger.info("Using Gateway AI client (http://127.0.0.1:8787)")
    return gateway_module


def _create_mock_claude_client():
    """Create a mock Claude client for offline operation.

    Provides basic responses based on common controller troubleshooting patterns.
    This ensures the controller AI remains functional even when the Claude API
    is unavailable or not configured.

    Returns:
        Mock module with call_claude_with_system function
    """
    import types

    def mock_call_claude(payload: str, system_prompt: str = "") -> str:
        """Mock Claude client that returns hardcoded helpful responses.

        Parses the payload JSON to extract user_message and provides
        context-aware responses for common controller scenarios.
        """
        try:
            import json
            data = json.loads(payload)
            user_msg = data.get("user_message", "").lower()
            context = data.get("context", {})

            # Pattern-based response selection
            if "not detected" in user_msg or "connection" in user_msg or "usb" in user_msg:
                return (
                    "I see you're having trouble with device connection. Here's what to check:\n\n"
                    "1. **Cable Connection**: Ensure the USB cable is firmly plugged into both "
                    "the encoder board and your PC. Try a different USB port (USB 2.0 works best).\n\n"
                    "2. **Power Check**: Some boards need external power. Look for LED indicators "
                    "on the board - they should be lit.\n\n"
                    "3. **Driver Installation**: On Windows, check Device Manager for yellow "
                    "exclamation marks. You may need manufacturer drivers.\n\n"
                    "4. **Permissions**: Try running the backend as Administrator for full USB access.\n\n"
                    "Once connected, the board should appear in the detection panel automatically."
                )

            elif "mapping" in user_msg or "pin" in user_msg or "button" in user_msg:
                unmapped = context.get("mapping_summary", {}).get("unmapped_inputs", 0)
                response = (
                    "For controller mapping, here's the workflow:\n\n"
                    "1. **Select Player**: Choose which player (1-4) you're configuring in the panel.\n\n"
                    "2. **Assign Pins**: Click each button label and assign it to a pin number "
                    "(1-32 for most boards).\n\n"
                    "3. **Test Inputs**: Use the test mode to verify each button registers correctly.\n\n"
                    "4. **Apply Changes**: Hit the green Apply button to save your configuration.\n\n"
                )
                if unmapped > 0:
                    response += f"**Note**: You currently have {unmapped} unmapped input(s). "
                    response += "Map them before applying to avoid incomplete configs."
                return response

            elif "mame" in user_msg or "generate" in user_msg or "config" in user_msg:
                return (
                    "To generate MAME configuration:\n\n"
                    "1. **Complete Mapping First**: Ensure all players have their buttons mapped "
                    "in the controls.json file.\n\n"
                    "2. **Generate Config**: Click the 'Generate MAME Config' button in Chuck's panel.\n\n"
                    "3. **Preview**: Review the generated default.cfg XML in the preview modal.\n\n"
                    "4. **Apply**: If the config looks good, hit Apply to write to "
                    "A:/config/mame/cfg/default.cfg.\n\n"
                    "This config tells MAME which keyboard keys (from your encoder) map to "
                    "arcade controls like P1_BUTTON1, P1_JOYSTICK_UP, etc."
                )

            elif "help" in user_msg or "how" in user_msg or "what" in user_msg:
                board_detected = context.get("board_status", {}).get("detected", False)
                status_msg = "âœ“ Board detected" if board_detected else "âš  No board detected"

                return (
                    f"**Controller Chuck Status**: {status_msg}\n\n"
                    "I can help you with:\n"
                    "- **Board Detection**: Troubleshooting USB connection issues\n"
                    "- **Pin Mapping**: Assigning buttons to encoder pins\n"
                    "- **MAME Config**: Generating arcade control configurations\n"
                    "- **Testing**: Verifying button inputs work correctly\n\n"
                    "What would you like help with? Be specific and I'll guide you through it!"
                )

            else:
                # Generic fallback
                return (
                    "I'm running in offline mode with limited AI capability. I can still help with "
                    "basic controller setup questions!\n\n"
                    "Try asking about:\n"
                    "- USB connection troubleshooting\n"
                    "- Button mapping workflow\n"
                    "- MAME configuration generation\n"
                    "- Testing arcade controls\n\n"
                    "For full AI assistance, configure ANTHROPIC_API_KEY or CLAUDE_API_KEY in your .env file."
                )

        except Exception as parse_exc:
            logger.debug(f"Mock client failed to parse payload: {parse_exc}")
            return (
                "I'm having trouble understanding your question. Could you rephrase it?\n\n"
                "I'm currently in offline mode and can help with:\n"
                "- USB connection issues\n"
                "- Controller mapping\n"
                "- MAME configuration\n"
            )

    # Create a module-like object
    mock_module = types.ModuleType("mock_claude_client")
    mock_module.call_claude_with_system = mock_call_claude

    return mock_module


class ControllerAIError(Exception):
    """Raised when the AI service cannot complete the request."""


@dataclass
class AIContext:
    """Structured context passed to the language model."""

    mapping_summary: Dict[str, Any] = field(default_factory=dict)
    board_status: Dict[str, Any] = field(default_factory=dict)
    handheld_devices: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    hints: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "mapping_summary": self.mapping_summary,
            "board_status": self.board_status,
            "handheld_devices": self.handheld_devices,
            "diagnostics": self.diagnostics,
            "hints": self.hints,
        }


class ControllerAIService:
    """Facade combining controller state with an AI persona response."""

    def __init__(
        self,
        detection_service: Optional[BoardDetectionService] = None,
        diagnostics_service: Optional[DiagnosticsService] = None,
        llm_client: Optional[Callable[[str, str], str]] = None,
        system_prompt: Optional[str] = None,
        max_history: int = 10,
    ) -> None:
        self._detection_service = detection_service
        self._diagnostics_service = diagnostics_service
        self._llm_client = llm_client or self._default_llm_client
        self._override_prompt = system_prompt.strip() if system_prompt else None
        self._prompt_cache: Dict[str, str] = {}
        self._max_history = max(2, max_history)
        self._history: Dict[str, List[Dict[str, str]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        message: str,
        drive_root: Path,
        device_id: str = "unknown",
        panel: str = "controller",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate an AI response for the Chuck persona."""
        if not message or not message.strip():
            raise ControllerAIError("Message cannot be empty")

        context = self.build_context(drive_root)
        if extra_context:
            context.mapping_summary["panel_payload"] = extra_context

        history = self._history.get(device_id, [])
        payload = self._build_user_payload(message, context.to_dict(), history, panel)
        prompt = self._resolve_prompt(panel, extra_context)

        try:
            reply = self._llm_client(payload, prompt)
        except ControllerAIError:
            raise
        except Exception as exc:
            logger.error("Controller AI request failed: %s", exc)
            raise ControllerAIError("AI provider unavailable") from exc

        reply_text = (reply or "").strip()
        if not reply_text:
            reply_text = "I'm not seeing anything yet. Could you restate the question with a bit more detail?"

        self._append_history(device_id, "user", message.strip())
        self._append_history(device_id, "assistant", reply_text)

        return {
            "reply": reply_text,
            "context": context.to_dict(),
            "history": self._history.get(device_id, []),
            "system_prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def build_context(self, drive_root: Path) -> AIContext:
        """Collect mapping, detection, and diagnostics data for the AI context."""
        mapping_summary = self._summarize_mapping(drive_root)
        board_status, hints = self._collect_board_status(mapping_summary)
        mapping_summary = self._apply_board_context(mapping_summary, board_status)
        handheld_devices, handheld_hints = self._collect_handheld_devices(board_status)
        diag_summary = self._collect_diagnostics()
        all_hints = hints + handheld_hints

        return AIContext(
            mapping_summary=mapping_summary,
            board_status=board_status,
            handheld_devices=handheld_devices,
            diagnostics=diag_summary,
            hints=[h for h in all_hints if h],
        )

    @staticmethod
    def _apply_board_context(
        mapping_summary: Dict[str, Any],
        board_status: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = dict(mapping_summary or {})
        configured_board = summary.get("board") or {}
        summary["board_source"] = board_status.get("source") or "none"

        if configured_board:
            summary["configured_board"] = configured_board

        user_override = (
            configured_board.get("detected") is False
            and bool(configured_board.get("name"))
        )

        live_board = board_status.get("details") or {}
        if board_status.get("source") == "canonical_board_lane" and live_board:
            board_name = live_board.get("name")
            board_source = "canonical_board_lane"
            if user_override:
                board_name = configured_board["name"]
                board_source = "user_override"
            summary["board"] = {
                "name": board_name,
                "vid": live_board.get("vid"),
                "pid": live_board.get("pid"),
                "detected": bool(board_status.get("detected")),
                "source": board_source,
            }
        elif user_override:
            summary["board"] = {
                "name": configured_board["name"],
                "vid": configured_board.get("vid"),
                "pid": configured_board.get("pid"),
                "detected": False,
                "source": "user_override",
            }
        elif configured_board:
            summary["board"] = configured_board

        return summary

    def health(self) -> Dict[str, Any]:
        """Return AI readiness diagnostics."""
        provider_configured = bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        )
        detection_ready = self._detection_service is not None
        diagnostics_ready = self._diagnostics_service is not None

        return {
            "provider": {"configured": provider_configured},
            "services": {
                "detection": detection_ready,
                "diagnostics": diagnostics_ready,
            },
            "supports_actions": True,
            "supports_streaming": False,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_history(self, device_id: str, role: str, content: str) -> None:
        history = self._history.setdefault(device_id, [])
        history.append({"role": role, "content": content})
        if len(history) > self._max_history:
            self._history[device_id] = history[-self._max_history :]

    def _build_user_payload(
        self,
        message: str,
        context: Dict[str, Any],
        history: List[Dict[str, str]],
        panel: str,
    ) -> str:
        payload = {
            "panel": panel,
            "user_message": message.strip(),
            "context": context,
            "recent_turns": history[-5:],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _default_llm_client(self, payload: str, system_prompt: str) -> str:
        module = _load_claude_client()
        try:
            response = module.call_claude_with_system(payload, system_prompt=system_prompt)
        except Exception as exc:
            raise ControllerAIError(str(exc)) from exc

        if not response:
            raise ControllerAIError("Claude response was empty")
        if response.startswith("[") and "Claude" in response:
            raise ControllerAIError(response)
        return response

    def _resolve_prompt(
        self, panel: str, extra_context: Optional[Dict[str, Any]]
    ) -> str:
        if self._override_prompt:
            return self._override_prompt

        ctx = extra_context or {}
        persona = ctx.get("persona")
        is_diagnosis = bool(ctx.get("isDiagnosisMode", False))

        key = "controller-chuck"
        if persona == "wizard" or (panel and "wizard" in panel):
            key = "controller-wizard"

        # V1 Constitution: hot-swap to Diagnosis Mode prompt when flag is set.
        # Cache both variants independently so neither has to reload from disk.
        cache_key = f"{key}--diagnosis" if is_diagnosis else key

        if cache_key not in self._prompt_cache:
            raw = _load_prompt_text(key)
            diag_delimiter = "---DIAGNOSIS---"
            if diag_delimiter in raw:
                chat_part, diag_part = raw.split(diag_delimiter, 1)
                self._prompt_cache[key] = chat_part.strip()
                self._prompt_cache[f"{key}--diagnosis"] = diag_part.strip()
            else:
                # No delimiter â€” same prompt for both modes (safe fallback)
                self._prompt_cache[key] = raw
                self._prompt_cache[f"{key}--diagnosis"] = raw

        base_prompt = self._prompt_cache[cache_key]
        knowledge = _load_local_knowledge(key)
        return base_prompt + knowledge if knowledge else base_prompt


    def _summarize_mapping(self, drive_root: Path) -> Dict[str, Any]:
        mapping_file = drive_root / "config" / "mappings" / "controls.json"
        summary: Dict[str, Any] = {
            "file_exists": mapping_file.exists(),
            "players": {},
            "unmapped_inputs": 0,
            "last_modified": None,
        }

        if not mapping_file.exists():
            summary["status"] = "missing"
            return summary

        try:
            mapping_data = json.loads(mapping_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read mapping file: %s", exc)
            summary["status"] = "unreadable"
            summary["error"] = str(exc)
            return summary

        summary["status"] = "loaded"
        summary["last_modified"] = mapping_data.get("last_modified")
        mappings = mapping_data.get("mappings", {})
        per_player: Dict[str, Dict[str, Any]] = {}
        unmapped = 0

        for control_key, data in mappings.items():
            if not isinstance(data, dict):
                continue
            parts = control_key.split(".", 1)
            player = parts[0] if len(parts) == 2 else "unknown"
            player_entry = per_player.setdefault(
                player,
                {"total": 0, "mapped": 0, "unmapped_controls": []},
            )
            player_entry["total"] += 1
            pin = data.get("pin")
            label = data.get("label") or control_key
            if pin is None or pin == "":
                unmapped += 1
                player_entry["unmapped_controls"].append(label)
            else:
                player_entry["mapped"] += 1

        summary["players"] = per_player
        summary["unmapped_inputs"] = unmapped
        summary["board"] = mapping_data.get("board", {})
        summary["metadata"] = {
            "version": mapping_data.get("version"),
            "modified_by": mapping_data.get("modified_by"),
        }
        return summary

    def _collect_board_status(
        self, mapping_summary: Dict[str, Any]
    ) -> tuple[Dict[str, Any], List[str]]:
        hints: List[str] = []
        board_info = mapping_summary.get("board") or {}
        vid = board_info.get("vid")
        pid = board_info.get("pid")
        status: Dict[str, Any] = {
            "configured": bool(vid and pid),
            "detected": False,
            "details": {},
            "source": "none",
            "configured_board": board_info,
            "runtime_endpoints": [],
        }

        live_board = self._select_live_encoder_board()
        if live_board:
            status["detected"] = bool(live_board.get("detected", True))
            status["details"] = live_board
            status["source"] = "canonical_board_lane"

            configured_key = self._normalize_vid_pid_pair(vid, pid)
            live_key = self._normalize_vid_pid_pair(
                live_board.get("vid"),
                live_board.get("pid"),
            )
            status["configured_match"] = bool(
                configured_key and live_key and configured_key == live_key
            )
            if board_info.get("name") and board_info.get("name") != live_board.get("name"):
                hints.append(
                    f"Saved mapping board '{board_info.get('name')}' does not match the live encoder board "
                    f"'{live_board.get('name')}'."
                )
            if configured_key and live_key and configured_key != live_key:
                hints.append(
                    f"Saved mapping VID/PID {configured_key} does not match the live encoder board {live_key}."
                )
            return status, hints

        service = self._detection_service or get_detection_service()
        self._detection_service = service

        if not vid or not pid:
            hints.append("No encoder board VID/PID configured yet.")
            return status, hints

        try:
            board: BoardInfo = service.detect_board(vid, pid, use_cache=True)
            status["detected"] = board.detected
            status["details"] = board.to_dict()
            status["source"] = "configured_mapping"
            if not board.detected:
                hints.append(f"Board {vid}:{pid} not currently detected.")
        except BoardNotFoundError:
            hints.append(f"Configured board {vid}:{pid} is not connected.")
        except BoardDetectionError as exc:
            hints.append(f"Board detection error: {exc}")
        except Exception as exc:  # pragma: no cover - unexpected hardware error
            logger.warning("Unexpected board detection error: %s", exc)
            hints.append("Unexpected error while detecting the encoder board.")

        return status, hints

    def _collect_handheld_devices(
        self,
        board_status: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        hints: List[str] = []
        try:
            devices = detect_controllers(use_cache=True)
            devices = devices or []

            if board_status and self._is_pacto_board_status(board_status):
                expected_children = int(
                    board_status.get("details", {}).get("xinput_nodes")
                    or board_status.get("details", {}).get("players")
                    or 0
                )
                generic_xinput = [
                    device for device in devices
                    if self._is_generic_xinput_controller(device)
                ]
                if expected_children and len(devices) == expected_children and len(generic_xinput) == len(devices):
                    board_status["runtime_endpoints"] = generic_xinput
                    hints.append(
                        f"Detected {expected_children} Xbox-style XInput endpoint(s) as child controllers of the encoder board."
                    )
                    return [], hints

            return devices, hints
        except USBPermissionError as exc:
            hints.append("USB permission denied. Try running the backend as Administrator or add the user to plugdev.")
            logger.warning("USB permission error while detecting controllers: %s", exc)
        except USBBackendError as exc:
            hints.append("USB backend unavailable. Start the backend on Windows or attach devices with usbipd (WSL).")
            logger.warning("USB backend unavailable during handheld detection: %s", exc)
        except GamepadDetectionError as exc:
            hints.append(f"Handheld detection issue: {exc}")
        except Exception as exc:  # pragma: no cover - unexpected hardware error
            hints.append("Handheld detection failed due to an unexpected error.")
            logger.error("Unhandled controller detection error: %s", exc)
        return [], hints

    @staticmethod
    def _normalize_vid_pid_pair(vid: Any, pid: Any) -> Optional[str]:
        """Wave 2: delegates to shared ``pacto_identity.normalize_vid_pid``."""
        return normalize_vid_pid(vid, pid)

    @staticmethod
    def _normalize_live_board(board: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": board.get("name") or board.get("board_name") or "Unknown Board",
            "vid": board.get("vid"),
            "pid": board.get("pid"),
            "vid_pid": normalize_vid_pid(board.get("vid"), board.get("pid")),
            "manufacturer": board.get("vendor") or board.get("manufacturer"),
            "board_type": board.get("board_type") or board.get("type"),
            "players": board.get("players"),
            "parent_hub": board.get("parent_hub"),
            "xinput_nodes": board.get("xinput_nodes"),
            "detected": bool(board.get("detected", False)),
            "source": board.get("source") or "canonical_board_lane",
        }

    @staticmethod
    def _looks_like_pacto_board(board: Dict[str, Any]) -> bool:
        """Wave 2: delegates to shared ``pacto_identity.looks_like_pacto``."""
        return looks_like_pacto(board)

    def _select_live_encoder_board(self) -> Optional[Dict[str, Any]]:
        try:
            detected_boards = [
                self._normalize_live_board(board)
                for board in detect_arcade_boards()
                if board.get("detected", False)
            ]
        except Exception as exc:
            logger.debug("Canonical live board detection unavailable for Chuck AI: %s", exc)
            return None

        if not detected_boards:
            return None

        pacto_board = next(
            (board for board in detected_boards if looks_like_pacto(board)),
            None,
        )
        return pacto_board or detected_boards[0]

    def _is_pacto_board_status(self, board_status: Dict[str, Any]) -> bool:
        details = board_status.get("details") or {}
        return looks_like_pacto(details)

    @staticmethod
    def _is_generic_xinput_controller(device: Dict[str, Any]) -> bool:
        if not is_spoofed_xinput_vid_pid(device.get("vid"), device.get("pid")):
            return False
        profile_id = str(device.get("profile_id") or "").lower()
        name = str(device.get("name") or device.get("product") or "").lower()
        return profile_id == "xbox_360" or "xinput" in name or "xbox" in name

    def _collect_diagnostics(self) -> Dict[str, Any]:
        service = self._diagnostics_service or get_diagnostics_service()
        self._diagnostics_service = service
        try:
            events = service.get_event_history(limit=10)
            health = [hc.to_dict() for hc in service.health_checks.values()]
            return {
                "recent_events": [self._event_to_dict(e) for e in events],
                "health_checks": health,
            }
        except Exception as exc:  # pragma: no cover - diagnostics failures are non-critical
            logger.warning("Failed to collect diagnostics: %s", exc)
            return {"recent_events": [], "health_checks": [], "error": str(exc)}

    @staticmethod
    def _event_to_dict(event: DiagnosticEvent) -> Dict[str, Any]:
        data = event.to_dict()
        data["timestamp_iso"] = datetime.fromtimestamp(event.timestamp).isoformat()
        return data



_controller_ai_service: Optional[ControllerAIService] = None


# ============================================================================
# Diagnosis Mode â€” AI Tool: remediate_controller_config (Q5)
# ============================================================================

def remediate_controller_config(
    drive_root: Path,
    control_key: str,
    pin: int,
    *,
    label: Optional[str] = None,
    source: str = "ai_tool",
    auto_commit: bool = False,
    confirmed_by: str = "ai_tool",
    reasoning: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Diagnosis Mode AI Tool: propose or commit a single GPIO pin override.

    Decision refs (diagnosis_mode_plan.md):
      Q5  â€” Gemini 2.0 Flash calls this tool via function calling when
             Diagnosis Mode is active and hardware truth requires a fix.
      Q7  â€” Hardware truth wins; conflicts are always surfaced before commit.
      Q8  â€” auto_commit=False (default) returns a proposal for UI confirmation;
             auto_commit=True commits immediately (AI-only, for unambiguous fixes).

    Called by:
      - ChuckSidebar when a Diagnosis Mode AI response includes a tool call
      - POST /profiles/mapping-override endpoint (via HTTP)

    Returns:
      {
        "phase": "proposal" | "committed",
        "control_key": str,
        "pin": int,
        "conflicts": [...],
        "result": {...} if committed,
        "reasoning": str,
      }
    """
    from .controller_bridge import ControllerBridge, ConflictError, ControllerBridgeError

    bridge   = ControllerBridge(drive_root)
    proposal = bridge.propose_override(
        control_key = control_key,
        pin         = pin,
        label       = label,
        source      = source,
    )

    has_errors = any(c["severity"] == "error" for c in proposal["conflicts"])

    # If conflicts and not auto-committing â€” return proposal for user review
    if has_errors and not auto_commit:
        logger.info(
            "[remediate_controller_config] Proposal halted â€” %d error conflict(s) on %s",
            len([c for c in proposal["conflicts"] if c["severity"] == "error"]),
            control_key,
        )
        return {
            "phase"       : "proposal",
            "control_key" : control_key,
            "pin"         : pin,
            "conflicts"   : proposal["conflicts"],
            "reasoning"   : reasoning,
            "message"     : (
                f"I found {len(proposal['conflicts'])} conflict(s) that need your confirmation "
                f"before I can assign pin {pin} to {control_key}. "
                "Review the proposal above and confirm to proceed."
            ),
        }

    # Auto-commit (clean path or forced)
    if auto_commit or not has_errors:
        try:
            result = bridge.commit_override(
                proposal,
                confirmed_by = confirmed_by,
                force        = auto_commit and has_errors,
            )
            logger.info(
                "[remediate_controller_config] Committed %s â†’ pin %d",
                control_key, pin,
            )
            return {
                "phase"       : "committed",
                "control_key" : control_key,
                "pin"         : pin,
                "conflicts"   : proposal["conflicts"],
                "result"      : result,
                "reasoning"   : reasoning,
                "message"     : (
                    f"Done. Pin {pin} is now assigned to {control_key}. "
                    + (f"Warnings: {len(result.get('warnings', []))}." if result.get("warnings") else "")
                ),
            }
        except (ConflictError, ControllerBridgeError) as exc:
            logger.warning("[remediate_controller_config] Commit failed: %s", exc)
            return {
                "phase"    : "error",
                "error"    : str(exc),
                "conflicts": proposal["conflicts"],
                "reasoning": reasoning,
            }

    # Fallback â€” return proposal if no explicit commit decision
    return {
        "phase"       : "proposal",
        "control_key" : control_key,
        "pin"         : pin,
        "conflicts"   : proposal["conflicts"],
        "reasoning"   : reasoning,
    }


def get_controller_ai_service() -> ControllerAIService:
    global _controller_ai_service
    if _controller_ai_service is None:
        _controller_ai_service = ControllerAIService()
    return _controller_ai_service

