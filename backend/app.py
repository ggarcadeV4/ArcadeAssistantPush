from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import sys
import platform
import uvicorn
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
import time
import json
import logging as _logging
from datetime import datetime
import threading
from glob import glob as _glob
from typing import Any, Dict, Optional

# ── Secrets vault (DPAPI — must load before any router reads env) ──────────
try:
    from secrets_loader import load_secrets as _load_vault_secrets
    _VAULT_AVAILABLE = True
except ImportError:
    _VAULT_AVAILABLE = False

# CRITICAL: Load .env BEFORE any imports that depend on AA_DRIVE_ROOT
# The a_drive_paths module evaluates AA_DRIVE_ROOT at import time!
def load_env_file():
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env_file()

# ── Load Tier 1 secrets from DPAPI vault ───────────────────────────────────
if _VAULT_AVAILABLE:
    _vault_loaded = _load_vault_secrets()
    if not _vault_loaded:
        _logging.getLogger("aa.startup").warning(
            "DPAPI vault not loaded — Supabase/fleet operations will use "
            ".env values only. Run 'python encrypt_secrets.py' to initialize "
            "the vault on this machine."
        )
else:
    _logging.getLogger("aa.startup").warning(
        "secrets_loader not found — running without DPAPI vault. "
        "Expected at: <AA_DRIVE_ROOT>/Arcade Assistant Local/secrets_loader.py"
    )

logger = _logging.getLogger("aa.startup")

print("DEBUG: .env file loaded")

# NOW safe to import modules that depend on AA_DRIVE_ROOT
from backend.constants.a_drive_paths import LaunchBoxPaths

LB_PLATFORMS_GLOB = str(LaunchBoxPaths.PLATFORMS_DIR / "*.xml")


def _example_windows_root(raw: str) -> str:
    if raw.startswith("/mnt/") and len(raw) >= 7:
        drive = raw[5].upper()
        rest = raw[6:].replace("/", "\\").lstrip("\\")
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return r"<Windows cabinet root path>"


def _example_wsl_root(raw: str) -> str:
    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return "/mnt/<drive>/arcade-assistant-root"

def _diagnose_path_mismatch():
    """Detect Windows Python + WSL path mismatches early in startup."""
    drive_root = os.getenv("AA_DRIVE_ROOT", "")
    if not drive_root:
        # No path set, let downstream validation handle it
        return

    # Detect the Python runtime environment
    is_windows_python = platform.system().lower() == "windows"

    # Detect path styles
    looks_like_wsl_path = drive_root.startswith("/mnt/")
    looks_like_windows_path = (":\\" in drive_root or ":/" in drive_root)

    # Check for mismatches
    if is_windows_python and looks_like_wsl_path:
        print("=" * 70)
        print("ERROR: PATH FORMAT MISMATCH DETECTED")
        print("=" * 70)
        print(f"You're running Windows Python but AA_DRIVE_ROOT is a WSL path:")
        print(f"  Current: {drive_root}")
        print()
        print("Solutions:")
        print("1. Run this through WSL: 'wsl python backend/app.py'")
        print("2. Or update AA_DRIVE_ROOT to a Windows path:")
        print(f"   Example for this configuration: {_example_windows_root(drive_root)}")
        print("=" * 70)
        sys.exit(1)

    if not is_windows_python and looks_like_windows_path:
        print("=" * 70)
        print("ERROR: PATH FORMAT MISMATCH DETECTED")
        print("=" * 70)
        print(f"You're running WSL/Linux Python but AA_DRIVE_ROOT is a Windows path:")
        print(f"  Current: {drive_root}")
        print()
        print("Solutions:")
        print("1. Update AA_DRIVE_ROOT to a WSL path:")
        print(f"   Example for this configuration: {_example_wsl_root(drive_root)}")
        print("2. Or run this with Windows Python directly")
        print("=" * 70)
        sys.exit(1)

# (load_env_file was moved to top of file - must load before a_drive_paths import)

# Diagnose path mismatches before any other initialization (non-fatal)
try:
    _diagnose_path_mismatch()
except SystemExit:
    print("WARNING: Path mismatch detected; continuing in lenient mode")

print("DEBUG: Importing startup_manager...")
from backend.startup_manager import validate_environment, initialize_app_state
print("DEBUG: Importing policies...")
from backend.policies.manifest_validator import validate_on_startup
print("DEBUG: Importing shutdown_manager...")
from backend.shutdown_manager import cleanup_resources
print("DEBUG: Importing routers...")
from backend.routers import health, config_ops, session_log, emulator_mame, emulator_retroarch, screen_capture, claude_api, launchbox, frontend_log, scorekeeper, led_blinky, led, drive_map, routing_policy, controller, system, hardware, console, dewey, dewey_chat, gaming_news, sessions
from backend.routers import chuck_hardware
from backend.routers import wizard_mapping
from backend.routers import emulator_status as emulator_status_router
print("DEBUG: All basic routers imported")
print("DEBUG: Importing profile router...")
from backend.routers import profile as profile_router
print("DEBUG: Importing compat router...")
from backend.routers import compat as compat_router
print("DEBUG: Importing launchbox_import...")
from backend.routers import launchbox_import
print("DEBUG: Importing launchbox_cache...")
from backend.routers import launchbox_cache as launchbox_cache_router
print("DEBUG: Importing teknoparrot_aliases...")
from backend.routers import teknoparrot_aliases
print("DEBUG: Importing teknoparrot_health...")
from backend.routers import teknoparrot_health
print("DEBUG: Importing hiscore...")
from backend.routers import hiscore
print("DEBUG: Importing tournament_router...")
from backend.routers import tournament_router
print("DEBUG: Importing score_router...")
from backend.routers import score_router
print("DEBUG: Importing aa_launch...")
from backend.routers import aa_launch
print("DEBUG: Importing diagnostics...")
from backend.routers import diagnostics
from backend.routers import devices
print("DEBUG: Importing launchbox_ps2...")
from backend.routers import launchbox_ps2
print("DEBUG: Importing autoconfig...")
from backend.routers import autoconfig
print("DEBUG: Importing console_wizard...")
from backend.routers import console_wizard
print("DEBUG: Importing supabase_health...")
from backend.routers import supabase_health
from backend.routers import supabase_device as supabase_device_router
print("DEBUG: Importing lightguns...")
from backend.routers import lightguns
print("DEBUG: Importing gunner...")
from backend.routers import gunner
print("DEBUG: Importing voice...")
from backend.routers import voice
print("DEBUG: Importing voice_advanced...")
from backend.routers import voice_advanced
print("DEBUG: Importing doc_diagnostics...")
from backend.routers import doc_diagnostics
from backend.routers import doc
from backend.routers import chuck
from backend.routers import wiz
from backend.routers import blinky_chat
from backend.routers import gunner_chat
print("DEBUG: Importing emulator (pause/save API)...")
from backend.routers import emulator
print("DEBUG: Importing hotkey...")
from backend.routers import hotkey
print("DEBUG: Importing content_manager...")
from backend.routers import content_manager
print("DEBUG: Importing marquee router...")
from backend.routers import marquee as marquee_router
print("DEBUG: Importing runtime state router...")
from backend.routers import runtime_state
print("DEBUG: Importing pegasus router...")
from backend.routers import pegasus as pegasus_router
print("DEBUG: Importing theme_assets router...")
from backend.routers import theme_assets as theme_assets_router
print("DEBUG: Importing updates router...")
from backend.routers import updates as updates_router
print("DEBUG: Importing provisioning router...")
# REMOVED: provisioning import
print("DEBUG: Importing tendencies router...")
from backend.routers import tendencies as tendencies_router
print("DEBUG: Importing model router...")
from backend.routers import model_router as model_router_router
print("DEBUG: Importing escalation router...")
from backend.routers import escalation as escalation_router
print("DEBUG: Importing wizard_router...")
from backend.routers import wizard_router
print("DEBUG: Importing game_lifecycle router...")
from backend.routers import game_lifecycle
print("DEBUG: Importing doc_diagnostics router...")
print("DEBUG: Importing engineering_bay router...")
from backend.routers import engineering_bay
print("DEBUG: Importing tts router...")
from backend.routers import tts as tts_router
from backend.routers import blinky as blinky_patterns
print("DEBUG: Importing launchbox_plugin_client...")
from backend.services.launchbox_plugin_client import get_plugin_client
from backend.services.led_hardware import write_port as led_write_port
from backend.services.led_priority_arbiter import led_priority_arbiter
print("DEBUG: All imports complete!")

def _is_wsl() -> bool:
    try:
        if platform.system().lower() != "linux":
            return False
        with open("/proc/version", "r", encoding="utf-8") as f:
            data = f.read().lower()
            return "microsoft" in data or "wsl" in data
    except Exception:
        return False

def _warn_if_wsl_usb_constraints():
    if _is_wsl():
        print("=" * 70)
        print("WARNING: Running under WSL — USB controllers may not be detected.")
        print("- Enable Windows→WSL USB passthrough (usbipd) and install libusb:")
        print("  Windows (Admin): winget install usbipd; usbipd wsl list; usbipd wsl attach --busid <BUSID>")
        print("  WSL: sudo apt-get install -y libusb-1.0-0")
        print("- For 95% reliability, run backend on Windows: start-gui.bat")
        print("=" * 70)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("=" * 50, flush=True)
    print("LIFESPAN STARTUP BEGINNING", flush=True)
    print("=" * 50, flush=True)
    sys.stdout.flush()
    try:
        t0 = time.perf_counter()

        validate_on_startup(app)

        t = time.perf_counter()
        await validate_environment()
        dur_validate = time.perf_counter() - t

        t = time.perf_counter()
        await initialize_app_state(app)
        dur_init_state = time.perf_counter() - t

        # Initialize Session Manager for ScoreKeeper Sam
        t = time.perf_counter()
        try:
            from backend.services.session_manager import initialize_session_manager
            from backend.services.leaderboard import initialize_leaderboard_service
            drive_root = getattr(app.state, "drive_root", None)
            if drive_root:
                state_dir = drive_root / ".aa" / "state" / "scorekeeper"
                state_dir.mkdir(parents=True, exist_ok=True)
                launches_file = state_dir / "launches.jsonl"
                initialize_session_manager(state_dir)
                initialize_leaderboard_service(launches_file)
                print(f"Session manager initialized at {state_dir}")
                print(f"Leaderboard service initialized with {launches_file}")
                
                try:
                    from backend.services.hiscore_watcher import initialize_hiscore_watcher
                    scores_file = state_dir / "scores.jsonl"
                    high_scores_index = state_dir / "high_scores_index.json"
                    await initialize_hiscore_watcher(None, scores_file, high_scores_index)
                    print(f"Hiscore watcher initialized at {scores_file}")
                except Exception as e:
                    print(f"WARNING: Hiscore watcher initialization failed: {e}")

                # PAUSED: Hiscore Watcher disabled until first customer
                # To re-enable, uncomment the block below
                # try:
                #     from backend.services.hiscore_watcher import initialize_hiscore_watcher
                #     from backend.constants.a_drive_paths import LaunchBoxPaths
                #     scores_file = state_dir / "scores.jsonl"
                #     high_scores_index = state_dir / "high_scores_index.json"
                #     mame_dirs = [
                #         LaunchBoxPaths.EMULATORS_ROOT / "MAME Gamepad",
                #         LaunchBoxPaths.EMULATORS_ROOT / "MAME",
                #     ]
                #     watchers_started = 0
                #     for mame_root in mame_dirs:
                #         if (mame_root / "hiscore").exists() or (mame_root / "hi").exists():
                #             try:
                #                 await initialize_hiscore_watcher(mame_root, scores_file, high_scores_index)
                #                 print(f"Hiscore watcher initialized for {mame_root}")
                #                 watchers_started += 1
                #             except Exception as we:
                #                 print(f"WARNING: Hiscore watcher for {mame_root} failed: {we}")
                #     if watchers_started == 0:
                #         print("WARNING: No MAME hiscore directories found")
                # except Exception as e:
                #     print(f"WARNING: Hiscore watcher initialization failed: {e}")
                print("INFO: Hiscore watcher ACTIVE")
                
                # Initialize AI Vision Score Service
                try:
                    from backend.services.vision_score_service import initialize_vision_score_service
                    screenshots_dir = state_dir / "screenshots"
                    await initialize_vision_score_service(
                        scores_dir=state_dir,
                        screenshots_dir=screenshots_dir
                    )
                    print(f"Vision score service initialized at {state_dir}")
                except Exception as e:
                    print(f"WARNING: Vision score service initialization failed: {e}")
                
                # PAUSED: Lua Score Watcher disabled until first customer
                # To re-enable, uncomment the block below
                # try:
                #     from backend.services.hiscore_watcher import initialize_lua_score_watcher
                #     lua_scores_json = state_dir / "mame_scores.json"
                #     await initialize_lua_score_watcher(lua_scores_json)
                #     print(f"Lua score watcher initialized for {lua_scores_json}")
                # except Exception as e:
                #     print(f"WARNING: Lua score watcher initialization failed: {e}")
                try:
                    from backend.services.hiscore_watcher import initialize_lua_score_watcher
                    lua_scores_json = state_dir / "mame_scores.json"
                    await initialize_lua_score_watcher(lua_scores_json)
                    print(f"Lua score watcher initialized for {lua_scores_json}")
                except Exception as e:
                    print(f"WARNING: Lua score watcher initialization failed: {e}")
                print("INFO: Lua score watcher ACTIVE")
                
                # Initialize Game Lifecycle Service (tracks game processes for Vision fallback)
                try:
                    from backend.services.game_lifecycle import initialize_game_lifecycle
                    await initialize_game_lifecycle()
                    print("Game lifecycle service initialized")
                except Exception as e:
                    print(f"WARNING: Game lifecycle service initialization failed: {e}")
                
                # PAUSED: Match Watcher disabled until first customer
                # To re-enable, uncomment the block below
                # try:
                #     from backend.services.match_watcher import start_match_watcher
                #     match_watcher = start_match_watcher(str(drive_root))
                #     app.state.match_watcher = match_watcher
                #     print(f"Match watcher started, watching: {match_watcher.results_path}")
                # except Exception as e:
                #     print(f"WARNING: Match watcher initialization failed: {e}")
                print("INFO: Match watcher PAUSED (no customers yet)")
            else:
                print("WARNING: Session/Leaderboard services not initialized (no drive root)")
        except Exception as e:
            print(f"WARNING: Session/Leaderboard initialization failed: {e}")
        dur_init_sessions = time.perf_counter() - t

        # Initialize LaunchBox cache
        t = time.perf_counter()
        # Always skip blocking initialization during startup
        # Cache will initialize lazily on first API request
        print("LaunchBox cache: deferred to lazy load on first request")
        dur_init_cache = 0

        # Optional: Start background thread to pre-warm cache
        if os.getenv("AA_PRELOAD_LB_CACHE", "false").lower() in {"1", "true", "yes"}:
            print("Starting LaunchBox cache preload in background thread...")
            def _preload():
                try:
                    launchbox.initialize_cache()
                    print("LaunchBox cache preload complete")
                except Exception as e:
                    print(f"LaunchBox cache preload failed: {e}")

            preload_thread = threading.Thread(target=_preload, daemon=True)
            preload_thread.start()

        # Initialize LED Blinky pattern resolver
        try:
            from backend.services.blinky.resolver import PatternResolver

            async def _init_blinky_resolver():
                try:
                    await PatternResolver.initialize()
                    led_priority_arbiter.set_fire_callback(led_write_port)
                    logger.info("Blinky: fire callback registered → led_hardware.write_port")
                    print("LED Blinky resolver ready (background)")
                except Exception as e:
                    print(f"WARNING: LED Blinky resolver background init failed: {e}")

            asyncio.create_task(_init_blinky_resolver())
        except Exception as e:
            print(f"WARNING: LED Blinky resolver initialization failed: {e}")

        # Initialize V2 Hotkey Service
        print(f"DEBUG: V2_HOTKEY_LAUNCHER = {os.getenv('V2_HOTKEY_LAUNCHER', 'NOT SET')}", flush=True)
        sys.stdout.flush()
        if os.getenv("V2_HOTKEY_LAUNCHER", "false").lower() == "true":
            print("[Hotkey] Starting hotkey service...", flush=True)
            try:
                from backend.services.hotkey_manager import get_hotkey_manager
                from backend.routers.hotkey import broadcast_hotkey_event
                print("[Hotkey] Imports successful, getting manager...", flush=True)
                manager = get_hotkey_manager()
                print("[Hotkey] Registering callback...", flush=True)
                manager.register_callback(broadcast_hotkey_event)
                print("[Hotkey] Starting keyboard listener...", flush=True)
                await manager.start()
                print("[Hotkey] Service started successfully!", flush=True)
                sys.stdout.flush()
            except Exception as e:
                print(f"[Hotkey] FAILED to start service: {e}", flush=True)
                print("[Hotkey] Make sure backend is running as Administrator", flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
        else:
            print("[Hotkey] Service disabled (V2_HOTKEY_LAUNCHER not enabled)", flush=True)
            sys.stdout.flush()

        # Optional: pre-warm heavy caches asynchronously to avoid first-request penalty
        if os.getenv("AA_PRELOAD_LB_CACHE", "false").lower() in {"1", "true", "yes"}:
            try:
                from backend.services.image_scanner import preload_images_async
                from backend.services.launchbox_parser import parser as lb_parser

                # Ensure thread tracking list exists
                if not hasattr(app.state, 'threads'):
                    app.state.threads = []

                # Start image cache preload (has its own thread)
                t = preload_images_async()
                if t:
                    getattr(app.state, "threads", []).append(t)

                # Start parser initialization in a background thread
                t = threading.Thread(target=lb_parser.initialize, daemon=True)
                t.start()
                getattr(app.state, "threads", []).append(t)
            except Exception as e:
                print(f"WARNING: Failed to start pre-warm tasks: {e}")

        print("FastAPI backend started successfully")
        _warn_if_wsl_usb_constraints()

        # Optional: start lightweight file watcher to auto-revalidate
        try:
            from backend.services.launchbox_cache import start_auto_revalidate_if_enabled
            start_auto_revalidate_if_enabled()
        except Exception as e:
            print(f"WARNING: Failed to start LaunchBox auto-revalidate: {e}")

        # Plugin preflight: read plugin health and cache basic info for diagnostics
        plugin_attempts = 3
        plugin_info: Dict[str, Any] = {"available": False}
        last_error: Optional[Exception] = None
        for attempt in range(1, plugin_attempts + 1):
            try:
                client = get_plugin_client()
                info = client.get_health()
                if info:
                    plugin_info = info
                    plugin_info["available"] = True
                    print(f"Plugin detected: {info.get('plugin')} v{info.get('version')}")
                else:
                    print("Plugin not detected during startup preflight")
                break
            except Exception as e:
                last_error = e
                print(f"WARNING: Plugin preflight attempt {attempt} failed: {e}")
                if attempt < plugin_attempts:
                    time.sleep(min(2 ** attempt, 5))
        else:
            if last_error:
                print(f"WARNING: Plugin preflight exhausted retries: {last_error}")
        app.state.plugin_info = plugin_info

        # Record startup timing to logs/startup-times.jsonl
        try:
            total = time.perf_counter() - t0
            drive_root = getattr(app.state, "drive_root", None)
            if drive_root:
                logs_dir = drive_root / ".aa" / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                log_path = logs_dir / "startup-times.jsonl"
                dur_init_blinky = 0.0
                record = {
                    "ts": datetime.now().isoformat(),
                    "durations_s": {
                        "validate_environment": round(dur_validate, 6),
                        "initialize_app_state": round(dur_init_state, 6),
                        "initialize_cache": round(dur_init_cache, 6),
                        "initialize_blinky": round(dur_init_blinky, 6),
                    },
                    "total_s": round(total, 6),
                }
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"WARNING: Failed to write startup timing: {e}")
        # Cabinet self-registration and heartbeat — ENABLED for drive duplication readiness
        try:
            from backend.services.cabinet_registration import register_cabinet_async
            from backend.services.heartbeat import start_heartbeat_task
            try:
                reg_result = await register_cabinet_async()
                if reg_result.get('success'):
                    print(f"Cabinet registered: device_id={reg_result.get('device_id')}, mac={reg_result.get('mac')}")
                else:
                    print(f"Cabinet registration skipped: {reg_result.get('error', 'unknown')}")
                print(f"Cabinet status: {reg_result.get('status', 'unknown')}")
            except Exception as reg_err:
                print(f"WARNING: Cabinet registration failed (non-fatal): {reg_err}")
            app.state._hb_task = start_heartbeat_task()
            print("Heartbeat loop started (30s interval)")
        except Exception as he_init:
            print(f"WARNING: Cabinet registration/heartbeat not started: {he_init}")

        # PAUSED: Dewey's auto-trivia scheduler disabled until first customer
        # To re-enable, uncomment the block below
        # try:
        #     from backend.services.dewey.trivia_scheduler import start_trivia_scheduler
        #     start_trivia_scheduler()
        #     print("Trivia auto-update scheduler started")
        # except Exception as trivia_err:
        #     print(f"WARNING: Trivia scheduler not started: {trivia_err}")
        print("INFO: Trivia auto-update scheduler PAUSED (no customers yet)")

    except Exception as e:
        print(f"Failed to start FastAPI backend: {e}")
        raise

    yield

    # Shutdown
    # Stop trivia scheduler
    try:
        from backend.services.dewey.trivia_scheduler import stop_trivia_scheduler
        stop_trivia_scheduler()
    except Exception:
        pass

    # Stop heartbeat task if running
    try:
        hb = getattr(app.state, '_hb_task', None)
        if hb:
            hb.cancel()
            try:
                await hb
            except Exception:
                pass
    except Exception:
        pass
    await cleanup_resources(app)
    print("FastAPI backend shut down cleanly")

app = FastAPI(
    title="Arcade Assistant - Local Operations API",
    description="Safe, scoped file operations for Arcade Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - locked to localhost gateway
# Include both localhost and 127.0.0.1 to prevent CORS identity crisis
app.add_middleware(
    CORSMiddleware,
      allow_origins=[
        "https://localhost:8787",
        "http://localhost:8787",
        "http://localhost:5173",
        "https://localhost:5173",
        # 127.0.0.1 variants (same machine, different hostname)
        "https://127.0.0.1:8787",
        "http://127.0.0.1:8787",
        "http://127.0.0.1:5173",
        "https://127.0.0.1:5173"
      ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["content-type", "authorization", "x-scope", "x-device-id", "x-panel", "x-corr-id"],
)

# Attach device id middleware to populate request.state.device_id
try:
    from backend.middleware import DeviceIdMiddleware
    app.add_middleware(DeviceIdMiddleware)
except Exception as _mw_err:
    print(f"WARNING: DeviceIdMiddleware not attached: {_mw_err}")

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(config_ops.router, prefix="/config", tags=["config"])
app.include_router(session_log.router, prefix="/docs/session_log", tags=["docs"])
app.include_router(frontend_log.router, prefix="/frontend", tags=["frontend"])
app.include_router(emulator_mame.router, prefix="/mame", tags=["mame"])
app.include_router(emulator_retroarch.router, prefix="/retroarch", tags=["retroarch"])
app.include_router(screen_capture.router, prefix="/screen", tags=["screen-capture"])
app.include_router(claude_api.router, prefix="/claude", tags=["claude-api"])
app.include_router(launchbox.router, tags=["launchbox"])  # ACTIVATED 2025-10-06
app.include_router(launchbox.local_router, prefix="/api/local")
app.include_router(launchbox_cache_router.router)
app.include_router(launchbox_import.router)
app.include_router(scorekeeper.router, prefix="/api/local/scorekeeper", tags=["scorekeeper"])
app.include_router(sessions.router, tags=["sessions"])  # Session management for ScoreKeeper Sam
app.include_router(profile_router.router, prefix="/api/local", tags=["profile"])  # /profile and /consent
app.include_router(devices.router, prefix="/api/local", tags=["devices"])
app.include_router(led_blinky.router, prefix="/api/local/led", tags=["led-blinky"])
app.include_router(led.router, prefix="/api/local/led", tags=["led-profiles"])
app.include_router(drive_map.router, tags=["drive-map"])  # JSON generator for A: drive mapping
app.include_router(routing_policy.router)
app.include_router(diagnostics.router, prefix="/api/local", tags=["diagnostics"])
app.include_router(teknoparrot_aliases.router)
app.include_router(teknoparrot_health.router)  # TeknoParrot diagnostics + health
app.include_router(hiscore.router)  # High score tracking for ScoreKeeper Sam
app.include_router(score_router.router)  # Score reset/backup API
app.include_router(aa_launch.router)  # Universal launcher endpoint
app.include_router(launchbox_ps2.router)
app.include_router(system.router)
app.include_router(system.local_router)
app.include_router(controller.router, prefix="/api/local/controller", tags=["controller"])
app.include_router(chuck_hardware.router, prefix="/api/local/controller", tags=["controller-hardware"])  # Phase 2: Hardware split
app.include_router(wizard_mapping.router, prefix="/api/local/controller", tags=["controller-wizard"])  # Phase 2: Wizard/Mapping split
app.include_router(hardware.router, prefix="/api/hardware", tags=["hardware"])
app.include_router(hardware.router, prefix="/api/local/hardware", tags=["hardware"])  # Also mount at /api/local for ControllerChuckPanel
app.include_router(console.router, prefix="/api/local/console", tags=["console"])
app.include_router(dewey.router)
app.include_router(dewey_chat.router)
app.include_router(gaming_news.router, prefix="/api/local/news", tags=["gaming-news"])
app.include_router(compat_router.router)
app.include_router(supabase_health.router, tags=["supabase"])
app.include_router(supabase_device_router.router, tags=["supabase"])
app.include_router(autoconfig.router)  # Controller auto-configuration
app.include_router(console_wizard.router, prefix="/api", tags=["console-wizard"])
app.include_router(lightguns.router, prefix="/lightguns", tags=["lightguns"])
app.include_router(lightguns.router, prefix="/api/local/lightguns", tags=["lightguns"])
app.include_router(gunner.router)  # Light gun calibration and profiles
app.include_router(gunner.router, prefix="/api/local", tags=["gunner"])
app.include_router(voice.router, prefix="/api", tags=["voice"])  # Voice Vicky lighting commands (basic)
app.include_router(voice_advanced.router, prefix="/api", tags=["voice-advanced"])  # Voice Vicky advanced NLP
app.include_router(emulator.router, tags=["emulator"])  # Emulator control (pause/save)
app.include_router(hotkey.router, tags=["hotkey"])  # V2: Global hotkey detection (A key for overlay)
app.include_router(emulator_status_router.router)  # /api/local/emulator/status
app.include_router(content_manager.router)  # Content & Display Manager (ROM paths, RetroFE, Marquee)
app.include_router(content_manager.registry_router)
app.include_router(marquee_router.router)
app.include_router(pegasus_router.router)  # Pegasus frontend status and metadata management
app.include_router(theme_assets_router.router, prefix="/api/local/theme-assets", tags=["theme-assets"])  # Theme asset management
app.include_router(runtime_state.router)
app.include_router(runtime_state.state_router)
# blinky_patterns router — active (aliased from backend.routers.blinky)
# Endpoints under /api/blinky/* are unavailable until blinky.__init__
# is converted to lazy exports.
app.include_router(blinky_patterns.router, prefix="/api/blinky", tags=["led-blinky-patterns"])
app.include_router(updates_router.router)  # Update plumbing (Phase 0)
# REMOVED: provisioning router
app.include_router(tendencies_router.router)  # User tendency/preference tracking
app.include_router(model_router_router.router)  # Smart AI model routing
app.include_router(escalation_router.router)  # AI escalation to Fleet Manager
app.include_router(wizard_router.router)  # Controller Wizard real-time input stream
app.include_router(tournament_router.router)  # Tournament mode plugin integration for Sam
app.include_router(game_lifecycle.router)  # Game lifecycle: Playnite start/stop → LEDBlinky Cinema Logic
app.include_router(doc_diagnostics.router, prefix="/api/doc", tags=["doc-diagnostics"])  # Phase 4: Doc's Pulse vitals
app.include_router(doc.router, prefix="/api/local/doc", tags=["doc"])
app.include_router(chuck.router, prefix="/api/local/chuck", tags=["chuck"])
app.include_router(wiz.router, prefix="/api/local/wiz", tags=["wiz"])
app.include_router(blinky_chat.router, prefix="/api/local/blinky", tags=["blinky"])
app.include_router(gunner_chat.router, prefix="/api/local/gunner", tags=["gunner"])
app.include_router(engineering_bay.router, prefix="/api", tags=["engineering-bay"])  # Unified EB chat: Vicky/Blinky/Gunner/Doc
app.include_router(tts_router.router, prefix="/api", tags=["tts"])  # ElevenLabs TTS via Supabase proxy

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else "An error occurred"
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True if os.getenv("DEBUG") else False
    )









