"""
LaunchBox Plugin Client
Communicates with the C# LaunchBox plugin via HTTP (localhost:9999 by default)

Optimizations:
- Connection pooling with requests.Session for connection reuse
- Reduced timeout to 2 seconds for faster failure detection
- Single retry logic for transient network failures
- Health check caching to reduce redundant calls
"""

import requests
import os
import logging
import time
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

# Module-level plugin connection settings (env-overridable)
# Evidence-aligned defaults: host 127.0.0.1, port 9999
PLUGIN_PORT = int(os.getenv("LB_PLUGIN_PORT", "9999"))
PLUGIN_HOST = os.getenv("LB_PLUGIN_HOST", "127.0.0.1")
PLUGIN_BASE = f"http://{PLUGIN_HOST}:{PLUGIN_PORT}"


class HealthStatus(Enum):
    """Enum for plugin health status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)  # frozen for hashability and immutability
class Game:
    """Immutable game data structure for better memory efficiency."""
    id: str
    title: str
    platform: str
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    release_date: str = ""
    application_path: str = ""


class LaunchBoxPluginError(Exception):
    """Base exception for LaunchBox plugin errors."""
    pass


class LaunchBoxPluginClient:
    """
    Optimized client for communicating with the LaunchBox C# plugin.

    Key optimizations:
    - Connection pooling via session reuse
    - Reduced timeout for faster failure detection
    - Retry logic for transient failures
    - Health check caching with TTL
    """

    # Constants for improved maintainability
    # Allow override via environment variable LB_PLUGIN_PORT; fallback to 9999
    DEFAULT_PORT = int(os.getenv("LB_PLUGIN_PORT", str(PLUGIN_PORT)))
    DEFAULT_TIMEOUT = 2  # Reduced from 5 to 2 seconds
    RETRY_COUNT = 1  # Single retry for transient failures
    HEALTH_CACHE_TTL = 30  # Cache health check for 30 seconds

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        """
        Initialize plugin client.

        Args:
            base_url: Override base URL (defaults to http://127.0.0.1:9999)
            timeout: Override timeout in seconds (defaults to 2)
        """
        self.base_url = base_url or PLUGIN_BASE
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Session with connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'LaunchBoxPlugin/1.0',
            'Accept': 'application/json',
            'Connection': 'keep-alive'  # Explicit keep-alive
        })

        # Health check caching
        self._health_cache: Optional[Dict[str, Any]] = None
        self._health_cache_time: float = 0

        logger.info(f"Plugin client initialized: {self.base_url} (timeout={self.timeout}s)")

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with single retry for transient failures.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            LaunchBoxPluginError: On persistent failure
        """
        last_error = None

        for attempt in range(self.RETRY_COUNT + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=self.timeout,
                    **kwargs
                )
                response.raise_for_status()
                return response

            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < self.RETRY_COUNT:
                    logger.debug(f"Request timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(0.1)  # Brief delay before retry

            except requests.exceptions.RequestException as e:
                last_error = e
                break  # Don't retry on non-timeout errors

        raise LaunchBoxPluginError(f"Request failed after {attempt + 1} attempts: {last_error}")

    def health_check(self) -> bool:
        """
        Check if the plugin is running and responding.

        Uses cached result if available and fresh.

        Returns:
            True if plugin is healthy, False otherwise
        """
        # Check cache validity
        now = time.time()
        if (self._health_cache is not None and
            (now - self._health_cache_time) < self.HEALTH_CACHE_TTL):
            return self._health_cache.get("available", False)

        try:
            response = self._request_with_retry("GET", f"{self.base_url}/health")
            data = response.json()

            # Cache the raw data
            self._health_cache = data
            self._health_cache_time = now

            # Determine availability in a backward-compatible way
            # Prefer explicit 'available' flag if provided; otherwise treat status=='ok' as available
            explicit = data.get("available")
            if isinstance(explicit, bool):
                is_available = explicit
            else:
                is_available = (data.get("status") == "ok")

            version = data.get("version", "unknown")
            logger.info(f"Plugin health check: available={is_available}, version={version}")
            return is_available

        except (LaunchBoxPluginError, ValueError) as e:
            logger.warning(f"Plugin health check failed: {e}")
            # Cache negative result for shorter duration
            self._health_cache = {"available": False}
            self._health_cache_time = now - (self.HEALTH_CACHE_TTL - 5)  # Cache for 5 seconds
            return False

    def get_health(self) -> Optional[Dict[str, Any]]:
        """
        Return cached health JSON from plugin or None on failure.

        Returns:
            Health status dict or None
        """
        if self.health_check():
            return self._health_cache
        return None

    def search_games(self, title: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search for games by title with efficient result limiting.

        Args:
            title: Game title or partial title to search for
            limit: Maximum number of results (capped at 50)

        Returns:
            List of game dictionaries

        Raises:
            LaunchBoxPluginError: On search failure
        """
        # Validate and cap limit for performance
        limit = min(limit, 50)

        try:
            response = self._request_with_retry(
                "GET",
                f"{self.base_url}/search-game",
                params={"title": title, "limit": limit}  # Pass limit to server
            )

            games = response.json()

            # Ensure we don't return more than requested
            if len(games) > limit:
                games = games[:limit]

            logger.info(f"Found {len(games)} games matching '{title}'")
            return games

        except LaunchBoxPluginError:
            raise
        except Exception as e:
            logger.error(f"Unexpected search error: {e}")
            raise LaunchBoxPluginError(f"Search failed: {e}")

    def launch_game(self, game_id: str) -> Dict[str, Any]:
        """
        Launch a game by its LaunchBox ID using new plugin API.

        Args:
            game_id: LaunchBox game ID (UUID string)

        Returns:
            Dictionary with 'launched' boolean and optional 'message' string
        """
        # Validate UUID format (basic check for performance)
        if not game_id or len(game_id) < 32:
            return {
                "launched": False,
                "success": False,  # Backward compatibility
                "message": "Invalid game ID format"
            }

        try:
            # Preferred API: POST /launch-game with { "GameId": "uuid" }
            response = self._request_with_retry(
                "POST",
                f"{self.base_url}/launch-game",
                json={"GameId": game_id},
                headers={"Content-Type": "application/json"}
            )
            result = response.json()

            # Normalize legacy shape to include 'launched'
            if "launched" not in result:
                result["launched"] = bool(result.get("success", False))

            if result.get("launched") or result.get("success"):
                logger.info(f"Game launched successfully: {game_id}")
                return result

            # If the endpoint exists but returns failure, bubble it up
            logger.warning(f"Plugin /launch-game returned failure: {result}")
            return result

        except LaunchBoxPluginError as e:
            # Attempt legacy alias /launch with { "id": "uuid" }
            logger.warning(f"/launch-game failed ({e}); trying legacy /launch endpoint")
            try:
                legacy = self._request_with_retry(
                    "POST",
                    f"{self.base_url}/launch",
                    json={"id": game_id},
                    headers={"Content-Type": "application/json"}
                )
                result = legacy.json()
                if "launched" not in result:
                    result["launched"] = bool(result.get("success", False))
                return result
            except LaunchBoxPluginError as ee:
                logger.error(f"Plugin launch error: {ee}")
                return {
                    "launched": False,
                    "success": False,
                    "message": f"Plugin error: {str(ee)}"
                }
        except Exception as e:
            logger.error(f"Unexpected launch error: {e}")
            return {
                "launched": False,
                "success": False,
                "message": f"Unexpected error: {str(e)}"
            }

    def list_platforms(self) -> List[str]:
        """
        Get all unique platforms in the LaunchBox library.

        Returns:
            List of platform names (empty list on failure)
        """
        try:
            response = self._request_with_retry("GET", f"{self.base_url}/list-platforms")
            platforms = response.json()

            # Ensure it's a list
            if not isinstance(platforms, list):
                logger.warning("Invalid platforms response format")
                return []

            logger.info(f"Retrieved {len(platforms)} platforms")
            return platforms

        except (LaunchBoxPluginError, ValueError) as e:
            logger.error(f"Failed to retrieve platforms: {e}")
            return []

    def list_genres(self) -> List[str]:
        """
        Get all unique genres in the LaunchBox library.

        Returns:
            List of genre names (empty list on failure)
        """
        try:
            response = self._request_with_retry("GET", f"{self.base_url}/list-genres")
            genres = response.json()

            # Ensure it's a list
            if not isinstance(genres, list):
                logger.warning("Invalid genres response format")
                return []

            logger.info(f"Retrieved {len(genres)} genres")
            return genres

        except (LaunchBoxPluginError, ValueError) as e:
            logger.error(f"Failed to retrieve genres: {e}")
            return []

    def is_available(self) -> bool:
        """
        Check if the plugin is available (cached).

        Returns:
            True if plugin is available, False otherwise
        """
        return self.health_check()

    def close(self):
        """Close the HTTP session and clear cache."""
        self._health_cache = None
        self._health_cache_time = 0
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Ensure session is closed on garbage collection."""
        try:
            self.close()
        except:
            pass  # Ignore errors during cleanup

    # -------------------- Import Helpers --------------------
    def list_missing(self, platform: str, folder: str) -> Dict[str, Any]:
        """List files in folder not yet in LaunchBox for given platform via plugin.

        Returns summary dict with keys: platform, folder, missing (list), counts.
        """
        try:
            resp = self._request_with_retry(
                "GET", f"{self.base_url}/import/missing", params={"platform": platform, "folder": folder}
            )
            return resp.json()
        except LaunchBoxPluginError:
            raise
        except Exception as e:
            raise LaunchBoxPluginError(f"List missing failed: {e}")

    def import_missing(self, platform: str, folder: str) -> Dict[str, Any]:
        """Import missing files as LaunchBox entries via plugin."""
        try:
            resp = self._request_with_retry(
                "POST", f"{self.base_url}/import/apply", json={"platform": platform, "folder": folder}
            )
            return resp.json()
        except LaunchBoxPluginError:
            raise
        except Exception as e:
            raise LaunchBoxPluginError(f"Import missing failed: {e}")


# Singleton instance with lazy initialization
_plugin_client: Optional[LaunchBoxPluginClient] = None


def get_plugin_client() -> LaunchBoxPluginClient:
    """
    Get singleton plugin client instance with lazy initialization.

    Returns:
        Shared LaunchBoxPluginClient instance
    """
    global _plugin_client
    if _plugin_client is None:
        _plugin_client = LaunchBoxPluginClient()
    return _plugin_client


def reset_plugin_client() -> None:
    """
    Reset the singleton client (useful for testing or configuration changes).
    """
    global _plugin_client
    if _plugin_client:
        _plugin_client.close()
        _plugin_client = None
