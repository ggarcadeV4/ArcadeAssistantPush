"""Compatibility shim for the launcher service.

The checked-in launcher module was truncated to an empty file. Load the
latest local backup and re-export its symbols so existing imports keep
working until the canonical source is restored.
"""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

_BACKUP_PATH = Path(__file__).with_name("launcher.py.bak-0f")

if not _BACKUP_PATH.exists():
    raise ImportError(f"Launcher backup not found: {_BACKUP_PATH}")

_LOADER = SourceFileLoader("backend.services._launcher_backup", str(_BACKUP_PATH))
_SPEC = spec_from_loader(_LOADER.name, _LOADER)
if _SPEC is None:
    raise ImportError(f"Unable to create launcher spec for {_BACKUP_PATH}")

_MODULE = module_from_spec(_SPEC)
_LOADER.exec_module(_MODULE)

for _name in dir(_MODULE):
    if _name.startswith("__") and _name not in {"__doc__", "__all__"}:
        continue
    globals()[_name] = getattr(_MODULE, _name)

