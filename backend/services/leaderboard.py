"""
Leaderboard Service
Analyzes launch logs to determine "who's the best at what game"

Provides:
- Player leaderboards: "Who's #1 at Street Fighter?"
- Game rankings: "Show me Dad's top 10 games"
- House statistics: "Most played games"
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import defaultdict, Counter
import json
from datetime import datetime, timezone


class LeaderboardService:
    """Analyzes launch logs to build leaderboards."""
    
    def __init__(self, launches_file: Path):
        self.launches_file = launches_file
        self.launches = []
        self._load_launches()
    
    def _load_launches(self) -> None:
        """Load launch events from JSONL file."""
        if not self.launches_file.exists():
            return
        
        try:
            with open(self.launches_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.launches.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[Leaderboard] Error loading launches: {e}")
    
    def get_player_top_games(
        self,
        player_id: str,
        limit: int = 10,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get a player's most played games.
        
        Args:
            player_id: Profile ID (e.g., "dad")
            limit: Number of games to return
            platform: Optional platform filter
        
        Returns:
            List of games with play counts, sorted by frequency
        """
        # Filter launches for this player
        player_launches = [
            l for l in self.launches
            if l.get('player_id') == player_id and l.get('success')
        ]
        
        # Apply platform filter if specified
        if platform:
            player_launches = [
                l for l in player_launches
                if l.get('platform', '').lower() == platform.lower()
            ]
        
        # Count by game
        game_counts = Counter()
        game_info = {}
        
        for launch in player_launches:
            game_id = launch.get('game_id')
            if game_id:
                game_counts[game_id] += 1
                # Store game info (title, platform) from most recent launch
                if game_id not in game_info or launch.get('timestamp', '') > game_info[game_id].get('last_played', ''):
                    game_info[game_id] = {
                        'game_id': game_id,
                        'title': launch.get('title', 'Unknown'),
                        'platform': launch.get('platform', 'Unknown'),
                        'last_played': launch.get('timestamp', '')
                    }
        
        # Build result
        result = []
        for game_id, count in game_counts.most_common(limit):
            info = game_info.get(game_id, {})
            result.append({
                **info,
                'play_count': count,
                'player_id': player_id
            })
        
        return result
    
    def get_game_leaderboard(
        self,
        game_id: Optional[str] = None,
        game_title: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard for a specific game (who plays it most).
        
        Args:
            game_id: Exact game ID
            game_title: Game title (fuzzy match)
            limit: Number of players to return
        
        Returns:
            List of players with play counts, sorted by frequency
        """
        # Filter launches for this game
        if game_id:
            game_launches = [
                l for l in self.launches
                if l.get('game_id') == game_id and l.get('success')
            ]
        elif game_title:
            # Fuzzy match on title
            title_lower = game_title.lower()
            game_launches = [
                l for l in self.launches
                if title_lower in l.get('title', '').lower() and l.get('success')
            ]
        else:
            return []
        
        # Count by player
        player_counts = Counter()
        player_info = {}
        
        for launch in game_launches:
            player_id = launch.get('player_id')
            if player_id:
                player_counts[player_id] += 1
                # Store player info from most recent launch
                if player_id not in player_info or launch.get('timestamp', '') > player_info[player_id].get('last_played', ''):
                    player_info[player_id] = {
                        'player_id': player_id,
                        'player_name': launch.get('player_name', player_id),
                        'last_played': launch.get('timestamp', '')
                    }
        
        # Build result
        result = []
        for player_id, count in player_counts.most_common(limit):
            info = player_info.get(player_id, {})
            result.append({
                **info,
                'play_count': count,
                'rank': len(result) + 1
            })
        
        return result
    
    def get_house_stats(self) -> Dict[str, Any]:
        """
        Get overall house statistics.
        
        Returns:
            Dict with most played games, most active players, etc.
        """
        successful_launches = [l for l in self.launches if l.get('success')]
        
        # Most played games
        game_counts = Counter()
        game_info = {}
        for launch in successful_launches:
            game_id = launch.get('game_id')
            if game_id:
                game_counts[game_id] += 1
                if game_id not in game_info:
                    game_info[game_id] = {
                        'game_id': game_id,
                        'title': launch.get('title', 'Unknown'),
                        'platform': launch.get('platform', 'Unknown')
                    }
        
        most_played_games = [
            {**game_info.get(gid, {}), 'play_count': count}
            for gid, count in game_counts.most_common(10)
        ]
        
        # Most active players
        player_counts = Counter()
        player_info = {}
        for launch in successful_launches:
            player_id = launch.get('player_id')
            if player_id:
                player_counts[player_id] += 1
                if player_id not in player_info:
                    player_info[player_id] = {
                        'player_id': player_id,
                        'player_name': launch.get('player_name', player_id)
                    }
        
        most_active_players = [
            {**player_info.get(pid, {}), 'play_count': count}
            for pid, count in player_counts.most_common(10)
        ]
        
        # Platform breakdown
        platform_counts = Counter(l.get('platform', 'Unknown') for l in successful_launches)
        
        return {
            'total_launches': len(successful_launches),
            'unique_games': len(game_counts),
            'unique_players': len(player_counts),
            'most_played_games': most_played_games,
            'most_active_players': most_active_players,
            'platform_breakdown': dict(platform_counts.most_common()),
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    
    def get_player_vs_player(
        self,
        player1_id: str,
        player2_id: str,
        game_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare two players' play history.
        
        Args:
            player1_id: First player ID
            player2_id: Second player ID
            game_id: Optional game filter
        
        Returns:
            Comparison stats
        """
        p1_launches = [
            l for l in self.launches
            if l.get('player_id') == player1_id and l.get('success')
        ]
        p2_launches = [
            l for l in self.launches
            if l.get('player_id') == player2_id and l.get('success')
        ]
        
        if game_id:
            p1_launches = [l for l in p1_launches if l.get('game_id') == game_id]
            p2_launches = [l for l in p2_launches if l.get('game_id') == game_id]
        
        return {
            'player1': {
                'player_id': player1_id,
                'play_count': len(p1_launches)
            },
            'player2': {
                'player_id': player2_id,
                'play_count': len(p2_launches)
            },
            'leader': player1_id if len(p1_launches) > len(p2_launches) else player2_id,
            'game_id': game_id
        }


# Global instance (initialized by backend on startup)
_leaderboard_service: Optional[LeaderboardService] = None


def initialize_leaderboard_service(launches_file: Path) -> LeaderboardService:
    """Initialize the global leaderboard service."""
    global _leaderboard_service
    _leaderboard_service = LeaderboardService(launches_file)
    return _leaderboard_service


def get_leaderboard_service() -> Optional[LeaderboardService]:
    """Get the global leaderboard service instance."""
    return _leaderboard_service
