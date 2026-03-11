"""
Cabinet heartbeat service for Supabase fleet management.

Sends periodic heartbeats to Supabase every 30 seconds to indicate
the cabinet is online and healthy.

All operations are best-effort and non-blocking.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from backend.services.cabinet_registration import load_device_id

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30


async def send_heartbeat() -> bool:
    """
    Send a single heartbeat to Supabase by updating devices.last_seen.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        device_id = load_device_id()
        if not device_id:
            logger.warning("No device_id available for heartbeat")
            return False
        
        from backend.services.supabase_client import get_client
        sb = get_client()

        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
        except ImportError:
            cpu = 0.0
            ram = 0.0

        heartbeat_time = datetime.now(timezone.utc).isoformat()
        payload = {
            "cpu_usage": cpu,
            "memory_usage": ram,
            "mac_address": os.getenv("DEVICE_SERIAL", "unknown"),
        }
        try:
            usage = shutil.disk_usage(os.getenv("AA_DRIVE_ROOT", os.getcwd()))
            disk_usage = round((usage.used / usage.total) * 100, 2)
            payload["disk_usage"] = disk_usage
        except Exception:
            disk_usage = None
        version = os.getenv("AA_VERSION")
        if version:
            payload["version"] = version

        data = {
            "cabinet_id": device_id,
            "observed_at": heartbeat_time,
            "status": "online",
            "cpu_usage": cpu,
            "memory_usage": ram,
            "payload": payload,
        }
        if disk_usage is not None:
            data["disk_usage"] = disk_usage
        if version:
            data["version"] = version

        admin = sb._get_client(admin=True)
        admin.table('cabinet_heartbeat').insert(data).execute()

        try:
            admin.table('cabinet').update({
                'last_seen': heartbeat_time,
                'status': 'online',
                'ip_address': '127.0.0.1'
            }).eq('cabinet_id', device_id).execute()
        except Exception:
            try:
                admin.table('cabinet').update({
                    'last_seen_at': heartbeat_time,
                    'status': 'online',
                    'ip_address': '127.0.0.1'
                }).eq('cabinet_id', device_id).execute()
            except Exception:
                pass
        
        logger.debug(f"Heartbeat sent for device {device_id}")
        return True
        
    except Exception as e:
        logger.warning(f"Heartbeat failed: {e}")
        return False


async def send_heartbeat_loop() -> None:
    """
    Send heartbeat to Supabase every 30 seconds.
    
    This coroutine runs indefinitely and should be started as a task
    during app lifespan startup.
    
    Errors are caught and logged but never propagate - the loop
    continues regardless of individual heartbeat failures.
    """
    logger.info(f"Starting heartbeat loop (interval: {HEARTBEAT_INTERVAL}s)")
    
    while True:
        try:
            await send_heartbeat()
        except Exception as e:
            logger.warning(f"Heartbeat loop error: {e}")
        
        await asyncio.sleep(HEARTBEAT_INTERVAL)


def start_heartbeat_task() -> asyncio.Task:
    """
    Create and return the heartbeat loop task.
    
    Call this from app lifespan startup to start the heartbeat service.
    
    Returns:
        The asyncio Task running the heartbeat loop.
    """
    return asyncio.create_task(send_heartbeat_loop())


