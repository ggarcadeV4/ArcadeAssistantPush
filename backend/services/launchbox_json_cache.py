"""
LaunchBox JSON Cache Loader

Provides fast game data access by loading from pre-built JSON cache
instead of parsing XML files at runtime.

Usage:
    from backend.services.launchbox_json_cache import json_cache
    games = json_cache.get_all_games()
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class LaunchBoxJSONCache:
    """
    JSON-based game cache for fast startup and queries.
    
    Falls back to XML parser if JSON cache is unavailable.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._games: List[Dict[str, Any]] = []
        self._games_by_id: Dict[str, Dict[str, Any]] = {}
        self._platforms: List[str] = []
        self._genres: List[str] = []
        self._metadata: Dict[str, Any] = {}
        self._loaded = False
        self._initialized = True
    
    def _get_cache_path(self) -> Path:
        """Get path to JSON cache file. No CWD fallback per Slice 2 contract."""
        from backend.constants.drive_root import get_drive_root
        try:
            aa_drive_root = str(get_drive_root(allow_cwd_fallback=False))
        except Exception:
            # Return sentinel that will fail to load cache (not a silent CWD)
            aa_drive_root = "<AA_DRIVE_ROOT_NOT_SET>"
        return Path(aa_drive_root) / '.aa' / 'launchbox_games.json'
    
    def _ensure_loaded(self) -> None:
        """Load cache from disk if not already loaded."""
        if self._loaded:
            return
        
        with self._lock:
            if self._loaded:
                return
            
            cache_path = self._get_cache_path()
            
            if not cache_path.exists():
                logger.warning(f"JSON cache not found at {cache_path}, falling back to parser")
                self._load_from_parser()
                return
            
            try:
                logger.info(f"Loading JSON cache from {cache_path}...")
                start = datetime.now()
                
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._metadata = data.get('metadata', {})
                self._platforms = data.get('platforms', [])
                self._genres = data.get('genres', [])
                self._games = data.get('games', [])
                
                # Build ID lookup index
                self._games_by_id = {g['id']: g for g in self._games if g.get('id')}
                
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(
                    f"✅ JSON cache loaded: {len(self._games)} games, "
                    f"{len(self._platforms)} platforms in {elapsed:.2f}s"
                )
                self._loaded = True
                
            except Exception as e:
                logger.error(f"Failed to load JSON cache: {e}, falling back to parser")
                self._load_from_parser()
    
    def _load_from_parser(self) -> None:
        """Fallback: load data from XML parser."""
        try:
            from backend.services.launchbox_parser import parser
            parser.initialize()
            
            games = parser.get_all_games()
            self._games = [self._serialize_game(g) for g in games]
            self._games_by_id = {g['id']: g for g in self._games if g.get('id')}
            self._platforms = parser.get_platforms()
            self._genres = parser.get_genres()
            self._loaded = True
            
            logger.info(f"Loaded {len(self._games)} games from XML parser (fallback)")
            
        except Exception as e:
            logger.error(f"Parser fallback also failed: {e}")
            self._games = []
            self._games_by_id = {}
            self._platforms = []
            self._genres = []
            self._loaded = True
    
    def _serialize_game(self, game) -> Dict[str, Any]:
        """Serialize a Game model to dict."""
        return {
            'id': game.id,
            'title': game.title,
            'sort_title': (game.title or '').lower(),
            'platform': game.platform,
            'year': game.year,
            'genre': game.genre,
            'developer': game.developer,
            'publisher': game.publisher,
            'region': game.region,
            'clear_logo_path': game.clear_logo_path,
            'box_front_path': game.box_front_path,
            'screenshot_path': game.screenshot_path,
            'rom_path': game.rom_path,
            'application_path': game.application_path,
            'emulator_id': game.emulator_id,
            'categories': game.categories or [],
        }
    
    def get_all_games(self) -> List[Dict[str, Any]]:
        """Get all games from cache."""
        self._ensure_loaded()
        return self._games
    
    def get_game_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get single game by ID."""
        self._ensure_loaded()
        return self._games_by_id.get(game_id)
    
    def get_platforms(self) -> List[str]:
        """Get list of all platforms."""
        self._ensure_loaded()
        return self._platforms
    
    def get_genres(self) -> List[str]:
        """Get list of all genres."""
        self._ensure_loaded()
        return self._genres
    
    def filter_games(
        self,
        platform: Optional[str] = None,
        genre: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Filter games by criteria.
        
        Args:
            platform: Filter by platform name
            genre: Filter by genre name
            search: Search in title (case-insensitive)
            limit: Maximum results
        
        Returns:
            Filtered list of games
        """
        self._ensure_loaded()
        
        results = self._games
        
        if platform and platform.lower() != 'all':
            results = [g for g in results if g.get('platform') == platform]
        
        if genre and genre.lower() != 'all':
            results = [g for g in results if g.get('genre') == genre]
        
        if search:
            search_lower = search.lower()
            results = [g for g in results if search_lower in (g.get('title') or '').lower()]
        
        return results[:limit]
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        self._ensure_loaded()
        return {
            'total_games': len(self._games),
            'platforms_count': len(self._platforms),
            'genres_count': len(self._genres),
            'cache_version': self._metadata.get('version', 'unknown'),
            'generated_at': self._metadata.get('generated_at'),
            'source': 'json_cache' if self._metadata else 'parser_fallback',
        }
    
    def reload(self) -> None:
        """Force reload cache from disk."""
        with self._lock:
            self._loaded = False
            self._games = []
            self._games_by_id = {}
            self._platforms = []
            self._genres = []
            self._metadata = {}
        self._ensure_loaded()


# Singleton instance
json_cache = LaunchBoxJSONCache()
