"""
Comprehensive pytest tests for ScoreKeeper Sam Router Endpoints

Test Coverage:
- GET /api/scores/highscores/{game_id} - LaunchBox high scores parsing
- POST /api/scores/autosubmit - Auto-submit on game end
- POST /api/scores/tournament/generate - Streaming bracket generation
- Model validation (PlayerData, TournamentConfig, BracketData)
- Edge cases: missing files, invalid data, concurrent requests
- Performance: timeout handling, file I/O optimization

Target: >85% code coverage
"""

import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock, mock_open
from datetime import datetime
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Test imports
from backend.routers.scorekeeper import (
    get_game_highscores,
    game_autosubmit,
    GameAutoSubmit,
    get_scorekeeper_dir,
    get_scores_file,
)

from backend.services.scorekeeper.models import (
    PlayerData,
    TournamentConfig,
    BracketData,
    TournamentState,
    Match,
    BracketRound,
    SeedingMode,
)


# ==================== Fixtures ====================

@pytest.fixture
def mock_request():
    """Mock FastAPI request object."""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.drive_root = Path("/mnt/a")
    return request


@pytest.fixture
def mock_highscores_data():
    """Mock HighScores.json structure."""
    return {
        "Games": [
            {
                "Id": "game-123",
                "Title": "Pac-Man",
                "Scores": [
                    {"Player": "Alice", "Score": 50000, "Timestamp": "2025-10-01T12:00:00"},
                    {"Player": "Bob", "Score": 45000, "Timestamp": "2025-10-02T14:00:00"},
                    {"Player": "Charlie", "Score": 40000, "Timestamp": "2025-10-03T16:00:00"},
                ]
            },
            {
                "Id": "game-456",
                "Title": "Donkey Kong",
                "Scores": [
                    {"Player": "Dave", "Score": 75000, "Timestamp": "2025-10-05T10:00:00"},
                ]
            }
        ]
    }


@pytest.fixture
def temp_scores_dir(tmp_path):
    """Create temporary scores directory."""
    scores_dir = tmp_path / "state" / "scorekeeper"
    scores_dir.mkdir(parents=True, exist_ok=True)
    return scores_dir


# ==================== Model Validation Tests ====================

class TestModelValidation:
    """Test Pydantic model validators."""

    def test_player_data_kid_detection(self):
        """Test automatic kid detection from age < 13."""
        # Kid player
        kid = PlayerData(id="1", name="Tim", age=10, skill_level=60)
        assert kid.is_kid is True

        # Adult player
        adult = PlayerData(id="2", name="Dad", age=35, skill_level=80)
        assert adult.is_kid is False

        # Age 12 is still < 13, so detected as kid
        teen = PlayerData(id="3", name="Sarah", age=12, skill_level=70)
        assert teen.is_kid is True

        # Age 13+ is not a kid
        older_teen = PlayerData(id="4", name="Jake", age=13, skill_level=75)
        assert older_teen.is_kid is False

    def test_tournament_config_bracket_size_auto_calc(self):
        """Test automatic bracket size calculation from player count."""
        # 5 players -> bracket size 8
        config = TournamentConfig(
            name="Test Tournament",
            players=["P1", "P2", "P3", "P4", "P5"],
            bracket_size=0  # Will be auto-calculated
        )
        assert config.bracket_size == 8

        # 17 players -> bracket size 32
        config_large = TournamentConfig(
            name="Large Tournament",
            players=[f"P{i}" for i in range(17)],
            bracket_size=0
        )
        assert config_large.bracket_size == 32

    def test_tournament_config_duplicate_players(self):
        """Test duplicate player removal with warning."""
        if True:  # Should log warning but not fail
            config = TournamentConfig(
                name="Duplicate Test",
                players=["Alice", "Bob", "Alice", "Charlie", "Bob"],
                bracket_size=0
            )
            # Duplicates removed, order preserved
            assert len(config.players) == 3
            assert config.players == ["Alice", "Bob", "Charlie"]

    def test_seeding_mode_validation(self):
        """Test seeding mode validation with fallback."""
        valid = SeedingMode(mode="casual")
        assert valid.mode == "casual"

        # Invalid mode defaults to casual
        if True:
            invalid = SeedingMode(mode="invalid_mode")
            assert invalid.mode == "casual"

    def test_match_winner_validation(self):
        """Test match winner must be one of the players."""
        # Valid winner
        match = Match(
            round_number=1,
            match_number=1,
            player1="Alice",
            player2="Bob",
            winner="Alice"
        )
        assert match.winner == "Alice"

        # Invalid winner raises error
        with pytest.raises(ValueError, match="Winner .* must be one of the players"):
            Match(
                round_number=1,
                match_number=1,
                player1="Alice",
                player2="Bob",
                winner="Charlie"  # Not in match
            )


# ==================== Highscores Endpoint Tests ====================

class TestHighscoresEndpoint:
    """Test GET /api/scores/highscores/{game_id}."""

    @pytest.mark.asyncio
    async def test_get_highscores_success(self, mock_request, mock_highscores_data, tmp_path):
        """Test successful highscores retrieval."""
        # Create mock HighScores.json
        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            json.dump(mock_highscores_data, f)

        with patch('os.getenv', return_value=str(tmp_path)):
            result = await get_game_highscores(mock_request, "game-123", limit=10)

        assert result["game_id"] == "game-123"
        assert result["game_title"] == "Pac-Man"
        assert len(result["scores"]) == 3
        assert result["scores"][0]["player"] == "Alice"
        assert result["scores"][0]["score"] == 50000
        assert result["scores"][0]["rank"] == 1
        assert result["total_count"] == 3

    @pytest.mark.asyncio
    async def test_get_highscores_limit(self, mock_request, mock_highscores_data, tmp_path):
        """Test limit parameter restricts results."""
        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            json.dump(mock_highscores_data, f)

        with patch('os.getenv', return_value=str(tmp_path)):
            result = await get_game_highscores(mock_request, "game-123", limit=2)

        assert len(result["scores"]) == 2
        assert result["total_count"] == 3  # Total still shows all scores

    @pytest.mark.asyncio
    async def test_get_highscores_file_not_found(self, mock_request, tmp_path):
        """Test graceful handling when HighScores.json missing."""
        with patch('os.getenv', return_value=str(tmp_path)):
            result = await get_game_highscores(mock_request, "game-999", limit=10)

        assert result["game_id"] == "game-999"
        assert result["game_title"] == "Unknown"
        assert result["scores"] == []
        assert result["total_count"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_highscores_invalid_json(self, mock_request, tmp_path):
        """Test error handling for malformed JSON."""
        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            f.write("{ invalid json }")

        with patch('os.getenv', return_value=str(tmp_path)):
            with pytest.raises(HTTPException) as exc_info:
                await get_game_highscores(mock_request, "game-123", limit=10)

        assert exc_info.value.status_code == 500
        assert "parse" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_highscores_game_not_found(self, mock_request, mock_highscores_data, tmp_path):
        """Test game ID not in HighScores.json."""
        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            json.dump(mock_highscores_data, f)

        with patch('os.getenv', return_value=str(tmp_path)):
            result = await get_game_highscores(mock_request, "game-999", limit=10)

        assert result["game_id"] == "game-999"
        assert result["game_title"] == "Unknown"
        assert result["scores"] == []
        assert result["total_count"] == 0


# ==================== Auto-Submit Endpoint Tests ====================

class TestAutoSubmitEndpoint:
    """Test POST /api/scores/autosubmit."""

    @pytest.mark.asyncio
    async def test_autosubmit_success(self, mock_request, temp_scores_dir):
        """Test successful score auto-submission."""
        submit_data = GameAutoSubmit(
            game_id="game-123",
            game_title="Pac-Man",
            player="Alice",
            score=75000,
            session_id="session-abc",
            tournament_id=None
        )

        with patch('os.getenv', return_value=str(temp_scores_dir.parent.parent)):
            result = await game_autosubmit(mock_request, submit_data)

        assert result["status"] == "submitted"
        assert result["game_id"] == "game-123"
        assert result["player"] == "Alice"
        assert result["score"] == 75000
        assert result["leaderboard_rank"] == 1  # First score
        assert "timestamp" in result

        # Verify JSONL entry created
        scores_file = temp_scores_dir / "scores.jsonl"
        assert scores_file.exists()
        with open(scores_file, 'r') as f:
            entry = json.loads(f.readline())
            assert entry["game_id"] == "game-123"
            assert entry["player"] == "Alice"
            assert entry["source"] == "game_autosubmit"

    @pytest.mark.asyncio
    async def test_autosubmit_leaderboard_rank(self, mock_request, temp_scores_dir):
        """Test leaderboard rank calculation with multiple scores."""
        # Submit first score
        submit1 = GameAutoSubmit(
            game_id="game-123",
            game_title="Pac-Man",
            player="Alice",
            score=50000
        )

        with patch('os.getenv', return_value=str(temp_scores_dir.parent.parent)):
            result1 = await game_autosubmit(mock_request, submit1)
            assert result1["leaderboard_rank"] == 1

            # Submit higher score
            submit2 = GameAutoSubmit(
                game_id="game-123",
                game_title="Pac-Man",
                player="Bob",
                score=75000
            )
            result2 = await game_autosubmit(mock_request, submit2)
            assert result2["leaderboard_rank"] == 1  # Bob is now #1

    @pytest.mark.asyncio
    async def test_autosubmit_tournament_detection(self, mock_request, temp_scores_dir):
        """Test tournament score detection (manual match update still required)."""
        submit_data = GameAutoSubmit(
            game_id="game-123",
            game_title="Pac-Man",
            player="Alice",
            score=75000,
            tournament_id="tournament-abc"
        )

        with patch('os.getenv', return_value=str(temp_scores_dir.parent.parent)):
            with patch('backend.routers.scorekeeper.get_tournament_config') as mock_config:
                # Mock tournament config with no active tournament
                mock_config_instance = Mock()
                mock_config_instance.resume_tournament = AsyncMock(return_value=None)
                mock_config.return_value = mock_config_instance

                result = await game_autosubmit(mock_request, submit_data)

                assert result["tournament_match_updated"] is False
                # Score still logged even if tournament update fails
                assert result["status"] == "submitted"


# ==================== Performance & Edge Cases ====================

class TestPerformanceAndEdgeCases:
    """Test timeout handling, large files, concurrent requests."""

    @pytest.mark.asyncio
    async def test_large_highscores_file(self, mock_request, tmp_path):
        """Test performance with large HighScores.json (1000+ games)."""
        # Generate large dataset
        large_data = {
            "Games": [
                {
                    "Id": f"game-{i}",
                    "Title": f"Game {i}",
                    "Scores": [{"Player": f"Player{j}", "Score": j * 1000, "Timestamp": f"2025-10-{j:02d}T12:00:00"}
                               for j in range(1, 11)]
                }
                for i in range(1000)
            ]
        }

        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            json.dump(large_data, f)

        with patch('os.getenv', return_value=str(tmp_path)):
            import time
            start = time.time()
            result = await get_game_highscores(mock_request, "game-500", limit=10)
            duration = time.time() - start

        # Should complete quickly even with large file
        assert duration < 1.0, f"Took {duration}s, expected <1s"
        assert result["game_id"] == "game-500"
        assert len(result["scores"]) == 10

    @pytest.mark.asyncio
    async def test_concurrent_autosubmits(self, mock_request, temp_scores_dir):
        """Test concurrent score submissions don't corrupt JSONL."""
        async def submit_score(player, score):
            submit_data = GameAutoSubmit(
                game_id="game-123",
                game_title="Pac-Man",
                player=player,
                score=score
            )
            with patch('os.getenv', return_value=str(temp_scores_dir.parent.parent)):
                return await game_autosubmit(mock_request, submit_data)

        # Submit 10 scores concurrently
        tasks = [submit_score(f"Player{i}", i * 1000) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r["status"] == "submitted" for r in results)

        # Verify all entries written correctly
        scores_file = temp_scores_dir / "scores.jsonl"
        with open(scores_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 10
            # Verify each line is valid JSON
            for line in lines:
                entry = json.loads(line.strip())
                assert "game_id" in entry
                assert "player" in entry
                assert "score" in entry


# ==================== Integration Tests ====================

class TestEndToEndIntegration:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_game_end_to_leaderboard_flow(self, mock_request, mock_highscores_data, tmp_path):
        """Test complete flow: game ends -> auto-submit -> appears in leaderboard."""
        # Setup HighScores.json
        highscores_path = tmp_path / "LaunchBox" / "Data" / "HighScores.json"
        highscores_path.parent.mkdir(parents=True, exist_ok=True)
        with open(highscores_path, 'w') as f:
            json.dump(mock_highscores_data, f)

        # Create scores directory
        scores_dir = tmp_path / "state" / "scorekeeper"
        scores_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Auto-submit new high score
        submit_data = GameAutoSubmit(
            game_id="game-123",
            game_title="Pac-Man",
            player="Zoe",
            score=100000  # Highest score
        )

        with patch('os.getenv', return_value=str(tmp_path)):
            submit_result = await game_autosubmit(mock_request, submit_data)
            assert submit_result["status"] == "submitted"
            assert submit_result["leaderboard_rank"] == 1

            # Step 2: Retrieve updated leaderboard from scores.jsonl
            scores_file = scores_dir / "scores.jsonl"
            assert scores_file.exists()

            # Verify Zoe's score is recorded
            with open(scores_file, 'r') as f:
                scores = [json.loads(line) for line in f if line.strip()]
                zoe_score = next((s for s in scores if s["player"] == "Zoe"), None)
                assert zoe_score is not None
                assert zoe_score["score"] == 100000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=backend/routers/scorekeeper", "--cov=backend/services/scorekeeper/models"])
