"""
Model Router API
Endpoints for AI model routing, cost tracking, and usage statistics.
"""

from fastapi import APIRouter, Query
from typing import Optional
from pydantic import BaseModel

from backend.services.model_router import (
    get_model_router,
    route_request,
    ModelTier,
    MODEL_CONFIGS,
)

router = APIRouter(prefix="/api/local/ai", tags=["ai-routing"])


class ClassifyRequest(BaseModel):
    """Request to classify a message and get model recommendation."""
    message: str
    panel: Optional[str] = None
    intent: Optional[str] = None  # "chat", "action", "config"


class UsageRecord(BaseModel):
    """Record API usage after a call."""
    tier: str  # "haiku", "sonnet", "opus"
    input_tokens: int
    output_tokens: int
    panel: Optional[str] = None


@router.post("/classify")
async def classify_task(request: ClassifyRequest):
    """
    Classify a task and get the recommended model tier.
    
    Use this before making an AI call to determine which model to use.
    Returns the recommended tier, model ID, and reasoning.
    """
    model_id, classification = route_request(
        message=request.message,
        panel=request.panel,
        intent=request.intent
    )
    
    config = MODEL_CONFIGS[classification.recommended_tier]
    
    return {
        "recommended_model": model_id,
        "tier": classification.recommended_tier.value,
        "confidence": classification.confidence,
        "reasons": classification.reasons,
        "escalation_triggers": classification.escalation_triggers,
        "cost_estimate_cents": classification.cost_estimate_cents,
        "model_info": {
            "max_tokens": config.max_tokens,
            "description": config.description
        }
    }


@router.post("/record-usage")
async def record_usage(request: UsageRecord):
    """
    Record API usage after a call completes.
    
    Call this after each AI request to track costs.
    """
    try:
        tier = ModelTier(request.tier)
    except ValueError:
        return {"error": f"Invalid tier '{request.tier}'. Use: haiku, sonnet, opus"}
    
    router_instance = get_model_router()
    entry = router_instance.record_usage(
        tier=tier,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        panel=request.panel
    )
    
    return {
        "recorded": True,
        "entry": entry
    }


@router.get("/usage")
async def get_usage_stats():
    """
    Get current usage statistics and cost tracking.
    
    Returns daily costs, budget status, and breakdown by tier/panel.
    """
    router_instance = get_model_router()
    return router_instance.get_usage_stats()


@router.get("/estimate")
async def estimate_costs(
    daily_queries: int = Query(100, ge=1, le=10000),
    cabinets: int = Query(1, ge=1, le=100)
):
    """
    Estimate monthly costs for fleet.
    
    Args:
        daily_queries: Expected queries per day per cabinet
        cabinets: Number of cabinets in fleet
    """
    router_instance = get_model_router()
    per_cabinet = router_instance.estimate_monthly_cost(daily_queries)
    
    return {
        "per_cabinet": per_cabinet,
        "fleet_size": cabinets,
        "fleet_monthly_usd": round(per_cabinet["monthly_estimate_usd"] * cabinets, 2),
        "fleet_yearly_usd": round(per_cabinet["monthly_estimate_usd"] * cabinets * 12, 2)
    }


@router.get("/models")
async def list_models():
    """
    List available model tiers and their configurations.
    """
    return {
        "models": [
            {
                "tier": config.tier.value,
                "model_id": config.model_id,
                "max_tokens": config.max_tokens,
                "cost_per_1m_input": config.cost_per_1m_input,
                "cost_per_1m_output": config.cost_per_1m_output,
                "description": config.description
            }
            for config in MODEL_CONFIGS.values()
        ],
        "default": "haiku",
        "note": "Use /classify endpoint to determine which model to use for a task"
    }


@router.get("/budget")
async def get_budget_status():
    """
    Get current budget status and limits.
    """
    router_instance = get_model_router()
    stats = router_instance.get_usage_stats()
    
    budget_pct = (stats["daily_cost_cents"] / stats["daily_budget_cents"]) * 100 if stats["daily_budget_cents"] > 0 else 0
    opus_pct = (stats["opus_today"] / stats["opus_daily_limit"]) * 100 if stats["opus_daily_limit"] > 0 else 0
    
    return {
        "daily_budget_cents": stats["daily_budget_cents"],
        "daily_spent_cents": stats["daily_cost_cents"],
        "daily_remaining_cents": stats["budget_remaining_cents"],
        "budget_used_percent": round(budget_pct, 1),
        "opus_today": stats["opus_today"],
        "opus_limit": stats["opus_daily_limit"],
        "opus_used_percent": round(opus_pct, 1),
        "status": "ok" if budget_pct < 80 else "warning" if budget_pct < 100 else "over_budget"
    }
