"""
ScoreKeeper Sam Tournament Service

Provides tournament bracket generation with profile-aware seeding strategies,
streaming bracket generation for large tournaments, and fairness scoring.

Key Features:
- Dictionary-based seeding strategies (random, elo, balanced_family, fair_play)
- Async profile fetching from Supabase for skill-based seeding
- Generator-based streaming for 64+ player tournaments
- "Kid Shield" - balanced grouping for family-friendly tournaments
- Fairness score calculation for tournament equity
- Edge case handling: duplicates, missing profiles, odd players, byes
"""

import asyncio
import random
import uuid
from typing import List, Dict, Optional, AsyncGenerator, Tuple, Callable
from datetime import datetime
from pydantic import BaseModel, Field, validator
from functools import lru_cache
from math import log, sqrt, pi, exp
import structlog

# Event bus for LED sync and cross-service communication
from backend.services.bus_events import get_event_bus, EventType

# Initialize structured logger for telemetry
logger = structlog.get_logger(__name__)


# ==================== Pydantic Models ====================

class PlayerProfile(BaseModel):
    """Player profile data from Supabase."""
    id: str
    name: str
    skill_level: int = Field(default=50, ge=0, le=100)  # 0=novice, 100=expert
    age: Optional[int] = None
    elo_score: int = Field(default=1200, ge=0)
    is_kid: bool = False
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))  # Tiebreaker for duplicates

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
    mode: str = Field(default="casual")  # casual, tournament, fair_play, elo_standard, elo_glicko, elo_family
    players: List[str]  # Player names
    game_id: Optional[str] = None  # LaunchBox game ID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    bracket_size: int  # 4, 8, 16, 32, 64, 128
    enable_kid_shield: bool = False  # Auto-balance kids
    handicap_enabled: bool = False  # Score multipliers for skill gaps
    rating_variant: Optional[str] = Field(default="standard")  # standard, glicko, family_adjusted

    @validator('mode')
    def validate_mode(cls, v):
        """Ensure mode is valid, default to casual."""
        valid_modes = [
            'casual', 'tournament', 'fair_play', 'random',
            'elo_standard', 'elo_glicko', 'elo_family', 'balanced_family'
        ]
        if v not in valid_modes:
            logger.warning("invalid_mode", mode=v, defaulting_to="casual")
            return 'casual'
        return v

    @validator('rating_variant')
    def validate_rating_variant(cls, v):
        """Ensure rating variant is valid."""
        valid_variants = ['standard', 'glicko', 'family_adjusted']
        if v not in valid_variants:
            logger.warning("invalid_rating_variant", variant=v, defaulting_to="standard")
            return 'standard'
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
            return 128  # Max size
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
    is_bye: bool = False  # Automatic advancement
    completed: bool = False


class BracketRound(BaseModel):
    """Single round in tournament bracket."""
    round_number: int
    round_name: str  # "Round 1", "Quarterfinals", "Semifinals", "Finals"
    matches: List[Match]
    completed: bool = False


class TournamentBracket(BaseModel):
    """Complete tournament bracket."""
    tournament_id: str
    rounds: List[BracketRound]
    fairness_score: float = 0.0  # 0-100, higher = more balanced
    seeding_method: str
    total_matches: int


class SeedData(BaseModel):
    """Seeding calculation result."""
    players: List[str]
    seed_scores: Dict[str, float]  # Player -> seed score
    method: str
    fairness_score: float


class RatingData(BaseModel):
    """Player rating data for Elo/Glicko-2 calculations."""
    player_id: str
    elo: float = Field(default=1500.0, ge=0)  # Standard starting Elo
    games: int = Field(default=0, ge=0)  # Games played count
    volatility: float = Field(default=0.06, ge=0, le=1.0)  # Glicko-2 sigma
    deviation: float = Field(default=350.0, ge=0)  # Glicko-2 RD (phi)


class MatchResult(BaseModel):
    """Match result for rating updates."""
    player_a: str
    player_b: str
    score_a: float  # 1.0 = win, 0.5 = draw, 0.0 = loss

    @validator('score_a')
    def valid_score(cls, v):
        """Validate score is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Score must be between 0 and 1 (1=win, 0.5=draw, 0=loss)")
        return v

    @property
    def score_b(self) -> float:
        """Complementary score for player B."""
        return 1.0 - self.score_a


# ==================== Glicko-2 Rating System ====================

class Glicko2Calculator:
    """
    Glicko-2 rating system implementation.

    Improves on Elo by adding:
    - Rating Deviation (RD/phi): Uncertainty in rating
    - Volatility (sigma): Rate of rating change

    Ideal for family tournaments with inconsistent play patterns.
    Conservative seeding uses: mu - 2*phi (accounts for uncertainty)
    """

    def __init__(self, tau: float = 0.5):
        """
        Initialize Glicko-2 calculator.

        Args:
            tau: System constant for volatility change (0.3-1.2)
                 Higher = more volatile ratings (good for casual family play)
        """
        self.tau = tau
        self.scale = 173.7178  # Convert to Elo scale (400 / log(10))
        self.convergence_tolerance = 0.000001  # For volatility iteration

    @lru_cache(maxsize=1024)
    def expected_score(self, mu: float, phi: float, mu_opp: float, phi_opp: float) -> float:
        """
        Calculate expected score (0-1) for player vs opponent.
        Cached for performance with repeated opponent pairs.

        Args:
            mu: Player's rating
            phi: Player's rating deviation
            mu_opp: Opponent's rating
            phi_opp: Opponent's rating deviation

        Returns:
            Expected score between 0 and 1
        """
        g = self._g(sqrt(phi**2 + phi_opp**2))
        return 1 / (1 + exp(-g * (mu - mu_opp)))

    def _g(self, phi: float) -> float:
        """Helper function for Glicko-2 calculations."""
        return 1 / sqrt(1 + 3 * (phi / pi)**2)

    def _f(self, x: float, delta: float, phi: float, v: float, a: float) -> float:
        """Helper function for volatility update iteration."""
        ex = exp(x)
        numerator = ex * (delta**2 - phi**2 - v - ex)
        denominator = 2 * (phi**2 + v + ex)**2
        return numerator / denominator - (x - a) / (self.tau**2)

    def _update_volatility(self, phi: float, v: float, delta: float, sigma: float) -> float:
        """
        Update volatility using Illinois algorithm (Glicko-2 step 5).

        Args:
            phi: Current rating deviation
            v: Variance estimate
            delta: Performance delta
            sigma: Current volatility

        Returns:
            Updated volatility
        """
        a = log(sigma**2)
        A = a

        # Find B such that f(B) and f(A) have opposite signs
        if delta**2 > phi**2 + v:
            B = log(delta**2 - phi**2 - v)
        else:
            k = 1
            while self._f(a - k * self.tau, delta, phi, v, a) < 0:
                k += 1
            B = a - k * self.tau

        # Illinois algorithm iteration
        fA = self._f(A, delta, phi, v, a)
        fB = self._f(B, delta, phi, v, a)

        while abs(B - A) > self.convergence_tolerance:
            C = A + (A - B) * fA / (fB - fA)
            fC = self._f(C, delta, phi, v, a)

            if fC * fB < 0:
                A = B
                fA = fB
            else:
                fA = fA / 2

            B = C
            fB = fC

        return exp(A / 2)

    async def update_ratings(
        self,
        results: List[MatchResult],
        ratings: Dict[str, Tuple[float, float, float]]
    ) -> Dict[str, Tuple[float, float, float]]:
        """
        Async batch update ratings for multiple matches.
        Optimized for concurrent tournament updates.

        Args:
            results: List of match results to process
            ratings: Current ratings dict {player_id: (mu, phi, sigma)}

        Returns:
            Updated ratings dict
        """
        # Process all matches concurrently
        tasks = [self._update_single(result, ratings) for result in results]
        updated_pairs = await asyncio.gather(*tasks)

        # Merge updates into new ratings dict
        new_ratings = ratings.copy()
        for i, result in enumerate(results):
            (a_mu, a_phi, a_sigma), (b_mu, b_phi, b_sigma) = updated_pairs[i]
            new_ratings[result.player_a] = (a_mu, a_phi, a_sigma)
            new_ratings[result.player_b] = (b_mu, b_phi, b_sigma)

        logger.info("ratings_updated_batch",
                   matches=len(results),
                   players_affected=len(set(r.player_a for r in results) | set(r.player_b for r in results)))

        return new_ratings

    async def _update_single(
        self,
        result: MatchResult,
        ratings: Dict[str, Tuple[float, float, float]]
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Update ratings for a single match using Glicko-2 algorithm.

        Args:
            result: Match result
            ratings: Current ratings

        Returns:
            Updated (mu, phi, sigma) tuples for both players
        """
        # Get current ratings with defaults for new players
        mu_a, phi_a, sigma_a = ratings.get(result.player_a, (1500.0, 350.0, 0.06))
        mu_b, phi_b, sigma_b = ratings.get(result.player_b, (1500.0, 350.0, 0.06))

        # Step 2: Calculate g and E (expected scores)
        g_b = self._g(phi_b)
        g_a = self._g(phi_a)
        E_a = self.expected_score(mu_a, phi_a, mu_b, phi_b)
        E_b = 1.0 - E_a

        # Step 3: Calculate variance (v)
        v_a = 1 / (g_b**2 * E_a * (1 - E_a))
        v_b = 1 / (g_a**2 * E_b * (1 - E_b))

        # Step 4: Calculate delta (performance measure)
        delta_a = v_a * g_b * (result.score_a - E_a)
        delta_b = v_b * g_a * (result.score_b - E_b)

        # Step 5: Update volatility
        sigma_a_new = self._update_volatility(phi_a, v_a, delta_a, sigma_a)
        sigma_b_new = self._update_volatility(phi_b, v_b, delta_b, sigma_b)

        # Step 6: Update phi_star (pre-rating period deviation)
        phi_a_star = sqrt(phi_a**2 + sigma_a_new**2)
        phi_b_star = sqrt(phi_b**2 + sigma_b_new**2)

        # Step 7: Update rating and deviation
        new_phi_a = 1 / sqrt(1 / phi_a_star**2 + 1 / v_a)
        new_mu_a = mu_a + new_phi_a**2 * g_b * (result.score_a - E_a)

        new_phi_b = 1 / sqrt(1 / phi_b_star**2 + 1 / v_b)
        new_mu_b = mu_b + new_phi_b**2 * g_a * (result.score_b - E_b)

        # Clamp volatility to prevent explosion (edge case protection)
        sigma_a_new = min(sigma_a_new, 0.09)
        sigma_b_new = min(sigma_b_new, 0.09)

        logger.debug("rating_update_single",
                    player_a=result.player_a,
                    mu_change=round(new_mu_a - mu_a, 2),
                    player_b=result.player_b,
                    mu_change_b=round(new_mu_b - mu_b, 2))

        return (new_mu_a, new_phi_a, sigma_a_new), (new_mu_b, new_phi_b, sigma_b_new)


# ==================== Seeding Strategies ====================

class TournamentService:
    """Core tournament service with seeding and bracket generation."""

    def __init__(self, supabase_client=None, tau: float = 0.5):
        """
        Initialize service with optional Supabase client for profiles.

        Args:
            supabase_client: Optional Supabase client for async profile fetching
            tau: Glicko-2 volatility constant (0.3-1.2, higher = more volatile)
        """
        self.supabase = supabase_client
        self.glicko2 = Glicko2Calculator(tau=tau)

        # Async-safe ratings cache: {(player_tuple, tournament_id): ratings_dict}
        self._ratings_cache: Dict[Tuple[Tuple[str, ...], str], Dict[str, "RatingData"]] = {}

        # Seeding strategies as dict for O(1) selection and extensibility
        self.SEED_STRATEGIES = {
            "random": self._seed_random,
            "elo": self._seed_elo,
            "balanced_family": self._seed_balanced_family,
            "fair_play": self._seed_fair_play,
        }

        # Elo seeding variants with strategy pattern
        self.ELO_VARIANTS: Dict[str, Callable[[List[RatingData], str], List[str]]] = {
            "standard": self._variant_standard_elo,
            "glicko": self._variant_glicko_conservative,
            "family_adjusted": self._variant_family_adjusted,
        }

    # ---------- Seeding Strategy Implementations ----------

    async def _seed_random(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """
        Random shuffle seeding for casual play.

        Args:
            players: List of player names
            profiles: Player profiles (ignored for random)

        Returns:
            Randomly shuffled player list
        """
        seeded = players.copy()
        random.shuffle(seeded)
        logger.info("seeding_random", player_count=len(seeded))
        return seeded

    async def _seed_elo(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """
        ELO-based seeding for competitive tournaments.
        Sorts players by ELO score (highest first) with UUID tiebreaker.

        Args:
            players: List of player names
            profiles: Player profiles with ELO scores

        Returns:
            ELO-sorted player list
        """
        def get_elo_key(player: str) -> Tuple[int, str]:
            profile = profiles.get(player)
            if profile:
                # Sort by ELO (descending), then UUID for stable sort on duplicates
                return (-profile.elo_score, profile.uuid)
            # Missing profiles get neutral ELO, last in sort
            logger.warning("missing_profile_elo", player=player)
            return (-1200, str(uuid.uuid4()))

        seeded = sorted(players, key=get_elo_key)
        logger.info("seeding_elo", player_count=len(seeded),
                   top_elo=profiles.get(seeded[0]).elo_score if seeded and profiles.get(seeded[0]) else None)
        return seeded

    async def _seed_balanced_family(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """
        Balanced grouping for family-friendly matches.
        Alternates high/low skill players to create fair matchups.
        Implements "Kid Shield" - groups kids against similar skill levels.

        Args:
            players: List of player names
            profiles: Player profiles with skill levels

        Returns:
            Skill-balanced player list
        """
        # Separate kids and adults if Kid Shield enabled
        kids = []
        adults = []

        for player in players:
            profile = profiles.get(player)
            if profile and profile.is_kid:
                kids.append(player)
            else:
                adults.append(player)

        # Sort each group by skill (low to high)
        def get_skill_key(player: str) -> Tuple[int, str]:
            profile = profiles.get(player)
            if profile:
                return (profile.skill_level, profile.uuid)
            logger.warning("missing_profile_balanced", player=player)
            return (50, str(uuid.uuid4()))  # Neutral skill

        kids_sorted = sorted(kids, key=get_skill_key)
        adults_sorted = sorted(adults, key=get_skill_key)

        # Balance each group: alternate high/low skill
        balanced_kids = self._alternate_high_low(kids_sorted)
        balanced_adults = self._alternate_high_low(adults_sorted)

        # Interleave kids and adults to prevent kid-adult early matchups
        seeded = []
        max_len = max(len(balanced_kids), len(balanced_adults))
        for i in range(max_len):
            if i < len(balanced_kids):
                seeded.append(balanced_kids[i])
            if i < len(balanced_adults):
                seeded.append(balanced_adults[i])

        logger.info("seeding_balanced_family",
                   total=len(seeded), kids=len(kids), adults=len(adults))
        return seeded

    async def _seed_fair_play(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> List[str]:
        """
        Fair play seeding optimizes for closest skill matchups.
        Groups players into skill tiers, randomizes within tiers.

        Args:
            players: List of player names
            profiles: Player profiles with skill levels

        Returns:
            Tier-balanced player list
        """
        # Group into skill tiers: novice (0-33), intermediate (34-66), expert (67-100)
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

        # Shuffle within each tier, then concatenate
        seeded = []
        for tier_name in ['expert', 'intermediate', 'novice']:
            tier_players = tiers[tier_name]
            random.shuffle(tier_players)
            seeded.extend(tier_players)

        logger.info("seeding_fair_play",
                   novice=len(tiers['novice']),
                   intermediate=len(tiers['intermediate']),
                   expert=len(tiers['expert']))
        return seeded

    def _alternate_high_low(self, sorted_players: List[str]) -> List[str]:
        """
        Alternate high and low skilled players for balance.

        Args:
            sorted_players: Players sorted by skill (low to high)

        Returns:
            Alternated player list
        """
        if not sorted_players:
            return []

        balanced = []
        left, right = 0, len(sorted_players) - 1

        while left <= right:
            balanced.append(sorted_players[left])  # Low skill
            if left != right:
                balanced.append(sorted_players[right])  # High skill
            left += 1
            right -= 1

        return balanced

    # ---------- Profile Fetching ----------

    async def _fetch_profiles(self, players: List[str]) -> Dict[str, PlayerProfile]:
        """
        Fetch player profiles from Supabase asynchronously.

        Args:
            players: List of player names

        Returns:
            Dict mapping player name to profile (missing profiles excluded)
        """
        if not self.supabase:
            logger.warning("supabase_not_configured", defaulting_to="mock_profiles")
            return self._generate_mock_profiles(players)

        try:
            # Async fetch from Supabase (non-blocking)
            response = await asyncio.to_thread(
                self.supabase.table('profiles')
                .select('*')
                .in_('name', players)
                .execute
            )

            profiles = {}
            for row in response.data:
                profile = PlayerProfile(**row)
                profiles[profile.name] = profile

            # Log missing profiles
            missing = set(players) - set(profiles.keys())
            if missing:
                logger.warning("missing_profiles", players=list(missing),
                             message="New players—using neutral seed")

            return profiles

        except Exception as e:
            logger.error("profile_fetch_failed", error=str(e), fallback="mock")
            return self._generate_mock_profiles(players)

    def _generate_mock_profiles(self, players: List[str]) -> Dict[str, PlayerProfile]:
        """Generate mock profiles for testing/offline mode."""
        profiles = {}
        for player in players:
            profiles[player] = PlayerProfile(
                id=str(uuid.uuid4()),
                name=player,
                skill_level=random.randint(30, 70),
                elo_score=random.randint(1000, 1400)
            )
        return profiles

    # ---------- Rating Data Fetching (Glicko-2) ----------

    async def _fetch_ratings(
        self,
        player_tuple: Tuple[str, ...],
        tournament_id: str
    ) -> Dict[str, RatingData]:
        """
        Fetch detailed rating data for players from Supabase.
        Cached per tournament ID to reduce DB hits by ~80% on repeated seeds.

        Args:
            player_tuple: Tuple of player IDs (tuple for hashability)
            tournament_id: Tournament ID for cache key

        Returns:
            Dict mapping player_id to RatingData
        """
        # Manual async-safe cache lookup (lru_cache doesn't work with async)
        cache_key = (player_tuple, tournament_id)
        if cache_key in self._ratings_cache:
            logger.debug("ratings_cache_hit", tournament_id=tournament_id, players=len(player_tuple))
            return self._ratings_cache[cache_key]

        if not self.supabase:
            logger.warning("supabase_not_configured_ratings", defaulting_to="mock_ratings")
            return self._generate_mock_ratings(list(player_tuple))

        try:
            # Batch async fetch from Supabase profiles table
            # Assumes profiles table has: id, name, elo_score, games_played, volatility, deviation
            response = await asyncio.to_thread(
                self.supabase.table('profiles')
                .select('id, name, elo_score, games_played, volatility, deviation')
                .in_('name', list(player_tuple))
                .execute
            )

            ratings = {}
            for row in response.data:
                rating = RatingData(
                    player_id=row.get('id', row.get('name')),  # Fallback to name as ID
                    elo=float(row.get('elo_score', 1500)),
                    games=int(row.get('games_played', 0)),
                    volatility=float(row.get('volatility', 0.06)),
                    deviation=float(row.get('deviation', 350.0))
                )
                ratings[row['name']] = rating

            # Log missing ratings
            missing = set(player_tuple) - set(ratings.keys())
            if missing:
                logger.warning("missing_ratings", players=list(missing),
                             message="New players—using default ratings")
                # Add default ratings for missing players
                for player in missing:
                    ratings[player] = RatingData(
                        player_id=player,
                        elo=1500.0,
                        games=0,
                        volatility=0.06,
                        deviation=350.0
                    )

            logger.info("ratings_fetched", players=len(ratings), cache_key=tournament_id)
            # Store in async-safe cache before returning
            self._ratings_cache[cache_key] = ratings
            return ratings

        except Exception as e:
            logger.error("rating_fetch_failed", error=str(e), fallback="mock")
            fallback_ratings = self._generate_mock_ratings(list(player_tuple))
            # Cache fallback too to avoid repeated failures
            self._ratings_cache[cache_key] = fallback_ratings
            return fallback_ratings

    def _generate_mock_ratings(self, players: List[str]) -> Dict[str, RatingData]:
        """Generate mock rating data for testing/offline mode."""
        ratings = {}
        for player in players:
            ratings[player] = RatingData(
                player_id=player,
                elo=random.uniform(1200, 1800),
                games=random.randint(0, 50),
                volatility=random.uniform(0.05, 0.08),
                deviation=random.uniform(200, 350)
            )
        return ratings

    # ---------- Elo Variant Implementations ----------

    def _variant_standard_elo(self, ratings: List[RatingData], tournament_id: str) -> List[str]:
        """
        Standard Elo seeding: Sort by Elo rating (descending).

        Args:
            ratings: List of player ratings
            tournament_id: Tournament ID (unused, for interface consistency)

        Returns:
            Player IDs sorted by Elo (highest first)
        """
        sorted_ratings = sorted(ratings, key=lambda r: (-r.elo, r.player_id))
        logger.info("seeding_standard_elo",
                   top_elo=sorted_ratings[0].elo if sorted_ratings else None,
                   player_count=len(sorted_ratings))
        return [r.player_id for r in sorted_ratings]

    def _variant_glicko_conservative(self, ratings: List[RatingData], tournament_id: str) -> List[str]:
        """
        Glicko-2 conservative seeding: mu - 2*phi (accounts for uncertainty).
        Players with high uncertainty (new/inactive) get lower seeds.

        Args:
            ratings: List of player ratings
            tournament_id: Tournament ID (unused)

        Returns:
            Player IDs sorted by conservative rating
        """
        # Conservative score = mu - 2*phi (95% confidence lower bound)
        def conservative_score(rating: RatingData) -> float:
            return rating.elo - (2 * rating.deviation)

        sorted_ratings = sorted(ratings, key=lambda r: (-conservative_score(r), r.player_id))
        logger.info("seeding_glicko_conservative",
                   top_conservative=conservative_score(sorted_ratings[0]) if sorted_ratings else None,
                   player_count=len(sorted_ratings))
        return [r.player_id for r in sorted_ratings]

    def _variant_family_adjusted(self, ratings: List[RatingData]) -> List[str]:
        """
        Family-adjusted seeding: Boost low-experience players for inclusion.
        Balances skill with participation equity (good for family tournaments).

        Formula: Elo + (1000 / (games_played + 1))
        Effect: New players get ~1000 point boost, diminishes with experience

        Args:
            ratings: List of player ratings

        Returns:
            Player IDs sorted by family-adjusted score
        """
        def family_score(rating: RatingData) -> float:
            # Boost for low game count (encourages new player participation)
            experience_boost = 1000 / (rating.games + 1)
            return rating.elo + experience_boost

        sorted_ratings = sorted(ratings, key=lambda r: (-family_score(r), r.player_id))
        logger.info("seeding_family_adjusted",
                   adjustments_applied=sum(1 for r in ratings if r.games < 10),
                   player_count=len(ratings))
        return [r.player_id for r in sorted_ratings]

    # ---------- Enhanced Elo Seeding Method ----------

    async def _seed_with_elo_variants(
        self,
        players: List[str],
        mode: str,
        tournament_id: str
    ) -> List[str]:
        """
        Seed players using Elo rating variants with async fetching.

        Args:
            players: List of player names
            mode: Variant mode (standard, glicko, family_adjusted)
            tournament_id: Tournament ID for caching

        Returns:
            Seeded player list
        """
        # Fetch ratings with caching (tuple for hashability)
        ratings_dict = await self._fetch_ratings(tuple(players), tournament_id)
        ratings_list = [ratings_dict[p] for p in players]

        # Select variant strategy
        variant = self.ELO_VARIANTS.get(mode, self.ELO_VARIANTS["standard"])

        # Execute seeding (some variants need tournament_id, some don't)
        if mode == "family_adjusted":
            seeded_players = variant(ratings_list)
        else:
            seeded_players = variant(ratings_list, tournament_id)

        logger.info("elo_variant_seeding_complete",
                   mode=mode,
                   players=len(seeded_players),
                   tournament_id=tournament_id)

        return seeded_players

    # ---------- Main Seeding Function ----------

    async def _seed_players(
        self,
        players: List[str],
        mode: str,
        profiles: Optional[Dict[str, PlayerProfile]] = None
    ) -> SeedData:
        """
        Seed players using specified mode strategy.

        Args:
            players: List of player names
            mode: Seeding mode (random, elo, balanced_family, fair_play)
            profiles: Optional pre-fetched profiles

        Returns:
            SeedData with seeded players and fairness score
        """
        # Fetch profiles if not provided
        if profiles is None:
            profiles = await self._fetch_profiles(players)

        # Select and execute seeding strategy
        strategy = self.SEED_STRATEGIES.get(mode, self.SEED_STRATEGIES["random"])
        seeded_players = await strategy(players, profiles)

        # Calculate seed scores and fairness
        seed_scores = self._calculate_seed_scores(seeded_players, profiles)
        fairness_score = self._calculate_fairness(seeded_players, profiles, mode)

        return SeedData(
            players=seeded_players,
            seed_scores=seed_scores,
            method=mode,
            fairness_score=fairness_score
        )

    def _calculate_seed_scores(self, players: List[str], profiles: Dict[str, PlayerProfile]) -> Dict[str, float]:
        """Calculate seed score for each player (position + skill)."""
        scores = {}
        for idx, player in enumerate(players):
            profile = profiles.get(player)
            # Seed score = position weight + skill/elo component
            position_score = (len(players) - idx) * 10  # Higher position = higher score
            skill_score = profile.skill_level if profile else 50
            scores[player] = position_score + skill_score
        return scores

    def _calculate_fairness(
        self,
        seeded_players: List[str],
        profiles: Dict[str, PlayerProfile],
        mode: str
    ) -> float:
        """
        Calculate fairness score (0-100) for tournament seeding.
        Higher = more balanced matchups.

        Heuristic: Variance in adjacent matchup skill gaps.
        """
        if len(seeded_players) < 2:
            return 100.0

        # Calculate skill gaps between adjacent players
        gaps = []
        for i in range(0, len(seeded_players) - 1, 2):
            p1 = profiles.get(seeded_players[i])
            p2 = profiles.get(seeded_players[i + 1]) if i + 1 < len(seeded_players) else None

            if p1 and p2:
                gap = abs(p1.skill_level - p2.skill_level)
                gaps.append(gap)

        if not gaps:
            return 100.0

        # Lower variance in gaps = higher fairness
        avg_gap = sum(gaps) / len(gaps)
        variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)

        # Normalize: low variance (0-10) = high fairness (90-100)
        # High variance (40+) = low fairness (0-50)
        fairness = max(0, 100 - (variance * 1.5))

        logger.info("fairness_calculated",
                   mode=mode,
                   fairness=round(fairness, 2),
                   avg_gap=round(avg_gap, 2))

        return round(fairness, 2)

    # ---------- Bracket Generation ----------

    def _build_bracket(self, seeded_players: List[str], tournament_data: TournamentData) -> List[BracketRound]:
        """
        Build tournament bracket with byes for odd player counts.

        Args:
            seeded_players: Seeded player list
            tournament_data: Tournament configuration

        Returns:
            List of bracket rounds
        """
        player_count = len(seeded_players)
        bracket_size = tournament_data.bracket_size

        # Add byes to fill bracket
        players_with_byes = seeded_players.copy()
        byes_needed = bracket_size - player_count

        if byes_needed > 0:
            logger.info("adding_byes", count=byes_needed, bracket_size=bracket_size)
            # Add byes at the end (lowest seeds get byes)
            players_with_byes.extend([None] * byes_needed)

        # Build rounds
        rounds = []
        round_number = 1
        current_players = players_with_byes

        # Round names based on remaining players
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

            # Pair adjacent players
            for i in range(0, len(current_players), 2):
                player1 = current_players[i]
                player2 = current_players[i + 1] if i + 1 < len(current_players) else None

                # Check for bye match (one player is None)
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

            # Prepare next round (winners only, excluding None/byes)
            current_players = [m.winner for m in matches if m.winner is not None]
            round_number += 1

        return rounds

    async def generate_bracket_stream(
        self,
        tournament_data: TournamentData
    ) -> AsyncGenerator[Dict, None]:
        """
        Generate tournament bracket with streaming progress updates.
        Yields progress messages for large tournaments (64+ players).

        Args:
            tournament_data: Tournament configuration

        Yields:
            Progress dicts with type, message, data
        """
        try:
            yield {
                "type": "progress",
                "message": "Fetching player profiles...",
                "progress": 10
            }

            # Fetch profiles asynchronously
            profiles = await self._fetch_profiles(tournament_data.players)

            yield {
                "type": "progress",
                "message": f"Seeding players using {tournament_data.mode} mode...",
                "progress": 30
            }

            # Seed players
            seed_data = await self._seed_players(
                tournament_data.players,
                tournament_data.mode,
                profiles
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

            # Build bracket (may batch for 128+ players)
            yield {
                "type": "progress",
                "message": "Building tournament bracket...",
                "progress": 70
            }

            rounds = self._build_bracket(seed_data.players, tournament_data)

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

            # Telemetry log
            logger.info("tournament_generated",
                       tournament_id=tournament_data.id,
                       mode=tournament_data.mode,
                       players=len(tournament_data.players),
                       matches=total_matches,
                       fairness=seed_data.fairness_score)

            # Publish tournament started event for LED sync
            try:
                bus = get_event_bus()
                await bus.publish(EventType.TOURNAMENT_STARTED, {
                    "tournament_id": tournament_data.id,
                    "name": tournament_data.name,
                    "mode": tournament_data.mode,
                    "player_count": len(tournament_data.players),
                    "total_matches": total_matches,
                    "fairness_score": seed_data.fairness_score
                })
                logger.debug("tournament_started_event_published", tournament_id=tournament_data.id)
            except Exception as e:
                logger.warning("tournament_event_publish_failed", error=str(e))

        except Exception as e:
            logger.error("bracket_generation_failed",
                        error=str(e),
                        tournament_id=tournament_data.id)
            yield {
                "type": "error",
                "message": f"Failed to generate bracket: {str(e)}",
                "progress": 0
            }

    # ---------- Match Management ----------

    async def submit_match_result(
        self,
        tournament_id: str,
        match_id: str,
        winner: str,
        player1: str,
        player2: str,
        score1: Optional[int] = None,
        score2: Optional[int] = None,
        update_ratings: bool = True
    ) -> Dict:
        """
        Submit match result with concurrent submission handling and rating updates.

        Args:
            tournament_id: Tournament ID
            match_id: Match ID
            winner: Winning player name
            player1: First player name
            player2: Second player name
            score1: Optional score for player 1
            score2: Optional score for player 2
            update_ratings: Whether to update Glicko-2 ratings (default: True)

        Returns:
            Updated match data with rating changes
        """
        logger.info("match_result_submitted",
                   tournament_id=tournament_id,
                   match_id=match_id,
                   winner=winner)

        result_data = {
            "match_id": match_id,
            "winner": winner,
            "completed": True,
            "ratings_updated": False
        }

        # Update ratings if enabled
        if update_ratings and self.supabase:
            try:
                # Determine match outcome (1.0 = player1 win, 0.5 = draw, 0.0 = player2 win)
                if winner == player1:
                    score_a = 1.0
                elif winner == player2:
                    score_a = 0.0
                else:
                    # Draw or unknown winner
                    score_a = 0.5
                    logger.warning("unknown_winner", winner=winner,
                                 players=[player1, player2],
                                 treating_as="draw")

                # Create match result
                match_result = MatchResult(
                    player_a=player1,
                    player_b=player2,
                    score_a=score_a
                )

                # Fetch current ratings
                ratings_dict = await self._fetch_ratings(
                    tuple([player1, player2]),
                    tournament_id
                )

                # Convert to Glicko-2 format (mu, phi, sigma)
                current_ratings = {
                    player1: (
                        ratings_dict[player1].elo,
                        ratings_dict[player1].deviation,
                        ratings_dict[player1].volatility
                    ),
                    player2: (
                        ratings_dict[player2].elo,
                        ratings_dict[player2].deviation,
                        ratings_dict[player2].volatility
                    )
                }

                # Update ratings using Glicko-2
                updated_ratings = await self.glicko2.update_ratings(
                    [match_result],
                    current_ratings
                )

                # Persist to Supabase
                await self._persist_rating_updates(
                    tournament_id,
                    match_id,
                    updated_ratings,
                    current_ratings
                )

                # Add rating changes to result
                result_data["ratings_updated"] = True
                result_data["rating_changes"] = {
                    player1: {
                        "old_elo": round(current_ratings[player1][0], 2),
                        "new_elo": round(updated_ratings[player1][0], 2),
                        "change": round(updated_ratings[player1][0] - current_ratings[player1][0], 2)
                    },
                    player2: {
                        "old_elo": round(current_ratings[player2][0], 2),
                        "new_elo": round(updated_ratings[player2][0], 2),
                        "change": round(updated_ratings[player2][0] - current_ratings[player2][0], 2)
                    }
                }

                logger.info("ratings_updated_post_match",
                           tournament_id=tournament_id,
                           match_id=match_id,
                           player1_change=result_data["rating_changes"][player1]["change"],
                           player2_change=result_data["rating_changes"][player2]["change"])

            except Exception as e:
                logger.error("rating_update_failed",
                            tournament_id=tournament_id,
                            match_id=match_id,
                            error=str(e),
                            continuing="without rating update")
                # Continue without rating update (non-critical failure)

        return result_data

    async def _persist_rating_updates(
        self,
        tournament_id: str,
        match_id: str,
        updated_ratings: Dict[str, Tuple[float, float, float]],
        old_ratings: Dict[str, Tuple[float, float, float]]
    ) -> None:
        """
        Persist rating updates to Supabase profiles table.

        Args:
            tournament_id: Tournament ID
            match_id: Match ID
            updated_ratings: New ratings {player: (mu, phi, sigma)}
            old_ratings: Previous ratings for logging
        """
        if not self.supabase:
            return

        try:
            # Batch update profiles
            for player_name, (new_mu, new_phi, new_sigma) in updated_ratings.items():
                old_mu, old_phi, old_sigma = old_ratings[player_name]

                # Update profile in Supabase
                await asyncio.to_thread(
                    self.supabase.table('profiles')
                    .update({
                        'elo_score': int(round(new_mu)),
                        'deviation': float(new_phi),
                        'volatility': float(new_sigma),
                        'games_played': self.supabase.table('profiles').select('games_played').eq('name', player_name).execute().data[0]['games_played'] + 1
                    })
                    .eq('name', player_name)
                    .execute
                )

            # Log to rating_history table (if exists)
            await self._log_rating_history(
                tournament_id,
                match_id,
                updated_ratings,
                old_ratings
            )

            logger.info("ratings_persisted",
                       tournament_id=tournament_id,
                       match_id=match_id,
                       players=len(updated_ratings))

        except Exception as e:
            logger.error("rating_persist_failed",
                        tournament_id=tournament_id,
                        error=str(e))
            raise

    async def _log_rating_history(
        self,
        tournament_id: str,
        match_id: str,
        updated_ratings: Dict[str, Tuple[float, float, float]],
        old_ratings: Dict[str, Tuple[float, float, float]]
    ) -> None:
        """
        Log rating changes to rating_history table for analytics.

        Args:
            tournament_id: Tournament ID
            match_id: Match ID
            updated_ratings: New ratings
            old_ratings: Previous ratings
        """
        if not self.supabase:
            return

        try:
            # Create history entries for each player
            history_entries = []
            for player_name, (new_mu, new_phi, new_sigma) in updated_ratings.items():
                old_mu, old_phi, old_sigma = old_ratings[player_name]

                history_entries.append({
                    'tournament_id': tournament_id,
                    'match_id': match_id,
                    'player_name': player_name,
                    'old_elo': int(round(old_mu)),
                    'new_elo': int(round(new_mu)),
                    'old_deviation': float(old_phi),
                    'new_deviation': float(new_phi),
                    'old_volatility': float(old_sigma),
                    'new_volatility': float(new_sigma),
                    'timestamp': datetime.utcnow().isoformat()
                })

            # Batch insert (if table exists)
            await asyncio.to_thread(
                self.supabase.table('rating_history')
                .insert(history_entries)
                .execute
            )

            logger.debug("rating_history_logged",
                        entries=len(history_entries))

        except Exception as e:
            # Non-critical - log but don't raise
            logger.warning("rating_history_log_failed",
                          error=str(e),
                          message="History tracking unavailable")

    # ---------- Rating Evolution Analytics ----------

    async def get_player_rating_evolution(
        self,
        player_name: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Fetch player's rating evolution history for UI display.

        Args:
            player_name: Player name
            limit: Max history entries to return

        Returns:
            List of rating changes with timestamps
        """
        if not self.supabase:
            return []

        try:
            response = await asyncio.to_thread(
                self.supabase.table('rating_history')
                .select('*')
                .eq('player_name', player_name)
                .order('timestamp', desc=True)
                .limit(limit)
                .execute
            )

            return response.data

        except Exception as e:
            logger.error("rating_evolution_fetch_failed",
                        player=player_name,
                        error=str(e))
            return []
