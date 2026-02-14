from fastapi.testclient import TestClient
from backend.app import app


def test_diagnostics_launches_ok(monkeypatch, tmp_path):
    p = tmp_path/"launch_events.jsonl"
    p.write_text('{"title":"Ms Pac-Man","method_used":"plugin","durationMs":123,"endedAt":"2025-10-13"}\n')
    from backend.routers import diagnostics
    diagnostics.LOG = p
    c = TestClient(app)
    r = c.get("/api/diagnostics/launches")
    j = r.json()
    assert j[0]["title"] == "Ms Pac-Man"

