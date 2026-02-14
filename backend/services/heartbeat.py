"""
Cabinet heartbeat service for Supabase fleet management.

Sends periodic heartbeats to Supabase every 30 seconds to indicate
the cabinet is online and healthy.

All operations are best-effort and non-blocking.
"""

import asyncio
import logging
import os
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

        # Gather system metrics (basic/mock if psutil missing)
        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
        except ImportError:
            cpu = 0.0
            ram = 0.0
        
        payload = {
            "cpu_usage": cpu,
            "memory_usage": ram,
            "mac_address": os.getenv("DEVICE_SERIAL", "unknown")
        }
        
        # Insert into cabinet_heartbeat table (History tracking)
        data = {
            "cabinet_id": device_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "status": "online",
            "payload": payload
        }

        # Use service_role key (admin) to ensure write access if RLS blocks anon
        admin = sb._get_client(admin=True)
        admin.table('cabinet_heartbeat').insert(data).execute()
        
        # Also update the main cabinet table for "quick verify" last_seen
        try:
             admin.table('cabinet').update({
                'last_seen_at': datetime.now(timezone.utc).isoformat(),
                'status': 'online',
                'ip_address': '127.0.0.1' # TODO: Get real IP
            }).eq('cabinet_id', device_id).execute()
        except:
            pass # Ignore second update failure, heartbeat history is priority
        
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
