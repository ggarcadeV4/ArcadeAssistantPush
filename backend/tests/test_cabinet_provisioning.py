import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import system
from backend.services.cabinet_identity import load_cabinet_identity, provision_device_id
from backend.startup_manager import initialize_app_state

PLACEHOLDER_DEVICE_ID = '00000000-0000-0000-0000-000000000001'


def _configure_env(monkeypatch, drive_root: Path) -> None:
    monkeypatch.setenv('AA_DRIVE_ROOT', str(drive_root))
    monkeypatch.setenv('AA_BACKUP_ON_WRITE', 'true')
    monkeypatch.setenv('AA_DRY_RUN_DEFAULT', 'false')
    monkeypatch.setattr(uuid, 'getnode', lambda: 0xAABBCCDDEEFF)
    monkeypatch.setenv('AA_ENV_FILE', str(drive_root / '.env'))


def test_initialize_app_state_bootstraps_identity_and_controls(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    (tmp_path / '.env').write_text(f'AA_DEVICE_ID={PLACEHOLDER_DEVICE_ID}\n', encoding='utf-8')
    app = FastAPI()

    asyncio.run(initialize_app_state(app))

    device_id_path = tmp_path / '.aa' / 'device_id.txt'
    cabinet_manifest_path = tmp_path / '.aa' / 'cabinet_manifest.json'
    controls_path = tmp_path / 'config' / 'mappings' / 'controls.json'
    manifest_path = tmp_path / '.aa' / 'manifest.json'

    assert manifest_path.exists()
    assert device_id_path.exists()
    assert cabinet_manifest_path.exists()
    assert controls_path.exists()

    device_id = device_id_path.read_text(encoding='utf-8').strip()
    assert device_id

    cabinet_manifest = json.loads(cabinet_manifest_path.read_text(encoding='utf-8'))
    assert cabinet_manifest['device_id'] == device_id
    assert cabinet_manifest['device_name'] == 'Arcade Cabinet'
    assert cabinet_manifest['device_serial'] == 'UNPROVISIONED'
    assert cabinet_manifest['mac_address'] == 'aa:bb:cc:dd:ee:ff'

    controls = json.loads(controls_path.read_text(encoding='utf-8'))
    assert controls['mappings'] == {}
    assert getattr(app.state, 'cabinet_identity', {})['device_id'] == device_id
    assert getattr(app.state, 'cabinet_identity', {})['mac_address'] == 'aa:bb:cc:dd:ee:ff'
    assert os.environ['AA_DEVICE_ID'] == device_id


def test_device_id_file_precedence_over_env(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv('AA_DEVICE_ID', 'env-device-id')

    aa_root = tmp_path / '.aa'
    aa_root.mkdir(parents=True)
    (aa_root / 'device_id.txt').write_text('file-device-id\n', encoding='utf-8')
    (aa_root / 'cabinet_manifest.json').write_text(json.dumps({'device_id': 'manifest-device-id'}), encoding='utf-8')

    identity = load_cabinet_identity(tmp_path)
    assert identity.device_id == 'file-device-id'
    assert identity.source == 'device_id_txt'
    assert identity.mac_address == 'aa:bb:cc:dd:ee:ff'


def test_provisioning_status_endpoint_reports_bootstrap_state(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    (tmp_path / '.env').write_text(f'AA_DEVICE_ID={PLACEHOLDER_DEVICE_ID}\n', encoding='utf-8')
    app = FastAPI()
    app.include_router(system.local_router)

    asyncio.run(initialize_app_state(app))

    client = TestClient(app)
    response = client.get('/api/local/system/provisioning_status')
    assert response.status_code == 200

    payload = response.json()
    assert payload['success'] is True
    assert payload['manifest_present'] is True
    assert payload['identity']['files_present']['device_id_txt'] is True
    assert payload['identity']['files_present']['controls_json'] is True
    assert payload['identity']['mac_address'] == 'aa:bb:cc:dd:ee:ff'


def test_provision_device_id_generates_when_missing(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    env_path = tmp_path / '.env'
    env_path.write_text('AA_DRIVE_ROOT=A:\\\n', encoding='utf-8')

    device_id = provision_device_id(tmp_path)

    assert uuid.UUID(device_id).version == 4
    assert (tmp_path / '.aa' / 'device_id.txt').read_text(encoding='utf-8').strip() == device_id
    assert f'AA_DEVICE_ID={device_id}' in env_path.read_text(encoding='utf-8')
    assert os.environ['AA_DEVICE_ID'] == device_id


def test_provision_device_id_replaces_placeholder(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    env_path = tmp_path / '.env'
    env_path.write_text(f'AA_DEVICE_ID={PLACEHOLDER_DEVICE_ID}\n', encoding='utf-8')
    aa_root = tmp_path / '.aa'
    aa_root.mkdir(parents=True)
    (aa_root / 'device_id.txt').write_text(f'{PLACEHOLDER_DEVICE_ID}\n', encoding='utf-8')

    device_id = provision_device_id(tmp_path)

    assert device_id != PLACEHOLDER_DEVICE_ID
    assert uuid.UUID(device_id).version == 4
    assert (aa_root / 'device_id.txt').read_text(encoding='utf-8').strip() == device_id
    assert f'AA_DEVICE_ID={device_id}' in env_path.read_text(encoding='utf-8')
    assert os.environ['AA_DEVICE_ID'] == device_id


def test_provision_device_id_keeps_existing_uuid(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    env_path = tmp_path / '.env'
    existing_device_id = str(uuid.uuid4())
    env_path.write_text(f'AA_DEVICE_ID={PLACEHOLDER_DEVICE_ID}\n', encoding='utf-8')
    aa_root = tmp_path / '.aa'
    aa_root.mkdir(parents=True)
    (aa_root / 'device_id.txt').write_text(f'{existing_device_id}\n', encoding='utf-8')

    device_id = provision_device_id(tmp_path)

    assert device_id == existing_device_id
    assert (aa_root / 'device_id.txt').read_text(encoding='utf-8').strip() == existing_device_id
    assert f'AA_DEVICE_ID={existing_device_id}' in env_path.read_text(encoding='utf-8')
    assert os.environ['AA_DEVICE_ID'] == existing_device_id
