from pathlib import Path
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class RetroArchConfigGenerator:
    def __init__(self, drive_root: str = "A:"):
        self.drive_root = Path(drive_root)
        self.config_dir = self.drive_root / "config" / "retroarch" / "config"
        self.sot_path = self.drive_root / "config" / "mappings" / "controls.json"

    def normalize_key(self, key: str) -> str:
        """Normalize config keys with whitespace/comment awareness"""
        # Remove comments
        key = re.sub(r'#.*$', '', key)
        # Normalize whitespace and case
        key = key.strip().lower().replace('-', '_').replace(' ', '_')
        # Remove duplicate underscores
        key = re.sub(r'_+', '_', key)
        return key

    def parse_existing_config(self, config_path: Path) -> Tuple[Dict, List]:
        """Parse existing config preserving comments and order"""
        config = {}
        comments = []

        if not config_path.exists():
            return config, comments

        for line_num, line in enumerate(config_path.read_text().splitlines()):
            if line.strip().startswith('#') or not line.strip():
                comments.append((line_num, line))
            elif ' = ' in line:
                key, value = line.split(' = ', 1)
                normalized_key = self.normalize_key(key)
                config[normalized_key] = (key.strip(), value.strip('"'))

        return config, comments

    def generate_core_config(self, core: str, controls: Dict) -> Dict[str, str]:
        """Generate deduplicated config for specific core"""
        config = {}
        seen_normalized = set()

        for key, value in controls.items():
            normalized = self.normalize_key(key)
            if normalized and normalized not in seen_normalized:
                config[key] = str(value)
                seen_normalized.add(normalized)

        return config

    def diff_configs(self, existing: Dict, new: Dict) -> Dict:
        """Generate diff between configs"""
        # Normalize existing keys for comparison
        existing_normalized = {self.normalize_key(k): v for k, v in existing.items()}
        new_normalized = {self.normalize_key(k): v for k, v in new.items()}

        added = {k: v for k, v in new.items() if self.normalize_key(k) not in existing_normalized}
        changed = {k: (existing_normalized.get(self.normalize_key(k)), v)
                  for k, v in new.items()
                  if self.normalize_key(k) in existing_normalized and existing_normalized[self.normalize_key(k)] != v}
        removed = {k: v for k, v in existing.items() if self.normalize_key(k) not in new_normalized}

        return {
            "added": added,
            "changed": changed,
            "removed": removed,
            "total_ops": len(added) + len(changed) + len(removed)
        }