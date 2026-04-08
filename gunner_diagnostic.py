"""
Gunner Auto-Detection Diagnostic Script
========================================
Run this from the Arcade Assistant root:
    python gunner_diagnostic.py

It will output everything Codex needs to make a safe repair plan.
No files are modified. Read-only diagnostics only.
"""
import os
import sys
import json
import traceback

print("=" * 70)
print("  GUNNER AUTO-DETECTION DIAGNOSTICS")
print("=" * 70)

# ── 1. Environment Variables ──────────────────────────────────────────
print("\n── 1. ENVIRONMENT VARIABLES ──")
env_val = os.getenv("ENVIRONMENT", "(unset)")
mock_val = os.getenv("AA_USE_MOCK_GUNNER", "(unset)")
print(f"  ENVIRONMENT        = {env_val}")
print(f"  AA_USE_MOCK_GUNNER = {mock_val}")

# ── 2. Python hid (hidapi) Import ─────────────────────────────────────
print("\n── 2. PYTHON HID IMPORT ──")
hid_ok = False
try:
    import hid
    hid_ok = True
    print("  ✅ import hid SUCCEEDED")
except ImportError as e:
    print(f"  ❌ import hid FAILED: {e}")
except Exception as e:
    print(f"  ❌ import hid ERROR: {e}")

# ── 3. Python pyusb (usb.core) Import ────────────────────────────────
print("\n── 3. PYTHON PYUSB IMPORT ──")
usb_ok = False
try:
    import usb.core
    import usb.util
    usb_ok = True
    print("  ✅ import usb.core SUCCEEDED")
except ImportError as e:
    print(f"  ❌ import usb.core FAILED: {e}")
except Exception as e:
    print(f"  ❌ import usb.core ERROR: {e}")

# ── 4. HID Enumeration ───────────────────────────────────────────────
print("\n── 4. HID ENUMERATION (hid.enumerate) ──")
hid_devices = []
if hid_ok:
    try:
        raw = hid.enumerate()
        # Filter to non-zero VIDs
        hid_devices = [d for d in raw if d.get("vendor_id", 0) != 0]
        print(f"  Total HID devices (non-zero VID): {len(hid_devices)}")
        for d in hid_devices:
            vid = d.get("vendor_id", 0)
            pid = d.get("product_id", 0)
            product = d.get("product_string", "") or "(no product string)"
            mfr = d.get("manufacturer_string", "") or "(no manufacturer)"
            path = d.get("path", b"")
            if isinstance(path, bytes):
                path = path.decode("utf-8", errors="replace")
            print(f"    VID=0x{vid:04X}  PID=0x{pid:04X}  product={product}  manufacturer={mfr}")
    except Exception as e:
        print(f"  ❌ hid.enumerate() FAILED: {e}")
        traceback.print_exc()
else:
    print("  ⏭️  Skipped (hid not available)")

# ── 5. PyUSB Enumeration ─────────────────────────────────────────────
print("\n── 5. PYUSB ENUMERATION (usb.core.find) ──")
usb_devices = []
if usb_ok:
    try:
        found = list(usb.core.find(find_all=True))
        usb_devices = found
        print(f"  Total USB devices: {len(usb_devices)}")
        for d in usb_devices:
            vid = d.idVendor
            pid = d.idProduct
            try:
                product = usb.util.get_string(d, d.iProduct) if d.iProduct else "(none)"
            except Exception:
                product = "(unreadable)"
            try:
                mfr = usb.util.get_string(d, d.iManufacturer) if d.iManufacturer else "(none)"
            except Exception:
                mfr = "(unreadable)"
            print(f"    VID=0x{vid:04X}  PID=0x{pid:04X}  product={product}  manufacturer={mfr}")
    except Exception as e:
        print(f"  ❌ usb.core.find() FAILED: {e}")
        traceback.print_exc()
else:
    print("  ⏭️  Skipped (pyusb not available)")

# ── 6. Signature Match Check ─────────────────────────────────────────
print("\n── 6. SIGNATURE MATCH CHECK ──")

# Legacy KNOWN_DEVICES from gunner_hardware.py
LEGACY_KNOWN = {
    "retro_shooter_p1": (0x0483, 0x5750),
    "retro_shooter_p2": (0x0483, 0x5751),
    "retro_shooter_p3": (0x0483, 0x5752),
    "retro_shooter_p4": (0x0483, 0x5753),
    "sinden":           (0x16C0, 0x0F38),
    "aimtrak":          (0xD209, 0x1601),
    "gun4ir":           (0x2341, 0x8036),
}

# Multi-gun registry from gunner/hardware.py
MULTI_GUN_KNOWN = {
    "Sinden":                    (0x16C0, 0x05DF),
    "Gun4IR":                    (0x1209, 0xBEEF),
    "AIMTRAK":                   (0x1130, 0x1001),
    "Ultimarc U-HID":            (0xD209, 0x0301),
    "Wiimote IR Adapter":        (0x057E, 0x0306),
    "Mayflash NES Zapper":       (0x0079, 0x0006),
    "EMS TopGun":                (0x0B43, 0x0003),
    "Retro Shooter RS3 (1A86)":  (0x1A86, 0x5750),
    "Retro Shooter RS3 G2 (1A86)":(0x1A86, 0x5751),
    "Retro Shooter MX24 (1A86)": (0x1A86, 0x5752),
    "Retro Shooter RS3 (0483)":  (0x0483, 0x5750),
    "Retro Shooter RS3 G2 (0483)":(0x0483, 0x5751),
    "Generic HID":               (0x1BAD, 0xF016),
}

legacy_set = set(LEGACY_KNOWN.values())
multi_set = set(MULTI_GUN_KNOWN.values())

print("  Checking HID-enumerated devices against signature tables:")
if hid_ok and hid_devices:
    for d in hid_devices:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        pair = (vid, pid)
        in_legacy = pair in legacy_set
        in_multi = pair in multi_set
        if in_legacy or in_multi:
            legacy_name = next((k for k, v in LEGACY_KNOWN.items() if v == pair), None)
            multi_name = next((k for k, v in MULTI_GUN_KNOWN.items() if v == pair), None)
            print(f"    🔫 0x{vid:04X}:0x{pid:04X} → legacy={legacy_name or '❌ NOT FOUND'}  multi-gun={multi_name or '❌ NOT FOUND'}")
    # Check for any that match neither
    unmatched = [d for d in hid_devices
                 if (d.get("vendor_id",0), d.get("product_id",0)) not in legacy_set
                 and (d.get("vendor_id",0), d.get("product_id",0)) not in multi_set]
    if unmatched:
        print(f"    ({len(unmatched)} HID devices matched neither table - normal for non-gun USB devices)")
else:
    print("    (No HID devices to check)")

print("\n  Checking PyUSB-enumerated devices against signature tables:")
if usb_ok and usb_devices:
    for d in usb_devices:
        vid = d.idVendor
        pid = d.idProduct
        pair = (vid, pid)
        in_legacy = pair in legacy_set
        in_multi = pair in multi_set
        if in_legacy or in_multi:
            legacy_name = next((k for k, v in LEGACY_KNOWN.items() if v == pair), None)
            multi_name = next((k for k, v in MULTI_GUN_KNOWN.items() if v == pair), None)
            print(f"    🔫 0x{vid:04X}:0x{pid:04X} → legacy={legacy_name or '❌ NOT FOUND'}  multi-gun={multi_name or '❌ NOT FOUND'}")
    unmatched = [d for d in usb_devices
                 if (d.idVendor, d.idProduct) not in legacy_set
                 and (d.idVendor, d.idProduct) not in multi_set]
    if unmatched:
        print(f"    ({len(unmatched)} USB devices matched neither table - normal for non-gun USB devices)")
else:
    print("    (No USB devices to check or pyusb unavailable)")

# ── 7. Live API Test ──────────────────────────────────────────────────
print("\n── 7. LIVE API TEST (GET /api/local/gunner/devices) ──")
try:
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        "http://localhost:8000/api/local/gunner/devices",
        headers={"x-scope": "state", "x-panel": "gunner"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        print(f"  ✅ HTTP {resp.status}")
        print(f"  Response: {json.dumps(data, indent=2)}")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"  ❌ HTTP {e.code}: {body}")
except urllib.error.URLError as e:
    print(f"  ❌ Connection failed: {e.reason}")
    print("     (Is the backend running on port 8000?)")
except Exception as e:
    print(f"  ❌ Unexpected error: {e}")
    traceback.print_exc()

# ── 8. Detector Factory Test ──────────────────────────────────────────
print("\n── 8. DETECTOR FACTORY TEST ──")
try:
    # Add project to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backend.services.gunner_factory import detector_factory, get_detector_status
    status = get_detector_status()
    print(f"  Factory status: {json.dumps(status, indent=2)}")

    print("  Creating detector via factory...")
    detector = detector_factory()
    print(f"  ✅ Detector type: {type(detector).__name__}")

    print("  Calling detector.get_devices()...")
    devices = detector.get_devices()
    print(f"  ✅ Devices returned: {len(devices)}")
    for d in devices:
        print(f"    {d}")
except Exception as e:
    print(f"  ❌ Factory test FAILED:")
    traceback.print_exc()

print("\n" + "=" * 70)
print("  DIAGNOSTICS COMPLETE")
print("=" * 70)
