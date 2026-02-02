#!/usr/bin/env python3
"""
Cabinet Connectivity Smoke Test
===============================
Tests Supabase connectivity from this cabinet PC using anon key only.
Read/Write to cabinet tables; Read-only command poll.
"""

from datetime import datetime
import os
import sys

# Try to load dotenv if available
DOTENV_LOADED = False
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_LOADED = True
except ImportError:
    pass

# Environment detection
PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

# Load required environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Test results storage
RESULTS = {
    "connection": {"status": None, "error": None},
    "registration": {"status": None, "error": None},
    "heartbeat": {"status": None, "error": None},
    "telemetry": {"status": None, "error": None},
    "command_poll": {"status": None, "error": None},
}


def print_header():
    print("=" * 60)
    print("CABINET CONNECTIVITY SMOKE TEST")
    print("=" * 60)
    print(f"Python Version: {PYTHON_VERSION}")
    print(f"Dotenv Loaded: {DOTENV_LOADED}")
    print(f"SUPABASE_URL: {'SET' if SUPABASE_URL else 'NOT SET'}")
    print(f"SUPABASE_ANON_KEY: {'SET' if SUPABASE_ANON_KEY else 'NOT SET'}")
    print("=" * 60)


def get_supabase_client():
    """Create and return Supabase client."""
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def test_1_connection(client, cabinet_id):
    """Test 1: Connection - select count from cabinet"""
    print("\n[TEST 1] Connection Check...")
    try:
        response = client.table("cabinet").select("*", count="exact").execute()
        count = response.count if hasattr(response, 'count') else len(response.data)
        print(f"  ✓ Connected! Cabinet table has {count} row(s).")
        RESULTS["connection"]["status"] = "PASS"
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ FAILED: {error_msg}")
        RESULTS["connection"]["status"] = "FAIL"
        RESULTS["connection"]["error"] = f"table=cabinet, op=SELECT COUNT, error={error_msg}"
        return False


def test_2_registration(client, cabinet_id, mac_address):
    """Test 2: Registration - upsert cabinet row"""
    print("\n[TEST 2] Cabinet Registration (Upsert)...")
    try:
        data = {
            "cabinet_id": cabinet_id,
            "name": f"Cabinet-{cabinet_id[:8]}",
            "mac_address": mac_address or None,
            "status": "online",
        }
        response = client.table("cabinet").upsert(data, on_conflict="cabinet_id").execute()
        print(f"  ✓ Upserted cabinet row for {cabinet_id}")
        RESULTS["registration"]["status"] = "PASS"
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ FAILED: {error_msg}")
        RESULTS["registration"]["status"] = "FAIL"
        RESULTS["registration"]["error"] = f"table=cabinet, op=UPSERT, error={error_msg}"
        return False


def test_3_heartbeat(client, cabinet_id):
    """Test 3: Heartbeat - insert into cabinet_heartbeat"""
    print("\n[TEST 3] Heartbeat Insert...")
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        data = {
            "cabinet_id": cabinet_id,
            "observed_at": now_iso,
            "status": "online",
            "payload": {},
        }
        response = client.table("cabinet_heartbeat").insert(data).execute()
        print(f"  ✓ Inserted heartbeat at {now_iso}")
        RESULTS["heartbeat"]["status"] = "PASS"
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ FAILED: {error_msg}")
        RESULTS["heartbeat"]["status"] = "FAIL"
        RESULTS["heartbeat"]["error"] = f"table=cabinet_heartbeat, op=INSERT, error={error_msg}"
        return False


def test_4_telemetry(client, cabinet_id):
    """Test 4: Telemetry - insert into cabinet_telemetry"""
    print("\n[TEST 4] Telemetry Insert...")
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        data = {
            "cabinet_id": cabinet_id,
            "level": "INFO",
            "message": "Integration test from smoke test",
            "occurred_at": now_iso,
        }
        response = client.table("cabinet_telemetry").insert(data).execute()
        print(f"  ✓ Inserted telemetry log at {now_iso}")
        RESULTS["telemetry"]["status"] = "PASS"
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ FAILED: {error_msg}")
        RESULTS["telemetry"]["status"] = "FAIL"
        RESULTS["telemetry"]["error"] = f"table=cabinet_telemetry, op=INSERT, error={error_msg}"
        return False


def test_5_command_poll(client, cabinet_id):
    """Test 5: Command Poll - READ ONLY select from command_queue"""
    print("\n[TEST 5] Command Queue Poll (READ ONLY)...")
    try:
        response = (
            client.table("command_queue")
            .select("*")
            .eq("cabinet_id", cabinet_id)
            .eq("status", "pending")
            .execute()
        )
        count = len(response.data) if response.data else 0
        print(f"  ✓ Polled command_queue: {count} pending command(s)")
        RESULTS["command_poll"]["status"] = "PASS"
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ FAILED: {error_msg}")
        RESULTS["command_poll"]["status"] = "FAIL"
        RESULTS["command_poll"]["error"] = f"table=command_queue, op=SELECT, error={error_msg}"
        return False


def print_completion_receipt():
    """Print the final completion receipt."""
    print("\n")
    print("=" * 60)
    print("COMPLETION RECEIPT")
    print("=" * 60)
    
    print(f"\nEnvironment Detected:")
    print(f"  - Python Version: {PYTHON_VERSION}")
    print(f"  - Dotenv Loaded: {DOTENV_LOADED}")
    
    print(f"\nTest Results:")
    tests = [
        ("1. Connection", "connection"),
        ("2. Registration", "registration"),
        ("3. Heartbeat", "heartbeat"),
        ("4. Telemetry", "telemetry"),
        ("5. Command Poll", "command_poll"),
    ]
    
    passed = []
    failed = []
    
    for label, key in tests:
        status = RESULTS[key]["status"] or "SKIPPED"
        error = RESULTS[key]["error"]
        status_icon = "✓" if status == "PASS" else ("✗" if status == "FAIL" else "○")
        print(f"  {status_icon} {label}: {status}")
        if error:
            print(f"      Error: {error}")
        
        if status == "PASS":
            passed.append(label)
        elif status == "FAIL":
            failed.append((label, error))
    
    print(f"\nItems Completed:")
    if passed:
        for item in passed:
            print(f"  • {item}")
    else:
        print("  • (none)")
    
    if failed:
        print(f"\nNext Fix:")
        for item, error in failed:
            print(f"  • {item}: Review RLS policies or table schema for fix")
    
    print("\n" + "=" * 60)
    overall = "ALL PASS" if len(failed) == 0 and len(passed) > 0 else "PARTIAL" if passed else "ALL FAIL"
    print(f"OVERALL STATUS: {overall}")
    print("=" * 60)


def main():
    print_header()
    
    # Validate environment
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("\n❌ ERROR: Missing SUPABASE_URL or SUPABASE_ANON_KEY")
        print("   Set these in .env or as environment variables.")
        return
    
    # Prompt for cabinet ID
    cabinet_id = input("\nEnter CABINET_ID (or press Enter to use default 'test-cabinet-001'): ").strip()
    if not cabinet_id:
        cabinet_id = "test-cabinet-001"
    print(f"Using CABINET_ID: {cabinet_id}")
    
    # Prompt for MAC address (optional)
    mac_address = input("Enter cabinet MAC address (or press Enter to skip): ").strip()
    if mac_address:
        print(f"Using MAC: {mac_address}")
    else:
        print("MAC address: (skipped)")
    
    # Initialize client
    print("\nInitializing Supabase client...")
    try:
        client = get_supabase_client()
        print("  ✓ Client initialized")
    except Exception as e:
        print(f"  ✗ Failed to initialize client: {e}")
        RESULTS["connection"]["status"] = "FAIL"
        RESULTS["connection"]["error"] = f"Client init failed: {e}"
        print_completion_receipt()
        return
    
    # Run tests in order
    test_1_connection(client, cabinet_id)
    test_2_registration(client, cabinet_id, mac_address)
    test_3_heartbeat(client, cabinet_id)
    test_4_telemetry(client, cabinet_id)
    test_5_command_poll(client, cabinet_id)
    
    # Print receipt
    print_completion_receipt()


if __name__ == "__main__":
    main()
