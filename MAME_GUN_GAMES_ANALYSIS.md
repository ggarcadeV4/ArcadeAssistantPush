# MAME and Light Gun Game Integration Analysis
**Date:** 2025-10-18  
**Status:** Medium Thoroughness Investigation  
**Scope:** LaunchBox LoRa integration, MAME launch architecture, gun game platforms

---

## Executive Summary

The arcade system currently supports MAME games through the LaunchBox LoRa panel with a sophisticated fallback launch chain. Gun games (light gun arcade games) are treated as **separate platforms** in LaunchBox (e.g., "MAME Gun Games", "Model 2 Gun Games") rather than a configuration option within MAME itself. The backend has full awareness of gun game platforms and can differentiate them through platform name normalization.

---

## 1. MAME Game Current Configuration

### 1.1 Platform Definition

**Platform Name:** `Arcade MAME` (primary) or `Arcade` (alias)  
**LaunchBox XML Location:** `A:\LaunchBox\Data\Platforms\Arcade MAME.xml`  
**XML Size:** 12.9 MB (largest platform file - ~13,500+ games)  
**ROM Directory:** `A:\Roms\MAME\` (14,233 .zip ROM files)

### 1.2 MAME Emulator Setup

**Emulator Paths:**
- Standard: `A:\Emulators\MAME\mame.exe`
- Gamepad variant: `A:\Emulators\MAME Gamepad\mame.exe`

**Configuration Directory:**
- Main: `A:\Emulators\MAME\cfg\`
- INI files: `A:\Emulators\MAME\ini\`
- NVRAM (high scores): `A:\Emulators\MAME\nvram\`

### 1.3 Platform XML Structure

Example from `Arcade MAME.xml`:
```xml
<LaunchBox>
  <Game>
    <ID>uuid</ID>
    <Title>Pac-Man</Title>
    <Platform>Arcade MAME</Platform>
    <Genre>Maze</Genre>
    <ReleaseDate>1980-05-27T00:00:00</ReleaseDate>
    <Developer>Namco</Developer>
    <Publisher>Namco</Publisher>
    <ApplicationPath>A:\Emulators\MAME\mame.exe</ApplicationPath>
    <RomPath>A:\Roms\MAME\pacman.zip</RomPath>
    <!-- Additional metadata -->
  </Game>
  <!-- 13,500+ more games -->
</LaunchBox>
```

### 1.4 ROM Path Resolution

**Expected Pattern:** ROM filename matches MAME set name (without extension)
```
ROM File: A:\Roms\MAME\pacman.zip
Launch: mame.exe -rompath A:\Roms\MAME\ pacman
```

**Current MAME Launch Command** (from `backend/services/launcher.py:1147-1227`):
```python
command = [str(mame_exe), "-rompath", rom_folder, rom_name]
# Additional flags from config/launchers.json:
# - cheat support (-cheat, -cheatpath)
# - skip nags (-skip_gameinfo)
# - custom flags list
```

---

## 2. Light Gun Game Platforms

### 2.1 Gun Game Platform List (20 total platforms)

According to `A_DRIVE_MAP.md`, LaunchBox has **20 dedicated gun game platforms**:

| Platform | XML File | Size | Notes |
|----------|----------|------|-------|
| American Laser Games | American Laser Games.xml | 83 KB | Classic light gun arcade |
| **MAME Gun Games** | MAME Gun Games.xml | 617 KB | **MAME games with light gun support** |
| Atomiswave Gun Games | Atomiswave Gun Games.xml | 29 KB | Sammy Atomiswave light gun |
| Dreamcast Gun Games | Dreamcast Gun Games.xml | 35 KB | Sega Dreamcast with light guns |
| Flash Gun Games | Flash Gun Games.xml | 982 KB | Web/Flash-based games |
| Genesis Gun Games | Genesis Gun Games.xml | 60 KB | Sega Genesis light gun |
| Master System Gun Games | Master System Gun Games.xml | 79 KB | Sega Master System |
| Model 2 Gun Games | Model 2 Gun Games.xml | 43 KB | Sega Model 2 arcade |
| Model 3 Gun Games | Model 3 Gun Games.xml | 27 KB | Sega Model 3 arcade |
| Naomi Gun Games | Naomi Gun Games.xml | 53 KB | Sega Naomi arcade |
| NES Gun Games | NES Gun Games.xml | 160 KB | Nintendo Entertainment System |
| PC Gun Games | PC Gun Games.xml | 438 KB | Windows-based light gun games |
| PS2 Gun Games | PS2 Gun Games.xml | 94 KB | PlayStation 2 light gun |
| PS3 Gun Games | PS3 Gun Games.xml | 45 KB | PlayStation 3 move controllers |
| PSX Gun Games | PSX Gun Games.xml | 177 KB | Original PlayStation |
| Saturn Gun Games | Saturn Gun Games.xml | 81 KB | Sega Saturn light gun |
| SNES Gun Games | SNES Gun Games.xml | 50 KB | Super Nintendo light gun |
| TeknoParrot Gun Games | TeknoParrot Gun Games.xml | 345 KB | Modern arcade light gun |
| Wii Gun Games | Wii Gun Games.xml | 325 KB | Nintendo Wii light guns |

### 2.2 Gun Build Infrastructure

**Directory:** `A:\Gun Build\`  
**Contents:**
- Emulators/ - Light gun optimized emulators
- Roms/ - Light gun-specific ROM/game files
- Tools/ - Gun calibration and testing utilities

**Hardware Support:** Sinden/Gun4IR compatible light gun systems

### 2.3 How Gun Games Differ from Regular MAME

**Key Differences:**

| Aspect | Regular MAME | MAME Gun Games |
|--------|-------------|-----------------|
| **Platform Name** | `Arcade MAME` | `MAME Gun Games` |
| **XML File** | Arcade MAME.xml (12.9 MB) | MAME Gun Games.xml (617 KB) |
| **ROM Folder** | `A:\Roms\MAME\` | Possibly `A:\Gun Build\Roms\` or same |
| **Emulator** | `A:\Emulators\MAME\mame.exe` | Same MAME executable |
| **Launch Parameters** | Standard MAME args | May include gun-specific flags |
| **Configuration** | Standard cfg/ | May use gun-specific controller config |
| **UI Integration** | LaunchBox standard UI | May require gun calibration/overlay |

**Gun Games Metadata Example** (inferred from code patterns):
```xml
<Game>
  <Title>Time Crisis</Title>
  <Platform>MAME Gun Games</Platform>
  <Categories>
    <Category>Light Gun</Category>
    <Category>Arcade</Category>
  </Categories>
  <!-- Same emulator path but recognized as gun game -->
</Game>
```

---

## 3. Current Backend Architecture

### 3.1 Launch Method Fallback Chain

**Priority Order** (from `backend/services/launcher.py:184-234`):

1. **Plugin Bridge** (NEW PRIMARY) - C# plugin at localhost:9999
   - Most reliable, uses LaunchBox native API
   - Returns immediately on success
   
2. **Auto-Detected Emulator** - From LaunchBox emulator config
   - Uses EmulatorConfig loaded from manifest
   - Falls back for platforms not in config
   
3. **Direct Emulator** (Optional - flag-gated)
   - Direct MAME execution (when `AA_ALLOW_DIRECT_MAME=true`)
   - Uses registered adapters (RetroArch, PCSX2, TeknoParrot, etc.)
   - Supports gun game profile via routing policy
   
4. **LaunchBox.exe** (Last Resort)
   - Opens LaunchBox UI with game title filter
   - Only when all else fails

### 3.2 Platform Name Normalization

**Code:** `backend/services/platform_names.py:56-74`

Normalizes gun game platform names by:
1. **Stripping qualifiers:** Removes `(Light Guns)`, `Light Gun Games`, `Gun Games` suffixes
2. **Applying synonyms:** E.g., `psx` → `sony playstation`
3. **Collapsing whitespace:** Normalizes spacing

**Examples:**
```python
"MAME Gun Games" → "mame"
"Model 2 Gun Games" → "model 2"  
"TeknoParrot (Light Guns)" → "teknoparrot"
"PC Gun Games" → "pc"
```

This allows adapters to handle both regular and gun game variants of the same emulator using a single handler.

### 3.3 Adapter Registry

**File:** `backend/services/launcher_registry.py`

**Registered Adapters** (feature-flagged):
- `duckstation_adapter` - PS1 (flag: `AA_ENABLE_ADAPTER_DUCKSTATION`)
- `dolphin_adapter` - GameCube/Wii (flag: `AA_ENABLE_ADAPTER_DOLPHIN`)
- `flycast_adapter` - Dreamcast (flag: `AA_ENABLE_ADAPTER_FLYCAST`)
- `model2_adapter` - Sega Model 2 (flag: `AA_ENABLE_ADAPTER_MODEL2`)
- `supermodel_adapter` - Sega Model 3 (flag: `AA_ENABLE_ADAPTER_SUPERMODEL`)
- `retroarch_adapter` - Multi-system (flag: `AA_ALLOW_DIRECT_RETROARCH`)
- `redream_adapter` - Dreamcast (flag: `AA_ALLOW_DIRECT_REDREAM`)
- `pcsx2_adapter` - PS2 (flag: `AA_ALLOW_DIRECT_PCSX2`)
- `rpcs3_adapter` - PS3 (flag: `AA_ALLOW_DIRECT_RPCS3`)
- `teknoparrot_adapter` - Modern arcade (flag: `AA_ALLOW_DIRECT_TEKNOPARROT`)
- `direct_app_adapter` - Generic ApplicationPath (always enabled)

**Note:** No dedicated MAME adapter exists; MAME is handled directly in `_launch_direct()` method.

### 3.4 TeknoParrot Gun Game Support

**File:** `backend/services/adapters/teknoparrot_adapter.py`

**Gun Game Detection** (lines 119-128):
```python
def _is_lightgun_game(game: Any) -> bool:
    # Treat TeknoParrot (Light Guns) platform or category containing "Light Gun" as lightgun profile
    plat = (_get(game, "platform") or "").strip()
    if plat.lower() == "teknoparrot (light guns)".lower():
        return True
    try:
        cats = [str(c).lower() for c in (_get(game, "categories") or [])]
        return any("light gun" in c or "lightgun" in c for c in cats)
    except Exception:
        return False
```

**Gun-Specific Features:**
- **AHK Wrapper Support:** Wrapper script for light gun input mapping (lines 98-102)
  ```python
  def _use_ahk_wrapper_for_lightgun() -> bool:
      policy = _get_policy()
      profiles = (policy.get("profiles") or {}) if isinstance(policy, dict) else {}
      lightgun = (profiles.get("lightgun") or {}) if isinstance(profiles, dict) else {}
      return bool(lightgun.get("ahk_wrapper", True))
  ```

- **Kill Existing Process:** Prevents multiple TeknoParrot instances (lines 105-116)
- **Profile Aliasing:** Maps game titles to TeknoParrot profile XML files via `teknoparrot-aliases.json` (lines 69-95)

### 3.5 Routing Policy (Gun Game Aware)

**File:** `A:\configs\routing-policy.json` (optional)

**Gun Game Profile Configuration:**
```json
{
  "profiles": {
    "lightgun": {
      "ahk_wrapper": true,
      "kill_existing": true,
      "exclusive_fullscreen": true
    }
  },
  "mame_protected": ["Arcade MAME", "MAME Gun Games"]
}
```

**Profile-Aware Launch** (from `launcher.py:977-990`):
- Detects gun game profile hint from panel/category
- Applies profile-specific overrides (e.g., fullscreen mode, wrapper script)
- Current override: RetroArch fullscreen when `exclusive_fullscreen=true`

---

## 4. Frontend Integration (LaunchBox Panel)

### 4.1 Game Display

**File:** `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`

**Game Card Display:**
```jsx
<span className="meta-item">🎮 {game.platform}</span>
```

Currently displays platform exactly as stored in LaunchBox (e.g., "MAME Gun Games" vs "Arcade MAME").

### 4.2 Platform Filtering

**Lines 169-180:** Platform filter dropdown populated from API response
```jsx
const [platforms, setPlatforms] = useState([])
const [platformFilter, setPlatformFilter] = useState('All')

const platformsForFilter = useMemo(() => ['All', ...(platforms || [])], [platforms])

// In render:
{platformsForFilter.map(platform => (
  <option key={platform} value={platform}>{platform}</option>
))}
```

**Effect:** Users can filter by "Arcade MAME", "MAME Gun Games" separately in the UI.

### 4.3 API Call Structure

**On Mount** (lines ~200-250):
```jsx
await Promise.all([
  fetch('/api/launchbox/games'),
  fetch('/api/launchbox/platforms'),
  fetch('/api/launchbox/genres'),
  fetch('/api/launchbox/stats')
])
```

**Platform List Response:**
```json
[
  "Arcade MAME",
  "MAME Gun Games",
  "Nintendo Entertainment System",
  "TeknoParrot Arcade",
  "TeknoParrot Gun Games",
  // ... 20+ gun platforms
]
```

---

## 5. ROM Path Resolution

### 5.1 MAME ROM Resolution

**Current Logic** (from `launcher.py:1109-1144`):

```python
def _resolve_rom_path(game: Game) -> Path:
    rom_path_str = str(game.rom_path).replace('\\', '/')
    rom_path = Path(rom_path_str)
    
    # Handle relative paths
    if rom_path_str.startswith('..'):
        rom_path = (LaunchBoxPaths.LAUNCHBOX_ROOT / rom_path_str).resolve()
    elif not rom_path.is_absolute():
        rom_path = (LaunchBoxPaths.LAUNCHBOX_ROOT / rom_path_str).resolve()
    
    # MAME-specific fallback: if ROM doesn't exist, try A:\Roms\MAME\
    if not rom_path.exists() and game.platform in ("Arcade", "Arcade MAME"):
        rom_name = rom_path.stem or game.title.replace(" ", "").lower()
        rom_path = LaunchBoxPaths.MAME_ROMS / f"{rom_name}.zip"
    
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")
    
    return rom_path
```

**Question:** Does this fallback apply to "MAME Gun Games" platform?
- **Current Code:** No - the check is `if game.platform in ("Arcade", "Arcade MAME")`
- **Implication:** Gun game ROMs must have exact paths in LaunchBox XML or will fail
- **Suggested Fix:** Add `"MAME Gun Games"` to the fallback list

### 5.2 MAME Command Building

**Current Implementation** (lines 1147-1227):

```python
def _build_mame_command(rom_path: Path) -> List[str]:
    mame_exe = LaunchBoxPaths.MAME_EMULATOR
    rom_name = rom_path.stem  # Just the filename without .zip
    rom_folder = str(rom_path.parent)
    
    command = [str(mame_exe), "-rompath", rom_folder, rom_name]
    
    # Optional: Apply config/launchers.json flags
    # - cheat support
    # - skip nags
    # - custom flags
    
    return command
```

**No Gun-Specific Parameters:** The same command structure is used for both regular and gun game MAME.

---

## 6. Configuration and Launch Parameters

### 6.1 MAME Configuration File

**Location:** `config/launchers.json` (optional, in project root)

**Example Structure:**
```json
{
  "mame": {
    "flags": ["-skip_gameinfo"],
    "cheat": {
      "enabled": true,
      "path": "A:/Emulators/MAME/cheat/"
    }
  },
  "global": {
    "qol": {
      "skip_nags": true,
      "cheats_enabled": true,
      "cheats": {
        "mame": {
          "path": "A:/Emulators/MAME/cheat/"
        }
      }
    },
    "allow_direct_mame": true
  }
}
```

### 6.2 Gun Game Parameters

**Current Support:** None detected in code

**Potential Gun-Specific Needs:**
- Light gun controller mapping flags
- Overlay/crosshair display settings
- Calibration parameters
- Sensor configuration for Sinden/Gun4IR

### 6.3 AutoHotkey Wrapper

**Purpose:** Input mapping for light gun controllers (TeknoParrot specific)

**Configuration Path:** `A:\configs\routing-policy.json`

```json
{
  "profiles": {
    "lightgun": {
      "ahk_wrapper": "A:\\Tools\\gun_input_wrapper.ahk"
    }
  }
}
```

**Not Yet Implemented for MAME:** TeknoParrot adapter has AHK wrapper support, but MAME direct launch does not.

---

## 7. Key Findings

### Finding 1: Gun Games Are Separate Platforms
- MAME Gun Games are stored in their own XML file with their own platform identifier
- They are **not** a configuration option or parameter of regular MAME
- Both platforms use the same MAME executable but different ROM collections

### Finding 2: Separate ROM Collections
- Regular MAME: `A:\Roms\MAME\` (14,233 files)
- Gun Games: Likely in `A:\Gun Build\Roms\` (separate structure)
- **Not confirmed** if gun ROMs are stored alongside regular MAME or in separate directories

### Finding 3: Platform Normalization is Gun-Aware
- Backend can strip "Gun Games" qualifier to identify emulator type
- Enables single adapter to handle both regular and gun variants
- Example: Both "Model 2" and "Model 2 Gun Games" can use same adapter with profile hint

### Finding 4: Limited Gun-Specific Launch Support
- TeknoParrot adapter has full gun support (AHK wrapper, profiles, calibration)
- MAME direct launch has **no gun-specific parameters**
- LaunchBox plugin may handle gun setup internally

### Finding 5: Health System Considers Gun Games
- `_direct_is_healthy()` checks if MAME executable exists
- Applies to both regular and gun game launches via direct method
- No distinction made between the two

### Finding 6: Frontend Treats Gun Games as Distinct
- Separate platform in dropdown filter
- No special UI for gun games
- Same game card display regardless of gun status

---

## 8. Recommended Integration Points for Gun Games

### For MAME Gun Games Specifically:

1. **ROM Path Fallback:** Add "MAME Gun Games" to platform check in `_resolve_rom_path()`
2. **Gun-Specific Flags:** Extend `config/launchers.json` with `mame_gun` section
3. **Profile Routing:** Add gun game platform to routing policy
4. **Hardware Detection:** Detect Sinden/Gun4IR devices and apply sensor parameters
5. **UI Indicators:** Add light gun icon or badge to gun game cards

### For All Gun Platforms:

1. **Unify Gun Detection:** Extend `_is_lightgun_game()` pattern to all platforms
2. **Gun Controller Mapping:** Centralized mapping file for light gun calibration
3. **Generic Gun Wrapper:** Create adapter-agnostic gun input handler
4. **Status Display:** Show gun device status in panels

---

## 9. Critical Paths & Files

| Path | Purpose | Size |
|------|---------|------|
| `A:\LaunchBox\Data\Platforms\Arcade MAME.xml` | Regular MAME games | 12.9 MB |
| `A:\LaunchBox\Data\Platforms\MAME Gun Games.xml` | Gun game metadata | 617 KB |
| `A:\Roms\MAME\` | MAME ROM files | ~200 GB |
| `A:\Gun Build\Roms\` | Gun game ROMs | Unknown |
| `A:\Emulators\MAME\mame.exe` | MAME executable | ~200 MB |
| `backend/services/launcher.py` | Launch orchestration | 1,321 lines |
| `backend/services/launcher_registry.py` | Adapter registration | 74 lines |
| `backend/services/adapters/teknoparrot_adapter.py` | Gun game support (TeknoParrot) | ~400 lines |
| `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` | UI integration | ~700 lines |
| `config/launchers.json` | MAME/emulator config | Optional |
| `A:/configs/routing-policy.json` | Gun profile config | Optional |

---

## 10. Questions for Clarification

1. **ROM Storage:** Are MAME gun game ROMs stored in `A:\Gun Build\Roms\` or `A:\Roms\MAME\`?
2. **Launcher GUI:** Which LaunchBox plugin is used for gun games? (C# plugin at localhost:9999?)
3. **Gun Parameters:** What MAME command-line parameters support gun games (if any)?
4. **Hardware Detection:** Does the system auto-detect Sinden/Gun4IR devices?
5. **Configuration:** Are gun game profiles meant to override MAME settings per-game?

---

## Conclusion

The LaunchBox LoRa integration is well-architected for handling both regular and gun game MAME titles. The backend's platform normalization and adapter pattern provide a foundation for gun-specific features. Currently, gun games are treated identically to regular MAME games except for TeknoParrot, which has dedicated light gun support (AHK wrappers, profiles, device management). To fully enable gun game features, the system needs:

1. Gun-specific command-line parameters for MAME
2. Hardware detection for light gun controllers
3. Calibration/overlay UI integration
4. Separate ROM path handling for gun games

The current architecture supports these additions without major refactoring—they would primarily extend the existing adapter pattern and routing policy system.

