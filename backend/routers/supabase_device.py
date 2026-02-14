from fastapi import APIRouter, Request
from typing import Any, Dict
from datetime import datetime
import os

router = APIRouter(prefix="/api/supabase", tags=["supabase-device"])

@router.get("/device")
async def get_supabase_device(request: Request) -> Dict[str, Any]:
    """Return device_id and cabinet status from Supabase (best-effort)."""
    try:
        device_id = getattr(request.state, 'device_id', '') or os.getenv('AA_DEVICE_ID', '')
        if not device_id:
            return { 'device_id': '', 'exists': False, 'details': None }

        try:
            from backend.services.supabase_client import get_client as _gc
            sb = _gc()
            admin = None
            try:
                admin = sb._get_client(admin=True)  # type: ignore[attr-defined]
            except Exception:
                admin = None
            if admin is None:
                return { 'device_id': device_id, 'exists': False, 'details': None }

            resp = admin.table('cabinet').select('*').eq('cabinet_id', device_id).limit(1).execute()
            rows = resp.data or []
            if not rows:
                return { 'device_id': device_id, 'exists': False, 'details': None }
            row = rows[0]
            return {
                'device_id': device_id,
                'exists': True,
                'details': {
                    'status': row.get('status'),
                    'version': row.get('version'),
                    'updated_at': row.get('updated_at'),
                    'serial_number': row.get('serial_number'),
                    'device_name': row.get('device_name'),
                    'tenant_id': row.get('tenant_id'),
                }
            }
        except Exception:
            return { 'device_id': device_id, 'exists': False, 'details': None }
    except Exception:
        return { 'device_id': '', 'exists': False, 'details': None }
