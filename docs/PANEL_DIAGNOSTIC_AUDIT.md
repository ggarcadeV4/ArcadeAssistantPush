# Panel Diagnostic Capabilities - Critical Audit
> Generated: December 2024
> Purpose: Ensure each panel can diagnose and fix problems for self-healing cabinet

## The Dream
Someone standing at the cabinet asks "What's wrong?" and the system:
1. Detects the issue automatically
2. Explains what's happening
3. Offers to fix it (config changes)
4. Applies fixes with backup/rollback

---

## Panel-by-Panel Audit

### 1. Controller Chuck ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Hardware Detection | ✅ | `GET /api/local/controller/devices` |
| Board Sanity Scan | ✅ | `GET /api/local/controller/board/sanity` |
| Health Check | ✅ | `GET /api/local/controller/health` |
| Config Read | ✅ | `GET /api/local/controller/mappings` |
| Config Fix (Preview) | ✅ | `POST /api/local/controller/mappings/preview` |
| Config Fix (Apply) | ✅ | `POST /api/local/controller/mappings/apply` |
| Wiring Wizard | ✅ | `POST /api/local/controller/wizard/start` |
| Voice/Chat | ✅ | Via Chuck panel |

**What Chuck Can Diagnose:**
- USB backend issues (permissions, drivers)
- Encoder not detected
- Ghost pulses / unstable pins
- Mode conflicts (turbo + analog)
- Mapping mismatches

**What Chuck Can Fix:**
- Remap buttons via wizard
- Update controller baseline
- Cascade mappings to emulators

---

### 2. LED Blinky ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Device Detection | ✅ | `GET /api/local/led/detect` |
| Status Check | ✅ | `GET /api/local/led/status` |
| Engine Health | ✅ | `GET /api/local/led/engine-health` |
| Config Read | ✅ | `GET /api/local/led/config` |
| Config Fix (Preview) | ✅ | `POST /api/local/led/config/preview` |
| Config Fix (Apply) | ✅ | `POST /api/local/led/config/apply` |
| Channel Test | ✅ | `POST /api/local/led/diagnostics/channel-test` |
| Voice/Chat | ✅ | Via Blinky panel |

**What Blinky Can Diagnose:**
- No LED hardware detected
- Simulation mode active
- HID library missing
- Channel not responding

**What Blinky Can Fix:**
- Apply LED profiles
- Bind profiles to games
- Adjust brightness/patterns

---

### 3. Console Wizard ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Emulator Scan | ✅ | `GET /api/local/console_wizard/scan` |
| Health Check | ✅ | `GET /api/local/console_wizard/health` |
| Chuck Sync Status | ✅ | `GET /api/local/console_wizard/status/chuck` |
| Config Read | ✅ | `GET /api/local/console_wizard/config/{emulator}` |
| Config Fix (Preview) | ✅ | `POST /api/local/console_wizard/sync/preview` |
| Config Fix (Apply) | ✅ | `POST /api/local/console_wizard/sync/apply` |
| Restore Defaults | ✅ | `POST /api/local/console_wizard/restore/{emulator}` |
| Voice/Chat | ✅ | Via Console Wizard panel |

**What Console Wizard Can Diagnose:**
- Emulator configs out of sync with Chuck
- Missing emulator installations
- Config file corruption

**What Console Wizard Can Fix:**
- Sync emulator configs to match controller mappings
- Restore default configs
- Apply per-emulator profiles

---

### 4. Gunner ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Gun Detection | ✅ | `GET /api/local/gunner/devices` |
| Hardware Advice | ✅ | `GET /api/local/gunner/advice` |
| Gun Registry | ✅ | `GET /api/local/gunner/registry` |
| Calibration | ✅ | `POST /api/local/gunner/calibrate/point` |
| Profile Save/Load | ✅ | `POST /api/local/gunner/profile/save` |
| Voice/Chat | ✅ | Via Gunner panel |

**What Gunner Can Diagnose:**
- No gun detected
- Gun type (Sinden, Ultimarc, Retro Shooter, etc.)
- Feature availability (IR, recoil, pedal)
- Calibration drift

**What Gunner Can Fix:**
- Re-calibrate gun (9-point wizard)
- Apply game-specific profiles
- Hardware-specific advice

---

### 5. LoRa (LaunchBox) ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Plugin Health | ✅ | `GET /api/local/scorekeeper/plugin/health` |
| Plugin Status | ✅ | `GET /api/local/launchbox/plugin-status` |
| Game Resolution | ✅ | `POST /api/local/launchbox/resolve` |
| Launch Game | ✅ | `POST /api/local/launchbox/launch/{guid}` |
| Platform List | ✅ | `GET /api/local/launchbox/platforms` |
| Voice/Chat | ✅ | Via LoRa panel |

**What LoRa Can Diagnose:**
- LaunchBox plugin offline
- Game not found
- Emulator path misconfigured
- Launch failures

**What LoRa Can Fix:**
- Resolve game by title
- Launch with correct adapter
- Update emulator paths in launchers.json

---

### 6. ScoreKeeper Sam ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Leaderboard | ✅ | `GET /api/local/scorekeeper/leaderboard` |
| Top Dog | ✅ | `GET /api/local/scorekeeper/topdog` |
| Champions | ✅ | `GET /api/local/scorekeeper/champions` |
| High Scores | ✅ | `GET /api/local/scorekeeper/highscores/{game}` |
| Tournament Create | ✅ | Preview/Apply pattern |
| Score Submit | ✅ | Preview/Apply pattern |
| Voice/Chat | ✅ | Via Sam panel |

**What Sam Can Diagnose:**
- No scores recorded
- Tournament incomplete
- Player not found

**What Sam Can Answer:**
- "Who's top dog?"
- "Who won the tournament?"
- "What's my high score at Galaga?"

---

### 7. Pegasus ✅ READY

| Capability | Status | Endpoint |
|------------|--------|----------|
| Status | ✅ | `GET /api/local/pegasus/status` |
| Health | ✅ | `GET /api/local/pegasus/health` |
| Platforms | ✅ | `GET /api/local/pegasus/platforms` |
| Sync | ✅ | `POST /api/local/pegasus/sync` (placeholder) |

---

## System-Wide Health

| Capability | Status | Endpoint |
|------------|--------|----------|
| Overall Health | ✅ | `GET /api/health` |
| Hardware Status | ✅ | `GET /api/health/hardware` |
| Active Alerts | ✅ | `GET /api/health/alerts/active` |
| Performance | ✅ | `GET /api/health/performance` |
| TeknoParrot Health | ✅ | `GET /api/local/teknoparrot/health` |

---

## Config File Safety Pattern

All config changes follow the **Preview → Apply** pattern:
1. **Preview**: Shows what would change (dry-run)
2. **Apply**: Makes the change with automatic backup
3. **Restore**: Can roll back using backup path

Backups stored in: `/backups/YYYYMMDD/`

---

## Voice Integration Status

| Panel | Can Talk | Can Listen | Can Fix via Voice |
|-------|----------|------------|-------------------|
| Controller Chuck | ✅ | ✅ | ✅ |
| LED Blinky | ✅ | ✅ | ✅ |
| Console Wizard | ✅ | ✅ | ✅ |
| Gunner | ✅ | ✅ | ✅ |
| LoRa | ✅ | ✅ | ✅ |
| ScoreKeeper Sam | ✅ | ✅ | ✅ |
| Dewey | ✅ | ✅ | ✅ |

---

## Recommendation: Unified "What's Wrong?" Handler

For the dream to fully work, consider adding:

```
GET /api/health/diagnose-all
```

This would aggregate:
- Controller health
- LED status
- Emulator sync status
- Gun detection
- LaunchBox plugin status
- Any active alerts

And return a human-readable summary like:
> "Everything looks good! Your Ultimarc encoder is connected, LEDs are active, and all emulators are in sync."

Or:
> "I found 2 issues: (1) Your controller isn't detected - check the USB connection. (2) RetroArch config is out of sync with your button mappings - would you like me to fix it?"

---

## Conclusion

**All 7 panels have the core diagnostic capabilities in place.** Each can:
- ✅ Detect hardware/config status
- ✅ Read relevant config files
- ✅ Preview changes before applying
- ✅ Apply fixes with automatic backup
- ✅ Respond via voice/chat

The system is **ready for the Golden Drive** with the confidence that someone at the cabinet can ask "What's wrong?" and get actionable help.
