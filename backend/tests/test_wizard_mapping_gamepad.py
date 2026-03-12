import json
from types import SimpleNamespace

from backend.routers import wizard_mapping
from backend.services.console_wizard_manager import ConsoleWizardManager


XBOX_PROFILE = {
    "profile_id": "xbox_360",
    "name": "Xbox 360 Controller",
    "retroarch_defaults": {
        "input_device": "Xbox 360 Controller",
        "input_player1_up_btn": "h0up",
        "input_player1_down_btn": "h0down",
        "input_player1_left_btn": "h0left",
        "input_player1_right_btn": "h0right",
        "input_player1_b_btn": "0",
        "input_player1_a_btn": "1",
        "input_player1_y_btn": "2",
        "input_player1_x_btn": "3",
        "input_player1_l_btn": "4",
        "input_player1_r_btn": "5",
        "input_player1_select_btn": "6",
        "input_player1_start_btn": "7",
    },
    "axes": {
        "left_stick_x": {"index": 0, "deadzone": 0.15},
        "left_stick_y": {"index": 1, "deadzone": 0.15},
        "right_stick_x": {"index": 2, "deadzone": 0.15},
        "right_stick_y": {"index": 3, "deadzone": 0.15},
    },
}


def test_build_gamepad_controls_from_preferences_adds_aliases_and_axes():
    preferences = {
        "mappings": {
            "up": 12,
            "down": 13,
            "left": 14,
            "right": 15,
            "a": 0,
            "b": 1,
            "x": 2,
            "y": 3,
            "l": 4,
            "r": 5,
            "select": 6,
            "start": 7,
            "l3": 8,
            "r3": 9,
        }
    }

    controls = wizard_mapping._build_gamepad_controls_from_preferences(preferences, XBOX_PROFILE)

    assert controls["p1.button1"]["pin"] == "0"
    assert controls["p1.button6"]["pin"] == "5"
    assert controls["p1.coin"]["pin"] == "6"
    assert controls["p1.start"]["pin"] == "7"
    assert controls["p1.lstick_left"]["pin"] == "-0"
    assert controls["p1.lstick_down"]["pin"] == "+1"
    assert controls["p1.rstick_right"]["pin"] == "+2"
    assert controls["p1.cstick_up"]["pin"] == "-3"


def test_console_wizard_manager_uses_analog_mapping(tmp_path):
    manager = ConsoleWizardManager(tmp_path, {"sanctioned_paths": ["config", "configs", "state", "backups", "logs"]})
    controls = {
        "p1.lstick_up": {"pin": "-0"},
        "p1.lstick_down": {"pin": "+0"},
        "p1.rstick_left": {"pin": "-2"},
    }
    profile = {
        "button_mapping": {},
        "special_controls": {},
        "analog_mapping": {
            "lstick_up": "LUp",
            "lstick_down": "LDown",
            "rstick_left": "RLeft",
        },
        "supported_players": 1,
    }

    mapping = manager._build_mapping_from_profile("pcsx2", controls, profile)

    assert mapping["Pad1/LUp"] == "-0"
    assert mapping["Pad1/LDown"] == "+0"
    assert mapping["Pad1/RLeft"] == "-2"


def test_sync_gamepad_preferences_to_cascade_state_updates_baseline(tmp_path, monkeypatch):
    prefs_path = tmp_path / ".aa" / "state" / "controller" / "gamepad_preferences.json"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(
        json.dumps(
            {
                "profile_id": "xbox_360",
                "mappings": {
                    "up": 12,
                    "down": 13,
                    "left": 14,
                    "right": 15,
                    "a": 0,
                    "b": 1,
                    "select": 6,
                    "start": 7,
                },
                "deadzone": 0.2,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(wizard_mapping, "get_profile_details", lambda profile_id: XBOX_PROFILE)

    class FakeManager:
        def __init__(self, drive_root, manifest):
            self.discovery = SimpleNamespace(
                discover_emulators=lambda console_only=True: [
                    SimpleNamespace(type="retroarch"),
                    SimpleNamespace(type="dolphin"),
                ]
            )

        def _build_mapping_for_emulator(self, emulator, controls):
            assert emulator == "dolphin"
            assert controls["p1.button1"]["pin"] == "0"
            assert controls["p1.lstick_left"]["pin"] == "-0"
            return {
                "GCPad1/Buttons/A": controls["p1.button1"]["pin"],
                "GCPad1/Main Stick/Left": controls["p1.lstick_left"]["pin"],
            }

    monkeypatch.setattr(wizard_mapping, "ConsoleWizardManager", FakeManager)

    result = wizard_mapping._sync_gamepad_preferences_to_cascade_state(tmp_path, {})

    assert result is not None
    assert result["profile_id"] == "xbox_360"
    assert result["emulators_synced"] == 2

    baseline = json.loads((tmp_path / "state" / "controller" / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["emulators"]["retroarch"]["mapping"]["input_player1_up_btn"] == "h0up"
    assert baseline["emulators"]["retroarch"]["mapping"]["input_player1_l_x_deadzone"] == "0.2"
    assert baseline["emulators"]["dolphin"]["mapping"]["GCPad1/Buttons/A"] == "0"
    assert baseline["emulators"]["dolphin"]["mapping"]["GCPad1/Main Stick/Left"] == "-0"