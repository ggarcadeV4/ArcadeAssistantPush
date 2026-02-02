import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient


def run_smoke():
    # Import app and modules
    from backend.app import app
    from backend.routers import launchbox_import as lb_import
    from backend.services import launchbox_plugin_client as lb_client
    from backend.services import launchbox_cache as lb_cache

    # Bypass real disk check in router
    os.path.isdir = lambda p: True

    # Stub plugin client
    class StubPlugin:
        def __init__(self):
            self.calls = []

        def is_available(self):
            return True

        def list_missing(self, platform, folder):
            if platform.lower().startswith("arcade"):
                missing = [
                    {"path": r"A:\\Console ROMs\\MAME\\game1.zip", "name": "game1"},
                    {"path": r"A:\\Console ROMs\\MAME\\game2.zip", "name": "game2"},
                ]
            else:
                missing = [
                    {"path": r"A:\\Console ROMs\\PlayStation 2\\ps2a.7z", "name": "ps2a"},
                    {"path": r"A:\\Console ROMs\\PlayStation 2\\ps2b.zip", "name": "ps2b"},
                ]
            return {"platform": platform, "folder": folder, "missing": missing, "counts": {"missing": len(missing), "existing": 0}}

        def import_missing(self, platform, folder):
            return {"added": 2, "skipped": 0, "duplicates": 0, "errors": []}

    # Monkeypatch singleton getter
    lb_client._plugin_client = StubPlugin()

    # Capture revalidate call
    revalidated = {"called": False}

    def fake_revalidate():
        revalidated["called"] = True
        return {"ok": True}

    lb_cache.revalidate = fake_revalidate

    c = TestClient(app)

    # Dry-run: MAME
    r = c.get(
        "/api/launchbox/import/missing",
        params={"platform": "Arcade", "folder": r"A:\\Console ROMs\\MAME"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["counts"]["missing"] == 2

    # Dry-run: PS2
    r = c.get(
        "/api/launchbox/import/missing",
        params={"platform": "Sony PlayStation 2", "folder": r"A:\\Console ROMs\\PlayStation 2"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["counts"]["missing"] == 2

    # Apply: MAME
    r = c.post(
        "/api/launchbox/import/apply",
        json={"platform": "Arcade", "folder": r"A:\\Console ROMs\\MAME"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["added"] == 2 and data["skipped"] == 0

    # Apply: PS2
    r = c.post(
        "/api/launchbox/import/apply",
        json={"platform": "Sony PlayStation 2", "folder": r"A:\\Console ROMs\\PlayStation 2"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["added"] == 2 and data["skipped"] == 0

    # Verify revalidate was called at least once
    assert revalidated["called"] is True

    print(json.dumps({"ok": True, "message": "Import routes smoke passed", "revalidated": revalidated["called"]}))


if __name__ == "__main__":
    run_smoke()
