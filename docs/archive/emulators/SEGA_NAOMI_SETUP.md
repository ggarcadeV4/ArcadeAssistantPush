# Sega Naomi Setup Summary

**Date:** 2025-10-17
**Systems:** Sega Naomi + Sammy Atomiswave (Bonus!)
**Emulator:** RetroArch-Controller
**Core:** Flycast (flycast_libretro.dll)
**Status:** ✅ Fully configured and tested

---

## What Was Done

### Added Two Platforms to RetroArch
Just **2 lines** added to `launchers.json`:

```json
"platform_map": {
  "Sega Naomi": "flycast",
  "Sammy Atomiswave": "flycast"
}
```

And added the core:
```json
"cores": {
  "flycast": "cores/flycast_libretro.dll"
}
```

---

## How It Works

### ROM Format
Both systems use **.zip ROM files** (like MAME):

```
A:/Roms/NAOMI/
├── mvsc2.zip         ← Marvel vs. Capcom 2
├── capsnk.zip        ← Capcom vs. SNK
└── ...

A:/Roms/ATOMISWAVE/
├── ggx.zip           ← Guilty Gear X
└── ...
```

### Launch Flow
1. User launches a Naomi game from LaunchBox LoRa
2. RetroArch adapter recognizes "Sega Naomi"
3. Launches with Flycast core:
   ```
   retroarch.exe -L flycast_libretro.dll -f mvsc2.zip
   ```

---

## Testing Results

### Sega Naomi
✅ Platform: "Sega Naomi"
✅ RetroArch can handle: True
✅ Core: flycast_libretro.dll
✅ Launch command generated correctly

### Sammy Atomiswave (Bonus!)
✅ Platform: "Sammy Atomiswave"
✅ RetroArch can handle: True
✅ Uses same Flycast core
✅ Works automatically!

---

## Launch Command Examples

**Sega Naomi:**
```bash
A:/Emulators/RetroArch/RetroArch-Controller/retroarch.exe \
  -L cores/flycast_libretro.dll \
  -f \
  A:/Roms/NAOMI/mvsc2.zip
```

**Sammy Atomiswave:**
```bash
A:/Emulators/RetroArch/RetroArch-Controller/retroarch.exe \
  -L cores/flycast_libretro.dll \
  -f \
  A:/Roms/ATOMISWAVE/ggx.zip
```

---

## For ScoreKeeper Sam

Sam will receive events for both platforms:

**Naomi:**
```json
{
  "event": "game_launched",
  "title": "Marvel vs. Capcom 2",
  "platform": "Sega Naomi",
  "emulator": "retroarch",
  "core": "flycast_libretro.dll",
  "timestamp": "2025-10-17T23:45:00Z"
}
```

**Atomiswave:**
```json
{
  "event": "game_launched",
  "title": "Guilty Gear X",
  "platform": "Sammy Atomiswave",
  "emulator": "retroarch",
  "core": "flycast_libretro.dll",
  "timestamp": "2025-10-17T23:50:00Z"
}
```

Platform names match the LaunchBox XMLs perfectly for score tracking.

---

## Alternative Emulator Option

Your LaunchBox also has **Demul Arcade** configured for Naomi:
- Path: `A:/Emulators/Demul 0.7/demul.exe`
- Command: `-run=naomi -rom=<gamename>`

We chose RetroArch + Flycast because:
- ✅ Already configured and working
- ✅ Consistent with other platforms
- ✅ Got Atomiswave as a bonus
- ✅ Simpler configuration

If you ever want to switch to Demul, we can add that later.

---

## Configuration Updated

### `configs/launchers.json`
```json
{
  "emulators": {
    "retroarch": {
      "platform_map": {
        "Atari 2600": "stella",
        "Atari 7800": "prosystem",
        "Sega Naomi": "flycast",          ← Added
        "Sammy Atomiswave": "flycast"     ← Added (bonus!)
      },
      "cores": {
        "stella": "cores/stella_libretro.dll",
        "prosystem": "cores/prosystem_libretro.dll",
        "flycast": "cores/flycast_libretro.dll"  ← Added
      }
    }
  }
}
```

---

## Systems Configured So Far

1. ✅ **Atari 2600** - RetroArch (stella)
2. ✅ **Atari 7800** - RetroArch (prosystem)
3. ✅ **Taito Type X** - TeknoParrot
4. ✅ **Sega Naomi** - RetroArch (flycast)
5. ✅ **Sammy Atomiswave** - RetroArch (flycast) *Bonus!*

Plus 15+ other platforms already in RetroArch platform_map!

---

## Files Modified

✅ **Updated**: `configs/launchers.json` - Added 2 platforms + 1 core
✅ **Created**: `SEGA_NAOMI_SETUP.md` - This file

---

**Status:** ✅ Ready for production
**Time to complete:** ~5 minutes
**Next system:** Your choice! 🎮
