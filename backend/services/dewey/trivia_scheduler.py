"""
Trivia Auto-Update Scheduler for Dewey
Automatically generates fresh trivia from gaming news on a schedule.
Runs as a background task when the backend starts.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_GENERATION_INTERVAL_HOURS = 24  # Generate new trivia daily
DEFAULT_QUESTIONS_PER_RUN = 10
SCHEDULER_STATE_PATH = Path(os.getenv("AA_DRIVE_ROOT", ".")) / "state" / "dewey" / "scheduler_state.json"


class TriviaScheduler:
    """
    Background scheduler that auto-generates trivia from news headlines.
    
    Runs daily (configurable) and keeps the trivia pool fresh without
    any manual intervention. Perfect for fleet deployments.
    """
    
    def __init__(
        self,
        interval_hours: int = DEFAULT_GENERATION_INTERVAL_HOURS,
        questions_per_run: int = DEFAULT_QUESTIONS_PER_RUN,
        enabled: bool = True
    ):
        self.interval_hours = interval_hours
        self.questions_per_run = questions_per_run
        self.enabled = enabled
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._run_count = 0
        self._total_generated = 0
        
        # Load previous state
        self._load_state()
    
    def _load_state(self) -> None:
        """Load scheduler state from disk."""
        import json
        
        SCHEDULER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        if SCHEDULER_STATE_PATH.exists():
            try:
                with open(SCHEDULER_STATE_PATH, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    if state.get("last_run"):
                        self._last_run = datetime.fromisoformat(state["last_run"])
                    self._run_count = state.get("run_count", 0)
                    self._total_generated = state.get("total_generated", 0)
                    logger.info(f"[TriviaScheduler] Loaded state: {self._run_count} runs, {self._total_generated} total generated")
            except Exception as e:
                logger.warning(f"[TriviaScheduler] Failed to load state: {e}")
    
    def _save_state(self) -> None:
        """Save scheduler state to disk."""
        import json
        
        SCHEDULER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "run_count": self._run_count,
            "total_generated": self._total_generated,
            "interval_hours": self.interval_hours,
            "questions_per_run": self.questions_per_run,
            "enabled": self.enabled
        }
        
        try:
            with open(SCHEDULER_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"[TriviaScheduler] Failed to save state: {e}")
    
    def _should_run_now(self) -> bool:
        """Check if we should run generation now."""
        if not self._last_run:
            return True
        
        elapsed = datetime.now(timezone.utc) - self._last_run
        return elapsed >= timedelta(hours=self.interval_hours)
    
    async def _generate_trivia(self) -> Dict[str, Any]:
        """Run trivia generation from news headlines."""
        try:
            from backend.routers.gaming_news import fetch_all_headlines
            from backend.services.dewey.trivia_generator import (
                generate_trivia_from_headline,
                generate_trivia_with_ai,
                add_generated_questions,
                get_generation_stats,
            )
            
            logger.info("[TriviaScheduler] Starting trivia generation...")
            
            # Fetch headlines
            headlines = await fetch_all_headlines()
            
            if not headlines:
                return {
                    "success": False,
                    "error": "No headlines available",
                    "generated": 0
                }
            
            # Try AI generation first
            generated = []
            try:
                generated = await generate_trivia_with_ai(headlines[:15])
                method = "ai"
            except Exception as e:
                logger.warning(f"[TriviaScheduler] AI generation failed: {e}")
                method = "pattern"
            
            # Fall back to pattern-based if AI didn't work
            if not generated:
                for h in headlines[:self.questions_per_run * 3]:
                    q = generate_trivia_from_headline(
                        h.get('title', ''),
                        h.get('summary', ''),
                        h.get('source', 'Unknown'),
                        h.get('categories', [])
                    )
                    if q:
                        generated.append(q)
                    if len(generated) >= self.questions_per_run:
                        break
                method = "pattern"
            
            # Add to pool
            added = add_generated_questions(generated)
            stats = get_generation_stats()
            
            result = {
                "success": True,
                "method": method,
                "generated": len(generated),
                "added_to_pool": added,
                "pool_size": stats["total_questions"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"[TriviaScheduler] Generated {len(generated)} questions ({added} new), pool size: {stats['total_questions']}")
            
            return result
            
        except Exception as e:
            logger.error(f"[TriviaScheduler] Generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "generated": 0
            }
    
    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        logger.info(f"[TriviaScheduler] Started (interval: {self.interval_hours}h, questions: {self.questions_per_run})")
        
        while self._running:
            try:
                if self._should_run_now():
                    logger.info("[TriviaScheduler] Running scheduled generation...")
                    
                    result = await self._generate_trivia()
                    
                    self._last_run = datetime.now(timezone.utc)
                    self._last_result = result
                    self._run_count += 1
                    
                    if result.get("success"):
                        self._total_generated += result.get("generated", 0)
                    
                    self._save_state()
                    
                    # Optionally sync to Supabase for fleet
                    if result.get("success") and os.getenv("SUPABASE_URL"):
                        await self._sync_to_fleet(result)
                
                # Sleep for 1 hour, then check again
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                logger.info("[TriviaScheduler] Cancelled")
                break
            except Exception as e:
                logger.error(f"[TriviaScheduler] Loop error: {e}", exc_info=True)
                await asyncio.sleep(3600)  # Wait before retrying
    
    async def _sync_to_fleet(self, result: Dict[str, Any]) -> None:
        """Sync generated trivia to Supabase for fleet distribution."""
        try:
            from backend.services.supabase_client import get_client
            
            client = get_client()
            
            # Log trivia generation event for fleet tracking
            client.send_telemetry(
                device_id=os.getenv("AA_DEVICE_ID", "unknown"),
                level="INFO",
                code="TRIVIA_GENERATED",
                message=f"Auto-generated {result.get('generated', 0)} trivia questions",
                metadata={
                    "method": result.get("method"),
                    "added": result.get("added_to_pool"),
                    "pool_size": result.get("pool_size")
                }
            )
            
            logger.info("[TriviaScheduler] Synced generation event to fleet")
            
        except Exception as e:
            logger.warning(f"[TriviaScheduler] Fleet sync failed: {e}")
    
    def start(self) -> None:
        """Start the scheduler background task."""
        if not self.enabled:
            logger.info("[TriviaScheduler] Disabled, not starting")
            return
        
        if self._running:
            logger.warning("[TriviaScheduler] Already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[TriviaScheduler] Background task started")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[TriviaScheduler] Stopped")
    
    async def run_now(self) -> Dict[str, Any]:
        """Manually trigger generation immediately."""
        logger.info("[TriviaScheduler] Manual generation triggered")
        
        result = await self._generate_trivia()
        
        self._last_run = datetime.now(timezone.utc)
        self._last_result = result
        self._run_count += 1
        
        if result.get("success"):
            self._total_generated += result.get("generated", 0)
        
        self._save_state()
        
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        next_run = None
        if self._last_run:
            next_run = (self._last_run + timedelta(hours=self.interval_hours)).isoformat()
        
        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_hours": self.interval_hours,
            "questions_per_run": self.questions_per_run,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": next_run,
            "run_count": self._run_count,
            "total_generated": self._total_generated,
            "last_result": self._last_result
        }
    
    def configure(
        self,
        interval_hours: Optional[int] = None,
        questions_per_run: Optional[int] = None,
        enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update scheduler configuration."""
        if interval_hours is not None:
            self.interval_hours = max(1, interval_hours)
        if questions_per_run is not None:
            self.questions_per_run = max(1, min(50, questions_per_run))
        if enabled is not None:
            self.enabled = enabled
            if enabled and not self._running:
                self.start()
            elif not enabled and self._running:
                self.stop()
        
        self._save_state()
        
        return self.get_status()


# Global scheduler instance
_scheduler: Optional[TriviaScheduler] = None


def get_trivia_scheduler() -> TriviaScheduler:
    """Get the global trivia scheduler instance."""
    global _scheduler
    if _scheduler is None:
        # Check if auto-trivia is enabled (default: True)
        enabled = os.getenv("AA_AUTO_TRIVIA", "1").lower() in ("1", "true", "yes", "on")
        interval = int(os.getenv("AA_TRIVIA_INTERVAL_HOURS", "24"))
        questions = int(os.getenv("AA_TRIVIA_QUESTIONS_PER_RUN", "10"))
        
        _scheduler = TriviaScheduler(
            interval_hours=interval,
            questions_per_run=questions,
            enabled=enabled
        )
    return _scheduler


def start_trivia_scheduler() -> None:
    """Start the trivia scheduler (call from app startup)."""
    scheduler = get_trivia_scheduler()
    scheduler.start()


def stop_trivia_scheduler() -> None:
    """Stop the trivia scheduler (call from app shutdown)."""
    if _scheduler:
        _scheduler.stop()
