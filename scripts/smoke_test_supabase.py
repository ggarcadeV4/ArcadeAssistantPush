#!/usr/bin/env python3
"""
Supabase Integration Smoke Test for Arcade Assistant (Basement)
Run: python scripts/smoke_test_supabase.py

Tests:
1. Environment variable configuration
2. Supabase client initialization
3. Connectivity health check
4. Telemetry insert (requires registered device)
5. Command fetch
6. Edge Function availability
"""
import os
import sys
import json
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_step(step: int, total: int, description: str):
    print(f"\n[{step}/{total}] {description}...")


def main():
    print_header("ARCADE ASSISTANT - SUPABASE SMOKE TEST")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    results = {
        'passed': 0,
        'warnings': 0,
        'failed': 0
    }
    
    # =========================================================================
    # 1. Check environment variables
    # =========================================================================
    print_step(1, 6, "Checking environment variables")
    
    required_vars = ['SUPABASE_URL', 'SUPABASE_ANON_KEY']
    optional_vars = ['SUPABASE_SERVICE_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'AA_DEVICE_ID']
    
    all_required_set = True
    for var in required_vars:
        val = os.getenv(var)
        if val:
            if 'KEY' in var:
                print(f"  ✅ {var} = [REDACTED - {len(val)} chars]")
            else:
                print(f"  ✅ {var} = {val}")
            results['passed'] += 1
        else:
            print(f"  ❌ {var} = NOT SET")
            results['failed'] += 1
            all_required_set = False
    
    for var in optional_vars:
        val = os.getenv(var)
        if val:
            print(f"  ✅ {var} = {'[REDACTED]' if 'KEY' in var else val}")
        else:
            print(f"  ⚠️  {var} = NOT SET (optional)")
            results['warnings'] += 1
    
    if not all_required_set:
        print("\n❌ FATAL: Required environment variables missing. Cannot continue.")
        return 1
    
    # =========================================================================
    # 2. Import and initialize client
    # =========================================================================
    print_step(2, 6, "Initializing Supabase client")
    
    try:
        from services.supabase_client import SupabaseClient, SupabaseError
        client = SupabaseClient()
        print(f"  ✅ Client initialized for {client.url}")
        results['passed'] += 1
    except SupabaseError as e:
        print(f"  ❌ Initialization failed: {e}")
        results['failed'] += 1
        return 1
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        print("     Run: pip install supabase")
        results['failed'] += 1
        return 1
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        results['failed'] += 1
        return 1
    
    # =========================================================================
    # 3. Health check (connectivity)
    # =========================================================================
    print_step(3, 6, "Testing connectivity (health check)")
    
    try:
        result = client.health_check()
        if result.get('connected'):
            latency = result.get('latency_ms', '?')
            print(f"  ✅ Connected to Supabase (latency: {latency}ms)")
            results['passed'] += 1
        else:
            error = result.get('error', 'Unknown error')
            print(f"  ❌ Not connected: {error}")
            results['failed'] += 1
            # Continue with other tests even if health check fails
    except Exception as e:
        print(f"  ❌ Health check exception: {e}")
        results['failed'] += 1
    
    # =========================================================================
    # 4. Test telemetry insert
    # =========================================================================
    print_step(4, 6, "Testing telemetry insert")
    
    test_device_id = os.getenv('AA_DEVICE_ID', 'smoke-test-device-00000000')
    print(f"  Using device_id: {test_device_id}")
    
    try:
        success = client.send_telemetry(
            device_id=test_device_id,
            level='INFO',
            code='SMOKE_TEST',
            message=f'Smoke test executed at {datetime.now(timezone.utc).isoformat()}',
            metadata={'test': True, 'script': 'smoke_test_supabase.py'},
            batch=False  # Immediate insert for testing
        )
        if success:
            print("  ✅ Telemetry insert succeeded")
            results['passed'] += 1
        else:
            print("  ⚠️  Telemetry insert returned False")
            print("     This may be expected if device is not registered or RLS blocks insert")
            results['warnings'] += 1
    except Exception as e:
        print(f"  ⚠️  Telemetry insert error: {e}")
        print("     This is expected if device is not registered in the devices table")
        results['warnings'] += 1
    
    # =========================================================================
    # 5. Test command fetch
    # =========================================================================
    print_step(5, 6, "Testing command fetch")
    
    try:
        commands = client.fetch_new_commands(test_device_id)
        if commands is not None:
            print(f"  ✅ Command fetch succeeded ({len(commands)} pending commands)")
            if commands:
                for i, cmd in enumerate(commands[:3]):  # Show first 3
                    print(f"      [{i+1}] type={cmd.get('type', '?')}, status={cmd.get('status', '?')}")
                if len(commands) > 3:
                    print(f"      ... and {len(commands) - 3} more")
            results['passed'] += 1
        else:
            print("  ⚠️  Command fetch returned None")
            print("     This may indicate an RLS policy issue or network problem")
            results['warnings'] += 1
    except Exception as e:
        print(f"  ⚠️  Command fetch error: {e}")
        results['warnings'] += 1
    
    # =========================================================================
    # 6. Test Edge Function availability
    # =========================================================================
    print_step(6, 6, "Testing Edge Function availability")
    
    import urllib.request
    import urllib.error
    
    base_url = os.getenv('SUPABASE_URL', '').rstrip('/')
    
    # Supabase Edge Functions URL pattern
    if '.supabase.co' in base_url:
        # Production: https://PROJECT.supabase.co -> https://PROJECT.functions.supabase.co
        functions_url = base_url.replace('.supabase.co', '.functions.supabase.co')
    else:
        # Local: assume /functions/v1 path
        functions_url = base_url + '/functions/v1'
    
    edge_functions = [
        'anthropic-proxy',
        'openai-proxy', 
        'elevenlabs-proxy',
        'register_device',
        'send_command',
        'sign_url'
    ]
    
    for fn in edge_functions:
        try:
            url = f"{functions_url}/{fn}"
            req = urllib.request.Request(url, method='OPTIONS')
            req.add_header('Origin', 'http://localhost:3000')
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  ✅ {fn}: reachable (HTTP {resp.status})")
                results['passed'] += 1
                
        except urllib.error.HTTPError as e:
            if e.code in [401, 403]:
                # Auth required is expected for most functions
                print(f"  ✅ {fn}: reachable (HTTP {e.code} - auth required, expected)")
                results['passed'] += 1
            elif e.code == 404:
                print(f"  ⚠️  {fn}: NOT DEPLOYED (HTTP 404)")
                results['warnings'] += 1
            else:
                print(f"  ⚠️  {fn}: HTTP {e.code}")
                results['warnings'] += 1
                
        except urllib.error.URLError as e:
            print(f"  ❌ {fn}: Network error - {e.reason}")
            results['failed'] += 1
            
        except Exception as e:
            print(f"  ⚠️  {fn}: {type(e).__name__}: {e}")
            results['warnings'] += 1
    
    # =========================================================================
    # Summary
    # =========================================================================
    print_header("SMOKE TEST SUMMARY")
    
    total = results['passed'] + results['warnings'] + results['failed']
    
    print(f"  ✅ Passed:   {results['passed']}")
    print(f"  ⚠️  Warnings: {results['warnings']}")
    print(f"  ❌ Failed:   {results['failed']}")
    print(f"  ───────────────────")
    print(f"  Total:      {total}")
    
    if results['failed'] > 0:
        print("\n❌ SMOKE TEST FAILED - See errors above")
        return 1
    elif results['warnings'] > 0:
        print("\n⚠️  SMOKE TEST PASSED WITH WARNINGS")
        return 0
    else:
        print("\n✅ SMOKE TEST PASSED")
        return 0


if __name__ == '__main__':
    sys.exit(main())
