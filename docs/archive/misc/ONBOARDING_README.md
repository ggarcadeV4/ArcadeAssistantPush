# Onboarding README - LaunchBox LoRa Panel Session

**Date:** 2025-10-17
**Branch:** fix/launchbox-lora-regression
**Focus:** Finish LaunchBox launch sequences for all emulators
**Session Goal:** Complete ROM pairing and launch validation for DuckStation, Dolphin, Flycast, Model2, Supermodel, and remaining adapters

---

## Project Overview

Arcade Assistant is a multi-panel React + FastAPI application that manages an arcade cabinet with 15,000+ games across 53 platforms. The LaunchBox LoRa panel is the game library frontend that allows browsing, filtering, and launching games through multiple emulator backends.

### Architecture Stack
- **Frontend:** React 18 + Vite (localhost:8787)
- **Gateway:** Node.js Express BFF layer (localhost:8787)
- **Backend:** FastAPI Python (localhost:8888 or 8000 depending on launch method)
- **Drive:** A: drive contains LaunchBox, ROMs, emulators, BIOS files

---

## Current Status

### Completed Components ✅
1. **LaunchBox XML Parsing** - Parses 53 platform XMLs from `A:\LaunchBox\Data\Platforms\`
2. **REST API Endpoints** - Games, platforms, genres, random selection, stats
3. **Launch Fallback Chain** - Plugin → Detected → Direct → LaunchBox UI
4. **Mock Data Mode** - 15 games for development when AA_DRIVE_ROOT not set to A:
5. **MAME Integration** - Direct MAME launch for arcade games working
6. **RetroArch Adapter** - Console game launching via RetroArch cores
7. **PCSX2 Auto-Extract** - Automatic .zip/.7z extraction to temp for PS2 games
8. **Plugin Bridge** - C# LaunchBox plugin at localhost:9999 (primary launch method)

### In Progress Components ⏳
1. **DuckStation Adapter** - PS1 emulation (.cue/.chd/.bin resolution needed)
2. **Dolphin Adapter** - GameCube/Wii emulation (adapter exists, needs ROM pairing validation)
3. **Flycast Adapter** - Dreamcast emulation (.gdi preference, companion file resolution)
4. **Model2 Adapter** - Sega Model 2 arcade (zip extraction, correct ROM arg passing)
5. **Supermodel Adapter** - Sega Model 3 arcade (zip extraction, CLI arg handling)
6. **PPSSPP, MelonDS, Saturn, Daphne, PinballFX** - Adapters created but not registered yet

### Known Issues ⚠️
- CLI_Launcher.exe NOT FOUND (expected at `ThirdParty\CLI_Launcher\`) - using plugin bridge instead
- Master LaunchBox.xml NOT FOUND - parsing platform XMLs directly (works fine)
- Some adapters need `resolve_rom_for_launch()` implementation for proper file resolution
- Archive extraction needs testing for Model2/Supermodel .zip ROMs
- Adapter dry-run flag (`AA_ADAPTER_DRY_RUN`) for safe testing without actual launches

---

## Key Files to Understand

### Backend Core
- `backend/services/launcher.py` (1249 lines) - Main launch orchestration with fallback chain
- `backend/services/launcher_registry.py` (69 lines) - Adapter registration with feature flags
- `backend/routers/launchbox.py` - REST API endpoints for game library
- `backend/services/launchbox_cache.py` - In-memory game cache with XML parsing

### Emulator Adapters (backend/services/adapters/)
- `retroarch_adapter.py` - Multi-system libretro cores (enabled via AA_ALLOW_DIRECT_RETROARCH)
- `duckstation_adapter.py` - PS1 games (flag: AA_ENABLE_ADAPTER_DUCKSTATION)
- `dolphin_adapter.py` - GameCube/Wii (flag: AA_ENABLE_ADAPTER_DOLPHIN)
- `flycast_adapter.py` - Dreamcast (flag: AA_ENABLE_ADAPTER_FLYCAST)
- `model2_adapter.py` - Sega Model 2 (flag: AA_ENABLE_ADAPTER_MODEL2)
- `supermodel_adapter.py` - Sega Model 3 (flag: AA_ENABLE_ADAPTER_SUPERMODEL)
- `pcsx2_adapter.py` - PS2 games (flag: AA_ALLOW_DIRECT_PCSX2)
- `redream_adapter.py` - Dreamcast alternative (flag: AA_ALLOW_DIRECT_REDREAM)
- `teknoparrot_adapter.py` - Modern arcade (flag: AA_ALLOW_DIRECT_TEKNOPARROT)

### Frontend
- `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` - Main React UI
- `frontend/src/panels/launchbox/launchbox.css` - Panel styling

### Configuration
- `configs/launchers.json` - Emulator paths, flags, QoL settings
- `configs/routing-policy.json` - Launch method routing rules
- `.env` - Environment variables (AA_DRIVE_ROOT, feature flags)

---

## Today's Mission: Finish Launch Sequences

### Priority Tasks
1. **Review existing adapters** - Understand what's implemented vs what needs work
2. **Implement ROM resolution** - Each adapter needs proper file path resolution
3. **Handle archive extraction** - Model2/Supermodel need .zip extraction to temp
4. **Test dry-run mode** - Validate commands without actual launches (AA_ADAPTER_DRY_RUN=1)
5. **Add friendly error messages** - MISSING-EMU and MISSING-ROM with helpful hints
6. **Create verification script** - `scripts/verify_pairing.py` for dry-run testing

### ROM Pairing Requirements (from CODEX_CLAUDE_TODO.md)
Each adapter must implement `resolve_rom_for_launch()`:
- **PS1 (DuckStation):** Prefer .cue → .chd → .bin; temp-extract archives first
- **Flycast:** Prefer .gdi; ensure companion files resolved; extract archives first
- **Model2/Supermodel:** Temp-extract .zip; pass correct ROM arg to CLI
- **All adapters:** Log to `logs/launch_attempts.jsonl` with AA_LAUNCH_TRACE=1

---

## Development Workflow

### Starting the Stack
```bash
# Set A: drive root (or leave unset for mock data)
export AA_DRIVE_ROOT="A:\"

# Start backend (port 8888)
npm run dev:backend

# Start frontend + gateway (port 8787)
npm run dev
```

### Testing Launch Sequences
```bash
# Enable dry-run mode (no actual launches)
export AA_ADAPTER_DRY_RUN=1

# Enable launch tracing (logs to logs/launch_attempts.jsonl)
export AA_LAUNCH_TRACE=1

# Enable specific adapters
export AA_ENABLE_ADAPTER_DUCKSTATION=true
export AA_ENABLE_ADAPTER_DOLPHIN=true
export AA_ENABLE_ADAPTER_FLYCAST=true

# Test endpoint
curl -X POST http://localhost:8888/api/launchbox/launch/{game_id}
```

### Health Checks
```bash
# Backend health
curl http://localhost:8888/health

# LaunchBox stats
curl http://localhost:8888/api/launchbox/stats
```

---

## Adapter Development Pattern

Each adapter must implement:
```python
def can_handle(game: Game, manifest: dict) -> bool:
    """Returns True if this adapter can launch the game's platform."""
    pass

def resolve(game: Game, manifest: dict) -> dict:
    """Returns launch configuration: {exe, args, cwd, success, message}"""
    pass
```

Best practices:
1. Check if emulator exe exists before claiming `can_handle()`
2. Use `resolve_rom_path()` from `archive_utils` for alternate extensions
3. Call `extract_if_archive()` for .zip/.7z archives
4. Return temp cleanup callback via `extracted_root` in result dict
5. Provide helpful error messages when ROM/emulator not found
6. Respect `AA_ADAPTER_DRY_RUN` flag for testing

---

## Next Steps After This Session

1. Run `scripts/verify_pairing.py` for dry-run validation (3 titles per adapter)
2. Flip `AA_ADAPTER_DRY_RUN=0` and real-launch one title per adapter
3. Document any platform-specific quirks in CLAUDE.md
4. Update LAUNCHBOX_IMPLEMENTATION_SUMMARY.md with adapter status
5. Create smoke tests for each adapter
6. Consider Supabase persistence for launch stats

---

**Remember:** Always read CLAUDE.md and A_DRIVE_MAP.md before making changes! The A: drive structure is well-documented, and all paths should be verified against the actual file locations.
