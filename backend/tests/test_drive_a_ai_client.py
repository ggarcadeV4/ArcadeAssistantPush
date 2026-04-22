from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from backend.services.drive_a_ai_client import (
    PanelConfigNotFound,
    PanelDisabled,
    SecureAIClient,
)


class FakeQuery:
    def __init__(self, response_data, log):
        self._response_data = response_data
        self._log = log
        self._filters = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def is_(self, column, value):
        self._filters.append(("is_", column, value))
        return self

    def limit(self, value):
        self._filters.append(("limit", value))
        return self

    def execute(self):
        self._log.append(list(self._filters))
        return SimpleNamespace(data=self._response_data)


class FakeSupabase:
    def __init__(self, responses):
        self._responses = list(responses)
        self.query_log = []

    def table(self, name):
        assert name == "panel_config"
        response_data = self._responses.pop(0)
        return FakeQuery(response_data, self.query_log)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setattr(
        SecureAIClient,
        "_get_cabinet_id",
        lambda self: "cabinet-under-test",
    )
    SecureAIClient._panel_config_cache = {}
    return SecureAIClient()


def test_resolver_returns_cabinet_override_when_present(client):
    fake_supabase = FakeSupabase(
        [[{"panel": "dewey", "cabinet_id": "cab-1", "provider": "openai", "enabled": True}]]
    )
    client._supabase_client = fake_supabase

    resolved = client._resolve_panel_config("dewey", "cab-1")

    assert resolved["provider"] == "openai"
    assert len(fake_supabase.query_log) == 1
    assert ("eq", "cabinet_id", "cab-1") in fake_supabase.query_log[0]


def test_resolver_falls_back_to_fleet_default_when_no_override(client):
    fake_supabase = FakeSupabase(
        [
            [],
            [{"panel": "dewey", "cabinet_id": None, "provider": "gemini", "enabled": True}],
        ]
    )
    client._supabase_client = fake_supabase

    resolved = client._resolve_panel_config("dewey", "cab-2")

    assert resolved["provider"] == "gemini"
    assert len(fake_supabase.query_log) == 2
    assert ("is_", "cabinet_id", "null") in fake_supabase.query_log[1]


def test_resolver_raises_panel_config_not_found_when_neither_exists(client):
    fake_supabase = FakeSupabase([[], []])
    client._supabase_client = fake_supabase

    with pytest.raises(PanelConfigNotFound):
        client._resolve_panel_config("dewey", "cab-3")

    assert len(fake_supabase.query_log) == 2


def test_resolver_caches_result(client):
    fake_supabase = FakeSupabase(
        [
            [],
            [{"panel": "dewey", "cabinet_id": None, "provider": "gemini", "enabled": True}],
        ]
    )
    client._supabase_client = fake_supabase

    first = client._resolve_panel_config("dewey", "cab-4")
    second = client._resolve_panel_config("dewey", "cab-4")

    assert first == second
    assert len(fake_supabase.query_log) == 2


def test_resolver_invalidate_cache_forces_requery(client):
    fake_supabase = FakeSupabase(
        [
            [],
            [{"panel": "dewey", "cabinet_id": None, "provider": "gemini", "enabled": True}],
            [],
            [{"panel": "dewey", "cabinet_id": None, "provider": "openai", "enabled": True}],
        ]
    )
    client._supabase_client = fake_supabase

    first = client._resolve_panel_config("dewey", "cab-5")
    client.invalidate_cache("dewey", None)
    second = client._resolve_panel_config("dewey", "cab-5")

    assert first["provider"] == "gemini"
    assert second["provider"] == "openai"
    assert len(fake_supabase.query_log) == 4


def test_call_ai_raises_panel_disabled_when_enabled_false(client):
    client._resolve_panel_config = Mock(
        return_value={
            "panel": "dewey",
            "cabinet_id": "cab-disabled",
            "provider": "gemini",
            "enabled": False,
        }
    )

    with pytest.raises(PanelDisabled):
        client.call_ai(
            panel="dewey",
            messages=[{"role": "user", "content": "hello"}],
            cabinet_id="cab-disabled",
        )


def test_call_ai_passes_resolved_model_to_proxy(client, monkeypatch):
    client._resolve_panel_config = Mock(
        return_value={
            "panel": "blinky",
            "cabinet_id": "cab-1",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "enabled": True,
        }
    )

    captured = {}

    class FakeResponse:
        status_code = 200
        ok = True

        def json(self):
            return {"provider": "gemini", "model": "gemini-2.5-flash", "text": "ok"}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("backend.services.drive_a_ai_client.requests.post", fake_post)

    result = client.call_ai(
        panel="blinky",
        messages=[{"role": "user", "content": "hello"}],
        cabinet_id="cab-1",
    )

    assert captured["url"].endswith("/functions/v1/gemini-proxy")
    assert captured["json"]["model"] == "gemini-2.5-flash"
    assert result["model"] == "gemini-2.5-flash"


def test_call_ai_retries_fallback_provider_on_rate_limit(client, monkeypatch):
    client._resolve_panel_config = Mock(
        return_value={
            "panel": "blinky",
            "cabinet_id": "cab-1",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "fallback_provider": "anthropic",
            "fallback_model": "claude-3-5-haiku-20241022",
            "enabled": True,
        }
    )

    calls = []

    class RateLimitedResponse:
        status_code = 429
        ok = False
        text = "rate limited"

        def json(self):
            return {"error": "rate_limited"}

        def raise_for_status(self):
            raise requests.HTTPError("429 rate limited")

    class FallbackSuccessResponse:
        status_code = 200
        ok = True

        def json(self):
            return {
                "provider": "anthropic",
                "model": "claude-3-5-haiku-20241022",
                "text": "fallback ok",
            }

    def fake_post(url, headers, json, timeout):
        calls.append((url, json))
        if url.endswith("/functions/v1/gemini-proxy"):
            return RateLimitedResponse()
        return FallbackSuccessResponse()

    monkeypatch.setattr("backend.services.drive_a_ai_client.requests.post", fake_post)

    result = client.call_ai(
        panel="blinky",
        messages=[{"role": "user", "content": "hello"}],
        cabinet_id="cab-1",
    )

    assert len(calls) == 2
    assert calls[0][0].endswith("/functions/v1/gemini-proxy")
    assert calls[0][1]["model"] == "gemini-2.0-flash"
    assert calls[1][0].endswith("/functions/v1/anthropic-proxy")
    assert calls[1][1]["model"] == "claude-3-5-haiku-20241022"
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-3-5-haiku-20241022"


def test_call_ai_omits_noncanonical_fallback_model_label(client, monkeypatch):
    client._resolve_panel_config = Mock(
        return_value={
            "panel": "blinky",
            "cabinet_id": "cab-1",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "fallback_provider": "anthropic",
            "fallback_model": "Haiku 3.5",
            "enabled": True,
        }
    )

    calls = []

    class RateLimitedResponse:
        status_code = 429
        ok = False
        text = "rate limited"

        def json(self):
            return {"error": "rate_limited"}

        def raise_for_status(self):
            raise requests.HTTPError("429 rate limited")

    class FallbackSuccessResponse:
        status_code = 200
        ok = True

        def json(self):
            return {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "text": "fallback ok",
            }

    def fake_post(url, headers, json, timeout):
        calls.append((url, json))
        if url.endswith("/functions/v1/gemini-proxy"):
            return RateLimitedResponse()
        return FallbackSuccessResponse()

    monkeypatch.setattr("backend.services.drive_a_ai_client.requests.post", fake_post)

    result = client.call_ai(
        panel="blinky",
        messages=[{"role": "user", "content": "hello"}],
        cabinet_id="cab-1",
    )

    assert len(calls) == 2
    assert calls[1][0].endswith("/functions/v1/anthropic-proxy")
    assert "model" not in calls[1][1]
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-3-5-sonnet-20241022"
