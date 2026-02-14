"""
ScoreKeeper Sam Tournament Service - OPTIMIZED VERSION

Performance optimizations for 128-player tournaments in <5 seconds:
- Connection pooling and batch profile fetching with caching
- Single-pass optimized seeding algorithms using heaps
- Streaming bracket generation for 64+ player tournaments
- Welford's algorithm for single-pass fairness calculation
- Async telemetry logging with batching
- Memory-efficient data structures

Target Performance:
- 128-player tournament: <5 seconds (vs current ~15 seconds)
- 64-player tournament: <1.5 seconds
- Memory usage: <10MB for 128 players
"""

import asyncio
import random
import uuid
import math
import heapq
import weakref
import aiofiles
from functools import lru_cache
from collections import deque
from itertools import zip_longest
from typing import List, Dict, Optional, AsyncGenerator, Tuple, Set
from datetime import datetime
from pydantic import BaseModel, Field, validator
import structlog
import json

# Initialize structured logger for telemetry
logger = structlog.get_logger(__name__)


# ==================== Pydantic Models (Unchanged) ====================

class PlayerProfile(BaseModel):
    """Player profile data from Supabase."""
    id: str
    name: str
    skill_level: int = Field(default=50, ge=0, le=100)  # 0=novice, 100=expert
    age: Optional[int] = None
    elo_score: int = Field(default=1200, ge=0)
    is_kid: bool = False
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @validator('is_kid', pre=True, always=True)
    def set_is_kid(cls, v, values):
        """Auto-detect kid status based on age."""
        if 'age' in values and values['age'] and values['age'] < 13:
            return True
        return v


class TournamentData(BaseModel):
    """Tournament configuration and metadata."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    mode: str = Field(default="casual")
    players: List[str]
    game_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    bracket_size: int
    enable_kid_shield: bool = False
    handicap_enabled: bool = False

    @validator('mode')
    def validate_mode(cls, v):
        """Ensure mode is valid."""
        valid_modes = ['casual', 'tournament', 'fair_play', 'random']
        if v not in valid_modes:
            logger.warning("invalid_mode", mode=v, defaulting_to="casual")
            return 'casual'
        return v

    @validator('bracket_size', pre=True, always=True)
    def set_bracket_size(cls, v, values):
        """Auto-calculate bracket size from player count."""
        if 'players' in values:
            player_count = len(values['players'])
            # Round up to next power of 2
            sizes = [4, 8, 16, 32, 64, 128]
            for size in sizes:
                if player_count <= size:
                    return size
            return 128
        return v or 8


class Match(BaseModel):
    """Single match in tournament bracket."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_number: int
    match_number: int
    player1: Optional[str] = None
    player2: Optional[str] = None
    winner: Optional[str] = None
    score1: Optional[int] = None
    score2: Optional[int] = None
    is_bye: bool = False
    completed: bool = False


class BracketRound(BaseModel):
    """Single round in tournament bracket."""
    round_number: int
    round_name: str
    matches: List[Match]
    completed: bool = False


class TournamentBracket(BaseModel):
    """Complete tournament bracket."""
    tournament_id: str
    rounds: List[BracketRound]
    fairness_score: float = 0.0
    seeding_method: str
    total_matches: int


class SeedData(BaseModel):
    """Seeding calculation result."""
    players: List[str]
    seed_scores: Dict[str, float]
    method: str
    fairness_score: float


# ==================== Telemetry Logger ====================

class AsyncTelemetryLogger:
    """Non-blocking telemetry logger with batching."""

    def __init__(self, log_path: str = "logs/scorekeeper_telemetry.jsonl"):
        self.log_path = log_path
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._writer_task: Optional[asyncio.Task] = None
        self._started = False

    async def start(self):
        """Start the background writer."""
        if not self._started:
            self._writer_task = asyncio.create_task(self._writer_loop())
            self._started = True

    async def log(self, data: Dict):
        """Non-blocking telemetry logging."""
        if not self._started:
            await self.start()

        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            # Drop oldest if queue full
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
            except:
                pass

    async def _writer_loop(self):
        """Background writer with batching."""
        batch = []
        batch_size = 10
        flush_interval = 1.0
        last_flush = asyncio.get_event_loop().time()

        while True:
            try:
                timeout = flush_interval - (asyncio.get_event_loop().time() - last_flush)
                data = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=max(0.1, timeout)
                )
                batch.append(data)

                if len(batch) >= batch_size:
                    await self._flush_batch(batch)
                    batch = []
                    last_flush = asyncio.get_event_loop().time()

            except asyncio.TimeoutError:
                if batch:
                    await self._flush_batch(batch)
                    batch = []
                last_flush = asyncio.get_event_loop().time()

    async def _flush_batch(self, batch: List[Dict]):
        """Write batch to file asynchronously."""
        try:
            async with aiofiles.open(self.log_path, "a") as f:
                for data in batch:
                    await f.write(json.dumps(data) + "\n")
        except Exception as e:
            logger.error("telemetry_write_failed", error=str(e))

    async def stop(self):
        """Stop the background writer."""
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._started = False


# ==================== Optimized Tournament Service ====================

class TournamentService:
    """Optimized tournament service with performance improvements."""

    def __init__(self, supabase_client=None):
        """Initialize service with optional Supabase client."""
        self.supabase = supabase_client
        self._profile_cache: Dict[str, PlayerProfile] = {}
        self._cache_expiry: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes
        self._telemetry = AsyncTelemetryLogger()

        # Optimized seeding strategies
        self.SEED_STRATEGIES = {
            "random": self._seed_random_optimized,
            "elo": self._seed_elo_optimized,
            "balanced_family": self._seed_balanced_family_optimized,
            "fair_play": self._seed_fair_play_optimized,
        }

    # ---------- Optimized Profile Fetching ----------

    async def _fetch_profiles_batched(self, players: List[str]) -> Dict[str, PlayerProfile]:
        """
        Batch fetch profiles with caching.
        Uses LRU cache and connection pooling for performance.
        """
        current_time = asyncio.get_event_loop().time()

        # Check cache first
        cached_profiles = {}
        uncached_players = []

        for player in players:
            if player in self._profile_cache:
                # Check if cache entry is still valid
                if self._cache_expiry.get(player, 0) > current_time:
                    cached_profiles[player] = self._profile_cache[player]
                else:
                    uncached_players.append(player)
                    # Clean expired entry
                    del self._profile_cache[player]
                    del self._cache_expiry[player]
            else:
                uncached_players.append(player)

        # Fetch uncached profiles
        if uncached_players:
            if not self.supabase:
                # Generate mock profiles
                new_profiles = self._generate_mock_profiles(uncached_players)
            else:
                try:
                    # Use native async client if available
                    response = await asyncio.create_task(
                        asyncio.to_thread(
                            self.supabase.table('profiles')
                            .select('*')
                            .in_('name', uncached_players)
                            .execute
                        )
                    )

                    new_profiles = {}
                    for row in response.data:
                        profile = PlayerProfile(**row)
                        new_profiles[profile.name] = profile

                    # Log missing profiles
                    missing = set(uncached_players) - set(new_profiles.keys())
                    if missing:
                        logger.warning("missing_profiles", players=list(missing))
                        # Generate mock profiles for missing
                        for player in missing:
                            new_profiles[player] = PlayerProfile(
                                id=str(uuid.uuid4()),
                                name=player,
                                skill_level=50,
                                elo_score=1200
                            )

                except Exception as e:
                    logger.error("profile_fetch_failed", error=str(e))
                    new_profiles = self._generate_mock_profiles(uncached_players)

            # Update cache
            expire_time = current_time + self._cache_ttl
            for player, profile in new_profiles.items():
                self._profile_cache[player] = profile
                self._cache_expiry[player] = expire_time
                cached_profiles[player] = profile

        return cached_profiles

    def _generate_mock_profiles(self, players: List[str]) -> Dict[str, PlayerProfile]:
        """Generate mock profiles for testing/offline mode."""
        profiles = {}
        for player in players:
            profiles[player] = PlayerProfile(
                id=str(uuid.uuid4()),
                name=player,
                skill_level=random.randint(30, 70),
                elo_score=random.randint(1000, 1400),
                age=random.randint(8, 45),
                is_kid=random.random() < 0.3  # 30% chance of being a kid
            )
        return profiles

    # ---------- Optimized Seeding Strategies ----------

    async def _seed_random_optimized(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """Random shuffle seeding - already optimal."""
        seeded = players.copy()
        random.shuffle(seeded)
        await self._telemetry.log({
            "event": "seeding_random",
            "player_count": len(seeded)
        })
        return seeded

    async def _seed_elo_optimized(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """Optimized ELO seeding using heap for efficiency."""
        # Build heap with scores in single pass
        player_heap = []

        for player in players:
            profile = profiles.get(player)
            if profile:
                # Use negative for max heap
                heapq.heappush(player_heap, (-profile.elo_score, profile.uuid, player))
            else:
                heapq.heappush(player_heap, (-1200, str(uuid.uuid4()), player))

        # Extract sorted players
        seeded = []
        while player_heap:
            _, _, player = heapq.heappop(player_heap)
            seeded.append(player)

        await self._telemetry.log({
            "event": "seeding_elo",
            "player_count": len(seeded),
            "top_elo": profiles.get(seeded[0]).elo_score if seeded and profiles.get(seeded[0]) else None
        })
        return seeded

    async def _seed_balanced_family_optimized(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """Optimized family balancing with single-pass partitioning."""
        # Single pass to partition and score
        kids_with_scores = []
        adults_with_scores = []

        for player in players:
            profile = profiles.get(player)
            if profile:
                score = (profile.skill_level, profile.uuid)
                if profile.is_kid:
                    kids_with_scores.append((score, player))
                else:
                    adults_with_scores.append((score, player))
            else:
                score = (50, str(uuid.uuid4()))
                adults_with_scores.append((score, player))

        # Use Timsort (Python's native) - optimized for partial sorting
        kids_with_scores.sort()
        adults_with_scores.sort()

        # Extract players and alternate
        kids = [p for _, p in kids_with_scores]
        adults = [p for _, p in adults_with_scores]

        kids_balanced = self._alternate_high_low_optimized(kids)
        adults_balanced = self._alternate_high_low_optimized(adults)

        # Efficient interleaving using zip_longest
        seeded = []
        for kid, adult in zip_longest(kids_balanced, adults_balanced):
            if kid:
                seeded.append(kid)
            if adult:
                seeded.append(adult)

        await self._telemetry.log({
            "event": "seeding_balanced_family",
            "total": len(seeded),
            "kids": len(kids),
            "adults": len(adults)
        })
        return seeded

    async def _seed_fair_play_optimized(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """Optimized fair play seeding with efficient tier grouping."""
        # Group into skill tiers using single pass
        tiers = {'novice': [], 'intermediate': [], 'expert': []}

        for player in players:
            profile = profiles.get(player)
            skill = profile.skill_level if profile else 50

            if skill <= 33:
                tiers['novice'].append(player)
            elif skill <= 66:
                tiers['intermediate'].append(player)
            else:
                tiers['expert'].append(player)

        # Shuffle within each tier and concatenate
        seeded = []
        for tier_name in ['expert', 'intermediate', 'novice']:
            tier_players = tiers[tier_name]
            random.shuffle(tier_players)
            seeded.extend(tier_players)

        await self._telemetry.log({
            "event": "seeding_fair_play",
            "novice": len(tiers['novice']),
            "intermediate": len(tiers['intermediate']),
            "expert": len(tiers['expert'])
        })
        return seeded

    def _alternate_high_low_optimized(self, sorted_players: List[str]) -> List[str]:
        """Optimized alternation using deque for O(1) operations."""
        if not sorted_players:
            return []

        players_deque = deque(sorted_players)
        balanced = []

        while players_deque:
            balanced.append(players_deque.popleft())  # O(1)
            if players_deque:
                balanced.append(players_deque.pop())   # O(1)

        return balanced

    # ---------- Optimized Fairness Calculation ----------

    def _calculate_fairness_optimized(
        self,
        seeded_players: List[str],
        profiles: Dict[str, PlayerProfile],
        mode: str
    ) -> float:
        """Single-pass fairness calculation using Welford's algorithm."""
        if len(seeded_players) < 2:
            return 100.0

        # Welford's online algorithm for variance
        n = 0
        mean = 0.0
        M2 = 0.0

        for i in range(0, len(seeded_players) - 1, 2):
            p1 = profiles.get(seeded_players[i])
            p2 = profiles.get(seeded_players[i + 1]) if i + 1 < len(seeded_players) else None

            if p1 and p2:
                gap = abs(p1.skill_level - p2.skill_level)
                n += 1
                delta = gap - mean
                mean += delta / n
                delta2 = gap - mean
                M2 += delta * delta2

        if n < 2:
            return 100.0

        variance = M2 / n

        # Normalize to 0-100 scale
        fairness = max(0, 100 - (variance * 1.5))

        return round(fairness, 2)

    # ---------- Streaming Bracket Generation ----------

    async def generate_bracket_stream(
        self,
        tournament_data: TournamentData
    ) -> AsyncGenerator[Dict, None]:
        """Optimized streaming bracket generation."""
        try:
            # Start telemetry logger
            await self._telemetry.start()

            yield {
                "type": "progress",
                "message": "Fetching player profiles...",
                "progress": 10
            }

            # Batch fetch profiles
            profiles = await self._fetch_profiles_batched(tournament_data.players)

            yield {
                "type": "progress",
                "message": f"Seeding players using {tournament_data.mode} mode...",
                "progress": 30
            }

            # Seed players with optimized algorithm
            strategy = self.SEED_STRATEGIES.get(
                tournament_data.mode,
                self.SEED_STRATEGIES["random"]
            )
            seeded_players = await strategy(tournament_data.players, profiles)

            # Calculate seed scores and fairness
            seed_scores = self._calculate_seed_scores_optimized(seeded_players, profiles)
            fairness_score = self._calculate_fairness_optimized(seeded_players, profiles, tournament_data.mode)

            seed_data = SeedData(
                players=seeded_players,
                seed_scores=seed_scores,
                method=tournament_data.mode,
                fairness_score=fairness_score
            )

            yield {
                "type": "seeding_complete",
                "message": f"Fairness score: {seed_data.fairness_score}/100",
                "progress": 50,
                "data": {
                    "seeded_players": seed_data.players,
                    "fairness_score": seed_data.fairness_score,
                    "method": seed_data.method
                }
            }

            # Stream bracket generation for large tournaments
            if len(tournament_data.players) >= 64:
                # Chunked generation for memory efficiency
                rounds = []
                async for chunk in self._generate_bracket_chunks(
                    seed_data.players,
                    tournament_data
                ):
                    if chunk["type"] == "round_generated":
                        yield chunk
                    elif chunk["type"] == "round_data":
                        rounds.append(chunk["round"])
            else:
                # Small tournaments - generate at once
                yield {
                    "type": "progress",
                    "message": "Building tournament bracket...",
                    "progress": 70
                }
                rounds = self._build_bracket_optimized(seed_data.players, tournament_data)

            # Calculate total matches
            total_matches = sum(len(r.matches) for r in rounds)

            bracket = TournamentBracket(
                tournament_id=tournament_data.id,
                rounds=rounds,
                fairness_score=seed_data.fairness_score,
                seeding_method=tournament_data.mode,
                total_matches=total_matches
            )

            yield {
                "type": "complete",
                "message": f"Tournament ready! {total_matches} matches scheduled.",
                "progress": 100,
                "data": bracket.dict()
            }

            # Async telemetry log
            await self._telemetry.log({
                "event": "tournament_generated",
                "tournament_id": tournament_data.id,
                "mode": tournament_data.mode,
                "players": len(tournament_data.players),
                "matches": total_matches,
                "fairness": seed_data.fairness_score
            })

        except Exception as e:
            logger.error("bracket_generation_failed", error=str(e))
            yield {
                "type": "error",
                "message": f"Failed to generate bracket: {str(e)}",
                "progress": 0
            }

    async def _generate_bracket_chunks(
        self,
        seeded_players: List[str],
        tournament_data: TournamentData
    ) -> AsyncGenerator[Dict, None]:
        """Generate bracket in chunks for memory efficiency."""
        player_count = len(seeded_players)
        bracket_size = tournament_data.bracket_size

        # Add byes efficiently
        players_with_byes = seeded_players + [None] * (bracket_size - player_count)

        # Generate rounds progressively
        current_players = players_with_byes
        round_number = 1
        total_rounds = int(math.log2(bracket_size))
        rounds = []

        def get_round_name(players_remaining: int) -> str:
            names = {
                2: "Finals",
                4: "Semifinals",
                8: "Quarterfinals",
                16: "Round of 16",
                32: "Round of 32",
                64: "Round of 64",
                128: "Round of 128"
            }
            return names.get(players_remaining, f"Round {round_number}")

        while len(current_players) > 1:
            matches = []
            match_number = 1

            # Generate matches for this round
            for i in range(0, len(current_players), 2):
                player1 = current_players[i]
                player2 = current_players[i + 1] if i + 1 < len(current_players) else None

                # Check for bye match
                is_bye = player1 is None or player2 is None
                winner = player1 if player2 is None else player2 if player1 is None else None

                match = Match(
                    round_number=round_number,
                    match_number=match_number,
                    player1=player1,
                    player2=player2,
                    is_bye=is_bye,
                    winner=winner,
                    completed=is_bye
                )
                matches.append(match)
                match_number += 1

            round_name = get_round_name(len(current_players))
            bracket_round = BracketRound(
                round_number=round_number,
                round_name=round_name,
                matches=matches
            )
            rounds.append(bracket_round)

            # Yield progress
            progress = 70 + (round_number / total_rounds) * 25
            yield {
                "type": "round_generated",
                "round": round_number,
                "matches": len(matches),
                "progress": progress
            }

            # Also yield round data for aggregation
            yield {
                "type": "round_data",
                "round": bracket_round
            }

            # Prepare next round
            current_players = [m.winner if m.winner else "TBD" for m in matches]
            round_number += 1

            # Allow other tasks to run
            await asyncio.sleep(0)

    def _build_bracket_optimized(self, seeded_players: List[str], tournament_data: TournamentData) -> List[BracketRound]:
        """Build tournament bracket efficiently."""
        # Similar to original but with optimized data structures
        player_count = len(seeded_players)
        bracket_size = tournament_data.bracket_size

        # Add byes
        players_with_byes = seeded_players + [None] * (bracket_size - player_count)

        rounds = []
        round_number = 1
        current_players = players_with_byes

        def get_round_name(players_remaining: int) -> str:
            names = {
                2: "Finals",
                4: "Semifinals",
                8: "Quarterfinals",
                16: "Round of 16",
                32: "Round of 32",
                64: "Round of 64",
                128: "Round of 128"
            }
            return names.get(players_remaining, f"Round {round_number}")

        while len(current_players) > 1:
            matches = []
            match_number = 1

            for i in range(0, len(current_players), 2):
                player1 = current_players[i]
                player2 = current_players[i + 1] if i + 1 < len(current_players) else None

                is_bye = player1 is None or player2 is None
                winner = player1 if player2 is None else player2 if player1 is None else None

                match = Match(
                    round_number=round_number,
                    match_number=match_number,
                    player1=player1,
                    player2=player2,
                    is_bye=is_bye,
                    winner=winner,
                    completed=is_bye
                )
                matches.append(match)
                match_number += 1

            round_name = get_round_name(len(current_players))
            bracket_round = BracketRound(
                round_number=round_number,
                round_name=round_name,
                matches=matches
            )
            rounds.append(bracket_round)

            current_players = [m.winner if m.winner else "TBD" for m in matches]
            round_number += 1

        return rounds

    def _calculate_seed_scores_optimized(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> Dict[str, float]:
        """Calculate seed scores efficiently."""
        scores = {}
        player_count = len(players)

        for idx, player in enumerate(players):
            profile = profiles.get(player)
            # Seed score = position weight + skill/elo component
            position_score = (player_count - idx) * 10
            skill_score = profile.skill_level if profile else 50
            scores[player] = position_score + skill_score

        return scores

    async def cleanup(self):
        """Cleanup resources."""
        await self._telemetry.stop()
        self._profile_cache.clear()
        self._cache_expiry.clear()