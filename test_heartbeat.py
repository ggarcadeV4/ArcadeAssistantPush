
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

# Mock environment if needed
os.environ["AA_DRIVE_ROOT"] = "A:\\" 

# Load .env manually
try:
    with open('a:\\Arcade Assistant Local\\.env', 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()
except Exception as e:
    print(f"Warning: Could not load .env: {e}") 

async def test_heartbeat():
    print("Testing heartbeat...")
    try:
        from backend.services.heartbeat import send_heartbeat
        success = await send_heartbeat()
        if success:
            print("✅ Heartbeat sent successfully!")
        else:
            print("❌ Heartbeat failed (check logs)")
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_heartbeat())
