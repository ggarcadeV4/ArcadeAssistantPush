"""Controller mapping persistence for Panel 5: Controller Chuck."""

from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import HTTPException

from .bus_events import get_event_bus
from .supabase_client import SupabaseError, get_client
from backend.constants.drive_root import get_drive_root

logger = logging.getLogger(__name__)
ControllerMap = Dict[str, int]
FallbackStore = Dict[str, ControllerMap]


class ControllerMappingService:
    """Manage controller maps across Supabase and local fallback storage."""

    TABLE_NAME = "controller_maps"
    SIMPLE_MODE_DEFAULT = {"p1.button1": 1, "p1.button2": 2, "p1.button3": 3, "p1.button4": 4}
    DEFAULT_MAP = {
        "p1.button1": 8, "p1.button2": 5, "p1.button3": 6, "p1.button4": 7,
        "p1.button5": 14, "p1.button6": 15, "p1.up": 10, "p1.down": 11,
        "p1.left": 12, "p1.right": 13,
    }

    def __init__(self) -> None:
        self._fallback_lock = Lock()
        self._bus = get_event_bus()
        # Golden Drive: store under .aa/state/controller_maps (not hardcoded A:/)
        drive_root = get_drive_root(allow_cwd_fallback=True)
        self.FALLBACK_PATH = drive_root / ".aa" / "state" / "controller_maps" / "fallback.json"
        self.FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)

    def save_map(self, user_id: str, session_id: str, mapping: ControllerMap) -> ControllerMap:
        """Persist a controller map for the given user/session pair."""
        self._validate_map(mapping)
        record = {"user_id": user_id, "session_id": session_id, "map": mapping}
        synced = self._upsert_supabase(record)
        payload = self._fallback_payload()
        payload[self._map_key(user_id, session_id)] = mapping
        self._fallback_payload(payload)
        self._invalidate_cache()
        self._emit_saved(user_id, session_id, mapping, synced)
        return mapping

    def load_map(
        self, user_id: str, session_id: str, tendencies: Optional[Dict[str, Any]] = None
    ) -> ControllerMap:
        """Convenience wrapper that derives defaults based on tendencies."""
        simple_mode = bool((tendencies or {}).get("simple_mode"))
        return self.get_map(user_id, session_id, simple_mode)

    @lru_cache(maxsize=50)
    def get_map(self, user_id: str, session_id: str, simple_mode: bool = False) -> ControllerMap:
        """Return the mapping for a user/session, cached for fast repeated lookups."""
        mapping = self._select_supabase_map(user_id, session_id)
        if not mapping:
            fallback = self._fallback_payload().get(self._map_key(user_id, session_id))
            mapping = dict(fallback) if isinstance(fallback, dict) else None
        if not mapping:
            mapping = self.SIMPLE_MODE_DEFAULT if simple_mode else self.DEFAULT_MAP
        return dict(mapping)

    def delete_map(self, user_id: str, session_id: str) -> None:
        """Remove the stored mapping for the provided identifiers."""
        self._delete_supabase_record(user_id, session_id)
        payload = self._fallback_payload()
        if payload.pop(self._map_key(user_id, session_id), None) is not None:
            self._fallback_payload(payload)
        self._invalidate_cache()

    def _validate_map(self, mapping: ControllerMap) -> None:
        if not isinstance(mapping, dict) or not mapping:
            raise HTTPException(status_code=400, detail="Mapping payload must be non-empty.")

        for key, value in mapping.items():
            if not isinstance(key, str):
                raise HTTPException(status_code=400, detail="Mapping keys must be strings.")
            if not isinstance(value, int):
                raise HTTPException(status_code=400, detail=f"Mapping for '{key}' must be int.")

    def _fallback_payload(self, new_payload: Optional[FallbackStore] = None) -> FallbackStore:
        with self._fallback_lock:
            if new_payload is not None:
                serialized = json.dumps(new_payload, indent=2)
                self.FALLBACK_PATH.write_text(serialized, encoding="utf-8")
                return new_payload
            if not self.FALLBACK_PATH.exists():
                return {}
            try:
                data = json.loads(self.FALLBACK_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read fallback mapping cache: %s", exc)
                return {}
        return data if isinstance(data, dict) else {}

    def _upsert_supabase(self, record: Dict[str, Any]) -> bool:
        try:
            table = get_client().table(self.TABLE_NAME)
        except (SupabaseError, Exception) as exc:
            logger.debug("Supabase unavailable, using fallback only: %s", exc)
            return False

        try:
            table.upsert(record, on_conflict="user_id,session_id").execute()
            return True
        except Exception as exc:
            logger.warning("Supabase upsert failed: %s", exc)
            return False

    def _select_supabase_map(self, user_id: str, session_id: str) -> Optional[ControllerMap]:
        try:
            table = get_client().table(self.TABLE_NAME)
        except (SupabaseError, Exception):
            return None

        try:
            filters = {"user_id": user_id, "session_id": session_id}
            response = table.select("map").match(filters).limit(1).execute()
        except Exception as exc:
            logger.warning("Supabase fetch failed: %s", exc)
            return None

        rows = getattr(response, "data", None) or getattr(response, "get", lambda *_: None)("data")
        if rows:
            mapping = rows[0].get("map")
            if isinstance(mapping, dict):
                return {key: int(value) for key, value in mapping.items()}
        return None

    def _delete_supabase_record(self, user_id: str, session_id: str) -> None:
        try:
            table = get_client().table(self.TABLE_NAME)
            filters = {"user_id": user_id, "session_id": session_id}
            table.delete().match(filters).execute()
        except (SupabaseError, Exception) as exc:
            logger.debug("Supabase delete skipped: %s", exc)

    def _invalidate_cache(self) -> None:
        try:
            self.get_map.cache_clear()
        except AttributeError:
            pass

    def _map_key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    def _emit_saved(self, user_id: str, session_id: str, mapping: ControllerMap, synced: bool):
        async def _publish() -> None:
            await self._bus.publish(
                "map_saved",
                dict(user_id=user_id, session_id=session_id, synced=synced, map_size=len(mapping)),
            )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_publish())
        except RuntimeError:
            asyncio.run(_publish())


controller_mapping = ControllerMappingService()
