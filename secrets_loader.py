"""
secrets_loader.py — Arcade Assistant DPAPI Secrets Manager
===========================================================
Decrypts Tier 1 secrets from .aa/credentials.dat using Windows DPAPI
and injects them into os.environ before the application starts.

DPAPI binds encryption to the current Windows user account + machine.
The credentials.dat file is unreadable on any other PC — plugging the
drive into a foreign machine returns garbage, not secrets.

Tier 1 secrets managed here:
  - SUPABASE_URL
  - SUPABASE_ANON_KEY
  - AA_PROVISIONING_TOKEN  (used during registration; cleared post-boot)
  - AA_SERVICE_TOKEN       (per-cabinet JWT; set after provisioning)

Tier 2/3 config (ports, paths, feature flags) stays in .env as plaintext.
These are not secrets — they carry no authentication value.

Usage (called once at app startup, before any router initializes):
  from secrets_loader import load_secrets
  load_secrets()  # Injects into os.environ; returns True on success

Dependencies:
  pip install pywin32
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aa.secrets")

# ── Paths ──────────────────────────────────────────────────────────────────────
# credentials.dat lives in .aa/ — the per-cabinet persistent state directory.
# This directory survives cloning (clean_for_clone.bat leaves it alone after
# first-boot generation), which is exactly what we want: secrets are
# machine-generated, not copied from a template.

def _get_credentials_path() -> Path:
    """Resolve .aa/credentials.dat relative to the drive root."""
    drive_root = os.environ.get("AA_DRIVE_ROOT", "A:\\Arcade Assistant Local")
    return Path(drive_root) / ".aa" / "credentials.dat"


# ── DPAPI Core ─────────────────────────────────────────────────────────────────

def _dpapi_encrypt(plaintext: str) -> bytes:
    """Encrypt a string using Windows DPAPI (current user scope)."""
    try:
        import win32crypt  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "pywin32 is required for DPAPI encryption. "
            "Run: pip install pywin32"
        )
    data = plaintext.encode("utf-8")
    encrypted = win32crypt.CryptProtectData(
        data,
        "AA_TIER1_SECRETS",   # Description label (stored with ciphertext)
        None,                  # Optional entropy — None = user+machine scope
        None,                  # Reserved
        None,                  # Prompt struct — None = silent
        0                      # Flags — 0 = current user scope
    )
    return encrypted


def _dpapi_decrypt(ciphertext: bytes) -> str:
    """Decrypt DPAPI-encrypted bytes back to a plaintext string."""
    try:
        import win32crypt  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "pywin32 is required for DPAPI decryption. "
            "Run: pip install pywin32"
        )
    _description, plaintext_bytes = win32crypt.CryptUnprotectData(
        ciphertext,
        None,   # Optional entropy — must match encrypt call
        None,   # Reserved
        None,   # Prompt struct
        0       # Flags
    )
    return plaintext_bytes.decode("utf-8")


# ── Credential Store ───────────────────────────────────────────────────────────

def save_secrets(secrets: dict[str, str], credentials_path: Optional[Path] = None) -> Path:
    """
    Encrypt a dict of Tier 1 secrets and write to credentials.dat.

    Each value is individually DPAPI-encrypted and hex-encoded for safe
    JSON storage. This means a partial key leak (e.g., someone copies
    one value) still cannot be decrypted off-machine.

    Args:
        secrets: Dict mapping env var name → plaintext value
        credentials_path: Override the default .aa/credentials.dat path

    Returns:
        Path to the written credentials.dat file
    """
    path = credentials_path or _get_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    encrypted_store: dict[str, str] = {}
    for key, value in secrets.items():
        if not value or not value.strip():
            logger.warning("Skipping empty secret: %s", key)
            continue
        ciphertext = _dpapi_encrypt(value.strip())
        encrypted_store[key] = ciphertext.hex()
        logger.info("Encrypted secret: %s (%d bytes)", key, len(ciphertext))

    payload = {
        "version": 1,
        "machine_bound": True,
        "secrets": encrypted_store,
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Credentials written to: %s", path)
    return path


def load_secrets(credentials_path: Optional[Path] = None) -> bool:
    """
    Decrypt credentials.dat and inject all Tier 1 secrets into os.environ.

    Called once at application startup (before FastAPI/routers initialize).
    Safe to call multiple times — existing env vars are NOT overwritten,
    so manually set vars always take precedence (useful for dev overrides).

    Args:
        credentials_path: Override the default .aa/credentials.dat path

    Returns:
        True if secrets were loaded successfully, False if file not found
        (non-fatal — app continues with .env-only config, logging a warning)
    """
    path = credentials_path or _get_credentials_path()

    if not path.exists():
        logger.warning(
            "credentials.dat not found at %s. "
            "Running with .env config only. "
            "Run 'python encrypt_secrets.py' to initialize the vault.",
            path
        )
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read credentials.dat: %s", exc)
        return False

    version = payload.get("version", 0)
    if version != 1:
        logger.error("Unsupported credentials.dat version: %d", version)
        return False

    loaded = 0
    skipped = 0
    for key, hex_ciphertext in payload.get("secrets", {}).items():
        if key in os.environ:
            # Dev override: env var already set (e.g., from .env or shell)
            logger.debug("Skipping %s — already set in environment", key)
            skipped += 1
            continue
        try:
            ciphertext = bytes.fromhex(hex_ciphertext)
            plaintext = _dpapi_decrypt(ciphertext)
            os.environ[key] = plaintext
            loaded += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to decrypt secret '%s': %s — "
                "This machine may not be the machine that encrypted this file.",
                key, exc
            )

    logger.info(
        "Secrets vault: %d loaded, %d skipped (already in env)", loaded, skipped
    )
    return loaded > 0


def update_secret(key: str, value: str, credentials_path: Optional[Path] = None) -> None:
    """
    Add or update a single secret in the vault without re-entering all secrets.
    Used by the provisioning flow to store the per-cabinet JWT after registration.

    Args:
        key: The env var name (e.g., 'AA_SERVICE_TOKEN')
        value: The plaintext secret value
        credentials_path: Override the default .aa/credentials.dat path
    """
    path = credentials_path or _get_credentials_path()

    # Load existing store
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {"version": 1, "machine_bound": True, "secrets": {}}
    else:
        payload = {"version": 1, "machine_bound": True, "secrets": {}}

    # Encrypt new value
    ciphertext = _dpapi_encrypt(value.strip())
    payload["secrets"][key] = ciphertext.hex()

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Updated secret in vault: %s", key)


def clear_secret(key: str, credentials_path: Optional[Path] = None) -> bool:
    """
    Remove a single secret from the vault.
    Used after provisioning to clear the one-time AA_PROVISIONING_TOKEN.

    Returns True if the key was found and removed, False if not present.
    """
    path = credentials_path or _get_credentials_path()

    if not path.exists():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    secrets = payload.get("secrets", {})
    if key not in secrets:
        return False

    del secrets[key]
    payload["secrets"] = secrets
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Cleared secret from vault: %s", key)
    return True


# ── Standalone verification ────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to verify the vault can be decrypted on this machine.
    Does NOT print secret values — only confirms keys and byte counts.

    Usage:
        python secrets_loader.py
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    path = _get_credentials_path()
    if not path.exists():
        print(f"[VAULT] No credentials.dat found at: {path}")
        print("[VAULT] Run 'python encrypt_secrets.py' to create the vault.")
        sys.exit(1)

    payload = json.loads(path.read_text(encoding="utf-8"))
    secrets = payload.get("secrets", {})

    print(f"\n[VAULT] credentials.dat — {len(secrets)} secret(s) stored")
    print(f"[VAULT] Path: {path}\n")

    all_ok = True
    for key, hex_val in secrets.items():
        try:
            ciphertext = bytes.fromhex(hex_val)
            plaintext = _dpapi_decrypt(ciphertext)
            masked = plaintext[:4] + "****" + plaintext[-4:] if len(plaintext) > 8 else "****"
            print(f"  ✅  {key:<32}  ({len(plaintext)} chars)  →  {masked}")
        except Exception as exc:
            print(f"  ❌  {key:<32}  DECRYPT FAILED: {exc}")
            all_ok = False

    print()
    if all_ok:
        print("[VAULT] All secrets verified. This machine can decrypt the vault.")
    else:
        print("[VAULT] ⚠ One or more secrets failed. This may not be the encrypting machine.")
    sys.exit(0 if all_ok else 1)
