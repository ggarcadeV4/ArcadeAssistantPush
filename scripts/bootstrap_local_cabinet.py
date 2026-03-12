from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.cabinet_identity import ensure_local_identity
from backend.startup_manager import _bootstrap_manifest


def load_env_file() -> None:
    env_file = PROJECT_ROOT / '.env'
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description='Bootstrap local cabinet identity and clone-safe config files.')
    parser.add_argument('--drive-root', dest='drive_root', default=os.getenv('AA_DRIVE_ROOT', ''), help='Cabinet drive root (for example A:\\)')
    args = parser.parse_args()

    load_env_file()

    raw_drive_root = (args.drive_root or '').strip()
    if not raw_drive_root:
        print('ERROR: AA_DRIVE_ROOT is not set and --drive-root was not provided.')
        return 1

    drive_root = Path(raw_drive_root)
    if not drive_root.exists():
        print(f'ERROR: Drive root does not exist: {drive_root}')
        return 1

    manifest_path = drive_root / '.aa' / 'manifest.json'
    if not manifest_path.exists():
        _bootstrap_manifest(drive_root, raw_drive_root)

    identity = ensure_local_identity(drive_root)
    print(f'BOOTSTRAP_DEVICE_ID={identity.device_id}')
    print(f'BOOTSTRAP_DEVICE_NAME={identity.device_name}')
    print(f'BOOTSTRAP_DEVICE_SERIAL={identity.device_serial}')
    print(f'BOOTSTRAP_AUTO_GENERATED={str(identity.auto_generated).lower()}')
    print(f'BOOTSTRAP_CONTROLS_PATH={identity.controls_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
