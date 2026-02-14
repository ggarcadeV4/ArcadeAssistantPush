#!/usr/bin/env python3
"""
Backend startup wrapper with platform detection and self-healing capabilities.

Optimizes startup by:
- Platform-aware path aliasing (Windows vs WSL)
- Dependency verification with optional auto-install
- Environment validation and logging
- Graceful degradation for missing services
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def check_deps():
    """Verify required dependencies are installed."""
    required = ['fastapi', 'pydantic', 'supabase', 'structlog', 'uvicorn']
    missing = []

    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"⚠️  Missing dependencies: {', '.join(missing)}")

        # Auto-install if enabled via environment flag
        if os.getenv("AA_AUTO_INSTALL", "false").lower() == "true":
            print(f"📦 Auto-installing: {' '.join(missing)}")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages"] + missing,
                check=True
            )
            print("✅ Dependencies installed")
        else:
            print(f"\n💡 To fix: pip install {' '.join(missing)}")
            print("💡 Or set AA_AUTO_INSTALL=true for automatic installation")
            sys.exit(1)

def detect_wsl():
    """Detect if running in WSL environment."""
    if platform.system().lower() != 'linux':
        return False

    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower() or 'wsl' in f.read().lower()
    except:
        return False

def fix_paths():
    """Platform-aware path configuration."""
    is_wsl = detect_wsl()
    is_windows = platform.system() == 'Windows'

    # Set AA_DRIVE_ROOT based on platform
    if 'AA_DRIVE_ROOT' not in os.environ:
        if is_wsl:
            os.environ['AA_DRIVE_ROOT'] = '/mnt/a/'
            print("🐧 WSL detected - using /mnt/a/ for A: drive")
        elif is_windows:
            os.environ['AA_DRIVE_ROOT'] = 'A:\\'
            print("🪟 Windows detected - using A:\\ for A: drive")
        else:
            # Default to project directory for development
            os.environ['AA_DRIVE_ROOT'] = str(Path.cwd())
            print(f"💻 Development mode - using {os.environ['AA_DRIVE_ROOT']}")
    else:
        print(f"📂 AA_DRIVE_ROOT: {os.environ['AA_DRIVE_ROOT']}")

    # Ensure PYTHONPATH includes project root
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        os.environ['PYTHONPATH'] = str(project_root)

def validate_env():
    """Validate critical environment variables."""
    warnings = []

    # Check for API keys (optional but recommended)
    if not os.getenv('ANTHROPIC_API_KEY') and not os.getenv('CLAUDE_API_KEY'):
        warnings.append("⚠️  No AI API key found (ANTHROPIC_API_KEY or CLAUDE_API_KEY)")

    if not os.getenv('SUPABASE_URL'):
        warnings.append("⚠️  SUPABASE_URL not set (cloud features disabled)")

    if warnings:
        print("\n".join(warnings))
        print("💡 Backend will run with limited features\n")

def start():
    """Start the backend with optimizations."""
    print("🚀 Arcade Assistant Backend Startup")
    print("=" * 50)

    # Step 1: Check dependencies
    print("\n📋 Checking dependencies...")
    check_deps()
    print("✅ All dependencies available")

    # Step 2: Fix paths
    print("\n🔧 Configuring paths...")
    fix_paths()

    # Step 3: Validate environment
    print("\n🔍 Validating environment...")
    validate_env()

    # Step 4: Import and configure logging
    print("\n📝 Initializing logging...")
    try:
        import structlog

        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer()
            ]
        )

        logger = structlog.get_logger()
        logger.info(
            "backend_starting",
            platform=platform.system(),
            python_version=platform.python_version(),
            environment=os.getenv('ENVIRONMENT', 'development'),
            drive_root=os.environ.get('AA_DRIVE_ROOT'),
            wsl=detect_wsl()
        )
    except ImportError:
        print("⚠️  structlog not available, using basic logging")

    # Step 5: Start uvicorn
    print("\n🌐 Starting FastAPI server...")
    print("=" * 50)

    try:
        import uvicorn

        # Configuration
        host = os.getenv('BACKEND_HOST', '0.0.0.0')
        port = int(os.getenv('BACKEND_PORT', '8000'))
        reload = os.getenv('ENVIRONMENT', 'development') == 'development'

        print(f"📍 Server: http://{host}:{port}")
        print(f"🔄 Hot reload: {'enabled' if reload else 'disabled'}")
        print(f"📖 API docs: http://localhost:{port}/docs")
        print()

        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level=os.getenv('LOG_LEVEL', 'info').lower()
        )
    except KeyboardInterrupt:
        print("\n\n👋 Backend shutting down...")
    except Exception as e:
        print(f"\n❌ Failed to start backend: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start()
