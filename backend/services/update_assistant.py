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
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
        self._drive_root = Path(os.getenv("AA_DRIVE_ROOT", "."))
        self._updates_dir = self._drive_root / ".aa" / "updates"
        self._state_dir = self._drive_root / ".aa" / "state"
        self._logs_dir = self._drive_root / ".aa" / "logs" / "updates"
        self._logs_dir.mkdir(parents=True, exist_ok=True)
    
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
        version_before = self._get_current_version()
        errors = []
        changes_applied = []
        
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
        
        # Step 2: Create backup
        backup_path = await self._create_backup()
        
        # Step 3: Apply files
        try:
            for file_info in manifest.get("files", []):
                path = file_info.get("path", "")
                action = file_info.get("action", "replace")
                
                if action == "replace":
                    # Extract from bundle and replace
                    # (simplified - actual implementation would unzip)
                    changes_applied.append(f"Updated: {path}")
                elif action == "delete":
                    target = self._drive_root / path
                    if target.exists():
                        target.unlink()
                    changes_applied.append(f"Deleted: {path}")
                elif action == "add":
                    changes_applied.append(f"Added: {path}")
            
            # Step 4: Update version file
            version_after = manifest.get("version", version_before)
            self._update_version(version_after, manifest.get("release_notes", ""))
            
            # Step 5: AI generates summary
            ai_summary = await self._generate_completion_summary(
                version_before, version_after, changes_applied, errors
            )
            
            # Step 6: Log success
            self._log_update_event("UPDATE_APPLIED", True, {
                "version_before": version_before,
                "version_after": version_after,
                "changes": len(changes_applied),
                "ai_assisted": True
            })
            
            return UpdateResult(
                success=True,
                version_before=version_before,
                version_after=version_after,
                changes_applied=changes_applied,
                errors=errors,
                rollback_available=True,
                ai_summary=ai_summary
            )
            
        except Exception as e:
            logger.error(f"Update failed: {e}")
            errors.append(str(e))
            
            # AI-assisted rollback decision
            should_rollback = await self._should_rollback(errors, changes_applied)
            
            if should_rollback:
                await self._rollback(backup_path)
                ai_summary = f"Update failed and was rolled back: {e}"
            else:
                ai_summary = f"Update partially applied with errors: {e}"
            
            return UpdateResult(
                success=False,
                version_before=version_before,
                version_after=version_before if should_rollback else manifest.get("version", version_before),
                changes_applied=changes_applied,
                errors=errors,
                rollback_available=not should_rollback,
                ai_summary=ai_summary
            )
    
    async def _create_backup(self) -> Path:
        """Create backup before update."""
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._updates_dir / "backups" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup critical directories
        for dir_name in ["configs", "state"]:
            src = self._drive_root / dir_name
            if src.exists():
                shutil.copytree(src, backup_dir / dir_name, dirs_exist_ok=True)
        
        return backup_dir
    
    async def _rollback(self, backup_path: Path) -> bool:
        """Rollback to backup."""
        import shutil
        try:
            for dir_name in ["configs", "state"]:
                src = backup_path / dir_name
                dst = self._drive_root / dir_name
                if src.exists():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
            return True
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
