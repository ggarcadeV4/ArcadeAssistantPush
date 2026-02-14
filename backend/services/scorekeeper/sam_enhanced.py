"""
Scorekeeper Sam - Enhanced Features Service

Phase 4 implementation for:
- Profile-to-Initials Mapping
- Hidden/Moderated Scores
- Household Player Registry

This service provides the business logic for Sam's enhanced features,
persisting state to sam_state.json in the scorekeeper directory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    InitialsMapping,
    HiddenScore,
    Household,
    HouseholdMember,
    HouseholdSettings,
    SamState,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# State Persistence
# -----------------------------------------------------------------------------

def get_sam_state_file(drive_root: Path) -> Path:
    """Get the path to sam_state.json."""
    return drive_root / ".aa" / "state" / "scorekeeper" / "sam_state.json"


def load_sam_state(drive_root: Path) -> SamState:
    """Load Sam state from disk.
    
    Returns an empty SamState if the file doesn't exist.
    """
    state_file = get_sam_state_file(drive_root)
    
    if not state_file.exists():
        return SamState()
    
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SamState.parse_obj(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to load Sam state: {e}")
        return SamState()


def save_sam_state(drive_root: Path, state: SamState) -> Path:
    """Save Sam state to disk.
    
    Returns the path to the saved file.
    """
    state_file = get_sam_state_file(drive_root)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    state.updated_at = datetime.utcnow()
    
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state.dict(), f, indent=2, default=str)
    
    logger.info(f"Saved Sam state to {state_file}")
    return state_file


# -----------------------------------------------------------------------------
# Initials Mapping Service
# -----------------------------------------------------------------------------

class InitialsMappingService:
    """Service for managing initials-to-profile mappings."""
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
    
    def create_mapping(
        self,
        initials: str,
        profile_id: str,
        profile_name: str,
        game_ids: Optional[List[str]] = None,
        created_by: Optional[str] = None,
    ) -> InitialsMapping:
        """Create a new initials mapping.
        
        Args:
            initials: 1-3 character arcade initials
            profile_id: Player profile ID
            profile_name: Display name for the profile
            game_ids: Optional list of game IDs (None = all games)
            created_by: Who created the mapping
        
        Returns:
            The created InitialsMapping
        """
        state = load_sam_state(self.drive_root)
        
        # Check for existing mapping with same initials and profile
        for existing in state.initials_mappings:
            if existing.initials == initials.upper() and existing.profile_id == profile_id:
                logger.info(f"Mapping already exists: {initials} -> {profile_name}")
                return existing
        
        mapping = InitialsMapping(
            initials=initials,
            profile_id=profile_id,
            profile_name=profile_name,
            game_ids=game_ids,
            created_by=created_by,
        )
        
        state.initials_mappings.append(mapping)
        save_sam_state(self.drive_root, state)
        
        logger.info(f"Created initials mapping: {initials} -> {profile_name}")
        return mapping
    
    def resolve_initials(
        self,
        initials: str,
        game_id: Optional[str] = None,
    ) -> Optional[InitialsMapping]:
        """Resolve initials to a player profile.
        
        If multiple mappings exist for the same initials, returns the
        one with highest priority. If game_id is provided, prefers
        game-specific mappings.
        
        Args:
            initials: Arcade initials to resolve
            game_id: Optional game ID for game-specific resolution
        
        Returns:
            The matching InitialsMapping or None
        """
        state = load_sam_state(self.drive_root)
        
        normalized = initials.upper().strip()
        candidates: List[InitialsMapping] = []
        
        for mapping in state.initials_mappings:
            if mapping.initials != normalized:
                continue
            
            # Check game filter
            if mapping.game_ids is not None and game_id not in mapping.game_ids:
                continue
            
            candidates.append(mapping)
        
        if not candidates:
            return None
        
        # Sort by: game-specific first, then priority
        def sort_key(m: InitialsMapping) -> tuple:
            is_game_specific = (
                m.game_ids is not None and game_id in m.game_ids
            ) if game_id else False
            return (not is_game_specific, -m.priority)
        
        candidates.sort(key=sort_key)
        return candidates[0]
    
    def list_mappings(
        self,
        profile_id: Optional[str] = None,
    ) -> List[InitialsMapping]:
        """List all initials mappings.
        
        Args:
            profile_id: Optional filter by profile ID
        
        Returns:
            List of InitialsMapping objects
        """
        state = load_sam_state(self.drive_root)
        
        if profile_id:
            return [m for m in state.initials_mappings if m.profile_id == profile_id]
        
        return state.initials_mappings
    
    def delete_mapping(self, mapping_id: str) -> bool:
        """Delete an initials mapping.
        
        Returns True if deleted, False if not found.
        """
        state = load_sam_state(self.drive_root)
        
        original_count = len(state.initials_mappings)
        state.initials_mappings = [
            m for m in state.initials_mappings if m.id != mapping_id
        ]
        
        if len(state.initials_mappings) < original_count:
            save_sam_state(self.drive_root, state)
            logger.info(f"Deleted initials mapping: {mapping_id}")
            return True
        
        return False


# -----------------------------------------------------------------------------
# Hidden Scores Service
# -----------------------------------------------------------------------------

class HiddenScoresService:
    """Service for managing hidden/moderated scores."""
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
    
    def hide_score(
        self,
        score_id: str,
        reason: str = "manual",
        hidden_by: Optional[str] = None,
        note: Optional[str] = None,
    ) -> HiddenScore:
        """Hide a score from the leaderboard.
        
        Args:
            score_id: ID of the score to hide
            reason: Why the score is being hidden
            hidden_by: Who is hiding the score
            note: Optional moderation note
        
        Returns:
            The HiddenScore metadata
        """
        state = load_sam_state(self.drive_root)
        
        hidden = HiddenScore(
            score_id=score_id,
            hidden=True,
            hidden_reason=reason,
            hidden_at=datetime.utcnow(),
            hidden_by=hidden_by,
            moderation_status="rejected" if reason == "inappropriate" else "pending",
            moderation_note=note,
        )
        
        state.hidden_scores[score_id] = hidden
        save_sam_state(self.drive_root, state)
        
        logger.info(f"Hidden score {score_id}: {reason}")
        return hidden
    
    def unhide_score(self, score_id: str) -> bool:
        """Unhide a previously hidden score.
        
        Returns True if unhidden, False if not found.
        """
        state = load_sam_state(self.drive_root)
        
        if score_id in state.hidden_scores:
            del state.hidden_scores[score_id]
            save_sam_state(self.drive_root, state)
            logger.info(f"Unhidden score: {score_id}")
            return True
        
        return False
    
    def is_hidden(self, score_id: str) -> bool:
        """Check if a score is hidden."""
        state = load_sam_state(self.drive_root)
        return score_id in state.hidden_scores
    
    def get_hidden_reason(self, score_id: str) -> Optional[str]:
        """Get the reason a score was hidden."""
        state = load_sam_state(self.drive_root)
        hidden = state.hidden_scores.get(score_id)
        return hidden.hidden_reason if hidden else None
    
    def list_hidden(self) -> List[HiddenScore]:
        """List all hidden scores."""
        state = load_sam_state(self.drive_root)
        return list(state.hidden_scores.values())
    
    def get_visible_score_ids(self, score_ids: List[str]) -> List[str]:
        """Filter a list of score IDs to only visible ones."""
        state = load_sam_state(self.drive_root)
        return [sid for sid in score_ids if sid not in state.hidden_scores]


# -----------------------------------------------------------------------------
# Household Service
# -----------------------------------------------------------------------------

class HouseholdService:
    """Service for managing households and family players."""
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
    
    def create_household(
        self,
        name: str,
        cabinet_id: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Household:
        """Create a new household.
        
        Args:
            name: Household name (e.g., "The Smith Family")
            cabinet_id: Optional initial cabinet ID
            settings: Optional household settings
        
        Returns:
            The created Household
        """
        state = load_sam_state(self.drive_root)
        
        household_settings = HouseholdSettings(**(settings or {}))
        cabinet_ids = [cabinet_id] if cabinet_id else []
        
        household = Household(
            name=name,
            cabinet_ids=cabinet_ids,
            settings=household_settings,
        )
        
        state.households[household.id] = household
        state.household_members[household.id] = []
        save_sam_state(self.drive_root, state)
        
        logger.info(f"Created household: {name} ({household.id})")
        return household
    
    def get_household(self, household_id: str) -> Optional[Household]:
        """Get a household by ID."""
        state = load_sam_state(self.drive_root)
        return state.households.get(household_id)
    
    def get_household_for_cabinet(self, cabinet_id: str) -> Optional[Household]:
        """Get the household that owns a cabinet."""
        state = load_sam_state(self.drive_root)
        
        for household in state.households.values():
            if cabinet_id in household.cabinet_ids:
                return household
        
        return None
    
    def add_member(
        self,
        household_id: str,
        profile_id: str,
        profile_name: str,
        role: str = "member",
        invited_by: Optional[str] = None,
    ) -> Optional[HouseholdMember]:
        """Add a member to a household.
        
        Returns the HouseholdMember or None if household not found.
        """
        state = load_sam_state(self.drive_root)
        
        if household_id not in state.households:
            return None
        
        # Check if already a member
        members = state.household_members.get(household_id, [])
        for m in members:
            if m.profile_id == profile_id:
                logger.info(f"Profile {profile_id} already in household {household_id}")
                return m
        
        member = HouseholdMember(
            household_id=household_id,
            profile_id=profile_id,
            profile_name=profile_name,
            role=role,
            invited_by=invited_by,
        )
        
        if household_id not in state.household_members:
            state.household_members[household_id] = []
        
        state.household_members[household_id].append(member)
        save_sam_state(self.drive_root, state)
        
        logger.info(f"Added {profile_name} to household {household_id} as {role}")
        return member
    
    def remove_member(
        self,
        household_id: str,
        profile_id: str,
    ) -> bool:
        """Remove a member from a household.
        
        Returns True if removed, False if not found.
        """
        state = load_sam_state(self.drive_root)
        
        if household_id not in state.household_members:
            return False
        
        original = len(state.household_members[household_id])
        state.household_members[household_id] = [
            m for m in state.household_members[household_id]
            if m.profile_id != profile_id
        ]
        
        if len(state.household_members[household_id]) < original:
            save_sam_state(self.drive_root, state)
            logger.info(f"Removed {profile_id} from household {household_id}")
            return True
        
        return False
    
    def list_members(self, household_id: str) -> List[HouseholdMember]:
        """List all members of a household."""
        state = load_sam_state(self.drive_root)
        return state.household_members.get(household_id, [])
    
    def get_member_profile_ids(self, household_id: str) -> List[str]:
        """Get all profile IDs in a household."""
        members = self.list_members(household_id)
        return [m.profile_id for m in members]
    
    def link_cabinet(self, household_id: str, cabinet_id: str) -> bool:
        """Link a cabinet to a household.
        
        Returns True if linked, False if household not found.
        """
        state = load_sam_state(self.drive_root)
        
        if household_id not in state.households:
            return False
        
        household = state.households[household_id]
        if cabinet_id not in household.cabinet_ids:
            household.cabinet_ids.append(cabinet_id)
            household.updated_at = datetime.utcnow()
            save_sam_state(self.drive_root, state)
            logger.info(f"Linked cabinet {cabinet_id} to household {household_id}")
        
        return True


# -----------------------------------------------------------------------------
# Combined Sam Service
# -----------------------------------------------------------------------------

class SamEnhancedService:
    """
    Combined service for all Sam enhanced features.
    
    Provides a single entry point for:
    - Initials mapping
    - Hidden scores
    - Household management
    """
    
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
        self.initials = InitialsMappingService(drive_root)
        self.hidden = HiddenScoresService(drive_root)
        self.households = HouseholdService(drive_root)
    
    def get_state(self) -> SamState:
        """Get the current Sam state."""
        return load_sam_state(self.drive_root)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Sam statistics."""
        state = load_sam_state(self.drive_root)
        return {
            "households_count": len(state.households),
            "members_count": sum(len(m) for m in state.household_members.values()),
            "initials_mappings_count": len(state.initials_mappings),
            "hidden_scores_count": len(state.hidden_scores),
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
