"""
Realtime invalidation for SecureAIClient panel_config cache.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from backend.services.drive_a_ai_client import SecureAIClient

try:
    from realtime.types import (
        RealtimePostgresChangesListenEvent,
        RealtimeSubscribeStates,
    )
    from supabase import create_async_client
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    RealtimePostgresChangesListenEvent = None
    RealtimeSubscribeStates = None
    create_async_client = None


logger = logging.getLogger(__name__)


class PanelConfigSync:
    def __init__(self, client: SecureAIClient):
        self.client = client
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if create_async_client is None or RealtimePostgresChangesListenEvent is None:
            logger.warning("Supabase Realtime is unavailable; panel_config sync disabled")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_thread,
            name="panel-config-sync",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_forever())
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("panel_config sync terminated unexpectedly")

    async def _run_forever(self) -> None:
        if not self.client.supabase_url or not self.client.supabase_client_key:
            logger.warning("Supabase credentials unavailable; panel_config sync disabled")
            return

        backoff = 1
        while not self._stop_event.is_set():
            try:
                await self._subscribe_once()
                backoff = 1
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.exception(
                    "panel_config Realtime connection dropped; retrying in %ss",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _subscribe_once(self) -> None:
        async_client = await create_async_client(
            self.client.supabase_url,
            self.client.supabase_client_key,
        )
        disconnect_event = asyncio.Event()

        def on_change(payload: Any) -> None:
            data = getattr(payload, "data", payload) or {}
            record = data.get("record") or data.get("new") or {}
            old_record = data.get("old_record") or data.get("old") or {}
            row = record or old_record
            panel = row.get("panel")
            if not panel:
                return
            cabinet_id = row.get("cabinet_id")
            self.client.invalidate_cache(panel, cabinet_id)

        def on_subscribe(status: Any, error: Optional[Exception]) -> None:
            if status in {
                RealtimeSubscribeStates.CHANNEL_ERROR,
                RealtimeSubscribeStates.CLOSED,
                RealtimeSubscribeStates.TIMED_OUT,
            }:
                if error:
                    logger.warning("panel_config Realtime status=%s error=%s", status, error)
                else:
                    logger.warning("panel_config Realtime status=%s", status)
                disconnect_event.set()

        channel = async_client.channel("panel-config-sync")
        channel.on_postgres_changes(
            RealtimePostgresChangesListenEvent.All,
            on_change,
            table="panel_config",
            schema="public",
        )
        await channel.subscribe(on_subscribe)

        try:
            while not self._stop_event.is_set() and not disconnect_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            try:
                await channel.unsubscribe()
            except Exception:
                logger.debug("panel_config channel unsubscribe failed", exc_info=True)
            try:
                await async_client.remove_channel(channel)
            except Exception:
                logger.debug("panel_config channel removal failed", exc_info=True)

        if disconnect_event.is_set():
            raise ConnectionError("panel_config Realtime channel disconnected")
