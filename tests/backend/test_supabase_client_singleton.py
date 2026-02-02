from pathlib import Path
from types import SimpleNamespace
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services import supabase_client as sc


def setup_function():
    sc.reset_supabase_client()


def test_injected_client_is_returned():
    injected = SimpleNamespace(name="injected")
    sc.inject_supabase_client(injected)

    assert sc.get_client() is injected


def test_cached_client_reuses_instance(monkeypatch):
    created = []

    def fake_instantiate(url, anon_key):
        sentinel = SimpleNamespace(url=url, anon=anon_key)
        created.append(sentinel)
        return sentinel

    monkeypatch.setattr(sc, "_instantiate_client", fake_instantiate)
    sc.reset_supabase_client()

    first = sc.get_client("https://example.supabase.co", "anon")
    second = sc.get_client("https://example.supabase.co", "anon")

    assert first is second
    assert len(created) == 1  # Only one instantiation due to caching
