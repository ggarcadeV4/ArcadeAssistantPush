import pytest
from backend.capabilities.retroarch_gen import RetroArchConfigGenerator
from pathlib import Path
import tempfile

def test_normalize_key_whitespace_comment():
    """Test key normalization with whitespace and comments"""
    gen = RetroArchConfigGenerator()

    # Test comment removal
    assert gen.normalize_key("input_device # Xbox controller") == "input_device"

    # Test whitespace normalization
    assert gen.normalize_key("  Input-Device  ") == "input_device"
    assert gen.normalize_key("VIDEO DRIVER") == "video_driver"

    # Test multiple underscores
    assert gen.normalize_key("input__device___test") == "input_device_test"

def test_no_duplicate_keys():
    """Test duplicate key prevention"""
    gen = RetroArchConfigGenerator()
    controls = {
        "input_device": "Xbox",
        "Input-Device": "PS4",  # Should be deduped
        "INPUT_DEVICE": "Switch",  # Should be deduped
        "video_driver": "gl"
    }

    config = gen.generate_core_config("mame", controls)

    # Should only have 2 unique normalized keys
    normalized_keys = set(gen.normalize_key(k) for k in config.keys())
    assert len(normalized_keys) == 2
    assert "input_device" in [gen.normalize_key(k) for k in config.keys()]
    assert "video_driver" in [gen.normalize_key(k) for k in config.keys()]

def test_diff_generation_normalized():
    """Test diff generation with normalized comparison"""
    gen = RetroArchConfigGenerator()

    existing = {
        "Input_Device": "Xbox",
        "video-driver": "vulkan"
    }

    new = {
        "input_device": "PS5",  # Changed (normalized match)
        "video_driver": "vulkan",  # Unchanged (normalized match)
        "audio_driver": "pulse"  # Added
    }

    diff = gen.diff_configs(existing, new)

    assert "audio_driver" in diff["added"]
    assert len(diff["changed"]) == 1  # input_device changed
    assert diff["total_ops"] == 2  # 1 added, 1 changed

def test_preview_no_writes(tmp_path):
    """Test that preview doesn't write to filesystem"""
    gen = RetroArchConfigGenerator(str(tmp_path))

    # Create SOT file
    sot_path = tmp_path / "config" / "controls_sot.json"
    sot_path.parent.mkdir(parents=True)
    sot_path.write_text('{"mame": {"input_a": "btn1"}}')

    # Get initial modification time
    import time
    before = time.time()

    # Generate preview
    config = gen.generate_core_config("mame", {"input_a": "btn1"})
    diff = gen.diff_configs({}, config)

    # Ensure no new files created
    cfg_path = tmp_path / "config" / "retroarch" / "config" / "mame.cfg"
    assert not cfg_path.exists()

def test_a_drive_constants():
    """Test that only A: drive constants are used"""
    gen = RetroArchConfigGenerator()

    assert str(gen.drive_root) == "A:"
    assert "A:" in str(gen.config_dir)
    assert "A:" in str(gen.sot_path)

    # Should not contain any other drive letters
    assert "C:" not in str(gen.config_dir)
    assert "D:" not in str(gen.config_dir)