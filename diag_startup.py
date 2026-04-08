"""
Quick startup diagnostic — run from repo root:
    .venv\Scripts\python.exe diag_startup.py

This simulates the import chain from backend.app to find the crash.
"""
import os, sys, traceback

# Step 0: Load .env
print("[DIAG 0] Loading .env...")
from pathlib import Path
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    print(f"  AA_DRIVE_ROOT = {os.getenv('AA_DRIVE_ROOT', '<NOT SET>')}")
else:
    print("  .env NOT FOUND")
    sys.exit(1)

# Step 1: Core constants
print("[DIAG 1] Importing drive_root...")
try:
    from backend.constants.drive_root import get_drive_root
    dr = get_drive_root(allow_cwd_fallback=True)
    print(f"  drive_root = {dr}  (exists={dr.exists()})")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("[DIAG 2] Importing a_drive_paths...")
try:
    from backend.constants.a_drive_paths import LaunchBoxPaths, EmulatorPaths
    print(f"  LaunchBox root = {LaunchBoxPaths.LAUNCHBOX_ROOT}")
    print(f"  Supermodel exe = {EmulatorPaths.supermodel()}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("[DIAG 3] Importing runtime_paths...")
try:
    from backend.constants.runtime_paths import aa_tmp_dir
    print(f"  aa_tmp_dir = {aa_tmp_dir()}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 2: Services
print("[DIAG 4] Importing startup_manager...")
try:
    from backend.startup_manager import validate_environment, initialize_app_state
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("[DIAG 5] Importing manifest_validator...")
try:
    from backend.policies.manifest_validator import validate_on_startup
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("[DIAG 6] Importing shutdown_manager...")
try:
    from backend.shutdown_manager import cleanup_resources
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 3: All routers (the big one)
routers = [
    "health", "config_ops", "session_log", "emulator_mame",
    "emulator_retroarch", "screen_capture", "claude_api", "launchbox",
    "frontend_log", "scorekeeper", "led_blinky", "led", "drive_map",
    "routing_policy", "controller", "system", "hardware", "console",
    "dewey", "dewey_chat", "gaming_news", "sessions",
    "chuck_hardware", "wizard_mapping",
    "emulator_status",
    "profile", "compat", "launchbox_import", "launchbox_cache",
    "teknoparrot_aliases", "teknoparrot_health",
    "hiscore", "tournament_router", "score_router",
    "aa_launch", "diagnostics", "devices", "launchbox_ps2",
    "autoconfig", "console_wizard",
    "supabase_health", "supabase_device",
    "lightguns", "gunner", "controller_ai",
    "voice", "voice_advanced", "doc_diagnostics",
    "emulator", "hotkey", "content_manager",
    "marquee", "runtime_state", "pegasus",
    "theme_assets", "updates",
    "tendencies", "model_router", "escalation",
    "wizard_router", "game_lifecycle",
    "engineering_bay", "tts", "blinky",
]
for name in routers:
    print(f"[DIAG 7] Importing backend.routers.{name}...", end=" ", flush=True)
    try:
        __import__(f"backend.routers.{name}")
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        traceback.print_exc()
        print(f"\n*** STARTUP FAILURE: backend.routers.{name} ***")
        sys.exit(1)

# Step 4: Services
print("[DIAG 8] Importing launchbox_plugin_client...")
try:
    from backend.services.launchbox_plugin_client import get_plugin_client
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

print("[DIAG 9] Importing launcher_registry...")
try:
    from backend.services.launcher_registry import REGISTERED, ADAPTER_STATUS
    print(f"  {len(REGISTERED)} adapters registered")
    for name, status in ADAPTER_STATUS.items():
        print(f"    {name}: {status}")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 5: Check port availability
print("[DIAG 10] Checking port 8000...")
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    result = s.connect_ex(('127.0.0.1', 8000))
    s.close()
    if result == 0:
        print("  ⚠️  PORT 8000 IS ALREADY IN USE — another backend instance may be running!")
        print("  Fix: Run 'netstat -ano | findstr :8000' to find the PID, then 'taskkill /F /PID <pid>'")
    else:
        print("  Port 8000 is available ✅")
except Exception as e:
    print(f"  Port check error: {e}")

print("\n" + "=" * 60)
print("ALL DIAGNOSTICS PASSED — backend import chain is healthy.")
print("If the backend still won't start, the issue is in the")
print("uvicorn process itself. Try running directly:")
print("  .venv\\Scripts\\python.exe -m uvicorn backend.app:app --host 0.0.0.0 --port 8000")
print("=" * 60)
