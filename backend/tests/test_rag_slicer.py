import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.rag_slicer import RAGSlicer  # type: ignore  # noqa: E402


def test_default_slicer_reads_factory_prompt_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))

    slicer = RAGSlicer()

    section = slicer.get_section("sega_model_2", "CONTROLLER_CONFIG")

    assert "JoyButton1" in section
    assert "EMULATOR.INI" in section


def test_override_knowledge_base_beats_factory_prompt(monkeypatch, tmp_path: Path):
    override_dir = tmp_path / ".aa" / "state" / "knowledge_base"
    override_dir.mkdir(parents=True)
    (override_dir / "sega_model_2.md").write_text(
        "## CONTROLLER_CONFIG\noverride wins\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))

    slicer = RAGSlicer()

    assert slicer.get_section("sega_model_2", "CONTROLLER_CONFIG") == "override wins"


def test_get_section_accepts_bare_and_header_tags(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    slicer = RAGSlicer()

    bare = slicer.get_section("sega_model_2", "CONTROLLER_CONFIG")
    header = slicer.get_section("sega_model_2", "## CONTROLLER_CONFIG")

    assert bare == header
    assert "JoyCoin" in bare


def test_gunner_persona_resolves_gun_config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    slicer = RAGSlicer()

    section = slicer.get_persona_slice("sega_model_2", "gunner")

    assert "DemulShooter" in section
    assert "A:/Gun Build/Emulators/Sega Model 2/emulator_multicpu.exe" in section


def test_launch_persona_prefers_launch_protocol(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    slicer = RAGSlicer()

    section = slicer.get_persona_slice("sega_model_2", "launchbox")

    assert "-rom=<stem>" in section
    assert "emulator_multicpu.exe -rom=<rom_stem>" in section


def test_launch_persona_falls_back_to_legacy_launch_tag(tmp_path: Path):
    legacy_dir = tmp_path / "kb"
    legacy_dir.mkdir()
    (legacy_dir / "legacy_model2.md").write_text(
        "## LAUNCH\nlegacy launch behavior\n",
        encoding="utf-8",
    )

    slicer = RAGSlicer(knowledge_dir=legacy_dir)

    assert slicer.get_persona_slice("legacy_model2", "launchbox") == "legacy launch behavior"


def test_missing_section_returns_empty_string(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_DRIVE_ROOT", str(tmp_path))
    slicer = RAGSlicer()

    assert slicer.get_section("sega_model_2", "SCORE_TRACKING") == ""
