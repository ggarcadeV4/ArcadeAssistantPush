import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.dewey.service import (
    DeweyService,
    ProfileCreate,
    ProfileData,
    ProfilePreferences,
    ProfileUpdate,
)


class FakeBus:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, _event, callback):
        self.callbacks.append(callback)

    async def publish(self, _event_type, event):
        for callback in self.callbacks:
            callback(event)


class FakeTable:
    def __init__(self, storage, should_fail=False):
        self.storage = storage
        self.filters = {}
        self.should_fail = should_fail
        self._pending_payload = None

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _):
        return self

    def execute(self):
        if self.should_fail:
            raise RuntimeError("boom")
        if self._pending_payload:
            payload = self._pending_payload
            self._pending_payload = None
            return SimpleNamespace(data=[payload])
        user_id = self.filters.get("user_id")
        if user_id and user_id in self.storage:
            return SimpleNamespace(data=[self.storage[user_id]])
        return SimpleNamespace(data=[])

    def upsert(self, payload):
        if self.should_fail:
            raise RuntimeError("boom")
        self.storage[payload["user_id"]] = payload
        self._pending_payload = payload
        return self


class FakeSupabase:
    def __init__(self, storage=None, should_fail=False):
        self.storage = storage or {}
        self.should_fail = should_fail

    def table(self, _name):
        return FakeTable(self.storage, should_fail=self.should_fail)


@pytest.fixture
def tmp_fallback(tmp_path):
    file_path = tmp_path / "profiles.json"
    return file_path


def test_create_profile_persists_locally(tmp_fallback):
    service = DeweyService(
        supabase=FakeSupabase(),
        fallback_path=tmp_fallback,
        bus=FakeBus(),
    )
    payload = ProfileCreate(
        user_id="guest",
        display_name="Guest User",
        preferences=ProfilePreferences(genres=["retro"]),
    )
    profile = service.create_profile(payload)

    assert profile.display_name == "Guest User"
    stored = json.loads(tmp_fallback.read_text())["guest"]
    assert stored["preferences"]["genres"] == ["retro"]


def test_get_profile_returns_default_when_missing(tmp_fallback):
    service = DeweyService(
        supabase=FakeSupabase(),
        fallback_path=tmp_fallback,
        bus=FakeBus(),
    )

    profile = service.get_profile("mom")
    assert profile.user_id == "mom"
    assert json.loads(tmp_fallback.read_text())["mom"]["display_name"] == "Mom"


def test_update_profile_merges_preferences(tmp_fallback):
    supabase = FakeSupabase()
    service = DeweyService(
        supabase=supabase,
        fallback_path=tmp_fallback,
        bus=FakeBus(),
    )
    service.create_profile(ProfileCreate(user_id="dad"))

    updated = service.update_profile(
        "dad",
        ProfileUpdate(preferences=ProfilePreferences(genres=["fighters"])),
    )
    assert updated.preferences.genres == ["fighters"]


def test_handle_relay_event_updates_profile(tmp_fallback):
    bus = FakeBus()
    service = DeweyService(
        supabase=FakeSupabase(),
        fallback_path=tmp_fallback,
        bus=bus,
    )
    event_payload = {
        "user_id": "tim",
        "profile": {
            "display_name": "Tim",
            "preferences": {"kid_mode": True},
        },
    }
    for callback in bus.callbacks:
        callback(event_payload)

    stored = service.get_profile("tim")
    assert stored.preferences.kid_mode is True


def test_shared_users_validation():
    with pytest.raises(ValueError):
        ProfilePreferences(shared_users=["mom", "mom"])


def test_kid_mode_share_limit():
    prefs = ProfilePreferences(kid_mode=True, shared_users=["a", "b", "c", "d", "e", "f"])
    with pytest.raises(ValueError):
        ProfileData(user_id="kiddo", preferences=prefs)
