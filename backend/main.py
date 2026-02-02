"""Application entrypoint with strict environment validation."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class EnvironmentSettings(BaseModel):
    """Pydantic-powered environment definition."""

    model_config = ConfigDict(populate_by_name=True)

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., alias="SUPABASE_ANON_KEY")
    supabase_service_key: str = Field(..., alias="SUPABASE_SERVICE_KEY")
    aa_drive_root: str = Field(..., alias="AA_DRIVE_ROOT")
    fastapi_url: Optional[str] = Field(None, alias="FASTAPI_URL")
    port: Optional[int] = Field(8787, alias="PORT")


def _read_env_file() -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not ENV_FILE.exists():
        return data

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _composed_env() -> Dict[str, str]:
    data = _read_env_file()
    # OS env should have priority over .env file
    data.update({key: value for key, value in os.environ.items() if value is not None})
    return data


@lru_cache(maxsize=1)
def get_settings() -> EnvironmentSettings:
    """Return cached settings instance so imports remain lightweight."""
    return EnvironmentSettings(**_composed_env())


def validate_environment_variables() -> EnvironmentSettings:
    """Validate required SUPABASE_* keys and raise immediately if missing."""
    try:
        return get_settings()
    except ValidationError as exc:
        missing_keys = ", ".join(
            err["loc"][0] for err in exc.errors() if err.get("type") == "missing"
        )
        message = (
            "Missing required environment variables "
            f"(ensure SUPABASE_* values are set): {missing_keys}"
        )
        raise RuntimeError(message) from exc


settings: Optional[EnvironmentSettings] = None
if os.getenv("AA_SKIP_ENV_VALIDATION", "0").lower() not in {"1", "true", "yes"}:
    settings = validate_environment_variables()


if os.getenv("AA_SKIP_APP_IMPORT", "0").lower() not in {"1", "true", "yes"}:
    from backend.app import app  # type: ignore  # noqa: WPS433
else:
    app = None  # type: ignore


__all__ = ["app", "EnvironmentSettings", "get_settings", "settings"]
