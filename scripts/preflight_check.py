#!/usr/bin/env python3
"""
Arcade Assistant Pre-flight Check
==================================
Validates that all components can load before starting services.
Run this before start-arcade-assistant.bat to catch issues early.

Exit codes:
  0 = All checks passed
  1 = Critical failure (won't start)
  2 = Warnings only (may work with reduced functionality)
"""

import sys
import os
from pathlib import Path

# Ensure we're in the right directory
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# ANSI colors for terminal output
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def print_header():
    print(f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════════════════════╗
║           ARCADE ASSISTANT - PRE-FLIGHT CHECK                ║
╚══════════════════════════════════════════════════════════════╝{Colors.RESET}
""")

def check_pass(msg: str):
    print(f"  {Colors.GREEN}✓{Colors.RESET} {msg}")

def check_warn(msg: str):
    print(f"  {Colors.YELLOW}⚠{Colors.RESET} {msg}")

def check_fail(msg: str):
    print(f"  {Colors.RED}✗{Colors.RESET} {msg}")

def section(title: str):
    print(f"\n{Colors.BOLD}[{title}]{Colors.RESET}")


def check_python_version() -> bool:
    """Verify Python 3.9+ is available."""
    section("Python Version")
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 9:
        check_pass(f"Python {major}.{minor} (3.9+ required)")
        return True
    else:
        check_fail(f"Python {major}.{minor} is too old. Requires 3.9+")
        return False


def check_env_file() -> bool:
    """Verify .env exists."""
    section("Environment")
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        check_pass(".env file found")
        return True
    else:
        check_fail(".env file missing - run install-cabinet.bat first")
        return False


def check_a_drive() -> bool:
    """Verify A: drive is accessible (Windows only)."""
    section("A: Drive")
    if os.name != 'nt':
        check_warn("Not on Windows - skipping A: drive check")
        return True
    
    a_drive = Path("A:/")
    if a_drive.exists():
        check_pass("A: drive accessible")
        # Check for LaunchBox
        lb_path = Path("A:/LaunchBox")
        if lb_path.exists():
            check_pass("LaunchBox folder found")
        else:
            check_warn("LaunchBox folder not found at A:/LaunchBox")
        return True
    else:
        check_fail("A: drive not accessible - game library won't load")
        return False


def check_backend_imports() -> tuple[bool, list[str]]:
    """Try importing the backend app to catch any import errors."""
    section("Backend Imports")
    errors = []
    
    # Suppress noisy logging and warnings during import checks
    import logging
    import warnings
    import io
    
    old_level = logging.root.level
    logging.root.setLevel(logging.ERROR)
    warnings.filterwarnings("ignore")
    
    # Redirect stdout/stderr to suppress DEBUG prints
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    # Test critical imports one by one for better error isolation
    critical_modules = [
        ("backend.constants.paths", "Path constants"),
        ("backend.services.policies", "Security policies"),
        ("backend.services.audit_log", "Audit logging"),
        ("backend.services.launchbox_parser", "LaunchBox parser"),
        ("backend.services.launchbox_json_cache", "Game cache"),
        ("backend.services.launcher", "Game launcher"),
        ("backend.routers.launchbox", "LaunchBox router"),
        ("backend.routers.scorekeeper", "ScoreKeeper router"),
        ("backend.routers.controller", "Controller router"),
    ]
    
    all_ok = True
    for module_name, friendly_name in critical_modules:
        # Suppress output for each import
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            __import__(module_name)
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            check_pass(f"{friendly_name}")
        except ImportError as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            check_fail(f"{friendly_name}: {e}")
            errors.append(f"{module_name}: {e}")
            all_ok = False
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            check_fail(f"{friendly_name}: {type(e).__name__}: {e}")
            errors.append(f"{module_name}: {e}")
            all_ok = False
    
    # Final full import test
    if all_ok:
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            from backend.app import app
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            check_pass("Full backend app loads successfully")
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            check_fail(f"Backend app failed to load: {e}")
            errors.append(f"backend.app: {e}")
            all_ok = False
    
    # Restore logging level
    logging.root.setLevel(old_level)
    
    return all_ok, errors


def check_node_gateway() -> bool:
    """Verify node and gateway dependencies exist."""
    section("Gateway (Node.js)")
    
    gateway_dir = PROJECT_ROOT / "gateway"
    if not gateway_dir.exists():
        check_fail("gateway/ folder not found")
        return False
    
    server_js = gateway_dir / "server.js"
    if not server_js.exists():
        check_fail("gateway/server.js not found")
        return False
    check_pass("gateway/server.js exists")
    
    # node_modules can be in gateway/ or project root (npm workspaces)
    node_modules = gateway_dir / "node_modules"
    node_modules_root = PROJECT_ROOT / "node_modules"
    if node_modules.exists() or node_modules_root.exists():
        check_pass("node_modules installed")
    else:
        check_warn("node_modules missing - run 'npm install'")
        return False
    
    return True


def check_game_cache() -> bool:
    """Check if game cache exists for fast startup."""
    section("Game Cache")
    
    cache_path = Path("A:/.aa/launchbox_games.json")
    if cache_path.exists():
        try:
            size_mb = cache_path.stat().st_size / (1024 * 1024)
            check_pass(f"Game cache exists ({size_mb:.1f} MB)")
            return True
        except Exception:
            check_warn("Game cache exists but couldn't read size")
            return True
    else:
        check_warn("Game cache not found - first load will be slower")
        print(f"       Run: python scripts/build_launchbox_cache.py")
        return True  # Not a failure, just a warning


def check_ports() -> bool:
    """Check if required ports are available."""
    section("Network Ports")
    import socket
    
    ports = [(8000, "Backend"), (8787, "Gateway")]
    all_free = True
    
    for port, name in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            sock.close()
            check_pass(f"Port {port} ({name}) is available")
        except OSError:
            check_warn(f"Port {port} ({name}) may be in use")
            all_free = False
        finally:
            sock.close()
    
    return all_free


def run_preflight() -> int:
    """Run all pre-flight checks and return exit code."""
    print_header()
    
    critical_failures = []
    warnings = []
    
    # Critical checks
    if not check_python_version():
        critical_failures.append("Python version")
    
    if not check_env_file():
        critical_failures.append(".env file")
    
    if not check_a_drive():
        warnings.append("A: drive")  # Downgrade to warning - might work partially
    
    backend_ok, backend_errors = check_backend_imports()
    if not backend_ok:
        critical_failures.append("Backend imports")
        print(f"\n{Colors.RED}Backend import errors:{Colors.RESET}")
        for err in backend_errors:
            print(f"  • {err}")
    
    if not check_node_gateway():
        warnings.append("Gateway dependencies")
    
    check_game_cache()  # Just informational
    check_ports()  # Just informational
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    
    if critical_failures:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ PRE-FLIGHT FAILED{Colors.RESET}")
        print(f"\nCritical issues that must be fixed:")
        for issue in critical_failures:
            print(f"  • {issue}")
        print(f"\n{Colors.YELLOW}The backend will not start until these are resolved.{Colors.RESET}")
        return 1
    elif warnings:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ PRE-FLIGHT PASSED WITH WARNINGS{Colors.RESET}")
        print(f"\nSome features may not work:")
        for issue in warnings:
            print(f"  • {issue}")
        print(f"\n{Colors.GREEN}You can still try starting Arcade Assistant.{Colors.RESET}")
        return 2
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL PRE-FLIGHT CHECKS PASSED{Colors.RESET}")
        print(f"\n{Colors.CYAN}Ready to start Arcade Assistant!{Colors.RESET}")
        return 0


if __name__ == "__main__":
    try:
        exit_code = run_preflight()
        print()
        input("Press Enter to continue...")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Pre-flight check crashed: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        input("Press Enter to continue...")
        sys.exit(1)
