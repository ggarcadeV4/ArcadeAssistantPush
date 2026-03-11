from pathlib import Path

from backend.services.adapters.direct_app_adapter import (
    _extract_run_target_from_ahk,
    _parse_daphne_ahk_command,
)


def test_parse_daphne_ahk_resolves_relative_bare_name_with_exe(tmp_path):
    ahk_path = tmp_path / "launch_relative.ahk"
    exe_path = tmp_path / "Hypseus.exe"
    exe_path.write_text("", encoding="utf-8")
    ahk_path.write_text('Run, Hypseus laserdisc.txt -framefile frame.txt\n', encoding="utf-8")

    parsed = _parse_daphne_ahk_command(ahk_path, {})

    assert parsed is not None
    assert Path(parsed["exe"]) == exe_path
    assert parsed["args"] == ["laserdisc.txt", "-framefile", "frame.txt"]


def test_parse_daphne_ahk_resolves_absolute_bare_name_with_exe(tmp_path):
    exe_dir = tmp_path / "Emulators" / "Daphne"
    exe_dir.mkdir(parents=True)
    exe_no_suffix = exe_dir / "Hypseus"
    exe_path = exe_dir / "Hypseus.exe"
    exe_path.write_text("", encoding="utf-8")

    ahk_path = tmp_path / "launch_absolute.ahk"
    ahk_path.write_text(f'Run, "{exe_no_suffix}" laserdisc.txt\n', encoding="utf-8")

    parsed = _parse_daphne_ahk_command(ahk_path, {})

    assert parsed is not None
    assert Path(parsed["exe"]) == exe_path
    assert parsed["args"] == ["laserdisc.txt"]


def test_parse_daphne_ahk_resolves_via_manifest_when_script_dir_missing(tmp_path):
    ahk_path = tmp_path / "launch_manifest.ahk"
    manifest_exe = tmp_path / "manifest" / "hypseus.exe"
    manifest_exe.parent.mkdir(parents=True)
    manifest_exe.write_text("", encoding="utf-8")
    ahk_path.write_text('Run, Hypseus laserdisc.txt\n', encoding="utf-8")

    parsed = _parse_daphne_ahk_command(
        ahk_path,
        {"emulators": {"hypseus": {"exe": str(manifest_exe)}}},
    )

    assert parsed is not None
    assert Path(parsed["exe"]) == manifest_exe
    assert parsed["args"] == ["laserdisc.txt"]


def test_extract_run_target_from_ahk_handles_quoted_comma_path(tmp_path):
    exe_dir = tmp_path / "Path, With Comma"
    exe_dir.mkdir(parents=True)
    exe_path = exe_dir / "hypseus.exe"
    exe_path.write_text("", encoding="utf-8")

    ahk_path = tmp_path / "launch_comma.ahk"
    ahk_path.write_text(
        f'Run, "{exe_path}" romname -framefile frame.txt, , UseErrorLevel\n',
        encoding="utf-8",
    )

    target, args = _extract_run_target_from_ahk(ahk_path)

    assert target == str(exe_path)
    assert args == ["romname", "-framefile", "frame.txt"]


def test_parse_daphne_ahk_unknown_executable_returns_none_with_debug_log(tmp_path, caplog):
    ahk_path = tmp_path / "launch_unknown.ahk"
    ahk_path.write_text("Run, TotallyUnknownLauncher game.txt\n", encoding="utf-8")

    with caplog.at_level("DEBUG"):
        parsed = _parse_daphne_ahk_command(ahk_path, {})

    assert parsed is None
    assert "unsupported_target" in caplog.text