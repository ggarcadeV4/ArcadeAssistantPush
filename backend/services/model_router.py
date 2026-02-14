"""
Smart Model Router for Arcade Assistant
Intelligently routes AI requests to the appropriate model tier based on task complexity.

Cost Management Strategy:
- Haiku 3.5 (default): Chat, recommendations, simple queries (~$0.25/1M tokens)
- Sonnet 3.5: Config changes, troubleshooting, complex reasoning (~$3/1M tokens)
- Opus (rare): Multi-step repairs, critical system changes (~$15/1M tokens)

At 20 cabinets with ~100 queries/day each = 2000 queries/day
- 95% Haiku = 1900 queries → ~$0.50/day
- 4% Sonnet = 80 queries → ~$0.25/day
- 1% Opus = 20 queries → ~$0.30/day
- Total: ~$1/day for fleet, ~$30/month

This router ensures we only escalate when truly needed.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Available model tiers, ordered by capability and cost."""
    HAIKU = "haiku"       # Fast, cheap, good for 90%+ of tasks
    SONNET = "sonnet"     # Balanced, for config/troubleshooting
    OPUS = "opus"         # Heavy lifting, critical operations only


@dataclass
class ModelConfig:
    """Configuration for a model tier."""
    tier: ModelTier
    model_id: str
    max_tokens: int
    cost_per_1m_input: float
    cost_per_1m_output: float
    description: str


# Model configurations (Anthropic pricing as of late 2024)
MODEL_CONFIGS: Dict[ModelTier, ModelConfig] = {
    ModelTier.HAIKU: ModelConfig(
        tier=ModelTier.HAIKU,
        model_id="claude-3-5-haiku-20241022",
        max_tokens=4096,
        cost_per_1m_input=0.25,
        cost_per_1m_output=1.25,
        description="Fast responses for chat, recommendations, simple queries"
    ),
    ModelTier.SONNET: ModelConfig(
        tier=ModelTier.SONNET,
        model_id="claude-3-5-sonnet-20241022",
        max_tokens=8192,
        cost_per_1m_input=3.00,
        cost_per_1m_output=15.00,
        description="Config changes, troubleshooting, complex reasoning"
    ),
    ModelTier.OPUS: ModelConfig(
        tier=ModelTier.OPUS,
        model_id="claude-3-opus-20240229",
        max_tokens=4096,
        cost_per_1m_input=15.00,
        cost_per_1m_output=75.00,
        description="Critical repairs, multi-step system changes"
    ),
}


@dataclass
class TaskClassification:
    """Result of classifying a task's complexity."""
    recommended_tier: ModelTier
    confidence: float  # 0-1
    reasons: List[str] = field(default_factory=list)
    escalation_triggers: List[str] = field(default_factory=list)
    cost_estimate_cents: float = 0.0


class TaskComplexityClassifier:
    """
    Classifies task complexity to determine appropriate model tier.
    
    Uses pattern matching and keyword analysis to avoid needing
    an AI call just to decide which AI to use.
    """
    
    # Keywords that suggest simple tasks (Haiku-appropriate)
    SIMPLE_KEYWORDS = {
        # General chat
        "hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye",
        "what is", "who is", "tell me about", "explain",
        # Simple queries
        "recommend", "suggestion", "what game", "which game", "play",
        "favorite", "popular", "best", "top", "random",
        # Status checks
        "status", "how many", "list", "show me", "display",
        # Trivia/fun
        "trivia", "quiz", "fun fact", "joke",
    }
    
    # Keywords that suggest medium complexity (Sonnet-appropriate)
    MEDIUM_KEYWORDS = {
        # Configuration
        "configure", "config", "setting", "settings", "change",
        "update", "modify", "edit", "adjust", "customize",
        # Troubleshooting
        "not working", "broken", "fix", "repair", "issue", "problem",
        "error", "wrong", "help me", "troubleshoot", "diagnose",
        # Mapping/profiles
        "remap", "mapping", "profile", "calibrate", "calibration",
        "controller", "button", "sensitivity",
        # Technical
        "emulator", "retroarch", "mame", "teknoparrot",
    }
    
    # Keywords that suggest high complexity (Opus-appropriate)
    HIGH_KEYWORDS = {
        # Multi-step operations
        "restore", "rollback", "backup", "migrate", "upgrade",
        "reinstall", "reset everything", "factory reset",
        # Critical changes
        "delete", "remove all", "wipe", "format",
        # Complex reasoning
        "why doesn't", "debug", "trace", "analyze logs",
        "compare configurations", "optimize",
        # Multi-system
        "all emulators", "every game", "entire library",
        "synchronize", "sync all",
    }
    
    # Panel-specific complexity overrides
    PANEL_COMPLEXITY = {
        # These panels deal with hardware/config - default to Sonnet for actions
        "controller_chuck": {"default": ModelTier.HAIKU, "action": ModelTier.SONNET},
        "gunner": {"default": ModelTier.HAIKU, "action": ModelTier.SONNET},
        "console_wizard": {"default": ModelTier.HAIKU, "action": ModelTier.SONNET},
        "led_blinky": {"default": ModelTier.HAIKU, "action": ModelTier.SONNET},
        
        # These panels are mostly chat/info - Haiku is fine
        "dewey": {"default": ModelTier.HAIKU, "action": ModelTier.HAIKU},
        "scorekeeper_sam": {"default": ModelTier.HAIKU, "action": ModelTier.HAIKU},
        "launchbox_lora": {"default": ModelTier.HAIKU, "action": ModelTier.HAIKU},
        "vicky_voice": {"default": ModelTier.HAIKU, "action": ModelTier.HAIKU},
        
        # Doc deals with diagnostics - may need Sonnet for complex issues
        "doc": {"default": ModelTier.HAIKU, "action": ModelTier.SONNET},
    }
    
    def classify(
        self,
        message: str,
        panel: Optional[str] = None,
        intent: Optional[str] = None,  # "chat", "action", "config"
        context: Optional[Dict[str, Any]] = None
    ) -> TaskClassification:
        """
        Classify a task and recommend a model tier.
        
        Args:
            message: The user's message/query
            panel: Which panel is making the request
            intent: Detected intent (chat, action, config)
            context: Additional context (conversation history length, etc.)
        
        Returns:
            TaskClassification with recommended tier and reasoning
        """
        message_lower = message.lower()
        reasons = []
        triggers = []
        
        # Start with Haiku as default
        tier = ModelTier.HAIKU
        confidence = 0.8
        
        # Check for high-complexity keywords first
        high_matches = [kw for kw in self.HIGH_KEYWORDS if kw in message_lower]
        if high_matches:
            tier = ModelTier.OPUS
            confidence = 0.9
            triggers.extend(high_matches)
            reasons.append(f"High-complexity keywords detected: {high_matches[:3]}")
        
        # Check for medium-complexity keywords
        elif any(kw in message_lower for kw in self.MEDIUM_KEYWORDS):
            medium_matches = [kw for kw in self.MEDIUM_KEYWORDS if kw in message_lower]
            tier = ModelTier.SONNET
            confidence = 0.85
            triggers.extend(medium_matches)
            reasons.append(f"Config/troubleshooting keywords: {medium_matches[:3]}")
        
        # Check for simple keywords (can override to Haiku)
        elif any(kw in message_lower for kw in self.SIMPLE_KEYWORDS):
            tier = ModelTier.HAIKU
            confidence = 0.95
            reasons.append("Simple query pattern detected")
        
        # Panel-specific overrides
        if panel and panel in self.PANEL_COMPLEXITY:
            panel_config = self.PANEL_COMPLEXITY[panel]
            intent_key = intent or "default"
            if intent_key in panel_config:
                panel_tier = panel_config[intent_key]
                # Only escalate, never downgrade from keyword detection
                if panel_tier.value > tier.value:
                    tier = panel_tier
                    reasons.append(f"Panel '{panel}' requires {tier.value} for {intent_key}")
        
        # Message length heuristic - longer messages might need more reasoning
        if len(message) > 500:
            if tier == ModelTier.HAIKU:
                tier = ModelTier.SONNET
                reasons.append("Long message may need deeper analysis")
        
        # Question complexity - multiple questions or conditional logic
        question_count = message_lower.count("?")
        if question_count > 2:
            if tier == ModelTier.HAIKU:
                tier = ModelTier.SONNET
                reasons.append(f"Multiple questions ({question_count}) detected")
        
        # Code/config detection
        if re.search(r'```|{.*}|\[.*\]', message):
            if tier == ModelTier.HAIKU:
                tier = ModelTier.SONNET
                reasons.append("Code or config block detected")
        
        # Cost estimation (rough, based on average token counts)
        avg_input_tokens = len(message.split()) * 1.5  # Rough estimate
        avg_output_tokens = 200  # Typical response
        config = MODEL_CONFIGS[tier]
        cost = (
            (avg_input_tokens / 1_000_000) * config.cost_per_1m_input +
            (avg_output_tokens / 1_000_000) * config.cost_per_1m_output
        ) * 100  # Convert to cents
        
        return TaskClassification(
            recommended_tier=tier,
            confidence=confidence,
            reasons=reasons or ["Default classification"],
            escalation_triggers=triggers,
            cost_estimate_cents=round(cost, 4)
        )


class ModelRouter:
    """
    Main router that panels use to get the appropriate AI client.
    
    Usage:
        router = get_model_router()
        classification = router.classify_task(message, panel="gunner")
        model_id = router.get_model_id(classification.recommended_tier)
        # Use model_id in your AI call
    """
    
    def __init__(self):
        self.classifier = TaskComplexityClassifier()
        self._usage_log: List[Dict[str, Any]] = []
        self._daily_cost_cents = 0.0
        self._cost_reset_date = datetime.now(timezone.utc).date()
        
        # Budget limits (configurable via env)
        self.daily_budget_cents = float(os.getenv("AA_AI_DAILY_BUDGET_CENTS", "100"))
        self.opus_daily_limit = int(os.getenv("AA_OPUS_DAILY_LIMIT", "50"))
        self._opus_today = 0
    
    def _check_reset_daily(self) -> None:
        """Reset daily counters if new day."""
        today = datetime.now(timezone.utc).date()
        if today != self._cost_reset_date:
            logger.info(f"Resetting daily AI cost tracking. Yesterday: ${self._daily_cost_cents/100:.2f}")
            self._daily_cost_cents = 0.0
            self._opus_today = 0
            self._cost_reset_date = today
    
    def classify_task(
        self,
        message: str,
        panel: Optional[str] = None,
        intent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskClassification:
        """
        Classify a task and get model recommendation.
        
        This is the main entry point for panels.
        """
        self._check_reset_daily()
        
        classification = self.classifier.classify(message, panel, intent, context)
        
        # Budget enforcement - downgrade if over budget
        if self._daily_cost_cents >= self.daily_budget_cents:
            if classification.recommended_tier != ModelTier.HAIKU:
                logger.warning("Daily budget exceeded, forcing Haiku")
                classification.recommended_tier = ModelTier.HAIKU
                classification.reasons.append("BUDGET: Daily limit reached, using Haiku")
        
        # Opus limit enforcement
        if classification.recommended_tier == ModelTier.OPUS:
            if self._opus_today >= self.opus_daily_limit:
                logger.warning("Daily Opus limit reached, downgrading to Sonnet")
                classification.recommended_tier = ModelTier.SONNET
                classification.reasons.append("LIMIT: Daily Opus limit reached")
        
        return classification
    
    def get_model_id(self, tier: ModelTier) -> str:
        """Get the model ID string for a tier."""
        return MODEL_CONFIGS[tier].model_id
    
    def get_model_config(self, tier: ModelTier) -> ModelConfig:
        """Get full config for a tier."""
        return MODEL_CONFIGS[tier]
    
    def record_usage(
        self,
        tier: ModelTier,
        input_tokens: int,
        output_tokens: int,
        panel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record API usage for cost tracking.
        
        Call this after each AI request completes.
        """
        self._check_reset_daily()
        
        config = MODEL_CONFIGS[tier]
        cost_cents = (
            (input_tokens / 1_000_000) * config.cost_per_1m_input +
            (output_tokens / 1_000_000) * config.cost_per_1m_output
        ) * 100
        
        self._daily_cost_cents += cost_cents
        
        if tier == ModelTier.OPUS:
            self._opus_today += 1
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tier": tier.value,
            "model": config.model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": round(cost_cents, 4),
            "panel": panel,
            "daily_total_cents": round(self._daily_cost_cents, 2)
        }
        
        self._usage_log.append(entry)
        
        # Keep last 1000 entries in memory
        if len(self._usage_log) > 1000:
            self._usage_log = self._usage_log[-1000:]
        
        return entry
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        self._check_reset_daily()
        
        return {
            "daily_cost_cents": round(self._daily_cost_cents, 2),
            "daily_budget_cents": self.daily_budget_cents,
            "budget_remaining_cents": round(self.daily_budget_cents - self._daily_cost_cents, 2),
            "opus_today": self._opus_today,
            "opus_daily_limit": self.opus_daily_limit,
            "recent_requests": len(self._usage_log),
            "cost_by_tier": self._get_cost_by_tier(),
            "requests_by_panel": self._get_requests_by_panel()
        }
    
    def _get_cost_by_tier(self) -> Dict[str, float]:
        """Get cost breakdown by tier for today."""
        costs = {tier.value: 0.0 for tier in ModelTier}
        today = datetime.now(timezone.utc).date().isoformat()
        
        for entry in self._usage_log:
            if entry["timestamp"].startswith(today):
                costs[entry["tier"]] += entry["cost_cents"]
        
        return {k: round(v, 2) for k, v in costs.items()}
    
    def _get_requests_by_panel(self) -> Dict[str, int]:
        """Get request count by panel for today."""
        counts: Dict[str, int] = {}
        today = datetime.now(timezone.utc).date().isoformat()
        
        for entry in self._usage_log:
            if entry["timestamp"].startswith(today):
                panel = entry.get("panel") or "unknown"
                counts[panel] = counts.get(panel, 0) + 1
        
        return counts
    
    def estimate_monthly_cost(self, daily_queries: int = 100) -> Dict[str, Any]:
        """
        Estimate monthly costs based on typical usage patterns.
        
        Args:
            daily_queries: Expected queries per day per cabinet
        """
        # Assume typical distribution
        haiku_pct = 0.90
        sonnet_pct = 0.08
        opus_pct = 0.02
        
        # Assume average tokens per query
        avg_input = 150
        avg_output = 300
        
        haiku_cost = daily_queries * haiku_pct * 30 * (
            (avg_input / 1_000_000) * MODEL_CONFIGS[ModelTier.HAIKU].cost_per_1m_input +
            (avg_output / 1_000_000) * MODEL_CONFIGS[ModelTier.HAIKU].cost_per_1m_output
        )
        
        sonnet_cost = daily_queries * sonnet_pct * 30 * (
            (avg_input / 1_000_000) * MODEL_CONFIGS[ModelTier.SONNET].cost_per_1m_input +
            (avg_output / 1_000_000) * MODEL_CONFIGS[ModelTier.SONNET].cost_per_1m_output
        )
        
        opus_cost = daily_queries * opus_pct * 30 * (
            (avg_input / 1_000_000) * MODEL_CONFIGS[ModelTier.OPUS].cost_per_1m_input +
            (avg_output / 1_000_000) * MODEL_CONFIGS[ModelTier.OPUS].cost_per_1m_output
        )
        
        return {
            "daily_queries": daily_queries,
            "monthly_estimate_usd": round(haiku_cost + sonnet_cost + opus_cost, 2),
            "breakdown": {
                "haiku": round(haiku_cost, 2),
                "sonnet": round(sonnet_cost, 2),
                "opus": round(opus_cost, 2)
            },
            "distribution": {
                "haiku": f"{haiku_pct*100:.0f}%",
                "sonnet": f"{sonnet_pct*100:.0f}%",
                "opus": f"{opus_pct*100:.0f}%"
            }
        }


# Global router instance
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get the global model router instance."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


# Convenience function for panels
def route_request(
    message: str,
    panel: Optional[str] = None,
    intent: Optional[str] = None
) -> Tuple[str, TaskClassification]:
    """
    Quick helper to get model ID for a request.
    
    Returns:
        Tuple of (model_id, classification)
    
    Usage:
        model_id, classification = route_request("fix my controller", panel="controller_chuck")
    """
    router = get_model_router()
    classification = router.classify_task(message, panel, intent)
    model_id = router.get_model_id(classification.recommended_tier)
    return model_id, classification
