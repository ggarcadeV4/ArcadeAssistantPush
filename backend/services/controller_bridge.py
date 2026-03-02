"""
controller_bridge.py
═══════════════════════════════════════════════════════════════════
ControllerBridge — the sole merge authority for controller mappings.

Decision refs (diagnosis_mode_plan.md):
  Q4  — ControllerBridge holds GPIO authority; semantic layer reads via
         hardware truth; 4 conflict types: pin collision, player boundary
         violation, sacred-number deviation, orphaned key
  Q7  — Hardware truth wins; 4 conflict resolution types; rollback mechanism
  Q8  — Optimistic per-input + confirm-before-commit (5-step atomic flow)

Responsibilities:
  1. Load / validate controls.json                  (load_mapping)
  2. Propose a single-input override                (propose_override)
  3. Detect and classify conflicts                  (detect_conflicts)
  4. Commit an override atomically with backup      (commit_override)
  5. Rollback to pre-commit backup                  (rollback)
  6. Enforce sacred button numbering law             (validate_sacred_law)

NOT responsible for:
  - Cascade orchestration      → services/controller_cascade.py
  - Emulator config generation → services/mame_config_generator.py
  - AI tool invocation         → services/chuck/ai.py
"""

from __future__ import annotations

import json
import logging
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Sacred Button Law (immutable — never change without a cabinet rebuild)
# ─────────────────────────────────────────────────────────────────────────────
# P1/P2 — 8 buttons: top row 1-2-3-7, bottom row 4-5-6-8
# P3/P4 — 4 buttons: top row 1-2, bottom row 3-4
SACRED_8BTN_TOP    = {1, 2, 3, 7}
SACRED_8BTN_BOTTOM = {4, 5, 6, 8}
SACRED_4BTN_TOP    = {1, 2}
SACRED_4BTN_BOTTOM = {3, 4}
SACRED_PLAYERS_8BTN = {"p1", "p2"}
SACRED_PLAYERS_4BTN = {"p3", "p4"}

# ─────────────────────────────────────────────────────────────────────────────
# Conflict types (Q4 / Q7)
# ─────────────────────────────────────────────────────────────────────────────
ConflictType = Literal[
    "pin_collision",         # GPIO pin already assigned to another control
    "player_boundary",       # Writing to a player slot that doesn't exist
    "sacred_law_deviation",  # Button number violates the doctrine
    "orphaned_key",          # Control key references non-existent player
]


class ControllerBridgeError(Exception):
    """Raised when ControllerBridge operations fail unrecoverably."""


class ConflictError(ControllerBridgeError):
    """Raised when a proposed override contains unresolvable conflicts."""

    def __init__(self, conflicts: List[Dict[str, Any]]) -> None:
        super().__init__(f"{len(conflicts)} conflict(s) detected")
        self.conflicts = conflicts


# ─────────────────────────────────────────────────────────────────────────────
# Data class helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mapping_path(drive_root: Path) -> Path:
    return drive_root / "config" / "mappings" / "controls.json"


def _backup_path(drive_root: Path, control_key: str) -> Path:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    safe_key = control_key.replace(".", "_")
    return drive_root / "config" / "mappings" / "backups" / f"controls_{safe_key}_{ts}.json"


# ─────────────────────────────────────────────────────────────────────────────
# ControllerBridge
# ─────────────────────────────────────────────────────────────────────────────

class ControllerBridge:
    """
    Sole merge authority for controller mappings.

    One instance per request (stateless service pattern).

    Usage:
        bridge = ControllerBridge(drive_root)
        proposal = bridge.propose_override(
            control_key="p1.button3",
            pin=42,
            label="Fire",
            source="ai_tool",      # or "user", "hardware"
        )
        if proposal["conflicts"]:
            # surface to UI — AI should explain and ask user to confirm
            ...
        result = bridge.commit_override(proposal, confirmed_by="user")
    """

    def __init__(self, drive_root: Path) -> None:
        self.drive_root   = Path(drive_root)
        self._mapping_path = _mapping_path(self.drive_root)
        self._backup: Optional[Path] = None   # set on commit, used for rollback

    # ── Load ───────────────────────────────────────────────────────────────────

    def load_mapping(self) -> Dict[str, Any]:
        """Load controls.json. Returns empty dict if file missing."""
        if not self._mapping_path.exists():
            logger.warning("[ControllerBridge] controls.json not found at %s", self._mapping_path)
            return {"mappings": {}, "board": {}}
        try:
            with open(self._mapping_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ControllerBridgeError(f"Invalid controls.json: {exc}") from exc

    # ── Sacred Law ─────────────────────────────────────────────────────────────

    def validate_sacred_law(
        self,
        control_key: str,
        button_num: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """
        Assert the control_key respects the sacred button numbering.
        Returns a conflict dict or None if clean.
        """
        parts = control_key.split(".")
        if len(parts) < 2:
            return None   # directional / util keys — no sacred law applies

        player, control = parts[0], parts[1]
        if not control.startswith("button"):
            return None   # joystick / util — skip

        if button_num is None:
            try:
                button_num = int("".join(filter(str.isdigit, control)))
            except ValueError:
                return None

        if player in SACRED_PLAYERS_8BTN:
            valid = SACRED_8BTN_TOP | SACRED_8BTN_BOTTOM
        elif player in SACRED_PLAYERS_4BTN:
            valid = SACRED_4BTN_TOP | SACRED_4BTN_BOTTOM
        else:
            return None   # unknown player — skip

        if button_num not in valid:
            return {
                "type"        : "sacred_law_deviation",
                "control_key" : control_key,
                "button_num"  : button_num,
                "valid_set"   : sorted(valid),
                "message"     : (
                    f"Button {button_num} is not in the sacred set {sorted(valid)} for {player}. "
                    "The button numbering law is the Rosetta Stone for all 45+ emulator configs — "
                    "deviating from it will silently break controls across the whole stack."
                ),
                "severity"    : "error",
            }
        return None

    # ── Conflict detection ─────────────────────────────────────────────────────

    def detect_conflicts(
        self,
        control_key: str,
        pin: int,
        mapping_data: Dict[str, Any],
        *,
        button_num: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run all 4 conflict checks (Q4).
        Returns a list of conflict dicts (empty = clean).
        """
        conflicts: List[Dict[str, Any]] = []
        mappings = mapping_data.get("mappings", {})

        # 1. Pin collision
        for existing_key, entry in mappings.items():
            if existing_key == control_key:
                continue
            if isinstance(entry, dict) and entry.get("pin") == pin:
                conflicts.append({
                    "type"         : "pin_collision",
                    "control_key"  : control_key,
                    "pin"          : pin,
                    "conflicts_with": existing_key,
                    "message"      : (
                        f"GPIO pin {pin} is already assigned to {existing_key}. "
                        "Assigning the same pin to two controls will cause ghost inputs."
                    ),
                    "severity"     : "error",
                })

        # 2. Player boundary — key must parse to a known player
        parts = control_key.split(".")
        if parts:
            player = parts[0]
            if player not in (SACRED_PLAYERS_8BTN | SACRED_PLAYERS_4BTN | {"p1", "p2", "p3", "p4"}):
                conflicts.append({
                    "type"        : "orphaned_key",
                    "control_key" : control_key,
                    "player"      : player,
                    "message"     : f"Player '{player}' is not a recognised player slot (p1–p4).",
                    "severity"    : "warning",
                })

        # 3. Sacred law
        sacred_conflict = self.validate_sacred_law(control_key, button_num)
        if sacred_conflict:
            conflicts.append(sacred_conflict)

        return conflicts

    # ── Propose ────────────────────────────────────────────────────────────────

    def propose_override(
        self,
        control_key: str,
        pin: int,
        label: Optional[str] = None,
        source: str = "user",
        button_num: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build a preview-only override proposal. Does NOT write to disk.

        Returns:
            {
                control_key, pin, label, source,
                conflicts: [...],
                mapping_before: {...},
                mapping_after:  {...},
                can_auto_commit: bool,  # True if no errors
            }
        """
        mapping_data  = self.load_mapping()
        conflicts     = self.detect_conflicts(
            control_key, pin, mapping_data, button_num=button_num
        )
        has_errors    = any(c["severity"] == "error" for c in conflicts)

        # Build the proposed mapping_after state (in memory only)
        mapping_before = deepcopy(mapping_data)
        mapping_after  = deepcopy(mapping_data)
        mapping_after.setdefault("mappings", {})[control_key] = {
            "pin"    : pin,
            "label"  : label or control_key,
            "type"   : "button" if "button" in control_key else "joystick",
            "source" : source,
        }

        return {
            "control_key"     : control_key,
            "pin"             : pin,
            "label"           : label,
            "source"          : source,
            "conflicts"       : conflicts,
            "mapping_before"  : mapping_before,
            "mapping_after"   : mapping_after,
            "can_auto_commit" : not has_errors,
        }

    # ── Commit (5-step atomic flow — Q8) ──────────────────────────────────────

    def commit_override(
        self,
        proposal: Dict[str, Any],
        *,
        confirmed_by: str = "user",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Atomically write the proposed override.

        Q8 — 5-step atomic flow:
          1. Validate proposal is not stale (reload mapping, re-check conflicts)
          2. Create timestamped backup
          3. Write new mapping to disk
          4. Update metadata (last_modified, modified_by, source)
          5. Return result including backup path for rollback

        Args:
            proposal:      Result from propose_override()
            confirmed_by:  Who confirmed ("user" | "ai_tool" | "auto")
            force:         If True, commit even if error-severity conflicts exist

        Raises:
            ConflictError if non-force and error conflicts remain.
            ControllerBridgeError on I/O failure.
        """
        # ── Step 1: Stale-check ───────────────────────────────────────────────
        current_mapping = self.load_mapping()
        fresh_conflicts = self.detect_conflicts(
            proposal["control_key"],
            proposal["pin"],
            current_mapping,
        )
        has_errors = any(c["severity"] == "error" for c in fresh_conflicts)

        if has_errors and not force:
            raise ConflictError(fresh_conflicts)

        # ── Step 2: Backup ────────────────────────────────────────────────────
        backup_dest = _backup_path(self.drive_root, proposal["control_key"])
        backup_dest.parent.mkdir(parents=True, exist_ok=True)
        if self._mapping_path.exists():
            shutil.copy2(self._mapping_path, backup_dest)
        self._backup = backup_dest

        # ── Step 3 + 4: Write ─────────────────────────────────────────────────
        new_mapping      = deepcopy(current_mapping)
        new_mapping.setdefault("mappings", {})[proposal["control_key"]] = {
            "pin"          : proposal["pin"],
            "label"        : proposal.get("label") or proposal["control_key"],
            "type"         : "button" if "button" in proposal["control_key"] else "joystick",
            "source"       : proposal.get("source", "user"),
            "confirmed_by" : confirmed_by,
        }
        new_mapping["last_modified"] = datetime.now().isoformat()
        new_mapping["modified_by"]   = confirmed_by

        self._mapping_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._mapping_path, "w", encoding="utf-8") as fh:
                json.dump(new_mapping, fh, indent=2)
        except OSError as exc:
            # I/O failure — attempt rollback from backup
            if backup_dest.exists():
                shutil.copy2(backup_dest, self._mapping_path)
            raise ControllerBridgeError(f"Write failed (rolled back): {exc}") from exc

        logger.info(
            "[ControllerBridge] Committed %s → pin %d (confirmed_by=%s)",
            proposal["control_key"],
            proposal["pin"],
            confirmed_by,
        )

        # ── Step 5: Return result ─────────────────────────────────────────────
        return {
            "status"         : "committed",
            "control_key"    : proposal["control_key"],
            "pin"            : proposal["pin"],
            "confirmed_by"   : confirmed_by,
            "backup_path"    : str(backup_dest),
            "mapping"        : new_mapping,
            "warnings"       : [c for c in fresh_conflicts if c["severity"] == "warning"],
        }

    # ── Rollback ───────────────────────────────────────────────────────────────

    def rollback(self) -> Dict[str, Any]:
        """
        Restore controls.json from the backup created in the last commit.
        Only valid immediately after a commit_override call.
        """
        if not self._backup or not self._backup.exists():
            raise ControllerBridgeError(
                "No backup available for rollback. "
                "commit_override must be called first."
            )

        shutil.copy2(self._backup, self._mapping_path)
        logger.info("[ControllerBridge] Rolled back to %s", self._backup)
        return {
            "status"       : "rolled_back",
            "restored_from": str(self._backup),
        }
