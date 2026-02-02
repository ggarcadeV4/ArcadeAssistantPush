"""
Cabinet self-registration service for Supabase fleet management.

Handles automatic cabinet registration on startup:
- Detects MAC address
- Generates or loads device_id from A:\.aa\device_id.txt
- Registers with Supabase via auto_register_cabinet RPC
- Checks approval status (informational only, never blocks)

All operations are best-effort and non-blocking.
"""

import os
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from backend.services.mac_detector import get_mac_address

logger = logging.getLogger(__name__)


def get_drive_root() -> Optional[Path]:
    """Get the AA_DRIVE_ROOT path."""
    raw = os.getenv("AA_DRIVE_ROOT", "")
    if not raw:
        return None
    return Path(raw)


def load_device_id() -> str:
    """
    Load or generate the cabinet's permanent device ID.
    
    Priority:
    1. Check A:\.aa\device_id.txt
    2. If missing, generate UUID and save it
    
    Returns:
        Device ID string (UUID format)
    """
    drive_root = get_drive_root()
    
    if drive_root:
        device_id_file = drive_root / ".aa" / "device_id.txt"
        
        # Try to load existing device_id
        if device_id_file.exists():
            try:
                device_id = device_id_file.read_text(encoding="utf-8").strip()
                if device_id:
                    logger.info(f"Loaded device_id from file: {device_id}")
                    return device_id
            except Exception as e:
                logger.warning(f"Failed to read device_id.txt, will regenerate: {e}")
        
        # Generate new device_id
        device_id = str(uuid.uuid4())
        try:
            device_id_file.parent.mkdir(parents=True, exist_ok=True)
            device_id_file.write_text(device_id, encoding="utf-8")
            logger.info(f"Generated new device_id: {device_id}")
        except Exception as e:
            logger.error(f"Failed to save device_id.txt: {e}")
        
        return device_id
    
    # No drive root - generate ephemeral ID
    device_id = str(uuid.uuid4())
    logger.warning(f"No AA_DRIVE_ROOT, using ephemeral device_id: {device_id}")
    return device_id


def auto_register_cabinet() -> Dict[str, Any]:
    """
    Automatically register this cabinet with Supabase.
    
    This should be called once on startup. It:
    1. Gets the MAC address
    2. Loads or generates device_id
    3. Calls Supabase auto_register_cabinet RPC
    4. Checks and logs approval status
    
    Returns:
        Dict with registration result:
        {
            'success': bool,
            'device_id': str,
            'mac': str,
            'status': str,  # 'pending_approval', 'active', 'error', etc.
            'error': Optional[str]
        }
    
    NEVER raises exceptions - all errors are caught and logged.
    """
    result = {
        'success': False,
        'device_id': '',
        'mac': '',
        'status': 'unknown',
        'error': None
    }
    
    try:
        # Step 1: Get MAC address
        mac_address = get_mac_address()
        result['mac'] = mac_address
        logger.info(f"Cabinet MAC address: {mac_address}")
        
        # Step 2: Load or generate device_id
        device_id = load_device_id()
        result['device_id'] = device_id
        
        # Also set in environment for other services
        os.environ['AA_DEVICE_ID'] = device_id
        
        # Step 3: Register/upsert into devices table
        try:
            from backend.services.supabase_client import get_client
            from datetime import datetime, timezone
            
            sb = get_client()
            admin = sb._get_client(admin=True)
            
            # Upsert device record
            serial_number = os.getenv('AA_SERIAL_NUMBER') or os.getenv('DEVICE_SERIAL') or f'AUTO-{device_id[:8]}'
            aa_version = os.getenv('AA_VERSION', '1.0.0')
            
            # Generate cabinet name from serial or device_id
            cabinet_name = os.getenv('DEVICE_NAME', f'Cabinet-{serial_number}')
            
            upsert_payload = {
                'id': device_id,
                'cabinet_id': device_id,  # Required - NOT NULL constraint
                'name': cabinet_name,     # Required - NOT NULL constraint
                'serial': serial_number,
                'status': 'online',
                'version_arcade_assistant': aa_version,
                'last_seen': datetime.now(timezone.utc).isoformat(),
                'mac_address': mac_address,
            }
            
            admin.table('cabinet').upsert(upsert_payload, on_conflict='id').execute()
            logger.info(f"Device registered/updated in Supabase: {device_id}")
            result['success'] = True
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Supabase registration failed (non-fatal): {error_msg}")
            result['error'] = error_msg
            # Continue - don't block startup
        
        # Step 4: Check device status (informational only)
        try:
            from backend.services.supabase_client import get_client
            sb = get_client()
            admin = sb._get_client(admin=True)
            
            status_result = admin.table('cabinet').select('status').eq('id', device_id).single().execute()
            
            if status_result.data:
                device_status = status_result.data.get('status', 'unknown')
                result['status'] = device_status
                logger.info(f"Device status: {device_status}")
            else:
                result['status'] = 'not_found'
                logger.info("Device not found in Supabase (may be first registration)")
                
        except Exception as e:
            logger.warning(f"Failed to check device status (non-fatal): {e}")
            result['status'] = 'check_failed'
        
        return result
        
    except Exception as e:
        logger.error(f"Cabinet registration failed unexpectedly: {e}")
        result['error'] = str(e)
        return result


async def register_cabinet_async() -> Dict[str, Any]:
    """
    Async wrapper for cabinet registration.
    Runs registration in a thread to avoid blocking the event loop.
    """
    import asyncio
    return await asyncio.to_thread(auto_register_cabinet)
