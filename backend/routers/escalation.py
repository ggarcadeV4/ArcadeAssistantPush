"""
Escalation API Router
Endpoints for the AI escalation system (Cabinet → Fleet Manager).
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import logging

from backend.services.escalation_service import (
    get_escalation_service,
    escalate_to_fleet,
    EscalationPriority,
    EscalationStatus
)

router = APIRouter(prefix="/api/local/escalation", tags=["escalation"])
logger = logging.getLogger(__name__)


class EscalateRequest(BaseModel):
    """Request to escalate an issue to Fleet Manager."""
    category: str = Field(..., description="Category: update, hardware, config, emulator, network")
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10)
    error_messages: Optional[List[str]] = None
    local_ai_analysis: Optional[str] = Field(None, description="What the local AI already tried")
    local_ai_attempts: Optional[List[Dict[str, Any]]] = None
    affected_components: Optional[List[str]] = None
    priority: str = Field("medium", description="low, medium, high, critical")
    include_logs: bool = True
    include_system_info: bool = True


class ApplySolutionRequest(BaseModel):
    """Request to apply a solution from Fleet Manager."""
    ticket_id: str
    solution: Dict[str, Any]


@router.post("/create")
async def create_escalation(request: Request, payload: EscalateRequest):
    """
    Escalate an issue to Fleet Manager.
    
    When the local AI can't solve a problem, this creates an escalation
    ticket that is pushed to Supabase for the Fleet Manager AI to analyze.
    
    The Fleet Manager AI has access to:
    - Fleet-wide patterns (is this happening on other cabinets?)
    - Historical solutions (has this been solved before?)
    - More powerful AI models (can use Opus for complex reasoning)
    """
    service = get_escalation_service()
    
    try:
        priority = EscalationPriority(payload.priority)
    except ValueError:
        priority = EscalationPriority.MEDIUM
    
    ticket = await service.escalate(
        category=payload.category,
        title=payload.title,
        description=payload.description,
        error_messages=payload.error_messages,
        local_ai_analysis=payload.local_ai_analysis or "",
        local_ai_attempts=payload.local_ai_attempts,
        affected_components=payload.affected_components,
        priority=priority,
        include_logs=payload.include_logs,
        include_system_info=payload.include_system_info
    )
    
    return {
        "ok": True,
        "ticket_id": ticket.id,
        "status": ticket.status.value,
        "message": f"Escalation created. Fleet Manager will analyze: {ticket.title}"
    }


@router.get("/pending")
async def get_pending_escalations():
    """
    Get all pending escalations for this cabinet.
    
    Shows issues that are waiting for Fleet Manager response.
    """
    service = get_escalation_service()
    pending = await service.get_pending_escalations()
    
    return {
        "pending_count": len(pending),
        "escalations": pending
    }


@router.get("/solutions")
async def check_for_solutions():
    """
    Check if Fleet Manager has provided any solutions.
    
    Cabinet should poll this periodically to see if solutions are available.
    """
    service = get_escalation_service()
    solutions = await service.check_for_solutions()
    
    return {
        "solutions_available": len(solutions),
        "solutions": solutions
    }


@router.post("/apply")
async def apply_solution(request: Request, payload: ApplySolutionRequest):
    """
    Apply a solution provided by Fleet Manager.
    
    The solution contains instructions that the local system executes.
    Supported solution types:
    - config_change: Update a config file
    - run_command: Run a safe command
    - restart_service: Restart a service
    - download_fix: Download a fix file
    - manual_steps: Provide steps for human
    """
    service = get_escalation_service()
    result = await service.apply_solution(payload.ticket_id, payload.solution)
    
    return {
        "ok": result.get("success", False),
        "result": result
    }


@router.post("/resolve/{ticket_id}")
async def mark_resolved(ticket_id: str, notes: str = ""):
    """
    Mark an escalation as resolved.
    
    Call this after a solution has been successfully applied.
    """
    service = get_escalation_service()
    await service._update_ticket_status(
        ticket_id,
        EscalationStatus.RESOLVED,
        notes or "Marked resolved by cabinet"
    )
    
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "status": "resolved"
    }


@router.get("/status")
async def escalation_status():
    """
    Get escalation system status.
    """
    service = get_escalation_service()
    pending = await service.get_pending_escalations()
    solutions = await service.check_for_solutions()
    
    return {
        "enabled": True,
        "device_id": service._device_id,
        "cabinet_name": service._cabinet_name,
        "pending_escalations": len(pending),
        "solutions_waiting": len(solutions),
        "capabilities": [
            "Escalate issues to Fleet Manager",
            "Receive AI-generated solutions",
            "Apply solutions automatically",
            "Track resolution status"
        ]
    }


# =============================================================================
# Integration point for other services to escalate
# =============================================================================

async def auto_escalate_if_needed(
    category: str,
    error: Exception,
    context: Dict[str, Any],
    local_attempts: List[str]
) -> Optional[str]:
    """
    Helper for other services to auto-escalate when they encounter issues.
    
    Usage (in update_assistant.py, for example):
        if not could_resolve:
            ticket_id = await auto_escalate_if_needed(
                category="update",
                error=the_exception,
                context={"manifest": manifest, "state": local_state},
                local_attempts=["Tried rollback", "Tried safe mode"]
            )
    
    Returns ticket_id if escalated, None if not needed.
    """
    # Determine priority based on error type
    error_str = str(error).lower()
    
    if any(kw in error_str for kw in ["critical", "fatal", "corrupt", "unrecoverable"]):
        priority = "critical"
    elif any(kw in error_str for kw in ["failed", "error", "unable"]):
        priority = "high"
    else:
        priority = "medium"
    
    ticket_id = await escalate_to_fleet(
        category=category,
        title=f"Auto-escalated: {type(error).__name__}",
        description=f"Error: {error}\n\nContext: {context}",
        local_ai_analysis=f"Local AI attempted: {', '.join(local_attempts)}",
        priority=priority
    )
    
    logger.info(f"Auto-escalated issue to Fleet Manager: {ticket_id}")
    return ticket_id
