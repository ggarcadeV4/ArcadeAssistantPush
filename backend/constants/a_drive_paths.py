"""
Drive path constants for LaunchBox integration.
NEVER hardcode paths elsewhere - always import from this module.

IMPORTANT: Runtime paths resolve from AA_DRIVE_ROOT and the shared drive-root
helpers, not from an inferred bare drive letter.

Critical path corrections (2025-10-06):
- LaunchBox root is <AA_DRIVE_ROOT>/LaunchBox unless LAUNCHBOX_ROOT overrides it
- Master XML (LaunchBox.xml) NOT FOUND - must parse platform XMLs
- CLI_Launcher.exe NOT FOUND - use fallback launch methods
"""
from pathlib import Path

from backend.constants.drive_root import (
    get_bios_root,
    get_drive_root,
    get_emulators_root,
    get_gun_emulators_root,
    get_launchbox_root,
    get_roms_root,
)


def _safe_path(factory):
    try:
        return factory()
    except Exception:
        return Path("<AA_DRIVE_ROOT_NOT_SET>")


AA_ROOT = _safe_path(lambda: get_drive_root(allow_cwd_fallback=False))
AA_DRIVE_ROOT = str(AA_ROOT)
STATE_DIR = AA_ROOT / ".aa" / "state"

# Legacy alias kept for compatibility with older imports.
DRIVE_LETTER_ROOT = AA_DRIVE_ROOT
LAUNCHBOX_ROOT_OVERRIDE = _safe_path(get_launchbox_root)


def is_on_a_drive() -> bool:
    """Check whether the configured root points at a reachable LaunchBox tree."""
    try:
        root_path = get_drive_root(allow_cwd_fallback=False)
        launchbox_root = get_launchbox_root(root_path)
    except Exception:
        return False

    if not root_path.exists():
        return False

    candidates = [
        launchbox_root,
        launchbox_root / "Data" / "Platforms",
        launchbox_root / "LaunchBox.exe",
    ]
    return any(candidate.exists() for candidate in candidates)


class LaunchBoxPaths:
    """
    LaunchBox directory structure constants.
    Configurable via LAUNCHBOX_ROOT environment variable.
    All paths derived dynamically from AA_DRIVE_ROOT.
    """

    # Root (configurable via env)
    LAUNCHBOX_ROOT = LAUNCHBOX_ROOT_OVERRIDE
    AA_DRIVE_ROOT = AA_DRIVE_ROOT

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

    # ROMs
    ROMS_ROOT = _safe_path(get_roms_root)
    MAME_ROMS = ROMS_ROOT / "MAME"  # 14,233 .zip files

    # BIOS
    BIOS_ROOT = _safe_path(get_bios_root)
    SYSTEM_BIOS = BIOS_ROOT / "system"  # 586 files

    # Emulators
    EMULATORS_ROOT = _safe_path(get_emulators_root)
    MAME_EMULATOR = EMULATORS_ROOT / "MAME" / "mame.exe"

    @classmethod
    def _get_launchbox_root_dynamic(cls) -> Path:
        """Get LaunchBox root dynamically from the current configured root."""
        return _safe_path(get_launchbox_root)

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
LB_PLATFORMS_GLOB = str(LAUNCHBOX_ROOT_OVERRIDE / "Data" / "Platforms" / "*.xml")


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
      - <AA_DRIVE_ROOT>/Emulators -> Arcade Panel & Gamepad builds
      - <AA_DRIVE_ROOT>/Gun Build/Emulators -> Light Gun builds
    RULES:
      - Every physical emulator folder with a distinct executable gets an accessor.
      - Variants that share the SAME executable but differ only by CLI args
        (e.g. Demul vs Demul Arcade) do NOT get separate accessors.
      - all_executables() must list every accessor for health-check scanning.
    """

    _PANEL_ROOT = _safe_path(get_emulators_root)
    _GUN_ROOT = _safe_path(get_gun_emulators_root)

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
