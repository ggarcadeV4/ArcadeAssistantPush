"""
Secure AI Client for Drive A - Arcade Assistant.

This module routes cabinet-side AI calls through Supabase Edge Function proxies.
"""

import logging
import os
import threading
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple

import requests

from backend.constants.drive_root import get_drive_root

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    create_client = None


# Import telemetry function (try-except for standalone usage)
try:
    from backend.services.supabase_client import SupabaseClient

    _supabase = SupabaseClient()

    def _send_telemetry(cabinet_id, level, code, message, payload=None, panel="system"):
        try:
            from backend.services.supabase_client import TelemetryEntry

            entry = TelemetryEntry(
                cabinet_id=cabinet_id,
                level=level,
                code=code,
                message=message,
                payload=payload,
            )
            _supabase.send_telemetry(entry)
        except Exception:
            pass  # Fire-and-forget
except ImportError:

    def _send_telemetry(*args, **kwargs):
        pass  # No telemetry available


logger = logging.getLogger(__name__)
_ALLOWED_PROVIDERS = {"gemini", "anthropic", "openai", "grok"}


class PanelConfigNotFound(Exception):
    """Raised when no panel_config row can be resolved for a panel/cabinet pair."""

    def __init__(self, panel: str, cabinet_id: Optional[str] = None):
        self.panel = panel
        self.cabinet_id = cabinet_id
        if cabinet_id:
            message = f"No panel_config found for panel='{panel}' cabinet_id='{cabinet_id}'"
        else:
            message = f"No panel_config found for panel='{panel}'"
        super().__init__(message)


class PanelDisabled(Exception):
    """Raised when panel_config disables AI calls for a panel."""

    def __init__(self, panel: str):
        self.panel = panel
        super().__init__(f"Panel '{panel}' is disabled in panel_config")


class SecureAIClient:
    """
    Unified client for calling AI services through Supabase Edge Functions.
    All API keys are stored securely in Supabase and never exposed to the cabinet.
    """

    _panel_config_cache: Dict[str, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()

    def __init__(self):
        self.supabase_url = os.environ.get("SUPABASE_URL")
        self._service_role_key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
        )
        self.anon_key = os.environ.get("SUPABASE_ANON_KEY")
        self.service_key = self._service_role_key or self.anon_key
        self.supabase_client_key = self._service_role_key or self.anon_key
        self.supabase_request_key = self.anon_key or self.service_key
        self.cabinet_id = self._get_cabinet_id()
        self.tenant_id = os.environ.get("TENANT_ID", "gg_arcade")
        self._supabase_client = None

        if not self.supabase_url or not self.supabase_client_key or not self.supabase_request_key:
            raise ValueError(
                "SUPABASE_URL and either SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SERVICE_KEY "
                "or SUPABASE_ANON_KEY must be set"
            )

    @classmethod
    def _cache_key(cls, panel: str, cabinet_id: Optional[str]) -> str:
        return f"{panel}:{cabinet_id}" if cabinet_id else f"{panel}:default"

    @classmethod
    def invalidate_cache(cls, panel: str, cabinet_id: Optional[str] = None) -> None:
        cache_key = cls._cache_key(panel, cabinet_id)
        with cls._cache_lock:
            cls._panel_config_cache.pop(cache_key, None)

    def _get_supabase_client(self):
        if self._supabase_client is not None:
            return self._supabase_client
        if create_client is None:
            raise RuntimeError("supabase client is not installed")
        self._supabase_client = create_client(self.supabase_url, self.supabase_client_key)
        return self._supabase_client

    def _proxy_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.supabase_request_key}",
            "Content-Type": "application/json",
            "apikey": self.supabase_request_key,
        }

    def _get_cabinet_id(self) -> str:
        """Read cabinet ID from drive_root/.aa/device_id.txt."""
        drive_root = get_drive_root(
            allow_cwd_fallback=True, context="drive_a_ai_client cabinet id"
        )
        device_id_path = os.path.join(str(drive_root), ".aa", "device_id.txt")
        try:
            with open(device_id_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Warning: Could not read cabinet_id from {device_id_path}: {e}")
            return "unknown-cabinet"

    @staticmethod
    def _split_system_messages(
        messages: List[Dict[str, Any]], system: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if system is not None:
            return [dict(msg) for msg in messages], system

        system_parts: List[str] = []
        filtered_messages: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                if isinstance(content, str) and content:
                    system_parts.append(content)
                continue
            filtered_messages.append(dict(msg))

        merged_system = "\n\n".join(system_parts) if system_parts else None
        return filtered_messages, merged_system

    def _query_panel_config(
        self, panel: str, cabinet_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        query = self._get_supabase_client().table("panel_config").select("*").eq("panel", panel)
        if cabinet_id is None:
            query = query.is_("cabinet_id", "null")
        else:
            query = query.eq("cabinet_id", cabinet_id)

        response = query.limit(1).execute()
        data = getattr(response, "data", None) or []
        return data[0] if data else None

    def _resolve_panel_config(self, panel: str, cabinet_id: str) -> Dict[str, Any]:
        override_key = self._cache_key(panel, cabinet_id)
        default_key = self._cache_key(panel, None)

        with self._cache_lock:
            cached = self._panel_config_cache.get(override_key)
            if cached is not None:
                return dict(cached)
            cached_default = self._panel_config_cache.get(default_key)
            if cached_default is not None:
                return dict(cached_default)

        try:
            override = self._query_panel_config(panel, cabinet_id)
            if override:
                with self._cache_lock:
                    self._panel_config_cache[override_key] = dict(override)
                return dict(override)

            fleet_default = self._query_panel_config(panel, None)
            if fleet_default:
                with self._cache_lock:
                    self._panel_config_cache[default_key] = dict(fleet_default)
                return dict(fleet_default)
        except Exception as exc:
            logger.exception(
                "Failed resolving panel_config for panel=%s cabinet_id=%s",
                panel,
                cabinet_id,
            )
            raise PanelConfigNotFound(panel, cabinet_id) from exc

        raise PanelConfigNotFound(panel, cabinet_id)

    def call_ai(
        self,
        panel: str,
        messages: List[Dict[str, Any]],
        cabinet_id: str,
        *,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        grounding: bool = False,
    ) -> Dict[str, Any]:
        """
        Unified AI call that routes to the correct provider based on panel_config.
        """
        if not panel:
            raise ValueError("panel is required")
        if not cabinet_id:
            raise ValueError("cabinet_id is required")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")

        resolved = self._resolve_panel_config(panel, cabinet_id)
        if resolved.get("enabled") is False:
            raise PanelDisabled(panel)

        provider = resolved.get("provider")
        if provider not in _ALLOWED_PROVIDERS:
            raise PanelConfigNotFound(panel, cabinet_id)

        payload_messages, system_text = self._split_system_messages(messages, system)
        payload: Dict[str, Any] = {
            "panel": panel,
            "cabinet_id": cabinet_id,
            "messages": payload_messages,
        }
        if system_text is not None:
            payload["system"] = system_text
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if tools is not None:
            payload["tools"] = tools
        if grounding:
            payload["grounding"] = True

        url = f"{self.supabase_url}/functions/v1/{provider}-proxy"
        start_time = time.time()
        response = requests.post(
            url,
            headers=self._proxy_headers(),
            json=payload,
            timeout=60,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 404:
            try:
                error_body = response.json()
            except ValueError:
                error_body = None
            if isinstance(error_body, dict) and error_body.get("code") == "PANEL_CONFIG_NOT_FOUND":
                logger.error(
                    "Edge Function reported PANEL_CONFIG_NOT_FOUND for panel=%s cabinet_id=%s",
                    panel,
                    cabinet_id,
                )
                raise PanelConfigNotFound(panel, cabinet_id)

        if not response.ok:
            logger.error(
                "AI proxy request failed for panel=%s provider=%s status=%s body=%s",
                panel,
                provider,
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        result = response.json()
        if result.get("disabled") is True:
            raise PanelDisabled(panel)

        usage = result.get("usage", {}) or {}
        result_provider = result.get("provider", provider)
        result_model = result.get("model", resolved.get("model", "unknown"))
        _send_telemetry(
            cabinet_id,
            "INFO",
            "AI_CALL",
            f"{result_provider} {result_model}: {latency_ms}ms",
            {
                "provider": result_provider,
                "model": result_model,
                "panel": panel,
                "latency_ms": latency_ms,
                "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
                "output_tokens": usage.get("output_tokens")
                or usage.get("completion_tokens"),
            },
            panel,
        )

        return result

    def call_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
        temperature: float = 1.0,
        panel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED: use call_ai(panel=...) instead.

        The model parameter is ignored. panel_config determines the provider/model.
        """
        warnings.warn(
            "call_anthropic is deprecated, use call_ai(panel=...) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        cabinet_id = os.environ.get("AA_DEVICE_ID") or self.cabinet_id or "unknown"
        return self.call_ai(
            panel=panel or "wiz",
            messages=list(messages),
            cabinet_id=cabinet_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def call_gemini(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-2.5-flash",
        max_tokens: int = 4096,
        temperature: float = 0.4,
        panel: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED: use call_ai(panel=...) instead.

        The model parameter is ignored. panel_config determines the provider/model.
        """
        warnings.warn(
            "call_gemini is deprecated, use call_ai(panel=...) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        cabinet_id = os.environ.get("AA_DEVICE_ID") or self.cabinet_id or "unknown"
        return self.call_ai(
            panel=panel or "dewey",
            messages=list(messages),
            cabinet_id=cabinet_id,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

    def call_openai(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
        panel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED: use call_ai(panel=...) instead.

        The model parameter is ignored. panel_config determines the provider/model.
        """
        warnings.warn(
            "call_openai is deprecated, use call_ai(panel=...) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        cabinet_id = os.environ.get("AA_DEVICE_ID") or self.cabinet_id or "unknown"
        return self.call_ai(
            panel=panel or "vicky",
            messages=list(messages),
            cabinet_id=cabinet_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def call_elevenlabs(
        self,
        text: str,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",
        model_id: str = "eleven_monolingual_v1",
        voice_settings: Optional[Dict[str, float]] = None,
        panel: Optional[str] = None,
    ) -> bytes:
        """
        Call ElevenLabs API through Supabase Edge Function.
        """
        url = f"{self.supabase_url}/functions/v1/elevenlabs-proxy"

        payload = {
            "text": text,
            "voice_id": voice_id,
            "model_id": model_id,
            "cabinet_id": self.cabinet_id,
            "tenant_id": self.tenant_id,
            "panel": panel,
        }

        if voice_settings:
            payload["voice_settings"] = voice_settings

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )

        response.raise_for_status()
        return response.content


if __name__ == "__main__":
    print("Testing Secure AI Client...")

    try:
        client = SecureAIClient()

        print("\n1. Testing Anthropic...")
        response = client.call_anthropic(
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            panel="test",
        )
        print(f"Claude says: {response['content'][0]['text']}")

        print("\n2. Testing OpenAI...")
        response = client.call_openai(
            messages=[{"role": "user", "content": "Say hello in 5 words"}],
            model="gpt-4",
            panel="test",
        )
        print(f"GPT says: {response['choices'][0]['message']['content']}")

        print("\n3. Testing ElevenLabs...")
        audio_data = client.call_elevenlabs(
            text="Welcome to the arcade!",
            panel="test",
        )
        output_path = os.path.join(
            str(
                get_drive_root(
                    allow_cwd_fallback=True,
                    context="drive_a_ai_client TTS output",
                )
            ),
            "state",
            "audio",
            "welcome.mp3",
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"Audio saved to: {output_path}")

        print("\nAll tests passed!")

    except Exception as e:
        print(f"\nError: {e}")
