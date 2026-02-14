import os
import types
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.models.game import Game
from backend.models.game import LaunchResponse
from backend.routers import launchbox as lb_router


@pytest.fixture(autouse=True)
def _no_mock_mode(monkeypatch):
    # Ensure router does not reject launches due to mock data
    def fake_stats():
        return {"is_mock_data": False}

    monkeypatch.setattr(lb_router.parser, "get_cache_stats", fake_stats)

    # Provide a fake game for lookups
    def fake_get_game_by_id(game_id: str):
        g = Game(
            id=game_id,
            title="Test Game",
            platform="Arcade",
            application_path="A:/Roms/MAME/test.zip",
            rom_path="A:/Roms/MAME/test.zip",
        )
        return g

    monkeypatch.setattr(lb_router.parser, "get_game_by_id", fake_get_game_by_id)


def test_launch_forbidden_without_panel_header():
    client = TestClient(app)
    r = client.post("/api/launchbox/launch/abc-123", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["method_used"] == "forbidden"


def test_launch_with_force_method_uses_launcher(monkeypatch):
    client = TestClient(app)

    # Monkeypatch launcher.launch to return the forced method
    def fake_launch(game, force_method=None):
        return LaunchResponse(
            success=True,
            game_id=game.id,
            method_used=force_method or "mock",
            command="test",
            message="ok",
        )

    monkeypatch.setattr(lb_router.launcher, "launch", fake_launch)

    r = client.post(
        "/api/launchbox/launch/abc-123",
        headers={"x-panel": "launchbox"},
        json={"force_method": "direct"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["method_used"] == "direct"
