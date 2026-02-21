import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import led, led_blinky
from backend.services.led_mapping_service import LEDMappingService


def _build_service(tmp_path):
    drive_root = tmp_path / "drive"
    drive_root.mkdir()

    _write_controls_file(
        drive_root,
        {
            "p1.button1": {"pin": 8, "label": "P1 Button 1"},
            "p1.button2": {"pin": 9, "label": "P1 Button 2"},
        },
    )
    _write_channel_file(
        drive_root,
        {
            "p1.button1": {"device_id": "mock-device", "channel": 8},
            "p1.button2": {"device_id": "mock-device", "channel": 9},
        },
    )

    manifest = {
        "sanctioned_paths": [
            "config",
            "configs",
            "configs/ledblinky",
            "configs/ledblinky/profiles",
            "backups",
            "logs",
        ]
    }

    service = LEDMappingService(drive_root, manifest)
    return service, drive_root


def _build_app(tmp_path):
    app = FastAPI()
    drive_root = tmp_path / "drive"
    drive_root.mkdir()
    (drive_root / "logs").mkdir()
    (drive_root / "configs" / "ledblinky" / "profiles").mkdir(parents=True, exist_ok=True)
    manifest = {
        "sanctioned_paths": [
            "config",
            "configs",
            "configs/ledblinky",
            "configs/ledblinky/profiles",
            "logs",
            "backups",
        ]
    }
    app.state.drive_root = drive_root
    app.state.manifest = manifest
    app.state.backup_on_write = True
    app.state.dry_run_default = True
    app.include_router(led_blinky.router, prefix="/api/local/led")
    return app, drive_root


def _build_led_router_app(tmp_path):
    app = FastAPI()
    drive_root = tmp_path / "drive"
    drive_root.mkdir()
    (drive_root / "logs").mkdir()
    (drive_root / "configs" / "ledblinky" / "profiles").mkdir(parents=True, exist_ok=True)
    manifest = {
        "sanctioned_paths": [
            "config",
            "configs",
            "configs/ledblinky",
            "configs/ledblinky/profiles",
            "logs",
            "backups",
        ]
    }
    _write_controls_file(
        drive_root,
        {
            "p1.button1": {"pin": 4, "type": "button"},
            "p1.button2": {"pin": 5, "type": "button"},
        },
    )
    _write_channel_file(
        drive_root,
        {
            "p1.button1": {"device_id": "mock-device", "channel": 4},
            "p1.button2": {"device_id": "mock-device", "channel": 5},
        },
    )
    app.state.drive_root = drive_root
    app.state.manifest = manifest
    app.state.backup_on_write = True
    app.state.dry_run_default = True
    app.include_router(led.router, prefix="/api/local/led")
    return app, drive_root


def _write_controls_file(drive_root, mappings):
    controls_dir = drive_root / "config" / "mappings"
    controls_dir.mkdir(parents=True, exist_ok=True)
    payload = {"board": {"vid": "0xAAAA", "pid": "0xBBBB", "name": "Fixture"}, "mappings": mappings}
    (controls_dir / "controls.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_channel_file(drive_root, channels):
    channel_path = drive_root / "configs" / "ledblinky"
    channel_path.mkdir(parents=True, exist_ok=True)
    payload = {"channels": channels}
    (channel_path / "led_channels.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_preview_resolves_buttons_and_reports_diff(tmp_path):
    service, drive_root = _build_service(tmp_path)
    payload = {
        "profile_name": "space-invaders",
        "scope": "game",
        "game": "space-invaders",
        "buttons": {
            "p1.button1": "#FF0000",
            "p1.button2": {"color": "#00FF00", "pattern": "wave"},
            "p9.button9": "#123456",
        },
    }

    preview = service.preview(payload)
    response = preview.response

    assert response["profile_name"] == "space-invaders"
    assert response["target_file"] == "configs/ledblinky/profiles/space-invaders.json"
    assert response["buttons"]["p1.button1"]["color"] == "#FF0000"
    assert response["resolved_buttons"][0]["channels"][0]["channel_index"] == 8
    assert "p9.button9" in response["missing_buttons"]
    assert response["has_changes"] is True
    assert "p1.button1" in response["diff"]
    assert response["total_channels"] == 2

    mapping_payload = service.load_controls_mapping()
    assert "p1.button1" in mapping_payload["mappings"]


def test_apply_writes_logical_payload_and_supports_dry_run(tmp_path):
    service, drive_root = _build_service(tmp_path)
    profiles_dir = drive_root / "configs" / "ledblinky" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = profiles_dir / "default.json"
    legacy_file.write_text(json.dumps({"old": True}), encoding="utf-8")

    payload = {
        "profile_name": "default",
        "scope": "default",
        "buttons": {"p1.button1": "#00FFAA"},
    }
    preview = service.preview(payload)
    result = service.apply(payload, dry_run=False, backup_on_write=True, preview=preview)

    assert result["status"] == "applied"
    assert result["target_file"] == "configs/ledblinky/profiles/default.json"
    assert result["backup_path"] is not None
    backup_file = drive_root / Path(result["backup_path"])
    assert backup_file.exists()
    written = json.loads((drive_root / Path(result["target_file"])).read_text())
    assert written["buttons"] == {"p1.button1": {"color": "#00FFAA"}}
    assert "resolved_buttons" not in written

    updated_preview = service.preview(
        {
            "profile_name": "default",
            "scope": "default",
            "buttons": {"p1.button1": "#770000"},
        }
    )
    dry_run_result = service.apply(
        {
            "profile_name": "default",
            "scope": "default",
            "buttons": {"p1.button1": "#770000"},
        },
        dry_run=True,
        backup_on_write=True,
        preview=updated_preview,
    )

    assert dry_run_result["status"] == "dry_run"
    assert dry_run_result["backup_path"] is None
    updated_written = json.loads((drive_root / Path(result["target_file"])).read_text())
    assert updated_written["buttons"]["p1.button1"]["color"] == "#00FFAA"


def test_preview_uses_scope_defaults_and_sanitizes_target(tmp_path):
    service, _ = _build_service(tmp_path)
    payload = {
        "scope": "game",
        "game": "My Game / 1",
        "buttons": {"p1.button2": "#ABCDEF"},
    }

    preview = service.preview(payload)
    response = preview.response

    assert response["profile_name"] == "My Game / 1"
    assert response["target_file"] == "configs/ledblinky/profiles/My_Game___1.json"
    assert response["missing_buttons"] == []
    assert response["buttons"]["p1.button2"]["color"] == "#ABCDEF"


def test_mapping_preview_endpoint_resolves_physical_channels(tmp_path):
    app, drive_root = _build_app(tmp_path)
    _write_controls_file(
        drive_root,
        {
            "p1.button1": {"pin": 4, "type": "button"},
            "p1.button2": {"pin": 5, "type": "button"},
        },
    )
    _write_channel_file(
        drive_root,
        {
            "p1.button1": {"device_id": "mock-device", "channel": 4},
            "p1.button2": {"device_id": "mock-device", "channel": 5},
        },
    )
    client = TestClient(app)

    payload = {
        "scope": "game",
        "game": "marble-madness",
        "buttons": {"p1.button1": {"color": "#ff0000"}},
    }
    response = client.post(
        "/api/local/led/mapping/preview",
        json=payload,
        headers={"x-device-id": "TEST", "x-panel": "led-blinky"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_changes"] is True
    assert data["target_file"].endswith("configs/ledblinky/profiles/marble-madness.json")
    assert data["buttons"]["p1.button1"]["color"] == "#ff0000"
    assert data["resolved_buttons"][0]["channels"][0]["channel_index"] == 4
    assert "p1.button1" in data["diff"]


def test_mapping_apply_dry_run_and_backup_logging(tmp_path):
    app, drive_root = _build_app(tmp_path)
    _write_controls_file(
        drive_root,
        {
            "p1.button1": {"pin": 4, "type": "button"},
            "p1.button2": {"pin": 5, "type": "button"},
        },
    )
    _write_channel_file(
        drive_root,
        {
            "p1.button1": {"device_id": "mock-device", "channel": 4},
            "p1.button2": {"device_id": "mock-device", "channel": 5},
        },
    )
    client = TestClient(app)
    profiles_dir = drive_root / "configs" / "ledblinky" / "profiles"
    target_file = profiles_dir / "default.json"
    target_file.write_text(
        json.dumps(
            {
                "profile_name": "default",
                "scope": "default",
                "buttons": {"p1.button1": {"color": "#000000"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    headers = {
        "x-device-id": "CAB-TEST",
        "x-panel": "led-blinky",
        "x-scope": "config",
    }
    base_payload = {
        "scope": "default",
        "buttons": {"p1.button1": {"color": "#00ff00"}},
    }

    dry_response = client.post(
        "/api/local/led/mapping/apply",
        json={**base_payload, "dry_run": True},
        headers=headers,
    )
    assert dry_response.status_code == 200
    dry_data = dry_response.json()
    assert dry_data["status"] == "dry_run"
    assert target_file.read_text(encoding="utf-8").count("#00ff00") == 0

    apply_response = client.post(
        "/api/local/led/mapping/apply",
        json={**base_payload, "dry_run": False},
        headers=headers,
    )
    assert apply_response.status_code == 200
    apply_data = apply_response.json()
    assert apply_data["status"] == "applied"
    assert apply_data["backup_path"]
    backup_file = drive_root / Path(apply_data["backup_path"])
    assert backup_file.exists()

    # Stored file contains logical data only (no physical channels)
    written_doc = json.loads(target_file.read_text(encoding="utf-8"))
    assert "resolved_buttons" not in written_doc
    assert written_doc["buttons"]["p1.button1"]["color"] == "#00ff00"
    serialized_written = json.dumps(written_doc)
    assert "channel_index" not in serialized_written
    assert "device_id" not in serialized_written

    # Verify log entry was written
    # Golden Drive contract: logs move to .aa/logs/led/changes.jsonl
    log_file = drive_root / ".aa" / "logs" / "led" / "changes.jsonl"
    assert log_file.exists()
    last_entry = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert last_entry["action"] == "mapping_apply"
    assert last_entry["backup_path"].endswith(Path(apply_data["backup_path"]).name)
    details = last_entry.get("details") or {}
    assert details["target_file"].endswith("configs/ledblinky/profiles/default.json")
    assert details["status"] == "applied"


def test_led_channel_mapping_endpoints(tmp_path):
    app, drive_root = _build_led_router_app(tmp_path)
    client = TestClient(app)
    headers = {"x-device-id": "CAB-TEST", "x-panel": "led-blinky"}

    list_response = client.get("/api/local/led/channels", headers=headers)
    assert list_response.status_code == 200
    data = list_response.json()
    assert data["total_channels"] == 2
    assert "p1.button1" in data["channels"]

    preview_payload = {
        "updates": [
            {
                "logical_button": "p1.button1",
                "device_id": "mock-device",
                "channel": 7,
            }
        ]
    }
    preview_response = client.post(
        "/api/local/led/channels/preview",
        json=preview_payload,
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["has_changes"] is True
    assert preview["channels"]["p1.button1"]["channel"] == 7

    apply_headers = {**headers, "x-scope": "config"}
    apply_response = client.post(
        "/api/local/led/channels/apply",
        json={**preview_payload, "dry_run": False},
        headers=apply_headers,
    )
    assert apply_response.status_code == 200
    apply_data = apply_response.json()
    assert apply_data["status"] == "applied"
    assert apply_data["backup_path"]

    stored = json.loads((drive_root / "configs" / "ledblinky" / "led_channels.json").read_text())
    assert stored["channels"]["p1.button1"]["channel"] == 7

    delete_response = client.delete(
        "/api/local/led/channels/p1.button2",
        headers=apply_headers,
    )
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["status"] in {"applied", "no_changes"}

    start_resp = client.post("/api/local/led/calibrate/start", headers=apply_headers)
    assert start_resp.status_code == 200
    token = start_resp.json()["token"]
    assign_response = client.post(
        "/api/local/led/calibrate/assign",
        json={
            "token": token,
            "logical_button": "p1.button1",
            "device_id": "mock-device",
            "channel": 9,
            "dry_run": False,
        },
        headers=apply_headers,
    )
    assert assign_response.status_code == 200
    flash_response = client.post(
        "/api/local/led/calibrate/flash",
        json={"token": token, "logical_button": "p1.button1", "duration_ms": 100},
        headers=apply_headers,
    )
    assert flash_response.status_code == 200
    stop_resp = client.post(
        "/api/local/led/calibrate/stop",
        json={"token": token},
        headers=apply_headers,
    )
    assert stop_resp.status_code == 200
    updated_channels = json.loads((drive_root / "configs" / "ledblinky" / "led_channels.json").read_text())
    assert updated_channels["channels"]["p1.button1"]["channel"] == 9
