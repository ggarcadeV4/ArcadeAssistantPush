"""
Controller Auto-Configuration Manager

Staging → Validate → Mirror pipeline for controller profiles.

SAFETY CONTRACT:
- Writes ONLY to A:\config\controllers\autoconfig\staging\*.cfg (sanctioned)
- Mirrors validated files to emulator trees (manager-only, not via general config routes)
- Validates size (<64KB), schema (valid .cfg format), naming (normalized)
- Logs all operations with device_class, vendor_id, product_id, profile_name
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

# Size limits
MAX_CONFIG_SIZE = 64 * 1024  # 64KB max per profile
MAX_LINE_LENGTH = 512  # Max line length in config

# Device class definitions
DEVICE_CLASSES = {
    "controller": ["gamepad", "controller", "joypad"],
    "encoder": ["arcade", "encoder", "ipac", "pacdrive"],
    "lightgun": ["lightgun", "gun", "aimtrak", "wiimote"],
    "led_controller": ["led", "ledwiz", "led-wiz", "pacdrive", "ultimarc", "blinky"]
}

class AutoConfigError(Exception):
    """Base exception for auto-config operations"""
    pass

class ValidationError(AutoConfigError):
    """Config validation failed"""
    pass

class MirrorError(AutoConfigError):
    """Mirror operation failed"""
    pass


def normalize_profile_name(name: str) -> str:
    """
    Normalize profile name to safe filesystem format.

    Examples:
        "8BitDo SN30 Pro+" → "8BitDo_SN30_Pro"
        "Xbox 360 Controller" → "Xbox_360_Controller"
    """
    # Remove unsafe characters
    safe = re.sub(r'[^\w\s-]', '', name)
    # Replace spaces/hyphens with underscores
    safe = re.sub(r'[\s-]+', '_', safe)
    # Remove leading/trailing underscores
    safe = safe.strip('_')
    return safe


def classify_device(name: str, vendor_id: Optional[str] = None, product_id: Optional[str] = None) -> str:
    """
    Classify device by name/VID/PID into controller/encoder/lightgun.

    Returns:
        "controller" | "encoder" | "lightgun" | "unknown"
    """
    name_lower = name.lower()

    # Check name against device class keywords
    for device_class, keywords in DEVICE_CLASSES.items():
        if any(kw in name_lower for kw in keywords):
            return device_class

    # VID/PID-based classification (optional enhancement)
    # For now, default to controller
    return "controller" if not any(kw in name_lower for kw in ["gun", "arcade"]) else "unknown"


def validate_config_content(content: str, profile_name: str) -> None:
    """
    Validate config file content.

    Checks:
        - Size <= 64KB
        - Valid .cfg format (key=value lines or sections)
        - No unsafe content (no shell commands, no path traversal)

    Raises:
        ValidationError: If validation fails
    """
    # Size check
    if len(content.encode('utf-8')) > MAX_CONFIG_SIZE:
        raise ValidationError(f"Config exceeds {MAX_CONFIG_SIZE} bytes")

    # Line length check
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if len(line) > MAX_LINE_LENGTH:
            raise ValidationError(f"Line {i} exceeds {MAX_LINE_LENGTH} characters")

    # Format validation (basic .cfg structure)
    has_valid_content = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith(';'):
            continue  # Comment or blank
        if stripped.startswith('[') and stripped.endswith(']'):
            continue  # Section header
        if '=' in stripped:
            has_valid_content = True
            # Check for unsafe patterns
            if any(unsafe in line.lower() for unsafe in ['$(', '`', 'eval', 'exec', '../', '..\\\\', '<script']):
                raise ValidationError(f"Unsafe content detected: {stripped[:50]}")
        else:
            # Non-comment, non-section, non-key=value line
            if stripped:  # Allow blank lines
                raise ValidationError(f"Invalid format at line {i}: {stripped[:50]}")

    if not has_valid_content:
        raise ValidationError("Config contains no valid key=value pairs")


def get_staging_path(profile_name: str, drive_root: Path) -> Path:
    """Get staging path for a profile"""
    normalized = normalize_profile_name(profile_name)
    return drive_root / "config" / "controllers" / "autoconfig" / "staging" / f"{normalized}.cfg"


def get_mirror_paths(profile_name: str, device_class: str, drive_root: Path) -> List[Path]:
    """
    Get list of mirror destinations for a profile.

    Returns paths for all emulators that support this device class.

    Example:
        controller → [A:\Emulators\RetroArch\autoconfig\8BitDo\8BitDo_SN30_Pro.cfg]
        lightgun → [A:\Emulators\RetroArch\autoconfig\lightgun\..., A:\MAME\ctrlr\lightgun\...]
    """
    normalized = normalize_profile_name(profile_name)
    mirrors = []

    # RetroArch autoconfig (controllers and lightguns)
    if device_class in ["controller", "lightgun"]:
        # Extract manufacturer from profile name (first word)
        manufacturer = normalized.split('_')[0] if '_' in normalized else normalized
        retroarch_dir = drive_root / "Emulators" / "RetroArch" / "autoconfig" / manufacturer
        mirrors.append(retroarch_dir / f"{normalized}.cfg")

    # MAME ctrlr configs (encoders and lightguns)
    if device_class in ["encoder", "lightgun"]:
        mame_dir = drive_root / "Emulators" / "MAME" / "ctrlr" / device_class
        mirrors.append(mame_dir / f"{normalized}.cfg")

    return mirrors


def mirror_to_emulators(staging_path: Path, profile_name: str, device_class: str, drive_root: Path) -> List[Path]:
    """
    Mirror validated config from staging to emulator trees.

    Args:
        staging_path: Source file in staging area
        profile_name: Profile name
        device_class: Device classification
        drive_root: AA_DRIVE_ROOT

    Returns:
        List of paths where config was mirrored

    Raises:
        MirrorError: If mirror operation fails
    """
    if not staging_path.exists():
        raise MirrorError(f"Staging file not found: {staging_path}")

    mirror_paths = get_mirror_paths(profile_name, device_class, drive_root)
    mirrored = []

    for target_path in mirror_paths:
        try:
            # Create parent directory if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(staging_path, target_path)
            mirrored.append(target_path)

        except Exception as e:
            raise MirrorError(f"Failed to mirror to {target_path}: {e}")

    return mirrored


def create_autoconfig_log_entry(
    operation: str,
    profile_name: str,
    device_class: str,
    vendor_id: Optional[str] = None,
    product_id: Optional[str] = None,
    backup_path: Optional[str] = None,
    mirror_paths: Optional[List[Path]] = None,
    device_id: str = "",
    panel: str = ""
) -> Dict[str, Any]:
    """
    Create log entry for autoconfig operation.

    Returns dict with all required fields for changes.jsonl
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "profile_name": profile_name,
        "device_class": device_class,
        "vendor_id": vendor_id,
        "product_id": product_id,
        "backup_path": backup_path,
        "mirror_paths": [str(p) for p in mirror_paths] if mirror_paths else [],
        "device": device_id,
        "panel": panel,
    }


def log_autoconfig_operation(drive_root: Path, entry: Dict[str, Any]) -> None:
    """Append autoconfig operation to changes.jsonl"""
    log_file = drive_root / ".aa" / "logs" / "changes.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")


# Public API

def stage_config(
    profile_name: str,
    content: str,
    device_class: str,
    vendor_id: Optional[str],
    product_id: Optional[str],
    drive_root: Path,
    device_id: str = "",
    panel: str = "controller_chuck"
) -> Dict[str, Any]:
    """
    Stage a controller config with validation.

    This should be called via /config/apply (not directly) to ensure
    proper backup creation and logging.

    Returns:
        Dict with staging_path and validation status
    """
    # Normalize and validate
    normalized = normalize_profile_name(profile_name)
    validate_config_content(content, profile_name)

    staging_path = get_staging_path(profile_name, drive_root)

    return {
        "staging_path": str(staging_path),
        "normalized_name": normalized,
        "device_class": device_class,
        "status": "validated",
        "size": len(content.encode('utf-8'))
    }


def mirror_staged_config(
    profile_name: str,
    device_class: str,
    vendor_id: Optional[str],
    product_id: Optional[str],
    drive_root: Path,
    device_id: str = "",
    panel: str = "controller_chuck"
) -> Dict[str, Any]:
    """
    Mirror a staged config to emulator trees.

    Args:
        profile_name: Profile name
        device_class: controller | encoder | lightgun
        vendor_id: USB VID (hex string)
        product_id: USB PID (hex string)
        drive_root: AA_DRIVE_ROOT
        device_id: x-device-id header value
        panel: x-panel header value

    Returns:
        Dict with mirror_paths and log entry

    Raises:
        MirrorError: If mirroring fails
    """
    staging_path = get_staging_path(profile_name, drive_root)

    # Mirror to emulator trees
    mirror_paths = mirror_to_emulators(staging_path, profile_name, device_class, drive_root)

    # Create log entry
    log_entry = create_autoconfig_log_entry(
        operation="mirror",
        profile_name=profile_name,
        device_class=device_class,
        vendor_id=vendor_id,
        product_id=product_id,
        mirror_paths=mirror_paths,
        device_id=device_id,
        panel=panel
    )

    # Log operation
    log_autoconfig_operation(drive_root, log_entry)

    return {
        "status": "mirrored",
        "profile_name": profile_name,
        "device_class": device_class,
        "mirror_paths": [str(p) for p in mirror_paths],
        "log_entry": log_entry
    }


def get_existing_profiles(device_class: str, drive_root: Path) -> List[str]:
    """
    List existing profiles for a device class.

    Returns list of profile names (without .cfg extension)
    """
    staging_dir = drive_root / "config" / "controllers" / "autoconfig" / "staging"

    if not staging_dir.exists():
        return []

    profiles = []
    for cfg_file in staging_dir.glob("*.cfg"):
        profiles.append(cfg_file.stem)

    return sorted(profiles)
