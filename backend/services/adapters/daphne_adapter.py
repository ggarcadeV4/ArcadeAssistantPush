"""Daphne Adapter - delegates to Hypseus adapter.

Daphne routing is handled by hypseus_adapter via launcher_registry aliasing.
This module exists only as documentation and compatibility for direct imports.
"""

from .hypseus_adapter import can_handle, is_enabled, launch, resolve