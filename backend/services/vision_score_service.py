"""
AI Vision Score Service for Arcade Assistant.

Captures screenshots at game exit and uses Gemini Vision to extract scores.
This is the "read" side of the AI Score Injector system.

@service: vision_score_service
@role: AI-powered score extraction from game screenshots
@owner: Arcade Assistant / ScoreKeeper Sam
@status: active
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Screen capture
try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

# HTTP client for Gemini API
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class VisionScoreService:
    """
    AI-powered score extraction using Gemini Vision.
    
    Flow:
    1. Capture screenshot when game exits
    2. Send to Gemini Vision API
    3. Extract score, initials, game info
    4. Save to scores.json for Lua injector
    5. Broadcast to ScoreKeeper Sam
    """
    
    def __init__(
        self,
        scores_dir: Path,
        screenshots_dir: Optional[Path] = None,
        gemini_api_key: Optional[str] = None,
        gateway_url: str = "http://127.0.0.1:8787"
    ):
        self.scores_dir = scores_dir
        self.screenshots_dir = screenshots_dir or scores_dir / "screenshots"
        self.scores_file = scores_dir / "ai_scores.json"
        self.gateway_url = gateway_url
        
        # Gemini API config - check both common env var names
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = "gemini-2.0-flash-exp"  # Fast vision model
        self.gemini_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        
        # Ensure directories exist
        self.scores_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing scores
        self._scores_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._load_scores()
        
        logger.info(f"VisionScoreService initialized, scores at {self.scores_file}")
    
    def _load_scores(self) -> None:
        """Load existing scores from JSON file."""
        if self.scores_file.exists():
            try:
                with open(self.scores_file, 'r', encoding='utf-8') as f:
                    self._scores_cache = json.load(f)
                logger.info(f"Loaded scores for {len(self._scores_cache)} games")
            except Exception as e:
                logger.error(f"Error loading scores: {e}")
                self._scores_cache = {}
        else:
            self._scores_cache = {}
    
    def _save_scores(self) -> None:
        """Save scores to JSON file."""
        try:
            with open(self.scores_file, 'w', encoding='utf-8') as f:
                json.dump(self._scores_cache, f, indent=2)
            logger.info(f"Saved scores for {len(self._scores_cache)} games")
        except Exception as e:
            logger.error(f"Error saving scores: {e}")
    
    def capture_screen(self, game_rom: str) -> Optional[Path]:
        """
        Capture the game window or full screen.
        
        Tries to capture the MAME window specifically first.
        Falls back to full screen capture if window not found.
        
        Args:
            game_rom: ROM name for filename
            
        Returns:
            Path to saved screenshot, or None on failure
        """
        if not MSS_AVAILABLE:
            logger.error("mss library not available for screen capture")
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{game_rom}_{timestamp}.png"
            filepath = self.screenshots_dir / filename
            
            with mss.mss() as sct:
                # Try to capture secondary monitor (usually where fullscreen games run)
                # monitors[0] = all combined, monitors[1] = primary, monitors[2] = secondary
                if len(sct.monitors) > 2:
                    # Use secondary monitor (left display in typical setup)
                    monitor = sct.monitors[2]
                    logger.info(f"Capturing secondary monitor: {monitor}")
                else:
                    # Single monitor - capture everything
                    monitor = sct.monitors[0]
                    logger.info("Single monitor detected, capturing all")
                
                screenshot = sct.grab(monitor)
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
            
            logger.info(f"Captured screenshot: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None
    
    def _find_mame_window(self, game_rom: str) -> Optional[Tuple[int, int, int, int]]:
        """
        Find the MAME window by title patterns.
        
        Returns:
            Window rect (left, top, right, bottom) or None if not found
        """
        try:
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            
            # Window titles to search for (MAME uses game title in window name)
            search_patterns = [
                game_rom.upper(),
                game_rom.lower(),
                "MAME",
                "mame",
            ]
            
            found_hwnd = None
            
            # Callback to enumerate windows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            
            def enum_callback(hwnd, lParam):
                nonlocal found_hwnd
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        title = buffer.value
                        
                        for pattern in search_patterns:
                            if pattern in title:
                                found_hwnd = hwnd
                                return False  # Stop enumeration
                return True  # Continue enumeration
            
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
            
            if found_hwnd:
                rect = wintypes.RECT()
                user32.GetWindowRect(found_hwnd, ctypes.byref(rect))
                logger.info(f"Found MAME window at: {rect.left}, {rect.top}, {rect.right}, {rect.bottom}")
                return (rect.left, rect.top, rect.right, rect.bottom)
            
            return None
            
        except Exception as e:
            logger.warning(f"Window search failed: {e}")
            return None
    
    async def extract_score_from_image(
        self,
        image_path: Path,
        game_rom: str
    ) -> Optional[Dict[str, Any]]:
        """
        Use Gemini Vision to extract score from screenshot.
        
        Args:
            image_path: Path to screenshot
            game_rom: ROM name for context
            
        Returns:
            Extracted score data or None on failure
        """
        if not HTTPX_AVAILABLE:
            logger.error("httpx library not available")
            return None
        
        if not self.gemini_api_key:
            logger.error("GEMINI_API_KEY not set")
            return None
        
        try:
            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Build Gemini Vision request
            prompt = self._build_score_extraction_prompt(game_rom)
            
            request_body = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,  # Low temp for accuracy
                    "maxOutputTokens": 256
                }
            }
            
            # Call Gemini API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.gemini_endpoint}?key={self.gemini_api_key}",
                    json=request_body,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                result = response.json()
            
            # Parse response
            return self._parse_gemini_response(result, game_rom)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Score extraction failed: {e}")
            return None
    
    def _build_score_extraction_prompt(self, game_rom: str) -> str:
        """Build the prompt for score extraction."""
        return f"""You are analyzing an arcade game screenshot from MAME.

Game ROM: {game_rom}

Your task is to extract the player's score from this screenshot.

Look for:
1. The main score display (usually at top or bottom of screen)
2. Player initials if visible (typically 3 characters like "AAA")
3. Whether this appears to be a Game Over screen, High Score entry screen, or active gameplay

Return ONLY a JSON object in this exact format:
{{
  "score": 12500,
  "initials": "AAA",
  "screen_type": "game_over",
  "confidence": 0.95
}}

Rules:
- "score" must be an integer (the numeric score value)
- "initials" should be 3 characters or null if not visible
- "screen_type" must be one of: "game_over", "high_score_entry", "gameplay", "attract_mode", "unknown"
- "confidence" is your confidence level from 0.0 to 1.0

If you cannot determine the score, return:
{{"score": null, "initials": null, "screen_type": "unknown", "confidence": 0.0}}"""
    
    def _parse_gemini_response(
        self,
        response: Dict[str, Any],
        game_rom: str
    ) -> Optional[Dict[str, Any]]:
        """Parse Gemini's response and extract score data."""
        try:
            # Extract text from response
            candidates = response.get("candidates", [])
            if not candidates:
                logger.warning("No candidates in Gemini response")
                return None
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                logger.warning("No parts in Gemini response")
                return None
            
            text = parts[0].get("text", "")
            
            # Try to parse JSON from response
            # Handle markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text.strip())
            
            # Validate and enhance result
            if result.get("score") is not None:
                result["game_rom"] = game_rom
                result["extracted_at"] = datetime.now(timezone.utc).isoformat()
                result["source"] = "gemini_vision"
                logger.info(f"Extracted score for {game_rom}: {result['score']}")
                return result
            else:
                logger.warning(f"No score extracted for {game_rom}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.debug(f"Raw response text: {text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            return None
    
    async def process_game_exit(
        self,
        game_rom: str,
        player_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point: Process a game exit event.
        
        1. Capture screenshot
        2. Extract score via AI
        3. Save to scores database
        4. Return extracted data
        
        Args:
            game_rom: ROM name of the game
            player_name: Optional player name for context
            
        Returns:
            Extracted and saved score data
        """
        logger.info(f"Processing game exit for {game_rom}")
        
        # Step 1: Capture screenshot
        screenshot_path = self.capture_screen(game_rom)
        if not screenshot_path:
            logger.warning("Screenshot capture failed, cannot extract score")
            return None
        
        # Step 2: Extract score via AI
        score_data = await self.extract_score_from_image(screenshot_path, game_rom)
        if not score_data:
            logger.warning("AI score extraction failed")
            return None
        
        # Add player name if provided
        if player_name:
            score_data["player_name"] = player_name
        
        # Step 3: Save to scores database
        await self.save_score(game_rom, score_data)
        
        return score_data
    
    async def save_score(
        self,
        game_rom: str,
        score_data: Dict[str, Any]
    ) -> None:
        """
        Save extracted score to database.
        
        Args:
            game_rom: ROM name
            score_data: Extracted score data
        """
        # Initialize game entry if needed
        if game_rom not in self._scores_cache:
            self._scores_cache[game_rom] = []
        
        # Add to scores list (keep top 10)
        self._scores_cache[game_rom].append(score_data)
        self._scores_cache[game_rom] = sorted(
            self._scores_cache[game_rom],
            key=lambda x: x.get("score", 0) or 0,
            reverse=True
        )[:10]
        
        # Persist to file
        self._save_scores()
        
        # Broadcast to ScoreKeeper Sam
        await self._broadcast_score(game_rom, score_data)
    
    async def _broadcast_score(
        self,
        game_rom: str,
        score_data: Dict[str, Any]
    ) -> None:
        """Broadcast score update to Gateway/ScoreKeeper Sam."""
        if not HTTPX_AVAILABLE:
            return
        
        try:
            broadcast_url = f"{self.gateway_url}/api/scorekeeper/broadcast"
            payload = {
                "type": "ai_score_extracted",
                "game": game_rom,
                "score": score_data.get("score"),
                "initials": score_data.get("initials"),
                "confidence": score_data.get("confidence"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(broadcast_url, json=payload)
                if response.is_success:
                    logger.info(f"Broadcast score for {game_rom}")
                else:
                    logger.debug(f"Broadcast returned {response.status_code}")
                    
        except Exception as e:
            logger.debug(f"Score broadcast failed (non-critical): {e}")
    
    def get_high_scores(self, game_rom: str) -> List[Dict[str, Any]]:
        """Get stored high scores for a game."""
        return self._scores_cache.get(game_rom, [])
    
    def get_top_score(self, game_rom: str) -> Optional[Dict[str, Any]]:
        """Get the top score for a game."""
        scores = self.get_high_scores(game_rom)
        return scores[0] if scores else None


# Global instance
_vision_score_service: Optional[VisionScoreService] = None


def get_vision_score_service() -> Optional[VisionScoreService]:
    """Get the global VisionScoreService instance."""
    return _vision_score_service


async def initialize_vision_score_service(
    scores_dir: Path,
    screenshots_dir: Optional[Path] = None,
    gemini_api_key: Optional[str] = None
) -> VisionScoreService:
    """Initialize the global VisionScoreService."""
    global _vision_score_service
    
    _vision_score_service = VisionScoreService(
        scores_dir=scores_dir,
        screenshots_dir=screenshots_dir,
        gemini_api_key=gemini_api_key
    )
    
    return _vision_score_service
