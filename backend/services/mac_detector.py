"""
MAC address detector for cabinet identification.

Detects the primary network interface MAC address for device registration.
Falls back to placeholder if detection fails.
"""

import logging
import uuid

logger = logging.getLogger(__name__)

# Placeholder MAC when detection fails
FALLBACK_MAC = "00:00:00:00:00:00"


def get_mac_address() -> str:
    """
    Get the MAC address of the primary network interface.
    
    Returns:
        MAC address in colon-separated format (e.g., "AA:BB:CC:DD:EE:FF")
        Returns FALLBACK_MAC ("00:00:00:00:00:00") if detection fails.
    """
    try:
        # uuid.getnode() returns MAC as 48-bit integer
        mac_int = uuid.getnode()
        
        # Check if it's a valid MAC (not a random one)
        # uuid.getnode() sets bit 40 for random MACs
        if (mac_int >> 40) & 1:
            logger.warning("MAC address appears to be randomly generated, using fallback")
            return FALLBACK_MAC
        
        # Convert to colon-separated hex format
        mac_hex = f"{mac_int:012x}"
        mac_formatted = ":".join(mac_hex[i:i+2].upper() for i in range(0, 12, 2))
        
        logger.info(f"Detected MAC address: {mac_formatted}")
        return mac_formatted
        
    except Exception as e:
        logger.error(f"Failed to detect MAC address: {e}")
        return FALLBACK_MAC
