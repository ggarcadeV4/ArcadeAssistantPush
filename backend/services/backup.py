import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.constants.drive_root import relativize_runtime_path

def create_backup(target_path: Path, drive_root: Path) -> Path:
    """Create a timestamped backup of the target file

    Args:
        target_path: Path to the file to backup
        drive_root: Root directory of the AA drive

    Returns:
        Path to the created backup file
    """
    if not target_path.exists():
        raise FileNotFoundError(f"Target file does not exist: {target_path}")

    # Create backup directory with current date under .aa/backups
    timestamp = datetime.now().strftime("%Y%m%d")
    backup_dir = drive_root / ".aa" / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique backup filename with time
    time_suffix = datetime.now().strftime("%H%M%S")
    
    relative_path = relativize_runtime_path(target_path, drive_root)

    # Replace path separators with underscores for filename
    backup_filename = str(relative_path).replace(os.sep, "_").replace("/", "_")
    backup_filename = f"{time_suffix}_{backup_filename}"

    backup_path = backup_dir / backup_filename

    # Copy the file
    shutil.copy2(target_path, backup_path)

    print(f"Created backup: {backup_path}")
    return backup_path

def restore_from_backup(backup_path: Path, target_path: Path) -> bool:
    """Restore a file from backup

    Args:
        backup_path: Path to the backup file
        target_path: Path where to restore the file

    Returns:
        True if restore was successful
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file does not exist: {backup_path}")

    # Ensure target directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy backup to target location
    shutil.copy2(backup_path, target_path)

    print(f"Restored from backup: {backup_path} -> {target_path}")
    return True
