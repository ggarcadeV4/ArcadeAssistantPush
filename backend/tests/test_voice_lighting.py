"""Comprehensive tests for voice lighting commands."""

import pytest
import asyncio
from datetime import datetime
from backend.services.voice.parser import LightingCommandParser
from backend.services.voice.models import LightingIntent, LightingCommand, ColorMapping
from backend.services.voice.command_buffer import CommandBuffer
from backend.services.voice.service import VoiceService


@pytest.fixture
def parser():
    """Create parser instance."""
    return LightingCommandParser()


@pytest.fixture
def command_buffer():
    """Create command buffer instance."""
    return CommandBuffer(debounce_ms=100)  # Shorter for tests


@pytest.fixture
def voice_service():
    """Create voice service instance."""
    return VoiceService()


# ============================================================================
# Model Validation Tests
# ============================================================================


def test_lighting_intent_valid_color():
    """Test LightingIntent with valid color."""
    intent = LightingIntent(
        action="color",
        target="p1",
        color="#FF0000"
    )
    assert intent.color == "#FF0000"
    assert intent.action == "color"
    assert intent.target == "p1"


def test_lighting_intent_color_without_hash():
    """Test LightingIntent normalizes color to include hash."""
    intent = LightingIntent(
        action="color",
        target="p1",
        color="FF0000"
    )
    assert intent.color == "#FF0000"


def test_lighting_intent_invalid_color_length():
    """Test LightingIntent rejects invalid color length."""
    with pytest.raises(ValueError, match="Invalid hex color"):
        LightingIntent(
            action="color",
            target="p1",
            color="#FF00"  # Too short
        )


def test_lighting_intent_invalid_hex_chars():
    """Test LightingIntent rejects invalid hex characters."""
    with pytest.raises(ValueError, match="Invalid hex color"):
        LightingIntent(
            action="color",
            target="p1",
            color="#GGGGGG"  # Invalid hex
        )


def test_lighting_intent_target_normalization():
    """Test target normalization."""
    intent = LightingIntent(
        action="color",
        target="P1",  # Uppercase
        color="#FF0000"
    )
    assert intent.target == "p1"


def test_lighting_intent_invalid_target():
    """Test LightingIntent rejects invalid target."""
    with pytest.raises(ValueError, match="Invalid target"):
        LightingIntent(
            action="color",
            target="invalid",
            color="#FF0000"
        )


def test_lighting_intent_action_requires_color():
    """Test that color action requires color parameter."""
    with pytest.raises(ValueError, match="requires a color parameter"):
        LightingIntent(
            action="color",
            target="p1"
            # Missing color
        )


def test_color_mapping_get_hex():
    """Test ColorMapping hex lookup."""
    assert ColorMapping.get_hex("RED") == "#FF0000"
    assert ColorMapping.get_hex("blue") == "#0000FF"
    assert ColorMapping.get_hex("invalid") is None


# ============================================================================
# Parser Tests
# ============================================================================


@pytest.mark.asyncio
async def test_parse_light_color(parser):
    """Test 'light P1 red' pattern."""
    intent = await parser.parse("light player 1 red")

    assert intent is not None
    assert intent.action == "color"
    assert intent.target == "p1"
    assert intent.color == "#FF0000"
    assert intent.confidence > 0.8


@pytest.mark.asyncio
async def test_parse_light_color_variations(parser):
    """Test various color command formats."""
    variations = [
        ("light p1 red", "p1", "#FF0000"),
        ("set player 2 blue", "p2", "#0000FF"),
        ("light all green", "all", "#00FF00"),
    ]

    for transcript, expected_target, expected_color in variations:
        intent = await parser.parse(transcript)
        assert intent is not None
        assert intent.target == expected_target
        assert intent.color == expected_color


@pytest.mark.asyncio
async def test_parse_dim_all(parser):
    """Test 'dim all lights' pattern."""
    intent = await parser.parse("dim all lights")

    assert intent is not None
    assert intent.action == "dim"
    assert intent.target == "all"


@pytest.mark.asyncio
async def test_parse_dim_specific_player(parser):
    """Test 'dim p1' pattern."""
    intent = await parser.parse("dim player 2")

    assert intent is not None
    assert intent.action == "dim"
    assert intent.target == "p2"


@pytest.mark.asyncio
async def test_parse_flash_target(parser):
    """Test 'flash target 5' pattern."""
    intent = await parser.parse("flash target 5")

    assert intent is not None
    assert intent.action == "flash"
    assert intent.target == "5"
    assert intent.duration_ms == 500


@pytest.mark.asyncio
async def test_parse_flash_with_color(parser):
    """Test 'flash P2 green' pattern."""
    intent = await parser.parse("flash p2 green")

    assert intent is not None
    assert intent.action == "flash"
    assert intent.target == "p2"
    assert intent.color == "#00FF00"


@pytest.mark.asyncio
async def test_parse_turn_off(parser):
    """Test 'turn off lights' pattern."""
    intent = await parser.parse("turn off all lights")

    assert intent is not None
    assert intent.action == "off"
    assert intent.target == "all"
    assert intent.color == "#000000"


@pytest.mark.asyncio
async def test_parse_pattern_mode(parser):
    """Test 'rainbow mode' pattern."""
    intent = await parser.parse("rainbow mode")

    assert intent is not None
    assert intent.action == "pattern"
    assert intent.pattern == "rainbow"


@pytest.mark.asyncio
async def test_parse_invalid_pattern(parser):
    """Test invalid pattern name."""
    intent = await parser.parse("invalid pattern")

    # Should fail parsing
    assert intent is None


@pytest.mark.asyncio
async def test_parse_color_player_alternative(parser):
    """Test 'blue player 2' alternative order."""
    intent = await parser.parse("blue player 2")

    assert intent is not None
    assert intent.action == "color"
    assert intent.target == "p2"
    assert intent.color == "#0000FF"


@pytest.mark.asyncio
async def test_parse_invalid_color(parser):
    """Test handling of invalid color."""
    intent = await parser.parse("light P1 purpleish")

    # Should fail or return None
    assert intent is None


@pytest.mark.asyncio
async def test_parse_empty_transcript(parser):
    """Test empty transcript handling."""
    intent = await parser.parse("")

    assert intent is None


@pytest.mark.asyncio
async def test_parse_no_match(parser):
    """Test transcript with no matching pattern."""
    intent = await parser.parse("this is not a lighting command")

    assert intent is None


# ============================================================================
# Command Buffer Tests
# ============================================================================


@pytest.mark.asyncio
async def test_command_buffer_enqueue_success(command_buffer):
    """Test successful command enqueueing."""
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    result = await command_buffer.enqueue(intent, "user1")
    assert result is True


@pytest.mark.asyncio
async def test_command_buffer_rate_limiting(command_buffer):
    """Test rate limiting blocks rapid commands."""
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    # First command should succeed
    result1 = await command_buffer.enqueue(intent, "user1")
    assert result1 is True

    # Second command within rate limit should fail
    result2 = await command_buffer.enqueue(intent, "user1")
    assert result2 is False


@pytest.mark.asyncio
async def test_command_buffer_different_users(command_buffer):
    """Test rate limiting is per-user."""
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    # User1 command
    result1 = await command_buffer.enqueue(intent, "user1")
    assert result1 is True

    # User2 command should succeed (different user)
    result2 = await command_buffer.enqueue(intent, "user2")
    assert result2 is True


@pytest.mark.asyncio
async def test_command_buffer_batching(command_buffer):
    """Test command batching with debounce."""
    intents = [
        LightingIntent(action="dim", target="all", color="#222222"),
        LightingIntent(action="color", target="p1", color="#FF0000"),
        LightingIntent(action="color", target="p2", color="#00FF00"),
    ]

    # Enqueue all commands with different users to bypass rate limiting
    for i, intent in enumerate(intents):
        await command_buffer.enqueue(intent, f"user{i}")

    # Wait for debounce + processing
    await asyncio.sleep(0.2)

    # Queue should be empty after processing
    assert command_buffer.queue.empty()


# ============================================================================
# Service Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_voice_service_process_valid_command(voice_service):
    """Test processing valid lighting command."""
    updates = []

    async for update in voice_service.process_lighting_command("light p1 red", "user1"):
        updates.append(update)

    # Should have: parsing, parsed, applying, complete
    assert len(updates) >= 3

    # Check parsing status
    assert updates[0]["status"] == "parsing"

    # Check parsed status
    parsed_update = next((u for u in updates if u["status"] == "parsed"), None)
    assert parsed_update is not None
    assert parsed_update["intent"]["action"] == "color"
    assert parsed_update["intent"]["target"] == "p1"

    # Check complete status
    complete_update = next((u for u in updates if u["status"] == "complete"), None)
    assert complete_update is not None
    assert complete_update["success"] is True


@pytest.mark.asyncio
async def test_voice_service_process_invalid_command(voice_service):
    """Test processing invalid lighting command."""
    updates = []

    async for update in voice_service.process_lighting_command("this is not valid", "user1"):
        updates.append(update)

    # Should have error status
    error_update = next((u for u in updates if u["status"] == "error"), None)
    assert error_update is not None
    assert "Could not understand" in error_update["error"]


@pytest.mark.asyncio
async def test_voice_service_tts_response(voice_service):
    """Test TTS response generation."""
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    response = voice_service._generate_tts_response(intent, success=True)
    assert "p1" in response.lower()


@pytest.mark.asyncio
async def test_voice_service_hex_to_rgb(voice_service):
    """Test hex to RGB conversion."""
    rgb = voice_service._hex_to_rgb("#FF0000")
    assert rgb == (255, 0, 0)

    rgb = voice_service._hex_to_rgb("#00FF00")
    assert rgb == (0, 255, 0)


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_commands(voice_service):
    """Test handling concurrent commands."""
    tasks = []

    # Create 5 concurrent command tasks
    for i in range(5):
        task = asyncio.create_task(
            voice_service.process_lighting_command(f"light p{i % 4 + 1} red", f"user{i}")
        )
        tasks.append(task)

    # Wait for all to complete
    results = await asyncio.gather(*[
        asyncio.create_task(_collect_updates(task))
        for task in tasks
    ])

    # All should complete successfully
    assert len(results) == 5


async def _collect_updates(gen_task):
    """Helper to collect all updates from an async generator."""
    updates = []
    async for update in await gen_task:
        updates.append(update)
    return updates


@pytest.mark.asyncio
async def test_parser_fuzzy_color_matching(parser):
    """Test fuzzy color matching for common misspellings."""
    # Test fuzzy matches defined in parser
    intent = await parser.parse("light p1 blu")
    assert intent is not None
    assert intent.color == "#0000FF"  # Should match "blue"


@pytest.mark.asyncio
async def test_timeout_handling(voice_service):
    """Test handling of timeout scenarios."""
    # This is a placeholder - in production would test actual timeouts
    # For now, just ensure the service doesn't crash
    updates = []

    async for update in voice_service.process_lighting_command("light p1 red", "user1"):
        updates.append(update)

    assert len(updates) > 0


@pytest.mark.asyncio
async def test_low_confidence_handling(voice_service):
    """Test handling of low confidence parses."""
    # Mock a low confidence scenario by creating a custom parser
    class LowConfidenceParser:
        async def parse(self, transcript):
            if "maybe" in transcript:
                return LightingIntent(
                    action="color",
                    target="p1",
                    color="#FF0000",
                    confidence=0.6  # Low confidence
                )
            return None

    # Temporarily replace parser
    original_parser = voice_service.parser
    voice_service.parser = LowConfidenceParser()

    updates = []
    async for update in voice_service.process_lighting_command("maybe light p1 red", "user1"):
        updates.append(update)

    # Should have low_confidence status
    low_conf_update = next((u for u in updates if u.get("status") == "low_confidence"), None)
    assert low_conf_update is not None

    # Restore original parser
    voice_service.parser = original_parser


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.asyncio
async def test_parser_performance(parser):
    """Test parser performance with rapid parsing."""
    start_time = datetime.utcnow()

    # Parse 100 commands
    for i in range(100):
        await parser.parse(f"light p{i % 4 + 1} red")

    elapsed = (datetime.utcnow() - start_time).total_seconds()

    # Should complete in < 1 second
    assert elapsed < 1.0, f"Parsing took too long: {elapsed}s"


@pytest.mark.asyncio
async def test_command_buffer_throughput(command_buffer):
    """Test command buffer throughput."""
    intent = LightingIntent(action="color", target="p1", color="#FF0000")

    start_time = datetime.utcnow()

    # Enqueue 50 commands with different users to bypass rate limiting
    for i in range(50):
        await command_buffer.enqueue(intent, f"user{i}")

    elapsed = (datetime.utcnow() - start_time).total_seconds()

    # Should complete quickly
    assert elapsed < 0.5, f"Enqueueing took too long: {elapsed}s"
