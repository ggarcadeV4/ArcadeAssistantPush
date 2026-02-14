from fastapi import HTTPException, Request
from pathlib import Path
from typing import Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)

def load_policies(drive_root: Path) -> Dict[str, Any]:
    """Load policies from .aa/policies.json"""
    policies_path = drive_root / ".aa" / "policies.json"
    if not policies_path.exists():
        return {}

    with open(policies_path) as f:
        return json.load(f)

def is_allowed_file(file_path: Path, drive_root: Path, sanctioned_paths: List[str]) -> bool:
    """Check if file path is within sanctioned areas

    Args:
        file_path: Path to check
        drive_root: Root directory
        sanctioned_paths: List of allowed path prefixes

    Returns:
        True if path is allowed
    """
    try:
        # Make path relative to drive root
        relative_path = file_path.relative_to(drive_root)

        # Normalize path separators to forward slashes for consistent comparison
        # This fixes Windows backslash vs POSIX forward slash mismatches
        relative_str = str(relative_path).replace('\\', '/')

        # Check if it starts with any sanctioned path
        for sanctioned in sanctioned_paths:
            # Normalize sanctioned path too
            sanctioned_normalized = sanctioned.replace('\\', '/')
            if relative_str.startswith(sanctioned_normalized):
                return True

        # Log rejection for debugging
        logger.debug(f"Path rejected: {relative_str} not in sanctioned paths: {sanctioned_paths}")
        return False
    except ValueError as e:
        # Path is not relative to drive_root
        logger.debug(f"Path not relative to drive_root: {file_path} vs {drive_root}")
        return False

def filter_allowed_keys(patch: Dict[str, Any], emulator: str, policies: Dict[str, Any]) -> Dict[str, Any]:
    """Filter patch to only include allowed keys

    Args:
        patch: Dictionary of key-value pairs to apply
        emulator: Emulator name (mame, retroarch, etc.)
        policies: Loaded policies dictionary

    Returns:
        Filtered patch with only allowed keys

    Raises:
        HTTPException: If unknown keys are found
    """
    if emulator not in policies:
        raise HTTPException(
            status_code=400,
            detail=f"No policy defined for emulator: {emulator}"
        )

    emulator_policy = policies[emulator]
    allowed_keys = emulator_policy.get("allowed_keys", [])

    if not allowed_keys:
        raise HTTPException(
            status_code=400,
            detail=f"No allowed keys defined for emulator: {emulator}"
        )

    # Find unknown keys
    unknown_keys = set(patch.keys()) - set(allowed_keys)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown keys not allowed by policy: {list(unknown_keys)}"
        )

    # Return only allowed keys (should be same as input if validation passes)
    return {k: v for k, v in patch.items() if k in allowed_keys}

def require_scope(request: Request, expected_scope: str):
    """Validate that request has the expected x-scope header

    Args:
        request: FastAPI request object
        expected_scope: Expected scope value (config|state|backup)

    Raises:
        HTTPException: If scope is missing or invalid
    """
    scope = request.headers.get("x-scope")

    if not scope:
        raise HTTPException(
            status_code=400,
            detail="Missing required x-scope header. Must be one of: config|state|backup"
        )

    valid_scopes = ["config", "state", "backup"]
    if scope not in valid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid x-scope: {scope}. Must be one of: {valid_scopes}"
        )

    if scope != expected_scope:
        raise HTTPException(
            status_code=400,
            detail=f"Wrong scope: expected '{expected_scope}', got '{scope}'"
        )

def validate_file_extension(file_path: Path, emulator: str, policies: Dict[str, Any]) -> bool:
    """Check if file extension is allowed for the emulator

    Args:
        file_path: Path to validate
        emulator: Emulator name
        policies: Loaded policies

    Returns:
        True if extension is allowed

    Raises:
        HTTPException: If extension is not allowed
    """
    if emulator not in policies:
        raise HTTPException(
            status_code=400,
            detail=f"No policy defined for emulator: {emulator}"
        )

    allowed_types = policies[emulator].get("file_types", [])
    file_ext = file_path.suffix.lstrip(".")

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{file_ext}' not allowed for {emulator}. Allowed: {allowed_types}"
        )

    return True