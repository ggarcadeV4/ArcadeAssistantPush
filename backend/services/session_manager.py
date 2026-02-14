"""
Session Manager Service
Tracks active gaming sessions with player rosters and session ownership.

Used by:
- Vicky Voice: Create sessions with player rosters
- ScoreKeeper Sam: Track who's playing, address session owner
- LaunchBox LoRa: Log launches to active session
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
import json
import uuid


class Session:
    """Represents an active gaming session."""
    
    def __init__(
        self,
        session_id: str,
        owner_id: str,
        owner_name: str,
        players: List[Dict[str, str]],
        created_at: Optional[str] = None
    ):
        self.session_id = session_id
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.players = players  # [{"id": "dad", "name": "Dad", "position": 1}, ...]
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.last_activity = datetime.now(timezone.utc).isoformat()
        self.games_played = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "players": self.players,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "games_played": self.games_played
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Deserialize session from dictionary."""
        session = cls(
            session_id=data["session_id"],
            owner_id=data["owner_id"],
            owner_name=data["owner_name"],
            players=data["players"],
            created_at=data.get("created_at")
        )
        session.last_activity = data.get("last_activity", session.last_activity)
        session.games_played = data.get("games_played", [])
        return session
    
    def add_game(self, game_id: str, game_title: str) -> None:
        """Record a game played in this session."""
        self.games_played.append({
            "game_id": game_id,
            "title": game_title,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.last_activity = datetime.now(timezone.utc).isoformat()
    
    def get_player_by_id(self, player_id: str) -> Optional[Dict[str, str]]:
        """Get player info by ID."""
        return next((p for p in self.players if p.get("id") == player_id), None)


class SessionManager:
    """Manages active gaming sessions."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.sessions_file = state_dir / "sessions.json"
        self.active_sessions: Dict[str, Session] = {}
        self._load_sessions()
    
    def _load_sessions(self) -> None:
        """Load sessions from disk."""
        if not self.sessions_file.exists():
            return
        
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for session_data in data.get("sessions", []):
                    session = Session.from_dict(session_data)
                    self.active_sessions[session.session_id] = session
        except Exception as e:
            print(f"[SessionManager] Error loading sessions: {e}")
    
    def _save_sessions(self) -> None:
        """Save sessions to disk."""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "sessions": [s.to_dict() for s in self.active_sessions.values()],
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SessionManager] Error saving sessions: {e}")
    
    def create_session(
        self,
        owner_id: str,
        owner_name: str,
        players: List[Dict[str, str]],
        session_id: Optional[str] = None
    ) -> Session:
        """
        Create a new gaming session.
        
        Args:
            owner_id: Profile ID of session owner (e.g., "dad")
            owner_name: Display name of owner (e.g., "Dad")
            players: List of player dicts [{"id": "dad", "name": "Dad", "position": 1}, ...]
            session_id: Optional custom session ID
        
        Returns:
            Created Session object
        """
        session_id = session_id or str(uuid.uuid4())
        session = Session(session_id, owner_id, owner_name, players)
        self.active_sessions[session_id] = session
        self._save_sessions()
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self.active_sessions.get(session_id)
    
    def get_active_session_for_player(self, player_id: str) -> Optional[Session]:
        """Get the most recent active session for a player."""
        player_sessions = [
            s for s in self.active_sessions.values()
            if any(p.get("id") == player_id for p in s.players)
        ]
        if not player_sessions:
            return None
        # Return most recently active
        return max(player_sessions, key=lambda s: s.last_activity)
    
    def end_session(self, session_id: str) -> bool:
        """End a session and remove it from active sessions."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            self._save_sessions()
            return True
        return False
    
    def log_game_to_session(
        self,
        session_id: str,
        game_id: str,
        game_title: str
    ) -> bool:
        """Log a game played to a session."""
        session = self.get_session(session_id)
        if session:
            session.add_game(game_id, game_title)
            self._save_sessions()
            return True
        return False
    
    def get_all_active_sessions(self) -> List[Session]:
        """Get all active sessions."""
        return list(self.active_sessions.values())
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours. Returns count removed."""
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        to_remove = []
        
        for session_id, session in self.active_sessions.items():
            last_active = datetime.fromisoformat(session.last_activity.replace('Z', '+00:00'))
            if last_active < cutoff:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del self.active_sessions[session_id]
        
        if to_remove:
            self._save_sessions()
        
        return len(to_remove)


# Global instance (initialized by backend on startup)
_session_manager: Optional[SessionManager] = None


def initialize_session_manager(state_dir: Path) -> SessionManager:
    """Initialize the global session manager."""
    global _session_manager
    _session_manager = SessionManager(state_dir)
    return _session_manager


def get_session_manager() -> Optional[SessionManager]:
    """Get the global session manager instance."""
    return _session_manager
