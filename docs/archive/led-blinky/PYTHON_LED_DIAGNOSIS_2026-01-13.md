# Python LED Blinky Diagnosis - 2026-01-13

## Issue Summary
The LED system is only detecting 1 of 3 LED-Wiz boards, even after the SUPPORTED_IDS fix was applied.

---

## Root Cause Found 🔴

### Problem: DLL LWZ_REGISTER Returns Incorrect Count

**File:** `backend/services/led_engine/ledwiz_dll_driver.py` (lines 96-108)

The DLL discovery relies on `LWZ_REGISTER` to report device count, but it returns **0** instead of **3**.

```python
# Current code:
device_count = dll._dll.LWZ_REGISTER(None, None)  # Returns 0 ❌
if device_count <= 0:
    device_count = 1  # Fallback to 1
```

**Test Results:**
```
DLL loaded successfully
Device count from LWZ_REGISTER: 0  ❌ Should be 3!
Device 1: Loaded ✅
Device 2: Loaded ✅
Device 3: Loaded ✅
```

**Why This Happens:**
The LEDWiz.dll's `LWZ_REGISTER` function doesn't reliably report device count on some systems. It's meant to be called once for initialization, and the return value may not reflect actual device count.

---

## Working Components ✅

### 1. HID Enumeration Works Perfectly
```
HID enumeration found 3 device(s):
  VID:PID = fafa:00f0 (LED-Wiz)
  VID:PID = fafa:00f1 (LED-Wiz Device 2)
  VID:PID = fafa:00f2 (LED-Wiz Device 3)
```

### 2. SUPPORTED_IDS Fixed
```python
SUPPORTED_IDS = {
    (0xFAFA, 0x00F0),  # ✅ Device 1
    (0xFAFA, 0x00F1),  # ✅ Device 2
    (0xFAFA, 0x00F2),  # ✅ Device 3
    (0xFAFA, 0x00F3),  # ✅ Device 4-8
    # ...
}
```

### 3. DLL Communication Works
- DLL loads successfully for all device IDs (1, 2, 3)
- Individual device access works
- LED control commands work

### 4. Backend Running
- Port 8000 active
- Health endpoint responds
- LED status API responds (but shows no devices)

---

## The Solution 🔧

The fix is to **use HID enumeration instead of relying on LWZ_REGISTER's count**.

### Current Flawed Logic:
```python
# ledwiz_dll_driver.py discover()
dll = LEDWizDLL(device_id=1)
if dll.load():
    device_count = dll._dll.LWZ_REGISTER(None, None)  # ❌ Returns 0
    # Creates only 1 driver
```

### Fixed Logic:
```python
# Should combine HID discovery with DLL control
async def discover(cls) -> list["LEDWizDLLDriver"]:
    """Use HID enumeration to find devices, DLL for control."""
    from .ledwiz_discovery import discover_devices as hid_discover

    # Find all LED-Wiz devices via HID
    hid_devices = await hid_discover()

    if not hid_devices:
        return []

    # Try to load DLL (just to verify it works)
    dll = LEDWizDLL(device_id=1)
    if not dll.load():
        logger.error("LEDWiz DLL failed to load")
        return []

    # Create a driver for each HID device found
    drivers = []
    for i, hid_dev in enumerate(hid_devices, start=1):
        device_id = f"{hid_dev.vendor_id:04x}:{hid_dev.product_id:04x}"
        drivers.append(cls(device_id=device_id, ledwiz_id=i))
        logger.info(f"Created driver for {device_id} (LEDWiz ID {i})")

    return drivers
```

---

## Files That Need Changes

### File 1: `backend/services/led_engine/ledwiz_dll_driver.py`
**Lines:** 89-122 (the `discover()` method)

**Change:** Replace DLL-based device counting with HID enumeration

**Impact:** Will detect all 3 LED-Wiz boards instead of just 1

---

## Alternative Approach (Simpler)

Since the code already falls back to HID discovery when DLL discovery returns empty, we could just make the DLL discovery **always** use HID:

### File: `backend/services/led_engine/ledwiz_discovery.py`
**Lines:** 75-112 (the `register_devices()` function)

**Current Logic:**
```python
dll_drivers = await LEDWizDLLDriver.discover()  # Returns 1 driver
if dll_drivers:
    # Use DLL drivers
else:
    # Fall back to HID
```

**Simpler Fix:**
```python
# Always use HID to discover, DLL to control
discovered = await discover_devices()  # HID finds all 3
if discovered:
    drivers = []
    for i, hid_dev in enumerate(discovered, start=1):
        device_id = f"{hid_dev.vendor_id:04x}:{hid_dev.product_id:04x}"
        driver = LEDWizDLLDriver(device_id=device_id, ledwiz_id=i)
        drivers.append(driver)

    for driver in drivers:
        devices_map[driver.device_id] = driver
```

This keeps the architecture clean: **HID for discovery, DLL for control**.

---

## Testing After Fix

```bash
# 1. Apply the fix to ledwiz_discovery.py

# 2. Restart backend
# Kill existing process
ps aux | grep python | grep backend | awk '{print $2}' | xargs kill

# Start backend
cd "a:\Arcade Assistant Local"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# 3. Check LED status
curl -s "http://localhost:8000/api/local/led/status" \
  -H "x-scope: state" -H "x-device-id: CAB-0001" | python -m json.tool

# Expected output:
# {
#   "devices": [
#     {"device_id": "fafa:00f0", ...},
#     {"device_id": "fafa:00f1", ...},
#     {"device_id": "fafa:00f2", ...}
#   ],
#   "registry": {
#     "physical_count": 3,
#     "simulation_mode": false
#   }
# }

# 4. Test LED flash
curl -X POST "http://localhost:8000/api/local/led/test/all" \
  -H "x-scope: state" -H "x-device-id: CAB-0001" \
  -H "Content-Type: application/json" \
  -d '{"duration_ms": 2000}'
```

---

## Why The Backend Needs Restart

The backend loaded the old code on startup. Even though you edited the files:
- Python modules are cached in memory
- The running process uses old bytecode
- Changes won't apply until restart

**Current backend process:**
- PID: 25180
- Started: ~1 hour ago (before fixes)
- Port: 8000 (listening)

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Python | ✅ OK | Version 3.11.9, 64-bit |
| HID Library | ✅ OK | Detects all 3 devices |
| DLL Loading | ✅ OK | Loads successfully |
| SUPPORTED_IDS | ✅ FIXED | Now includes 0x00F0-0x00F7 |
| DLL Discovery | 🔴 BROKEN | LWZ_REGISTER returns 0 |
| Backend Running | ✅ OK | Port 8000, needs restart |
| LED API | ⚠️ PARTIAL | Responds but shows no devices |

**Action Required:** Fix `ledwiz_discovery.py` to use HID enumeration, then restart backend.
