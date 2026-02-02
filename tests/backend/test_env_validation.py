import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODULE_NAME = "backend.main"


def _reload_main(monkeypatch) -> object:
    """Reload backend.main with fresh environment."""
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service")
    monkeypatch.setenv("AA_DRIVE_ROOT", "C:/Arcade")
    monkeypatch.setenv("AA_SKIP_APP_IMPORT", "1")
    monkeypatch.delenv("AA_SKIP_ENV_VALIDATION", raising=False)


def test_env_settings_loaded_when_all_keys_present(monkeypatch):
    _set_required_env(monkeypatch)
    module = _reload_main(monkeypatch)

    assert module.settings is not None
    assert module.settings.supabase_url == "https://example.supabase.co"
    assert module.settings.port == 8787


def test_env_validation_raises_when_supabase_missing(monkeypatch):
    for key in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "AA_DRIVE_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AA_SKIP_APP_IMPORT", "1")
    monkeypatch.delenv("AA_SKIP_ENV_VALIDATION", raising=False)

    with pytest.raises(RuntimeError):
        _reload_main(monkeypatch)
