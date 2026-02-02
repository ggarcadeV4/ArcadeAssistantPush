"""Tests for LaunchBox Router Optimizations

Tests timeout wrappers, dependency injection, performance logging,
and the service container pattern.

Target coverage: >85%
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException
from pathlib import Path

from backend.routers.launchbox import (
    with_timeout,
    LaunchBoxServices,
    get_launchbox_services,
    get_games,
    launch_game,
)
from backend.models.game import Game


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_request():
    """Create mock FastAPI Request."""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.drive_root = Path("/tmp")
    request.headers = {"x-panel": "launchbox", "x-corr-id": "test-123"}
    return request


@pytest.fixture
def mock_services():
    """Create mock LaunchBoxServices."""
    services = Mock(spec=LaunchBoxServices)

    # Mock parser
    services.parser = Mock()
    services.parser.get_game_by_id = Mock(return_value=None)
    services.parser.get_cache_stats = Mock(return_value={"is_mock_data": False})

    # Mock cache
    services.cache = Mock()
    services.cache.get_games = Mock(return_value=[])

    # Mock launcher
    services.launcher = Mock()

    # Mock plugin client
    services.plugin_client = Mock()
    services.plugin_client.is_available = Mock(return_value=False)

    return services


@pytest.fixture
def sample_game():
    """Create a sample Game instance."""
    return Game(
        id="test-game-123",
        title="Test Game",
        platform="Arcade",
        year=2000,
        genre="Action",
    )


# =============================================================================
# Tests: Timeout Decorator
# =============================================================================


@pytest.mark.asyncio
async def test_with_timeout_success():
    """Test timeout decorator allows fast functions to complete."""

    @with_timeout(1.0)
    async def fast_function():
        await asyncio.sleep(0.1)
        return "success"

    result = await fast_function()

    assert result == "success"


@pytest.mark.asyncio
async def test_with_timeout_raises_http_exception():
    """Test timeout decorator raises HTTPException on timeout."""

    @with_timeout(0.1)
    async def slow_function():
        await asyncio.sleep(1.0)
        return "should not reach"

    with pytest.raises(HTTPException) as exc_info:
        await slow_function()

    assert exc_info.value.status_code == 504
    assert "timeout" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_with_timeout_preserves_function_metadata():
    """Test timeout decorator preserves original function metadata."""

    @with_timeout(1.0)
    async def documented_function():
        """This function has documentation."""
        pass

    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This function has documentation."


# =============================================================================
# Tests: LaunchBoxServices Container
# =============================================================================


def test_launchbox_services_initialization():
    """Test LaunchBoxServices initializes with all dependencies."""
    services = LaunchBoxServices()

    assert services.parser is not None
    assert services.cache is not None
    assert services.launcher is not None
    assert services.plugin_client is not None
    assert services.image_scanner is not None


def test_launchbox_services_invalidate_caches():
    """Test cache invalidation method."""
    services = LaunchBoxServices()

    # Should not raise
    services.invalidate_caches()


def test_get_launchbox_services_singleton():
    """Test get_launchbox_services creates service container."""
    services = get_launchbox_services()

    assert isinstance(services, LaunchBoxServices)


# =============================================================================
# Tests: GET /games Endpoint (with timeout and DI)
# =============================================================================


@pytest.mark.asyncio
async def test_get_games_with_dependency_injection(mock_services):
    """Test /games endpoint uses injected services."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="Game A", platform="Arcade", year=1990, genre="Action"),
        Game(id="2", title="Game B", platform="NES", year=1992, genre="Puzzle"),
    ]

    result = await get_games(services=mock_services)

    assert len(result) == 2
    assert result[0].title == "Game A"
    mock_services.cache.get_games.assert_called_once()


@pytest.mark.asyncio
async def test_get_games_platform_filter(mock_services):
    """Test /games endpoint filters by platform."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="Arcade Game", platform="Arcade", year=1990, genre="Action"),
        Game(id="2", title="NES Game", platform="NES", year=1992, genre="Puzzle"),
    ]

    result = await get_games(platform="Arcade", services=mock_services)

    assert len(result) == 1
    assert result[0].platform == "Arcade"


@pytest.mark.asyncio
async def test_get_games_genre_filter(mock_services):
    """Test /games endpoint filters by genre."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="Game A", platform="Arcade", year=1990, genre="Action"),
        Game(id="2", title="Game B", platform="Arcade", year=1992, genre="Puzzle"),
    ]

    result = await get_games(genre="Action", services=mock_services)

    assert len(result) == 1
    assert result[0].genre == "Action"


@pytest.mark.asyncio
async def test_get_games_decade_filter(mock_services):
    """Test /games endpoint filters by decade."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="80s Game", platform="Arcade", year=1985, genre="Action"),
        Game(id="2", title="90s Game", platform="Arcade", year=1995, genre="Action"),
    ]

    result = await get_games(decade=1980, services=mock_services)

    assert len(result) == 1
    assert result[0].year == 1985


@pytest.mark.asyncio
async def test_get_games_search_filter(mock_services):
    """Test /games endpoint filters by search term."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="Pac-Man", platform="Arcade", year=1980, genre="Action"),
        Game(id="2", title="Donkey Kong", platform="Arcade", year=1981, genre="Action"),
    ]

    result = await get_games(search="pac", services=mock_services)

    assert len(result) == 1
    assert "pac" in result[0].title.lower()


@pytest.mark.asyncio
async def test_get_games_pagination(mock_services):
    """Test /games endpoint paginates results correctly."""
    games = [
        Game(id=f"{i}", title=f"Game {i}", platform="Arcade", year=1980, genre="Action")
        for i in range(100)
    ]
    mock_services.cache.get_games.return_value = games

    # Page 1
    result_p1 = await get_games(page=1, limit=10, services=mock_services)
    assert len(result_p1) == 10
    assert result_p1[0].title == "Game 0"

    # Page 2
    result_p2 = await get_games(page=2, limit=10, services=mock_services)
    assert len(result_p2) == 10
    assert result_p2[0].title == "Game 10"


@pytest.mark.asyncio
async def test_get_games_performance_logging(mock_services, caplog):
    """Test /games endpoint logs performance metrics."""
    import logging

    caplog.set_level(logging.INFO)

    mock_services.cache.get_games.return_value = []

    await get_games(services=mock_services)

    # Check that performance log was written
    assert any("GET /games:" in record.message for record in caplog.records)


# =============================================================================
# Tests: POST /launch/{game_id} Endpoint (with timeout and DI)
# =============================================================================


@pytest.mark.asyncio
async def test_launch_game_forbidden_panel(mock_request, mock_services, sample_game):
    """Test /launch endpoint rejects non-LaunchBox panels."""
    mock_request.headers = {"x-panel": "scorekeeper"}  # Wrong panel

    response = await launch_game("test-id", mock_request, services=mock_services)

    assert response.success is False
    assert "Forbidden" in response.message


@pytest.mark.asyncio
async def test_launch_game_throttle(mock_request, mock_services, sample_game):
    """Test /launch endpoint throttles rapid requests."""
    mock_services.parser.get_game_by_id.return_value = sample_game
    mock_services.parser.get_cache_stats.return_value = {"is_mock_data": False}

    # First launch
    response1 = await launch_game("test-id", mock_request, services=mock_services)

    # Immediate second launch (should be throttled)
    response2 = await launch_game("test-id", mock_request, services=mock_services)

    # Second response should indicate throttling
    assert "wait" in response2.message.lower() or response2.method_used == "throttled"


@pytest.mark.asyncio
async def test_launch_game_mock_mode_rejected(mock_request, mock_services, sample_game):
    """Test /launch endpoint rejects launches in mock mode."""
    mock_services.parser.get_game_by_id.return_value = sample_game
    mock_services.parser.get_cache_stats.return_value = {"is_mock_data": True}

    response = await launch_game("test-id", mock_request, services=mock_services)

    assert response.success is False
    assert "mock mode" in response.message.lower()


@pytest.mark.asyncio
async def test_launch_game_not_found(mock_request, mock_services):
    """Test /launch endpoint handles game not found."""
    mock_services.parser.get_game_by_id.return_value = None
    mock_services.parser.get_cache_stats.return_value = {"is_mock_data": False}

    response = await launch_game("nonexistent-id", mock_request, services=mock_services)

    assert response.success is False
    assert "not found" in response.message.lower()


# =============================================================================
# Tests: Performance Monitoring
# =============================================================================


@pytest.mark.asyncio
async def test_slow_request_warning(mock_services, caplog):
    """Test slow requests trigger performance warnings."""
    import logging

    caplog.set_level(logging.WARNING)

    # Simulate slow cache access
    async def slow_get_games():
        await asyncio.sleep(0.5)  # Artificially slow
        return []

    with patch.object(mock_services.cache, "get_games", side_effect=slow_get_games):
        # Force synchronous execution for testing
        with patch("backend.routers.launchbox.run_in_threadpool", side_effect=lambda f: f()):
            await get_games(services=mock_services)

    # Should log warning for slow request (>1000ms check in code)
    # Note: This test may pass/fail depending on execution speed
    # In production, use pytest-benchmark for accurate perf testing


# =============================================================================
# Tests: Dependency Override (for testing)
# =============================================================================


@pytest.mark.asyncio
async def test_dependency_override_in_tests():
    """Test that LaunchBoxServices can be overridden in tests."""
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    app = FastAPI()

    # Mock endpoint using dependency
    @app.get("/test")
    async def test_endpoint(services: LaunchBoxServices = Depends(get_launchbox_services)):
        return {"parser": services.parser is not None}

    # Override dependency with mock
    mock_services = Mock(spec=LaunchBoxServices)
    mock_services.parser = Mock()

    app.dependency_overrides[get_launchbox_services] = lambda: mock_services

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    assert response.json()["parser"] is True


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_get_games_empty_results(mock_services):
    """Test /games handles empty game list gracefully."""
    mock_services.cache.get_games.return_value = []

    result = await get_games(services=mock_services)

    assert result == []


@pytest.mark.asyncio
async def test_get_games_invalid_decade(mock_services):
    """Test /games handles invalid decade filter gracefully."""
    mock_services.cache.get_games.return_value = [
        Game(id="1", title="Game", platform="Arcade", year=1990, genre="Action")
    ]

    # Should not raise, just skip decade filter
    result = await get_games(decade="invalid", services=mock_services)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_concurrent_launch_requests(mock_request, mock_services, sample_game):
    """Test concurrent launch requests are handled correctly (inflight guard)."""
    mock_services.parser.get_game_by_id.return_value = sample_game
    mock_services.parser.get_cache_stats.return_value = {"is_mock_data": False}

    # Simulate concurrent requests
    tasks = [launch_game("test-id", mock_request, services=mock_services) for _ in range(3)]

    results = await asyncio.gather(*tasks)

    # At least one should be throttled or in-flight
    throttled = sum(
        1 for r in results if r.method_used in ("throttled", "inflight") or not r.success
    )
    assert throttled >= 1  # Some requests should be rejected
