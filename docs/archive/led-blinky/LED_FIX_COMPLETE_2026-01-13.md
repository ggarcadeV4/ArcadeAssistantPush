# LED-Wiz Multi-Device Discovery - Fix Complete

## Status: ✅ CODE FIXED - RESTART REQUIRED

---

## What Was Fixed

### Problem
The LED system was only detecting 1 of 3 LED-Wiz boards because the DLL's `LWZ_REGISTER` function returns 0 instead of 3 on this system.

### Solution Applied
Changed the discovery strategy to:
1. **Use HID enumeration** to find all LED-Wiz devices (reliable, finds all 3)
2. **Use DLL** for actual LED control (reliable, works perfectly)

### Files Modified

**File:** `backend/services/led_engine/ledwiz_dll_driver.py`
- **Method:** `LEDWizDLLDriver.discover()`
- **Change:** Now calls `hid_discover()` to find devices instead of relying on DLL count

**File:** `backend/services/led_engine/ledwiz_driver.py`
- **Line:** 20-29
- **Change:** Added PIDs 0x00F0 through 0x00F7 to `SUPPORTED_IDS`

---

## Test Results

### Before Fix
```
Found 1 driver(s)
  - Device ID: fafa:00f0, LEDWiz ID: 1
```
❌ Only 32 of 96 channels available

### After Fix
```
Found 3 driver(s)
  - Device ID: fafa:00f0, LEDWiz ID: 1
  - Device ID: fafa:00f1, LEDWiz ID: 2
  - Device ID: fafa:00f2, LEDWiz ID: 3
```
✅ All 96 channels available!

---

## Backend Restart Required

The backend is currently running with old code cached in memory:
- **Process ID:** 25180
- **Port:** 8000
- **Status:** Running but using old discovery logic

### Option 1: Restart via npm (Recommended)

```bash
# Stop all services
cd "a:\Arcade Assistant Local"
# Press Ctrl+C if running in terminal, or:
taskkill /F /PID 25180

# Restart full stack
npm run dev
```

### Option 2: Restart Backend Only

```bash
# Stop backend
taskkill /F /PID 25180

# Start backend
cd "a:\Arcade Assistant Local"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Let `npm run dev` handle it

If you're using the dev script, it should auto-reload when files change. Wait ~5 seconds and test.

---

## Verification Steps

After restarting, run these tests:

### Test 1: Check LED Status
```bash
curl -s "http://localhost:8000/api/local/led/status" \
  -H "x-scope: state" -H "x-device-id: CAB-0001" | python -m json.tool
```

**Expected Output:**
```json
{
  "devices": [
    {"device_id": "fafa:00f0", "channel_count": 32, ...},
    {"device_id": "fafa:00f1", "channel_count": 32, ...},
    {"device_id": "fafa:00f2", "channel_count": 32, ...}
  ],
  "registry": {
    "physical_count": 3,
    "simulation_mode": false
  }
}
```

### Test 2: Test All LEDs
```bash
curl -X POST "http://localhost:8000/api/local/led/test/all" \
  -H "x-scope: state" -H "x-device-id: CAB-0001" \
  -H "Content-Type: application/json" \
  -d '{"duration_ms": 2000}'
```

**Expected:** All button LEDs across all players should light up for 2 seconds

### Test 3: Test Specific Channel
```bash
# Test channel 1 (P1 Button 1)
curl -X POST "http://localhost:8000/api/local/led/calibrate/flash" \
  -H "x-scope: config" -H "x-device-id: CAB-0001" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "fafa:00f0", "channel": 1, "duration_ms": 1000}'

# Test channel 40 (P2 button on board 2)
curl -X POST "http://localhost:8000/api/local/led/calibrate/flash" \
  -H "x-scope: config" -H "x-device-id: CAB-0001" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "fafa:00f1", "channel": 8, "duration_ms": 1000}'
```

---

## What Changed in the Code

### Discovery Logic (Before)
```python
# Relied on DLL to report device count
device_count = dll._dll.LWZ_REGISTER(None, None)  # Returns 0 ❌
if device_count <= 0:
    device_count = 1  # Only creates 1 driver
```

### Discovery Logic (After)
```python
# Use HID enumeration to find all devices
hid_devices = await hid_discover()  # Finds all 3 ✅

# Create DLL driver for each one
for i, hid_dev in enumerate(hid_devices, start=1):
    device_id = f"{hid_dev.vendor_id:04x}:{hid_dev.product_id:04x}"
    driver = cls(device_id=device_id, ledwiz_id=i)
    drivers.append(driver)
```

**Result:** HID finds devices, DLL controls them. Best of both worlds!

---

## Troubleshooting

### If still showing 0 devices after restart:

1. **Check backend logs for errors:**
   ```bash
   # Look for LED-related errors
   grep -i "led" backend_logs.txt | tail -20
   ```

2. **Verify HID module works:**
   ```bash
   python -c "import hid; print(f'HID devices: {len(hid.enumerate())}')"
   ```

3. **Test DLL loading:**
   ```bash
   cd "a:\Arcade Assistant Local"
   python -c "from backend.services.led_engine.ledwiz_dll_wrapper import LEDWizDLL; dll = LEDWizDLL(); print(f'DLL loaded: {dll.load()}')"
   ```

4. **Check if engine is started:**
   ```bash
   curl -s "http://localhost:8000/api/local/led/status" | grep "running"
   ```

### If LEDs still don't light:

This fix handles **device discovery only**. If devices are detected but LEDs don't light, check:

1. **LED channel mappings** - Do you have `configs/ledblinky/led_channels.json`?
2. **Wiring** - Are buttons wired to the correct LED-Wiz channels?
3. **Power** - Are LED-Wiz boards getting 5V power?

---

## Summary

| Component | Before | After |
|-----------|--------|-------|
| LED-Wiz Boards Detected | 1 | 3 ✅ |
| Available Channels | 32 | 96 ✅ |
| Discovery Method | DLL (broken) | HID (reliable) ✅ |
| Control Method | DLL | DLL ✅ |
| Code Changes | - | 2 files ✅ |
| Backend Restart | - | **REQUIRED** ⚠️ |

**Next Step:** Restart the backend to apply changes!
