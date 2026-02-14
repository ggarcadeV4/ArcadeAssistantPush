"""
Supabase health check router for monitoring connection status.
Provides endpoints to verify Supabase connectivity without exposing secrets.
"""

import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

# Import the supabase client
try:
    from backend.services.supabase_client import health_check as supabase_health_check
except ImportError:
    # Fallback if module structure differs
    try:
        from services.supabase_client import health_check as supabase_health_check
    except ImportError:
        supabase_health_check = None

logger = logging.getLogger(__name__)

# Create router with prefix
router = APIRouter(prefix="/api/supabase", tags=["supabase"])


# Pydantic response models
class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str
    supabase: bool
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class StatusResponse(BaseModel):
    """Response model for configuration status endpoint."""
    configured: bool
    url_set: bool
    key_set: bool
    details: Optional[Dict[str, str]] = None


@router.get("/health", response_model=HealthCheckResponse)
async def check_supabase_health() -> HealthCheckResponse:
    """
    Check Supabase connection health.

    Returns:
        - 200: Successfully connected to Supabase
        - 503: Failed to connect to Supabase
    """
    try:
        # Check if supabase_client module is available
        if supabase_health_check is None:
            logger.error("Supabase client module not found")
            return HealthCheckResponse(
                status="disconnected",
                supabase=False,
                error="Supabase client module not available",
                details={"module_loaded": False}
            )

        # Attempt health check
        logger.info("Performing Supabase health check")
        health_result = supabase_health_check()

        # Check if health check returned successful result
        if health_result and isinstance(health_result, dict):
            is_healthy = health_result.get("connected", False)

            if is_healthy:
                logger.info("Supabase health check succeeded")
                return HealthCheckResponse(
                    status="connected",
                    supabase=True,
                    details={
                        "timestamp": health_result.get("timestamp"),
                        "latency_ms": health_result.get("latency_ms")
                    }
                )
            else:
                error_msg = health_result.get("error", "Connection failed")
                logger.warning(f"Supabase health check failed: {error_msg}")
                raise HTTPException(
                    status_code=503,
                    detail={
                        "status": "disconnected",
                        "supabase": False,
                        "error": error_msg,
                        "details": health_result.get("details")
                    }
                )

        # Handle unexpected response format
        logger.error(f"Unexpected health check response: {health_result}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "disconnected",
                "supabase": False,
                "error": "Invalid health check response format"
            }
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ImportError as e:
        # Handle import errors specifically
        logger.error(f"Import error during health check: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "disconnected",
                "supabase": False,
                "error": "Supabase dependencies not installed",
                "details": {"import_error": str(e)}
            }
        )
    except ConnectionError as e:
        # Handle connection errors
        logger.error(f"Connection error during health check: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "disconnected",
                "supabase": False,
                "error": "Failed to connect to Supabase",
                "details": {"connection_error": str(e)}
            }
        )
    except TimeoutError as e:
        # Handle timeout errors
        logger.error(f"Timeout during health check: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "disconnected",
                "supabase": False,
                "error": "Supabase connection timeout",
                "details": {"timeout": True}
            }
        )
    except Exception as e:
        # Catch all other exceptions
        logger.error(f"Unexpected error during health check: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "disconnected",
                "supabase": False,
                "error": "Unexpected error during health check",
                "details": {"exception": str(type(e).__name__)}
            }
        )


@router.get("/status", response_model=StatusResponse)
async def check_supabase_status() -> StatusResponse:
    """
    Check Supabase configuration status without exposing secrets.

    Returns configuration presence, NOT actual values.
    """
    try:
        # Check environment variables without exposing values
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_ANON_KEY", "")

        # Alternative key names that might be used
        if not supabase_key:
            supabase_key = os.getenv("SUPABASE_KEY", "")
        if not supabase_key:
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

        url_set = bool(supabase_url and supabase_url.strip())
        key_set = bool(supabase_key and supabase_key.strip())
        configured = url_set and key_set

        # Validate URL format without exposing it
        url_valid = False
        if url_set:
            url_valid = (
                supabase_url.startswith("https://") and
                ".supabase.co" in supabase_url
            )

        # Build response
        response = StatusResponse(
            configured=configured,
            url_set=url_set,
            key_set=key_set,
            details={
                "environment": os.getenv("NODE_ENV", "production"),
                "url_valid": str(url_valid) if url_set else "not_set",
                "key_type": "anon" if os.getenv("SUPABASE_ANON_KEY") else "service" if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "unknown"
            }
        )

        logger.info(f"Supabase status check: configured={configured}, url_set={url_set}, key_set={key_set}")
        return response

    except Exception as e:
        logger.error(f"Error checking Supabase status: {e}", exc_info=True)
        # Return safe default values on error
        return StatusResponse(
            configured=False,
            url_set=False,
            key_set=False,
            details={"error": "Failed to check configuration"}
        )


@router.get("/ping")
async def ping_supabase() -> Dict[str, Any]:
    """
    Simple ping endpoint to verify router is loaded.

    This does NOT test Supabase connection, just confirms the router is mounted.
    """
    return {
        "message": "Supabase router is active",
        "endpoints": [
            "/api/supabase/health - Check connection health",
            "/api/supabase/status - Check configuration status",
            "/api/supabase/ping - Verify router is loaded"
        ]
    }