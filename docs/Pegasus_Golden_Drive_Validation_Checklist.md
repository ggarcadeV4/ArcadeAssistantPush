# Pegasus Golden Drive Validation Checklist

> **Purpose:** Structured checklist for a human operator to validate that Pegasus is correctly configured and functioning on a Golden Drive.  
> **Scope:** Pegasus behavior, launch reliability, metadata, artwork, and boot assumptions.  
> **Out of Scope:** New features, refactors, Scorekeeper Sam Phase 4, emulator config changes.

---

## 1. Prerequisites

Before running validation, ensure:

- [ ] Arcade Assistant backend is running (`npm start` or `npm run dev`)
- [ ] Gateway is responding on port 8787
- [ ] Backend is responding on port 8000
- [ ] The A: drive is connected and accessible

**How to verify:**
```cmd
netstat -ano | findstr ":8787"
netstat -ano | findstr ":8000"
dir A:\Tools\Pegasus
```

**Pass:** All three ports show LISTENING; Pegasus directory exists.  
**Regression indicator:** Port not listening, or A: drive not mounted.

---

## 2. Pegasus Launches Successfully

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| Pegasus executable runs | Launch `A:\Tools\Pegasus\pegasus-fe.exe` | Pegasus UI appears fullscreen with theme loaded | Crash, black screen, or error dialog |
| Theme loads correctly | Observe UI after launch | XboxOS theme (or configured theme) displays with navigation | Default/broken theme, no artwork |
| Game library visible | Navigate with controller or keyboard | Games appear organized by platform | Empty collections, "No games found" |

---

## 3. Launch Pipeline (Critical Path)

### 3.1 Bridge Script Execution

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| Wrapper script exists | `dir A:\Tools\aa_pegasus.bat` | File exists | File missing |
| Wrapper script callable | Run manually: `A:\Tools\aa_pegasus.bat "Air Raid" "Atari 2600"` | No "not recognized" error; game attempts to launch | "not recognized as a command" error |
| Log file created | `type "A:\Arcade Assistant Local\logs\pegasus_launch.log"` | Log shows HTTP response and game title | Log missing or empty |

### 3.2 Game Launch End-to-End

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| RetroArch game launches from Pegasus | Select any NES/SNES/Atari game, press launch | Emulator opens, game plays | "Boot loop" (Pegasus regains control immediately) |
| MAME game launches from Pegasus | Select any Arcade game, press launch | MAME opens, game plays | Boot loop or silent failure |
| TeknoParrot game launches (if applicable) | Select a TeknoParrot game, press launch | TeknoParrot loader opens, game plays | Boot loop or error popup |
| Plugin bridge used (not direct launch) | Check backend logs after launch | Log shows "plugin_first policy" for Pegasus | Log shows "direct_only" or no policy message |

**Manual test command:**
```cmd
A:\Tools\aa_pegasus.bat "Game Title Here" "Platform Name"
```

---

## 4. Metadata Integrity

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| Metadata files exist | `dir A:\Tools\Pegasus\metadata\*\metadata.pegasus.txt` | Files exist for all 50 platforms | Missing platform folders |
| Launch command format correct | Open any `metadata.pegasus.txt`, find `launch:` line | Points to `A:\Tools\aa_pegasus.bat` | Points to broken path with spaces, or old script |
| No C: drive paths | `findstr /s /i "C:\\" A:\Tools\Pegasus\metadata\*` | No results | Any match = dev path leaked |
| No dev usernames | `findstr /s /i "Users" A:\Tools\Pegasus\metadata\*` | No results | Any match = local path leaked |

---

## 5. Artwork Integrity

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| Artwork paths resolve | Check `assets.` lines point to `A:\LaunchBox\Images\...` | Paths are absolute A: drive paths | Relative paths or C: drive paths |
| Box art displays in Pegasus | Browse any platform, observe game tiles | Game artwork visible | Placeholder icons or missing art |
| Platform art exists | `dir A:\Artwork\Pegasus\platforms\` | Platform images present (nes.png, snes.png, etc.) | Folder missing or empty |
| Special category art exists | `dir A:\Artwork\Pegasus\categories\` | Category images present (nes_gun_games.png, etc.) | Folder missing or empty |
| No "TODO" placeholder art visible | Browse all major categories in Pegasus | Professional artwork throughout | "TODO", placeholder, or broken images |

---

## 6. Pegasus Configuration

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| Settings file exists | `type A:\Tools\Pegasus\config\settings.txt` | File displays theme path and key bindings | File missing or empty |
| Theme path correct | Check `general.theme:` line | Points to `A:/Tools/Pegasus/themes/...` | Points to C: or relative path |
| Fullscreen enabled | Check `general.fullscreen:` | Value is `true` | Value is `false` or missing |
| Game controller navigation | Use gamepad in Pegasus | D-pad/stick navigates, A button launches | Navigation broken or unresponsive |

---

## 7. Golden Drive Path Safety

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| No hardcoded C: paths in scripts | `findstr /i "C:\\" A:\Tools\aa_pegasus.bat` | No results | Any C: path found |
| No hardcoded C: paths in bridge | `findstr /i "C:\\" "A:\Arcade Assistant Local\scripts\aa_launch_pegasus_simple.bat"` | No results | Any C: path found |
| Wrapper uses relative call | Open `A:\Tools\aa_pegasus.bat`, inspect | Calls script via full A: path | Uses relative or C: path |

---

## 8. Boot/Startup Assumptions

| What to Validate | How to Validate | Pass Criteria | Regression Indicator |
|------------------|-----------------|---------------|----------------------|
| AA backend starts before Pegasus | If using auto-start, verify startup order | Backend healthy before Pegasus launches | Pegasus launches with backend offline |
| Pegasus survives backend restart | Restart backend while Pegasus is open | Pegasus remains stable; next launch works | Pegasus crashes or hangs |
| Clean exit returns to Pegasus | Launch game, exit emulator normally | Returns to Pegasus game list | Stuck on black screen or crashes |

---

## Validation Summary Template

Copy and fill out after validation:

```
Pegasus Golden Drive Validation - [DATE]
==========================================
Operator: ________________
Drive Serial: ________________

Prerequisites:          [ PASS / FAIL ]
Pegasus Launches:       [ PASS / FAIL ]
Launch Pipeline:        [ PASS / FAIL ]
Metadata Integrity:     [ PASS / FAIL ]
Artwork Integrity:      [ PASS / FAIL ]
Configuration:          [ PASS / FAIL ]
Path Safety:            [ PASS / FAIL ]
Boot Assumptions:       [ PASS / FAIL ]

Notes:
_____________________________________
_____________________________________
```

---

## If Something Fails, Where to Look First

| Failure Type | Files/Subsystems to Check |
|--------------|---------------------------|
| **Game won't launch from Pegasus** | `A:\Tools\aa_pegasus.bat`, `scripts/aa_launch_pegasus_simple.bat`, `logs/pegasus_launch.log`, `backend/routers/launchbox.py` (lines 2238-2241) |
| **Boot loop (game starts then exits)** | `logs/pegasus_launch.log`, backend console output, `AA_LAUNCH_POLICY` in `.env` |
| **Artwork missing in Pegasus** | `A:\Tools\Pegasus\metadata\<platform>\metadata.pegasus.txt` (check `assets.` lines), `A:\LaunchBox\Images\` |
| **Platform/category art missing** | `A:\Artwork\Pegasus\platforms\`, `A:\Artwork\Pegasus\categories\` |
| **Pegasus crashes on launch** | `A:\Tools\Pegasus\config\settings.txt`, `A:\Tools\Pegasus\themes\` folder permissions |
| **Wrong theme or broken UI** | `A:\Tools\Pegasus\config\settings.txt` (`general.theme:` line) |
| **Metadata out of date** | `scripts/generate_pegasus_metadata.py`, `A:\.aa\launchbox_games.json` |
| **Backend not receiving requests** | Gateway logs, `netstat -ano | findstr ":8787"`, `netstat -ano | findstr ":8000"` |
| **Path with spaces error** | Confirm `A:\Tools\aa_pegasus.bat` exists and is used instead of direct path to `A:\Arcade Assistant Local\scripts\...` |

---

_Document created: 2025-12-11_  
_Based on: README.md, docs/Pegasus_Integration_Journal.md_
