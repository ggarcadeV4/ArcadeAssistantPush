"""LED Pattern Storage with sanctioned paths and backup workflow.

Safety Constraint: All pattern storage MUST use the sanctioned path and
create a backup before any write operation.

Sanctioned Path: A:/Arcade Assistant/configs/led-patterns.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .backup import create_backup

logger = logging.getLogger(__name__)

# SANCTIONED PATH - Do not modify without Senior Architect approval
SANCTIONED_PATH = Path("A:/Arcade Assistant/configs/led-patterns.json")


class LEDPatternStorage:
    """Storage service for LED patterns with mandatory backup workflow.
    
    Implements Preview → Apply → Backup pattern for safe file mutations.
    """
    
    def __init__(self, drive_root: Path):
        """Initialize storage service.
        
        Args:
            drive_root: Root directory for backup operations
        """
        self._drive_root = drive_root
        self._sanctioned_path = SANCTIONED_PATH
    
    def _load_current(self) -> Dict[str, Any]:
        """Load current patterns from sanctioned path.
        
        Returns:
            Current pattern data or empty dict if file doesn't exist
        """
        if not self._sanctioned_path.exists():
            return {}
        
        try:
            return json.loads(self._sanctioned_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load patterns: {e}")
            return {}
    
    def preview_patterns(self, proposed: Dict[str, Any]) -> Dict[str, Any]:
        """Preview changes without saving.
        
        Args:
            proposed: New pattern data to preview
            
        Returns:
            Dict with 'current' and 'proposed' for comparison
        """
        current = self._load_current()
        return {
            "current": current,
            "proposed": proposed,
            "has_changes": current != proposed,
            "sanctioned_path": str(self._sanctioned_path)
        }
    
    def apply_patterns(self, patterns: Dict[str, Any]) -> Dict[str, Any]:
        """Save patterns with mandatory backup workflow.
        
        Safety: Creates backup BEFORE writing new data.
        
        Args:
            patterns: Pattern data to save
            
        Returns:
            Result dict with status and backup path
        """
        backup_path: Optional[Path] = None
        
        # Ensure parent directory exists
        self._sanctioned_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Step 1: Create backup if file exists
        if self._sanctioned_path.exists():
            try:
                backup_path = create_backup(self._sanctioned_path, self._drive_root)
                logger.info(f"Backup created: {backup_path}")
            except Exception as e:
                logger.error(f"Backup failed: {e}")
                return {
                    "status": "error",
                    "error": f"Backup failed: {e}",
                    "backup_path": None
                }
        
        # Step 2: Write new patterns
        try:
            self._sanctioned_path.write_text(
                json.dumps(patterns, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.info(f"Patterns saved to {self._sanctioned_path}")
        except IOError as e:
            logger.error(f"Write failed: {e}")
            return {
                "status": "error",
                "error": f"Write failed: {e}",
                "backup_path": str(backup_path) if backup_path else None
            }
        
        return {
            "status": "applied",
            "sanctioned_path": str(self._sanctioned_path),
            "backup_path": str(backup_path) if backup_path else None
        }
    
    def get_patterns(self) -> Dict[str, Any]:
        """Get current patterns from storage.
        
        Returns:
            Current pattern data
        """
        return self._load_current()


# Module-level factory
_storage: Optional[LEDPatternStorage] = None


def get_pattern_storage(drive_root: Path) -> LEDPatternStorage:
    """Get or create pattern storage instance.
    
    Args:
        drive_root: Root directory for backup operations
        
    Returns:
        LEDPatternStorage instance
    """
    global _storage
    if _storage is None:
        _storage = LEDPatternStorage(drive_root)
    return _storage
