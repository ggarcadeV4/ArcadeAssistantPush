"""Comprehensive test suite for LED Blinky service.

Tests cover:
- Pydantic model validation (GamePattern, SequenceStep, SequenceState)
- Pattern resolver with XML parsing
- Service stream generators
- Tutor sequence state machine
- Edge cases and error handling

Target: >85% code coverage
"""
import asyncio
import pytest
from typing import Dict
from unittest.mock import AsyncMock, Mock, patch

from backend.services.blinky.models import (
    GamePattern,
    LEDAction,
    PatternPreview,
    SequenceState,
    SequenceStep,
    StepUpdate,
    TutorMode
)
from backend.services.blinky.resolver import (
    MockResolver,
    PatternResolver,
    get_mock_patterns,
    infer_button_pattern
)
from backend.services.blinky.service import BlinkyService, hex_to_rgb, batch_updates
from backend.services.blinky.sequencer import (
    MockInputPoller,
    build_tutor_sequence,
    generate_tutor_sequence,
    run_tutor_sequence
)


# ============================================================================
# Model Tests
# ============================================================================

class TestModels:
    """Test Pydantic model validation."""

    def test_game_pattern_valid(self):
        """Test valid GamePattern creation."""
        pattern = GamePattern(
            rom="sf2",
            active_leds={1: "#FF0000", 2: "#00FF00"},
            inactive_leds=[3, 4, 5],
            game_name="Street Fighter 2"
        )
        assert pattern.rom == "sf2"
        assert len(pattern.active_leds) == 2
        assert len(pattern.inactive_leds) == 3

    def test_game_pattern_invalid_color(self):
        """Test GamePattern rejects invalid hex colors."""
        with pytest.raises(ValueError, match="hex format"):
            GamePattern(
                rom="test",
                active_leds={1: "red"},  # Invalid - not hex
                inactive_leds=[]
            )

    def test_game_pattern_overlap_validation(self):
        """Test GamePattern prevents LED overlap."""
        with pytest.raises(ValueError, match="both active and inactive"):
            GamePattern(
                rom="test",
                active_leds={1: "#FF0000"},
                inactive_leds=[1]  # Overlap!
            )

    def test_game_pattern_get_combined_updates(self):
        """Test get_combined_updates merges active and inactive."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00"},
            inactive_leds=[3, 4],
            inactive_color="#000000"
        )
        updates = pattern.get_combined_updates(total_leds=8)

        assert updates[1] == "#FF0000"
        assert updates[2] == "#00FF00"
        assert updates[3] == "#000000"  # Inactive
        assert updates[4] == "#000000"  # Inactive
        assert updates[5] == "#000000"  # Unspecified, defaults to inactive

    def test_sequence_step_valid(self):
        """Test valid SequenceStep creation."""
        step = SequenceStep(
            led_id=1,
            action=LEDAction.PULSE,
            duration_ms=1500,
            color="#FF0000",
            hint="Press red button"
        )
        assert step.led_id == 1
        assert step.action == LEDAction.PULSE
        assert step.duration_ms == 1500

    def test_sequence_step_invalid_duration(self):
        """Test SequenceStep rejects invalid durations."""
        with pytest.raises(ValueError):
            SequenceStep(
                led_id=1,
                action=LEDAction.PULSE,
                duration_ms=300,  # Too short (min 500ms)
                color="#FF0000"
            )

    def test_sequence_state_advance(self):
        """Test SequenceState advance logic."""
        state = SequenceState(
            rom="test",
            steps=[
                SequenceStep(led_id=1, action=LEDAction.PULSE, duration_ms=1000, color="#FF0000"),
                SequenceStep(led_id=2, action=LEDAction.PULSE, duration_ms=1000, color="#00FF00"),
            ]
        )

        assert state.current_step == 0
        assert not state.is_complete()

        state.advance()
        assert state.current_step == 1

        state.advance()
        assert state.is_complete()

    def test_sequence_state_retry_branch(self):
        """Test SequenceState retry branching."""
        state = SequenceState(
            rom="test",
            steps=[
                SequenceStep(led_id=1, action=LEDAction.PULSE, duration_ms=1000, color="#FF0000")
            ],
            branches={
                0: [SequenceStep(led_id=1, action=LEDAction.PULSE, duration_ms=2000, color="#FF0000")]
            },
            max_retries=2
        )

        # First retry
        retry = state.branch_to_retry()
        assert retry is not None
        assert state.retry_count == 1

        # Second retry
        retry = state.branch_to_retry()
        assert retry is not None
        assert state.retry_count == 2

        # Max retries exceeded
        retry = state.branch_to_retry()
        assert retry is None


# ============================================================================
# Resolver Tests
# ============================================================================

class TestResolver:
    """Test pattern resolver functionality."""

    def test_mock_patterns(self):
        """Test mock patterns are available."""
        patterns = get_mock_patterns()
        assert "sf2" in patterns
        assert "dkong" in patterns
        assert len(patterns) >= 5

    def test_mock_resolver_get_pattern(self):
        """Test MockResolver returns patterns."""
        resolver = MockResolver()
        pattern = resolver.get_pattern("sf2")

        assert pattern.rom == "sf2"
        assert len(pattern.active_leds) == 6  # 6 buttons for SF2

    def test_mock_resolver_unknown_rom(self):
        """Test MockResolver handles unknown ROMs."""
        resolver = MockResolver()
        pattern = resolver.get_pattern("unknown_rom_xyz")

        # Should return default pattern
        assert pattern.rom == "unknown_rom_xyz"
        assert len(pattern.active_leds) >= 1  # At least one button

    def test_infer_button_pattern_fighting(self):
        """Test button inference for fighting games."""
        pattern = infer_button_pattern("sf2", "Street Fighter II", "Arcade")

        assert len(pattern.active_leds) == 6  # Fighting games have 6 buttons
        assert pattern.control_count == 6

    def test_infer_button_pattern_single_button(self):
        """Test button inference for single button games."""
        pattern = infer_button_pattern("dkong", "Donkey Kong", "Arcade")

        assert len(pattern.active_leds) == 1  # Single jump button
        assert pattern.control_count == 1

    def test_infer_button_pattern_beatem_up(self):
        """Test button inference for beat-em-ups."""
        pattern = infer_button_pattern("tmnt", "Teenage Mutant Ninja Turtles", "Arcade")

        assert len(pattern.active_leds) == 3  # 3 buttons for beat-em-ups
        assert pattern.control_count == 3

    @pytest.mark.asyncio
    async def test_pattern_resolver_initialize(self):
        """Test PatternResolver initialization."""
        # Initialize resolver
        await PatternResolver.initialize()

        resolver = PatternResolver()
        patterns = resolver.get_all_patterns()

        # Should have patterns loaded (either real or mock)
        assert len(patterns) > 0

    def test_pattern_resolver_lru_cache(self):
        """Test PatternResolver LRU cache functionality."""
        resolver = PatternResolver()

        # First call - cache miss
        pattern1 = resolver.get_pattern("sf2")
        assert pattern1 is not None

        # Second call - cache hit (should return same object)
        pattern2 = resolver.get_pattern("sf2")
        assert pattern2 is not None

        # Clear cache
        resolver.clear_cache()

        # After clear - cache miss again
        pattern3 = resolver.get_pattern("sf2")
        assert pattern3 is not None


# ============================================================================
# Service Tests
# ============================================================================

class TestBlinkyService:
    """Test BlinkyService stream generators."""

    def test_hex_to_rgb(self):
        """Test hex color conversion."""
        assert hex_to_rgb("#FF0000") == (255, 0, 0)  # Red
        assert hex_to_rgb("#00FF00") == (0, 255, 0)  # Green
        assert hex_to_rgb("#0000FF") == (0, 0, 255)  # Blue
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)  # White

    def test_batch_updates(self):
        """Test LED update batching."""
        updates = {i: f"#{i:02x}0000" for i in range(1, 17)}  # 16 LEDs

        batches = batch_updates(updates, batch_size=4)

        assert len(batches) == 4  # 16 LEDs / 4 per batch
        assert len(batches[0]) == 4
        assert len(batches[3]) == 4

    @pytest.mark.asyncio
    async def test_service_singleton(self):
        """Test BlinkyService is singleton."""
        service1 = BlinkyService()
        service2 = BlinkyService()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_get_pattern_preview(self):
        """Test pattern preview generation."""
        await PatternResolver.initialize()
        service = BlinkyService()

        preview = await service.get_pattern_preview("sf2", total_leds=32)

        assert isinstance(preview, PatternPreview)
        assert preview.rom == "sf2"
        assert preview.active_count == 6  # SF2 has 6 buttons
        assert len(preview.preview_updates) == 32  # All 32 LEDs specified

    @pytest.mark.asyncio
    @patch('backend.services.blinky.service.write_port')
    async def test_process_game_lights_preview(self, mock_write):
        """Test process_game_lights in preview mode."""
        await PatternResolver.initialize()
        service = BlinkyService()

        updates = []
        async for update in service.process_game_lights(
            rom="sf2",
            preview_only=True
        ):
            updates.append(update)

        # Should have processing, applying, and completed statuses
        statuses = [u['status'] for u in updates]
        assert 'processing' in statuses
        assert 'completed' in statuses

        # Preview mode should not write to hardware
        mock_write.assert_not_called()

    @pytest.mark.asyncio
    @patch('backend.services.blinky.service.get_devices')
    async def test_apply_all_dark(self, mock_devices):
        """Test apply_all_dark turns off all LEDs."""
        mock_devices.return_value = [{"id": 0, "ports": 8}]

        service = BlinkyService()

        with patch('backend.services.blinky.service.write_port') as mock_write:
            await service.apply_all_dark(device_id=0, total_leds=8)

            # Should have written black (0,0,0) to all 8 LEDs
            assert mock_write.call_count == 8

            for i in range(1, 9):
                mock_write.assert_any_call(0, i, (0, 0, 0))


# ============================================================================
# Sequencer Tests
# ============================================================================

class TestSequencer:
    """Test tutor sequence generator."""

    def test_build_tutor_sequence_kid_mode(self):
        """Test tutor sequence building for kid mode."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00", 3: "#0000FF", 4: "#FFFF00", 5: "#FF00FF"},
            inactive_leds=[]
        )

        state = build_tutor_sequence(pattern, TutorMode.KID)

        # Kid mode limits to 4 steps
        assert len(state.steps) <= 4

        # Kid mode has longer durations
        for step in state.steps:
            assert step.duration_ms >= 2000  # 2x slower

    def test_build_tutor_sequence_pro_mode(self):
        """Test tutor sequence building for pro mode."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00", 3: "#0000FF"},
            inactive_leds=[]
        )

        state = build_tutor_sequence(pattern, TutorMode.PRO)

        # Pro mode faster durations
        for step in state.steps:
            assert step.duration_ms < 1500  # 0.7x faster

    @pytest.mark.asyncio
    async def test_generate_tutor_sequence(self):
        """Test simple tutor sequence generation."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00"},
            inactive_leds=[]
        )

        steps = []
        async for step in generate_tutor_sequence(pattern, mode='standard'):
            steps.append(step)

        assert len(steps) == 2
        assert steps[0].led_id == 1
        assert steps[1].led_id == 2

    @pytest.mark.asyncio
    async def test_run_tutor_sequence_success_path(self):
        """Test tutor sequence with all successful inputs."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00"},
            inactive_leds=[]
        )

        # Mock poller that always succeeds
        poller = MockInputPoller()
        with patch.object(poller, 'check_press', return_value=True):
            updates = []
            async for update in run_tutor_sequence(
                pattern=pattern,
                mode=TutorMode.STANDARD,
                poller=poller,
                preview_only=True
            ):
                updates.append(update)

            # Should have completed all steps
            completed = [u for u in updates if u.status == "completed"]
            assert len(completed) == 2

    @pytest.mark.asyncio
    async def test_run_tutor_sequence_with_retries(self):
        """Test tutor sequence with missed inputs and retries."""
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000"},
            inactive_leds=[]
        )

        # Mock poller that fails first, then succeeds
        poller = MockInputPoller()
        call_count = 0

        async def mock_check(led_id, timeout):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Fail first, succeed after

        with patch.object(poller, 'check_press', side_effect=mock_check):
            updates = []
            async for update in run_tutor_sequence(
                pattern=pattern,
                mode=TutorMode.STANDARD,
                poller=poller,
                preview_only=True
            ):
                updates.append(update)

            # Should have retry status
            statuses = [u.status for u in updates]
            assert "retry" in statuses


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_pattern_with_no_active_leds(self):
        """Test pattern with only inactive LEDs (joystick only)."""
        pattern = GamePattern(
            rom="pacman",
            active_leds={},
            inactive_leds=[1, 2, 3, 4]
        )

        assert len(pattern.active_leds) == 0
        updates = pattern.get_combined_updates(8)

        # All LEDs should be dark
        for i in range(1, 9):
            assert updates[i] == "#000000"

    def test_pattern_brightness_validation(self):
        """Test brightness validation."""
        with pytest.raises(ValueError):
            GamePattern(
                rom="test",
                active_leds={1: "#FF0000"},
                inactive_leds=[],
                brightness=150  # Invalid - max 100
            )

    def test_sequence_step_max_duration(self):
        """Test sequence step max duration validation."""
        with pytest.raises(ValueError):
            SequenceStep(
                led_id=1,
                action=LEDAction.PULSE,
                duration_ms=6000,  # Too long (max 5000ms)
                color="#FF0000"
            )

    def test_sequence_state_max_retries(self):
        """Test sequence state max retries validation."""
        with pytest.raises(ValueError):
            SequenceState(
                rom="test",
                steps=[],
                max_retries=10  # Too many (max 5)
            )

    @pytest.mark.asyncio
    async def test_service_handles_missing_device(self):
        """Test service handles missing LED device gracefully."""
        with patch('backend.services.blinky.service.get_devices', return_value=[]):
            service = BlinkyService()

            updates = []
            async for update in service.process_game_lights("sf2"):
                updates.append(update)

            # Should have error status
            assert any(u['status'] == 'error' for u in updates)

    @pytest.mark.asyncio
    async def test_service_handles_pattern_overrides(self):
        """Test service applies pattern overrides."""
        await PatternResolver.initialize()
        service = BlinkyService()

        preview = await service.get_pattern_preview(
            "sf2",
            overrides={"brightness": 50},
            total_leds=32
        )

        assert preview.pattern.brightness == 50


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for end-to-end workflows."""

    async def test_full_pattern_application_workflow(self):
        """Test complete workflow from ROM to LED application."""
        # Initialize resolver
        await PatternResolver.initialize()

        # Get service
        service = BlinkyService()

        # Preview pattern
        preview = await service.get_pattern_preview("sf2", total_leds=32)
        assert preview.active_count == 6

        # Apply pattern (preview mode)
        with patch('backend.services.blinky.service.get_devices') as mock_devices:
            mock_devices.return_value = [{"id": 0, "ports": 32}]

            updates = []
            async for update in service.process_game_lights(
                rom="sf2",
                preview_only=True
            ):
                updates.append(update)

            assert any(u['status'] == 'completed' for u in updates)

    async def test_full_tutor_sequence_workflow(self):
        """Test complete tutor sequence workflow."""
        # Build pattern
        pattern = GamePattern(
            rom="test",
            active_leds={1: "#FF0000", 2: "#00FF00"},
            inactive_leds=[]
        )

        # Build sequence
        state = build_tutor_sequence(pattern, TutorMode.STANDARD)
        assert len(state.steps) == 2

        # Run sequence
        poller = MockInputPoller()
        updates = []
        async for update in run_tutor_sequence(
            pattern=pattern,
            mode=TutorMode.STANDARD,
            poller=poller,
            preview_only=True
        ):
            updates.append(update)

        # Should have executed both steps
        assert len(updates) >= 2
