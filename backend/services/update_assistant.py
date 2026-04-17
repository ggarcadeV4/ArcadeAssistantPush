"""
AI-Assisted Update Service for Arcade Assistant
The AI helps analyze, validate, and apply updates intelligently.

Why AI-Assisted Updates?
1. Consistent behavior across all cabinets in the fleet
2. Intelligent conflict detection (local state vs update)
3. Natural language explanations for users
4. Edge case handling without hardcoding every scenario
5. Self-healing capabilities

The AI uses Haiku (cheap) for analysis, only escalating to Sonnet
for complex conflicts. This keeps fleet-wide costs minimal.
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from backend.constants.drive_root import get_drive_root
logger = logging.getLogger(__name__)


UPDATE_TIMEOUT_SECONDS = 120
ROLLBACK_SIZE_LIMIT_BYTES = 500 * 1024 * 1024
PROTECTED_UPDATE_PATHS = {
    Path(".aa/device_id.txt"),
    Path(".aa/cabinet_manifest.json"),
    Path(".env"),
}
PROTECTED_UPDATE_PREFIXES = {
    Path(".aa/state"),
}
ROLLBACK_SNAPSHOT_PATHS = (
    Path("backend"),
    Path("frontend/dist"),
    Path("gateway"),
    Path("configs"),
    Path("prompts"),
)


@dataclass
class UpdateAnalysis:
    """Result of AI analyzing an update."""
    safe_to_apply: bool
    confidence: float  # 0-1
    summary: str  # Human-readable summary
    changes: List[str]  # List of changes
    risks: List[str]  # Potential risks identified
    conflicts: List[Dict[str, Any]]  # Detected conflicts with local state
    recommendations: List[str]  # AI recommendations
    requires_user_approval: bool
    estimated_downtime_seconds: int


@dataclass
class UpdateResult:
    """Result of applying an update."""
    success: bool
    version_before: str
    version_after: str
    changes_applied: List[str]
    errors: List[str]
    rollback_available: bool
    ai_summary: str  # AI-generated summary of what happened


class UpdateAssistant:
    """
    AI-powered update assistant for Arcade Assistant.
    
    Runs on each cabinet, ensuring consistent update behavior across fleet.
    Uses local AI routing to minimize costs while maximizing reliability.
    """
    
    def __init__(self):
        self._drive_root = get_drive_root(context="update_assistant")
        self._updates_dir = self._drive_root / ".aa" / "updates"
        self._state_dir = self._drive_root / ".aa" / "state"
        self._logs_dir = self._drive_root / ".aa" / "logs" / "updates"
        self._updates_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def _updates_enabled(self) -> bool:
        return os.getenv("AA_UPDATES_ENABLED", "0") == "1"

    def _staging_dir(self) -> Path:
        path = self._updates_dir / "staging"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _rollback_dir(self) -> Path:
        path = self._updates_dir / "rollback"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _record_dir(self) -> Path:
        path = self._updates_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _normalize_relative_path(self, raw_path: str) -> Path:
        normalized = Path(str(raw_path or "").replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"Unsafe update path: {raw_path}")
        return normalized

    def _is_protected_path(self, relative_path: Path) -> bool:
        if relative_path in PROTECTED_UPDATE_PATHS:
            return True
        return any(relative_path == prefix or prefix in relative_path.parents for prefix in PROTECTED_UPDATE_PREFIXES)

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _load_manifest_from_directory(self, extracted_root: Path) -> Dict[str, Any]:
        manifest_path = extracted_root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("Update bundle is missing manifest.json")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _safe_extract_zip(self, bundle_path: Path, extracted_root: Path) -> None:
        with zipfile.ZipFile(bundle_path) as archive:
            for member in archive.infolist():
                relative_path = self._normalize_relative_path(member.filename)
                target_path = extracted_root / relative_path
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

    def _validate_extracted_manifest(self, extracted_root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        files = manifest.get("files")
        if not isinstance(files, list):
            raise ValueError("Update manifest must include a files list")

        normalized_files: List[Dict[str, Any]] = []
        for file_info in files:
            relative_path = self._normalize_relative_path(str(file_info.get("path", "")))
            action = str(file_info.get("action", "replace")).lower()
            if action not in {"replace", "add", "delete"}:
                raise ValueError(f"Unsupported update action: {action}")

            source_path = extracted_root / relative_path
            if action in {"replace", "add"} and not source_path.exists():
                raise FileNotFoundError(f"Bundle is missing payload file: {relative_path}")

            checksum = str(file_info.get("sha256") or "").strip()
            if checksum and source_path.exists() and source_path.is_file():
                actual_checksum = self._file_sha256(source_path)
                if actual_checksum.lower() != checksum.lower():
                    raise ValueError(f"Checksum mismatch for {relative_path}")

            normalized_files.append(
                {
                    **file_info,
                    "path": str(relative_path).replace("\\", "/"),
                    "action": action,
                }
            )

        return normalized_files

    def _compute_snapshot_size_bytes(self) -> int:
        total = 0
        for relative_path in ROLLBACK_SNAPSHOT_PATHS:
            source = self._drive_root / relative_path
            if not source.exists():
                continue
            if source.is_file():
                total += source.stat().st_size
                continue
            for entry in source.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        return total

    def _restore_directory(self, source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination, dirs_exist_ok=True)

    def _report_command_status(
        self,
        command_id: Optional[Union[str, int]],
        status: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        if command_id is None:
            return
        try:
            from backend.services.supabase_client import update_command_status

            update_command_status(str(command_id), status, result)
        except Exception as exc:
            logger.warning(f"[UpdateAssistant] Failed to report command status: {exc}")

    def _disabled_result(self) -> Dict[str, Any]:
        logger.warning("[UpdateAssistant] Updates disabled - AA_UPDATES_ENABLED != 1")
        return {"status": "disabled", "reason": "AA_UPDATES_ENABLED is not set to 1"}

    async def download_update(
        self,
        bundle_url: str,
        checksum: Optional[str] = None,
        bundle_name: Optional[str] = None,
    ) -> Union[Path, Dict[str, Any]]:
        """Download an update bundle into the staging directory."""
        if not self._updates_enabled():
            return self._disabled_result()

        if not bundle_url:
            raise ValueError("bundle_url is required")

        staging_dir = self._staging_dir()
        parsed = urlparse(bundle_url)
        filename = bundle_name or Path(parsed.path).name or f"update_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
        destination = staging_dir / filename
        digest = hashlib.sha256()

        try:
            if parsed.scheme in {"http", "https"}:
                timeout = httpx.Timeout(UPDATE_TIMEOUT_SECONDS)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    async with client.stream("GET", bundle_url) as response:
                        response.raise_for_status()
                        with open(destination, "wb") as handle:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                if not chunk:
                                    continue
                                handle.write(chunk)
                                digest.update(chunk)
            else:
                source_path = Path(bundle_url)
                if not source_path.exists():
                    raise FileNotFoundError(f"Update bundle not found: {bundle_url}")
                with open(source_path, "rb") as source, open(destination, "wb") as handle:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        handle.write(chunk)
                        digest.update(chunk)

            if not destination.exists() or destination.stat().st_size <= 0:
                raise ValueError("Downloaded update bundle is empty")

            if checksum and digest.hexdigest().lower() != checksum.lower():
                raise ValueError("Downloaded update bundle checksum mismatch")

            logger.info(f"[UpdateAssistant] Downloaded update bundle to {destination}")
            return destination
        except Exception as exc:
            logger.error(f"[UpdateAssistant] download_update failed: {exc}")
            destination.unlink(missing_ok=True)
            raise

    async def create_rollback_snapshot(
        self,
        source_version: Optional[str] = None,
    ) -> Union[Path, Dict[str, Any]]:
        """Create a rollback snapshot of critical runtime directories."""
        if not self._updates_enabled():
            return self._disabled_result()

        snapshot_root = self._rollback_dir()
        total_size = self._compute_snapshot_size_bytes()
        if total_size > ROLLBACK_SIZE_LIMIT_BYTES:
            raise ValueError(
                f"Rollback snapshot would exceed 500MB ({total_size} bytes)"
            )

        for relative_path in ROLLBACK_SNAPSHOT_PATHS:
            target = snapshot_root / relative_path
            if target.exists():
                shutil.rmtree(target)

        for relative_path in ROLLBACK_SNAPSHOT_PATHS:
            source = self._drive_root / relative_path
            if not source.exists():
                continue
            target = snapshot_root / relative_path
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        snapshot_metadata = {
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "source_version": source_version or self._get_current_version(),
            "paths": [str(path).replace("\\", "/") for path in ROLLBACK_SNAPSHOT_PATHS],
            "size_bytes": total_size,
        }
        self._write_json(snapshot_root / "snapshot.json", snapshot_metadata)
        logger.info(f"[UpdateAssistant] Created rollback snapshot at {snapshot_root}")
        return snapshot_root

    async def rollback(self, reason: str = "update_apply_failed") -> Dict[str, Any]:
        """Restore critical runtime directories from the latest rollback snapshot."""
        if not self._updates_enabled():
            return self._disabled_result()

        snapshot_root = self._rollback_dir()
        snapshot_path = snapshot_root / "snapshot.json"
        if not snapshot_path.exists():
            logger.critical("[UpdateAssistant] No rollback snapshot found")
            raise FileNotFoundError("Rollback snapshot does not exist")

        metadata = json.loads(snapshot_path.read_text(encoding="utf-8"))
        for relative_path in ROLLBACK_SNAPSHOT_PATHS:
            source = snapshot_root / relative_path
            if not source.exists():
                continue
            destination = self._drive_root / relative_path
            if source.is_dir():
                self._restore_directory(source, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

        rollback_record = {
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        self._write_json(self._record_dir() / "last_rollback.json", rollback_record)
        logger.warning(f"[UpdateAssistant] Rollback completed: {reason}")
        return {"status": "rolled_back", "snapshot_at": metadata.get("snapshot_at"), "reason": reason}

    async def apply_update(
        self,
        bundle_path: Path,
        manifest: Optional[Dict[str, Any]] = None,
        bundle_format: Optional[str] = None,
        version: Optional[str] = None,
        rollback_reason: str = "update_apply_failed",
    ) -> Dict[str, Any]:
        """Apply a downloaded update bundle with automatic rollback protection."""
        if not self._updates_enabled():
            return self._disabled_result()

        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")

        snapshot = await self.create_rollback_snapshot(source_version=self._get_current_version())
        if isinstance(snapshot, dict):
            return snapshot

        archive_format = (bundle_format or bundle_path.suffix.lstrip(".") or "zip").lower()
        if archive_format != "zip":
            raise ValueError(f"Unsupported bundle format: {archive_format}")

        temp_root_base = self._updates_dir / "tmp"
        temp_root_base.mkdir(parents=True, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory(dir=temp_root_base) as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                extracted_root = temp_dir / "payload"
                extracted_root.mkdir(parents=True, exist_ok=True)
                self._safe_extract_zip(bundle_path, extracted_root)

                bundle_manifest = manifest or self._load_manifest_from_directory(extracted_root)
                normalized_files = self._validate_extracted_manifest(extracted_root, bundle_manifest)
                applied_changes: List[str] = []
                skipped_paths: List[str] = []

                for file_info in normalized_files:
                    relative_path = self._normalize_relative_path(file_info["path"])
                    if self._is_protected_path(relative_path):
                        skipped_paths.append(str(relative_path).replace("\\", "/"))
                        continue

                    action = file_info["action"]
                    destination = self._drive_root / relative_path

                    if action == "delete":
                        if destination.is_dir():
                            shutil.rmtree(destination)
                        elif destination.exists():
                            destination.unlink()
                        applied_changes.append(f"Deleted: {relative_path}")
                        continue

                    source_path = extracted_root / relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if source_path.is_dir():
                        if destination.exists() and destination.is_file():
                            destination.unlink()
                        shutil.copytree(source_path, destination, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source_path, destination)
                    applied_changes.append(f"{'Added' if action == 'add' else 'Updated'}: {relative_path}")

                resolved_version = str(version or bundle_manifest.get("version") or self._get_current_version())
                self._write_json(
                    self._record_dir() / "last_update.json",
                    {
                        "version": resolved_version,
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                        "bundle": bundle_path.name,
                    },
                )
                self._update_version(resolved_version, str(bundle_manifest.get("release_notes", "")))
                self._log_update_event(
                    "UPDATE_APPLIED",
                    True,
                    {
                        "version": resolved_version,
                        "bundle": bundle_path.name,
                        "changes_applied": applied_changes,
                        "skipped_paths": skipped_paths,
                    },
                )
                return {
                    "status": "applied",
                    "version": resolved_version,
                    "rolled_back": False,
                    "changes_applied": applied_changes,
                    "skipped_paths": skipped_paths,
                }
        except Exception as exc:
            logger.error(f"[UpdateAssistant] apply_update failed: {exc}")
            try:
                rollback_result = await self.rollback(reason=rollback_reason)
            except Exception as rollback_exc:
                rollback_result = {"status": "failed", "error": str(rollback_exc)}
            self._log_update_event(
                "UPDATE_FAILED",
                False,
                {
                    "bundle": bundle_path.name,
                    "error": str(exc),
                    "rollback": rollback_result,
                },
            )
            return {
                "status": "failed",
                "version": str(version or (manifest.get("version") if manifest else None) or self._get_current_version()),
                "rolled_back": rollback_result.get("status") == "rolled_back",
                "error": str(exc),
            }

    async def handle_update_command(
        self,
        command_payload: Dict[str, Any],
        command_id: Optional[Union[str, int]] = None,
    ) -> Dict[str, Any]:
        """Handle a DOWNLOAD_UPDATE command payload from Fleet Manager."""
        if not self._updates_enabled():
            result = self._disabled_result()
            self._report_command_status(command_id, "FAILED", result)
            return result

        bundle_url = str(
            command_payload.get("bundle_url")
            or command_payload.get("url")
            or command_payload.get("source_url")
            or ""
        ).strip()
        if not bundle_url:
            result = {"status": "failed", "error": "bundle_url is required"}
            self._report_command_status(command_id, "FAILED", result)
            return result

        checksum = (
            command_payload.get("sha256")
            or command_payload.get("checksum")
            or command_payload.get("checksum_sha256")
        )
        version = command_payload.get("version")
        bundle_format = command_payload.get("bundle_format") or command_payload.get("format")
        manifest = command_payload.get("manifest") if isinstance(command_payload.get("manifest"), dict) else None

        self._report_command_status(command_id, "PROCESSING", {"status": "processing", "bundle_url": bundle_url})
        try:
            bundle_path = await self.download_update(
                bundle_url=bundle_url,
                checksum=str(checksum) if checksum else None,
                bundle_name=command_payload.get("bundle_name"),
            )
            if isinstance(bundle_path, dict):
                self._report_command_status(command_id, "FAILED", bundle_path)
                return bundle_path

            result = await self.apply_update(
                bundle_path=bundle_path,
                manifest=manifest,
                bundle_format=bundle_format,
                version=str(version) if version else None,
            )
            status = "COMPLETED" if result.get("status") == "applied" else "FAILED"
            self._report_command_status(command_id, status, result)
            return result
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
            self._report_command_status(command_id, "FAILED", result)
            return result
    
    async def analyze_update(
        self,
        manifest: Dict[str, Any],
        local_state: Optional[Dict[str, Any]] = None
    ) -> UpdateAnalysis:
        """
        AI analyzes an update before applying.
        
        Args:
            manifest: Update manifest (version, files, changes)
            local_state: Current local state (configs, profiles, etc.)
        
        Returns:
            UpdateAnalysis with AI's assessment
        """
        if not self._updates_enabled():
            logger.warning("[UpdateAssistant] Updates disabled - analysis returning safe_to_apply=False")
            return UpdateAnalysis(
                safe_to_apply=False,
                confidence=1.0,
                summary="Updates are disabled on this cabinet.",
                changes=[],
                risks=["AA_UPDATES_ENABLED is not set to 1"],
                conflicts=[],
                recommendations=["Set AA_UPDATES_ENABLED=1 before applying updates."],
                requires_user_approval=True,
                estimated_downtime_seconds=0,
            )

        # Gather local state if not provided
        if local_state is None:
            local_state = await self._gather_local_state()
        
        # Build analysis prompt
        prompt = self._build_analysis_prompt(manifest, local_state)
        
        # Get AI analysis (use Haiku for cost efficiency)
        try:
            analysis = await self._get_ai_analysis(prompt)
            return analysis
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            # Fallback to rule-based analysis
            return self._fallback_analysis(manifest, local_state)
    
    async def _gather_local_state(self) -> Dict[str, Any]:
        """Gather current local state for conflict detection."""
        state = {
            "version": self._get_current_version(),
            "configs_modified": [],
            "custom_profiles": [],
            "pending_data": {},
            "disk_space_mb": self._get_disk_space(),
            "uptime_hours": self._get_uptime(),
        }
        
        # Check for modified configs
        configs_dir = self._drive_root / "configs"
        if configs_dir.exists():
            for cfg in configs_dir.rglob("*.json"):
                # Check if config has local modifications (compare to baseline)
                state["configs_modified"].append(str(cfg.relative_to(self._drive_root)))
        
        # Check for custom user profiles
        profiles_dir = self._state_dir / "voice" / "profiles"
        if profiles_dir.exists():
            state["custom_profiles"] = [p.name for p in profiles_dir.iterdir() if p.is_dir()]
        
        # Check for pending scores/telemetry
        scores_file = self._state_dir / "scorekeeper" / "scores.jsonl"
        if scores_file.exists():
            state["pending_data"]["scores_count"] = sum(1 for _ in open(scores_file))
        
        return state
    
    def _get_current_version(self) -> str:
        """Get current installed version."""
        version_file = self._drive_root / ".aa" / "version.json"
        if version_file.exists():
            try:
                data = json.loads(version_file.read_text())
                return data.get("version", "1.0.0")
            except:
                pass
        return os.getenv("AA_VERSION", "1.0.0")
    
    def _get_disk_space(self) -> int:
        """Get available disk space in MB."""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self._drive_root)
            return free // (1024 * 1024)
        except:
            return -1
    
    def _get_uptime(self) -> float:
        """Get system uptime in hours."""
        try:
            import time
            # On Windows, use ctypes
            if os.name == 'nt':
                import ctypes
                lib = ctypes.windll.kernel32
                tick = lib.GetTickCount64()
                return tick / (1000 * 60 * 60)
        except:
            pass
        return 0
    
    def _build_analysis_prompt(
        self,
        manifest: Dict[str, Any],
        local_state: Dict[str, Any]
    ) -> str:
        """Build prompt for AI analysis."""
        return f"""You are an update assistant for Arcade Assistant arcade cabinets.
Analyze this update and determine if it's safe to apply.

CURRENT STATE:
- Version: {local_state.get('version', 'unknown')}
- Modified configs: {len(local_state.get('configs_modified', []))} files
- Custom profiles: {len(local_state.get('custom_profiles', []))} users
- Pending scores: {local_state.get('pending_data', {}).get('scores_count', 0)}
- Disk space: {local_state.get('disk_space_mb', 'unknown')} MB free
- Uptime: {local_state.get('uptime_hours', 0):.1f} hours

UPDATE MANIFEST:
- New version: {manifest.get('version', 'unknown')}
- Previous version: {manifest.get('previous_version', 'unknown')}
- Files changed: {len(manifest.get('files', []))}
- Release notes: {manifest.get('release_notes', 'None provided')}

FILES TO UPDATE:
{json.dumps(manifest.get('files', [])[:10], indent=2)}

Respond in JSON format:
{{
  "safe_to_apply": true/false,
  "confidence": 0.0-1.0,
  "summary": "Brief human-readable summary",
  "changes": ["change1", "change2"],
  "risks": ["risk1", "risk2"] or [],
  "conflicts": [
    {{"file": "path", "issue": "description", "resolution": "suggestion"}}
  ] or [],
  "recommendations": ["rec1", "rec2"],
  "requires_user_approval": true/false,
  "estimated_downtime_seconds": number
}}"""
    
    async def _get_ai_analysis(self, prompt: str) -> UpdateAnalysis:
        """Get AI analysis using the model router."""
        try:
            from backend.services.model_router import route_request, get_model_router
            
            # Use Haiku for cost efficiency
            model_id, _ = route_request(prompt, panel="updates", intent="action")
            
            # Call Claude API
            from backend.routers.claude_api import call_claude_direct
            
            response = await call_claude_direct(
                prompt=prompt,
                model=model_id,
                max_tokens=1000,
                system="You are an update analysis assistant. Always respond with valid JSON."
            )
            
            # Parse response
            result = json.loads(response)
            
            # Record usage
            router = get_model_router()
            router.record_usage(
                tier=router.classifier.classify(prompt).recommended_tier,
                input_tokens=len(prompt.split()) * 2,
                output_tokens=len(response.split()) * 2,
                panel="updates"
            )
            
            return UpdateAnalysis(
                safe_to_apply=result.get("safe_to_apply", False),
                confidence=result.get("confidence", 0.5),
                summary=result.get("summary", "Analysis complete"),
                changes=result.get("changes", []),
                risks=result.get("risks", []),
                conflicts=result.get("conflicts", []),
                recommendations=result.get("recommendations", []),
                requires_user_approval=result.get("requires_user_approval", True),
                estimated_downtime_seconds=result.get("estimated_downtime_seconds", 60)
            )
            
        except Exception as e:
            logger.warning(f"AI analysis failed, using fallback: {e}")
            raise
    
    def _fallback_analysis(
        self,
        manifest: Dict[str, Any],
        local_state: Dict[str, Any]
    ) -> UpdateAnalysis:
        """Rule-based fallback when AI unavailable."""
        risks = []
        conflicts = []
        safe = True
        
        # Check version compatibility
        current = local_state.get("version", "0.0.0")
        target = manifest.get("version", "0.0.0")
        prev = manifest.get("previous_version", current)
        
        if current != prev:
            risks.append(f"Version mismatch: current {current} != expected {prev}")
            safe = False
        
        # Check disk space
        disk_mb = local_state.get("disk_space_mb", 0)
        if disk_mb < 500:
            risks.append(f"Low disk space: {disk_mb} MB")
            safe = False
        
        # Check for modified configs that might be overwritten
        modified = local_state.get("configs_modified", [])
        update_files = [f.get("path", "") for f in manifest.get("files", [])]
        
        for cfg in modified:
            if cfg in update_files:
                conflicts.append({
                    "file": cfg,
                    "issue": "Local modifications will be overwritten",
                    "resolution": "Backup will be created automatically"
                })
        
        return UpdateAnalysis(
            safe_to_apply=safe and len(conflicts) == 0,
            confidence=0.7 if safe else 0.3,
            summary=f"Update from {current} to {target}" + (" (conflicts detected)" if conflicts else ""),
            changes=[f"Update to version {target}"],
            risks=risks,
            conflicts=conflicts,
            recommendations=["Review conflicts before applying"] if conflicts else [],
            requires_user_approval=len(conflicts) > 0 or not safe,
            estimated_downtime_seconds=30
        )
    
    async def apply_update_with_ai(
        self,
        manifest: Dict[str, Any],
        bundle_path: Path,
        user_approved: bool = False
    ) -> UpdateResult:
        """
        Apply update with AI assistance.
        
        The AI monitors the process and can handle edge cases.
        """
        if not self._updates_enabled():
            return UpdateResult(
                success=False,
                version_before=self._get_current_version(),
                version_after=self._get_current_version(),
                changes_applied=[],
                errors=["AA_UPDATES_ENABLED is not set to 1"],
                rollback_available=False,
                ai_summary="Updates are disabled on this cabinet.",
            )

        version_before = self._get_current_version()
        
        # Step 1: AI analysis
        analysis = await self.analyze_update(manifest)
        
        if not analysis.safe_to_apply and not user_approved:
            return UpdateResult(
                success=False,
                version_before=version_before,
                version_after=version_before,
                changes_applied=[],
                errors=["AI determined update is not safe. User approval required."],
                rollback_available=False,
                ai_summary=analysis.summary
            )
        
        apply_result = await self.apply_update(
            bundle_path=bundle_path,
            manifest=manifest,
            version=str(manifest.get("version") or version_before),
        )
        success = apply_result.get("status") == "applied"
        version_after = str(apply_result.get("version") or version_before)
        errors = [] if success else [str(apply_result.get("error") or "Apply failed")]
        changes_applied = list(apply_result.get("changes_applied") or [])
        ai_summary = await self._generate_completion_summary(
            version_before,
            version_after,
            changes_applied,
            errors,
        )

        return UpdateResult(
            success=success,
            version_before=version_before,
            version_after=version_after,
            changes_applied=changes_applied,
            errors=errors,
            rollback_available=bool(not apply_result.get("rolled_back", False)),
            ai_summary=ai_summary if success else f"{ai_summary} Rolled back={apply_result.get('rolled_back', False)}.",
        )
    
    async def _create_backup(self) -> Path:
        """Create backup before update."""
        snapshot = await self.create_rollback_snapshot(source_version=self._get_current_version())
        if isinstance(snapshot, dict):
            raise RuntimeError(snapshot.get("reason", "Updates disabled"))
        return snapshot
    
    async def _rollback(self, backup_path: Path) -> bool:
        """Rollback to backup."""
        try:
            result = await self.rollback(reason=f"legacy_rollback:{backup_path}")
            return result.get("status") == "rolled_back"
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    async def _should_rollback(
        self,
        errors: List[str],
        changes_applied: List[str]
    ) -> bool:
        """AI decides if rollback is needed."""
        # If more than half the changes failed, rollback
        if len(errors) > len(changes_applied) / 2:
            return True
        
        # If critical errors, rollback
        critical_keywords = ["corrupt", "permission denied", "critical", "fatal"]
        for error in errors:
            if any(kw in error.lower() for kw in critical_keywords):
                return True
        
        return False
    
    def _update_version(self, version: str, release_notes: str) -> None:
        """Update version file."""
        version_file = self._drive_root / ".aa" / "version.json"
        version_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "version": version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "release_notes": release_notes
        }
        
        version_file.write_text(json.dumps(data, indent=2))
    
    async def _generate_completion_summary(
        self,
        version_before: str,
        version_after: str,
        changes: List[str],
        errors: List[str]
    ) -> str:
        """Generate human-readable summary of update."""
        if errors:
            return f"Updated from {version_before} to {version_after} with {len(errors)} issues. {len(changes)} files changed."
        return f"Successfully updated from {version_before} to {version_after}. {len(changes)} files updated."
    
    def _log_update_event(
        self,
        event: str,
        success: bool,
        details: Dict[str, Any]
    ) -> None:
        """Log update event."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "success": success,
            "details": details,
            "device_id": os.getenv("AA_DEVICE_ID", "unknown")
        }
        
        log_file = self._logs_dir / "ai_assisted_updates.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")


# Global instance
_assistant: Optional[UpdateAssistant] = None


def get_update_assistant() -> UpdateAssistant:
    """Get global update assistant instance."""
    global _assistant
    if _assistant is None:
        _assistant = UpdateAssistant()
    return _assistant
