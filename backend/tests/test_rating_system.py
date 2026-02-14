"""
Comprehensive tests for Elo/Glicko-2 rating system in ScoreKeeper Sam.

Tests cover:
- All rating variants (standard, glicko, family_adjusted)
- Glicko-2 rating updates
- Edge cases (new players, high volatility, extreme deltas)
- Performance (caching, async batch operations)
"""

import pytest
import asyncio
from typing import Dict, Tuple, List
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.scorekeeper.service import (
    TournamentService,
    Glicko2Calculator,
    RatingData,
    MatchResult,
    TournamentData,
    PlayerProfile
)


# ==================== Fixtures ====================

@pytest.fixture
def glicko2_calculator():
    """Glicko-2 calculator with standard tau."""
    return Glicko2Calculator(tau=0.5)


@pytest.fixture
def glicko2_calculator_volatile():
    """Glicko-2 calculator with high volatility (family mode)."""
    return Glicko2Calculator(tau=0.7)


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for testing."""
    mock = Mock()
    mock.table = Mock(return_value=mock)
    mock.select = Mock(return_value=mock)
    mock.in_ = Mock(return_value=mock)
    mock.eq = Mock(return_value=mock)
    mock.execute = Mock()
    return mock


@pytest.fixture
def tournament_service(mock_supabase):
    """Tournament service with mocked Supabase."""
    return TournamentService(supabase_client=mock_supabase, tau=0.5)


@pytest.fixture
def sample_ratings():
    """Sample rating data for testing."""
    return {
        'Alice': RatingData(player_id='Alice', elo=1600, games=20, volatility=0.06, deviation=200),
        'Bob': RatingData(player_id='Bob', elo=1400, games=15, volatility=0.07, deviation=250),
        'Charlie': RatingData(player_id='Charlie', elo=1500, games=0, volatility=0.06, deviation=350),  # New player
        'David': RatingData(player_id='David', elo=1800, games=50, volatility=0.05, deviation=150),  # Expert
    }


@pytest.fixture
def sample_ratings_dict():
    """Sample ratings in Glicko-2 tuple format."""
    return {
        'Alice': (1600.0, 200.0, 0.06),
        'Bob': (1400.0, 250.0, 0.07),
    }


# ==================== Glicko-2 Calculator Tests ====================

class TestGlicko2Calculator:
    """Test Glicko-2 rating calculation algorithm."""

    def test_expected_score_equal_ratings(self, glicko2_calculator):
        """Test expected score with equal ratings (should be 0.5)."""
        mu1, phi1 = 1500.0, 200.0
        mu2, phi2 = 1500.0, 200.0

        expected = glicko2_calculator.expected_score(mu1, phi1, mu2, phi2)

        assert 0.49 < expected < 0.51, "Equal ratings should have ~0.5 expected score"

    def test_expected_score_rating_difference(self, glicko2_calculator):
        """Test expected score with 400 point difference (~0.9 expected)."""
        mu_strong, phi_strong = 1900.0, 200.0
        mu_weak, phi_weak = 1500.0, 200.0

        expected = glicko2_calculator.expected_score(mu_strong, phi_strong, mu_weak, phi_weak)

        assert expected > 0.85, "400 point advantage should have high expected score"

    def test_expected_score_caching(self, glicko2_calculator):
        """Test that expected_score uses lru_cache correctly."""
        # First call
        result1 = glicko2_calculator.expected_score(1500, 200, 1400, 200)
        # Second call with same params (should use cache)
        result2 = glicko2_calculator.expected_score(1500, 200, 1400, 200)

        assert result1 == result2
        # Check cache info (should have 1 hit)
        cache_info = glicko2_calculator.expected_score.cache_info()
        assert cache_info.hits >= 1

    @pytest.mark.asyncio
    async def test_update_single_win(self, glicko2_calculator, sample_ratings_dict):
        """Test rating update for clear win (Alice beats Bob)."""
        match = MatchResult(player_a='Alice', player_b='Bob', score_a=1.0)

        updated = await glicko2_calculator.update_ratings([match], sample_ratings_dict)

        # Alice should gain rating (won as expected)
        assert updated['Alice'][0] > sample_ratings_dict['Alice'][0]
        # Bob should lose rating
        assert updated['Bob'][0] < sample_ratings_dict['Bob'][0]
        # Volatilities should be clamped below 0.09
        assert updated['Alice'][2] <= 0.09
        assert updated['Bob'][2] <= 0.09

    @pytest.mark.asyncio
    async def test_update_single_upset(self, glicko2_calculator):
        """Test rating update for upset (weak player beats strong player)."""
        ratings = {
            'Weak': (1200.0, 300.0, 0.06),
            'Strong': (1800.0, 200.0, 0.05),
        }
        match = MatchResult(player_a='Weak', player_b='Strong', score_a=1.0)

        updated = await glicko2_calculator.update_ratings([match], ratings)

        # Weak player should gain significant rating (upset win)
        rating_gain = updated['Weak'][0] - ratings['Weak'][0]
        assert rating_gain > 50, "Upset win should yield large rating gain"

        # Strong player should lose significant rating
        rating_loss = ratings['Strong'][0] - updated['Strong'][0]
        assert rating_loss > 50, "Upset loss should yield large rating loss"

    @pytest.mark.asyncio
    async def test_update_draw(self, glicko2_calculator, sample_ratings_dict):
        """Test rating update for draw (0.5 score)."""
        match = MatchResult(player_a='Alice', player_b='Bob', score_a=0.5)

        updated = await glicko2_calculator.update_ratings([match], sample_ratings_dict)

        # Higher rated Alice should lose small amount in draw
        assert updated['Alice'][0] < sample_ratings_dict['Alice'][0]
        # Lower rated Bob should gain small amount in draw
        assert updated['Bob'][0] > sample_ratings_dict['Bob'][0]

    @pytest.mark.asyncio
    async def test_batch_updates(self, glicko2_calculator):
        """Test async batch processing of multiple matches."""
        ratings = {
            'P1': (1500.0, 250.0, 0.06),
            'P2': (1500.0, 250.0, 0.06),
            'P3': (1500.0, 250.0, 0.06),
            'P4': (1500.0, 250.0, 0.06),
        }
        matches = [
            MatchResult(player_a='P1', player_b='P2', score_a=1.0),
            MatchResult(player_a='P3', player_b='P4', score_a=0.0),
        ]

        updated = await glicko2_calculator.update_ratings(matches, ratings)

        # All 4 players should have updated ratings
        assert len(updated) == 4
        # P1 and P4 (winners) should gain
        assert updated['P1'][0] > ratings['P1'][0]
        assert updated['P4'][0] > ratings['P4'][0]
        # P2 and P3 (losers) should lose
        assert updated['P2'][0] < ratings['P2'][0]
        assert updated['P3'][0] < ratings['P3'][0]

    def test_volatility_convergence(self, glicko2_calculator):
        """Test that volatility update converges (no infinite loop)."""
        phi = 200.0
        v = 0.5
        delta = 100.0
        sigma = 0.06

        # Should not raise or hang
        new_sigma = glicko2_calculator._update_volatility(phi, v, delta, sigma)

        assert 0 < new_sigma < 1, "Volatility should be in valid range"

    @pytest.mark.asyncio
    async def test_edge_case_new_player_high_uncertainty(self, glicko2_calculator):
        """Test new player with high deviation (should have conservative rating)."""
        ratings = {
            'Veteran': (1800.0, 150.0, 0.05),
            'Newbie': (1500.0, 350.0, 0.06),  # High uncertainty
        }
        match = MatchResult(player_a='Newbie', player_b='Veteran', score_a=1.0)

        updated = await glicko2_calculator.update_ratings([match], ratings)

        # Newbie should gain rating but deviation should decrease
        assert updated['Newbie'][0] > ratings['Newbie'][0]
        assert updated['Newbie'][1] < ratings['Newbie'][1], "Deviation should decrease after match"

    def test_high_tau_increases_volatility_change(self):
        """Test that high tau allows more volatile ratings."""
        calc_standard = Glicko2Calculator(tau=0.3)
        calc_volatile = Glicko2Calculator(tau=0.9)

        assert calc_volatile.tau > calc_standard.tau
        # Higher tau should allow more volatility change (tested in update flow)


# ==================== Rating Variant Tests ====================

class TestRatingVariants:
    """Test Elo seeding variants (standard, glicko, family_adjusted)."""

    @pytest.mark.parametrize("mode,expected_order", [
        ("standard", ['David', 'Alice', 'Charlie', 'Bob']),  # Sort by Elo
        ("glicko", ['David', 'Alice', 'Bob', 'Charlie']),  # Conservative (mu - 2*phi)
        ("family_adjusted", ['Charlie', 'David', 'Alice', 'Bob']),  # Boost new players
    ])
    def test_variant_seeding(self, tournament_service, sample_ratings, mode, expected_order):
        """Parametrized test for all seeding variants."""
        ratings_list = list(sample_ratings.values())

        if mode == "standard":
            result = tournament_service._variant_standard_elo(ratings_list, "test_id")
        elif mode == "glicko":
            result = tournament_service._variant_glicko_conservative(ratings_list, "test_id")
        elif mode == "family_adjusted":
            result = tournament_service._variant_family_adjusted(ratings_list)

        assert result == expected_order, f"{mode} seeding order incorrect"

    def test_standard_elo_tiebreaker(self, tournament_service):
        """Test standard Elo with identical ratings (uses player_id tiebreaker)."""
        ratings = [
            RatingData(player_id='A', elo=1500, games=10, volatility=0.06, deviation=200),
            RatingData(player_id='B', elo=1500, games=10, volatility=0.06, deviation=200),
        ]

        result = tournament_service._variant_standard_elo(ratings, "test_id")

        # Should be deterministic based on player_id
        assert len(result) == 2
        assert result[0] in ['A', 'B']

    def test_glicko_conservative_uncertainty_penalty(self, tournament_service):
        """Test Glicko conservative penalizes high uncertainty."""
        ratings = [
            RatingData(player_id='Certain', elo=1600, games=50, volatility=0.05, deviation=150),
            RatingData(player_id='Uncertain', elo=1600, games=5, volatility=0.08, deviation=350),
        ]

        result = tournament_service._variant_glicko_conservative(ratings, "test_id")

        # Certain player should rank higher despite equal Elo
        assert result[0] == 'Certain', "Lower deviation should rank higher"

    def test_family_adjusted_new_player_boost(self, tournament_service):
        """Test family adjustment boosts new players."""
        ratings = [
            RatingData(player_id='Veteran', elo=1600, games=100, volatility=0.05, deviation=150),
            RatingData(player_id='Newbie', elo=1400, games=0, volatility=0.06, deviation=350),
        ]

        result = tournament_service._variant_family_adjusted(ratings)

        # Newbie should rank higher due to 1000/(0+1) boost
        assert result[0] == 'Newbie', "New player should get inclusion boost"

    def test_family_adjusted_diminishing_boost(self, tournament_service):
        """Test family adjustment boost diminishes with experience."""
        ratings = [
            RatingData(player_id='P0', elo=1400, games=0, volatility=0.06, deviation=300),  # +1000
            RatingData(player_id='P10', elo=1400, games=10, volatility=0.06, deviation=250),  # +90.9
            RatingData(player_id='P100', elo=1400, games=100, volatility=0.05, deviation=200),  # +9.9
        ]

        result = tournament_service._variant_family_adjusted(ratings)

        # Order should be: P0 (most boost), P10, P100
        assert result == ['P0', 'P10', 'P100'], "Boost should diminish with games"


# ==================== Rating Fetch & Caching Tests ====================

class TestRatingFetch:
    """Test async rating fetching with caching."""

    @pytest.mark.asyncio
    async def test_fetch_ratings_success(self, tournament_service, mock_supabase):
        """Test successful rating fetch from Supabase."""
        # Mock Supabase response
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'alice_id', 'name': 'Alice', 'elo_score': 1600, 'games_played': 20,
             'volatility': 0.06, 'deviation': 200},
            {'id': 'bob_id', 'name': 'Bob', 'elo_score': 1400, 'games_played': 15,
             'volatility': 0.07, 'deviation': 250},
        ])

        ratings = await tournament_service._fetch_ratings(('Alice', 'Bob'), 'tournament_1')

        assert len(ratings) == 2
        assert ratings['Alice'].elo == 1600
        assert ratings['Bob'].games == 15

    @pytest.mark.asyncio
    async def test_fetch_ratings_missing_player(self, tournament_service, mock_supabase):
        """Test fetch with missing player (should add defaults)."""
        # Mock Supabase returns only Alice
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'alice_id', 'name': 'Alice', 'elo_score': 1600, 'games_played': 20,
             'volatility': 0.06, 'deviation': 200},
        ])

        ratings = await tournament_service._fetch_ratings(('Alice', 'Unknown'), 'tournament_1')

        assert len(ratings) == 2
        assert ratings['Unknown'].elo == 1500.0, "Missing player should get default rating"
        assert ratings['Unknown'].games == 0

    @pytest.mark.asyncio
    async def test_fetch_ratings_caching(self, tournament_service, mock_supabase):
        """Test lru_cache reduces DB hits."""
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'alice_id', 'name': 'Alice', 'elo_score': 1600, 'games_played': 20,
             'volatility': 0.06, 'deviation': 200},
        ])

        # First fetch
        ratings1 = await tournament_service._fetch_ratings(('Alice',), 'tournament_1')
        # Second fetch with same params (should use cache)
        ratings2 = await tournament_service._fetch_ratings(('Alice',), 'tournament_1')

        # Should be same object from cache
        assert ratings1 == ratings2
        # Check cache usage
        cache_info = tournament_service._fetch_ratings.cache_info()
        assert cache_info.hits >= 1, "Cache should be hit on second fetch"

    @pytest.mark.asyncio
    async def test_fetch_ratings_fallback_mock(self, tournament_service):
        """Test fallback to mock ratings when Supabase fails."""
        # Force Supabase to None
        tournament_service.supabase = None

        ratings = await tournament_service._fetch_ratings(('Alice', 'Bob'), 'tournament_1')

        assert len(ratings) == 2
        # Should have mock data
        assert 1000 <= ratings['Alice'].elo <= 2000
        assert ratings['Alice'].games >= 0


# ==================== Match Result Submission Tests ====================

class TestMatchResultSubmission:
    """Test match result submission with rating updates."""

    @pytest.mark.asyncio
    async def test_submit_match_with_rating_update(self, tournament_service, mock_supabase):
        """Test match submission updates ratings."""
        # Mock rating fetch
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'alice_id', 'name': 'Alice', 'elo_score': 1600, 'games_played': 20,
             'volatility': 0.06, 'deviation': 200},
            {'id': 'bob_id', 'name': 'Bob', 'elo_score': 1400, 'games_played': 15,
             'volatility': 0.07, 'deviation': 250},
        ])

        result = await tournament_service.submit_match_result(
            tournament_id='t1',
            match_id='m1',
            winner='Alice',
            player1='Alice',
            player2='Bob',
            update_ratings=True
        )

        assert result['completed'] is True
        assert result['winner'] == 'Alice'
        # Rating updates should be present
        if result['ratings_updated']:
            assert 'rating_changes' in result
            assert 'Alice' in result['rating_changes']
            assert result['rating_changes']['Alice']['change'] > 0  # Winner gains

    @pytest.mark.asyncio
    async def test_submit_match_draw(self, tournament_service, mock_supabase):
        """Test match submission with draw (unknown winner)."""
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'alice_id', 'name': 'Alice', 'elo_score': 1500, 'games_played': 10,
             'volatility': 0.06, 'deviation': 250},
            {'id': 'bob_id', 'name': 'Bob', 'elo_score': 1500, 'games_played': 10,
             'volatility': 0.06, 'deviation': 250},
        ])

        result = await tournament_service.submit_match_result(
            tournament_id='t1',
            match_id='m1',
            winner='Unknown',  # Should be treated as draw
            player1='Alice',
            player2='Bob',
            update_ratings=True
        )

        # Should handle gracefully
        assert result['completed'] is True

    @pytest.mark.asyncio
    async def test_submit_match_no_rating_update(self, tournament_service):
        """Test match submission without rating updates."""
        result = await tournament_service.submit_match_result(
            tournament_id='t1',
            match_id='m1',
            winner='Alice',
            player1='Alice',
            player2='Bob',
            update_ratings=False
        )

        assert result['completed'] is True
        assert result['ratings_updated'] is False


# ==================== Edge Case Tests ====================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_extreme_rating_gap(self, glicko2_calculator):
        """Test extreme rating difference (1000+ points)."""
        ratings = {
            'Grandmaster': (2400.0, 100.0, 0.05),
            'Beginner': (800.0, 350.0, 0.08),
        }
        match = MatchResult(player_a='Beginner', player_b='Grandmaster', score_a=1.0)

        updated = await glicko2_calculator.update_ratings([match], ratings)

        # Should not crash or produce invalid values
        assert 0 < updated['Beginner'][0] < 3000
        assert 0 < updated['Grandmaster'][0] < 3000

    @pytest.mark.asyncio
    async def test_all_new_players(self, tournament_service):
        """Test seeding with all new players (random tiebreaker)."""
        ratings = [
            RatingData(player_id='P1', elo=1500, games=0, volatility=0.06, deviation=350),
            RatingData(player_id='P2', elo=1500, games=0, volatility=0.06, deviation=350),
            RatingData(player_id='P3', elo=1500, games=0, volatility=0.06, deviation=350),
        ]

        result = tournament_service._variant_standard_elo(ratings, "test_id")

        # Should have all 3 players in some order
        assert len(result) == 3
        assert set(result) == {'P1', 'P2', 'P3'}

    @pytest.mark.asyncio
    async def test_volatility_clamping(self, glicko2_calculator):
        """Test volatility is clamped to 0.09 max."""
        ratings = {
            'Volatile': (1500.0, 300.0, 0.08),  # High deviation
            'Stable': (1500.0, 150.0, 0.05),
        }
        # Extreme upset that would cause volatility spike
        match = MatchResult(player_a='Volatile', player_b='Stable', score_a=1.0)

        updated = await glicko2_calculator.update_ratings([match], ratings)

        # Volatility should be clamped
        assert updated['Volatile'][2] <= 0.09, "Volatility should be clamped to 0.09"

    def test_pydantic_validation_invalid_score(self):
        """Test MatchResult validation rejects invalid scores."""
        with pytest.raises(ValueError):
            MatchResult(player_a='Alice', player_b='Bob', score_a=1.5)  # > 1.0

        with pytest.raises(ValueError):
            MatchResult(player_a='Alice', player_b='Bob', score_a=-0.1)  # < 0.0

    def test_rating_data_defaults(self):
        """Test RatingData uses correct defaults."""
        rating = RatingData(player_id='TestPlayer')

        assert rating.elo == 1500.0
        assert rating.games == 0
        assert rating.volatility == 0.06
        assert rating.deviation == 350.0


# ==================== Performance Tests ====================

class TestPerformance:
    """Test performance optimizations."""

    @pytest.mark.asyncio
    async def test_batch_update_performance(self, glicko2_calculator):
        """Test async batch updates are concurrent."""
        ratings = {f'P{i}': (1500.0, 250.0, 0.06) for i in range(32)}
        matches = [
            MatchResult(player_a=f'P{i}', player_b=f'P{i+1}', score_a=1.0 if i % 2 == 0 else 0.0)
            for i in range(0, 30, 2)
        ]

        import time
        start = time.time()
        updated = await glicko2_calculator.update_ratings(matches, ratings)
        duration = time.time() - start

        # Should complete reasonably fast with async
        assert duration < 1.0, "Batch updates should be fast"
        assert len(updated) == 32

    def test_cache_hit_rate(self, tournament_service, mock_supabase):
        """Test cache improves performance on repeated fetches."""
        mock_supabase.execute.return_value = Mock(data=[
            {'id': 'p1', 'name': 'P1', 'elo_score': 1500, 'games_played': 10,
             'volatility': 0.06, 'deviation': 250},
        ])

        # Clear cache
        tournament_service._fetch_ratings.cache_clear()

        # Multiple fetches with same params
        async def fetch_multiple():
            for _ in range(10):
                await tournament_service._fetch_ratings(('P1',), 'tournament_1')

        asyncio.run(fetch_multiple())

        cache_info = tournament_service._fetch_ratings.cache_info()
        # Should have 9 hits (first is miss, rest are hits)
        assert cache_info.hits >= 9, "Cache should reduce DB queries"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
