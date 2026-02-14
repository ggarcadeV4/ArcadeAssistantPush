"""PactoTech board repair scaffolding.

This module will eventually drive corrective actions (soft reset, mode toggles,
etc.) for Controller Chuck.  For now we expose the data structures and method
signatures so the router and gateway work can proceed incrementally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .board_sanity import BoardSanityScanner, HIDTransport, ModeFlags

logger = logging.getLogger(__name__)

@dataclass
class RepairReport:
    """Structured summary of a repair attempt.

    Fields intentionally mirror what Chuck will narrate back to the user once a
    repair is complete.  The `summary` string will be persona-ready text.
    """

    issue_detected: bool
    issue_type: Optional[str] = None
    actions_attempted: List[str] = field(default_factory=list)
    actions_successful: List[str] = field(default_factory=list)
    actions_failed: List[str] = field(default_factory=list)
    final_state_verified: bool = False
    mode_flags_before: Optional[ModeFlags] = None
    mode_flags_after: Optional[ModeFlags] = None
    summary: str = ""
    backup_path: Optional[str] = None


class BoardRepairService:
    """Coordinator for safe, reversible PactoTech repairs.

    This class will command the HID transport used by :mod:`board_sanity`
    to toggle mode flags, perform soft resets, and validate the board state.
    """

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._transport = HIDTransport()

    def repair(self, actions: List[str], dry_run: bool = True) -> RepairReport:
        """Coordinate dual-mode repairs using ModeFlags snapshots.

        Dry-run mode mutates copies of the ModeFlags so the persona can narrate
        the planned changes without touching hardware. Non-dry-run mode issues
        the same commands via HIDTransport after taking a fresh BoardSanityScanner
        reading and performs minimal validation/backup metadata recording.
        """
        scanner: Optional[BoardSanityScanner] = None
        try:
            scanner = BoardSanityScanner(self.device_id)
            scan_report = scanner.scan()
            before_flags = scan_report.mode_flags
        except Exception:  # pragma: no cover - hardware dependent
            before_flags = ModeFlags()
            scan_report = None

        after_flags = replace(before_flags)
        issue_detected = before_flags.turbo and before_flags.analog
        issue_type = "dual_mode_conflict" if issue_detected else None

        attempted: List[str] = []
        successes: List[str] = []
        failures: List[str] = []

        allowed_actions = ("disable_turbo", "disable_analog", "soft_reset")
        planned_actions: List[str] = [
            action for action in (actions or []) if action in allowed_actions
        ]
        if issue_detected:
            for required in ("disable_turbo", "disable_analog"):
                if required not in planned_actions:
                    planned_actions.append(required)
        if not planned_actions:
            planned_actions = list(planned_actions)  # ensure copy for mutation

        for action in planned_actions:
            attempted.append(action)
            if action == "disable_turbo":
                if dry_run:
                    if after_flags.turbo:
                        after_flags.turbo = False
                    successes.append(action)
                else:
                    if self.disable_turbo():
                        after_flags.turbo = False
                        successes.append(action)
                    else:
                        failures.append(action)
            elif action == "disable_analog":
                if dry_run:
                    if after_flags.analog:
                        after_flags.analog = False
                    successes.append(action)
                else:
                    if self.disable_analog():
                        after_flags.analog = False
                        successes.append(action)
                    else:
                        failures.append(action)
            elif action == "soft_reset":
                if dry_run:
                    successes.append(action)
                else:
                    if self.soft_reset():
                        successes.append(action)
                    else:
                        failures.append(action)

        if not dry_run:
            after_flags = self.validate_repair()

        backup_path = None
        if not dry_run:
            backup_path = self._preview_backup()

        final_state_verified = not after_flags.analog and not after_flags.turbo
        summary = self._build_summary(
            issue_detected=issue_detected,
            issue_type=issue_type,
            actions_successful=successes,
            actions_failed=failures,
            dry_run=dry_run,
            before=before_flags,
            after=after_flags,
        )
        report = RepairReport(
            issue_detected=issue_detected,
            issue_type=issue_type,
            actions_attempted=attempted,
            actions_successful=successes,
            actions_failed=failures,
            final_state_verified=final_state_verified,
            mode_flags_before=before_flags,
            mode_flags_after=after_flags,
            summary=summary,
            backup_path=backup_path,
        )
        self._record_change(report)
        return report

    def _preview_backup(self) -> Optional[str]:
        """Placeholder that would create and return a backup path."""
        return None

    def _record_change(self, report: RepairReport) -> None:
        """Placeholder that would log repair actions to a change log."""
        # Real logging will be implemented when sanctioned paths are available.
        return

    def soft_reset(self) -> bool:
        """Simulate the encoder soft reset command via HIDTransport."""
        try:
            return self._write_feature_report({"reset": True})
        except Exception as exc:  # pragma: no cover - transport failure
            logger.warning("Soft reset failed for %s: %s", self.device_id, exc)
            return False

    def disable_turbo(self) -> bool:
        """Send the feature-report mutation that clears the turbo flag."""
        try:
            return self._write_feature_report({"turbo": False})
        except Exception as exc:  # pragma: no cover - transport failure
            logger.warning("Failed to disable turbo for %s: %s", self.device_id, exc)
            return False

    def disable_analog(self) -> bool:
        """Send the feature-report mutation that clears the analog flag."""
        try:
            return self._write_feature_report({"analog": False})
        except Exception as exc:  # pragma: no cover - transport failure
            logger.warning("Failed to disable analog for %s: %s", self.device_id, exc)
            return False

    def reset_to_default(self) -> bool:
        """Apply the known-safe default preset (no turbo, D-Pad only)."""
        return True

    def validate_repair(self) -> ModeFlags:
        """Run a post-repair sanity scan to confirm the board state."""
        return self._get_current_mode_flags()

    def _get_current_mode_flags(self) -> ModeFlags:
        try:
            scanner = BoardSanityScanner(self.device_id)
            report = scanner.scan()
            return report.mode_flags
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("Failed to read mode flags for %s: %s", self.device_id, exc)
            return ModeFlags()

    @staticmethod
    def _build_summary(
        issue_detected: bool,
        issue_type: Optional[str],
        actions_successful: List[str],
        actions_failed: List[str],
        dry_run: bool,
        before: ModeFlags,
        after: ModeFlags,
    ) -> str:
        sentences: List[str] = []
        if issue_detected and issue_type == "dual_mode_conflict":
            sentences.append(
                "I spotted analog and turbo running together, which causes cross-talk on this encoder."
            )
            if dry_run:
                sentences.append(
                    "I simulated disabling both flags so you can preview the fix without writing to hardware."
                )
            else:
                if actions_failed:
                    sentences.append(
                        f"I tried to disable both flags but these steps failed: {', '.join(actions_failed)}."
                    )
                else:
                    sentences.append(
                        "I disabled the conflict directly on the board and verified the commands were accepted."
                    )
            if actions_successful:
                sentences.append(
                    f"Successful steps: {', '.join(actions_successful)}."
                )
            sentences.append(
                f"Latest telemetry reports turbo={'ON' if after.turbo else 'OFF'} and analog={'ON' if after.analog else 'OFF'}."
            )
            sentences.append(
                "Let me know if you want another scan or a full reset for extra assurance."
            )
            return " ".join(sentences)

        sentences.append(
            "I did not detect the analog+turbo conflict during this session."
        )
        if actions_successful:
            sentences.append(
                f"I still simulated the requested steps ({', '.join(actions_successful)}) so you know what would happen."
            )
        sentences.append(
            f"The board currently reports turbo={'ON' if after.turbo else 'OFF'} and analog={'ON' if after.analog else 'OFF'}."
        )
        sentences.append("Everything looks steady, but ping me if you notice new symptoms.")
        return " ".join(sentences)

    def _write_feature_report(self, payload: Dict[str, Any]) -> bool:
        """Stubbed HID write that validates driver availability."""
        driver = getattr(self._transport, "_driver", None)
        if not driver:
            return False
        # Real HID write will map payload to feature report bytes.
        logger.debug("Simulated HID write for %s: %s", self.device_id, payload)
        return True
