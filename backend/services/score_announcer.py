"""
AI Score Announcer Service
Generates personalized commentary for high scores using Gemini.

@service: score_announcer
@role: AI-powered score commentary generation
@owner: Arcade Assistant / ScoreKeeper Sam
@status: active
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Gateway URL for TTS
GATEWAY_URL = os.getenv('GATEWAY_URL', 'http://127.0.0.1:8787')

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class ScoreAnnouncer:
    """
    Generates AI-powered commentary for high scores.
    
    When a new high score is achieved:
    1. Formats context (game, score, rank, previous scores)
    2. Calls Gemini for witty, personalized commentary
    3. Optionally sends to TTS for Sam to speak
    """
    
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = "gemini-2.0-flash"
        self.gemini_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        
        # Cache recent announcements to avoid repeats
        self._recent_announcements: List[str] = []
        self._max_cache = 10
    
    async def generate_commentary(
        self,
        game_name: str,
        score: int,
        initials: str = "???",
        rank: int = 1,
        previous_scores: Optional[List[Dict[str, Any]]] = None,
        is_new_high_score: bool = True
    ) -> Optional[str]:
        """
        Generate personalized commentary for a score.
        
        Args:
            game_name: Name of the game
            score: The score achieved
            initials: Player initials
            rank: Position on leaderboard (1 = top)
            previous_scores: Other scores for context
            is_new_high_score: Whether this is a new personal/cabinet high
            
        Returns:
            Generated commentary text or None on failure
        """
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available for AI commentary")
            return None
        
        if not self.gemini_api_key:
            logger.debug("No Gemini API key, skipping AI commentary")
            return None
        
        prompt = self._build_prompt(
            game_name, score, initials, rank, 
            previous_scores, is_new_high_score
        )
        
        try:
            request_body = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.9,  # Higher temp for creative commentary
                    "maxOutputTokens": 100
                }
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.gemini_endpoint}?key={self.gemini_api_key}",
                    json=request_body,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                result = response.json()
            
            commentary = self._parse_response(result)
            
            if commentary:
                # Cache to avoid repeats
                self._recent_announcements.append(commentary)
                if len(self._recent_announcements) > self._max_cache:
                    self._recent_announcements.pop(0)
                
                logger.info(f"Generated commentary for {game_name}: {commentary}")
            
            return commentary
            
        except Exception as e:
            logger.error(f"AI commentary generation failed: {e}")
            return None
    
    def _build_prompt(
        self,
        game_name: str,
        score: int,
        initials: str,
        rank: int,
        previous_scores: Optional[List[Dict[str, Any]]],
        is_new_high_score: bool
    ) -> str:
        """Build the Gemini prompt for commentary generation."""
        
        context = f"Game: {game_name}\nPlayer: {initials}\nScore: {score:,}\nRank: #{rank}"
        
        if previous_scores:
            top_score = previous_scores[0].get('score', 0) if previous_scores else 0
            context += f"\nPrevious top score: {top_score:,}"
        
        achievement = "NEW HIGH SCORE!" if is_new_high_score else f"Placed #{rank} on the leaderboard"
        
        prompt = f"""You are ScoreKeeper Sam, an enthusiastic arcade announcer with a Brooklyn accent.
Generate a SHORT, FUN announcement for this achievement (MAX 2 sentences, under 30 words):

{context}
Achievement: {achievement}

Requirements:
- Be excited but BRIEF
- Use arcade lingo ("crushed it", "legendary run", "on fire")
- Reference the game if you know it
- If it's the #1 score, make it extra special
- NO hashtags, NO emojis in the text
- Write as if you're speaking aloud

Recent announcements (DON'T repeat these exactly):
{chr(10).join(self._recent_announcements[-3:]) if self._recent_announcements else 'None yet'}

Your announcement:"""

        return prompt
    
    def _parse_response(self, response: Dict[str, Any]) -> Optional[str]:
        """Parse Gemini's response and extract commentary."""
        try:
            candidates = response.get("candidates", [])
            if not candidates:
                return None
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None
            
            text = parts[0].get("text", "").strip()
            
            # Clean up the text
            text = text.replace('"', '').strip()
            
            # Limit length for TTS
            if len(text) > 200:
                text = text[:197] + "..."
            
            return text if text else None
            
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            return None
    
    async def announce_score(
        self,
        game_name: str,
        score: int,
        initials: str = "???",
        rank: int = 1,
        previous_scores: Optional[List[Dict[str, Any]]] = None,
        speak: bool = True
    ) -> Optional[str]:
        """
        Generate commentary and optionally speak it via Sam TTS.
        
        Returns the generated commentary text.
        """
        commentary = await self.generate_commentary(
            game_name=game_name,
            score=score,
            initials=initials,
            rank=rank,
            previous_scores=previous_scores,
            is_new_high_score=(rank == 1)
        )
        
        if commentary and speak:
            await self._speak_commentary(commentary)
        
        return commentary
    
    async def _speak_commentary(self, text: str) -> None:
        """Send commentary to Sam TTS via Gateway."""
        if not HTTPX_AVAILABLE:
            return
        
        try:
            tts_url = f"{GATEWAY_URL}/api/tts/speak"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    tts_url,
                    json={
                        "text": text,
                        "voice": "sam",
                        "panel": "scorekeeper"
                    }
                )
                
                if response.is_success:
                    logger.info("Commentary sent to TTS")
                else:
                    logger.debug(f"TTS returned {response.status_code}")
                    
        except Exception as e:
            logger.debug(f"TTS request failed (non-critical): {e}")


# Global instance
_score_announcer: Optional[ScoreAnnouncer] = None


def get_score_announcer() -> ScoreAnnouncer:
    """Get or create the global ScoreAnnouncer instance."""
    global _score_announcer
    if _score_announcer is None:
        _score_announcer = ScoreAnnouncer()
    return _score_announcer


async def announce_high_score(
    game_name: str,
    score: int,
    initials: str = "???",
    rank: int = 1,
    previous_scores: Optional[List[Dict[str, Any]]] = None,
    speak: bool = True
) -> Optional[str]:
    """
    Convenience function to generate and announce a high score.
    
    Returns the generated commentary text.
    """
    announcer = get_score_announcer()
    return await announcer.announce_score(
        game_name=game_name,
        score=score,
        initials=initials,
        rank=rank,
        previous_scores=previous_scores,
        speak=speak
    )
