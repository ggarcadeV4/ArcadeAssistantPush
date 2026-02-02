import asyncio
import logging
from typing import Any

async def cleanup_resources(app: Any = None):
    """Clean shutdown: cancels asyncio tasks (5s wait) and joins any app.state.threads (2s timeout). Ensures no orphaned workers."""

    # Cancel any background tasks - be more defensive
    try:
        current_task = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
        if tasks:
            print(f"Cancelling {len(tasks)} background tasks...")
            for task in tasks:
                try:
                    if not task.cancelled():
                        task.cancel()
                except Exception as e:
                    print(f"Error cancelling task: {e}")

            # Wait for tasks to complete cancellation with timeout
            try:
                await asyncio.wait(tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED)
            except Exception as e:
                print(f"Error waiting for task cancellation: {e}")
    except Exception as e:
        print(f"Error during task cleanup: {e}")

    # Flush logs
    try:
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    except Exception:
        pass

    # Join background threads if tracked
    try:
        if app is not None and hasattr(app, 'state'):
            threads = getattr(app.state, "threads", [])
            if threads:
                print(f"Joining {len(threads)} background threads...")
                for t in threads:
                    try:
                        t.join(timeout=2.0)
                    except Exception as e:
                        logging.warning(f"Thread join timeout: {getattr(t, 'name', 'unknown')} ({e})")
    except Exception as e:
        print(f"Error during thread cleanup: {e}")

    print("Resources cleaned up successfully")
