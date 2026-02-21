# MAME & Light Gun Games Exploration - Document Index

**Date:** October 18, 2025  
**Thoroughness Level:** Medium  
**Status:** Complete with 3 detailed reports

## Documents Created

### 1. MAME_GUN_GAMES_ANALYSIS.md (18 KB) - COMPREHENSIVE REFERENCE
**Purpose:** Deep technical analysis of MAME and gun game architecture  
**Audience:** Developers, architects, technical decision-makers  
**Contents:**
- Executive summary
- MAME current configuration (platform, emulator, ROM paths)
- 20 light gun game platforms with detailed comparison table
- 5-section backend architecture breakdown
- Frontend integration details
- ROM path resolution and command building
- Configuration system and parameters
- 7 key findings with implications
- 8 recommended integration points
- 9 critical paths and file locations
- 10 clarification questions for implementation

**Best for:** Understanding the complete system, identifying integration points, planning enhancements

---

### 2. GUN_GAMES_QUICK_REFERENCE.md (4.7 KB) - ONE-PAGE GUIDE
**Purpose:** Fast lookup guide for gun game setup  
**Audience:** Developers implementing features, quick reference during coding  
**Contents:**
- How gun games are currently set up (5 key points)
- Key files and their roles (table)
- Identified ROM path bug and fix
- List of 20 gun game platforms
- Priority-ordered implementation roadmap (4 levels)
- Testing command examples
- 5 clarification questions

**Best for:** Quick answers, implementation checklists, bug fixes

---

### 3. GUN_GAMES_ARCHITECTURE.txt (11 KB) - ASCII DIAGRAM & FLOWCHARTS
**Purpose:** Visual reference for system architecture  
**Audience:** Visual learners, system designers, documentation  
**Contents:**
- LaunchBox data layer structure
- Emulator layer configuration
- Backend launch chain flowchart
- MAME command building diagram
- Platform detection & normalization table
- Gun game support matrix (all 20 platforms)
- ROM path resolution logic code
- Frontend integration flow
- Configuration file structure
- Adapter registry listing
- Identified issues with fixes
- Priority-ordered recommendations

**Best for:** System overview, understanding data flow, architecture presentations

---

## Quick Links to Source Code

### Backend (Python)
- **Launcher Orchestration:** `/backend/services/launcher.py` (1,321 lines)
  - `_launch_via_plugin()` - C# plugin bridge (lines 547-591)
  - `_launch_direct()` - Direct emulator (lines 859-1032)
  - `_build_mame_command()` - MAME command building (lines 1147-1227)
  - `_resolve_rom_path()` - ROM path resolution (lines 1109-1144)
  - **BUG LOCATION:** Line 1137 - Missing "MAME Gun Games" in fallback

- **Launcher Registry:** `/backend/services/launcher_registry.py` (74 lines)
  - Adapter registration system
  - 11 total adapters (feature-flagged)
  - No dedicated MAME adapter

- **TeknoParrot Adapter:** `/backend/services/adapters/teknoparrot_adapter.py` (~400 lines)
  - `_is_lightgun_game()` (lines 119-128) - Gun detection pattern
  - `_use_ahk_wrapper_for_lightgun()` (lines 98-102) - AHK wrapper support
  - Profile aliasing and routing

- **Platform Names:** `/backend/services/platform_names.py` (75 lines)
  - `normalize_key()` (lines 56-74) - Gun-aware platform normalization

### Frontend (React/JavaScript)
- **LaunchBox Panel:** `/frontend/src/panels/launchbox/LaunchBoxPanel.jsx` (~700 lines)
  - Platform filtering (lines 169-180)
  - API integration (lines ~200-250)
  - Game card display with platform info

### Configuration
- **Launcher Config:** `config/launchers.json` (optional)
  - MAME configuration section
  - Global toggles (allow_direct_mame)
  - Cheat support settings

- **Routing Policy:** `A:\configs\routing-policy.json` (optional)
  - Gun game profiles (profiles.lightgun)
  - MAME protection rules (mame_protected)
  - Profile aliasing

---

## Key Findings Summary

### Finding 1: Gun Games Are Separate Platforms
- Not configuration options but distinct LaunchBox platforms
- 20 dedicated gun platforms (one per system type)
- Separate XML files but same emulator executables

### Finding 2: Unified Launch Chain
- All games use same 4-method fallback priority
- No special launch method for gun games
- Plugin bridge is most reliable (localhost:9999)

### Finding 3: Platform Normalization Handles Guns
- Backend strips "Gun Games" suffix for adapter matching
- Same adapter can handle regular + gun variants
- Example: Both "Model 2" and "Model 2 Gun Games" match same adapter

### Finding 4: Limited Gun Support Currently
- Only TeknoParrot has full gun features (AHK wrapper, profiles)
- MAME gun games use same parameters as regular MAME (no gun flags)
- TeknoParrot adapter: 350 lines, MAME adapter: 0 lines

### Finding 5: Critical Bug Found
- ROM path fallback missing "MAME Gun Games" platform
- Will fail if LaunchBox XML path is incorrect
- **Fix:** Add one platform name to line 1137

---

## Implementation Roadmap

### Priority 1 - URGENT BUG FIX
**Estimated Time:** 5 minutes  
**Files:** `backend/services/launcher.py:1137`  
**Change:** Add "MAME Gun Games" to platform check
```python
if game.platform in ("Arcade", "Arcade MAME", "MAME Gun Games"):
```
**Validation:** Test with gun game that has missing ROM

---

### Priority 2 - CONFIGURATION (SOON)
**Estimated Time:** 1-2 hours  
**Files:** 
- Create `config/mame-gun.json`
- Update `launcher.py:_build_mame_command()`

**Tasks:**
- Identify which MAME flags support light guns
- Map hardware (Sinden/Gun4IR) to configuration
- Create per-game profile mapping

---

### Priority 3 - ROUTING POLICY (SOON)
**Estimated Time:** 1 hour  
**Files:** `A:\configs\routing-policy.json`

**Tasks:**
- Add lightgun profile for MAME games
- Define per-game profile mappings
- Set up hardware detection rules

---

### Priority 4 - UI POLISH (LATER)
**Estimated Time:** 2-3 hours  
**Files:** `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`

**Tasks:**
- Add gun game icons/badges
- Create separate filter tab for gun games
- Display hardware status

---

### Priority 5 - HARDWARE SUPPORT (LATER)
**Estimated Time:** 4-8 hours  
**Files:** New files needed

**Tasks:**
- Auto-detect Sinden/Gun4IR devices
- Implement calibration UI
- Per-game device mapping
- Create unified gun input wrapper

---

## Clarification Questions

These need to be answered before full implementation:

1. **ROM Storage:** Where are MAME gun game ROMs? (`A:\Roms\MAME\` vs `A:\Gun Build\Roms\`?)
2. **MAME Flags:** What MAME parameters support light guns? (`-gun`, `-gunaxis`, etc.?)
3. **Hardware:** Is Sinden/Gun4IR hardware present? What device IDs?
4. **Configuration:** Should gun games use separate config or extend standard config?
5. **Plugin:** Does LaunchBox C# plugin handle gun setup internally?

---

## How to Use These Documents

**If you need to...**
- **...understand the full system** → Read MAME_GUN_GAMES_ANALYSIS.md (15 min)
- **...implement a quick fix** → Use GUN_GAMES_QUICK_REFERENCE.md (5 min)
- **...visualize the architecture** → Reference GUN_GAMES_ARCHITECTURE.txt (10 min)
- **...track a bug** → Look at Finding #5 and Priority 1 in this index
- **...plan enhancements** → Follow the Implementation Roadmap above
- **...understand data flow** → Study the ASCII flowcharts in ARCHITECTURE.txt

---

## Document Statistics

| Document | Lines | Size | Focus |
|----------|-------|------|-------|
| MAME_GUN_GAMES_ANALYSIS.md | ~450 | 18 KB | Deep analysis, code examples |
| GUN_GAMES_QUICK_REFERENCE.md | ~120 | 4.7 KB | Quick lookup, checklists |
| GUN_GAMES_ARCHITECTURE.txt | ~250 | 11 KB | Visual diagrams, flowcharts |
| **TOTAL** | **~820** | **~34 KB** | Complete reference set |

---

## Next Steps

1. **Read the summary above** (5 minutes)
2. **Choose your document based on need** (see "How to Use" section)
3. **Review the Implementation Roadmap** for timeline
4. **Answer the Clarification Questions** before starting Priority 2+
5. **Start with Priority 1 bug fix** for immediate win

---

## Document Version History

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2025-10-18 | Claude Code | Initial comprehensive exploration |

---

**Total Investigation Time:** ~2 hours at medium thoroughness level  
**Files Analyzed:** 15+ Python files, 3 JS files, configuration files, XML structures  
**Code References:** 50+ specific line numbers with context  
**Platforms Documented:** 50+ unique platforms, 20 gun variants  
**Critical Issues Found:** 1 bug, 2 missing features  

---

