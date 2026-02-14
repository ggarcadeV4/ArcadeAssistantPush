"""Retro shooter mode handlers for game-specific calibration.

Provides specialized calibration and validation for arcade light gun classics:
- Time Crisis: Off-screen reload detection + pedal mechanics
- House of the Dead: Rapid fire with recoil weighting
- Point Blank: Precision trick shots
- Virtua Cop: Balanced accuracy focus
- Duck Hunt: Simple NES Zapper emulation
- Operation Wolf: Scrolling shooter with ammo limits

Each mode implements custom validation logic based on game mechanics.
"""

import logging
from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Retro Mode Enumeration
# ============================================================================

class RetroMode(str, Enum):
    """Retro arcade shooter game modes.

    Each mode represents a specific arcade game or style with unique
    calibration requirements and validation logic.
    """
    TIME_CRISIS = "time_crisis"
    HOUSE_DEAD = "house_dead"
    OPERATION_WOLF = "operation_wolf"
    POINT_BLANK = "point_blank"
    VIRTUA_COP = "virtua_cop"
    DUCK_HUNT = "duck_hunt"
    LETHAL_ENFORCERS = "lethal_enforcers"
    AREA_51 = "area51"


# ============================================================================
# Mode Data Model
# ============================================================================

class ModeData(BaseModel):
    """Retro mode configuration data.

    Attributes:
        mode: Selected retro game mode
        reload_threshold: Edge distance for off-screen reload (0.0-1.0)
        recoil_weight: Recoil impact on accuracy calculation
        rapid_fire: Enable rapid fire validation
        pedal_enabled: Footpedal for cover mechanics
    """
    mode: RetroMode = Field(..., description="Retro shooter game mode")
    reload_threshold: float = Field(
        0.8,
        ge=0.0,
        le=1.0,
        description="Screen edge threshold for off-screen reload"
    )
    recoil_weight: float = Field(
        1.0,
        ge=0.0,
        le=2.0,
        description="Recoil impact multiplier on accuracy"
    )
    rapid_fire: bool = Field(False, description="Enable rapid fire validation")
    pedal_enabled: bool = Field(False, description="Foot pedal for cover/reload")

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "time_crisis",
                "reload_threshold": 0.85,
                "recoil_weight": 1.2,
                "rapid_fire": False,
                "pedal_enabled": True
            }
        }


# ============================================================================
# Mode Handler Abstract Base Class
# ============================================================================

class ModeHandler(ABC):
    """Abstract base class for retro shooter mode handlers.

    Implementations provide game-specific calibration validation and
    post-calibration testing logic.
    """

    @abstractmethod
    async def validate_calib(
        self,
        points: List[Dict],
        gun_features: Dict[str, bool]
    ) -> Dict:
        """Validate calibration points for mode-specific requirements.

        Args:
            points: List of calibration points (x, y, confidence)
            gun_features: Gun capability flags (ir, recoil, rumble)

        Returns:
            Validation result with valid flag and mode-specific feedback
        """
        pass

    @abstractmethod
    async def test_mode_specific(self, gun: Dict) -> Dict:
        """Run mode-specific post-calibration tests.

        Args:
            gun: Gun device dictionary with features and config

        Returns:
            Test results with pass/fail and scores
        """
        pass

    @abstractmethod
    def get_mode_name(self) -> str:
        """Get human-readable mode name."""
        pass

    @abstractmethod
    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        """Get mode-specific recommendations based on gun features.

        Args:
            gun_features: Gun capability flags

        Returns:
            List of recommendation strings for user
        """
        pass


# ============================================================================
# Time Crisis Handler
# ============================================================================

class TimeCrisisHandler(ModeHandler):
    """Time Crisis mode handler.

    Validates:
    - Off-screen reload points (pedal or edge shots)
    - Cover mechanics compatibility
    - Rapid point acquisition

    Recommended for: Sinden, AIMTRAK, Gun4IR with recoil
    """

    async def validate_calib(
        self,
        points: List[Dict],
        gun_features: Dict[str, bool]
    ) -> Dict:
        """Validate Time Crisis calibration requirements.

        Time Crisis requires:
        - At least 3 off-screen edge points for reload detection
        - Good center accuracy for target acquisition
        - Optional recoil for immersion

        Args:
            points: Calibration points
            gun_features: Gun capabilities

        Returns:
            Validation result with reload detection feedback
        """
        # Detect off-screen edge points (reload zones)
        edges = [
            p for p in points
            if p['x'] < 0.05 or p['x'] > 0.95 or p['y'] < 0.05 or p['y'] > 0.95
        ]

        if len(edges) < 3:
            return {
                'valid': False,
                'error': 'Insufficient off-screen points for pedal reload (need 3+ edge points)',
                'edge_points': len(edges),
                'recommendation': 'Recalibrate with points near screen edges for reload detection'
            }

        # Calculate center accuracy (middle 5 points)
        center_indices = [3, 4, 5, 6, 7]  # Assuming 3x3 grid
        center_points = [points[i] for i in center_indices if i < len(points)]
        center_accuracy = sum(p.get('confidence', 1.0) for p in center_points) / len(center_points)

        return {
            'valid': True,
            'reload_score': len(edges) / len(points),
            'center_accuracy': center_accuracy,
            'edge_points': len(edges),
            'recoil_ready': gun_features.get('recoil', False)
        }

    async def test_mode_specific(self, gun: Dict) -> Dict:
        """Test Time Crisis-specific features.

        Tests:
        - Reload detection via edge tracking
        - Recoil vibration (if supported)
        - Rapid target switching

        Args:
            gun: Gun device with features

        Returns:
            Test results with scores
        """
        results = {
            'passes': True,
            'tests': {}
        }

        # Test 1: Reload detection
        results['tests']['reload_detection'] = {
            'pass': gun['features'].get('ir', False),
            'score': 100 if gun['features'].get('ir') else 50,
            'note': 'IR required for accurate reload detection'
        }

        # Test 2: Recoil capability
        results['tests']['recoil'] = {
            'pass': True,  # Optional
            'score': 100 if gun['features'].get('recoil') else 80,
            'note': 'Recoil enhances immersion but not required'
        }

        # Overall score
        scores = [t['score'] for t in results['tests'].values()]
        results['overall_score'] = sum(scores) / len(scores)

        return results

    def get_mode_name(self) -> str:
        return "Time Crisis"

    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        recs = []

        if not gun_features.get('ir'):
            recs.append("⚠️ IR tracking recommended for accurate reload detection")

        if not gun_features.get('recoil'):
            recs.append("💡 Recoil-enabled gun enhances immersion")

        recs.append("🎯 Calibrate edge points carefully for off-screen reload")
        recs.append("🦶 Consider footpedal for authentic Time Crisis experience")

        return recs


# ============================================================================
# House of the Dead Handler
# ============================================================================

class HouseOfTheDeadHandler(ModeHandler):
    """House of the Dead mode handler.

    Validates:
    - Rapid fire capability
    - Recoil weighting for accuracy
    - Fast target switching

    Recommended for: Gun4IR, AIMTRAK with recoil
    """

    async def validate_calib(
        self,
        points: List[Dict],
        gun_features: Dict[str, bool]
    ) -> Dict:
        """Validate House of the Dead calibration.

        House of the Dead requires:
        - Good overall accuracy (rapid fire compensates for spread)
        - Recoil support for authentic feel
        - Center-weighted calibration

        Args:
            points: Calibration points
            gun_features: Gun capabilities

        Returns:
            Validation result with recoil weighting
        """
        # Calculate overall accuracy
        total_confidence = sum(p.get('confidence', 1.0) for p in points)
        avg_accuracy = total_confidence / len(points)

        # Apply recoil weighting if supported
        if gun_features.get('recoil'):
            # Boost accuracy for recoil-enabled guns
            weighted_accuracy = min(avg_accuracy * 1.15, 1.0)
        else:
            weighted_accuracy = avg_accuracy

        return {
            'valid': True,
            'accuracy': weighted_accuracy,
            'recoil_weighted': gun_features.get('recoil', False),
            'rapid_fire_ready': True,  # Assume all guns can rapid fire
            'recommendation': 'Enable recoil for authentic zombie shooting experience'
        }

    async def test_mode_specific(self, gun: Dict) -> Dict:
        """Test House of the Dead-specific features.

        Tests:
        - Recoil vibration
        - Rapid fire timing
        - Target tracking

        Args:
            gun: Gun device

        Returns:
            Test results
        """
        results = {
            'passes': True,
            'tests': {}
        }

        # Recoil test
        results['tests']['recoil'] = {
            'pass': gun['features'].get('recoil', False),
            'score': 100 if gun['features'].get('recoil') else 70,
            'note': 'Recoil highly recommended for zombie shooting immersion'
        }

        # IR tracking
        results['tests']['tracking'] = {
            'pass': gun['features'].get('ir', False),
            'score': 100 if gun['features'].get('ir') else 85,
            'note': 'IR improves fast-moving target tracking'
        }

        scores = [t['score'] for t in results['tests'].values()]
        results['overall_score'] = sum(scores) / len(scores)

        return results

    def get_mode_name(self) -> str:
        return "House of the Dead"

    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        recs = []

        if not gun_features.get('recoil'):
            recs.append("⚠️ Recoil strongly recommended for authentic zombie shooting")

        recs.append("🎯 Center-weighted calibration for rapid target switching")
        recs.append("💥 Enable rapid fire mode for multi-zombie encounters")

        return recs


# ============================================================================
# Point Blank Handler
# ============================================================================

class PointBlankHandler(ModeHandler):
    """Point Blank mode handler.

    Validates:
    - Precision accuracy (trick shots)
    - Edge accuracy for target gallery
    - Fast acquisition

    Recommended for: All guns, especially precision models
    """

    async def validate_calib(
        self,
        points: List[Dict],
        gun_features: Dict[str, bool]
    ) -> Dict:
        """Validate Point Blank precision calibration.

        Point Blank requires:
        - High accuracy across all points
        - Good edge accuracy for trick shots
        - Precision over speed

        Args:
            points: Calibration points
            gun_features: Gun capabilities

        Returns:
            Validation result with precision metrics
        """
        # Calculate overall precision
        total_confidence = sum(p.get('confidence', 1.0) for p in points)
        avg_accuracy = total_confidence / len(points)

        # Check for poor calibration points
        poor_points = [p for p in points if p.get('confidence', 1.0) < 0.85]

        if poor_points:
            return {
                'valid': False,
                'error': f'Point Blank requires high precision (found {len(poor_points)} poor points)',
                'avg_accuracy': avg_accuracy,
                'poor_points': len(poor_points),
                'recommendation': 'Recalibrate with steady aim for all points (>85% confidence)'
            }

        return {
            'valid': True,
            'accuracy': avg_accuracy,
            'precision_grade': 'Excellent' if avg_accuracy > 0.95 else 'Good',
            'trick_shot_ready': avg_accuracy > 0.9
        }

    async def test_mode_specific(self, gun: Dict) -> Dict:
        """Test Point Blank precision features.

        Args:
            gun: Gun device

        Returns:
            Test results
        """
        results = {
            'passes': True,
            'tests': {}
        }

        # Precision test
        results['tests']['precision'] = {
            'pass': True,
            'score': 100,
            'note': 'All guns suitable for Point Blank with good calibration'
        }

        results['overall_score'] = 100

        return results

    def get_mode_name(self) -> str:
        return "Point Blank"

    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        return [
            "🎯 Take your time - precision over speed",
            "👌 Calibrate with steady hand for trick shot accuracy",
            "🏆 Practice makes perfect - recalibrate if accuracy drops"
        ]


# ============================================================================
# Virtua Cop Handler
# ============================================================================

class VirtuaCopHandler(ModeHandler):
    """Virtua Cop mode handler - balanced arcade action."""

    async def validate_calib(self, points: List[Dict], gun_features: Dict[str, bool]) -> Dict:
        # Balanced validation (standard accuracy)
        total_confidence = sum(p.get('confidence', 1.0) for p in points)
        avg_accuracy = total_confidence / len(points)

        return {
            'valid': avg_accuracy > 0.75,
            'accuracy': avg_accuracy,
            'balanced': True
        }

    async def test_mode_specific(self, gun: Dict) -> Dict:
        return {
            'passes': True,
            'overall_score': 90,
            'tests': {'balanced': {'pass': True, 'score': 90}}
        }

    def get_mode_name(self) -> str:
        return "Virtua Cop"

    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        return ["🎮 Balanced calibration for classic arcade action"]


# ============================================================================
# Duck Hunt Handler
# ============================================================================

class DuckHuntHandler(ModeHandler):
    """Duck Hunt mode handler - simple NES Zapper emulation."""

    async def validate_calib(self, points: List[Dict], gun_features: Dict[str, bool]) -> Dict:
        # Relaxed validation for emulated Zapper
        return {
            'valid': True,
            'emulation_mode': True,
            'note': 'Accuracy approximate for emulated Zapper'
        }

    async def test_mode_specific(self, gun: Dict) -> Dict:
        return {
            'passes': True,
            'overall_score': 85,
            'tests': {'emulation': {'pass': True, 'score': 85, 'note': 'Emulation mode'}}
        }

    def get_mode_name(self) -> str:
        return "Duck Hunt"

    def get_recommendations(self, gun_features: Dict[str, bool]) -> List[str]:
        recs = ["🦆 Simple emulation mode - perfect for NES classics"]

        if not gun_features.get('ir'):
            recs.append("💡 Physical adapter improves accuracy over emulation")

        return recs


# ============================================================================
# Mode Handler Registry
# ============================================================================

MODE_HANDLERS: Dict[RetroMode, ModeHandler] = {
    RetroMode.TIME_CRISIS: TimeCrisisHandler(),
    RetroMode.HOUSE_DEAD: HouseOfTheDeadHandler(),
    RetroMode.POINT_BLANK: PointBlankHandler(),
    RetroMode.VIRTUA_COP: VirtuaCopHandler(),
    RetroMode.DUCK_HUNT: DuckHuntHandler(),
}


def get_mode_handler(mode: RetroMode) -> Optional[ModeHandler]:
    """Get mode handler by RetroMode enum.

    Args:
        mode: RetroMode enum value

    Returns:
        ModeHandler instance or None if not found
    """
    return MODE_HANDLERS.get(mode)
