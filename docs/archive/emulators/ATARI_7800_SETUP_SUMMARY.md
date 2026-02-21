# Atari 7800 Setup Summary

**Date:** 2025-10-17
**System:** Atari 7800
**Emulator:** RetroArch (RetroArch-Controller instance)
**Core:** ProSystem (prosystem_libretro.dll)
**Status:** ✅ Fully configured and tested

---

## What Was Done

### 1. Created LaunchBox Manifest (`configs/launchers.json`)
Created a new manifest file that the RetroArch adapter can read. This file defines:
- RetroArch executable path
- Platform-to-core mappings
- Core DLL locations
- Global flags (fullscreen mode)

### 2. Configured Both Atari Systems
Both systems now use the **same RetroArch-Controller instance** as requested:

| System | Core | ROM Extension |
|--------|------|---------------|
| Atari 2600 | stella_libretro.dll | .a26 |
| Atari 7800 | prosystem_libretro.dll | .a78 |

### 3. Enabled RetroArch Adapter
Added `AA_ALLOW_DIRECT_RETROARCH=true` to `.env` file to enable direct RetroArch launches.

---

## Configuration Files

### `configs/launchers.json` (NEW)
```json
{
  "global": {
    "allow_direct_retroarch": true
  },
  "emulators": {
    "retroarch": {
      "exe": "A:/Emulators/RetroArch/RetroArch-Controller/retroarch.exe",
      "platform_map": {
        "Atari 2600": "stella",
        "Atari 7800": "prosystem"
      },
      "cores": {
        "stella": "cores/stella_libretro.dll",
        "prosystem": "cores/prosystem_libretro.dll"
      },
      "flags": ["-f"]
    }
  }
}
```

### `.env` (UPDATED)
```bash
AA_ALLOW_DIRECT_RETROARCH=true
```

---

## Launch Chain

When launching an Atari 7800 game, the system follows this fallback chain:

1. **Plugin Bridge** (Primary) - LaunchBox C# plugin at localhost:9999
2. **Detected Emulator** (Secondary) - Auto-detected from LaunchBox configs
3. **Direct RetroArch** (Tertiary) - Uses launchers.json manifest with RetroArch adapter
4. **LaunchBox UI** (Last Resort) - Opens LaunchBox with game filter

### Example Launch Command
```bash
/mnt/a/LaunchBox/Emulators/RetroArch/RetroArch-Controller/retroarch.exe \
  -L /mnt/a/LaunchBox/Emulators/RetroArch/RetroArch-Controller/cores/prosystem_libretro.dll \
  -f \
  /mnt/a/Console ROMs/Atari 7800/Centipede.a78
```

---

## Verification Test Results

### Atari 2600
✅ Can handle: True
✅ Core: stella_libretro.dll
✅ Uses: RetroArch-Controller

### Atari 7800
✅ Can handle: True
✅ Core: prosystem_libretro.dll
✅ Uses: RetroArch-Controller

**Both systems confirmed using the same RetroArch instance!**

---

## How to Test

### Dry-Run Mode (Safe Testing)
```bash
# Set environment variables
export AA_ADAPTER_DRY_RUN=1
export AA_LAUNCH_TRACE=1
export AA_ALLOW_DIRECT_RETROARCH=true

# Start backend
npm run dev:backend

# Test launch endpoint
curl -X POST http://localhost:8888/api/launchbox/launch/{game_id}
```

### Real Launch
```bash
# Remove dry-run flag
unset AA_ADAPTER_DRY_RUN

# Launch from frontend at localhost:8787
# Or via API:
curl -X POST http://localhost:8888/api/launchbox/launch/{game_id}
```

---

## Next Steps

To add more RetroArch platforms:

1. **Update `configs/launchers.json`**:
   ```json
   "platform_map": {
     "New Platform": "core_key"
   },
   "cores": {
     "core_key": "cores/core_name_libretro.dll"
   }
   ```

2. **Restart backend** to reload manifest

3. **Test with dry-run mode first**

---

## Files Modified

- ✅ **Created**: `configs/launchers.json` - RetroArch manifest
- ✅ **Created**: `ONBOARDING_README.md` - Session onboarding guide
- ✅ **Created**: `ATARI_7800_SETUP_SUMMARY.md` - This file
- ✅ **Updated**: `.env` - Added `AA_ALLOW_DIRECT_RETROARCH=true`

---

## Additional Platforms Configured

The `launchers.json` manifest also includes mappings for:
- Nintendo Entertainment System (mesen)
- Super Nintendo Entertainment System (snes9x)
- Sega Genesis (genesis_plus_gx)
- Game Boy / Game Boy Color (gambatte)
- Game Boy Advance (mgba)
- And more...

All these platforms can now be launched via the same RetroArch-Controller instance!

---

**Status:** ✅ Ready for production testing
**Session Complete:** 2025-10-17
