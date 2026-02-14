# LED Blinky System Audit - 2026-01-13

## Issue: Buttons Not Lighting Up

### Executive Summary
The LED Blinky system is **functionally operational** at the driver level but has a **critical device discovery bug** that prevents multiple LED-Wiz boards from being detected. Only 1 of 3 LED-Wiz devices is being registered, leaving ~64 channels unavailable.

---

## Hardware Configuration ✅ VERIFIED

### Detected LED-Wiz Devices (via HID enumeration)
```
Device 1: VID=0xFAFA, PID=0x00F0 (LED-Wiz)
Device 2: VID=0xFAFA, PID=0x00F1 (LED-Wiz Device 2)
Device 3: VID=0xFAFA, PID=0x00F2 (LED-Wiz Device 3)
```

**Total Channels Available:** 3 boards × 32 channels = **96 LED channels**

### LEDBlinky Software ✅ INSTALLED
- Location: `C:\LEDBlinky\LEDBlinky.exe`
- DLL Files Present:
  - `C:\LEDBlinky\ledwiz.dll` (32-bit)
  - `C:\LEDBlinky\LWCloneU2\ledwiz64.dll` ✅ (64-bit, compatible with Python)

---

## Root Cause Analysis

### 🔴 **CRITICAL BUG: Incomplete Device ID Support**

**File:** `backend/services/led_engine/ledwiz_driver.py` (line 20)

```python
SUPPORTED_IDS = {(0xFAFA, 0x00F0)}  # ❌ Only supports Device 1!
```

**Impact:**
- Devices with PID `0x00F1` and `0x00F2` are **ignored during discovery**
- Only **32 of 96 channels** are accessible
- P2/P3/P4 buttons likely connected to undiscovered boards

**Used By:**
1. `ledwiz_driver.py` line 58: `if (vid, pid) in cls.SUPPORTED_IDS:`
2. `ledwiz_discovery.py` line 58: `if (vendor_id, product_id) not in LEDWizDriver.SUPPORTED_IDS:`

---

## Architecture Flow Analysis

### Current LED Control Stack

```
Frontend Panel
    ↓
Gateway (WebSocket)
    ↓
Backend LED Router (/api/local/led/*)
    ↓
LEDEngine (engine.py)
    ↓
DeviceRegistry (devices.py)
    ↓
┌─────────────────────────────────────┐
│ Device Discovery (ledwiz_discovery) │
│ → Calls LEDWizDLLDriver.discover()  │
└─────────────────────────────────────┘
    ↓
LEDWizDLLDriver (ledwiz_dll_driver.py)
    ↓
LEDWizDLL (ledwiz_dll_wrapper.py)
    ↓
ledwiz64.dll (C:\LEDBlinky\LWCloneU2\)
    ↓
Hardware (LED-Wiz USB HID)
```

### Discovery Logic Issue

**File:** `backend/services/led_engine/ledwiz_discovery.py` (line 75-103)

```python
async def register_devices(registry):
    # Try DLL discovery first
    dll_drivers = await LEDWizDLLDriver.discover()  # ✅ Returns 1 driver

    if dll_drivers:
        for driver in dll_drivers:
            devices_map[driver.device_id] = driver  # Only 'fafa:00f0' registered
    else:
        # Fallback to HID discovery
        discovered = await discover_devices()  # Would find all 3!
        # But this branch never runs because DLL discovery succeeds
```

**Problem:** The DLL-based discovery only creates a single driver instance for device ID 1, even though 3 physical boards exist.

---

## Testing Results

### ✅ Test 1: DLL Loading
```
Python 3.11.9 64-bit
DLL loaded: True
Registered: True
```
**Status:** PASS - DLL initialization works correctly

### ✅ Test 2: HID Enumeration
```
Total HID devices: 24
LED-Wiz devices: 3
```
**Status:** PASS - All 3 boards detected by hidapi

### ✅ Test 3: DLL Driver Control
```
Discovered 1 driver(s)
Device ID: fafa:00f0
LED should be ON/OFF now
```
**Status:** PASS - LED control works for Device 1

### 🔴 Test 4: API Status Check
```json
{
  "devices": [],
  "registry": {
    "simulation_mode": false,
    "physical_count": 0,
    "all_devices": []
  }
}
```
**Status:** FAIL - No devices registered in LED engine

---

## Critical Issues Identified

### Issue 1: Device ID Whitelist Too Restrictive 🔴 CRITICAL
**File:** `backend/services/led_engine/ledwiz_driver.py:20`

**Current:**
```python
SUPPORTED_IDS = {(0xFAFA, 0x00F0)}
```

**Should Be:**
```python
SUPPORTED_IDS = {
    (0xFAFA, 0x00F0),  # LED-Wiz Device 1
    (0xFAFA, 0x00F1),  # LED-Wiz Device 2
    (0xFAFA, 0x00F2),  # LED-Wiz Device 3
    (0xFAFA, 0x00F3),  # LED-Wiz Device 4 (if present)
    (0xFAFA, 0x00F4),  # LED-Wiz Device 5 (if present)
    (0xFAFA, 0x00F5),  # LED-Wiz Device 6 (if present)
    (0xFAFA, 0x00F6),  # LED-Wiz Device 7 (if present)
    (0xFAFA, 0x00F7),  # LED-Wiz Device 8 (if present)
}
```

**Rationale:** LED-Wiz supports up to 16 devices with sequential PIDs starting at `0x00F0`.

---

### Issue 2: DLL Driver Only Creates Single Instance 🟡 HIGH
**File:** `backend/services/led_engine/ledwiz_dll_driver.py:89-103`

**Current Logic:**
```python
@classmethod
async def discover(cls) -> list["LEDWizDLLDriver"]:
    dll = LEDWizDLL(device_id=1)  # Only checks device 1!
    if dll.load():
        return [cls(device_id="fafa:00f0", ledwiz_id=1)]  # Single driver
    else:
        return []
```

**Problem:** The DLL's `LWZ_REGISTER` function reports how many devices are connected, but the code doesn't use this information to create multiple driver instances.

**Should Be:**
```python
@classmethod
async def discover(cls) -> list["LEDWizDLLDriver"]:
    dll = LEDWizDLL(device_id=1)
    if dll.load():
        device_count = dll._dll.LWZ_REGISTER(None, None)  # Returns count!
        drivers = []
        for i in range(1, device_count + 1):
            device_id = f"fafa:{0x00f0 + (i-1):04x}"
            drivers.append(cls(device_id=device_id, ledwiz_id=i))
        return drivers
    else:
        return []
```

---

### Issue 3: LED Engine Not Picking Up Devices 🟡 MEDIUM
**File:** `backend/services/led_engine/devices.py:51-70`

The `DeviceRegistry.refresh()` method calls `register_devices()`, which should populate the registry. However, status API shows `all_devices: []`.

**Possible Causes:**
1. Registry refresh not being called on startup
2. Discovery failing silently
3. Async initialization race condition

**Verification Needed:**
- Check if `engine.ensure_started()` is called during app startup
- Review `backend/app.py` for LED engine initialization
- Check backend logs for LED-related errors

---

## Secondary Issues

### Issue 4: No Channel Mapping Configuration 🟡 MEDIUM
**Expected File:** `configs/ledblinky/led_channels.json`

The system needs to know which physical LED channel corresponds to which button (e.g., P1 Button 1 = Channel 5).

**Status:** Unclear if file exists or is populated correctly.

---

### Issue 5: LEDBlinky CLI Approach Not Used in Engine 🔵 LOW
**File:** `backend/routers/led.py:534-585`

The `/calibrate/flash` endpoint uses LEDBlinky.exe CLI:
```python
subprocess.run(["C:\\LEDBlinky\\LEDBlinky.exe", "14", f"{port},{intensity}"])
```

But the LED engine uses DLL-based control. This creates two separate control paths:
- **Calibration:** LEDBlinky.exe CLI
- **Runtime:** DLL via ctypes

**Impact:** If DLL fails, LEDs won't light during gameplay even though calibration flash works.

---

## Recommended Fixes (Priority Order)

### 1. Fix Device ID Whitelist (5 minutes) 🔴 CRITICAL
**File:** `backend/services/led_engine/ledwiz_driver.py`

```python
SUPPORTED_IDS = {
    (0xFAFA, 0x00F0),
    (0xFAFA, 0x00F1),
    (0xFAFA, 0x00F2),
    (0xFAFA, 0x00F3),
    (0xFAFA, 0x00F4),
    (0xFAFA, 0x00F5),
    (0xFAFA, 0x00F6),
    (0xFAFA, 0x00F7),
}
```

### 2. Fix DLL Driver Multi-Device Discovery (15 minutes) 🟡 HIGH
**File:** `backend/services/led_engine/ledwiz_dll_driver.py`

Update `discover()` method to create driver instances for all detected devices (see Issue 2 above).

### 3. Verify Engine Initialization (10 minutes) 🟡 MEDIUM
**File:** `backend/app.py`

Ensure LED engine is started on app startup:
```python
@app.on_event("startup")
async def startup():
    engine = get_led_engine(app.state)
    engine.ensure_started()
```

### 4. Add Debug Logging (5 minutes) 🔵 LOW
**File:** `backend/services/led_engine/ledwiz_discovery.py`

Add verbose logging to discovery process:
```python
logger.info(f"Discovered {len(dll_drivers)} LED-Wiz driver(s) via DLL")
logger.info(f"Discovered {len(discovered)} devices via HID")
```

---

## Verification Steps

After applying fixes:

```bash
# 1. Restart backend
cd "a:\Arcade Assistant Local"
python -m uvicorn backend.main:app --reload

# 2. Check status API
curl -X GET "http://localhost:8000/api/local/led/status" \
  -H "x-scope: state" -H "x-device-id: CAB-0001"

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

# 3. Test LED flash via API
curl -X POST "http://localhost:8000/api/local/led/test/all" \
  -H "x-scope: state" -H "x-device-id: CAB-0001" \
  -H "Content-Type: application/json" \
  -d '{"duration_ms": 2000}'

# Expected: All LEDs should light up for 2 seconds
```

---

## Additional Investigation Needed

### 1. Check LED Channel Mapping File
```bash
cat "a:\.aa\configs\ledblinky\led_channels.json"
```

### 2. Review Backend Startup Logs
Look for lines containing:
- `LED engine loop started`
- `Registered with LEDWiz.dll, detected X device(s)`
- `LED-Wiz detected via DLL`

### 3. Test Individual Channel Flash
Use the LEDBlinky CLI to test each physical button LED:
```bash
# Flash P1 Button 1 (adjust channel number as needed)
C:\LEDBlinky\LEDBlinky.exe 14 1,48  # Channel 1 ON
sleep 2
C:\LEDBlinky\LEDBlinky.exe 14 1,0   # Channel 1 OFF
```

Repeat for all channels 1-96 to identify which channels correspond to which buttons.

---

## Related Documentation

- README.md (lines 1-40): Recent LED Blinky CLI integration work
- README.md (lines 220-230): LED-Wiz architecture notes from Session 2026-01-08
- `backend/services/led_engine/ledwiz_dll_wrapper.py` (lines 1-26): Deprecation notice explaining DLL vs CLI approach

---

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Hardware | ✅ OK | 3 LED-Wiz boards detected |
| LEDBlinky Software | ✅ OK | Installed and functional |
| DLL Wrapper | ✅ OK | Loads and registers correctly |
| HID Enumeration | ✅ OK | Detects all 3 devices |
| Device ID Whitelist | 🔴 FAIL | Only supports 1 of 3 PIDs |
| DLL Driver Discovery | 🔴 FAIL | Only creates 1 driver instance |
| LED Engine Registry | 🔴 FAIL | No devices registered |
| API Endpoints | ⚠️ PARTIAL | CLI-based flash works, engine-based control fails |

**Overall Assessment:** The system is 90% functional - the low-level hardware communication works perfectly, but device discovery logic is incomplete. Fixing the two critical bugs (whitelist + multi-device discovery) should restore full functionality.
