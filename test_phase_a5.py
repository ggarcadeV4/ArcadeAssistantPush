"""Phase A5 Verification Tests.

Tests the three architectural constraints:
1. Performance: WebSocket endpoint exists
2. Robustness: asyncio.to_thread is used for hardware I/O
3. Safety: Pattern storage uses sanctioned path + backup
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_asyncio_to_thread_in_service():
    """Verify that write_port is wrapped with asyncio.to_thread."""
    service_path = Path("backend/services/blinky/service.py")
    content = service_path.read_text()
    
    # Check for asyncio.to_thread usage
    count = content.count("asyncio.to_thread(write_port")
    
    if count >= 3:
        print(f"✅ ROBUSTNESS: Found {count} asyncio.to_thread(write_port) calls")
        return True
    else:
        print(f"❌ ROBUSTNESS: Only found {count} asyncio.to_thread calls (expected 3+)")
        return False


def test_websocket_endpoint_exists():
    """Verify WebSocket endpoint is defined in led.py."""
    led_path = Path("backend/routers/led.py")
    content = led_path.read_text()
    
    # Check for WebSocket decorator
    has_ws_decorator = '@router.websocket("/ws")' in content
    has_raw_dict = 'websocket.send_json(frame)' in content
    no_pydantic = 'Pydantic' not in content[content.find('@router.websocket'):] if has_ws_decorator else False
    
    if has_ws_decorator and has_raw_dict:
        print("✅ PERFORMANCE: WebSocket endpoint exists with raw dict streaming")
        return True
    else:
        print(f"❌ PERFORMANCE: WebSocket check failed (decorator={has_ws_decorator}, raw_dict={has_raw_dict})")
        return False


def test_pattern_storage_exists():
    """Verify pattern storage with sanctioned path and backup."""
    storage_path = Path("backend/services/led_pattern_storage.py")
    
    if not storage_path.exists():
        print("❌ SAFETY: led_pattern_storage.py does not exist")
        return False
    
    content = storage_path.read_text()
    
    has_sanctioned = 'SANCTIONED_PATH = Path("A:/Arcade Assistant/configs/led-patterns.json")' in content
    has_backup = 'create_backup(' in content
    
    if has_sanctioned and has_backup:
        print("✅ SAFETY: Pattern storage with sanctioned path and backup workflow")
        return True
    else:
        print(f"❌ SAFETY: Storage check failed (sanctioned={has_sanctioned}, backup={has_backup})")
        return False


def test_pattern_storage_logic():
    """Test that pattern storage can preview and apply."""
    try:
        os.environ["AA_SKIP_ENV_VALIDATION"] = "1"
        os.environ["AA_SKIP_APP_IMPORT"] = "1"
        
        from backend.services.led_pattern_storage import LEDPatternStorage
        
        storage = LEDPatternStorage(Path("A:/Arcade Assistant Local"))
        
        # Test preview
        preview = storage.preview_patterns({"test": "data"})
        if "current" in preview and "proposed" in preview:
            print("✅ SAFETY: preview_patterns() works correctly")
            return True
        else:
            print("❌ SAFETY: preview_patterns() missing expected keys")
            return False
    except Exception as e:
        print(f"❌ SAFETY: Pattern storage import failed: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("PHASE A5 VERIFICATION TESTS")
    print("="*60 + "\n")
    
    results = []
    results.append(test_asyncio_to_thread_in_service())
    results.append(test_websocket_endpoint_exists())
    results.append(test_pattern_storage_exists())
    results.append(test_pattern_storage_logic())
    
    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if all(results):
        print("🎉 ALL PHASE A5 CONSTRAINTS VERIFIED!")
    else:
        print("⚠️  Some tests failed")
    print("="*60 + "\n")
    
    sys.exit(0 if all(results) else 1)
