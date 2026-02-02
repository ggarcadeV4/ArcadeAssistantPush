"""
ScoreKeeper Sam - Pydantic Models

Data models for tournament management with comprehensive validation:
- PlayerProfile: Player data with skill levels and ratings
- TournamentData: Tournament configuration and metadata
- Match, BracketRound, TournamentBracket: Bracket structure
- SeedData: Seeding calculation results
- RatingData, MatchResult: Rating system models

All models include validators for data integrity and edge case handling.
"""

import uuid
from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
import structlog

# Initialize structured logger
logger = structlog.get_logger(__name__)


# ==================== Core Models ====================

class PlayerProfile(BaseModel):
    """
    Player profile data from Supabase.

    Attributes:
        id: Unique player identifier
        name: Display name
        skill_level: Skill rating 0-100 (0=novice, 100=expert)
        age: Player age for family-friendly seeding
        elo_score: Elo rating (default 1200)
        is_kid: Auto-detected from age < 13
        uuid: Tiebreaker for duplicate names
    """
    id: str
    name: str
    skill_level: int = Field(default=50, ge=0, le=100)
    age: Optional[int] = None
    elo_score: int = Field(default=1200, ge=0)
    is_kid: bool = False
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @validator('is_kid', pre=True, always=True)
    def set_is_kid(cls, v, values):
        """Auto-detect kid status based on age < 13."""
        if 'age' in values and values['age'] and values['age'] < 13:
            return True
        return v


class SeedingMode(BaseModel):
    """
    Seeding mode enum with validation.

    Supported modes:
    - casual: Random seeding
    - tournament: Elo-based seeding
    - fair_play: Balanced seeding for competitive fairness
    - random: Pure random
    - elo_standard: Standard Elo seeding
    - elo_glicko: Glicko-2 seeding with uncertainty
    - elo_family: Family-adjusted Elo
    - balanced_family: Kid Shield enabled
    """
    mode: str = Field(default="casual")

    @validator('mode')
    def validate_mode(cls, v):
        """Ensure mode is valid, default to casual."""
        valid_modes = [
            'casual', 'tournament', 'fair_play', 'random',
            'elo_standard', 'elo_glicko', 'elo_family', 'balanced_family'
        ]
        if v not in valid_modes:
            logger.warning("invalid_seeding_mode", mode=v, defaulting_to="casual")
            return 'casual'
        return v


class TournamentConfig(BaseModel):
    """
    Tournament configuration and metadata.

    Validates bracket size, player count, and seeding parameters.
    Automatically calculates bracket size from player count.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    mode: str = Field(default="casual")
    players: List[str]
    game_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    bracket_size: int
    enable_kid_shield: bool = False
    handicap_enabled: bool = False
    rating_variant: Optional[str] = Field(default="standard")

    @validator('mode')
    def validate_mode(cls, v):
        """Ensure mode is valid."""
        return SeedingMode(mode=v).mode

    @validator('players')
    def validate_players(cls, v):
        """Validate player list is not empty and has no duplicates."""
        if not v:
            raise ValueError("Player list cannot be empty")
        if len(v) != len(set(v)):
            duplicates = [p for p in v if v.count(p) > 1]
            logger.warning("duplicate_players_detected", duplicates=list(set(duplicates)))
            # Remove duplicates, keep first occurrence
            seen = set()
            v = [p for p in v if not (p in seen or seen.add(p))]
        return v

    @validator('bracket_size', pre=True, always=True)
    def set_bracket_size(cls, v, values):
        """
        Auto-calculate bracket size from player count.
        Rounds up to next power of 2 (4, 8, 16, 32, 64, 128).
        """
        if 'players' in values:
            player_count = len(values['players'])
            sizes = [4, 8, 16, 32, 64, 128]
            for size in sizes:
                if player_count <= size:
                    return size
            return 128  # Max size
        return v or 8

    @validator('rating_variant')
    def validate_rating_variant(cls, v):
        """Ensure rating variant is valid."""
        valid_variants = ['standard', 'glicko', 'family_adjusted']
        if v not in valid_variants:
            logger.warning("invalid_rating_variant", variant=v, defaulting_to="standard")
            return 'standard'
        return v


# Alias for backward compatibility
TournamentData = TournamentConfig


class Match(BaseModel):
    """
    Single match in tournament bracket.

    Attributes:
        id: Unique match identifier
        round_number: Round number (1-based)
        match_number: Match number within round
        player1, player2: Competing players (None if TBD)
        winner: Match winner (None if incomplete)
        score1, score2: Match scores
        is_bye: True if automatic advancement
        completed: Match completion status
    """
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

    @validator('winner')
    def validate_winner(cls, v, values):
        """Ensure winner is one of the players if set."""
        if v and 'player1' in values and 'player2' in values:
            if v not in [values['player1'], values['player2']]:
                raise ValueError(f"Winner {v} must be one of the players")
        return v


class BracketRound(BaseModel):
    """
    Single round in tournament bracket.

    Attributes:
        round_number: Round number (1-based)
        round_name: Human-readable name (e.g., "Quarterfinals")
        matches: List of matches in this round
        completed: True if all matches completed
    """
    round_number: int
    round_name: str
    matches: List[Match]
    completed: bool = False

    @validator('round_name', pre=True, always=True)
    def set_round_name(cls, v, values):
        """Auto-generate round name from number if not provided."""
        if v:
            return v
        if 'round_number' in values and 'matches' in values:
            round_num = values['round_number']
            match_count = len(values['matches'])
            # Determine name based on remaining matches
            if match_count == 1:
                return "Finals"
            elif match_count == 2:
                return "Semifinals"
            elif match_count == 4:
                return "Quarterfinals"
            else:
                return f"Round {round_num}"
        return "Round 1"


class BracketData(BaseModel):
    """
    Complete tournament bracket structure.

    Attributes:
        tournament_id: Associated tournament ID
        rounds: List of bracket rounds
        fairness_score: 0-100 balance metric (higher = more balanced)
        seeding_method: Seeding strategy used
        total_matches: Total match count
    """
    tournament_id: str
    rounds: List[BracketRound]
    fairness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    seeding_method: str
    total_matches: int

    @validator('total_matches', pre=True, always=True)
    def calculate_total_matches(cls, v, values):
        """Auto-calculate total matches from rounds."""
        if 'rounds' in values:
            return sum(len(r.matches) for r in values['rounds'])
        return v or 0


# Alias for backward compatibility
TournamentBracket = BracketData


class SeedData(BaseModel):
    """
    Seeding calculation result.

    Contains seeded player order and fairness metrics.
    """
    players: List[str]
    seed_scores: Dict[str, float]
    method: str
    fairness_score: float = Field(ge=0.0, le=100.0)


class RatingData(BaseModel):
    """
    Player rating data for Elo/Glicko-2 calculations.

    Attributes:
        player_id: Player identifier
        elo: Standard Elo rating (default 1500)
        games: Games played count
        volatility: Glicko-2 sigma (rate of rating change)
        deviation: Glicko-2 RD/phi (rating uncertainty)
    """
    player_id: str
    elo: float = Field(default=1500.0, ge=0)
    games: int = Field(default=0, ge=0)
    volatility: float = Field(default=0.06, ge=0, le=1.0)
    deviation: float = Field(default=350.0, ge=0)


class MatchResult(BaseModel):
    """
    Match result for rating updates.

    Attributes:
        player_a: First player ID
        player_b: Second player ID
        score_a: Result score (1.0=win, 0.5=draw, 0.0=loss)
    """
    player_a: str
    player_b: str
    score_a: float

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


class TournamentState(BaseModel):
    """
    Persisted tournament state for resume functionality.

    Tracks tournament progress and completed matches.
    """
    tournament_id: str
    name: str
    mode: str
    players: List[str]
    bracket_data: Dict  # TournamentBracket as dict
    current_round: int = 1
    completed_matches: List[str] = []
    active: bool = True
    created_at: datetime
    updated_at: datetime
    fairness_score: float = 0.0


class PlayerData(BaseModel):
    """
    Extended player data for tournament participation.

    Combines profile data with tournament-specific attributes.
    """
    id: str
    name: str
    skill_level: int = Field(default=50, ge=0, le=100)
    age: Optional[int] = None
    elo_score: int = Field(default=1200, ge=0)
    is_kid: bool = False
    tournament_seed: Optional[int] = None  # Assigned seed position
    handicap_multiplier: float = Field(default=1.0, ge=0.5, le=2.0)  # Score multiplier

    @validator('is_kid', pre=True, always=True)
    def set_is_kid(cls, v, values):
        """Auto-detect kid status based on age."""
        if 'age' in values and values['age'] and values['age'] < 13:
            return True
        return v


# ==================== Phase 4: Enhanced Sam Features ====================

class InitialsMapping(BaseModel):
    """
    Maps arcade initials (e.g., "DAD", "MOM") to player profiles.
    
    Allows Sam to recognize that "DAD" on Street Fighter leaderboard
    is the same person as "DAD" on Pac-Man.
    
    Attributes:
        id: Unique mapping identifier
        initials: 1-3 character arcade initials (uppercase)
        profile_id: FK to player profile
        profile_name: Display name for the linked profile
        game_ids: Optional list of game IDs this mapping applies to (None = all)
        priority: For disambiguation when multiple profiles use same initials
        created_at: When the mapping was created
        created_by: Who created the mapping (user/voice/auto)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    initials: str = Field(..., min_length=1, max_length=3)
    profile_id: str
    profile_name: str
    game_ids: Optional[List[str]] = None  # None = applies to all games
    priority: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    @validator('initials')
    def validate_initials(cls, v):
        """Ensure initials are uppercase and alphanumeric."""
        cleaned = v.upper().strip()
        if not cleaned.replace(" ", "").isalnum():
            raise ValueError("Initials must be alphanumeric")
        return cleaned


class HiddenReason(BaseModel):
    """
    Reason why a score was hidden from the leaderboard.
    """
    reason: str = Field(default="manual")

    @validator('reason')
    def validate_reason(cls, v):
        """Ensure reason is valid."""
        valid_reasons = [
            'practice',        # Marked as practice by user
            'inappropriate',   # Inappropriate initials
            'test',            # Test/setup score
            'duplicate',       # Duplicate entry
            'manual',          # Manually hidden by operator
            'auto_moderated',  # Flagged by auto-moderation
            'impossibly_high', # Score exceeds known max
        ]
        if v not in valid_reasons:
            logger.warning("invalid_hidden_reason", reason=v, defaulting_to="manual")
            return 'manual'
        return v


class HiddenScore(BaseModel):
    """
    Metadata for a hidden/moderated score entry.
    
    Scores can be hidden from the public leaderboard without deletion.
    
    Attributes:
        score_id: The ID of the hidden score entry
        hidden: Whether the score is currently hidden
        hidden_reason: Why the score was hidden
        hidden_at: When the score was hidden
        hidden_by: Who hid the score (operator, auto, voice)
        moderation_status: approved, pending, or rejected
        moderation_note: Optional note from moderator
    """
    score_id: str
    hidden: bool = False
    hidden_reason: Optional[str] = None
    hidden_at: Optional[datetime] = None
    hidden_by: Optional[str] = None
    moderation_status: str = Field(default="approved")
    moderation_note: Optional[str] = None

    @validator('moderation_status')
    def validate_moderation_status(cls, v):
        """Ensure moderation status is valid."""
        valid_statuses = ['approved', 'pending', 'rejected']
        if v not in valid_statuses:
            return 'approved'
        return v


class HouseholdSettings(BaseModel):
    """
    Configuration settings for a household.
    """
    auto_moderate: bool = False          # Auto-hide inappropriate scores
    require_approval: bool = False       # New scores need approval
    allow_guest_scores: bool = True      # Allow unlinked initials
    default_visibility: str = Field(default="public")  # public, household_only, private

    @validator('default_visibility')
    def validate_visibility(cls, v):
        valid = ['public', 'household_only', 'private']
        if v not in valid:
            return 'public'
        return v


class Household(BaseModel):
    """
    A household that owns one or more arcade cabinets.
    
    Groups players together for family leaderboards and management.
    
    Attributes:
        id: Unique household identifier
        name: Household name (e.g., "The Smith Family")
        cabinet_ids: List of cabinet IDs in this household
        settings: Household configuration
        created_at: When the household was created
        updated_at: Last update time
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cabinet_ids: List[str] = Field(default_factory=list)
    settings: HouseholdSettings = Field(default_factory=HouseholdSettings)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HouseholdMemberRole(BaseModel):
    """
    Role for a household member.
    """
    role: str = Field(default="member")

    @validator('role')
    def validate_role(cls, v):
        valid_roles = ['owner', 'admin', 'member', 'guest']
        if v not in valid_roles:
            return 'member'
        return v


class HouseholdMember(BaseModel):
    """
    A member of a household.
    
    Links player profiles to households with role-based permissions.
    
    Attributes:
        id: Unique membership identifier
        household_id: FK to household
        profile_id: FK to player profile
        profile_name: Display name
        role: owner, admin, member, or guest
        joined_at: When they joined
        invited_by: Who invited them (profile_id)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    household_id: str
    profile_id: str
    profile_name: str
    role: str = Field(default="member")
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    invited_by: Optional[str] = None

    @validator('role')
    def validate_role(cls, v):
        return HouseholdMemberRole(role=v).role


# ==================== Sam Persistence State ====================

class SamState(BaseModel):
    """
    Complete Sam state for persistence.
    
    Stores all Sam-managed data including households, initials mappings,
    and hidden score metadata.
    """
    households: Dict[str, Household] = Field(default_factory=dict)
    household_members: Dict[str, List[HouseholdMember]] = Field(default_factory=dict)  # household_id -> members
    initials_mappings: List[InitialsMapping] = Field(default_factory=list)
    hidden_scores: Dict[str, HiddenScore] = Field(default_factory=dict)  # score_id -> hidden metadata
    updated_at: datetime = Field(default_factory=datetime.utcnow)

