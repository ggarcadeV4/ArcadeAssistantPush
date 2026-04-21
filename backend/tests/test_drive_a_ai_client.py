from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
