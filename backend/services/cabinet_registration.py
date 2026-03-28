"""
Cabinet self-registration service for Supabase fleet management.

Handles automatic cabinet registration on startup:
- Loads or provisions device identity under A:\.aa
- Registers with Supabase via upsert
- Checks approval status (informational only, never blocks)

All operations are best-effort and non-blocking.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from backend.services.cabinet_identity import ensure_local_identity

logger = logging.getLogger(__name__)


def get_drive_root() -> Optional[Path]:
    raw = os.getenv("AA_DRIVE_ROOT", "")
    if not raw:
        return None
    return Path(raw)


def load_device_identity() -> Dict[str, str]:
    drive_root = get_drive_root()
    identity = ensure_local_identity(drive_root)
    return {
        "device_id": identity.device_id,
        "device_name": identity.device_name,
        "device_serial": identity.device_serial,
        "mac_address": identity.mac_address,
    }


def load_device_id() -> str:
    """Backward-compatible helper used by heartbeat startup."""
    return load_device_identity().get("device_id", "")


def auto_register_cabinet() -> Dict[str, Any]:
    result = {
        'success': False,
        'device_id': '',
        'mac': '',
        'status': 'unknown',
        'error': None
    }

    try:
        identity = load_device_identity()
        device_id = identity['device_id']
        mac_address = identity.get('mac_address', '')
        result['mac'] = mac_address
        result['device_id'] = device_id
        os.environ['AA_DEVICE_ID'] = device_id

        logger.info("Cabinet MAC address: %s", mac_address or '<unavailable>')

        try:
            from backend.services.supabase_client import get_client
            from datetime import datetime, timezone

            sb = get_client()
            admin = sb._get_client(admin=True)

            serial_number = identity['device_serial']
            aa_version = os.getenv('AA_VERSION', '1.0.0')
            cabinet_name = identity['device_name']

            upsert_payload = {
                'id': device_id,
                'cabinet_id': device_id,
                'name': cabinet_name,
                'serial': serial_number,
                'status': 'online',
                'version_arcade_assistant': aa_version,
                'last_seen': datetime.now(timezone.utc).isoformat(),
                'mac_address': mac_address,
            }

            admin.table('cabinet').upsert(upsert_payload, on_conflict='id').execute()
            logger.info("Device registered/updated in Supabase: %s", device_id)
            result['success'] = True

        except Exception as e:
            error_msg = str(e)
            logger.warning("Supabase registration failed (non-fatal): %s", error_msg)
            result['error'] = error_msg

        try:
            from backend.services.supabase_client import get_client
            sb = get_client()
            admin = sb._get_client(admin=True)

            status_result = admin.table('cabinet').select('status').eq('id', device_id).single().execute()

            if status_result.data:
                device_status = status_result.data.get('status', 'unknown')
                result['status'] = device_status
                logger.info("Device status: %s", device_status)
            else:
                result['status'] = 'not_found'
                logger.info("Device not found in Supabase (may be first registration)")

        except Exception as e:
            logger.warning("Failed to check device status (non-fatal): %s", e)
            result['status'] = 'check_failed'

        return result

    except Exception as e:
        logger.error("Cabinet registration failed unexpectedly: %s", e)
        result['error'] = str(e)
        return result


async def register_cabinet_async() -> Dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(auto_register_cabinet)
