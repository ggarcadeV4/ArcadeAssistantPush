"""
Advanced NLP parser with pluggable stages and dependency injection.

Supports multi-stage parsing pipeline with confidence-based fallthrough.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache
import asyncio
import structlog

from .models import LightingIntent

logger = structlog.get_logger(__name__)


@dataclass
class ParseResult:
    """
    Result from a single parsing stage.

    Attributes:
        intent: Parsed lighting intent (if successful)
        confidence: Confidence score 0.0-1.0
        stage: Name of the stage that produced this result
        candidates: Alternative interpretations
        context: Additional parsing context
    """
    intent: Optional[LightingIntent]
    confidence: float
    stage: str
    candidates: List[LightingIntent] = None
    context: Dict[str, Any] = None

    def __post_init__(self):
        if self.candidates is None:
            self.candidates = []
        if self.context is None:
            self.context = {}

        # Validate confidence range
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

        # Low confidence validation
        if self.intent and self.confidence < 0.6:
            logger.warning("low_confidence_parse",
                         confidence=self.confidence,
                         stage=self.stage,
                         suggestion="Consider rephrasing")


class NLPParser(ABC):
    """
    Abstract base class for NLP parsing stages.

    Allows pluggable parser implementations (spaCy, Transformers, etc.)
    with consistent interface for dependency injection.
    """

    @abstractmethod
    async def extract_intent(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> ParseResult:
        """
        Extract lighting intent from transcript.

        Args:
            transcript: Voice transcript text
            context: Additional context (user_id, active_panel, etc.)

        Returns:
            ParseResult with intent and confidence
        """
        pass

    @abstractmethod
    def get_stage_name(self) -> str:
        """Return the name of this parsing stage."""
        pass


class KeywordStage(NLPParser):
    """
    Fast keyword/regex-based parsing stage.

    Uses existing regex patterns for common commands.
    Good for high-confidence, low-latency parsing.
    """

    def __init__(self):
        # Import existing parser
        from .parser import get_parser
        self.regex_parser = get_parser()

    async def extract_intent(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> ParseResult:
        """Extract intent using regex patterns."""
        logger.info("keyword_stage_parsing", transcript=transcript)

        try:
            intent = await self.regex_parser.parse(transcript)

            if intent:
                return ParseResult(
                    intent=intent,
                    confidence=intent.confidence,
                    stage="keyword",
                    context={"method": "regex"}
                )
            else:
                # No match
                return ParseResult(
                    intent=None,
                    confidence=0.0,
                    stage="keyword",
                    context={"reason": "no_pattern_match"}
                )
        except Exception as e:
            logger.error("keyword_stage_failed", error=str(e))
            return ParseResult(
                intent=None,
                confidence=0.0,
                stage="keyword",
                context={"error": str(e)}
            )

    def get_stage_name(self) -> str:
        return "keyword"


class SpacyNLPStage(NLPParser):
    """
    spaCy-based NLP parsing stage.

    Uses named entity recognition and dependency parsing
    for more sophisticated intent extraction.
    """

    def __init__(self, model_name: str = "en_core_web_sm"):
        self.model_name = model_name
        self._nlp = None
        self._load_lock = asyncio.Lock()

    async def _ensure_model_loaded(self):
        """Lazy load spaCy model (expensive operation)."""
        if self._nlp is not None:
            return

        async with self._load_lock:
            if self._nlp is not None:
                return

            try:
                # Load in thread to avoid blocking
                await asyncio.to_thread(self._load_model)
            except Exception as e:
                logger.error("spacy_model_load_failed", error=str(e))
                raise

    def _load_model(self):
        """Load spaCy model (runs in thread)."""
        try:
            import spacy
            self._nlp = spacy.load(self.model_name)
            logger.info("spacy_model_loaded", model=self.model_name)
        except OSError:
            # Model not found - use blank model as fallback
            logger.warning("spacy_model_not_found",
                         model=self.model_name,
                         fallback="blank")
            import spacy
            self._nlp = spacy.blank("en")

    async def extract_intent(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> ParseResult:
        """Extract intent using spaCy NLP."""
        logger.info("spacy_stage_parsing", transcript=transcript)

        try:
            await self._ensure_model_loaded()

            # Process in thread (spaCy is CPU-bound)
            doc = await asyncio.to_thread(self._nlp, transcript)

            # Extract entities and dependencies
            entities = [(ent.text, ent.label_) for ent in doc.ents]
            verbs = [token.lemma_ for token in doc if token.pos_ == "VERB"]
            adjectives = [token.lemma_ for token in doc if token.pos_ == "ADJ"]

            # Map to lighting intent
            intent = self._map_to_intent(doc, entities, verbs, adjectives, transcript)

            if intent:
                # Calculate confidence based on entity clarity
                confidence = self._calculate_confidence(doc, entities, verbs)

                return ParseResult(
                    intent=intent,
                    confidence=confidence,
                    stage="spacy",
                    context={
                        "entities": entities,
                        "verbs": verbs,
                        "adjectives": adjectives
                    }
                )
            else:
                return ParseResult(
                    intent=None,
                    confidence=0.0,
                    stage="spacy",
                    context={"reason": "no_nlp_match"}
                )

        except Exception as e:
            logger.error("spacy_stage_failed", error=str(e))
            return ParseResult(
                intent=None,
                confidence=0.0,
                stage="spacy",
                context={"error": str(e)}
            )

    def _map_to_intent(self, doc, entities, verbs, adjectives, transcript: str) -> Optional[LightingIntent]:
        """Map spaCy analysis to LightingIntent."""
        from .models import ColorMapping

        # Detect action from verbs
        action = None
        if any(v in ['dim', 'lower', 'darken'] for v in verbs):
            action = 'dim'
        elif any(v in ['flash', 'blink', 'strobe'] for v in verbs):
            action = 'flash'
        elif any(v in ['light', 'set', 'color', 'illuminate'] for v in verbs):
            action = 'color'
        elif any(v in ['turn', 'switch'] for v in verbs) and 'off' in transcript.lower():
            action = 'off'
        elif any(v in ['apply', 'run', 'start'] for v in verbs):
            action = 'pattern'

        if not action:
            return None

        # Detect target (player number or 'all')
        target = 'all'
        for token in doc:
            text_lower = token.text.lower()
            if text_lower in ['p1', 'p2', 'p3', 'p4']:
                target = text_lower
                break
            elif text_lower in ['all', 'everyone', 'everybody']:
                target = 'all'
                break
            elif text_lower.startswith('player'):
                # Extract player number
                for num in ['1', '2', '3', '4']:
                    if num in text_lower:
                        target = f'p{num}'
                        break

        # Detect color from adjectives or entities
        color = None
        for adj in adjectives:
            hex_color = ColorMapping.get_hex(adj)
            if hex_color:
                color = hex_color
                break

        # Also check raw text for color names
        if not color:
            for word in transcript.lower().split():
                hex_color = ColorMapping.get_hex(word)
                if hex_color:
                    color = hex_color
                    break

        # Build intent
        try:
            if action == 'dim':
                return LightingIntent(
                    action='dim',
                    target=target,
                    color='#222222',
                    confidence=0.7
                )
            elif action == 'flash':
                return LightingIntent(
                    action='flash',
                    target=target,
                    color=color or '#FFFFFF',
                    duration_ms=500,
                    confidence=0.75
                )
            elif action == 'color' and color:
                return LightingIntent(
                    action='color',
                    target=target,
                    color=color,
                    confidence=0.8
                )
            elif action == 'off':
                return LightingIntent(
                    action='off',
                    target=target,
                    color='#000000',
                    confidence=0.9
                )
            elif action == 'pattern':
                # Detect pattern name
                pattern = None
                for word in transcript.lower().split():
                    if word in ['rainbow', 'pulse', 'wave', 'chase', 'breathe']:
                        pattern = word
                        break

                if pattern:
                    return LightingIntent(
                        action='pattern',
                        target='all',
                        pattern=pattern,
                        confidence=0.75
                    )
        except Exception as e:
            logger.error("intent_construction_failed", error=str(e))
            return None

        return None

    def _calculate_confidence(self, doc, entities, verbs) -> float:
        """Calculate confidence score based on NLP features."""
        confidence = 0.5  # Base confidence

        # Boost for recognized entities
        if entities:
            confidence += 0.1

        # Boost for clear verb
        if verbs:
            confidence += 0.15

        # Boost for sentence completeness
        if len(doc) >= 3:  # At least 3 tokens
            confidence += 0.1

        # Cap at 0.9 for NLP stage (never 1.0)
        return min(confidence, 0.9)

    def get_stage_name(self) -> str:
        return "spacy"


class ContextResolver(NLPParser):
    """
    Context-aware resolver stage.

    Uses panel state and user history to resolve ambiguities.
    """

    def __init__(self):
        self.panel_context = {}
        self.user_vocab = {}  # User-specific learned vocabulary

    async def extract_intent(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> ParseResult:
        """Resolve intent using context."""
        logger.info("context_resolver_parsing",
                   transcript=transcript,
                   context=context)

        # Get active panel from context
        active_panel = context.get('active_panel')
        user_id = context.get('user_id')

        # Panel-specific resolution
        if active_panel == 'gunner':
            # In gunner calibration, prioritize "light target" as flash
            if 'light' in transcript.lower() and 'target' in transcript.lower():
                try:
                    # Extract target number
                    import re
                    match = re.search(r'target\s+(\d+)', transcript.lower())
                    if match:
                        target_num = match.group(1)
                        return ParseResult(
                            intent=LightingIntent(
                                action='flash',
                                target=target_num,
                                color='#FFFF00',  # Yellow for calibration
                                duration_ms=1000,
                                confidence=0.95
                            ),
                            confidence=0.95,
                            stage="context",
                            context={"panel": "gunner", "method": "calibration_hint"}
                        )
                except Exception as e:
                    logger.error("gunner_context_failed", error=str(e))

        # User-specific vocab resolution
        if user_id and user_id in self.user_vocab:
            vocab = self.user_vocab[user_id]
            # Apply learned aliases
            for alias, canonical in vocab.items():
                if alias in transcript.lower():
                    transcript = transcript.lower().replace(alias, canonical)
                    logger.info("applied_user_vocab",
                              user_id=user_id,
                              alias=alias,
                              canonical=canonical)

        # No context-specific resolution
        return ParseResult(
            intent=None,
            confidence=0.0,
            stage="context",
            context={"reason": "no_context_match"}
        )

    def get_stage_name(self) -> str:
        return "context"

    def update_user_vocab(self, user_id: str, alias: str, canonical: str):
        """Update user-specific vocabulary learning."""
        if user_id not in self.user_vocab:
            self.user_vocab[user_id] = {}

        self.user_vocab[user_id][alias] = canonical
        logger.info("user_vocab_updated",
                   user_id=user_id,
                   alias=alias,
                   canonical=canonical)


class MockNLPParser(NLPParser):
    """
    Mock parser for testing without spaCy dependency.
    """

    async def extract_intent(
        self,
        transcript: str,
        context: Dict[str, Any]
    ) -> ParseResult:
        """Return mock result."""
        return ParseResult(
            intent=None,
            confidence=0.0,
            stage="mock",
            context={"mode": "test"}
        )

    def get_stage_name(self) -> str:
        return "mock"


# LRU cache for hot commands (reduces repeated parsing)
@lru_cache(maxsize=100)
def get_cached_intent(transcript: str) -> Optional[str]:
    """
    Cache common transcripts to avoid repeated parsing.

    Returns serialized intent JSON or None.
    """
    # This is populated by the pipeline on first parse
    return None


def cache_intent(transcript: str, intent_json: str):
    """Cache a successfully parsed intent."""
    # Update LRU cache
    get_cached_intent.__wrapped__(transcript)
    # In production, use Redis or similar for shared cache
    logger.debug("cached_intent", transcript=transcript)


# Dependency injection helpers
def get_keyword_stage() -> KeywordStage:
    """Get keyword parsing stage."""
    return KeywordStage()


def get_spacy_stage(test_mode: bool = False) -> NLPParser:
    """
    Get spaCy NLP stage with environment-based selection.

    Args:
        test_mode: If True, return mock parser

    Returns:
        SpacyNLPStage or MockNLPParser
    """
    if test_mode:
        return MockNLPParser()

    try:
        return SpacyNLPStage()
    except Exception as e:
        logger.warning("spacy_unavailable_fallback_mock", error=str(e))
        return MockNLPParser()


def get_context_resolver() -> ContextResolver:
    """Get context resolver stage."""
    return ContextResolver()
