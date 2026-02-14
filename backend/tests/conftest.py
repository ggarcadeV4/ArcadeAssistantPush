import asyncio
import inspect

import pytest


@pytest.fixture
def event_loop():
    """Create a fresh event loop for async tests."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Run coroutine tests without requiring external asyncio plugins."""
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
        if name in pyfuncitem.funcargs
    }

    loop = kwargs.get("event_loop") or pyfuncitem.funcargs.get("event_loop")
    if loop is None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(pyfuncitem.obj(**kwargs))
        finally:
            asyncio.set_event_loop(None)
            loop.close()
    else:
        loop.run_until_complete(pyfuncitem.obj(**kwargs))

    return True
