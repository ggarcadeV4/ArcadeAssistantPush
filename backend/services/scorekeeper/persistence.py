"""
ScoreKeeper Sam Persistence Layer

Handles Supabase CRUD operations for tournaments with:
- Upsert for tournament creation/updates
- Resume functionality for interrupted tournaments
- Concurrent submission locking
- Tournament state management
- Round completion telemetry
- Offline fallback to local JSON storage

Renamed from config.py per POR naming convention.
"""

import asyncio
from typing import Dict, Optional, List
from datetime import datetime
import structlog

from .models import TournamentData, TournamentBracket, Match, BracketRound, TournamentState

# Event bus for LED sync
from backend.services.bus_events import get_event_bus, EventType

# Initialize structured logger
logger = structlog.get_logger(__name__)


class PersistenceService:
    """Handles tournament persistence and state management via Supabase.

    Provides offline-first architecture with local fallback.
    """

    def __init__(self, supabase_client=None):
        """
        Initialize config handler with Supabase client.

        Args:
            supabase_client: Supabase client for async operations
        """
        self.supabase = supabase_client
        self._submission_locks: Dict[str, asyncio.Lock] = {}  # Tournament-level locks

    # ---------- CRUD Operations ----------

    async def upsert_tournament(self, tournament_data: TournamentData, bracket: TournamentBracket) -> Dict:
        """
        Create or update tournament in Supabase.

        Args:
            tournament_data: Tournament configuration
            bracket: Generated bracket

        Returns:
            Persisted tournament state
        """
        if not self.supabase:
            logger.warning("supabase_not_configured", operation="upsert", fallback="local")
            return self._mock_upsert(tournament_data, bracket)

        try:
            state = TournamentState(
                tournament_id=tournament_data.id,
                name=tournament_data.name,
                mode=tournament_data.mode,
                players=tournament_data.players,
                bracket_data=bracket.dict(),
                created_at=tournament_data.created_at,
                updated_at=datetime.utcnow(),
                fairness_score=bracket.fairness_score
            )

            # Upsert to Supabase (insert or update if exists)
            response = await asyncio.to_thread(
                self.supabase.table('tournaments')
                .upsert(state.dict(), on_conflict='tournament_id')
                .execute
            )

            logger.info("tournament_upserted",
                       tournament_id=tournament_data.id,
                       mode=tournament_data.mode,
                       players=len(tournament_data.players))

            return response.data[0] if response.data else state.dict()

        except Exception as e:
            logger.error("upsert_failed", error=str(e), tournament_id=tournament_data.id)
            raise

    async def resume_tournament(self, tournament_id: str) -> Optional[TournamentState]:
        """
        Resume an existing tournament by merging saved state.

        Args:
            tournament_id: Tournament ID to resume

        Returns:
            Tournament state or None if not found
        """
        if not self.supabase:
            logger.warning("supabase_not_configured", operation="resume", fallback="local")
            return None

        try:
            # Fetch tournament from Supabase
            response = await asyncio.to_thread(
                self.supabase.table('tournaments')
                .select('*')
                .eq('tournament_id', tournament_id)
                .eq('active', True)
                .execute
            )

            if not response.data:
                logger.warning("tournament_not_found", tournament_id=tournament_id)
                return None

            state_data = response.data[0]
            state = TournamentState(**state_data)

            logger.info("tournament_resumed",
                       tournament_id=tournament_id,
                       current_round=state.current_round,
                       completed_matches=len(state.completed_matches))

            return state

        except Exception as e:
            logger.error("resume_failed", error=str(e), tournament_id=tournament_id)
            return None

    async def submit_match(
        self,
        tournament_id: str,
        match_id: str,
        round_number: int,
        winner: str,
        score1: Optional[int] = None,
        score2: Optional[int] = None
    ) -> Dict:
        """
        Submit match result with concurrent submission locking.
        Ensures only one match update happens at a time per tournament.

        Args:
            tournament_id: Tournament ID
            match_id: Match ID
            round_number: Current round number
            winner: Winning player name
            score1: Optional score for player 1
            score2: Optional score for player 2

        Returns:
            Updated match data with telemetry
        """
        # Get or create lock for this tournament
        if tournament_id not in self._submission_locks:
            self._submission_locks[tournament_id] = asyncio.Lock()

        lock = self._submission_locks[tournament_id]

        async with lock:
            logger.info("match_submission_locked",
                       tournament_id=tournament_id,
                       match_id=match_id)

            if not self.supabase:
                return self._mock_submit(tournament_id, match_id, winner, score1, score2)

            try:
                # Fetch current tournament state
                state = await self.resume_tournament(tournament_id)
                if not state:
                    raise ValueError(f"Tournament {tournament_id} not found")

                # Update bracket data with match result
                bracket = TournamentBracket(**state.bracket_data)
                updated = False

                for bracket_round in bracket.rounds:
                    if bracket_round.round_number == round_number:
                        for match in bracket_round.matches:
                            if match.id == match_id:
                                # Update match
                                match.winner = winner
                                match.score1 = score1
                                match.score2 = score2
                                match.completed = True
                                updated = True

                                # Check if round is complete
                                round_complete = all(m.completed for m in bracket_round.matches)
                                if round_complete:
                                    bracket_round.completed = True
                                    # Telemetry log on round completion
                                    await self._log_round_completion(
                                        tournament_id=tournament_id,
                                        round_number=round_number,
                                        round_name=bracket_round.round_name,
                                        matches=bracket_round.matches
                                    )

                                break
                        if updated:
                            break

                if not updated:
                    raise ValueError(f"Match {match_id} not found in tournament {tournament_id}")

                # Update tournament state in Supabase
                state.bracket_data = bracket.dict()
                state.completed_matches.append(match_id)
                state.updated_at = datetime.utcnow()

                # Check if all rounds complete (tournament finished)
                if all(r.completed for r in bracket.rounds):
                    state.active = False
                    logger.info("tournament_completed",
                               tournament_id=tournament_id,
                               winner=winner)
                    
                    # Publish tournament completed event for LED sync
                    try:
                        bus = get_event_bus()
                        await bus.publish(EventType.TOURNAMENT_COMPLETED, {
                            "tournament_id": tournament_id,
                            "winner": winner,
                            "total_matches": len(state.completed_matches) + 1,
                            "mode": state.mode
                        })
                        logger.debug("tournament_completed_event_published", tournament_id=tournament_id)
                    except Exception as e:
                        logger.warning("tournament_event_publish_failed", error=str(e))

                # Persist update
                await asyncio.to_thread(
                    self.supabase.table('tournaments')
                    .update(state.dict())
                    .eq('tournament_id', tournament_id)
                    .execute
                )

                # Calculate round_complete safely with bounds checking
                round_complete = False
                if 0 < round_number <= len(bracket.rounds):
                    round_complete = bracket.rounds[round_number - 1].completed

                logger.info("match_submitted",
                           tournament_id=tournament_id,
                           match_id=match_id,
                           winner=winner,
                           round_complete=round_complete)

                return {
                    "match_id": match_id,
                    "winner": winner,
                    "score1": score1,
                    "score2": score2,
                    "completed": True,
                    "round_complete": round_complete,
                    "tournament_complete": not state.active
                }

            except Exception as e:
                logger.error("match_submission_failed",
                            error=str(e),
                            tournament_id=tournament_id,
                            match_id=match_id)
                raise

    async def _log_round_completion(
        self,
        tournament_id: str,
        round_number: int,
        round_name: str,
        matches: List[Match]
    ):
        """
        Log round completion to structlog telemetry (JSONL).

        Args:
            tournament_id: Tournament ID
            round_number: Completed round number
            round_name: Round name (e.g., "Semifinals")
            matches: List of matches in round
        """
        winners = [m.winner for m in matches if m.winner]
        match_count = len(matches)

        logger.info("round_completed",
                   tournament_id=tournament_id,
                   round_number=round_number,
                   round_name=round_name,
                   matches=match_count,
                   winners=winners,
                   timestamp=datetime.utcnow().isoformat())

        # Additional telemetry: log to file for persistent analytics
        telemetry_data = {
            "event": "round_completed",
            "tournament_id": tournament_id,
            "round_number": round_number,
            "round_name": round_name,
            "match_count": match_count,
            "winners": winners,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Write to JSONL telemetry file (append mode)
        try:
            import json
            import os
            # Ensure logs directory exists
            os.makedirs("logs", exist_ok=True)
            with open("logs/scorekeeper_telemetry.jsonl", "a") as f:
                f.write(json.dumps(telemetry_data) + "\n")
        except Exception as e:
            logger.warning("telemetry_file_write_failed", error=str(e))

    async def get_active_tournaments(self, limit: int = 10) -> List[TournamentState]:
        """
        Fetch active tournaments for resume/display.

        Args:
            limit: Max number of tournaments to return

        Returns:
            List of active tournament states
        """
        if not self.supabase:
            logger.warning("supabase_not_configured", operation="get_active", fallback="empty")
            return []

        try:
            response = await asyncio.to_thread(
                self.supabase.table('tournaments')
                .select('*')
                .eq('active', True)
                .order('updated_at', desc='true')
                .limit(limit)
                .execute
            )

            tournaments = [TournamentState(**data) for data in response.data]

            logger.info("active_tournaments_fetched", count=len(tournaments))
            return tournaments

        except Exception as e:
            logger.error("fetch_active_failed", error=str(e))
            return []

    async def archive_tournament(self, tournament_id: str) -> bool:
        """
        Archive completed tournament (set active=False).

        Args:
            tournament_id: Tournament ID to archive

        Returns:
            Success status
        """
        if not self.supabase:
            logger.warning("supabase_not_configured", operation="archive", fallback="noop")
            return False

        try:
            await asyncio.to_thread(
                self.supabase.table('tournaments')
                .update({'active': False, 'updated_at': datetime.utcnow().isoformat()})
                .eq('tournament_id', tournament_id)
                .execute
            )

            logger.info("tournament_archived", tournament_id=tournament_id)
            return True

        except Exception as e:
            logger.error("archive_failed", error=str(e), tournament_id=tournament_id)
            return False

    # ---------- Mock Operations (Offline Mode) ----------

    def _mock_upsert(self, tournament_data: TournamentData, bracket: TournamentBracket) -> Dict:
        """Mock upsert for offline development."""
        return {
            "tournament_id": tournament_data.id,
            "name": tournament_data.name,
            "mode": tournament_data.mode,
            "status": "mock_created"
        }

    def _mock_submit(
        self,
        tournament_id: str,
        match_id: str,
        winner: str,
        score1: Optional[int],
        score2: Optional[int]
    ) -> Dict:
        """Mock submission for offline development."""
        logger.info("mock_match_submission",
                   tournament_id=tournament_id,
                   match_id=match_id,
                   winner=winner)

        return {
            "match_id": match_id,
            "winner": winner,
            "score1": score1,
            "score2": score2,
            "completed": True,
            "mock": True
        }

    # ---------- Health Check ----------

    async def health_check(self) -> Dict:
        """
        Check Supabase connection health.

        Returns:
            Health status dict
        """
        if not self.supabase:
            return {
                "status": "offline",
                "message": "Supabase not configured"
            }

        try:
            # Simple query to test connection
            response = await asyncio.to_thread(
                self.supabase.table('tournaments')
                .select('tournament_id')
                .limit(1)
                .execute
            )

            return {
                "status": "online",
                "message": "Supabase connected",
                "tournaments_available": len(response.data) > 0
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Supabase error: {str(e)}"
            }


# Backward compatibility alias
TournamentConfig = PersistenceService
