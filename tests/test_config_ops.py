import os, json, time, tempfile, shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="function")
def drive(tmp_path):
    root = tmp_path
    (root / ".aa").mkdir(parents=True, exist_ok=True)
    # Allow configs/state writes; minimal MAME policy
    (root / ".aa" / "manifest.json").write_text(json.dumps({"sanctioned_paths": ["configs", "state"]}), encoding="utf-8")
    (root / ".aa" / "policies.json").write_text(json.dumps({"mame": {"allowed_keys": ["foo"], "file_types": ["ini"]}}), encoding="utf-8")
    os.environ["AA_DRIVE_ROOT"] = str(root)
    os.environ["AA_BACKUP_ON_WRITE"] = "true"
    os.environ["AA_DRY_RUN_DEFAULT"] = "true"
    yield root

@pytest.fixture
def client(drive):
    from backend.app import app
    return TestClient(app)

def test_preview_no_write_by_default(client, drive):
    r = client.post("/config/preview", json={"target_file": "configs/test.ini", "patch": {"foo": "bar"}})
    assert r.status_code == 200
    body = r.json()
    assert body["has_changes"] is True
    assert not (drive / "configs" / "test.ini").exists()

def test_apply_requires_dry_run_false(client, drive):
    r = client.post("/config/apply", headers={"x-scope":"config"}, json={"target_file":"configs/test.ini","patch":{"foo":"bar"},"emulator":"mame"})
    assert r.status_code == 200
    assert r.json()["status"] == "preview"
    # Force write
    r2 = client.post("/config/apply", headers={"x-scope":"config","x-device-id":"TEST-DEVICE","x-panel":"settings"}, json={"target_file":"configs/test.ini","patch":{"foo":"bar"},"emulator":"mame","dry_run":False})
    assert r2.status_code == 200
    assert r2.json()["status"] == "applied"
    assert (drive / "configs" / "test.ini").read_text(encoding="utf-8").strip() == "foo=bar"

def test_apply_logs_device_panel_backup(client, drive):
    # Precreate file to trigger backup
    t = drive / "configs" / "test.ini"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text("foo=old\n", encoding="utf-8")
    r = client.post("/config/apply", headers={"x-scope":"config","x-device-id":"TEST-DEVICE","x-panel":"settings"}, json={"target_file":"configs/test.ini","patch":{"foo":"new"},"emulator":"mame","dry_run":False})
    assert r.status_code == 200
    log = (drive / "logs" / "changes.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    entry = json.loads(log)
    assert entry["device"] == "TEST-DEVICE"
    assert entry["panel"] == "settings"
    assert entry["backup_path"] is not None
    assert entry["result"] == "applied"
    assert entry["ops_count"] == 1
