from __future__ import annotations

import json
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

DEVICE_ID_RELATIVE = Path(".aa/device_id.txt")
CABINET_MANIFEST_RELATIVE = Path(".aa/cabinet_manifest.json")
CONTROLS_RELATIVE = Path("config/mappings/controls.json")
KNOWLEDGE_BASE_RELATIVE = Path(".aa/state/knowledge_base")


@dataclass
class CabinetProvisioningResult:
    device_id: str
    device_name: str
    device_serial: str
    mac_address: str
    source: str
    auto_generated: bool
    device_id_file_present: bool
    cabinet_manifest_present: bool
    controls_file_present: bool
    device_id_path: Optional[Path]
    cabinet_manifest_path: Optional[Path]
    controls_path: Optional[Path]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_serial": self.device_serial,
            "mac_address": self.mac_address,
            "source": self.source,
            "auto_generated": self.auto_generated,
            "files_present": {
                "device_id_txt": self.device_id_file_present,
                "cabinet_manifest_json": self.cabinet_manifest_present,
                "controls_json": self.controls_file_present,
            },
            "paths": {
                "device_id_txt": str(self.device_id_path) if self.device_id_path else None,
                "cabinet_manifest_json": str(self.cabinet_manifest_path) if self.cabinet_manifest_path else None,
                "controls_json": str(self.controls_path) if self.controls_path else None,
            },
        }


def _hostname_fallback() -> str:
    try:
        return socket.gethostname().strip()
    except Exception:
        return ""


def _detect_mac_address() -> str:
    """Auto-detect the primary network adapter MAC address."""
    try:
        import uuid as _uuid

        raw = _uuid.getnode()
        mac_hex = f"{raw:012x}"
        return ":".join(mac_hex[i:i + 2] for i in range(0, 12, 2))
    except Exception:
        return ""


def _default_device_name(env: Optional[Dict[str, str]] = None) -> str:
    env = env or os.environ
    configured = (env.get("DEVICE_NAME") or "").strip()
    if configured:
        return configured
    hostname = _hostname_fallback()
    return hostname or "Arcade Cabinet"


def _default_device_serial(env: Optional[Dict[str, str]] = None) -> str:
    env = env or os.environ
    configured = (env.get("DEVICE_SERIAL") or env.get("AA_SERIAL_NUMBER") or "").strip()
    if configured:
        return configured
    hostname = _hostname_fallback()
    return f"{hostname}-UNPROVISIONED" if hostname else "UNPROVISIONED"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_device_id(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _identity_paths(drive_root: Optional[Path]) -> Dict[str, Optional[Path]]:
    if not drive_root:
        return {
            "device_id": None,
            "cabinet_manifest": None,
            "controls": None,
        }
    root = Path(drive_root)
    return {
        "device_id": root / DEVICE_ID_RELATIVE,
        "cabinet_manifest": root / CABINET_MANIFEST_RELATIVE,
        "controls": root / CONTROLS_RELATIVE,
    }


def build_controls_skeleton() -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "comment": "Bootstrap skeleton for cloned cabinets. Populate via Controller Chuck or Console Wizard.",
        "version": "1.0",
        "created_at": now,
        "last_modified": now,
        "modified_by": "system_bootstrap",
        "board": {
            "name": "Unprovisioned Cabinet",
            "detected": False,
            "modes": {},
        },
        "mappings": {},
    }


def load_cabinet_identity(
    drive_root: Optional[Path],
    *,
    env: Optional[Dict[str, str]] = None,
) -> CabinetProvisioningResult:
    env = env or os.environ
    paths = _identity_paths(drive_root)
    device_id_path = paths["device_id"]
    cabinet_manifest_path = paths["cabinet_manifest"]
    controls_path = paths["controls"]

    device_id = ""
    source = "unresolved"

    if device_id_path and device_id_path.exists():
        device_id = _read_device_id(device_id_path)
        if device_id:
            source = "device_id_txt"

    manifest_payload: Dict[str, Any] = {}
    if not device_id and cabinet_manifest_path and cabinet_manifest_path.exists():
        manifest_payload = _read_json(cabinet_manifest_path)
        device_id = str(
            manifest_payload.get("device_id")
            or manifest_payload.get("id")
            or ""
        ).strip()
        if device_id:
            source = "cabinet_manifest"

    if not manifest_payload and cabinet_manifest_path and cabinet_manifest_path.exists():
        manifest_payload = _read_json(cabinet_manifest_path)

    if not device_id:
        device_id = (env.get("AA_DEVICE_ID") or "").strip()
        if device_id:
            source = "env"

    device_name = str(
        manifest_payload.get("device_name")
        or manifest_payload.get("name")
        or _default_device_name(env)
    ).strip() or "Arcade Cabinet"
    device_serial = str(
        manifest_payload.get("device_serial")
        or manifest_payload.get("serial")
        or _default_device_serial(env)
    ).strip() or "UNPROVISIONED"
    mac_address = str(
        manifest_payload.get("mac_address")
        or _detect_mac_address()
    ).strip().lower()

    return CabinetProvisioningResult(
        device_id=device_id,
        device_name=device_name,
        device_serial=device_serial,
        mac_address=mac_address,
        source=source,
        auto_generated=False,
        device_id_file_present=bool(device_id_path and device_id_path.exists()),
        cabinet_manifest_present=bool(cabinet_manifest_path and cabinet_manifest_path.exists()),
        controls_file_present=bool(controls_path and controls_path.exists()),
        device_id_path=device_id_path,
        cabinet_manifest_path=cabinet_manifest_path,
        controls_path=controls_path,
    )


def ensure_knowledge_base_dir(drive_root: Path) -> Path:
    knowledge_dir = Path(drive_root) / KNOWLEDGE_BASE_RELATIVE
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    return knowledge_dir


def ensure_controls_json(drive_root: Path) -> Path:
    controls_path = Path(drive_root) / CONTROLS_RELATIVE
    controls_path.parent.mkdir(parents=True, exist_ok=True)
    if not controls_path.exists():
        controls_path.write_text(
            json.dumps(build_controls_skeleton(), indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Bootstrapped controls.json at %s", controls_path)
    return controls_path


def ensure_local_identity(
    drive_root: Optional[Path],
    *,
    env: Optional[Dict[str, str]] = None,
) -> CabinetProvisioningResult:
    env = env or os.environ
    identity = load_cabinet_identity(drive_root, env=env)

    if not drive_root:
        return identity

    root = Path(drive_root)
    aa_root = root / ".aa"
    aa_root.mkdir(parents=True, exist_ok=True)

    auto_generated = False
    if not identity.device_id:
        identity.device_id = str(uuid.uuid4())
        identity.source = "generated"
        auto_generated = True

    identity.mac_address = (identity.mac_address or _detect_mac_address()).strip().lower()

    if identity.device_id_path:
        identity.device_id_path.parent.mkdir(parents=True, exist_ok=True)
        current_device_id = _read_device_id(identity.device_id_path) if identity.device_id_path.exists() else ""
        if current_device_id != identity.device_id:
            identity.device_id_path.write_text(identity.device_id + "\n", encoding="utf-8")
        identity.device_id_file_present = True

    manifest_payload: Dict[str, Any] = {}
    if identity.cabinet_manifest_path and identity.cabinet_manifest_path.exists():
        manifest_payload = _read_json(identity.cabinet_manifest_path)

    manifest_payload.update(
        {
            "device_id": identity.device_id,
            "device_name": identity.device_name or _default_device_name(env),
            "device_serial": identity.device_serial or _default_device_serial(env),
            "mac_address": identity.mac_address,
            "identity_source": identity.source,
            "provisioned_at": manifest_payload.get("provisioned_at") or datetime.now(timezone.utc).isoformat(),
            "emulator_root": str(root.drive + "\\Emulators") if root.drive else str(root / "Emulators"),
            "notes": "Golden image assumes emulator installs live under A:\\Emulators and sanctioned_paths align to that layout.",
        }
    )

    if identity.cabinet_manifest_path:
        identity.cabinet_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        identity.cabinet_manifest_path.write_text(
            json.dumps(manifest_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        identity.cabinet_manifest_present = True

    ensure_controls_json(root)
    ensure_knowledge_base_dir(root)

    identity = load_cabinet_identity(root, env=env)
    identity.auto_generated = auto_generated
    os.environ["AA_DEVICE_ID"] = identity.device_id
    return identity
