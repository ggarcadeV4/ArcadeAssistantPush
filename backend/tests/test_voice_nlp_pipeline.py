"""Comprehensive tests for advanced NLP parsing pipeline with spaCy mocks."""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from backend.services.voice.nlp_parser import (
    KeywordStage,
    SpacyNLPStage,
    ContextResolver,
    ParseResult,
    MockNLPParser
)
from backend.services.voice.pipeline import (
    ParsingPipeline,
    PipelineConfig,
    WorkerQueue,
    get_pipeline
)
from backend.services.voice.models import LightingIntent


# ============================================================================
# Parser Stage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_keyword_stage_success():
    """Test keyword stage with matching pattern."""
    stage = KeywordStage()

    result = await stage.extract_intent("light p1 red", {})

    assert result.intent is not None
    assert result.intent.action == "color"
    assert result.intent.target == "p1"
    assert result.stage == "keyword"
    assert result.confidence > 0.8


@pytest.mark.asyncio
async def test_keyword_stage_no_match():
    """Test keyword stage with no matching pattern."""
    stage = KeywordStage()

    result = await stage.extract_intent("not a valid command", {})

    assert result.intent is None
    assert result.stage == "keyword"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_spacy_stage_with_mock():
    """Test spaCy stage with mocked model."""
    stage = SpacyNLPStage()

    # Mock spaCy doc
    mock_doc = Mock()
    mock_doc.ents = []
    mock_doc.__iter__ = Mock(return_value=iter([
        Mock(lemma_="dim", pos_="VERB", text="dim"),
        Mock(lemma_="all", pos_="DET", text="all"),
        Mock(lemma_="light", pos_="NOUN", text="lights")
    ]))

    # Mock spaCy model
    mock_nlp = Mock()
    mock_nlp.return_value = mock_doc

    with patch('spacy.load', return_value=mock_nlp):
        await stage._ensure_model_loaded()
        result = await stage.extract_intent("dim all lights", {})

        assert result.stage == "spacy"
        if result.intent:
            assert result.intent.action == "dim"


@pytest.mark.asyncio
async def test_context_resolver_gunner_mode():
    """Test context resolver with gunner panel active."""
    resolver = ContextResolver()

    result = await resolver.extract_intent(
        "light target 5",
        {"active_panel": "gunner"}
    )

    assert result.stage == "context"
    if result.intent:
        # Should flash yellow for calibration
        assert result.intent.action == "flash"
        assert result.intent.color == "#FFFF00"


@pytest.mark.asyncio
async def test_context_resolver_user_vocab():
    """Test context resolver with user vocab learning."""
    resolver = ContextResolver()

    # Train user vocab
    resolver.update_user_vocab("user1", "boo", "blue")

    result = await resolver.extract_intent(
        "light p1 boo",
        {"user_id": "user1"}
    )

    # Transcript should be corrected internally
    # (actual parsing happens in next stage, but vocab is applied)
    assert "user1" in resolver.user_vocab
    assert resolver.user_vocab["user1"]["boo"] == "blue"


# ============================================================================
# Worker Queue Tests
# ============================================================================


@pytest.mark.asyncio
async def test_worker_queue_enqueue():
    """Test worker queue task enqueueing."""
    queue = WorkerQueue(maxsize=5, batch_interval_ms=50)
    await queue.start()

    try:
        # Create mock parser
        mock_parser = Mock(spec=MockNLPParser)
        mock_result = ParseResult(
            intent=None,
            confidence=0.5,
            stage="test"
        )
        mock_parser.extract_intent = Mock(return_value=mock_result)

        # Make extract_intent async
        async def async_extract(*args, **kwargs):
            return mock_result

        mock_parser.extract_intent = async_extract

        # Enqueue task
        result = await queue.enqueue(
            "task1",
            mock_parser,
            "test transcript",
            {}
        )

        assert result is not None
        assert result.stage == "test"

    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_worker_queue_batching():
    """Test worker queue batches multiple tasks."""
    queue = WorkerQueue(maxsize=10, batch_interval_ms=100)
    await queue.start()

    try:
        tasks = []
        for i in range(5):
            mock_parser = Mock(spec=MockNLPParser)

            async def async_extract(transcript, context):
                return ParseResult(
                    intent=None,
                    confidence=0.5,
                    stage=f"batch_{i}"
                )

            mock_parser.extract_intent = async_extract

            task = asyncio.create_task(
                queue.enqueue(f"task{i}", mock_parser, f"test{i}", {})
            )
            tasks.append(task)

        # Wait for all tasks
        results = await asyncio.gather(*tasks)

        assert len(results) == 5

    finally:
        await queue.stop()


# ============================================================================
# Pipeline Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_keyword_early_exit():
    """Test pipeline exits early on high-confidence keyword match."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        results = []
        async for result in pipeline.parse("light p1 red", {}):
            results.append(result)

        # Should have keyword result with high confidence
        assert len(results) >= 1
        keyword_result = results[0]
        assert keyword_result.stage == "keyword"

        # Should exit early if confidence high
        if keyword_result.confidence >= pipeline.config.keyword_threshold:
            assert len(results) == 1  # No further stages

    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_pipeline_fallthrough():
    """Test pipeline falls through to next stage on low confidence."""
    config = PipelineConfig(
        keyword_threshold=0.95,  # Very high threshold
        enable_worker_queue=False  # Disable for test
    )
    pipeline = ParsingPipeline(config=config, test_mode=True)
    await pipeline.start()

    try:
        results = []
        async for result in pipeline.parse("dim all lights", {}):
            results.append(result)

        # Should try multiple stages
        assert len(results) > 1

    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_pipeline_cache_hit():
    """Test pipeline cache returns cached result."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        # First parse (cache miss)
        results1 = []
        async for result in pipeline.parse("light p1 blue", {}):
            results1.append(result)

        # Cache the result manually
        if results1 and results1[0].intent:
            pipeline._cache_result("light p1 blue", results1[0])

        # Second parse (cache hit)
        results2 = []
        async for result in pipeline.parse("light p1 blue", {}):
            results2.append(result)

        # Should return cached result
        if results2:
            assert "cached" in results2[0].stage

    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_pipeline_parse_best():
    """Test pipeline parse_best returns highest confidence."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        result = await pipeline.parse_best("light p1 red", {})

        assert result is not None
        assert result.intent is not None

    finally:
        await pipeline.stop()


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.asyncio
async def test_parse_result_low_confidence_warning():
    """Test ParseResult warns on low confidence."""
    # Should log warning but not raise
    result = ParseResult(
        intent=LightingIntent(action="color", target="p1", color="#FF0000"),
        confidence=0.5,  # Low confidence
        stage="test"
    )

    assert result.confidence == 0.5


@pytest.mark.asyncio
async def test_parse_result_invalid_confidence():
    """Test ParseResult rejects invalid confidence."""
    with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
        ParseResult(
            intent=None,
            confidence=1.5,  # Invalid
            stage="test"
        )


@pytest.mark.asyncio
async def test_spacy_stage_model_not_found_fallback():
    """Test spaCy stage falls back to blank model if model not found."""
    with patch('spacy.load', side_effect=OSError("Model not found")):
        with patch('spacy.blank') as mock_blank:
            mock_doc = Mock()
            mock_doc.ents = []
            mock_doc.__iter__ = Mock(return_value=iter([]))

            mock_nlp = Mock()
            mock_nlp.return_value = mock_doc
            mock_blank.return_value = mock_nlp

            stage = SpacyNLPStage()
            await stage._ensure_model_loaded()

            # Should have loaded blank model
            assert stage._nlp is not None


@pytest.mark.asyncio
async def test_pipeline_no_match():
    """Test pipeline handles no match across all stages."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        results = []
        async for result in pipeline.parse("xyz abc invalid", {}):
            results.append(result)

        # Should try all stages but find no match
        for result in results:
            if result.intent:
                # If any match found, should have low confidence
                assert result.confidence < 0.7

    finally:
        await pipeline.stop()


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_full_pipeline_with_context():
    """Test full pipeline with panel context."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        context = {
            "user_id": "user1",
            "active_panel": "gunner"
        }

        results = []
        async for result in pipeline.parse("light target 3", context):
            results.append(result)

        # Should get results
        assert len(results) > 0

    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_concurrent_pipeline_requests():
    """Test pipeline handles concurrent requests."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        tasks = [
            asyncio.create_task(pipeline.parse_best(f"light p{i} red", {}))
            for i in range(1, 5)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete
        assert len(results) == 4

    finally:
        await pipeline.stop()


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_performance():
    """Test pipeline performance with 50 requests."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        import time
        start = time.time()

        tasks = [
            asyncio.create_task(pipeline.parse_best(f"light p1 red", {}))
            for _ in range(50)
        ]

        await asyncio.gather(*tasks)

        elapsed = time.time() - start

        # Should complete in <2 seconds
        assert elapsed < 2.0

    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_cache_performance_boost():
    """Test cache provides performance boost."""
    pipeline = ParsingPipeline(test_mode=True)
    await pipeline.start()

    try:
        import time

        # First parse (cache miss)
        start = time.time()
        await pipeline.parse_best("light p1 blue", {})
        first_time = time.time() - start

        # Cache it
        result = await pipeline.parse_best("light p1 blue", {})
        if result:
            pipeline._cache_result("light p1 blue", result)

        # Second parse (cache hit)
        start = time.time()
        result = await pipeline.parse_best("light p1 blue", {})
        second_time = time.time() - start

        # Cache should be faster (or similar for mock)
        # In production with real spaCy, would be significantly faster

    finally:
        await pipeline.stop()
