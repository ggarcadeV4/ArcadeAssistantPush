# Light Gun Games - Quick Reference

## How Gun Games Are Currently Set Up

### 1. Separate LaunchBox Platforms
Gun games are **NOT** configuration options—they are separate game collections:
- **Arcade MAME**: Regular MAME games (13,500+ games in Arcade MAME.xml)
- **MAME Gun Games**: Light gun arcade games (~200-300 games in MAME Gun Games.xml)
- **20 Total Gun Platforms** across all systems (Model 2, Dreamcast, TeknoParrot, etc.)

### 2. Same Emulator, Different Setup
- Both use `A:\Emulators\MAME\mame.exe` (same executable)
- Both use MAME command: `mame.exe -rompath [folder] [rom_name]`
- No special MAME parameters for gun games
- Difference is in **LaunchBox XML metadata** and **ROM collection**

### 3. Launch Priority (All Use Same Chain)
1. **Plugin Bridge** (localhost:9999) ← Most reliable
2. **Detected Emulator** (from LaunchBox config)
3. **Direct MAME** (when flag enabled, both regular and gun)
4. **LaunchBox.exe** ← Fallback

### 4. Backend Knows About Gun Games
**Platform Normalization** removes "Gun Games" suffix:
- `"MAME Gun Games"` → `"mame"` (for adapter matching)
- `"Model 2 Gun Games"` → `"model 2"`
- Allows same adapter to handle both variants

### 5. Gun-Specific Features (Limited)
Only **TeknoParrot** has dedicated gun support:
- AutoHotkey wrapper for input mapping
- Process killing to prevent multi-instance issues
- Title-to-profile aliasing via `teknoparrot-aliases.json`
- Profile routing via `routing-policy.json`

**MAME Gun Games:** No special features yet (future enhancement)

---

## Key Files

| File | Role | Handles Gun Games? |
|------|------|-------------------|
| `backend/services/launcher.py` | Launch orchestration | Yes (same as regular MAME) |
| `backend/services/adapters/teknoparrot_adapter.py` | TeknoParrot handling | Yes (full support) |
| `backend/services/platform_names.py` | Platform normalization | Yes (strips "Gun Games") |
| `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` | UI display | Yes (separate filter option) |
| `config/launchers.json` | MAME config | No (regular MAME only) |
| `A:\configs\routing-policy.json` | Gun profiles | Partial (TeknoParrot only) |

---

## ROM Path Issue (IMPORTANT)

**Current Code** (launcher.py:1137):
```python
if not rom_path.exists() and game.platform in ("Arcade", "Arcade MAME"):
    rom_path = LaunchBoxPaths.MAME_ROMS / f"{rom_name}.zip"
```

**Problem:** `"MAME Gun Games"` platform is **NOT** in this list!
- If gun game ROM path in XML is wrong, launch will fail
- Suggested fix: Add `"MAME Gun Games"` to the platform check

---

## 20 Gun Game Platforms

All have dedicated XMLs in `A:\LaunchBox\Data\Platforms\`:
1. American Laser Games
2. Atomiswave Gun Games
3. Dreamcast Gun Games
4. Flash Gun Games
5. Genesis Gun Games
6. **MAME Gun Games** ← The MAME variant
7. Master System Gun Games
8. Model 2 Gun Games
9. Model 3 Gun Games
10. Naomi Gun Games
11. NES Gun Games
12. PC Gun Games
13. PS2 Gun Games
14. PS3 Gun Games
15. PSX Gun Games
16. Saturn Gun Games
17. SNES Gun Games
18. TeknoParrot Gun Games
19. Wii Gun Games

---

## What Needs to Change for Full Gun Game Support

### Priority 1 (Bug Fix)
Add MAME Gun Games to ROM path fallback
```python
if not rom_path.exists() and game.platform in ("Arcade", "Arcade MAME", "MAME Gun Games"):
    # ... existing logic
```

### Priority 2 (Configuration)
Create `config/mame-gun.json` for gun-specific parameters:
```json
{
  "mame_gun": {
    "flags": ["-gun", "-gunaxis", "lightgun"],
    "overlay": "crosshair",
    "input_device": "Sinden"
  }
}
```

### Priority 3 (Profile Support)
Extend `routing-policy.json` to support MAME gun games:
```json
{
  "profiles": {
    "lightgun_mame": {
      "overlay_enabled": true,
      "calibration_mode": true
    }
  },
  "game_profiles": {
    "time_crisis": "lightgun_mame"
  }
}
```

### Priority 4 (UI Polish)
Add gun game indicators in LaunchBox panel:
- Light gun emoji/icon next to gun game titles
- Separate filter tab for gun games
- Hardware status display (Sinden/Gun4IR detected?)

---

## Testing Command

Direct MAME launch (for testing):
```bash
# Assuming gun ROM at A:\Roms\MAME\timetrap.zip
mame.exe -rompath A:\Roms\MAME\ timetrap

# With potential gun-specific flags (if supported by MAME version):
mame.exe -rompath A:\Roms\MAME\ -gun -gunaxis "crosshair" timetrap
```

---

## Questions to Answer

1. What is the exact path for MAME gun game ROMs? (`A:\Roms\MAME\` or `A:\Gun Build\Roms\`?)
2. Does this MAME version support `-gun` or similar light gun flags?
3. Is Sinden/Gun4IR hardware present? (If so, what device ID?)
4. Are gun games meant to use standard MAME config or separate config?
5. Does LaunchBox plugin handle gun setup internally?

