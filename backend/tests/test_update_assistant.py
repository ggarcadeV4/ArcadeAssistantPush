import asyncio
import json
import zipfile
from pathlib import Path

from backend.services.update_assistant import UpdateAssistant


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, indent=2))


def _seed_drive(drive_root: Path) -> None:
    _write_text(drive_root / "backend" / "app.py", "print('old backend')\n")
    _write_text(drive_root / "frontend" / "dist" / "index.html", "<html>old</html>\n")
    _write_text(drive_root / "gateway" / "server.js", "console.log('old gateway')\n")
    _write_json(drive_root / "configs" / "app.json", {"mode": "old"})
    _write_text(drive_root / "prompts" / "base.txt", "old prompt\n")
    _write_text(drive_root / ".aa" / "state" / "session.json", '{"keep":"state"}\n')
    _write_text(drive_root / ".aa" / "device_id.txt", "device-123\n")
    _write_json(drive_root / ".aa" / "cabinet_manifest.json", {"name": "cabinet"})
    _write_text(drive_root / ".env", "AA_DEVICE_ID=placeholder\nKEEP=1\n")
    _write_json(drive_root / ".aa" / "version.json", {"version": "1.0.0"})


def _make_bundle(bundle_path: Path, manifest: dict, payload_files: dict[str, str]) -> Path:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for relative_path, content in payload_files.items():
            archive.writestr(relative_path, content)
    return bundle_path


def test_download_update_returns_disabled_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("AA_UPDATES_ENABLED", "0")

    assistant = UpdateAssistant()
    result = asyncio.run(assistant.download_update("https://example.com/update.zip"))

    assert result["status"] == "disabled"


def test_apply_update_preserves_identity_files_and_manual_rollback_restores_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("AA_UPDATES_ENABLED", "1")
    _seed_drive(tmp_path)

    manifest = {
        "version": "1.2.0",
        "previous_version": "1.0.0",
        "release_notes": "Patch release",
        "files": [
            {"path": "backend/app.py", "action": "replace"},
            {"path": "configs/app.json", "action": "replace"},
            {"path": ".env", "action": "replace"},
            {"path": ".aa/device_id.txt", "action": "replace"},
            {"path": ".aa/state/session.json", "action": "replace"},
        ],
    }
    bundle = _make_bundle(
        tmp_path / "bundle.zip",
        manifest,
        {
            "backend/app.py": "print('new backend')\n",
            "configs/app.json": json.dumps({"mode": "new"}),
            ".env": "AA_DEVICE_ID=overwrite-me\n",
            ".aa/device_id.txt": "overwritten-device\n",
            ".aa/state/session.json": '{"keep":"overwritten"}\n',
        },
    )

    assistant = UpdateAssistant()
    result = asyncio.run(assistant.apply_update(bundle))

    assert result["status"] == "applied"
    assert (tmp_path / "backend" / "app.py").read_text(encoding="utf-8") == "print('new backend')\n"
    assert json.loads((tmp_path / "configs" / "app.json").read_text(encoding="utf-8")) == {"mode": "new"}
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "AA_DEVICE_ID=placeholder\nKEEP=1\n"
    assert (tmp_path / ".aa" / "device_id.txt").read_text(encoding="utf-8") == "device-123\n"
    assert (tmp_path / ".aa" / "state" / "session.json").read_text(encoding="utf-8") == '{"keep":"state"}\n'
    assert (tmp_path / ".aa" / "updates" / "last_update.json").exists()

    _write_text(tmp_path / "backend" / "app.py", "print('broken local change')\n")
    rollback_result = asyncio.run(assistant.rollback(reason="test rollback"))

    assert rollback_result["status"] == "rolled_back"
    assert (tmp_path / "backend" / "app.py").read_text(encoding="utf-8") == "print('old backend')\n"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "AA_DEVICE_ID=placeholder\nKEEP=1\n"
    assert (tmp_path / ".aa" / "device_id.txt").read_text(encoding="utf-8") == "device-123\n"
    assert (tmp_path / ".aa" / "cabinet_manifest.json").read_text(encoding="utf-8").strip()
    assert (tmp_path / ".aa" / "state" / "session.json").read_text(encoding="utf-8") == '{"keep":"state"}\n'
    assert (tmp_path / ".aa" / "updates" / "last_rollback.json").exists()


def test_handle_update_command_reports_processing_and_completed(tmp_path, monkeypatch):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    monkeypatch.setenv("AA_UPDATES_ENABLED", "1")

    assistant = UpdateAssistant()
    statuses: list[tuple[str, dict | None]] = []

    async def fake_download_update(**_kwargs):
        return tmp_path / "downloaded.zip"

    async def fake_apply_update(**_kwargs):
        return {"status": "applied", "version": "1.2.3", "rolled_back": False}

    def fake_report(command_id, status, result=None):
        statuses.append((status, result))

    monkeypatch.setattr(assistant, "download_update", fake_download_update)
    monkeypatch.setattr(assistant, "apply_update", fake_apply_update)
    monkeypatch.setattr(assistant, "_report_command_status", fake_report)

    result = asyncio.run(
        assistant.handle_update_command(
            {"bundle_url": "https://example.com/update.zip", "version": "1.2.3"},
            command_id=42,
        )
    )

    assert result["status"] == "applied"
    assert statuses[0][0] == "PROCESSING"
    assert statuses[-1][0] == "COMPLETED"
