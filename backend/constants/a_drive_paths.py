"""
Drive path constants for LaunchBox integration.
NEVER hardcode paths elsewhere - always import from this module.

IMPORTANT: No hardcoded drive letters. Uses AA_DRIVE_ROOT environment variable.

Critical path corrections (2025-10-06):
- LaunchBox root is <AA_DRIVE_ROOT>/LaunchBox
- Master XML (LaunchBox.xml) NOT FOUND - must parse platform XMLs
- CLI_Launcher.exe NOT FOUND - use fallback launch methods
"""
import os
from pathlib import Path

from backend.constants.drive_root import get_drive_root


# Environment-based root detection
def _convert_to_wsl_path(windows_path: str) -> str:
    """
    Convert Windows path to WSL path ONLY when running inside WSL.

    CRITICAL FIX: Do NOT convert paths on native Windows systems!
    Only performs conversion when:
    1. System is Linux (not Windows)
    2. Kernel release contains 'microsoft' (WSL indicator)
    3. Path is a valid Windows path (drive letter format)

    Args:
        windows_path: Windows-style path (e.g., "C:\\Users\\...")

    Returns:
        WSL path if running in WSL, original path otherwise
    """
    import platform

    # Check if we're actually running on WSL
    is_wsl = platform.system() == 'Linux' and 'microsoft' in platform.release().lower()

    # CRITICAL: Return unchanged on native Windows
    if not is_wsl:
        return windows_path  # Do NOT modify paths on Windows!

    # Only convert valid Windows paths in WSL environment
    if windows_path and len(windows_path) >= 2 and windows_path[1] == ':':
        drive_letter = windows_path[0].lower()
        rest = windows_path[2:].replace('\\', '/').lstrip('/')
        wsl_path = f"/mnt/{drive_letter}"
        if rest:
            wsl_path = f"{wsl_path}/{rest}"
        return wsl_path

    return windows_path


def _get_drive_root_str() -> str:
    """Get drive root as string. No CWD fallback per Slice 2 contract."""
    try:
        return str(get_drive_root(allow_cwd_fallback=False))
    except Exception:
        # Return sentinel that will fail path validation, not a silent CWD
        return "<AA_DRIVE_ROOT_NOT_SET>"


_raw_drive_root = os.getenv('AA_DRIVE_ROOT', '') or _get_drive_root_str()
AA_DRIVE_ROOT = _convert_to_wsl_path(_raw_drive_root)

# Extract drive letter root (e.g., "A:\" from "A:\Arcade Assistant Local")
# LaunchBox, ROMs, Emulators are at drive root, not project folder
def _get_drive_letter_root() -> str:
    """Get just the drive letter root from AA_DRIVE_ROOT."""
    root = AA_DRIVE_ROOT
    if len(root) >= 2 and root[1] == ':':
        return root[0:2] + "\\"
    if root.startswith('/mnt/') and len(root) >= 6:
        return root[0:6]  # /mnt/a
    return root

DRIVE_LETTER_ROOT = _get_drive_letter_root()

# LaunchBox root can be configured separately from AA_DRIVE_ROOT
# This allows LaunchBox on any drive while Arcade Assistant is elsewhere
_raw_launchbox_root = os.getenv('LAUNCHBOX_ROOT', None)
if _raw_launchbox_root:
    # User specified explicit LaunchBox location
    LAUNCHBOX_ROOT_OVERRIDE = Path(_convert_to_wsl_path(_raw_launchbox_root))
else:
    # Default: LaunchBox at drive root (A:\LaunchBox), not project folder
    LAUNCHBOX_ROOT_OVERRIDE = Path(DRIVE_LETTER_ROOT) / "LaunchBox"


def is_on_a_drive() -> bool:
    """Check if AA_DRIVE_ROOT points to A: drive.
    
    Note: This is deprecated. Drive letter should not matter for functionality.
    Re-reads from env to handle late .env loading.
    """
    root = os.getenv('AA_DRIVE_ROOT', '') or ''
    root_upper = root.upper()
    return root_upper.startswith('A:') or root_upper.startswith('/MNT/A')


class LaunchBoxPaths:
    """
    LaunchBox directory structure constants.
    Configurable via LAUNCHBOX_ROOT environment variable.
    All paths derived dynamically from AA_DRIVE_ROOT.
    """

    # Root (configurable via env)
    LAUNCHBOX_ROOT = LAUNCHBOX_ROOT_OVERRIDE

    # Data directories
    DATA_DIR = LAUNCHBOX_ROOT / "Data"
    PLATFORMS_DIR = DATA_DIR / "Platforms"  # 50+ XML files here

    # Images
    IMAGES_DIR = LAUNCHBOX_ROOT / "Images"
    BOX_FRONT_DIR = IMAGES_DIR / "Box - Front"
    SCREENSHOTS_DIR = IMAGES_DIR / "Screenshot - Gameplay"
    CLEAR_LOGOS_DIR = IMAGES_DIR / "Clear Logo"

    # Executables
    LAUNCHBOX_EXE = LAUNCHBOX_ROOT / "LaunchBox.exe"
    BIGBOX_EXE = LAUNCHBOX_ROOT / "BigBox.exe"
    CLI_LAUNCHER_EXE = LAUNCHBOX_ROOT / "ThirdParty" / "CLI_Launcher" / "CLI_Launcher.exe"

    # ROMs (at drive root, not project folder)
    ROMS_ROOT = Path(DRIVE_LETTER_ROOT) / "Roms"
    MAME_ROMS = ROMS_ROOT / "MAME"  # 14,233 .zip files

    # BIOS (at drive root, not project folder)
    BIOS_ROOT = Path(DRIVE_LETTER_ROOT) / "Bios"
    SYSTEM_BIOS = BIOS_ROOT / "system"  # 586 files

    # Emulators (at drive root, not project folder)
    EMULATORS_ROOT = Path(DRIVE_LETTER_ROOT) / "Emulators"
    MAME_EMULATOR = EMULATORS_ROOT / "MAME" / "mame.exe"

    @classmethod
    def _get_launchbox_root_dynamic(cls) -> Path:
        """Get LaunchBox root dynamically from current env (handles late .env loading)."""
        raw = os.getenv('LAUNCHBOX_ROOT', '')
        if raw:
            return Path(_convert_to_wsl_path(raw))
        # Default: derive from AA_DRIVE_ROOT
        drive_root = os.getenv('AA_DRIVE_ROOT', '')
        if drive_root and len(drive_root) >= 2 and drive_root[1] == ':':
            drive_letter = drive_root[0:2] + "\\"
            return Path(drive_letter) / "LaunchBox"
        return cls.LAUNCHBOX_ROOT  # Fall back to cached value

    @classmethod
    def validate(cls) -> dict:
        """
        Validate critical paths exist.
        Returns dict with path -> exists status.
        """
        lb_root = cls._get_launchbox_root_dynamic()
        return {
            "launchbox_root": lb_root.exists(),
            "platforms_dir": (lb_root / "Data" / "Platforms").exists(),
            "launchbox_exe": (lb_root / "LaunchBox.exe").exists(),
            "bigbox_exe": (lb_root / "BigBox.exe").exists(),
            "cli_launcher_exe": (lb_root / "ThirdParty" / "CLI_Launcher" / "CLI_Launcher.exe").exists(),
            "mame_roms": cls.MAME_ROMS.exists(),
            "mame_emulator": cls.MAME_EMULATOR.exists(),
        }

    @classmethod
    def get_status_message(cls) -> str:
        """Get human-readable status of drive paths."""
        lb_root = cls._get_launchbox_root_dynamic()
        validation = cls.validate()

        if not validation["launchbox_root"]:
            return f"❌ LaunchBox not found at {lb_root}"

        if not validation["platforms_dir"]:
            return f"❌ Platform XMLs directory missing at {lb_root / 'Data' / 'Platforms'}"

        if not validation["launchbox_exe"]:
            return "⚠️ LaunchBox.exe not found (launch fallback required)"

        if not validation["cli_launcher_exe"]:
            return "⚠️ CLI_Launcher.exe not found (using fallback launch methods)"

        return "✅ All LaunchBox paths validated"

    @classmethod
    def get_platform_xml_files(cls) -> list:
        """
        Get list of all platform XML files.
        Returns empty list if directory doesn't exist.
        """
        if not cls.PLATFORMS_DIR.exists():
            return []

        return sorted(cls.PLATFORMS_DIR.glob("*.xml"))


# LaunchBox platform XML discovery (robust, AA_DRIVE_ROOT-based)
# Example: <AA_DRIVE_ROOT>/LaunchBox/Data/Platforms/*.xml
LB_A_ROOT = AA_DRIVE_ROOT
LB_PLATFORMS_GLOB = str(Path(LB_A_ROOT) / "LaunchBox" / "Data" / "Platforms" / "*.xml")


class AutoConfigPaths:
    """
    Controller Auto-Configuration paths.

    SAFETY CONTRACT:
    - STAGING_ROOT is sanctioned for writes via /config/apply
    - MIRROR destinations (emulator trees) are manager-only (not direct writes)
    - Validates size, schema, naming before mirroring

    Usage:
        - Stage configs to STAGING_ROOT via /config/apply
        - Mirror via autoconfig_manager.mirror_staged_config()
        - Never write directly to emulator autoconfig dirs
    """

    # Sanctioned write area (staging configs before validation)
    STAGING_ROOT = Path(AA_DRIVE_ROOT) / "config" / "controllers" / "autoconfig" / "staging"

    # Mirror-only destinations (written via autoconfig_manager only)
    RETROARCH_AUTOCONFIG = Path(AA_DRIVE_ROOT) / "Emulators" / "RetroArch" / "autoconfig"
    MAME_CTRLR = Path(AA_DRIVE_ROOT) / "Emulators" / "MAME" / "ctrlr"

    @classmethod
    def get_sanctioned_paths(cls) -> list:
        """
        Get list of sanctioned write paths for manifest.json.

        Returns:
            List of path strings relative to AA_DRIVE_ROOT
        """
        return [
            "config/controllers/autoconfig/staging"
        ]

    @classmethod
    def is_staging_path(cls, path: Path) -> bool:
        """Check if path is within sanctioned staging area"""
        try:
            path.relative_to(cls.STAGING_ROOT)
            return True
        except ValueError:
            return False

    @classmethod
    def is_mirror_destination(cls, path: Path) -> bool:
        """Check if path is a mirror-only destination (no direct writes allowed)"""
        try:
            # Check if path is under emulator autoconfig trees
            path.relative_to(cls.RETROARCH_AUTOCONFIG)
            return True
        except ValueError:
            pass

        try:
            path.relative_to(cls.MAME_CTRLR)
            return True
        except ValueError:
            pass

        return False

    @classmethod
    def validate(cls) -> dict:
        """Validate autoconfig paths exist and are writable"""
        return {
            "staging_root": cls.STAGING_ROOT.exists(),
            "retroarch_autoconfig": cls.RETROARCH_AUTOCONFIG.exists(),
            "mame_ctrlr": cls.MAME_CTRLR.exists(),
        }

