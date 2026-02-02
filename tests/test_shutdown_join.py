import asyncio, threading, time, types
import pytest
from backend.shutdown_manager import cleanup_resources

@pytest.mark.asyncio
async def test_shutdown_joins_threads():
    """Verify shutdown manager joins worker threads with timeout"""
    app = types.SimpleNamespace(state=types.SimpleNamespace(threads=[]))

    def worker():
        time.sleep(0.05)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    app.state.threads.append(t)

    # Run cleanup
    await cleanup_resources(app)

    # Thread should have finished or been joined
    assert not t.is_alive(), "Worker thread should be joined after cleanup"

@pytest.mark.asyncio
async def test_shutdown_handles_no_threads():
    """Verify cleanup handles apps without threads gracefully"""
    app = types.SimpleNamespace(state=types.SimpleNamespace())

    # Should not crash when no threads attribute
    await cleanup_resources(app)

    # Should not crash when threads is empty
    app.state.threads = []
    await cleanup_resources(app)
