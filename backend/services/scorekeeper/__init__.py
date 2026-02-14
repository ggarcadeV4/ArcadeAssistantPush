"""
ScoreKeeper Sam - Tournament Service Module

Modular architecture for tournament management:
- models.py: Pydantic schemas with validators
- service.py: Core tournament seeding and bracket generation
- persistence.py: Supabase persistence and state management

Exports:
- Models: PlayerData, BracketData, TournamentConfig, TournamentState, etc.
- TournamentService: Core tournament seeding and bracket generation
- PersistenceService: Supabase persistence with offline fallback
"""

from .models import (
    PlayerProfile,
    PlayerData,
    TournamentConfig,
    TournamentData,
    Match,
    BracketRound,
    BracketData,
    TournamentBracket,
    SeedData,
    RatingData,
    MatchResult,
    TournamentState,
    SeedingMode,
)

from .service import TournamentService

from .persistence import PersistenceService

__all__ = [
    # Models
    'PlayerProfile',
    'PlayerData',
    'TournamentConfig',
    'TournamentData',
    'Match',
    'BracketRound',
    'BracketData',
    'TournamentBracket',
    'SeedData',
    'RatingData',
    'MatchResult',
    'TournamentState',
    'SeedingMode',
    # Services
    'TournamentService',
    'PersistenceService',
]
