"""Persistent encoder declaration helpers for Wiz/Chuck integration."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BOARD_MODEL_MAP: Dict[str, Dict[str, Any]] = {
    "pacto_2000t": {"name": "Pacto Tech 2000T", "players": 2},
    "pacto_4000t": {"name": "Pacto Tech 4000T", "players": 4},
}


def declaration_path(drive_root: Path) -> Path:
    return drive_root / ".aa" / "state" / "controller" / "encoder_declaration.json"


def normalize_board_model(board_model: str) -> Optional[str]:
    token = str(board_model or "").strip().lower()
    return token if token in BOARD_MODEL_MAP else None


def load_encoder_declaration(drive_root: Path) -> Optional[Dict[str, Any]]:
    path = declaration_path(drive_root)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read encoder declaration: %s", exc)
        return None

    board_model = normalize_board_model(data.get("board_model", ""))
    if not board_model:
        return None

    model_meta = BOARD_MODEL_MAP[board_model]
    declaration = {
        "version": int(data.get("version", 1)),
        "saved_at": str(data.get("saved_at") or ""),
        "board_model": board_model,
        "board_name": str(data.get("board_name") or model_meta["name"]),
        "players": int(data.get("players") or model_meta["players"]),
        "vid": "0x045e",
        "pid": "0x028e",
        "vid_pid": "0x045e:0x028e",
        "type": "keyboard_encoder",
        "controller_ids": list(data.get("controller_ids") or []),
        "source_controllers": list(data.get("source_controllers") or []),
    }
    return declaration


def save_encoder_declaration(
    drive_root: Path,
    *,
    board_model: str,
    controller_ids: Optional[List[str]] = None,
    source_controllers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    normalized = normalize_board_model(board_model)
    if not normalized:
        raise ValueError(f"Unsupported board model: {board_model}")

    model_meta = BOARD_MODEL_MAP[normalized]
    payload: Dict[str, Any] = {
        "version": 1,
        "saved_at": datetime.now().isoformat(),
        "board_model": normalized,
        "board_name": model_meta["name"],
        "players": model_meta["players"],
        "vid": "0x045e",
        "pid": "0x028e",
        "vid_pid": "0x045e:0x028e",
        "type": "keyboard_encoder",
        "controller_ids": list(controller_ids or []),
        "source_controllers": list(source_controllers or []),
    }

    path = declaration_path(drive_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
        prefix="encoder_declaration_",
    )
    try:
        import os as _os

        with _os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        Path(tmp_path).replace(path)
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise

    return payload


def clear_encoder_declaration(drive_root: Path) -> bool:
    path = declaration_path(drive_root)
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def declaration_as_board_entry(declaration: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not declaration:
        return None

    board_model = normalize_board_model(declaration.get("board_model", ""))
    if not board_model:
        return None

    model_meta = BOARD_MODEL_MAP[board_model]
    return {
        "vid": "0x045e",
        "pid": "0x028e",
        "vid_pid": "0x045e:0x028e",
        "name": model_meta["name"],
        "vendor": "Pacto Tech",
        "type": "keyboard_encoder",
        "players": int(declaration.get("players") or model_meta["players"]),
        "detected": True,
        "known": True,
        "source": "manual_declaration",
    }
