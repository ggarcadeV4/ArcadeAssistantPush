"""
encrypt_secrets.py — Arcade Assistant Vault Initialization Tool
================================================================
Run this ONCE on the arcade cabinet machine to encrypt your Tier 1
secrets into .aa/credentials.dat using Windows DPAPI.

The resulting credentials.dat is machine-bound — it CANNOT be
decrypted on any other PC. The plaintext .env is then demoted to
a .env.template containing only non-sensitive Tier 2/3 config.

WHEN TO RUN THIS:
  - First-time cabinet setup (before the golden image is cut)
  - After generating a new provisioning token
  - After provisioning completes and the cabinet JWT is issued
  - When rotating the Supabase anon key

HOW TO RUN:
  cd A:\Arcade Assistant Local
  python encrypt_secrets.py

WHAT IT DOES:
  1. Prompts you to enter each Tier 1 secret (input is hidden)
  2. Encrypts each value using Windows DPAPI (machine-bound)
  3. Writes .aa/credentials.dat
  4. Optionally strips Tier 1 values from .env (replaces with placeholders)
  5. Verifies decryption works before exiting

REQUIREMENTS:
  pip install pywin32

TIER REFERENCE:
  Tier 1 (DPAPI vault — this script):
    SUPABASE_URL             The https://xxx.supabase.co URL
    SUPABASE_ANON_KEY        The public anon key (still sensitive at rest)
    AA_PROVISIONING_TOKEN    One-time bootstrap token (clear after use)
    AA_SERVICE_TOKEN         Per-cabinet JWT (set after first registration)

  Tier 2/3 (.env — stays plaintext, not sensitive):
    AA_DRIVE_ROOT, GATEWAY_PORT, BACKEND_PORT, AA_DEVICE_ID,
    AA_MARQUEE_ENABLED, AA_UPDATES_ENABLED, feature flags, etc.
"""

import getpass
import json
import logging
import os
import re
import sys
from pathlib import Path

# ── Bootstrap path so we can import secrets_loader from same directory ─────────
sys.path.insert(0, str(Path(__file__).parent))
from secrets_loader import save_secrets, load_secrets, _get_credentials_path  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# ── Tier 1 secret definitions ──────────────────────────────────────────────────
# Each entry: (env_var_name, prompt_label, required)
TIER_1_SECRETS = [
    (
        "SUPABASE_URL",
        "Supabase Project URL (https://zlkhsxacfyxsctqpvbsh.supabase.co)",
        True,
    ),
    (
        "SUPABASE_ANON_KEY",
        "Supabase Anon Key (eyJhbGci...)",
        True,
    ),
    (
        "AA_PROVISIONING_TOKEN",
        "Provisioning Token (one-time bootstrap token — leave blank if not yet issued)",
        False,
    ),
    (
        "AA_SERVICE_TOKEN",
        "Cabinet Service JWT (leave blank if not yet provisioned)",
        False,
    ),
]

# These keys will be scrubbed/replaced in .env after vault creation
TIER_1_ENV_KEYS = {entry[0] for entry in TIER_1_SECRETS}

# Placeholder written into .env to replace real values
PLACEHOLDER = "VAULT_MANAGED"


def _banner(msg: str) -> None:
    width = 70
    print("\n" + "═" * width)
    print(f"  {msg}")
    print("═" * width)


def _collect_secrets() -> dict[str, str]:
    """Interactively collect Tier 1 secret values from the operator."""
    _banner("ARCADE ASSISTANT — VAULT INITIALIZATION")
    print("""
  This tool encrypts your Tier 1 secrets using Windows DPAPI.
  The encrypted vault is bound to THIS machine and THIS Windows user.

  ⚠  Run this tool DIRECTLY on the arcade cabinet — not on your dev PC.
  ⚠  Input is hidden. Values are never written to terminal history.
  ⚠  Press Enter to skip optional secrets.
""")

    secrets: dict[str, str] = {}

    for env_key, label, required in TIER_1_SECRETS:
        print(f"\n  [{env_key}]")
        print(f"  {label}")

        # Check if already in environment (from .env)
        existing = os.environ.get(env_key, "")
        if existing and existing != PLACEHOLDER:
            use_existing = input(
                f"  ↳ Found in environment. Use current value? [Y/n]: "
            ).strip().lower()
            if use_existing in ("", "y", "yes"):
                secrets[env_key] = existing
                print(f"  ✅ Using environment value for {env_key}")
                continue

        while True:
            value = getpass.getpass("  Enter value (hidden): ").strip()

            if not value:
                if required:
                    print("  ⚠  This secret is required. Please enter a value.")
                    continue
                else:
                    print(f"  ↳ Skipping {env_key} (optional)")
                    break

            confirm = getpass.getpass("  Confirm value (hidden): ").strip()
            if value != confirm:
                print("  ✗  Values don't match. Try again.")
                continue

            secrets[env_key] = value
            print(f"  ✅ {env_key} accepted ({len(value)} chars)")
            break

    return secrets


def _scrub_dotenv(env_path: Path) -> None:
    """
    Replace Tier 1 values in .env with VAULT_MANAGED placeholders.
    Preserves all other keys, comments, and formatting exactly.
    """
    if not env_path.exists():
        print(f"\n  ⚠  .env not found at {env_path} — skipping scrub.")
        return

    content = env_path.read_text(encoding="utf-8")
    original = content

    for key in TIER_1_ENV_KEYS:
        # Match KEY=anything (quoted or unquoted, with or without spaces)
        pattern = rf"^({re.escape(key)}\s*=\s*)(.+)$"
        replacement = rf"\g<1>{PLACEHOLDER}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content == original:
        print("\n  ℹ  .env: No Tier 1 values found to scrub (may already be clean).")
    else:
        # Write updated .env
        env_path.write_text(content, encoding="utf-8")
        print(f"\n  ✅ .env scrubbed — Tier 1 values replaced with '{PLACEHOLDER}'")

    # Also update .env.template to reflect clean state
    template_path = env_path.parent / ".env.template"
    if not template_path.exists():
        template_path.write_text(content, encoding="utf-8")
        print(f"  ✅ .env.template created from scrubbed .env")


def _verify_vault(credentials_path: Path, secrets: dict[str, str]) -> bool:
    """Verify all written secrets decrypt correctly."""
    print("\n" + "─" * 70)
    print("  VERIFICATION — Confirming vault decrypts correctly on this machine")
    print("─" * 70)

    # Temporarily clear the env vars so load_secrets actually loads them
    backup = {}
    for key in secrets:
        backup[key] = os.environ.pop(key, None)

    success = load_secrets(credentials_path)

    # Restore
    for key, val in backup.items():
        if val is not None:
            os.environ[key] = val

    if success:
        print("\n  ✅ Vault verified — all secrets decrypt correctly on this machine.")
    else:
        print("\n  ❌ Vault verification FAILED. Please re-run this script.")

    return success


def main() -> int:
    # ── Determine paths ────────────────────────────────────────────────────────
    # Try to load .env first so existing values are available as defaults
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        env_path = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\Arcade Assistant Local")) / ".env"
        load_dotenv(env_path, override=False)
    except ImportError:
        env_path = Path(os.environ.get("AA_DRIVE_ROOT", "A:\\Arcade Assistant Local")) / ".env"

    credentials_path = _get_credentials_path()

    # ── Warn if vault already exists ───────────────────────────────────────────
    if credentials_path.exists():
        print(f"\n  ⚠  Existing vault found: {credentials_path}")
        overwrite = input("  Overwrite? This will re-encrypt ALL Tier 1 secrets. [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("  Aborted. Existing vault unchanged.")
            return 0

    # ── Collect secrets interactively ──────────────────────────────────────────
    secrets = _collect_secrets()

    if not secrets:
        print("\n  ✗ No secrets entered. Vault not created.")
        return 1

    # ── Write vault ────────────────────────────────────────────────────────────
    _banner("WRITING VAULT")
    print(f"\n  Encrypting {len(secrets)} secret(s) with Windows DPAPI...")

    try:
        save_secrets(secrets, credentials_path)
    except RuntimeError as exc:
        print(f"\n  ❌ Encryption failed: {exc}")
        return 1

    print(f"\n  ✅ Vault written: {credentials_path}")

    # ── Scrub .env ─────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    scrub = input("  Scrub Tier 1 values from .env now? [Y/n]: ").strip().lower()
    if scrub in ("", "y", "yes"):
        _scrub_dotenv(env_path)
    else:
        print("  Skipping .env scrub. Remember to do this before golden image cut.")

    # ── Verify ─────────────────────────────────────────────────────────────────
    ok = _verify_vault(credentials_path, secrets)

    # ── Final summary ──────────────────────────────────────────────────────────
    _banner("VAULT INITIALIZATION COMPLETE")
    print(f"""
  Vault location : {credentials_path}
  Secrets stored : {len(secrets)}
  Machine-bound  : YES (unreadable on other PCs)

  NEXT STEPS:
  1. Confirm start-aa.bat calls 'python secrets_loader.py' (or that
     app.py imports secrets_loader and calls load_secrets() at boot).
  2. Confirm .env no longer contains live Tier 1 values.
  3. Run 'python secrets_loader.py' anytime to verify vault integrity.

  TO ADD/UPDATE A SINGLE SECRET LATER:
    python -c "
    from secrets_loader import update_secret
    update_secret('AA_SERVICE_TOKEN', 'your-new-jwt-here')
    "
""")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
