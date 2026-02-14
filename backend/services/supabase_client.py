"""
Supabase client for Arcade Assistant cloud operations.

Provides a production-ready interface to Supabase for:
- Device registration and heartbeat
- Telemetry logging
- Command queue management
- Tournament/score tracking

Optimizations:
- Singleton pattern with lazy initialization
- Connection pooling via supabase-py
- Automatic retry with exponential backoff
- Efficient batch operations
- Comprehensive error handling and logging
- Type hints for all operations

Environment Variables:
- SUPABASE_URL: Supabase project URL (required)
- SUPABASE_ANON_KEY: Anonymous/public API key (required)
- SUPABASE_SERVICE_KEY: Service role key (optional, for admin ops)
"""

import os
from pathlib import Path
import logging
import json
import shutil
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from functools import wraps, lru_cache
from threading import Lock

# Import supabase client
try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

# Configure module logger
logger = logging.getLogger(__name__)


# Type definitions for better code clarity
@dataclass
class TelemetryEntry:
    """Telemetry log entry structure (unified schema)."""
    cabinet_id: str
    level: str  # 'INFO', 'WARN', 'ERROR', 'CRITICAL'
    code: str
    message: str
    payload: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Supabase insert."""
        # Maps to 'cabinet_telemetry' schema
        return {
            'cabinet_id': self.cabinet_id,  # Changed from device_id
            'level': self.level,
            # 'code': self.code, # Not in schema, put in payload
            'message': self.message,
            'payload': {
                **(self.payload or {}),
                'code': self.code,
                'tenant_id': os.getenv('AA_TENANT_ID', 'default')
            },
            'panel': 'system', # Default panel
            'occurred_at': self.timestamp or datetime.now(timezone.utc).isoformat(), # Schema requires occurred_at
        }


@dataclass
class ScoreEntry:
    """High score entry structure (unified schema).
    
    Matches the cabinet_game_score table in Supabase.
    See supabase/README.md for the full data contract.
    
    Note: Supabase table uses:
      - cabinet_id (not device_id)
      - achieved_at (not created_at)
      - game_id is UUID type (we generate one from text if needed)
    """
    cabinet_id: str
    game_id: str
    player: str
    score: int
    game_title: Optional[str] = None  # Human-readable game name
    source: Optional[str] = None  # 'mame_hiscore', 'retroachievements', 'manual'
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        # Handle game_id - Supabase expects UUID, but we may have text
        # Generate deterministic UUID from game_id string if not already UUID
        import uuid as uuid_mod
        game_id_val = self.game_id
        try:
            # Try parsing as UUID first
            uuid_mod.UUID(self.game_id)
        except (ValueError, AttributeError):
            # Generate deterministic UUID from string (using namespace)
            game_id_val = str(uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, self.game_id or "unknown"))
        
        result = {
            'cabinet_id': self.cabinet_id,  # Supabase uses cabinet_id, not device_id
            'game_id': game_id_val,
            'player': self.player,
            'score': self.score,
            'achieved_at': datetime.now(timezone.utc).isoformat(),  # Supabase uses achieved_at
        }
        # Add optional fields if provided
        if self.game_title:
            result['game_title'] = self.game_title
        if self.source:
            result['source'] = self.source
        # Note: 'meta' column does not exist in cabinet_game_score table
        # If meta support is needed later, add column via migration first
        return result


class SupabaseError(Exception):
    """Base exception for Supabase operations."""
    pass


def retry_on_failure(max_attempts: int = 3, backoff_factor: float = 1.0):
    """
    Decorator for automatic retry with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_factor * (2 ** attempt)
                        logger.debug(f"Retry {attempt + 1}/{max_attempts} after {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        logger.warning(f"All {max_attempts} attempts failed for {func.__name__}: {e}")

            # Return None or False based on return type hints
            return_type = func.__annotations__.get('return')
            if return_type and 'bool' in str(return_type):
                return False
            return None

        return wrapper
    return decorator


class SupabaseClient:
    """
    Production-ready Supabase client with optimized operations.

    Implements singleton pattern with lazy initialization for
    efficient resource usage and connection pooling.
    """

    # Class-level constants
    HEARTBEAT_INTERVAL = 300  # 5 minutes in seconds
    TELEMETRY_BATCH_SIZE = 100  # Max records per batch insert
    COMMAND_POLL_INTERVAL = 30  # Check for new commands every 30 seconds

    def __init__(self, url: Optional[str] = None, anon_key: Optional[str] = None):
        """
        Initialize Supabase client with credentials.

        Args:
            url: Supabase project URL (or from env SUPABASE_URL)
            anon_key: Anonymous API key (or from env SUPABASE_ANON_KEY)

        Raises:
            SupabaseError: If Supabase library not installed or credentials missing
        """
        if not SUPABASE_AVAILABLE:
            raise SupabaseError("supabase-py not installed. Run: pip install supabase")

        # Get credentials from env or parameters
        self.url = url or os.getenv('SUPABASE_URL')
        self.anon_key = anon_key or os.getenv('SUPABASE_ANON_KEY')
        # Optional service key for admin operations (and fallback for client)
        self.service_key = os.getenv('SUPABASE_SERVICE_KEY')

        if not self.url or (not self.anon_key and not self.service_key):
            raise SupabaseError(
                "Supabase credentials not configured. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY."
            )

        # Lazy initialization - client created on first use
        self._client: Optional[Client] = None
        self._admin_client: Optional[Client] = None
        self._init_lock = Lock()

        # Cache for performance optimization
        self._last_heartbeat: Dict[str, float] = {}
        self._telemetry_buffer: List[Dict[str, Any]] = []
        self._telemetry_lock = Lock()

        # Outbox (offline spooling) directory
        self._outbox_dir = Path(os.getenv('AA_DRIVE_ROOT', os.getcwd())) / 'state' / 'outbox'
        try:
            self._outbox_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        logger.info(f"SupabaseClient initialized for {self.url}")

    def _get_client(self, admin: bool = False) -> Client:
        """
        Get or create Supabase client instance (lazy initialization).

        Args:
            admin: If True, use service key for admin operations

        Returns:
            Configured Supabase client

        Raises:
            SupabaseError: If client creation fails
        """
        with self._init_lock:
            if admin and self.service_key:
                if not self._admin_client:
                    try:
                        # Create admin client with service key
                        options = ClientOptions(
                            persist_session=False,  # No session for service role
                            auto_refresh_token=False
                        )
                        self._admin_client = create_client(
                            self.url,
                            self.service_key,
                            options=options
                        )
                    except Exception as e:
                        raise SupabaseError(f"Failed to create admin client: {e}")
                return self._admin_client

            # Regular anon client (fallback to service client when anon missing)
            if not self._client:
                try:
                    # Create client with connection pooling enabled
                    options = ClientOptions(
                        persist_session=True,  # Keep session for performance
                        auto_refresh_token=True
                    )
                    if self.anon_key:
                        self._client = create_client(
                            self.url,
                            self.anon_key,
                            options=options
                        )
                    elif self.service_key:
                        # Use service key as the primary client when anon is unavailable
                        self._client = create_client(
                            self.url,
                            self.service_key,
                            options=options
                        )
                except Exception as e:
                    raise SupabaseError(f"Failed to create client: {e}")

            # If anon not provided but service key exists, route normal ops through admin client
            if not self.anon_key and self.service_key:
                return self._get_client(admin=True)
            else:
                return self._client

    @retry_on_failure(max_attempts=3, backoff_factor=0.5)
    def health_check(self) -> Dict[str, Any]:
        """
        Return detailed connectivity status with latency and error info.
        """
        t0 = time.perf_counter()
        try:
            client = self._get_client()
            client.table('cabinet').select('id').limit(1).execute()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                'connected': True,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'latency_ms': latency_ms,
                'error': None,
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"Health check failed: {e}")
            return {
                'connected': False,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'latency_ms': latency_ms,
                'error': str(e),
            }

    @retry_on_failure(max_attempts=2, backoff_factor=0.3)
    def send_telemetry(
        self,
        device_id: str,
        level: str,
        code: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        batch: bool = True
    ) -> bool:
        """Send telemetry to cabinet_telemetry (unified schema)."""
        try:
            entry = TelemetryEntry(
                cabinet_id=device_id,
                level=level.upper(),
                code=code,
                message=message,
                payload=metadata,
            )

            if batch:
                # Add to buffer for batch processing
                with self._telemetry_lock:
                    self._telemetry_buffer.append(entry.to_dict())

                    # Flush if buffer full
                    if len(self._telemetry_buffer) >= self.TELEMETRY_BATCH_SIZE:
                        return self._flush_telemetry_buffer()

                return True

            # Immediate insert
            # Insert into cabinet_telemetry
            # Using admin client to bypass RLS if strict
            admin = self._get_client(admin=True)
            insert_result = admin.table('cabinet_telemetry').insert(entry.to_dict()).execute()
            logger.debug(f"Telemetry sent for cabinet {device_id}: {code}")
            return bool(insert_result.data)

        except Exception as e:
            logger.error(f"Failed to send telemetry: {e}")
            return False

    def _flush_telemetry_buffer(self) -> bool:
        """
        Flush buffered telemetry entries in batch.

        Returns:
            True if successful, False on failure
        """
        with self._telemetry_lock:
            if not self._telemetry_buffer:
                return True

            try:
                client = self._get_client()
                result = client.table('cabinet_telemetry').insert(self._telemetry_buffer).execute()
                count = len(self._telemetry_buffer)
                self._telemetry_buffer.clear()
                logger.info(f"Flushed {count} telemetry entries")
                return bool(result.data)
            except Exception as e:
                logger.error(f"Failed to flush telemetry buffer: {e}")
                # Spool to outbox for later retry
                try:
                    out = self._outbox_dir / 'telemetry.jsonl'
                    with out.open('a', encoding='utf-8') as f:
                        for row in self._telemetry_buffer:
                            f.write(json.dumps(row) + "\n")
                    self._telemetry_buffer.clear()
                except Exception:
                    pass
                return False

    @retry_on_failure(max_attempts=3, backoff_factor=1.0)
    def update_device_heartbeat(self, device_id: str, force: bool = False) -> bool:
        """
        Update device last_seen timestamp.

        Implements rate limiting to avoid excessive updates.

        Args:
            device_id: Unique device identifier
            force: If True, bypass rate limiting

        Returns:
            True if successful, False on failure
        """
        try:
            # Rate limit heartbeats (unless forced)
            if not force:
                last_beat = self._last_heartbeat.get(device_id, 0)
                if time.time() - last_beat < self.HEARTBEAT_INTERVAL:
                    logger.debug(f"Heartbeat throttled for device {device_id}")
                    return True

            admin = self._get_client(admin=bool(self.service_key))
            # Insert heartbeat row with metrics
            try:
                cpu = None; mem = None; diskp = None; uptime = None
                try:
                    import psutil  # optional
                    cpu = psutil.cpu_percent(interval=0.1)
                    mem = psutil.virtual_memory().percent
                    uptime = int(time.time() - psutil.boot_time())
                except Exception:
                    pass
                try:
                    root = os.getenv('AA_DRIVE_ROOT', os.getcwd())
                    du = shutil.disk_usage(root)
                    diskp = round((du.used / du.total) * 100, 2)
                except Exception:
                    pass
                admin.table('cabinet_heartbeat').insert({
                    'cabinet_id': device_id,
                    'uptime_seconds': uptime,
                    'cpu_percent': cpu,
                    'ram_percent': mem,
                    'disk_percent': diskp,
                }).execute()
            except Exception:
                pass

            # Update devices.last_seen
            result = admin.table('cabinet').update({
                'last_seen': datetime.now(timezone.utc).isoformat()
            }).eq('id', device_id).execute()

            if result.data:
                self._last_heartbeat[device_id] = time.time()
                logger.debug(f"Heartbeat recorded for cabinet {device_id}")
                return True

            logger.warning(f"No device found with id {device_id}")
            # Auto-insert device row (first boot provisioning)
            try:
                if self.service_key:
                    serial_number = os.getenv('AA_SERIAL_NUMBER') or os.getenv('DEVICE_SERIAL') or device_id
                    # device_name = os.getenv('DEVICE_NAME', 'Arcade Cabinet')
                    # tenant_id = os.getenv('AA_TENANT_ID', 'default')
                    
                    insert_row = {
                        'id': device_id,
                        'serial': serial_number,
                        'status': 'online',
                        'last_seen': datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        admin.table('cabinet').upsert(insert_row, on_conflict='id').execute()
                    except Exception:
                        try:
                            admin.table('cabinet').insert(insert_row).execute()
                        except Exception:
                            pass
                    # Attempt last_seen set again
                    result2 = admin.table('cabinet').update({
                        'last_seen': datetime.now(timezone.utc).isoformat()
                    }).eq('id', device_id).execute()
                    if result2.data:
                        self._last_heartbeat[device_id] = time.time()
                        logger.info(f"Device auto-provisioned and heartbeat recorded: {device_id}")
                        return True
            except Exception as ie:
                logger.warning(f"Device auto-insert failed for {device_id}: {ie}")
            return False

        except Exception as e:
            # logger.error(f"Failed to update heartbeat: {e}") # SILENCED
            return False

    @retry_on_failure(max_attempts=2, backoff_factor=0.5)
    def fetch_new_commands(self, device_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get pending commands for device with status='NEW'.

        Args:
            device_id: Unique device identifier

        Returns:
            List of command dictionaries or None on failure
        """
        try:
            client = self._get_client()
            result = client.table('command_queue')\
                .select('*')\
                .eq('cabinet_id', device_id)\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute()

            commands = result.data or []
            if commands:
                logger.info(f"Fetched {len(commands)} new commands for device {device_id}")

            return commands

        except Exception as e:
            logger.error(f"Failed to fetch commands: {e}")
            return None

    @retry_on_failure(max_attempts=2, backoff_factor=0.3)
    def update_command_status(
        self,
        command_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update command execution status and result.

        Args:
            command_id: Unique command identifier
            status: New status ('PROCESSING', 'COMPLETED', 'FAILED')
            result: Optional execution result data

        Returns:
            True if successful, False on failure
        """
        try:
            client = self._get_client()

            # Normalize statuses: PROCESSING->RUNNING, COMPLETED->DONE, FAILED->ERROR
            norm = {
                'PROCESSING': 'RUNNING',
                'COMPLETED': 'DONE',
                'FAILED': 'ERROR',
            }
            nstatus = norm.get(status.upper(), status)

            update_data = {
                'status': nstatus,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            if result is not None:
                update_data['result'] = result

            response = client.table('command_queue')\
                .update(update_data)\
                .eq('id', command_id)\
                .execute()

            if response.data:
                logger.info(f"Command {command_id} status updated to {status}")
                return True

            logger.warning(f"No command found with id {command_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to update command status: {e}")
            return False

    @retry_on_failure(max_attempts=2, backoff_factor=0.3)
    def insert_score(
        self,
        device_id: str,
        game_id: str,
        player: str,
        score: int,
        game_title: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add high score entry (unified schema).

        Args:
            device_id: Unique device identifier (cabinet serial)
            game_id: Game identifier (LaunchBox GUID or mame_{rom})
            player: Player name/identifier
            score: Numeric score value
            game_title: Human-readable game title (e.g., "Donkey Kong")
            source: Score source: 'mame_hiscore', 'retroachievements', 'manual'
            metadata: Optional additional data (combo, level, etc.)

        Returns:
            True if successful, False on failure
        """
        entry = None
        try:
            entry = ScoreEntry(
                cabinet_id=device_id,
                game_id=game_id,
                player=player,
                score=score,
                game_title=game_title,
                source=source,
                meta=metadata,
            )

            client = self._get_client()
            result = client.table('cabinet_game_score').insert(entry.to_dict()).execute()

            if result.data:
                logger.info(f"Score recorded: {player} - {score} on {game_title or game_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to insert score: {e}")
            # Spool to outbox
            if entry:
                try:
                    out = self._outbox_dir / 'scores.jsonl'
                    with out.open('a', encoding='utf-8') as f:
                        f.write(json.dumps(entry.to_dict()) + "\n")
                except Exception:
                    pass
            return False

    def flush(self) -> bool:
        """
        Flush any buffered data (telemetry, etc.).

        Returns:
            True if successful, False on failure
        """
        ok = self._flush_telemetry_buffer()
        try:
            self.flush_outbox()
        except Exception:
            pass
        return ok

    def flush_outbox(self) -> None:
        """Attempt to flush offline spooled telemetry/scores from outbox."""
        try:
            client = self._get_client()
        except Exception:
            # No client available
            return

        # Flush telemetry
        tele_path = self._outbox_dir / 'telemetry.jsonl'
        if tele_path.exists():
            try:
                lines = tele_path.read_text(encoding='utf-8').splitlines()
                if lines:
                    rows = [json.loads(l) for l in lines if l.strip()]
                    if rows:
                        client.table('cabinet_telemetry').insert(rows).execute()
                        tele_path.unlink(missing_ok=True)
            except Exception:
                # Keep file for next attempt
                pass
        # Flush scores
        scores_path = self._outbox_dir / 'scores.jsonl'
        if scores_path.exists():
            try:
                lines = scores_path.read_text(encoding='utf-8').splitlines()
                if lines:
                    for l in lines:
                        try:
                            row = json.loads(l)
                            client.table('cabinet_game_score').insert(row).execute()
                        except Exception:
                            pass
                    scores_path.unlink(missing_ok=True)
            except Exception:
                pass

    def close(self) -> None:
        """Clean up resources and flush buffers."""
        try:
            # Flush any pending telemetry
            self.flush()

            # Clear caches
            self._last_heartbeat.clear()

            # Note: supabase-py client doesn't need explicit closing
            # as it uses requests.Session internally which handles cleanup

            logger.info("SupabaseClient closed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup."""
        self.close()

    def __del__(self):
        """Destructor - ensure cleanup on garbage collection."""
        try:
            self.close()
        except:
            pass  # Ignore errors during cleanup


# Module-level singleton helpers ------------------------------------------------
_client_override: Optional[SupabaseClient] = None


def _instantiate_client(url: Optional[str], anon_key: Optional[str]) -> SupabaseClient:
    """Factory function kept separate for easier patching/tests."""
    return SupabaseClient(url=url, anon_key=anon_key)


@lru_cache(maxsize=1)
def _cached_client(url: Optional[str], anon_key: Optional[str]) -> SupabaseClient:
    """Return memoized client instance."""
    return _instantiate_client(url, anon_key)


def get_client(
    url: Optional[str] = None,
    anon_key: Optional[str] = None
) -> SupabaseClient:
    """
    Get singleton Supabase client instance with optional overrides.

    Args:
        url: Optionally override SUPABASE_URL (useful for tests)
        anon_key: Optionally override SUPABASE_ANON_KEY
    """
    if _client_override is not None:
        return _client_override
    return _cached_client(url, anon_key)


def inject_supabase_client(client: SupabaseClient) -> None:
    """Inject pre-built client (useful for tests)."""
    global _client_override
    _client_override = client


def reset_supabase_client() -> None:
    """Clear overrides and cached singleton."""
    global _client_override
    _client_override = None
    _cached_client.cache_clear()


# Convenience functions using singleton client
def health_check() -> Dict[str, Any]:
    """Return detailed Supabase connectivity status."""
    try:
        result = get_client().health_check()
        if isinstance(result, dict):
            return result
        return {
            'connected': bool(result),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'latency_ms': 0,
            'error': None if result else 'Unknown',
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'connected': False,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'latency_ms': 0,
            'error': str(e),
        }


def send_telemetry(
    device_id: str,
    level: str,
    code: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Send telemetry log entry."""
    try:
        return get_client().send_telemetry(device_id, level, code, message, metadata)
    except Exception as e:
        logger.error(f"Failed to send telemetry: {e}")
        return False


def update_device_heartbeat(device_id: str) -> bool:
    """Update device heartbeat timestamp."""
    try:
        return get_client().update_device_heartbeat(device_id)
    except Exception as e:
        logger.error(f"Failed to update heartbeat: {e}")
        return False


def fetch_new_commands(device_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch pending commands for device."""
    try:
        return get_client().fetch_new_commands(device_id)
    except Exception as e:
        logger.error(f"Failed to fetch commands: {e}")
        return None


def update_command_status(
    command_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None
) -> bool:
    """Update command execution status."""
    try:
        return get_client().update_command_status(command_id, status, result)
    except Exception as e:
        logger.error(f"Failed to update command status: {e}")
        return False


def insert_score(
    device_id: str,
    game_id: str,
    player: str,
    score: int,
    game_title: Optional[str] = None,
    source: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Insert high score to Supabase cabinet_game_score table."""
    try:
        return get_client().insert_score(
            device_id, game_id, player, score,
            game_title=game_title,
            source=source,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Failed to insert score: {e}")
        return False


