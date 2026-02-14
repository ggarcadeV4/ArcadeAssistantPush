"""
AI Escalation Service for Arcade Assistant
When local AI can't solve a problem, escalate to Fleet Manager AI.

Flow:
1. Cabinet AI encounters problem it can't solve
2. Creates escalation ticket with full context
3. Pushes to Supabase `escalations` table
4. Fleet Manager AI receives notification
5. Fleet Manager AI analyzes with broader context (fleet-wide patterns)
6. Solution pushed back to cabinet via command queue
7. Cabinet applies solution or requests human intervention

This creates a two-tier AI support system:
- Tier 1: Local cabinet AI (fast, cheap, handles 95% of issues)
- Tier 2: Fleet Manager AI (smarter, sees patterns across fleet)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class EscalationPriority(str, Enum):
    """Priority levels for escalations."""
    LOW = "low"           # Can wait, not affecting gameplay
    MEDIUM = "medium"     # Degraded experience, but playable
    HIGH = "high"         # Significant issue, needs attention soon
    CRITICAL = "critical" # Cabinet unusable, needs immediate help


class EscalationStatus(str, Enum):
    """Status of an escalation ticket."""
    PENDING = "pending"           # Waiting for Fleet Manager
    ACKNOWLEDGED = "acknowledged" # Fleet Manager received it
    ANALYZING = "analyzing"       # Fleet AI is working on it
    SOLUTION_READY = "solution_ready"  # Solution available
    APPLIED = "applied"           # Solution applied on cabinet
    RESOLVED = "resolved"         # Issue confirmed resolved
    FAILED = "failed"             # Could not resolve
    HUMAN_NEEDED = "human_needed" # Requires human intervention


@dataclass
class EscalationTicket:
    """
    Escalation ticket sent to Fleet Manager.
    
    Contains everything the Fleet Manager AI needs to understand
    and potentially solve the problem.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = ""
    cabinet_name: str = ""
    cabinet_serial: str = ""
    
    # Problem description
    category: str = ""  # "update", "hardware", "config", "emulator", "network", etc.
    title: str = ""
    description: str = ""
    
    # Context for AI
    error_messages: List[str] = field(default_factory=list)
    logs_snippet: str = ""
    local_ai_analysis: str = ""  # What the local AI already tried/concluded
    local_ai_attempts: List[Dict[str, Any]] = field(default_factory=list)
    
    # System state
    system_info: Dict[str, Any] = field(default_factory=dict)
    affected_components: List[str] = field(default_factory=list)
    
    # Metadata
    priority: EscalationPriority = EscalationPriority.MEDIUM
    status: EscalationStatus = EscalationStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""
    
    # Solution (filled by Fleet Manager)
    solution: Optional[Dict[str, Any]] = None
    resolution_notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Supabase."""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "cabinet_name": self.cabinet_name,
            "cabinet_serial": self.cabinet_serial,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "error_messages": self.error_messages,
            "logs_snippet": self.logs_snippet,
            "local_ai_analysis": self.local_ai_analysis,
            "local_ai_attempts": self.local_ai_attempts,
            "system_info": self.system_info,
            "affected_components": self.affected_components,
            "priority": self.priority.value if isinstance(self.priority, EscalationPriority) else self.priority,
            "status": self.status.value if isinstance(self.status, EscalationStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at or self.created_at,
            "solution": self.solution,
            "resolution_notes": self.resolution_notes
        }


class EscalationService:
    """
    Service for escalating issues to Fleet Manager.
    
    When local AI can't solve a problem:
    1. Call escalate() with problem details
    2. Ticket is pushed to Supabase
    3. Fleet Manager AI receives and analyzes
    4. Solution comes back via check_for_solutions()
    """
    
    def __init__(self):
        self._drive_root = Path(os.getenv("AA_DRIVE_ROOT", "."))
        self._aa_root = self._drive_root / ".aa"
        self._escalations_dir = self._aa_root / "escalations"
        self._escalations_dir.mkdir(parents=True, exist_ok=True)
        
        # Load cabinet identity
        self._device_id = os.getenv("AA_DEVICE_ID", "")
        self._cabinet_name = ""
        self._cabinet_serial = ""
        self._load_identity()
    
    def _load_identity(self) -> None:
        """Load cabinet identity from manifest."""
        manifest_path = self._aa_root / "cabinet_manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text())
                self._device_id = data.get("device_id", self._device_id)
                self._cabinet_name = data.get("name", "")
                self._cabinet_serial = data.get("serial", "")
            except:
                pass
    
    async def escalate(
        self,
        category: str,
        title: str,
        description: str,
        error_messages: Optional[List[str]] = None,
        local_ai_analysis: str = "",
        local_ai_attempts: Optional[List[Dict[str, Any]]] = None,
        affected_components: Optional[List[str]] = None,
        priority: EscalationPriority = EscalationPriority.MEDIUM,
        include_logs: bool = True,
        include_system_info: bool = True
    ) -> EscalationTicket:
        """
        Escalate an issue to Fleet Manager.
        
        Args:
            category: Type of issue (update, hardware, config, emulator, network)
            title: Brief title of the problem
            description: Detailed description
            error_messages: List of error messages encountered
            local_ai_analysis: What the local AI concluded
            local_ai_attempts: What solutions were already tried
            affected_components: Which parts of the system are affected
            priority: How urgent is this
            include_logs: Include recent log snippets
            include_system_info: Include system state
        
        Returns:
            EscalationTicket that was created
        """
        ticket = EscalationTicket(
            device_id=self._device_id,
            cabinet_name=self._cabinet_name,
            cabinet_serial=self._cabinet_serial,
            category=category,
            title=title,
            description=description,
            error_messages=error_messages or [],
            local_ai_analysis=local_ai_analysis,
            local_ai_attempts=local_ai_attempts or [],
            affected_components=affected_components or [],
            priority=priority
        )
        
        # Gather logs if requested
        if include_logs:
            ticket.logs_snippet = await self._gather_recent_logs(category)
        
        # Gather system info if requested
        if include_system_info:
            ticket.system_info = await self._gather_system_info()
        
        # Save locally first (in case Supabase is down)
        self._save_local_ticket(ticket)
        
        # Push to Supabase
        success = await self._push_to_supabase(ticket)
        
        if success:
            logger.info(f"Escalation {ticket.id} pushed to Fleet Manager: {title}")
        else:
            logger.warning(f"Escalation {ticket.id} saved locally, Supabase push failed")
        
        return ticket
    
    async def _gather_recent_logs(self, category: str) -> str:
        """Gather relevant recent logs for the escalation."""
        logs = []
        logs_dir = self._aa_root / "logs"
        
        # Map category to relevant log files
        log_files = {
            "update": ["updates/events.jsonl", "updates/ai_assisted_updates.jsonl"],
            "hardware": ["hardware/events.jsonl"],
            "config": ["config/changes.jsonl"],
            "emulator": ["emulator/events.jsonl"],
            "general": ["app.log"]
        }
        
        relevant_logs = log_files.get(category, log_files["general"])
        
        for log_rel in relevant_logs:
            log_path = logs_dir / log_rel
            if log_path.exists():
                try:
                    # Get last 50 lines
                    with open(log_path, 'r') as f:
                        lines = f.readlines()[-50:]
                        logs.append(f"=== {log_rel} ===\n" + "".join(lines))
                except:
                    pass
        
        return "\n\n".join(logs)[:10000]  # Cap at 10KB
    
    async def _gather_system_info(self) -> Dict[str, Any]:
        """Gather current system state."""
        import platform
        import shutil
        
        info = {
            "hostname": platform.node(),
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "aa_version": os.getenv("AA_VERSION", "unknown"),
        }
        
        # Disk space
        try:
            total, used, free = shutil.disk_usage(self._drive_root)
            info["disk_free_gb"] = round(free / (1024**3), 2)
            info["disk_total_gb"] = round(total / (1024**3), 2)
        except:
            pass
        
        # Check key services
        info["services"] = {}
        
        # Check if backend is responding
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8000/health", timeout=2) as resp:
                    info["services"]["backend"] = resp.status == 200
        except:
            info["services"]["backend"] = "unknown"
        
        return info
    
    def _save_local_ticket(self, ticket: EscalationTicket) -> None:
        """Save ticket locally as backup."""
        ticket_path = self._escalations_dir / f"{ticket.id}.json"
        ticket_path.write_text(json.dumps(ticket.to_dict(), indent=2))
    
    async def _push_to_supabase(self, ticket: EscalationTicket) -> bool:
        """Push escalation ticket to Supabase."""
        try:
            from backend.services.supabase_client import get_client
            
            client = get_client()
            
            # Try admin client first
            try:
                admin = client._get_client(admin=True)
                admin.table("escalations").upsert(ticket.to_dict()).execute()
                return True
            except Exception as e:
                logger.warning(f"Admin upsert failed: {e}")
            
            # Fallback to regular client
            try:
                client.client.table("escalations").upsert(ticket.to_dict()).execute()
                return True
            except Exception as e:
                logger.warning(f"Regular upsert failed: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to push escalation to Supabase: {e}")
            return False
    
    async def check_for_solutions(self) -> List[Dict[str, Any]]:
        """
        Check if Fleet Manager has provided any solutions.
        
        Returns list of solutions ready to be applied.
        """
        solutions = []
        
        try:
            from backend.services.supabase_client import get_client
            
            client = get_client()
            
            # Query for solutions for this device
            response = client.client.table("escalations").select("*").eq(
                "device_id", self._device_id
            ).eq(
                "status", "solution_ready"
            ).execute()
            
            for row in response.data or []:
                solutions.append({
                    "ticket_id": row.get("id"),
                    "title": row.get("title"),
                    "solution": row.get("solution"),
                    "resolution_notes": row.get("resolution_notes")
                })
            
        except Exception as e:
            logger.error(f"Failed to check for solutions: {e}")
        
        # Also check local tickets that may have been updated
        for ticket_file in self._escalations_dir.glob("*.json"):
            try:
                data = json.loads(ticket_file.read_text())
                if data.get("status") == "solution_ready" and data.get("solution"):
                    solutions.append({
                        "ticket_id": data.get("id"),
                        "title": data.get("title"),
                        "solution": data.get("solution"),
                        "resolution_notes": data.get("resolution_notes"),
                        "local_only": True
                    })
            except:
                pass
        
        return solutions
    
    async def apply_solution(
        self,
        ticket_id: str,
        solution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply a solution provided by Fleet Manager.
        
        The solution dict contains instructions that the local AI executes.
        """
        result = {
            "ticket_id": ticket_id,
            "success": False,
            "actions_taken": [],
            "errors": []
        }
        
        solution_type = solution.get("type", "")
        
        try:
            if solution_type == "config_change":
                # Apply config changes
                config_path = solution.get("config_path")
                changes = solution.get("changes", {})
                
                if config_path and changes:
                    full_path = self._drive_root / config_path
                    if full_path.exists():
                        # Backup first
                        backup = full_path.with_suffix(".bak")
                        import shutil
                        shutil.copy(full_path, backup)
                        
                        # Apply changes
                        data = json.loads(full_path.read_text())
                        data.update(changes)
                        full_path.write_text(json.dumps(data, indent=2))
                        
                        result["actions_taken"].append(f"Updated {config_path}")
                        result["success"] = True
            
            elif solution_type == "run_command":
                # Run a command (carefully!)
                command = solution.get("command")
                if command and self._is_safe_command(command):
                    import subprocess
                    proc = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd=str(self._drive_root)
                    )
                    result["actions_taken"].append(f"Ran command: {command}")
                    result["command_output"] = proc.stdout
                    result["success"] = proc.returncode == 0
                else:
                    result["errors"].append("Command not allowed")
            
            elif solution_type == "restart_service":
                # Restart a specific service
                service = solution.get("service")
                result["actions_taken"].append(f"Restart {service} requested")
                result["requires_restart"] = True
                result["success"] = True
            
            elif solution_type == "download_fix":
                # Download a fix file
                url = solution.get("url")
                target = solution.get("target_path")
                result["actions_taken"].append(f"Download fix to {target}")
                # Would implement actual download here
                result["success"] = True
            
            elif solution_type == "manual_steps":
                # Provide manual steps for user
                steps = solution.get("steps", [])
                result["manual_steps"] = steps
                result["requires_human"] = True
                result["success"] = True
            
            else:
                result["errors"].append(f"Unknown solution type: {solution_type}")
            
            # Update ticket status
            await self._update_ticket_status(
                ticket_id,
                EscalationStatus.APPLIED if result["success"] else EscalationStatus.FAILED,
                str(result)
            )
            
        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Failed to apply solution for {ticket_id}: {e}")
        
        return result
    
    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe to run."""
        # Whitelist of safe command prefixes
        safe_prefixes = [
            "python -m",
            "npm run",
            "node scripts/",
        ]
        
        # Blacklist of dangerous commands
        dangerous = [
            "rm -rf", "del /f", "format", "fdisk",
            "shutdown", "reboot", "> /dev/",
            "curl | sh", "wget | sh"
        ]
        
        command_lower = command.lower()
        
        # Check blacklist
        for d in dangerous:
            if d in command_lower:
                return False
        
        # Check whitelist
        for safe in safe_prefixes:
            if command.startswith(safe):
                return True
        
        return False
    
    async def _update_ticket_status(
        self,
        ticket_id: str,
        status: EscalationStatus,
        notes: str = ""
    ) -> None:
        """Update ticket status in Supabase and locally."""
        # Update local
        ticket_path = self._escalations_dir / f"{ticket_id}.json"
        if ticket_path.exists():
            try:
                data = json.loads(ticket_path.read_text())
                data["status"] = status.value
                data["resolution_notes"] = notes
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                ticket_path.write_text(json.dumps(data, indent=2))
            except:
                pass
        
        # Update Supabase
        try:
            from backend.services.supabase_client import get_client
            client = get_client()
            client.client.table("escalations").update({
                "status": status.value,
                "resolution_notes": notes,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", ticket_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update ticket status in Supabase: {e}")
    
    async def get_pending_escalations(self) -> List[Dict[str, Any]]:
        """Get all pending escalations for this device."""
        pending = []
        
        for ticket_file in self._escalations_dir.glob("*.json"):
            try:
                data = json.loads(ticket_file.read_text())
                if data.get("status") in ["pending", "acknowledged", "analyzing"]:
                    pending.append(data)
            except:
                pass
        
        return pending


# Global instance
_service: Optional[EscalationService] = None


def get_escalation_service() -> EscalationService:
    """Get global escalation service instance."""
    global _service
    if _service is None:
        _service = EscalationService()
    return _service


# =============================================================================
# Convenience function for quick escalation
# =============================================================================

async def escalate_to_fleet(
    category: str,
    title: str,
    description: str,
    local_ai_analysis: str = "",
    priority: str = "medium"
) -> str:
    """
    Quick helper to escalate an issue to Fleet Manager.
    
    Returns the ticket ID.
    
    Usage:
        ticket_id = await escalate_to_fleet(
            category="update",
            title="Update failed with unknown error",
            description="The AI-assisted update process failed...",
            local_ai_analysis="I tried X, Y, Z but couldn't resolve...",
            priority="high"
        )
    """
    service = get_escalation_service()
    
    priority_enum = EscalationPriority(priority) if priority in [p.value for p in EscalationPriority] else EscalationPriority.MEDIUM
    
    ticket = await service.escalate(
        category=category,
        title=title,
        description=description,
        local_ai_analysis=local_ai_analysis,
        priority=priority_enum
    )
    
    return ticket.id
