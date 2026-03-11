from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ScoreStrategyName = Literal["mame_hiscore", "mame_lua", "file_parser", "vision", "manual_only", "none"]
ScoreAttemptStatus = Literal["captured_auto", "captured_manual", "pending_review", "unsupported", "failed"]


logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CanonicalGameEvent(BaseModel):
    session_id: Optional[str] = None
    source: str = "arcade_assistant"
    game_id: Optional[str] = None
    title: str
    platform: str = "Unknown"
    emulator: Optional[str] = None
    pid: Optional[int] = None
    launch_method: str = "unknown"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    player: Optional[str] = None
    rom_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoreStrategy(BaseModel):
    primary: ScoreStrategyName
    fallback: Optional[ScoreStrategyName] = None
    resolution_source: str = "default"
    notes: Optional[str] = None


class ScoreAttempt(BaseModel):
    attempt_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    game_id: Optional[str] = None
    game_title: str
    platform: str
    player: Optional[str] = None
    strategy: ScoreStrategyName
    fallback_strategy: Optional[ScoreStrategyName] = None
    status: ScoreAttemptStatus
    raw_score: Optional[int] = None
    final_score: Optional[int] = None
    confidence: float = 0.0
    evidence_path: Optional[str] = None
    source: str = "score_tracking"
    captured_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoreReviewDecision(BaseModel):
    action: Literal["approve", "edit", "reject", "mark_unsupported"]
    score: Optional[int] = None
    player: Optional[str] = None
    note: Optional[str] = None


DEFAULT_STRATEGIES: List[tuple[tuple[str, ...], ScoreStrategyName, Optional[ScoreStrategyName]]] = [
    (("mame", "arcade"), "mame_hiscore", "mame_lua"),
    (("pinball",), "manual_only", None),
    (("daphne", "laserdisc", "hypseus"), "vision", "manual_only"),
    (("teknoparrot",), "vision", "manual_only"),
    (("wii u", "cemu"), "vision", "manual_only"),
    (("steam", "windows", "pc"), "vision", "manual_only"),
]


class ScoreTrackingService:
    def __init__(self, drive_root: Path):
        self.drive_root = Path(drive_root)
        self.state_dir = self.drive_root / ".aa" / "state" / "scorekeeper"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_file = self.state_dir / "score_attempts.jsonl"
        self.sessions_file = self.state_dir / "active_score_sessions.json"
        self.strategy_overrides_file = self.drive_root / "configs" / "score_strategy_overrides.json"
        self._cleanup_stale_sessions()

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, lambda handle: json.dump(payload, handle, indent=2))

    def _atomic_write(self, path: Path, write_callback) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as handle:
                write_callback(handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _read_attempts(self) -> List[ScoreAttempt]:
        if not self.attempts_file.exists():
            return []
        attempts: List[ScoreAttempt] = []
        with open(self.attempts_file, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    attempts.append(ScoreAttempt.model_validate_json(raw))
                except Exception:
                    continue
        return attempts

    def _write_attempts(self, attempts: List[ScoreAttempt]) -> None:
        self.attempts_file.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            self.attempts_file,
            lambda handle: [handle.write(attempt.model_dump_json() + "\n") for attempt in attempts],
        )

    def _load_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        raw = self._read_json(self.sessions_file, {})
        return raw if isinstance(raw, dict) else {}

    def _save_active_sessions(self, sessions: Dict[str, Dict[str, Any]]) -> None:
        self._write_json(self.sessions_file, sessions)

    def _parse_session_time(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _cleanup_stale_sessions(self, max_age_hours: int = 24) -> None:
        sessions = self._load_active_sessions()
        if not sessions:
            return

        now = datetime.now(timezone.utc)
        stale_ids: List[str] = []
        for session_id, session in sessions.items():
            started_at = self._parse_session_time(session.get("started_at"))
            if (now - started_at).total_seconds() > max_age_hours * 3600:
                stale_ids.append(session_id)

        for session_id in stale_ids:
            session = self.close_session(session_id=session_id)
            if session:
                self.record_failure(
                    session,
                    strategy_name="none",
                    reason="stale_session_cleanup",
                    details=f"Session was {max_age_hours}+ hours old at startup",
                )

        if stale_ids:
            logger.info("Cleaned %s stale sessions on startup", len(stale_ids))

    def _load_strategy_overrides(self) -> Dict[str, Any]:
        raw = self._read_json(self.strategy_overrides_file, {})
        return raw if isinstance(raw, dict) else {}

    def resolve_strategy(
        self,
        *,
        game_id: Optional[str],
        title: str,
        platform: str,
        emulator: Optional[str] = None,
    ) -> ScoreStrategy:
        overrides = self._load_strategy_overrides()
        normalized_game_id = (game_id or "").strip().lower()
        normalized_title = (title or "").strip().lower()
        normalized_platform = (platform or "").strip().lower()
        normalized_emulator = (emulator or "").strip().lower()

        for entry in overrides.get("games", []):
            if not isinstance(entry, dict):
                continue
            keys = {
                str(entry.get("game_id", "")).strip().lower(),
                str(entry.get("title", "")).strip().lower(),
            }
            if (normalized_game_id and normalized_game_id in keys) or (normalized_title and normalized_title in keys):
                primary = entry.get("primary") or "manual_only"
                fallback = entry.get("fallback")
                return ScoreStrategy(
                    primary=primary,
                    fallback=fallback,
                    resolution_source="game_override",
                    notes=entry.get("notes"),
                )

        for entry in overrides.get("platforms", []):
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("platform", "")).strip().lower()
            if key and key in normalized_platform:
                primary = entry.get("primary") or "manual_only"
                fallback = entry.get("fallback")
                return ScoreStrategy(
                    primary=primary,
                    fallback=fallback,
                    resolution_source="platform_override",
                    notes=entry.get("notes"),
                )

        combined = " ".join(part for part in [normalized_platform, normalized_emulator] if part).strip()
        for keywords, primary, fallback in DEFAULT_STRATEGIES:
            if any(keyword in combined for keyword in keywords):
                return ScoreStrategy(primary=primary, fallback=fallback, resolution_source="default")

        return ScoreStrategy(
            primary="vision",
            fallback="manual_only",
            resolution_source="default",
            notes="Default long-tail strategy",
        )

    def record_launch(self, event: CanonicalGameEvent) -> Dict[str, Any]:
        sessions = self._load_active_sessions()
        strategy = self.resolve_strategy(
            game_id=event.game_id,
            title=event.title,
            platform=event.platform,
            emulator=event.emulator,
        )

        matched_session_id = None
        if event.session_id and event.session_id in sessions:
            matched_session_id = event.session_id
        else:
            for existing_session_id, existing in reversed(list(sessions.items())):
                if event.pid and existing.get("pid") == event.pid:
                    matched_session_id = existing_session_id
                    break
                if event.game_id and existing.get("game_id") == event.game_id:
                    matched_session_id = existing_session_id
                    break
                if event.rom_name and existing.get("rom_name") == event.rom_name and existing.get("platform") == event.platform:
                    matched_session_id = existing_session_id
                    break
                if event.title and existing.get("title") == event.title and existing.get("platform") == event.platform:
                    matched_session_id = existing_session_id
                    break

        if matched_session_id:
            session = dict(sessions[matched_session_id])
            session["source"] = event.source or session.get("source")
            session["game_id"] = event.game_id or session.get("game_id")
            session["title"] = event.title or session.get("title") or "Unknown"
            session["platform"] = event.platform or session.get("platform") or "Unknown"
            session["emulator"] = event.emulator or session.get("emulator")
            session["pid"] = event.pid or session.get("pid")
            session["launch_method"] = event.launch_method or session.get("launch_method") or "unknown"
            session["ended_at"] = event.ended_at or session.get("ended_at")
            session["player"] = event.player or session.get("player")
            session["rom_name"] = event.rom_name or session.get("rom_name")
            session["started_at"] = session.get("started_at") or event.started_at or _utc_now()
            session["strategy"] = strategy.model_dump()
            session["metadata"] = {
                **(session.get("metadata") or {}),
                **(event.metadata or {}),
            }
            sessions[matched_session_id] = session
            self._save_active_sessions(sessions)
            return session

        session_id = event.session_id or str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "source": event.source,
            "game_id": event.game_id,
            "title": event.title,
            "platform": event.platform,
            "emulator": event.emulator,
            "pid": event.pid,
            "launch_method": event.launch_method,
            "started_at": event.started_at or _utc_now(),
            "ended_at": event.ended_at,
            "player": event.player,
            "rom_name": event.rom_name,
            "strategy": strategy.model_dump(),
            "metadata": event.metadata or {},
        }
        sessions[session_id] = session
        self._save_active_sessions(sessions)
        return session

    def resolve_session(
        self,
        *,
        session_id: Optional[str] = None,
        game_id: Optional[str] = None,
        title: Optional[str] = None,
        pid: Optional[int] = None,
        rom_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sessions = self._load_active_sessions()
        if session_id and session_id in sessions:
            return sessions[session_id]

        candidates = list(sessions.values())
        for session in reversed(candidates):
            if pid and session.get("pid") == pid:
                return session
            if game_id and session.get("game_id") == game_id:
                return session
            if rom_name and session.get("rom_name") == rom_name:
                return session
            if title and session.get("title") == title:
                return session
        return None

    def close_session(
        self,
        *,
        session_id: Optional[str] = None,
        game_id: Optional[str] = None,
        title: Optional[str] = None,
        pid: Optional[int] = None,
        rom_name: Optional[str] = None,
        ended_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sessions = self._load_active_sessions()
        session = None
        if session_id and session_id in sessions:
            session = dict(sessions[session_id])
        else:
            for existing in reversed(list(sessions.values())):
                if pid and existing.get("pid") == pid:
                    session = dict(existing)
                    break
                if game_id and existing.get("game_id") == game_id:
                    session = dict(existing)
                    break
                if rom_name and existing.get("rom_name") == rom_name:
                    session = dict(existing)
                    break
                if title and existing.get("title") == title:
                    session = dict(existing)
                    break

        if not session:
            logger.info("Session already closed or not found: %s", session_id or game_id or pid or rom_name or title)
            return None

        session["ended_at"] = ended_at or _utc_now()
        sessions.pop(session["session_id"], None)
        self._save_active_sessions(sessions)
        return session

    def _upsert_attempt(self, attempt: ScoreAttempt) -> ScoreAttempt:
        attempts = self._read_attempts()
        replaced = False
        for index, existing in enumerate(attempts):
            if existing.attempt_id == attempt.attempt_id:
                attempts[index] = attempt
                replaced = True
                break
        if not replaced:
            attempts.append(attempt)
        self._write_attempts(attempts)
        return attempt

    def get_attempt(self, attempt_id: str) -> Optional[ScoreAttempt]:
        for attempt in reversed(self._read_attempts()):
            if attempt.attempt_id == attempt_id:
                return attempt
        return None

    def get_latest_attempt_for_session(self, session_id: str) -> Optional[ScoreAttempt]:
        for attempt in reversed(self._read_attempts()):
            if attempt.session_id == session_id:
                return attempt
        return None

    def begin_attempt(self, session: Dict[str, Any]) -> ScoreAttempt:
        existing = self.get_latest_attempt_for_session(session["session_id"])
        if existing:
            return existing
        strategy = ScoreStrategy.model_validate(session.get("strategy") or {})
        attempt = ScoreAttempt(
            session_id=session["session_id"],
            game_id=session.get("game_id"),
            game_title=session.get("title") or "Unknown",
            platform=session.get("platform") or "Unknown",
            player=session.get("player"),
            strategy=strategy.primary,
            fallback_strategy=strategy.fallback,
            status="pending_review" if strategy.primary == "manual_only" else "failed",
            source=session.get("source") or "score_tracking",
            metadata={
                "launch_method": session.get("launch_method"),
                "emulator": session.get("emulator"),
                "rom_name": session.get("rom_name"),
                "reason": "manual_only_strategy" if strategy.primary == "manual_only" else "capture_pending",
            },
        )
        return self._upsert_attempt(attempt)

    def record_auto_capture(
        self,
        session: Dict[str, Any],
        *,
        strategy_name: ScoreStrategyName,
        score: int,
        confidence: float,
        evidence_path: Optional[str] = None,
        player: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScoreAttempt:
        attempt = self.get_latest_attempt_for_session(session["session_id"]) or self.begin_attempt(session)
        attempt.strategy = strategy_name
        attempt.status = "captured_auto"
        attempt.raw_score = int(score)
        attempt.final_score = int(score)
        attempt.confidence = float(confidence)
        attempt.evidence_path = evidence_path
        attempt.player = player or attempt.player
        attempt.updated_at = _utc_now()
        attempt.metadata.update(metadata or {})
        return self._upsert_attempt(attempt)

    def record_manual_submission(
        self,
        *,
        game_id: Optional[str],
        game_title: str,
        platform: Optional[str],
        player: Optional[str],
        score: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScoreAttempt:
        attempt = None
        for existing in reversed(self._read_attempts()):
            if game_id and existing.game_id == game_id and existing.status in {"pending_review", "failed"}:
                attempt = existing
                break
            if existing.game_title == game_title and existing.status in {"pending_review", "failed"}:
                attempt = existing
                break
        if attempt is None:
            attempt = ScoreAttempt(
                session_id=str(uuid.uuid4()),
                game_id=game_id,
                game_title=game_title,
                platform=platform or "Unknown",
                player=player,
                strategy="manual_only",
                fallback_strategy=None,
                status="captured_manual",
                source="scorekeeper_submit",
            )
        attempt.status = "captured_manual"
        attempt.final_score = int(score)
        attempt.raw_score = int(score)
        attempt.confidence = 1.0
        attempt.player = player or attempt.player
        attempt.updated_at = _utc_now()
        attempt.metadata.update(metadata or {})
        return self._upsert_attempt(attempt)

    def record_pending_review(
        self,
        session: Dict[str, Any],
        *,
        strategy_name: ScoreStrategyName,
        confidence: float = 0.0,
        raw_score: Optional[int] = None,
        evidence_path: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScoreAttempt:
        attempt = self.get_latest_attempt_for_session(session["session_id"]) or self.begin_attempt(session)
        attempt.strategy = strategy_name
        attempt.status = "pending_review"
        attempt.raw_score = raw_score
        attempt.confidence = float(confidence)
        attempt.evidence_path = evidence_path
        attempt.updated_at = _utc_now()
        if reason:
            attempt.metadata["reason"] = reason
        attempt.metadata.update(metadata or {})
        return self._upsert_attempt(attempt)

    def record_failure(
        self,
        session: Dict[str, Any],
        *,
        strategy_name: ScoreStrategyName,
        reason: str,
        details: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScoreAttempt:
        attempt = self.get_latest_attempt_for_session(session["session_id"]) or self.begin_attempt(session)
        attempt.strategy = strategy_name
        attempt.status = "failed"
        attempt.updated_at = _utc_now()
        attempt.metadata["reason"] = reason
        if details:
            attempt.metadata["details"] = details
        attempt.metadata.update(metadata or {})
        return self._upsert_attempt(attempt)

    def record_unsupported(
        self,
        session: Dict[str, Any],
        *,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScoreAttempt:
        attempt = self.get_latest_attempt_for_session(session["session_id"]) or self.begin_attempt(session)
        attempt.status = "unsupported"
        attempt.updated_at = _utc_now()
        attempt.metadata["reason"] = reason
        attempt.metadata.update(metadata or {})
        return self._upsert_attempt(attempt)

    def list_review_queue(self, limit: int = 25) -> List[Dict[str, Any]]:
        items = [
            attempt.model_dump()
            for attempt in reversed(self._read_attempts())
            if attempt.status in {"pending_review", "failed"}
        ]
        return items[:limit]

    def review_attempt(self, attempt_id: str, decision: ScoreReviewDecision) -> Optional[ScoreAttempt]:
        attempt = self.get_attempt(attempt_id)
        if not attempt:
            return None
        if decision.action == "approve":
            attempt.status = "captured_manual"
            if attempt.raw_score is not None:
                attempt.final_score = attempt.raw_score
            if decision.player:
                attempt.player = decision.player
        elif decision.action == "edit":
            attempt.status = "captured_manual"
            if decision.score is not None:
                attempt.final_score = int(decision.score)
                attempt.raw_score = int(decision.score)
            if decision.player:
                attempt.player = decision.player
        elif decision.action == "mark_unsupported":
            attempt.status = "unsupported"
        else:
            attempt.status = "failed"
        attempt.updated_at = _utc_now()
        if decision.note:
            attempt.metadata["review_note"] = decision.note
        return self._upsert_attempt(attempt)

    def coverage_summary(self) -> Dict[str, Any]:
        attempts = self._read_attempts()
        active_sessions = self._load_active_sessions()
        counts = {
            "captured_auto": 0,
            "captured_manual": 0,
            "pending_review": 0,
            "unsupported": 0,
            "failed": 0,
        }
        auto_games = set()
        unsupported_games = set()
        platform_breakdown: Dict[str, Dict[str, int]] = {}

        for attempt in attempts:
            counts[attempt.status] = counts.get(attempt.status, 0) + 1
            game_key = attempt.game_id or attempt.game_title
            if attempt.status == "captured_auto":
                auto_games.add(game_key)
            elif attempt.status == "unsupported":
                unsupported_games.add(game_key)
            platform_entry = platform_breakdown.setdefault(
                attempt.platform or "Unknown",
                {"captured_auto": 0, "captured_manual": 0, "pending_review": 0, "unsupported": 0, "failed": 0},
            )
            platform_entry[attempt.status] = platform_entry.get(attempt.status, 0) + 1

        return {
            "attempt_count": len(attempts),
            "active_sessions": len(active_sessions),
            "tracked_automatically": len(auto_games),
            "captured_manual": counts["captured_manual"],
            "pending_review": counts["pending_review"] + counts["failed"],
            "unsupported": len(unsupported_games),
            "status_counts": counts,
            "platform_breakdown": platform_breakdown,
        }


_services: Dict[str, ScoreTrackingService] = {}


def get_score_tracking_service(drive_root: Path) -> ScoreTrackingService:
    root = str(Path(drive_root))
    if root not in _services:
        _services[root] = ScoreTrackingService(Path(drive_root))
    return _services[root]



