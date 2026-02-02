import configparser
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Tuple

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.services.controller_baseline import (  # noqa:E402
    load_controller_baseline,
    update_controller_baseline,
)
from backend.services.controller_cascade import (  # noqa:E402
    enqueue_cascade_job,
    run_cascade_job,
    _validate_mame_cli,
)


class _FakeProcessSuccess:
    def __init__(self, stdout_text: str = "<game name='sf2'/>"):
        self._stdout = io.StringIO(stdout_text)
        self._stderr = io.StringIO("")
        self._killed = False

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._killed = True


class _FakeProcessTimeout:
    def __init__(self):
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self._killed = False

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd=["mame"], timeout=timeout)

    def kill(self):
        self._killed = True


def _prepare_drive_root(tmp_path: Path) -> Path:
    drive_root = tmp_path / "drive"
    drive_root.mkdir(parents=True, exist_ok=True)
    (drive_root / "state" / "controller").mkdir(parents=True, exist_ok=True)
    (drive_root / "emulators" / "mame").mkdir(parents=True, exist_ok=True)
    return drive_root


def _write_dummy_files(drive_root: Path) -> Tuple[Path, Path]:
    mame_ini = drive_root / "emulators" / "mame" / "mame.ini"
    mame_ini.parent.mkdir(parents=True, exist_ok=True)
    mame_ini.write_text("[DEFAULT]\n", encoding="utf-8")

    mame_exe = drive_root / "emulators" / "mame" / "mame.exe"
    mame_exe.write_text("dummy", encoding="utf-8")
    os.chmod(mame_exe, 0o755)
    return mame_ini, mame_exe


def _baseline_with_mame(drive_root: Path, mapping: dict, roms: Iterable[str] = ()):
    load_controller_baseline(drive_root)
    update_controller_baseline(
        drive_root,
        {
            "emulators": {
                "mame": {
                    "mapping": mapping,
                    "roms": list(roms),
                }
            }
        },
        backup=False,
    )


def test_validate_mame_cli_success(monkeypatch, tmp_path):
    from backend.services import controller_cascade as cascade  # local import for monkeypatch

    drive_root = _prepare_drive_root(tmp_path)
    _, mame_exe = _write_dummy_files(drive_root)

    def fake_popen(cmd, stdout=None, stderr=None, text=None):
        return _FakeProcessSuccess("<game name='sf2'/>\n<game name='mk2'/>")

    monkeypatch.setattr(cascade.subprocess, "Popen", fake_popen)

    ok, message = _validate_mame_cli(mame_exe, rom_filter=["sf2"])
    assert ok is True
    assert "validated" in message.lower()


def test_validate_mame_cli_timeout(monkeypatch, tmp_path):
    from backend.services import controller_cascade as cascade

    drive_root = _prepare_drive_root(tmp_path)
    _, mame_exe = _write_dummy_files(drive_root)

    def fake_popen(cmd, stdout=None, stderr=None, text=None):
        return _FakeProcessTimeout()

    monkeypatch.setattr(cascade.subprocess, "Popen", fake_popen)

    ok, message = _validate_mame_cli(mame_exe, rom_filter=[])
    assert ok is False
    assert "timed out" in message.lower()


def test_run_cascade_job_mame_success(monkeypatch, tmp_path):
    from backend.services import controller_cascade as cascade

    drive_root = _prepare_drive_root(tmp_path)
    mame_ini, mame_exe = _write_dummy_files(drive_root)

    mapping = {
        "DEFAULT": {"coin_lockout": "0"},
        "input_general": {"joystick_deadzone": "0.25"},
    }
    _baseline_with_mame(drive_root, mapping, roms=["sf2"])

    manifest = {
        "sanctioned_paths": ["state", "emulators", "LED"],
        "emulators": {
            "mame": {
                "ini": "emulators/mame/mame.ini",
                "executable": "emulators/mame/mame.exe",
            }
        },
    }

    monkeypatch.setattr(
        cascade,
        "_validate_mame_cli",
        lambda exe, rom_filter: (True, "CLI OK"),
    )

    job = enqueue_cascade_job(
        drive_root,
        requested_by="test-device",
        skip_led=True,
        skip_emulators=[],
        backup=False,
    )

    run_cascade_job(
        drive_root,
        manifest,
        job["job_id"],
        backup=False,
    )

    baseline_after = load_controller_baseline(drive_root)
    mame_state = baseline_after["emulators"]["mame"]

    assert mame_state["status"] == "completed"
    assert "CLI OK" in mame_state["message"]
    assert "coin_lockout" in Path(mame_state["config_path"]).name or mame_state["config_path"].endswith("mame.ini")

    parser = configparser.ConfigParser()
    parser.read(mame_ini, encoding="utf-8")
    assert parser["DEFAULT"]["coin_lockout"] == "0"
    assert parser["input_general"]["joystick_deadzone"] == "0.25"
