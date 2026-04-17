"""
Game launcher service with fallback chain - REFACTORED 2025-10-13

Launch methods (in priority order):
0. Mock launcher (when AA_DEV_MODE=true) - for development/testing
1. Plugin bridge via HTTP (NEW - localhost:9999) - most reliable
2. Auto-detected emulator from LaunchBox config - secondary fallback
3. Direct emulator execution with hardcoded paths - optional (AA_ALLOW_DIRECT_EMULATOR=true)
4. LaunchBox.exe - last resort fallback for unknown platforms

Performance Optimizations:
- Plugin client singleton with connection pooling
- Cached emulator configurations
- Early return on successful launch
- Minimal object creation in hot paths
"""

import subprocess
import logging
import shlex
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List, Tuple
import json
from backend.services.supabase_client import send_telemetry as sb_send_telemetry
import platform

from backend.constants.drive_root import (
    get_drive_root,
    get_drive_root_or_none,
    get_project_root,
    resolve_runtime_path,
)
from backend.models.game import Game, LaunchResponse
from backend.constants.a_drive_paths import LaunchBoxPaths
from backend.services.launchbox_plugin_client import get_plugin_client, LaunchBoxPluginError
import threading
from backend.services.launcher_registry import REGISTERED as ADAPTERS
from backend.constants.runtime_paths import aa_tmp_dir
from backend.services.archive_utils import extract_if_archive, ExtractResult, resolve_rom_path
from backend.services.adapters.adapter_utils import dry_run_enabled
from backend.services.platform_names import normalize_key
from backend.services.ps2_resolver import load_overrides
import shutil
import socket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Launcher Agent client — sends launch commands to arcade_launcher_agent.py
# which runs in a clean interactive session (not under run-backend.bat's
# redirected stdout chain).  Required for OpenGL emulators like Supermodel.
# ---------------------------------------------------------------------------
_AGENT_HOST = "127.0.0.1"
_AGENT_PORT = int(os.getenv("AA_LAUNCHER_AGENT_PORT", "9123"))
_AGENT_TIMEOUT = 5.0  # seconds


def _agent_is_reachable(timeout: float = 0.5) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((_AGENT_HOST, _AGENT_PORT))
        sock.close()
        return True
    except Exception:
        return False


def _start_launcher_agent() -> bool:
    if _agent_is_reachable():
        return True

    repo_root = Path(__file__).resolve().parents[2]
    starter_script = repo_root / "scripts" / "start_launcher_agent.bat"
    agent_script = repo_root / "scripts" / "arcade_launcher_agent.py"
    if not agent_script.exists():
        logger.warning("[Agent] script missing: %s", agent_script)
        return False

    if starter_script.exists():
        try:
            subprocess.Popen(
                f'cmd.exe /c start "" "{starter_script}"',
                cwd=str(repo_root),
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning("[Agent] batch auto-start failed: %s", e)
        else:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if _agent_is_reachable():
                    logger.info("[Agent] auto-start via batch succeeded")
                    return True
                time.sleep(0.2)

    python_candidates = []
    try:
        exe_path = Path(sys.executable)
        python_candidates.append(exe_path.with_name("pythonw.exe"))
        python_candidates.append(exe_path)
    except Exception:
        pass
    python_candidates.append(Path(str(repo_root / ".venv" / "Scripts" / "pythonw.exe")))
    python_candidates.append(Path(str(repo_root / ".venv" / "Scripts" / "python.exe")))

    python_cmd = None
    for candidate in python_candidates:
        try:
            if candidate.exists():
                python_cmd = str(candidate)
                break
        except Exception:
            continue
    if not python_cmd:
        python_cmd = "pythonw.exe"

    try:
        create_new_process_group = 0x00000200
        detached_process = 0x00000008
        subprocess.Popen(
            [python_cmd, str(agent_script)],
            cwd=str(repo_root),
            creationflags=create_new_process_group | detached_process,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.warning("[Agent] auto-start failed: %s", e)
        return False

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if _agent_is_reachable():
            logger.info("[Agent] auto-start succeeded")
            return True
        time.sleep(0.2)

    logger.warning("[Agent] auto-start timed out")
    return False


def _launch_via_agent(
    command: list,
    cwd: str = None,
    env_override: dict = None,
    _retry_started: bool = False,
) -> dict:
    """Send a launch command to the Launcher Agent.

    Returns dict with {"ok": True, "pid": ...} on success,
    or {"ok": False, "error": "..."} on failure / agent unreachable.
    """
    payload = {
        "exe": str(command[0]),
        "args": [str(a) for a in command[1:]],
        "cwd": str(cwd) if cwd else None,
        "env_override": env_override or {},
    }
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_AGENT_TIMEOUT)
        sock.connect((_AGENT_HOST, _AGENT_PORT))
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)            # signal end of request
        resp_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp_data += chunk
        sock.close()
        result = json.loads(resp_data.decode("utf-8").strip())
        logger.info("[Agent] response: %s", result)
        return result
    except Exception as e:
        logger.warning("[Agent] unreachable (%s:%d): %s", _AGENT_HOST, _AGENT_PORT, e)
        if not _retry_started and _start_launcher_agent():
            return _launch_via_agent(
                command,
                cwd=cwd,
                env_override=env_override,
                _retry_started=True,
            )
        return {"ok": False, "error": str(e)}



def _convert_wsl_paths_for_windows(command: List[str]) -> List[str]:
    """
    Convert WSL paths to Windows paths for executing Windows .exe files from WSL.

    Args:
        command: Command list with potential WSL paths

    Returns:
        Command list with Windows paths
    """
    if platform.system() != "Linux" or "microsoft" not in platform.release().lower():
        # Not running in WSL, return as-is
        return command

    converted = []
    for arg in command:
        arg_str = str(arg)
        # Convert /mnt/X/ paths to Windows X:\ paths
        if arg_str.startswith("/mnt/"):
            try:
                # Use wslpath utility to convert
                result = subprocess.run(
                    ["wslpath", "-w", arg_str],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    converted.append(result.stdout.strip())
                else:
                    converted.append(arg_str)
            except Exception:
                # Fallback: manual conversion
                # /mnt/a/path -> A:\path
                parts = arg_str.split("/", 3)
                if len(parts) >= 3:
                    drive = parts[2].upper()
                    rest = parts[3] if len(parts) > 3 else ""
                    win_rest = rest.replace('/', '\\')
                    converted.append(f"{drive}:\\{win_rest}")
                else:
                    converted.append(arg_str)
        else:
            converted.append(arg_str)

    return converted


def _absolutize_daphne_wrapper_args(args: List[str], base_dir: Path) -> List[str]:
    """Resolve relative Hypseus/Singe wrapper paths against the AHK script directory."""
    rewritten: List[str] = []
    idx = 0
    path_flags = {"-framefile", "-script", "-homedir", "-bezel"}
    while idx < len(args):
        token = str(args[idx])
        low = token.lower()

        if low in path_flags and idx + 1 < len(args):
            value = str(args[idx + 1]).strip().strip('"')
            candidate = Path(value.replace("\\", "/"))
            if value and not candidate.is_absolute():
                candidate = (base_dir / candidate).resolve()
                if low == "-bezel" and not candidate.exists():
                    bezel_candidate = (base_dir / "bezels" / value).resolve()
                    if bezel_candidate.exists():
                        candidate = bezel_candidate
            rewritten.extend([token, str(candidate)])
            idx += 2
            continue

        if "=" in token:
            key, value = token.split("=", 1)
            if key.lower() in path_flags:
                candidate = Path(value.strip().strip('"').replace("\\", "/"))
                if value and not candidate.is_absolute():
                    candidate = (base_dir / candidate).resolve()
                    if key.lower() == "-bezel" and not candidate.exists():
                        bezel_candidate = (base_dir / "bezels" / value).resolve()
                        if bezel_candidate.exists():
                            candidate = bezel_candidate
                rewritten.append(f"{key}={candidate}")
                idx += 1
                continue

        rewritten.append(token)
        idx += 1

    return rewritten


class GameLauncher:
    """
    Service for launching games via multiple fallback methods.

    Key optimizations:
    - Plugin-first architecture for reliability
    - Singleton pattern to avoid repeated initialization
    - Cached emulator configurations
    - Efficient method dispatch with early returns
    """

    # Stderr trap: last result for remediation loop access
    _last_trap_result: Optional[Dict[str, Any]] = None

    def __init__(self):
        """Initialize launcher and load emulator configurations."""
        # Load emulator config eagerly to avoid repeated lazy imports
        from backend.services.emulator_detector import detector
        self.emulator_config = detector.get_or_detect_config()
        self._log_config_status()

        # Get plugin client singleton
        self.plugin_client = get_plugin_client()

        # Define launch methods with their names for cleaner code
        # Priority: Plugin FIRST, then LaunchBox-detected, then LaunchBox UI
        # Allow direct emulator fallback when explicitly enabled.
        # Support both AA_* env flags and config/launchers.json global toggles.
        allow_direct_env = any(
            str(os.getenv(name, "false")).lower() in {"1", "true", "yes"}
            for name in (
                "AA_ALLOW_DIRECT_EMULATOR",
                "AA_ALLOW_DIRECT_MAME",
                "AA_ALLOW_DIRECT_RETROARCH",
                "AA_ALLOW_DIRECT_TEKNOPARROT",
            )
        )
        # Consult manifest toggles as well (e.g., allow_direct_retroarch)
        allow_direct_cfg = False
        try:
            manifest = self._load_launchers_config() or {}
            g = (manifest.get("global") or {}) if isinstance(manifest, dict) else {}
            allow_direct_cfg = any(
                bool(g.get(k)) for k in (
                    "allow_direct_emulator",
                    "allow_direct_mame",
                    "allow_direct_retroarch",
                    "allow_direct_redream",
                    "allow_direct_pcsx2",
                    "allow_direct_rpcs3",
                )
            )
        except Exception:
            allow_direct_cfg = False
        allow_direct = bool(allow_direct_env or allow_direct_cfg)

        methods: List[Tuple[str, Callable]] = [
            ("plugin", self._launch_via_plugin),  # NEW: Plugin-first method
            ("detected_emulator", self._launch_via_detected_emulator),  # LaunchBox configs
            ("launchbox", self._launch_via_launchbox),  # Open LaunchBox UI as last resort
        ]

        if allow_direct:
            # Optional direct emulator launch (opt-in only)
            methods.insert(2, ("direct", self._launch_direct))

        self._launch_methods = methods
        logger.info(f"Launcher initialized with methods: {[m[0] for m in methods]}")

        # Concurrency guard for 'direct' launches
        try:
            max_conc = int(os.getenv('AA_DIRECT_MAX_CONCURRENCY', '1'))
        except Exception:
            max_conc = 1
        self._direct_sem = threading.Semaphore(max(1, max_conc))

        # Health cache for direct leg
        self._direct_health_cache = None
        self._direct_health_time = 0.0

        # Routing policy cache
        self._routing_policy: Optional[Dict[str, Any]] = None
        self._routing_policy_time: float = 0.0
        # PS2 overrides cache
        self._ps2_overrides = None
        self._ps2_lock = threading.Lock()

    def _log_config_status(self) -> None:
        """Log the emulator configuration status."""
        if self.emulator_config and self.emulator_config.emulators:
            logger.info(
                f"Loaded {len(self.emulator_config.emulators)} emulator configs "
                f"with {len(self.emulator_config.platform_mappings)} platform mappings"
            )
        else:
            logger.info("No emulator config loaded - will use plugin and hardcoded fallbacks")

    def launch(self, game: Game, force_method: Optional[str] = None, profile_hint: Optional[str] = None) -> LaunchResponse:
        """
        Launch game with automatic fallback chain.

        Args:
            game: Game model to launch
            force_method: Optional forced method (mock|plugin|detected_emulator|direct|launchbox)

        Returns:
            LaunchResponse with success status and method used
        """
        # Check for dev mode FIRST - enables mock launcher for testing
        if os.getenv('AA_DEV_MODE', 'false').lower() == 'true' and force_method != 'production':
            logger.info(f"Dev mode enabled - using mock launcher for {game.title}")
            result = self._launch_mock(game)
            return LaunchResponse(
                success=True,
                game_id=game.id,
                method_used="mock",
                command=result.get("command", ""),
                message=result.get("message", ""),
            )

        # Determine which methods to try
        methods = self._get_launch_methods(force_method)

        # Enforce routing-policy guardrails (e.g., mame_protected skip of 'direct')
        if force_method != 'direct':
            policy = self._get_routing_policy()
            try:
                protected = set(policy.get('mame_protected', []) if isinstance(policy, dict) else [])
            except Exception:
                protected = set()
            if protected and (game.platform in protected):
                methods = [(n, f) for (n, f) in methods if n != 'direct']


        # Direct-preferred platforms: reorder so 'direct' runs FIRST.
        # These platforms have dedicated adapters and must bypass stale
        # LaunchBox cached emulator mappings when possible.
        platform_key = normalize_key(getattr(game, 'platform', '') or '')
        direct_preferred = {
            'sega model 3',
            'sega dreamcast',
            'dreamcast',
            'sony playstation 2',
            'playstation 2',
            'ps2',
            'ps2 gun games',
        }
        prefer_retroarch_direct = self._should_prefer_retroarch_direct(game)
        direct_only_platforms = {
            'sony playstation 2',
            'playstation 2',
            'ps2',
            'ps2 gun games',
        }
        if prefer_retroarch_direct:
            # RetroArch-routed console platforms must stay on the direct
            # adapter path. LaunchBox/plugin fallbacks route into stale
            # LaunchBox-managed RetroArch installs and break bezel/core
            # selection for end users.
            methods = [(n, f) for (n, f) in methods if n == 'direct']
            direct_preferred.add(platform_key)
        elif platform_key in direct_only_platforms:
            # PS2 must launch directly through PCSX2 and never route back
            # through LaunchBox/plugin fallbacks.
            methods = [(n, f) for (n, f) in methods if n == 'direct']

        if platform_key in direct_preferred:
            direct_methods = [(n, f) for (n, f) in methods if n == 'direct']
            other_methods = [(n, f) for (n, f) in methods if n != 'direct']
            if direct_methods:
                methods = direct_methods + other_methods
        no_launchbox_fallback = {'daphne', 'hypseus', 'laserdisc'}
        if platform_key in no_launchbox_fallback:
            methods = [(n, f) for (n, f) in methods if n != 'launchbox']
        # Try each method in sequence (optimized: early return on success)
        last_failure: Optional[str] = None
        for method_name, method_func in methods:
            result, failure_msg = self._try_launch_method(game, method_name, method_func, profile_hint)
            if result:
                return result
            if failure_msg:
                last_failure = f"{method_name}: {failure_msg}"

        # All methods failed
        try:
            sb_send_telemetry(os.getenv('AA_DEVICE_ID', ''), 'ERROR', 'LAUNCH_FAIL', f"All launch methods failed for {game.title}")
        except Exception:
            pass
        return LaunchResponse(
            success=False,
            game_id=game.id,
            method_used="none",
            command="",
            message=last_failure or f"All launch methods failed for {game.title}",
            error="No suitable launch method found",
        )

    def _get_launch_methods(
        self, force_method: Optional[str]
    ) -> List[Tuple[str, Callable]]:
        """
        Get the list of launch methods to try.

        Args:
            force_method: Optional method to force

        Returns:
            List of (method_name, method_function) tuples
        """
        if force_method:
            # Filter to only the forced method (optimized: list comprehension)
            forced = [
                (name, func)
                for name, func in self._launch_methods
                if name == force_method
            ]
            # If forcing 'direct' but not enabled globally, still allow it explicitly
            if not forced and force_method == 'direct':
                forced = [('direct', self._launch_direct)]
            return forced
        methods = list(self._launch_methods)
        # Skip 'direct' when unhealthy (unless caller forced direct earlier)
        try:
            healthy = self._direct_is_healthy()
        except Exception:
            healthy = False
        if not healthy:
            methods = [(n, f) for (n, f) in methods if n != 'direct']
        return methods

    def _should_prefer_retroarch_direct(self, game: Game) -> bool:
        platform_name = getattr(game, 'platform', '') or ''
        if not platform_name:
            return False

        try:
            manifest = self._load_launchers_config() or {}
        except Exception:
            manifest = {}

        for adapter in ADAPTERS:
            try:
                adapter_name = str(getattr(adapter, "__name__", "") or getattr(adapter, "__module__", ""))
                if not adapter_name.endswith("retroarch_adapter"):
                    continue
                if hasattr(adapter, "is_enabled") and not adapter.is_enabled(manifest):
                    return False
                return bool(adapter.can_handle(game, manifest))
            except Exception as e:
                logger.debug(f"[DIRECT] RetroArch routing probe failed for {platform_name}: {e}")
                return False

        return False

    def _ps2_lookup_override(self, game_id: str, requested: str) -> Optional[str]:
        try:
            # Load lazily under lock
            if self._ps2_overrides is None:
                with self._ps2_lock:
                    if self._ps2_overrides is None:
                        self._ps2_overrides = load_overrides()
            ov = self._ps2_overrides or {}
            by_id = ov.get("by_game_id", {})
            if game_id and game_id in by_id:
                return by_id[game_id]
            rp = str(Path(requested)).lower().replace("/", "\\")
            return (ov.get("by_request_path", {}) or {}).get(rp)
        except Exception:
            return None

    def reload_ps2_overrides(self) -> Dict[str, int]:
        """Reload overrides atomically; returns counts."""
        with self._ps2_lock:
            self._ps2_overrides = load_overrides()
            data = self._ps2_overrides or {}
            by_id = (data.get("by_game_id", {}) or {})
            by_req = (data.get("by_request_path", {}) or {})
            return {"by_game_id": len(by_id), "by_request_path": len(by_req)}

    def _get_routing_policy(self) -> Dict[str, Any]:
        """Load routing-policy.json from configs with simple TTL cache."""
        ttl = 10.0  # seconds
        now = time.time()
        if self._routing_policy is not None and (now - self._routing_policy_time) < ttl:
            return self._routing_policy or {}
        try:
            root = get_drive_root(context="launcher routing policy")
            target = root / 'configs' / 'routing-policy.json'
            if target.exists():
                data = json.loads(target.read_text(encoding='utf-8'))
                self._routing_policy = data if isinstance(data, dict) else {}
            else:
                self._routing_policy = {}
        except Exception:
            self._routing_policy = {}
        self._routing_policy_time = now
        return self._routing_policy

    def _direct_is_healthy(self) -> bool:
        ttl = 30.0
        now = time.time()
        if self._direct_health_cache is not None and (now - self._direct_health_time) < ttl:
            return bool(self._direct_health_cache)

        # Check if ANY direct launch flag is enabled via env OR manifest
        enabled_env = any(
            str(os.getenv(name, 'false')).lower() in {'1', 'true', 'yes'}
            for name in (
                'AA_ALLOW_DIRECT_EMULATOR',
                'AA_ALLOW_DIRECT_MAME',
                'AA_ALLOW_DIRECT_RETROARCH',
                'AA_ALLOW_DIRECT_REDREAM',
                'AA_ALLOW_DIRECT_PCSX2',
                'AA_ALLOW_DIRECT_RPCS3',
                'AA_ALLOW_DIRECT_TEKNOPARROT',
            )
        )
        enabled_cfg = False
        try:
            cfg = self._load_launchers_config() or {}
            g = (cfg.get('global') or {}) if isinstance(cfg, dict) else {}
            enabled_cfg = any(
                bool(g.get(k)) for k in (
                    'allow_direct_emulator',
                    'allow_direct_mame',
                    'allow_direct_retroarch',
                    'allow_direct_redream',
                    'allow_direct_pcsx2',
                    'allow_direct_rpcs3',
                )
            )
        except Exception:
            enabled_cfg = False
        enabled = bool(enabled_env or enabled_cfg)
        if not enabled:
            self._direct_health_cache = False
            self._direct_health_time = now
            return False

        # Check if MAME emulator exists (for direct MAME launch)
        mame_exists = False
        try:
            mame_exe = LaunchBoxPaths.MAME_EMULATOR
            mame_exists = mame_exe.exists()
        except Exception:
            mame_exists = False

        # Check if RetroArch exists (for direct RetroArch launch)
        cfg = self._load_launchers_config() or {}
        ra = None
        for k in ('emulators', 'launchers'):
            block = cfg.get(k)
            if isinstance(block, dict) and isinstance(block.get('retroarch'), dict):
                ra = block.get('retroarch')
                break
        if ra is None and isinstance(cfg.get('retroarch'), dict):
            ra = cfg.get('retroarch')

        ra_exists = False
        try:
            exe = (ra or {}).get('exe')
            if isinstance(exe, str) and exe:
                p = Path(exe)
                # Convert to WSL mount only if actually running under WSL
                is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()
                if not p.exists() and is_wsl and len(exe) >= 2 and exe[1] == ':':
                    drive = exe[0].lower()
                    p = Path(exe.replace('\\', '/').replace(f"{exe[0]}:", f"/mnt/{drive}"))
                if not p.exists():
                    # Fallback discovery: scan common locations for retroarch.exe
                    try:
                        from backend.constants.a_drive_paths import LaunchBoxPaths
                        lb_emus = LaunchBoxPaths.LAUNCHBOX_ROOT / 'Emulators'
                        cands = []
                        for base in [lb_emus, LaunchBoxPaths.EMULATORS_ROOT]:
                            try:
                                if base.exists():
                                    cands.extend(base.rglob('retroarch.exe'))
                            except Exception:
                                continue
                        if cands:
                            p = cands[0]
                    except Exception:
                        pass
                ra_exists = p.exists()
        except Exception:
            ra_exists = False

        # Check if Redream exists (for direct Redream launch)
        redream_exists = False
        try:
            # Get Redream config from manifest
            redream_cfg = None
            for key in ('emulators', 'launchers'):
                block = cfg.get(key)
                if isinstance(block, dict) and isinstance(block.get('redream'), dict):
                    redream_cfg = block.get('redream')
                    break
            if not redream_cfg and isinstance(cfg.get('redream'), dict):
                redream_cfg = cfg.get('redream')

            if redream_cfg:
                exe = redream_cfg.get("exe")
                if isinstance(exe, str) and exe:
                    p = Path(exe)
                is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()
                if not p.exists() and is_wsl and len(exe) >= 2 and exe[1] == ':':
                    drive = exe[0].lower()
                    p = Path(exe.replace('\\', '/').replace(f"{exe[0]}:", f"/mnt/{drive}"))
                redream_exists = p.exists()
        except Exception:
            redream_exists = False

        # Check if PCSX2 exists (for direct PS2 launch)
        pcsx2_exists = False
        try:
            pcsx2_cfg = None
            for key in ('emulators', 'launchers'):
                block = cfg.get(key)
                if isinstance(block, dict) and isinstance(block.get('pcsx2'), dict):
                    pcsx2_cfg = block.get('pcsx2')
                    break
            if not pcsx2_cfg and isinstance(cfg.get('pcsx2'), dict):
                pcsx2_cfg = cfg.get('pcsx2')

            if pcsx2_cfg:
                exe = pcsx2_cfg.get("exe")
                if isinstance(exe, str) and exe:
                    p = Path(exe)
                    is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()
                    if not p.exists() and is_wsl and len(exe) >= 2 and exe[1] == ':':
                        drive = exe[0].lower()
                        p = Path(exe.replace('\\', '/').replace(f"{exe[0]}:", f"/mnt/{drive}"))
                    pcsx2_exists = p.exists()
        except Exception:
            pcsx2_exists = False

        # Check if RPCS3 exists (for direct PS3 launch)
        rpcs3_exists = False
        try:
            rpcs3_cfg = None
            for key in ('emulators', 'launchers'):
                block = cfg.get(key)
                if isinstance(block, dict) and isinstance(block.get('rpcs3'), dict):
                    rpcs3_cfg = block.get('rpcs3')
                    break
            if not rpcs3_cfg and isinstance(cfg.get('rpcs3'), dict):
                rpcs3_cfg = cfg.get('rpcs3')

            if rpcs3_cfg:
                exe = rpcs3_cfg.get("exe")
                if isinstance(exe, str) and exe:
                    p = Path(exe)
                    is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()
                    if not p.exists() and is_wsl and len(exe) >= 2 and exe[1] == ':':
                        drive = exe[0].lower()
                        p = Path(exe.replace('\\', '/').replace(f"{exe[0]}:", f"/mnt/{drive}"))
                    rpcs3_exists = p.exists()
        except Exception:
            rpcs3_exists = False

        # Check TeknoParrot exists
        teknoparrot_exists = False
        try:
            from backend.services.adapters import teknoparrot_adapter as tp
            tp_exe = tp._teknoparrot_exe()
            teknoparrot_exists = Path(tp_exe).exists()
        except Exception:
            teknoparrot_exists = False

        # Direct launch is healthy if enabled AND (any emulator exists)
        self._direct_health_cache = enabled and (
            mame_exists or ra_exists or redream_exists or pcsx2_exists or rpcs3_exists or teknoparrot_exists
        )
        self._direct_health_time = now
        return bool(self._direct_health_cache)

    def _try_launch_method(
        self, game: Game, method_name: str, method_func: Callable, profile_hint: Optional[str] = None
    ) -> Tuple[Optional[LaunchResponse], Optional[str]]:
        """
        Try a single launch method and return result if successful.

        Args:
            game: Game to launch
            method_name: Name of the method being tried
            method_func: Function to call for launching

        Returns:
            Tuple of (LaunchResponse if successful, failure message if failed)
        """
        try:
            logger.info(f"Attempting launch via {method_name}: {game.title}")
            if method_name == 'direct':
                result = self._launch_direct(game, profile_hint)
            else:
                result = method_func(game)

            # Optional trace line (log every attempt result)
            if str(os.getenv('AA_LAUNCH_TRACE', '0')).lower() in {'1','true','yes'}:
                try:
                    trace = {
                        "game_id": game.id,
                        "platform": game.platform,
                        "adapter": method_name,
                        "rom_from_api": game.rom_path,
                        "resolved_file": result.get("resolved_file", ""),
                        "extracted": result.get("extracted", None),
                        "command": result.get("command", ""),
                        "message": result.get("message", ""),
                        "notes": result.get("notes", ""),
                        "dry_run": 1 if 'dry-run' in (result.get('message','').lower()) else 0,
                    }
                    os.makedirs('logs', exist_ok=True)
                    with open('logs/launch_attempts.jsonl','a',encoding='utf-8') as f:
                        f.write(json.dumps(trace) + "\n")
                except Exception:
                    pass
            if result.get("success"):
                return LaunchResponse(
                    success=True,
                    game_id=game.id,
                    method_used=method_name,
                    command=result.get("command", ""),
                    message=f"Launched {game.title} via {method_name}",
                ), None
            failure_msg = result.get("message") or result.get("error") or str(result)
            logger.warning(
                "%s returned non-success for %s: %s",
                method_name,
                game.title,
                failure_msg,
            )
            return None, str(failure_msg)

        except Exception as e:
            logger.warning(f"{method_name} failed for {game.title}: {e}")
            try:
                sb_send_telemetry(os.getenv('AA_DEVICE_ID', ''), 'ERROR', 'LAUNCH_FAIL', f"{method_name} failed for {game.title}: {e}")
            except Exception:
                pass
            return None, str(e)

        return None, None

    def _launch_via_plugin(self, game: Game) -> Dict[str, Any]:
        """
        Launch game via C# plugin bridge (NEW PRIMARY METHOD).

        This method uses the LaunchBox C# plugin running on localhost:9999
        to launch games directly through LaunchBox's native API.

        Args:
            game: Game to launch

        Returns:
            Dict with success status and optional command

        Raises:
            LaunchBoxPluginError: If plugin is unavailable or launch fails
        """
        # Check plugin availability first (cached for performance)
        if not self.plugin_client.is_available():
            raise LaunchBoxPluginError("Plugin not available at localhost:9999")

        logger.info(f"Launching '{game.title}' via C# plugin bridge...")

        # Launch via plugin with proper error handling
        try:
            result = self.plugin_client.launch_game(game.id)

            # Check for both 'launched' and 'success' keys for compatibility
            launched = result.get("launched", False) or result.get("success", False)

            if launched:
                logger.info(f"Plugin launch successful for '{game.title}'")
                return {
                    "success": True,
                    "command": f"[Plugin] LaunchBox native launch for {game.id}",
                    "message": result.get("message", "Game launched via plugin")
                }
            else:
                error_msg = result.get("message", "Plugin launch failed")
                logger.warning(f"Plugin launch failed for '{game.title}': {error_msg}")
                raise LaunchBoxPluginError(error_msg)

        except Exception as e:
            # Log and re-raise for fallback handling
            logger.error(f"Plugin launch error for '{game.title}': {e}")
            raise

    def _launch_via_detected_emulator(self, game: Game) -> Dict[str, Any]:
        """
        Launch game using auto-detected emulator configuration from LaunchBox.

        This is the SECONDARY launch method when plugin is unavailable.
        Falls back to hardcoded methods if no config found for this platform.
        """
        if not self.emulator_config or not self.emulator_config.emulators:
            raise ValueError("No emulator config loaded")

        # Get emulator and mapping for this game's platform
        result = self.emulator_config.get_emulator_for_platform(game.platform)

        if not result:
            raise ValueError(f"No emulator configured for platform: {game.platform}")

        emulator, mapping = result

        # Special-case PCSX2 to apply resolver + archive handling here too (consistency with direct)
        try:
            launchbox_root = self._get_launchbox_root()
            emulator_exe = emulator.resolve_path(launchbox_root)
            is_pcsx2 = 'pcsx2' in str(emulator_exe).lower() or 'pcsx2' in str(getattr(emulator, 'title', '')).lower()
        except Exception:
            is_pcsx2 = False

        if is_pcsx2:
            # Resolve and extract if needed then run with cleanup
            rom_str = self._get_rom_path(game)
            src = Path(rom_str)
            actual, how = resolve_rom_path(src)
            if not actual:
                raise FileNotFoundError(f"ROM not found for {src.name} (checked alt extensions)")

            # Optional free space guard
            try:
                min_free_gb = float(os.getenv("AA_EXTRACT_MIN_FREE_GB", "10"))
            except Exception:
                min_free_gb = 10.0
            tmp_base = aa_tmp_dir()
            try:
                usage = shutil.disk_usage(tmp_base)
                free_gb = usage.free / (1024 ** 3)
                if free_gb < min_free_gb:
                    raise RuntimeError(f"Insufficient free space in temp dir drive: {free_gb:.1f} GB < {min_free_gb} GB")
            except Exception as e:
                logger.debug(f"AA_EXTRACT_MIN_FREE_GB check skipped: {e}")

            result: ExtractResult = extract_if_archive(actual, tmp_base)
            iso_path = str(result.extracted_path) if result.extracted_path else str(actual)
            if result.used_tool:
                logger.info("PCSX2: resolved=%s requested=%s actual=%s used_tool=%s", how, src.name, actual.name, result.used_tool)
            else:
                logger.debug("PCSX2: resolved=%s requested=%s actual=%s", how, src.name, actual.name)

            # Build args from mapping + iso_path
            flags = []
            if mapping.command_line:
                flags.extend(shlex.split(mapping.command_line))
            args = [*flags, iso_path]

            # Prepare cleanup callback if temp root created
            cleanup_cb = None
            if result.temp_root:
                base = aa_tmp_dir().resolve()
                root = result.temp_root.resolve()

                def _cleanup():
                    try:
                        if str(root).startswith(str(base)):
                            shutil.rmtree(root, ignore_errors=True)
                            logger.debug("PCSX2 temp cleaned: %s", str(root))
                    except Exception as ce:
                        logger.warning("PCSX2 temp cleanup failed: %s", ce)

                cleanup_cb = _cleanup

            self._run_adapter_process(str(emulator_exe), args, str(Path(emulator_exe).parent), cleanup_cb)
            return {"success": True, "command": " ".join([str(emulator_exe), *args])}

        # Default path for other emulators
        command = self._build_emulator_command(game, emulator, mapping)
        self._execute_emulator(command, emulator)
        return {"success": True, "command": " ".join(command)}

    def _build_emulator_command(
        self, game: Game, emulator: Any, mapping: Any
    ) -> List[str]:
        """
        Build the command line for launching an emulator.

        Args:
            game: Game to launch
            emulator: EmulatorDefinition
            mapping: PlatformEmulatorMapping

        Returns:
            Command line as list of strings

        Raises:
            FileNotFoundError: If emulator executable not found
            ValueError: If no ROM path found
        """
        # Resolve emulator executable path
        launchbox_root = self._get_launchbox_root()
        emulator_exe = emulator.resolve_path(launchbox_root)

        if not emulator_exe.exists():
            raise FileNotFoundError(f"Emulator not found: {emulator_exe}")

        # Build command line (optimized: pre-allocated list)
        command = [str(emulator_exe)]

        # Add command line args: mapping-level overrides emulator-level,
        # but fall back to emulator-level if mapping has none.
        # LaunchBox stores flags at EITHER level (e.g., Cemu has "-f -g"
        # on the Emulator object, not the EmulatorPlatform mapping).
        effective_cmd_line = mapping.command_line or getattr(emulator, 'command_line', '') or ''
        if effective_cmd_line:
            command.extend(shlex.split(effective_cmd_line))

        # Add ROM path (resolve relative paths against LaunchBox root)
        rom_path = self._get_rom_path(game)
        try:
            rp = str(rom_path).replace('\\', '/')
            is_abs = bool((len(rp) >= 3 and rp[1] == ':' and rp[2] == '/') or rp.startswith('/mnt/'))
            if is_abs:
                rom_final = Path(rp)
            else:
                base = self._get_launchbox_root()
                rom_final = (base / rp).resolve()
        except Exception:
            rom_final = Path(str(rom_path))
        command.append(str(rom_final))

        return command

    def _get_launchbox_root(self) -> Path:
        """Get the LaunchBox root directory."""
        if self.emulator_config and self.emulator_config.launchbox_root:
            return Path(self.emulator_config.launchbox_root)
        return LaunchBoxPaths.LAUNCHBOX_ROOT

    @staticmethod
    def _get_rom_path(game: Game) -> str:
        """
        Get the ROM path for a game with efficient checking.

        Args:
            game: Game object

        Returns:
            ROM path as string

        Raises:
            ValueError: If no ROM path found
        """
        # Optimized: check most likely path first
        if game.application_path:
            return game.application_path
        elif game.rom_path:
            return game.rom_path
        else:
            raise ValueError(f"No ROM path found for game: {game.title}")

    def _execute_emulator(self, command: List[str], emulator: Any) -> None:
        """
        Execute the emulator command with proper error handling.

        Args:
            command: Command line as list of strings
            emulator: EmulatorDefinition for working directory
        """
        logger.info(f"Launching with detected emulator: {emulator.title}")
        logger.debug(f"Command (before conversion): {' '.join(command)}")

        # Convert WSL paths to Windows paths if running in WSL
        win_command = _convert_wsl_paths_for_windows(command)
        logger.info(f"Command (after conversion): {' '.join(win_command)}")

        # Determine working directory
        emulator_exe = Path(command[0])
        working_dir = self._get_working_directory(emulator, emulator_exe)

        # Keep working directory in WSL format - subprocess.Popen needs WSL path
        wsl_cwd = str(working_dir) if working_dir else None

        # Launch with proper error handling
        try:
            # OpenGL/DirectX emulators (e.g. Supermodel) need full process
            # detachment via cmd.exe /c start — direct subprocess.Popen
            # prevents SDL/OpenGL from hooking into the Windows DWM + GPU.
            emu_title = getattr(emulator, 'title', '') or ''
            needs_detach = 'supermodel' in emu_title.lower() or 'supermodel' in str(command[0]).lower()

            if needs_detach:
                # Route through the Launcher Agent — a separate process running
                # in a clean interactive session without poisoned console handles.
                # Required because run-backend.bat redirects stdout/stderr to a
                # log file, which taints the entire process tree and prevents
                # SDL/OpenGL from initialising.
                agent_result = _launch_via_agent(win_command, cwd=wsl_cwd)
                if agent_result.get("ok"):
                    logger.info("[DetectedEmu] Launched %s via agent, PID=%s",
                                emu_title, agent_result.get('pid'))
                else:
                    raise RuntimeError(
                        f"Launcher Agent failed for {emu_title}: "
                        f"{agent_result.get('error', 'unknown')}"
                    )
            elif working_dir and working_dir.exists():
                subprocess.Popen(win_command, cwd=wsl_cwd)
            else:
                if working_dir:
                    logger.warning(
                        f"Working directory {working_dir} doesn't exist, "
                        "launching without cwd"
                    )
                subprocess.Popen(win_command)
        except OSError as e:
            raise RuntimeError(f"Failed to launch emulator: {e}")

    @staticmethod
    def _get_working_directory(emulator: Any, emulator_exe: Path) -> Optional[Path]:
        """
        Determine the working directory for emulator execution.

        Args:
            emulator: EmulatorDefinition
            emulator_exe: Path to emulator executable

        Returns:
            Path to working directory or None
        """
        if hasattr(emulator, 'working_directory') and emulator.working_directory:
            return Path(emulator.working_directory)
        return emulator_exe.parent

    @staticmethod
    def _launch_via_cli(game: Game) -> dict:
        """
        Launch via CLI_Launcher.exe (DEPRECATED).
        NOTE: CLI_Launcher.exe NOT FOUND on A: drive as of 2025-10-06.
        """
        cli_exe = LaunchBoxPaths.CLI_LAUNCHER_EXE

        if not cli_exe.exists():
            raise FileNotFoundError(f"CLI_Launcher.exe not found: {cli_exe}")

        # CLI_Launcher.exe -game "Game Title" -platform "Platform Name"
        command = [
            str(cli_exe),
            "-game", game.title,
            "-platform", game.platform,
        ]

        subprocess.Popen(command, cwd=cli_exe.parent)

        return {
            "success": True,
            "command": " ".join(command),
        }

    def _launch_via_launchbox(self, game: Game) -> Dict[str, Any]:
        """
        Launch via LaunchBox.exe with game filter (LAST RESORT).

        Args:
            game: Game to launch

        Returns:
            Dict with success status and command

        Raises:
            FileNotFoundError: If LaunchBox.exe not found
        """
        platform_key = normalize_key(getattr(game, "platform", "") or "")
        if platform_key in {"daphne", "hypseus", "laserdisc"}:
            return {
                "success": False,
                "message": f"LaunchBox fallback disabled for direct-only platform: {game.platform}",
            }

        lb_exe = LaunchBoxPaths.LAUNCHBOX_EXE

        if not lb_exe.exists():
            raise FileNotFoundError(f"LaunchBox.exe not found: {lb_exe}")

        # LaunchBox.exe supports command line parameters
        command = [str(lb_exe), game.title]

        # WSL interop: Use cmd.exe to launch Windows executables from WSL
        import platform
        if platform.system() == 'Linux' and 'microsoft' in platform.release().lower():
            # Running in WSL - use cmd.exe to launch Windows executables
            # Convert /mnt/a path to A:\ for Windows
            # Convert /mnt/x path to X:\ for Windows
            windows_exe = str(lb_exe)
            if windows_exe.startswith('/mnt/') and len(windows_exe) > 6:
                 drive = windows_exe[5].upper()
                 path_part = windows_exe[7:].replace('/', '\\')
                 windows_exe = f"{drive}:\\{path_part}"
            else:
                 # Fallback/already windows format
                 windows_exe = windows_exe.replace('/', '\\')

            windows_cmd = f'cmd.exe /c start "" "{windows_exe}" "{game.title}"'
            subprocess.Popen(windows_cmd, shell=True)
        else:
            # Native Windows or other OS
            subprocess.Popen(command, cwd=str(lb_exe.parent), shell=False)

        return {
            "success": True,
            "command": " ".join(command),
        }

    # ── Stderr Trap: 1.5s Watchdog ──────────────────────────────────────

    @staticmethod
    def _launch_with_stderr_trap(
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Launch a subprocess with stderr capture and a 1.5s watchdog.

        Wraps ``subprocess.Popen`` with ``stdout=PIPE, stderr=PIPE``.
        After 1.5 seconds:
        - If the process is still running → launch is healthy, release pipes.
        - If the process exited with code 0 → clean exit.
        - If the process exited with non-zero code → capture up to 4 KB stderr.

        Returns a ``StderrTrapResult`` dict:
            success (bool), command (str), return_code (int|None),
            stderr (str, ≤4 KB), timestamp (str ISO 8601).
        """
        from datetime import datetime, timezone

        WATCHDOG_SECONDS = 1.5
        MAX_STDERR_BYTES = 4096
        cmd_str = " ".join(command)
        ts = datetime.now(timezone.utc).isoformat()

        logger.info("[StderrTrap] Launching: %s", cmd_str[:120])

        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as exc:
            logger.error("[StderrTrap] Popen failed: %s", exc)
            return {
                "success": False,
                "command": cmd_str,
                "return_code": -1,
                "stderr": str(exc),
                "timestamp": ts,
            }

        # Wait up to 1.5s for early crash
        try:
            proc.wait(timeout=WATCHDOG_SECONDS)
        except subprocess.TimeoutExpired:
            # Process still running after watchdog window → healthy launch
            logger.info(
                "[StderrTrap] Process PID %d still running after %.1fs — launch OK",
                proc.pid, WATCHDOG_SECONDS,
            )
            # Release pipes in a background thread so they don't block
            def _drain():
                try:
                    proc.stdout.close()
                    proc.stderr.close()
                except Exception:
                    pass
            threading.Thread(target=_drain, daemon=True).start()
            return {
                "success": True,
                "command": cmd_str,
                "return_code": None,
                "stderr": "",
                "timestamp": ts,
                "pid": proc.pid,
            }

        # Process exited within 1.5s
        exit_code = proc.returncode
        if exit_code == 0:
            logger.info("[StderrTrap] Process exited cleanly (code 0)")
            return {
                "success": True,
                "command": cmd_str,
                "return_code": 0,
                "stderr": "",
                "timestamp": ts,
            }

        # Non-zero exit — capture stderr (bounded at 4 KB)
        stderr_output = ""
        try:
            raw = proc.stderr.read(MAX_STDERR_BYTES) if proc.stderr else b""
            stderr_output = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("[StderrTrap] Failed to read stderr: %s", exc)

        logger.warning(
            "[StderrTrap] Process crashed (code %d). stderr: %s",
            exit_code, stderr_output[:200],
        )
        return {
            "success": False,
            "command": cmd_str,
            "return_code": exit_code,
            "stderr": stderr_output,
            "timestamp": ts,
        }

    def _launch_direct(self, game: Game, profile_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Direct emulator launch for specific platforms.
        
        ARCHITECTURE (2025-12-11): Direct-to-Emulator Model
        ====================================================
        This is the PRIMARY launch path for Pegasus and future frontends.
        Pegasus -> Arcade Assistant -> Emulator (no LaunchBox in chain).
        
        Supports:
        - MAME for Arcade platforms
        - RetroArch for console platforms (ALWAYS enabled)
        - Other adapters (PCSX2, TeknoParrot, etc.)

        Args:
            game: Game to launch
            profile_hint: Optional profile (e.g., 'lightgun')

        Returns:
            Dict with success status and command

        Raises:
            ValueError: If no ROM path found
            NotImplementedError: If platform not supported
            FileNotFoundError: If ROM or emulator not found
        """
        # Concurrency limit
        self._direct_sem.acquire()
        try:
            # Log entry point for diagnostics
            logger.info(f"[DIRECT] Attempting launch: title='{game.title}', platform='{game.platform}', profile={profile_hint}")
            
            # -------------------------------------------------------------
            # GENRE PROFILE: Detect and log the applicable genre profile
            # This enables "configure once, apply by genre" functionality
            # -------------------------------------------------------------
            applied_genre_profile = None
            try:
                from backend.services.genre_profile_service import get_genre_profile_service
                genre_service = get_genre_profile_service()
                
                # Get genre from game metadata (if available from LaunchBox)
                game_genre = getattr(game, 'genre', None)
                
                # Lookup matching profile
                profile_key, profile = genre_service.get_profile_for_game(
                    game_id=getattr(game, 'id', None),
                    game_title=game.title,
                    genre=game_genre,
                    platform=game.platform,
                )
                
                if profile_key and profile_key != "default":
                    applied_genre_profile = profile_key
                    logger.info(
                        f"[GENRE] Matched profile '{profile_key}' for '{game.title}' "
                        f"(genre={game_genre or 'unknown'}, platform={game.platform})"
                    )
                    # TODO: Future - apply LED profile and emulator-specific mappings
                    # led_profile = genre_service.get_led_profile(profile_key)
                    # if led_profile:
                    #     apply_led_profile(led_profile)
                else:
                    logger.debug(f"[GENRE] Using default profile for '{game.title}'")
            except Exception as e:
                logger.debug(f"[GENRE] Genre profile lookup skipped: {e}")
            # -------------------------------------------------------------
            
            # MAME path for Arcade (including gun games) plus legacy Daphne titles that still point to MAME ROM zips
            app_path_str = str(getattr(game, "application_path", "") or "").lower()
            daphne_uses_mame = (
                game.platform == "Daphne"
                and app_path_str.endswith((".zip", ".7z"))
            )
            daphne_wrapper_launch = app_path_str.endswith((".ahk", ".bat", ".cmd"))
            platform_key = normalize_key(getattr(game, "platform", "") or "")
            if platform_key in {"arcade", "arcade mame", "mame"} or daphne_uses_mame:
                rom_path = self._resolve_rom_path(game)
                command = self._build_mame_command(rom_path)
                mame_exe = Path(command[0])
                logger.info(f"[DIRECT] MAME launch: exe={mame_exe}, rom={rom_path}, cwd={mame_exe.parent}")
                # Convert paths for WSL
                win_command = _convert_wsl_paths_for_windows(command)
                # Keep cwd in WSL format - subprocess.Popen needs WSL path
                wsl_cwd = str(mame_exe.parent)
                if dry_run_enabled():
                    logger.info(f"[DIRECT] MAME DRY-RUN: {' '.join(win_command)}")
                    return {"success": True, "command": " ".join(win_command), "message": "dry-run"}
                trap_result = self._launch_with_stderr_trap(win_command, cwd=wsl_cwd)
                if trap_result["success"]:
                    logger.info(f"[DIRECT] MAME launch SUCCESS: {' '.join(win_command)}")
                    return {"success": True, "command": " ".join(win_command)}
                else:
                    logger.warning(f"[DIRECT] MAME launch FAILED (code {trap_result['return_code']})")
                    return {
                        "success": False,
                        "command": " ".join(win_command),
                        "stderr_trap": trap_result,
                    }

            # Daphne/Hypseus laserdisc direct launch
            if platform_key == "daphne" and not daphne_uses_mame and not daphne_wrapper_launch:
                aa_root_path = get_drive_root_or_none() or Path(LaunchBoxPaths.LAUNCHBOX_ROOT).parent

                exe = aa_root_path / "Emulators" / "Hypseus" / "Hypseus Singe" / "hypseus.exe"
                homedir = aa_root_path / "Roms" / "DAPHNE"

                daphne_game_map = {
                    "astron belt": ("astron", homedir / "framefile" / "astron.txt"),
                    "badlands": ("badlands", homedir / "framefile" / "badlands.txt"),
                    "bega's battle": ("bega", homedir / "framefile" / "bega.txt"),
                    "cobra command": ("cobraab", homedir / "framefile" / "cobraab.txt"),
                    "dragons lair": ("lair", homedir / "vldp" / "lair" / "lair.txt"),
                    "dragon's lair hd": ("lair", homedir / "vldp" / "lair" / "lair.txt"),
                    "dragon's lair ii hd": ("lair2", homedir / "vldp" / "lair2" / "dl2-framefile.txt"),
                    "galaxy ranger": ("galaxy", homedir / "framefile" / "galaxy.txt"),
                    "gp world": ("gpworld", homedir / "framefile" / "gpworld.txt"),
                    "inter stellar": ("interstellar", homedir / "framefile" / "interstellar.txt"),
                    "mach 3": ("mach3", homedir / "framefile" / "mach3.txt"),
                    "road blaster": ("roadblaster", homedir / "framefile" / "roadblaster.txt"),
                    "space ace hd": ("ace", homedir / "vldp" / "ace" / "ace.txt"),
                    "super don quix-ote": ("sdq", homedir / "framefile" / "sdq.txt"),
                    "thayer's quest": ("tq", homedir / "framefile" / "tq.txt"),
                    "us vs them": ("uvt", homedir / "framefile" / "uvt.txt"),
                }

                # Allow lookup by LaunchBox title, Hypseus ROM name, or framefile stem.
                for _, mapping in list(daphne_game_map.items()):
                    mapped_game_name, mapped_framefile = mapping
                    daphne_game_map.setdefault(mapped_game_name.lower(), mapping)
                    daphne_game_map.setdefault(Path(mapped_framefile).stem.lower(), mapping)

                app_ref = str(getattr(game, "application_path", "") or getattr(game, "rom_path", "") or "").strip()
                app_ref_path = Path(app_ref.replace("\\", "/")) if app_ref else Path()
                app_ext = app_ref_path.suffix.lower()

                framefile: Optional[Path] = None
                game_name: Optional[str] = None
                primary_lookup = app_ref_path.stem.lower() if app_ref else ""

                if app_ext in {".txt", ".m2v"}:
                    framefile = app_ref_path
                    if not framefile.is_absolute():
                        framefile = (LaunchBoxPaths.LAUNCHBOX_ROOT / framefile).resolve()
                    alias = daphne_game_map.get(framefile.stem.lower())
                    if alias:
                        game_name = alias[0]
                    else:
                        cleaned = "".join(ch for ch in framefile.stem.lower() if ch.isalnum())
                        game_name = cleaned or framefile.stem.lower()
                else:
                    title_lookup = str(getattr(game, "title", "") or "").strip().lower()
                    alias = None
                    for candidate in (primary_lookup, title_lookup):
                        if candidate and candidate in daphne_game_map:
                            alias = daphne_game_map[candidate]
                            break
                    if not alias:
                        raise ValueError(f"No Hypseus mapping for Daphne game: {primary_lookup}")
                    game_name, framefile = alias

                if framefile is None:
                    raise ValueError(f"No framefile resolved for Daphne game: {primary_lookup or game.title}")

                command = [
                    str(exe),
                    game_name,
                    "vldp",
                    "-homedir", str(homedir),
                    "-framefile", str(framefile),
                    "-fullscreen",
                    "-x", "1920",
                    "-y", "1080",
                ]
                hypseus_exe = Path(command[0])
                logger.info(
                    f"[DIRECT] Hypseus launch: exe={hypseus_exe}, game={game_name}, framefile={framefile}, cwd={hypseus_exe.parent}"
                )
                win_command = _convert_wsl_paths_for_windows(command)
                wsl_cwd = str(hypseus_exe.parent)
                if dry_run_enabled():
                    logger.info(f"[DIRECT] Hypseus DRY-RUN: {' '.join(win_command)}")
                    return {"success": True, "command": " ".join(win_command), "message": "dry-run"}
                trap_result = self._launch_with_stderr_trap(win_command, cwd=wsl_cwd)
                if trap_result["success"]:
                    logger.info(f"[DIRECT] Hypseus launch SUCCESS: {' '.join(win_command)}")
                    return {"success": True, "command": " ".join(win_command)}
                logger.warning(f"[DIRECT] Hypseus launch FAILED (code {trap_result['return_code']})")
                return {
                    "success": False,
                    "command": " ".join(win_command),
                    "stderr_trap": trap_result,
                }

            # Try registered adapters (e.g., RetroArch) for consoles
            manifest = self._load_launchers_config() or {}
            last_msg: Optional[str] = None
            adapters_tried = []
            has_registered_adapter = False
            for adapter in ADAPTERS:
                try:
                    if adapter.can_handle(game, manifest):
                        has_registered_adapter = True
                        break
                except Exception:
                    continue

            for adapter in ADAPTERS:
                adapter_name = getattr(adapter, "__name__", str(adapter)).split('.')[-1]
                # Check if adapter can handle this game's platform FIRST
                try:
                    can_handle = adapter.can_handle(game, manifest)
                    if not can_handle:
                        continue
                    adapters_tried.append(adapter_name)
                except Exception as e:
                    logger.debug(f"[DIRECT] Adapter {adapter_name} can_handle() raised: {e}")
                    continue

                # Adapter claims it can handle this platform - try to resolve config
                logger.info(f"[DIRECT] Trying adapter: {adapter_name} for platform={game.platform}")
                try:
                    cfg = adapter.resolve(game, manifest)
                except Exception as e:
                    logger.warning(f"[DIRECT] Adapter {adapter_name} resolve() failed: {e}")
                    cfg = {"success": False, "message": str(e)}

                if isinstance(cfg, dict) and not cfg.get("success") and cfg.get("message"):
                    last_msg = str(cfg.get("message"))
                exe = (cfg or {}).get("exe")
                args = list((cfg or {}).get("args", []))
                cwd = (cfg or {}).get("cwd")
                
                # Log adapter resolution result
                if exe:
                    core = (cfg or {}).get("core", "N/A")
                    romfile = (cfg or {}).get("romfile", args[-1] if args else "N/A")
                    logger.info(f"[DIRECT] Adapter {adapter_name} resolved: exe={exe}, core={core}, rom={romfile}, cwd={cwd}")

                # PCSX2 auto-extraction: if ROM is .zip/.7z, extract to temp and swap path
                # NOTE: PCSX2-qt supports .gz (gzip) natively, so skip extraction for .gz files
                cleanup_cb = None
                try:
                    adapter_name = getattr(adapter, "__name__", "").lower()
                    if exe and "pcsx2" in adapter_name:
                        try:
                            from backend.services.pcsx2_preflight import kill_running_pcsx2, write_upscale_override

                            kill_running_pcsx2()
                            write_upscale_override(game, exe, upscale_multiplier=2)
                        except Exception as preflight_exc:
                            logger.warning("PCSX2 preflight setup skipped: %s", preflight_exc)

                        # Determine romfile argument (prefer explicit key from cfg)
                        romfile = (cfg or {}).get("romfile") or (args[-1] if args else None)
                        if romfile:
                            src = Path(str(romfile))
                            
                            # PCSX2-qt supports .gz natively - skip extraction entirely
                            if src.suffix.lower() == '.gz' and src.exists():
                                logger.info(f"PCSX2: Using .gz directly (native support): {src}")
                                # args already has the correct path, no extraction needed
                            elif src.suffix.lower() == '.gz':
                                # .gz file doesn't exist at expected path, try to resolve
                                actual, how = resolve_rom_path(src)
                                if actual and actual.suffix.lower() == '.gz':
                                    logger.info(f"PCSX2: Using resolved .gz directly: {actual}")
                                    if args:
                                        args[-1] = str(actual)
                                elif not actual:
                                    raise FileNotFoundError(f"ROM not found for {src.name}")
                            else:
                                # Non-.gz files: try extraction if needed
                                ovr = self._ps2_lookup_override(getattr(game, 'id', ''), str(src))
                                if ovr and Path(ovr).exists():
                                    actual = Path(ovr)
                                    how = "override"
                                else:
                                    actual, how = resolve_rom_path(src)
                                if not actual:
                                    raise FileNotFoundError(f"ROM not found for {src.name} (checked alt extensions)")
                                
                                # Skip extraction for .gz files (PCSX2 native support)
                                if actual.suffix.lower() == '.gz':
                                    logger.info(f"PCSX2: Using .gz directly (native support): {actual}")
                                    if args:
                                        args[-1] = str(actual)
                                elif actual.suffix.lower() in ('.zip', '.7z'):
                                    # Only extract .zip/.7z, not .gz
                                    try:
                                        min_free_gb = float(os.getenv("AA_EXTRACT_MIN_FREE_GB", "10"))
                                    except Exception:
                                        min_free_gb = 10.0
                                    tmp_base = aa_tmp_dir()
                                    try:
                                        usage = shutil.disk_usage(tmp_base)
                                        free_gb = usage.free / (1024 ** 3)
                                        if free_gb < min_free_gb:
                                            raise RuntimeError(f"Insufficient free space: {free_gb:.1f} GB < {min_free_gb} GB")
                                    except Exception as e:
                                        logger.debug(f"AA_EXTRACT_MIN_FREE_GB check skipped: {e}")

                                    result: ExtractResult = extract_if_archive(actual, tmp_base)
                                    iso_path = str(result.extracted_path) if result.extracted_path else str(actual)
                                    if result.used_tool:
                                        logger.info("PCSX2: resolved=%s actual=%s used_tool=%s", how, actual.name, result.used_tool)
                                    if args:
                                        args[-1] = iso_path

                                    if result.temp_root:
                                        base = aa_tmp_dir().resolve()
                                        root = result.temp_root.resolve()

                                        def _cleanup():
                                            try:
                                                if str(root).startswith(str(base)):
                                                    shutil.rmtree(root, ignore_errors=True)
                                                    logger.debug("PCSX2 temp cleaned: %s", str(root))
                                            except Exception as ce:
                                                logger.warning("PCSX2 temp cleanup failed: %s", ce)

                                        cleanup_cb = _cleanup

                        if "-batch" not in args:
                            args.insert(min(len(args), 1), "-batch")
                except Exception as e:
                    logger.warning(f"PCSX2 auto-extract preparation skipped: {e}")

                # Profile-aware minimal overrides (safe defaults only)
                try:
                    if profile_hint and exe:
                        adapter_name = getattr(adapter, "__name__", "").lower()
                        policy = self._get_routing_policy()
                        profiles = (policy.get('profiles') or {}) if isinstance(policy, dict) else {}
                        prof = (profiles.get(profile_hint) or {}) if isinstance(profiles, dict) else {}
                        if 'retroarch' in adapter_name:
                            # Harmless fullscreen help when requested by profile
                            if prof.get('exclusive_fullscreen') and "--fullscreen" not in args and "-f" not in args:
                                args.insert(0, "--fullscreen")
                        # Future: teknoparrot ahk_wrapper handled in dedicated adapter
                except Exception:
                    pass
                # Generic temp cleanup for adapters that extracted content to temp
                try:
                    ex_root = (cfg or {}).get("extracted_root")
                    if ex_root:
                        base = aa_tmp_dir().resolve()
                        root = Path(str(ex_root)).resolve()
                        def _cleanup_extracted():
                            try:
                                if str(root).startswith(str(base)):
                                    shutil.rmtree(root, ignore_errors=True)
                                    logger.debug("temp cleaned: %s", str(root))
                            except Exception:
                                pass
                        if cleanup_cb:
                            prev = cleanup_cb
                            def _chain():
                                try:
                                    prev()
                                finally:
                                    _cleanup_extracted()
                            cleanup_cb = _chain
                        else:
                            cleanup_cb = _cleanup_extracted
                except Exception:
                    pass

                if exe:
                    # Respect global adapter dry-run: do not spawn, just report command
                    if dry_run_enabled():
                        logger.info(f"[DIRECT] Adapter {adapter_name} DRY-RUN: {' '.join([exe, *[str(a) for a in args]])}")
                        return {"success": True, "command": " ".join([exe, *[str(a) for a in args]]), "notes": (cfg or {}).get("notes", "")}
                    no_pipe = bool((cfg or {}).get("no_pipe"))
                    self._run_adapter_process(
                        exe,
                        args,
                        cwd,
                        cleanup_cb,
                        no_pipe=no_pipe,
                        skip_agent=has_registered_adapter,
                    )
                    logger.info(f"[DIRECT] Adapter {adapter_name} launch SUCCESS: {' '.join([exe, *[str(a) for a in args]])}")
                    return {"success": True, "command": " ".join([exe, *[str(a) for a in args]]), "notes": (cfg or {}).get("notes", "")}

            # No adapter handled this platform
            logger.warning(f"[DIRECT] No adapter found for platform={game.platform}, adapters_tried={adapters_tried}")
            if last_msg:
                logger.warning(f"[DIRECT] Last adapter message: {last_msg}")
                return {"success": False, "message": last_msg}
            raise NotImplementedError(f"Direct launch not supported for platform: {game.platform}")
        finally:
            try:
                self._direct_sem.release()
            except Exception:
                pass

    @staticmethod
    def _run_adapter_process(
        exe: str,
        args: List[str],
        cwd: Optional[str],
        on_exit: Optional[Callable[[], None]] = None,
        *,
        no_pipe: bool = False,
        skip_agent: bool = False,
    ) -> None:
        """Execute adapter-provided command line.

        Uses working directory if provided; otherwise defaults to exe parent.
        Works in Windows and WSL interop environments.

        Args:
            no_pipe: If True, launch without stdout/stderr PIPE capture.
                     Required for OpenGL/DirectX emulators (e.g. Supermodel)
                     that fail with 'OpenGL not available' when pipes are attached.
        """
        workdir = Path(cwd) if cwd else Path(exe).parent
        exe_name = Path(str(exe)).name.lower()
        daphne_wrapper_bypass = exe_name in {
            "daphne",
            "daphne.exe",
            "hypseus",
            "hypseus.exe",
            "singe",
            "singe.exe",
            "singe-v2.00-windows-x86_64.exe",
        }
        try:
            # WSL interop: if running under WSL Linux and exe looks like Windows path, use cmd.exe start
            if platform.system() == 'Linux' and 'microsoft' in platform.release().lower() and (':' in exe or exe.lower().startswith('/mnt/')):
                # Convert /mnt/x/... to X:\... for Windows
                win_exe = exe
                if exe.lower().startswith('/mnt/') and len(exe) > 6:
                    drive = exe[5].upper()
                    rest = exe[7:].replace('/', '\\')
                    sep = '\\' if (rest and not rest.startswith('\\')) else ''
                    win_exe = f"{drive}:{sep}{rest}"
                # Convert any /mnt/x/... args to Windows paths as well
                def _arg_to_win(a: Any) -> str:
                    try:
                        s = str(a)
                    except Exception:
                        return str(a)
                    low = s.lower()
                    if low.startswith('/mnt/') and len(s) > 6:
                        d = s[5].upper()
                        rest = s[7:].replace('/', '\\')
                        sep2 = '\\' if (rest and not rest.startswith('\\')) else ''
                        return f"{d}:{sep2}{rest}"
                    # Also normalize X:/ style into X:\ style
                    if len(s) >= 3 and s[1] == ':' and s[2] == '/':
                        return s.replace('/', '\\')
                    return s
                win_args = [_arg_to_win(a) for a in args]
                # Quote arguments for Windows shell
                safe_args = " ".join([f'"{str(a)}"' for a in win_args])
                windows_cmd = f'cmd.exe /c start "" "{win_exe}" {safe_args}'
                subprocess.Popen(windows_cmd, shell=True)
                if on_exit:
                    # No process handle; schedule delayed cleanup as best-effort
                    try:
                        ttl = int(os.getenv('AA_TMP_CLEANUP_TTL_S', '900'))
                    except Exception:
                        ttl = 900
                    def _delayed():
                        try:
                            time.sleep(max(1, ttl))
                        finally:
                            try:
                                on_exit()
                            except Exception:
                                pass
                    threading.Thread(target=_delayed, daemon=True).start()
            elif no_pipe and not daphne_wrapper_bypass and skip_agent:
                logger.info("[Adapter] Launching registered adapter without agent or pipes: %s", exe)
                full_command = [exe, *args]
                win_command = _convert_wsl_paths_for_windows(full_command)
                wsl_cwd = str(workdir)
                if "supermodel" in exe_name:
                    agent_result = _launch_via_agent(win_command, cwd=wsl_cwd)
                    if agent_result.get("ok"):
                        logger.info("[Adapter] Launched Supermodel via auto-started agent, PID=%s", agent_result.get('pid'))
                    else:
                        raise RuntimeError(
                            f"Launcher Agent failed: {agent_result.get('error', 'unknown')}"
                        )
                    if on_exit:
                        try:
                            ttl = int(os.getenv('AA_TMP_CLEANUP_TTL_S', '900'))
                        except Exception:
                            ttl = 900
                        def _delayed_agent():
                            try:
                                time.sleep(max(1, ttl))
                            finally:
                                try:
                                    on_exit()
                                except Exception:
                                    pass
                        threading.Thread(target=_delayed_agent, daemon=True).start()
                    return
                create_new_process_group = 0x00000200
                detached_process = 0x00000008
                subprocess.Popen(
                    win_command,
                    cwd=wsl_cwd,
                    creationflags=create_new_process_group | detached_process,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if on_exit:
                    try:
                        ttl = int(os.getenv('AA_TMP_CLEANUP_TTL_S', '900'))
                    except Exception:
                        ttl = 900
                    def _delayed_skip_agent():
                        try:
                            time.sleep(max(1, ttl))
                        finally:
                            try:
                                on_exit()
                            except Exception:
                                pass
                    threading.Thread(target=_delayed_skip_agent, daemon=True).start()
            elif no_pipe and not daphne_wrapper_bypass:
                # Route through the Launcher Agent (see _execute_emulator).
                full_command = [exe, *args]
                win_command = _convert_wsl_paths_for_windows(full_command)
                wsl_cwd = str(workdir)
                agent_result = _launch_via_agent(win_command, cwd=wsl_cwd)
                if agent_result.get("ok"):
                    logger.info("[Adapter] Launched via agent, PID=%s", agent_result.get('pid'))
                else:
                    raise RuntimeError(
                        f"Launcher Agent failed: {agent_result.get('error', 'unknown')}"
                    )
                if on_exit:
                    # No direct process handle with cmd.exe /c start; use delayed cleanup
                    try:
                        ttl = int(os.getenv('AA_TMP_CLEANUP_TTL_S', '900'))
                    except Exception:
                        ttl = 900
                    def _delayed_np():
                        try:
                            time.sleep(max(1, ttl))
                        finally:
                            try:
                                on_exit()
                            except Exception:
                                pass
                    threading.Thread(target=_delayed_np, daemon=True).start()
            elif no_pipe and daphne_wrapper_bypass:
                logger.info("[Adapter] Launching Daphne/Singe wrapper without agent or pipes: %s", exe)
                safe_args = _absolutize_daphne_wrapper_args([str(a) for a in args], workdir)
                full_command = [exe, *safe_args]
                win_command = _convert_wsl_paths_for_windows(full_command)
                wsl_cwd = str(workdir)
                subprocess.Popen(
                    win_command,
                    cwd=wsl_cwd,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
                if on_exit:
                    try:
                        ttl = int(os.getenv('AA_TMP_CLEANUP_TTL_S', '900'))
                    except Exception:
                        ttl = 900
                    def _delayed_np_bypass():
                        try:
                            time.sleep(max(1, ttl))
                        finally:
                            try:
                                on_exit()
                            except Exception:
                                pass
                    threading.Thread(target=_delayed_np_bypass, daemon=True).start()
            else:
                # Convert paths for WSL
                full_command = [exe, *args]
                win_command = _convert_wsl_paths_for_windows(full_command)
                # Keep working directory in WSL format - subprocess.Popen needs WSL path
                wsl_cwd = str(workdir)
                # Use stderr trap for crash detection
                trap_result = GameLauncher._launch_with_stderr_trap(win_command, cwd=wsl_cwd)
                if not trap_result["success"]:
                    logger.warning(
                        "[Adapter] Process crashed (code %s): %s",
                        trap_result.get("return_code"),
                        trap_result.get("stderr", "")[:200],
                    )
                    # Store trap result for remediation (caller can inspect)
                    GameLauncher._last_trap_result = trap_result
                if on_exit:
                    # Schedule cleanup — process already exited or is running
                    if trap_result.get("pid"):
                        # Process still running, wait for it
                        def _await_then_cleanup(pid):
                            try:
                                import psutil
                                p = psutil.Process(pid)
                                p.wait()
                            except Exception:
                                pass
                            finally:
                                try:
                                    on_exit()
                                except Exception:
                                    pass
                        threading.Thread(target=_await_then_cleanup, args=(trap_result["pid"],), daemon=True).start()
                    else:
                        # Process already exited, run cleanup now
                        try:
                            on_exit()
                        except Exception:
                            pass
        except OSError as e:
            raise RuntimeError(f"Failed to launch adapter process: {e}")

    @staticmethod
    def _resolve_rom_path(game: Game) -> Path:
        """
        Resolve the ROM path for a game with fallback locations.

        Args:
            game: Game object

        Returns:
            Path to ROM file

        Raises:
            ValueError: If no ROM path in game
            FileNotFoundError: If ROM file not found
        """
        if not game.rom_path:
            raise ValueError(f"No ROM path for game: {game.title}")

        rom_path_str = str(game.rom_path).replace('\\', '/')
        rom_path = Path(rom_path_str)

        # If path is relative (starts with ..), resolve against LaunchBox root
        if rom_path_str.startswith('..'):
            rom_path = (LaunchBoxPaths.LAUNCHBOX_ROOT / rom_path_str).resolve()
        # If path is not absolute, resolve against LaunchBox root
        elif not rom_path.is_absolute():
            rom_path = (LaunchBoxPaths.LAUNCHBOX_ROOT / rom_path_str).resolve()

        # If ROM doesn't exist, try alternate location for MAME (including gun games)
        platform_key = normalize_key(getattr(game, "platform", "") or "")
        if not rom_path.exists() and platform_key in {"arcade", "arcade mame", "mame"}:
            rom_name = rom_path.stem or game.title.replace(" ", "").lower()
            rom_path = LaunchBoxPaths.MAME_ROMS / f"{rom_name}.zip"

        if not rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {rom_path}")

        return rom_path

    @staticmethod
    def _build_mame_command(rom_path: Path) -> List[str]:
        """
        Build MAME command line with optimized arguments.

        Args:
            rom_path: Path to ROM file

        Returns:
            Command line as list of strings

        Raises:
            FileNotFoundError: If MAME executable not found
        """
        cfg = GameLauncher._load_launchers_config() or {}
        mame_cfg = ((cfg or {}).get("emulators", {}) or {}).get("mame", {})

        mame_candidates: List[Path] = []
        cfg_exe = mame_cfg.get("exe")
        if isinstance(cfg_exe, str) and cfg_exe.strip():
            mame_candidates.append(Path(cfg_exe))
        aa_root = get_drive_root_or_none()
        if aa_root is not None:
            mame_candidates.append(aa_root / "Emulators" / "MAME" / "mame.exe")
        mame_candidates.extend([
            LaunchBoxPaths.MAME_EMULATOR,
            LaunchBoxPaths.LAUNCHBOX_ROOT / "Emulators" / "MAME" / "mame.exe",
        ])
        mame_exe = next((candidate for candidate in mame_candidates if candidate.exists()), None)

        if not mame_exe:
            raise FileNotFoundError(
                "MAME emulator not found: "
                + ", ".join(str(candidate) for candidate in mame_candidates)
            )

        # MAME expects just the ROM name without extension
        rom_name = rom_path.stem

        # Add rompath so MAME knows where to find ROMs
        rom_folder = str(rom_path.parent)

        command = [str(mame_exe), "-rompath", rom_folder, rom_name]

        # QoL: merge flags from config/launchers.json if present
        try:
            mame_cfg = mame_cfg if isinstance(mame_cfg, dict) else {}
            # extra flags
            extra_flags = mame_cfg.get("flags", [])
            if isinstance(extra_flags, list):
                # only include strings
                command.extend([str(f) for f in extra_flags if isinstance(f, str) and f])

            # cheat support
            cheat = mame_cfg.get("cheat", {}) or {}
            if isinstance(cheat, dict) and cheat.get("enabled"):
                cheat_path = cheat.get("path")
                if isinstance(cheat_path, str) and cheat_path:
                    # Include path only if it exists on this system
                    # Handle WSL path translation for A:/ → /mnt/a/
                    cpath = cheat_path
                    try:
                        if platform.system() == 'Linux' and 'microsoft' in platform.release().lower():
                            if len(cpath) > 2 and cpath[1] == ':' and cpath[2] in ('\\', '/'):
                                drv = cpath[0].lower()
                                rest = cpath[3:].replace('\\', '/')
                                cpath = f"/mnt/{drv}/{rest}"
                        p = Path(cpath)
                        if p.exists():
                            command.extend(["-cheatpath", cheat_path])
                    except Exception:
                        # best-effort; ignore path existence errors
                        pass
                # Add -cheat flag when enabled
                command.append("-cheat")

            # Global QoL toggles
            qol = ((cfg or {}).get("global", {}) or {}).get("qol", {}) or {}
            # Skip nags: always add -skip_gameinfo when enabled
            if isinstance(qol.get("skip_nags"), bool) and qol.get("skip_nags"):
                if "-skip_gameinfo" not in command:
                    command.append("-skip_gameinfo")

            # Cheats: when enabled globally and path exists, add -cheat -cheatpath
            if isinstance(qol.get("cheats_enabled"), bool) and qol.get("cheats_enabled"):
                mame_cheat = ((qol.get("cheats") or {}).get("mame") or {}).get("path")
                if isinstance(mame_cheat, str) and mame_cheat:
                    cpath = mame_cheat
                    try:
                        if platform.system() == 'Linux' and 'microsoft' in platform.release().lower():
                            if len(cpath) > 2 and cpath[1] == ':' and cpath[2] in ('\\', '/'):
                                drv = cpath[0].lower()
                                rest = cpath[3:].replace('\\', '/')
                                cpath = f"/mnt/{drv}/{rest}"
                        if Path(cpath).exists():
                            if "-cheat" not in command:
                                command.append("-cheat")
                            command.extend(["-cheatpath", mame_cheat])
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"launchers.json not applied: {e}")

        return command

    _launchers_config_cache: Optional[dict] = None
    _launchers_config_mtime: Optional[float] = None

    @staticmethod
    def _canonicalize_launcher_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: GameLauncher._canonicalize_launcher_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [GameLauncher._canonicalize_launcher_value(v) for v in value]
        if not isinstance(value, str):
            return value

        text = value.strip()
        is_path_like = (
            "${AA_DRIVE_ROOT}" in text
            or "${LAUNCHBOX_ROOT}" in text
            or text.lower().startswith("/mnt/")
            or (len(text) > 2 and text[1] == ":" and text[2] in ("\\", "/"))
        )
        if not is_path_like:
            return value

        resolved = resolve_runtime_path(text)
        if resolved is not None:
            return str(resolved)
        return value

    @staticmethod
    def _canonicalize_launcher_config(config: Any) -> Any:
        return GameLauncher._canonicalize_launcher_value(config)

    @staticmethod
    def _load_launchers_config() -> Optional[dict]:
        """Load config/launchers.json from repo root if available.

        Caches content but invalidates when file mtime changes to reflect
        boolean toggles on next launch without restart.
        """

        candidates = [get_project_root() / 'config' / 'launchers.json']
        for fp in candidates:
            try:
                if fp.exists():
                    mtime = fp.stat().st_mtime
                    if (GameLauncher._launchers_config_cache is None) or (GameLauncher._launchers_config_mtime != mtime):
                        with open(fp, 'r', encoding='utf-8') as f:
                            raw = json.load(f)
                            GameLauncher._launchers_config_cache = GameLauncher._canonicalize_launcher_config(raw)
                            GameLauncher._launchers_config_mtime = mtime
                            logger.info(f"Loaded launcher config from {fp}")
                    break
            except Exception as e:
                logger.warning(f"Failed to read {fp}: {e}")
        return GameLauncher._launchers_config_cache

    def _launch_mock(self, game: Game) -> Dict[str, Any]:
        """
        Mock launcher for development/testing when AA_DEV_MODE=true.

        Simulates successful game launch without actually executing anything.
        Useful for:
        - Frontend development without LaunchBox/emulators installed
        - API testing and integration tests
        - Demo environments

        Args:
            game: Game object to "launch"

        Returns:
            Dict with success status and mock command
        """
        # Generate realistic-looking mock command based on platform
        mock_command = self._generate_mock_command(game)

        logger.info(f"[MOCK] Simulating launch of {game.title} ({game.platform})")
        logger.info(f"[MOCK] Generated command: {mock_command}")

        return {
            "success": True,
            "command": mock_command,
            "message": f"Mock launch successful for {game.title} on {game.platform}"
        }

    def _generate_mock_command(self, game: Game) -> str:
        """
        Generate realistic mock commands for different platforms.

        Args:
            game: Game object

        Returns:
            Realistic mock command string
        """
        # Platform-specific mock commands for realism
        platform_commands = {
            "Arcade": f"mock://mame.exe {game.title.lower().replace(' ', '')}",
            "Arcade MAME": f"mock://mame.exe {game.title.lower().replace(' ', '')}",
            "Nintendo Entertainment System": f"mock://nestopia.exe \"{game.rom_path or game.title}.nes\"",
            "Super Nintendo Entertainment System": f"mock://snes9x.exe \"{game.rom_path or game.title}.sfc\"",
            "Sega Genesis": f"mock://kega.exe \"{game.rom_path or game.title}.md\"",
            "Sony Playstation": f"mock://epsxe.exe -loadiso \"{game.rom_path or game.title}.iso\"",
            "Nintendo 64": f"mock://project64.exe \"{game.rom_path or game.title}.z64\"",
            "Nintendo Game Boy": f"mock://vba.exe \"{game.rom_path or game.title}.gb\"",
            "Nintendo Game Boy Advance": f"mock://vba.exe \"{game.rom_path or game.title}.gba\"",
            "Sega Dreamcast": f"mock://demul.exe -run=dc \"{game.rom_path or game.title}.cdi\"",
            "Sony PlayStation 2": f"mock://pcsx2.exe \"{game.rom_path or game.title}.iso\"",
        }

        # Return platform-specific command or generic fallback
        return platform_commands.get(
            game.platform,
            f"mock://launcher.exe --game \"{game.title}\" --platform \"{game.platform}\""
        )


# Singleton instance (performance optimization: avoid repeated initialization)
launcher = GameLauncher()
