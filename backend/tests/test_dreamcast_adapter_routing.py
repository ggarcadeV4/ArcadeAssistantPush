from types import SimpleNamespace

from backend.services.adapters import flycast_adapter
from backend.services.adapters import redream_adapter


def test_flycast_does_not_claim_dreamcast_when_redream_exists(monkeypatch):
    game = SimpleNamespace(platform="Sega Dreamcast")

    monkeypatch.setattr(flycast_adapter, "_redream_available", lambda: True)

    assert flycast_adapter.can_handle(game, {}) is False


def test_flycast_claims_dreamcast_only_when_redream_missing(monkeypatch):
    game = SimpleNamespace(platform="Sega Dreamcast")

    monkeypatch.setattr(flycast_adapter, "_redream_available", lambda: False)

    assert flycast_adapter.can_handle(game, {}) is True


def test_redream_resolve_marks_detached_no_pipe(monkeypatch, tmp_path):
    exe_dir = tmp_path / "redream"
    exe_dir.mkdir()
    exe_path = exe_dir / "redream.exe"
    exe_path.write_text("", encoding="ascii")

    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    rom_path = rom_dir / "Capcom vs. SNK (USA).chd"
    rom_path.write_text("", encoding="ascii")

    game = SimpleNamespace(
        platform="Sega Dreamcast",
        application_path=str(rom_path),
        rom_path=None,
        romPath=None,
    )

    monkeypatch.setattr(redream_adapter.EmulatorPaths, "redream", staticmethod(lambda: exe_path))

    cfg = redream_adapter.resolve(game, {})

    assert cfg["exe"] == str(exe_path)
    assert cfg["args"] == [str(rom_path)]
    assert cfg["cwd"] == str(exe_dir)
    assert cfg["no_pipe"] is True
