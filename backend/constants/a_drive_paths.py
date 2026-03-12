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



class EmulatorPaths:
    """
    Deterministic emulator executable paths for the Dual-Build Architecture.
    Two trees exist:
      - DRIVE_LETTER_ROOT / Emulators       -> Arcade Panel & Gamepad builds
      - DRIVE_LETTER_ROOT / Gun Build / Emulators -> Light Gun builds
    RULES:
      - Every physical emulator folder with a distinct executable gets an accessor.
      - Variants that share the SAME executable but differ only by CLI args
        (e.g. Demul vs Demul Arcade) do NOT get separate accessors.
      - all_executables() must list every accessor for health-check scanning.
    """

    _PANEL_ROOT = Path(DRIVE_LETTER_ROOT) / "Emulators"
    _GUN_ROOT = Path(DRIVE_LETTER_ROOT) / "Gun Build" / "Emulators"

    # Arcade Panel / Gamepad Builds
    # MAME family
    @staticmethod
    def mame() -> Path:
        return EmulatorPaths._PANEL_ROOT / "MAME" / "mame.exe"

    @staticmethod
    def mame_gamepad() -> Path:
        return EmulatorPaths._PANEL_ROOT / "MAME Gamepad" / "mame.exe"

    @staticmethod
    def psx_mame() -> Path:
        return EmulatorPaths._PANEL_ROOT / "PSX MAME" / "mame.exe"

    # RetroArch family
    @staticmethod
    def retroarch() -> Path:
        return EmulatorPaths._PANEL_ROOT / "RetroArch" / "retroarch.exe"

    @staticmethod
    def retroarch_gamepad() -> Path:
        return EmulatorPaths._PANEL_ROOT / "RetroArch Gamepad" / "retroarch.exe"

    @staticmethod
    def retroarch_fbneo() -> Path:
        return EmulatorPaths._PANEL_ROOT / "RetroArch FBNeo RA" / "retroarch.exe"

    # Dolphin family
    @staticmethod
    def dolphin() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Dolphin" / "Dolphin.exe"

    @staticmethod
    def dolphin_joystick() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Dolphin Joystick" / "Dolphin.exe"

    @staticmethod
    def dolphin_triforce() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Dolphin Tri-Force" / "Dolphin.exe"

    @staticmethod
    def dolphin_mka1() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Sega Triforce" / "Mario Kart Arcade GP 1" / "DolphinWX.exe"

    @staticmethod
    def dolphin_mka2() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Sega Triforce" / "Mario Kart Arcade GP 2" / "DolphinWX.exe"

    # TeknoParrot family
    @staticmethod
    def teknoparrot() -> Path:
        return EmulatorPaths._PANEL_ROOT / "TeknoParrot" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_237() -> Path:
        return EmulatorPaths._PANEL_ROOT / "TeknoParrot .237" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_140() -> Path:
        return EmulatorPaths._PANEL_ROOT / "TeknoParrot .140" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_latest() -> Path:
        return EmulatorPaths._PANEL_ROOT / "TeknoParrot Latest" / "TeknoParrotUi.exe"

    # Sega family
    @staticmethod
    def model2() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Sega Model 2" / "emulator_multicpu.exe"

    @staticmethod
    def supermodel() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Super Model" / "Supermodel.exe"

    @staticmethod
    def demul() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Demul 0.7" / "demul.exe"

    @staticmethod
    def demul_cdi() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Demul 0.7 CDI" / "demul.exe"

    # PlayStation family
    @staticmethod
    def pcsx2() -> Path:
        return EmulatorPaths._PANEL_ROOT / "PCSX2" / "pcsx2-qt.exe"

    @staticmethod
    def pcsx2_joystick() -> Path:
        return EmulatorPaths._PANEL_ROOT / "PCSX2 Joystick" / "pcsx2-qt.exe"

    @staticmethod
    def duckstation() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Duckstation" / "duckstation-qt-x64-ReleaseLTCG.exe"

    @staticmethod
    def ppsspp() -> Path:
        return EmulatorPaths._PANEL_ROOT / "PPSSPP" / "PPSSPPWindows64.exe"

    # Other standalones
    @staticmethod
    def xenia() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Xenia" / "xenia.exe"

    @staticmethod
    def xenia_canary() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Xenia" / "xenia_canary.exe"

    @staticmethod
    def rpcs3() -> Path:
        return EmulatorPaths._PANEL_ROOT / "rpcs3" / "rpcs3.exe"

    @staticmethod
    def cemu() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Cemu" / "Cemu.exe"

    @staticmethod
    def yuzu() -> Path:
        return EmulatorPaths._PANEL_ROOT / "yuzu" / "yuzu.exe"

    @staticmethod
    def citra() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Citra" / "nightly" / "citra-qt.exe"

    @staticmethod
    def ryujinx() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Ryujinx" / "Ryujinx.exe"

    @staticmethod
    def redream() -> Path:
        return EmulatorPaths._PANEL_ROOT / "redream.x86_64-windows-v1.5.0" / "redream.exe"

    @staticmethod
    def xemu() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Xemu" / "xemu.exe"

    @staticmethod
    def cxbx() -> Path:
        return EmulatorPaths._PANEL_ROOT / "CXBX" / "cxbxr-ldr.exe"

    @staticmethod
    def vita3k() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Vita3K" / "Vita3K.exe"

    @staticmethod
    def mupen64() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Mupen64" / "RMG.exe"

    @staticmethod
    def mesen() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Messen" / "Mesen.exe"

    @staticmethod
    def fusion() -> Path:
        return EmulatorPaths._PANEL_ROOT / "Fusion" / "Fusion.exe"

    @staticmethod
    def aae() -> Path:
        return EmulatorPaths._PANEL_ROOT / "AAE" / "aae.exe"

    @staticmethod
    def rocket_launcher() -> Path:
        return EmulatorPaths._PANEL_ROOT / "RocketLauncher" / "RocketLauncher.exe"

    @staticmethod
    def mfme() -> Path:
        return EmulatorPaths._PANEL_ROOT / "MFME" / "MFME" / "MFME.exe"

    @staticmethod
    def mfme_19() -> Path:
        return EmulatorPaths._PANEL_ROOT / "MFME 19" / "MFME" / "MFME.exe"

    # Gun Build Variants
    @staticmethod
    def mame_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "MAME" / "mame.exe"

    @staticmethod
    def mame_gun_4x3() -> Path:
        return EmulatorPaths._GUN_ROOT / "MAME 4x3" / "mame.exe"

    @staticmethod
    def retroarch_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "RetroArch" / "retroarch.exe"

    @staticmethod
    def retroarch_gun_win64() -> Path:
        return EmulatorPaths._GUN_ROOT / "RetroArch-Win64" / "retroarch.exe"

    @staticmethod
    def supermodel_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Super Model" / "Supermodel.exe"

    @staticmethod
    def model2_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Sega Model 2" / "emulator_multicpu.exe"

    @staticmethod
    def dolphin_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Dolphin" / "Dolphin.exe"

    @staticmethod
    def dolphin_gun_50() -> Path:
        return EmulatorPaths._GUN_ROOT / "Dolphin 5.0" / "Dolphin.exe"

    @staticmethod
    def demul_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Demul" / "demul.exe"

    @staticmethod
    def demul_gun_braveff() -> Path:
        return EmulatorPaths._GUN_ROOT / "Demul BraveFF" / "demul.exe"

    @staticmethod
    def flycast_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Flycast" / "flycast.exe"

    @staticmethod
    def pcsx2_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "PCSX2" / "pcsx2-qt.exe"

    @staticmethod
    def pcsx2_gcon45() -> Path:
        return EmulatorPaths._GUN_ROOT / "PCSX2 G-Con45" / "pcsx2-qt.exe"

    @staticmethod
    def pcsx2_tc() -> Path:
        return EmulatorPaths._GUN_ROOT / "PCSX2 TC" / "pcsx2-qt.exe"

    @staticmethod
    def rpcs3_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "RPCS3" / "rpcs3.exe"

    @staticmethod
    def rpcs3_eden() -> Path:
        return EmulatorPaths._GUN_ROOT / "RPCS3 Eden" / "rpcs3.exe"

    @staticmethod
    def epsxe_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "ePSXe" / "ePSXe.exe"

    @staticmethod
    def teknoparrot_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "TeknoParrot" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_gun_945() -> Path:
        return EmulatorPaths._GUN_ROOT / "TeknoParrot .945" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_gun_latest() -> Path:
        return EmulatorPaths._GUN_ROOT / "TeknoParrot Latest" / "TeknoParrotUi.exe"

    @staticmethod
    def teknoparrot_gun_le3() -> Path:
        return EmulatorPaths._GUN_ROOT / "TeknoParrot LE3" / "TeknoParrotUi.exe"

    @staticmethod
    def flash_player() -> Path:
        return EmulatorPaths._GUN_ROOT / "Flash Player" / "ruffle.exe"

    @staticmethod
    def play2x6_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Play2x6 Gun" / "Play.exe"

    @staticmethod
    def snes9x_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Snes9x" / "snes9x-x64.exe"

    @staticmethod
    def mesen_gun() -> Path:
        return EmulatorPaths._GUN_ROOT / "Messen" / "Mesen.exe"

    @staticmethod
    def cxbx_gun_silent_scope() -> Path:
        return EmulatorPaths._GUN_ROOT / "CXBX Silent Scope" / "cxbxr-ldr.exe"

    @staticmethod
    def cxbx_gun_vc3() -> Path:
        return EmulatorPaths._GUN_ROOT / "CXBX VC3" / "cxbxr-ldr.exe"

    @staticmethod
    def t4user() -> Path:
        return EmulatorPaths._GUN_ROOT / "T4User" / "T4User.exe"

    @classmethod
    def all_executables(cls) -> dict:
        """
        Return dict of {name: Path} for every known emulator executable.
        Used by system health checks and discovery scans.
        """
        return {
            "mame": cls.mame(),
            "mame_gamepad": cls.mame_gamepad(),
            "psx_mame": cls.psx_mame(),
            "retroarch": cls.retroarch(),
            "retroarch_gamepad": cls.retroarch_gamepad(),
            "retroarch_fbneo": cls.retroarch_fbneo(),
            "dolphin": cls.dolphin(),
            "dolphin_joystick": cls.dolphin_joystick(),
            "dolphin_triforce": cls.dolphin_triforce(),
            "dolphin_mka1": cls.dolphin_mka1(),
            "dolphin_mka2": cls.dolphin_mka2(),
            "teknoparrot": cls.teknoparrot(),
            "teknoparrot_237": cls.teknoparrot_237(),
            "teknoparrot_140": cls.teknoparrot_140(),
            "teknoparrot_latest": cls.teknoparrot_latest(),
            "model2": cls.model2(),
            "supermodel": cls.supermodel(),
            "demul": cls.demul(),
            "demul_cdi": cls.demul_cdi(),
            "pcsx2": cls.pcsx2(),
            "pcsx2_joystick": cls.pcsx2_joystick(),
            "duckstation": cls.duckstation(),
            "ppsspp": cls.ppsspp(),
            "xenia": cls.xenia(),
            "xenia_canary": cls.xenia_canary(),
            "rpcs3": cls.rpcs3(),
            "cemu": cls.cemu(),
            "yuzu": cls.yuzu(),
            "citra": cls.citra(),
            "ryujinx": cls.ryujinx(),
            "redream": cls.redream(),
            "xemu": cls.xemu(),
            "cxbx": cls.cxbx(),
            "vita3k": cls.vita3k(),
            "mupen64": cls.mupen64(),
            "mesen": cls.mesen(),
            "fusion": cls.fusion(),
            "aae": cls.aae(),
            "rocket_launcher": cls.rocket_launcher(),
            "mfme": cls.mfme(),
            "mfme_19": cls.mfme_19(),
            "mame_gun": cls.mame_gun(),
            "mame_gun_4x3": cls.mame_gun_4x3(),
            "retroarch_gun": cls.retroarch_gun(),
            "retroarch_gun_win64": cls.retroarch_gun_win64(),
            "supermodel_gun": cls.supermodel_gun(),
            "model2_gun": cls.model2_gun(),
            "dolphin_gun": cls.dolphin_gun(),
            "dolphin_gun_50": cls.dolphin_gun_50(),
            "demul_gun": cls.demul_gun(),
            "demul_gun_braveff": cls.demul_gun_braveff(),
            "flycast_gun": cls.flycast_gun(),
            "pcsx2_gun": cls.pcsx2_gun(),
            "pcsx2_gcon45": cls.pcsx2_gcon45(),
            "pcsx2_tc": cls.pcsx2_tc(),
            "rpcs3_gun": cls.rpcs3_gun(),
            "rpcs3_eden": cls.rpcs3_eden(),
            "epsxe_gun": cls.epsxe_gun(),
            "teknoparrot_gun": cls.teknoparrot_gun(),
            "teknoparrot_gun_945": cls.teknoparrot_gun_945(),
            "teknoparrot_gun_latest": cls.teknoparrot_gun_latest(),
            "teknoparrot_gun_le3": cls.teknoparrot_gun_le3(),
            "flash_player": cls.flash_player(),
            "play2x6_gun": cls.play2x6_gun(),
            "snes9x_gun": cls.snes9x_gun(),
            "mesen_gun": cls.mesen_gun(),
            "cxbx_gun_silent_scope": cls.cxbx_gun_silent_scope(),
            "cxbx_gun_vc3": cls.cxbx_gun_vc3(),
            "t4user": cls.t4user(),
        }

    @classmethod
    def validate(cls) -> dict:
        """Return dict of {name: bool} for every known executable."""
        return {name: path.exists() for name, path in cls.all_executables().items()}
