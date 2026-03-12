"""Profile service powering Panel 2 (Dewey liaison)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Set

try:
    from cachetools import TTLCache
except ImportError:  # pragma: no cover - fallback when dependency missing
    class TTLCache(dict):  # type: ignore
        def __init__(self, maxsize: int, ttl: int):
            super().__init__()

from pydantic import BaseModel, Field, field_validator, model_validator

from ..bus_events import EventType, StateEvent, get_event_bus, log_state_event
from ..supabase_client import SupabaseClient, get_client

logger = logging.getLogger(__name__)


class ProfilePreferences(BaseModel):
    """Structured preferences used across panels."""

    genres: List[str] = Field(default_factory=list)
    favorite_platforms: List[str] = Field(default_factory=list)
    kid_mode: bool = False
    shared_users: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("shared_users")
    @classmethod
    def validate_shared_users(cls, value: List[str]) -> List[str]:
        seen: Set[str] = set()
        for entry in value:
            if entry in seen:
                raise ValueError("shared_users entries must be unique")
            seen.add(entry)
        if len(value) > 10:
            raise ValueError("shared_users cannot exceed 10 family members")
        return value


class ProfileData(BaseModel):
    """Family profile shared between panels."""

    user_id: str
    display_name: str = "Guest"
    family_group_id: Optional[str] = None
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    def _coerce_preferences(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        raw = values.get("preferences")
        if raw is None:
            values["preferences"] = ProfilePreferences()
        elif not isinstance(raw, ProfilePreferences):
            values["preferences"] = ProfilePreferences(**raw)
        return values

    @model_validator(mode="after")
    def _validate_family_rules(self) -> "ProfileData":
        if self.preferences.kid_mode and len(self.preferences.shared_users) > 5:
            raise ValueError("Kid mode profiles can only share with five users")
        return self

    @property
    def is_family_safe(self) -> bool:
        return bool(self.preferences.kid_mode) and len(self.preferences.shared_users) <= 5


class ProfileCreate(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    family_group_id: Optional[str] = None
    preferences: Optional[ProfilePreferences] = None


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    family_group_id: Optional[str] = None
    preferences: Optional[ProfilePreferences] = None


class DeweyService:
    """Profile CRUD with Supabase + local fallback."""

    TABLE_NAME = "dewey_profiles"
    FALLBACK_PATH = Path("state/dewey/profiles.json")

    def __init__(
        self,
        supabase: Optional[SupabaseClient] = None,
        fallback_path: Optional[Path] = None,
        bus=None,
    ) -> None:
        self._supabase = supabase or get_client()
        self._fallback_path = Path(fallback_path or self.FALLBACK_PATH)
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = TTLCache(maxsize=128, ttl=300)
        self._cache_lock = RLock()
        self._bus = bus or get_event_bus()
        self._bus.subscribe(EventType.STATE_UPDATED.value, self.handle_relay_event)

    def get_profile(self, user_id: str) -> ProfileData:
        with self._cache_lock:
            cached = self._cache.get(user_id)
            if cached:
                return cached

        profile = self._fetch_remote_profile(user_id)
        if not profile:
            profile = self._fetch_local_profile(user_id)
        if not profile:
            profile = self._default_profile(user_id)
            self._persist_local(profile)

        with self._cache_lock:
            self._cache[user_id] = profile
        return profile

    def create_profile(self, payload: ProfileCreate) -> ProfileData:
        profile = ProfileData(
            user_id=payload.user_id,
            display_name=payload.display_name or payload.user_id.title(),
            family_group_id=payload.family_group_id,
            preferences=payload.preferences or ProfilePreferences(),
            updated_at=datetime.now(timezone.utc),
        )
        self._persist(profile)
        self._invalidate_cache(profile.user_id)
        return profile

    def update_profile(self, user_id: str, payload: ProfileUpdate) -> ProfileData:
        existing = self.get_profile(user_id)
        updated = existing.model_copy(update={
            "display_name": payload.display_name or existing.display_name,
            "family_group_id": payload.family_group_id or existing.family_group_id,
            "preferences": payload.preferences or existing.preferences,
            "updated_at": datetime.now(timezone.utc),
        })
        self._persist(updated)
        self._invalidate_cache(user_id)
        return updated

    def handle_relay_event(self, event_data: Dict[str, Any]) -> None:
        try:
            user_id = event_data.get("user_id")
            if not user_id:
                return
            updates = event_data.get("profile") or {}
            prefs = updates.get("preferences")
            payload = ProfileUpdate(
                display_name=updates.get("display_name"),
                family_group_id=updates.get("family_group_id"),
                preferences=ProfilePreferences(**prefs) if prefs else None,
            )
            self.update_profile(user_id, payload)
            log_state_event(user_id, "relay_applied")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to relay Dewey event: %s", exc)

    def _persist(self, profile: ProfileData) -> None:
        self._persist_local(profile)
        self._persist_remote(profile)
        with self._cache_lock:
            self._cache[profile.user_id] = profile

    def _persist_local(self, profile: ProfileData) -> None:
        store = self._read_local_store()
        store[profile.user_id] = profile.model_dump(mode="json")
        self._fallback_path.write_text(json.dumps(store, indent=2), encoding="utf-8")

    def _persist_remote(self, profile: ProfileData) -> None:
        try:
            payload = profile.model_dump(mode="json")
            self._supabase.table(self.TABLE_NAME).upsert(payload).execute()
        except Exception as exc:
            logger.warning("Supabase unavailable for Dewey upsert: %s", exc)
        else:
            log_state_event(profile.user_id, "profile_upserted")
            self._emit_profile_event(profile)

    def _fetch_remote_profile(self, user_id: str) -> Optional[ProfileData]:
        try:
            response = (
                self._supabase.table(self.TABLE_NAME)
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = getattr(response, "data", None)
            if rows:
                return ProfileData(**rows[0])
        except Exception as exc:
            logger.warning("Supabase fetch skipped for Dewey profile %s: %s", user_id, exc)
            return None
        return None

    def _fetch_local_profile(self, user_id: str) -> Optional[ProfileData]:
        store = self._read_local_store()
        record = store.get(user_id)
        if record:
            return ProfileData(**record)
        return None

    def _read_local_store(self) -> Dict[str, Dict[str, Any]]:
        if not self._fallback_path.exists():
            return {}
        try:
            return json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Corrupt Dewey fallback file; recreating.")
            return {}

    def _default_profile(self, user_id: str) -> ProfileData:
        return ProfileData(user_id=user_id, display_name=user_id.title())

    def _invalidate_cache(self, user_id: str) -> None:
        with self._cache_lock:
            if user_id in self._cache:
                del self._cache[user_id]

    def _emit_profile_event(self, profile: ProfileData) -> None:
        event: StateEvent = {
            "user_id": profile.user_id,
            "profile": profile.model_dump(mode="json"),
            "source": "dewey",
            "priority": "medium",
        }

        async def _push():
            await self._bus.publish(EventType.STATE_UPDATED.value, event)

        try:
            log_state_event(profile.user_id, "profile_event_emit")
            if not hasattr(self._bus, "publish"):
                return
            loop = asyncio.get_running_loop()
            loop.create_task(_push())
        except RuntimeError:
            asyncio.run(_push())
        except Exception as exc:
            logger.debug("Bus publish failed for Dewey profile update: %s", exc)


@lru_cache(maxsize=1)
def get_dewey_service() -> DeweyService:
    return DeweyService()


__all__ = [
    "DeweyService",
    "ProfileCreate",
    "ProfileData",
    "ProfilePreferences",
    "ProfileUpdate",
    "get_dewey_service",
]
