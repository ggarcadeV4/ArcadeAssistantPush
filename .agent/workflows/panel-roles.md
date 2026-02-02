# Panel Roles & Responsibilities

> Updated: 2025-12-11 | Phase 3 of TeknoParrot Integration

This document clarifies the distinct roles of the Arcade Assistant's agent panels to avoid scope confusion and over-promising.

---

## Controller Chuck 🔧

**Role**: Arcade Encoder → Emulator Bridge

**Owned Responsibilities**:
- Defines the **canonical logical mapping** (`controls.json`) for arcade panel buttons/joysticks
- Maps physical encoder pins to logical controls (p1.button1, p1.up, etc.)
- Previews and applies mappings
- Triggers **cascade jobs** to propagate mappings downstream to emulators

**What Chuck Does NOT Do**:
- Does not directly write emulator config files (that's cascade/Wizard territory)
- Does not manage console gamepads (Xbox, PS, Switch) — see Console Wizard

**TeknoParrot Integration** (Phase 1):
- Chuck knows about TeknoParrot's canonical control schema (racing, lightgun, generic)
- Chuck outputs TP-compatible canonical mappings
- Actual TP UserProfile XML writes are delegated to cascade/Wizard

---

## Console Wizard 🎮

**Role**: Emulator Configuration Orchestrator

**Owned Responsibilities**:
- Translates Chuck's logical mappings into emulator-specific configs
- Generates configs for: MAME, RetroArch, Dolphin, PCSX2, **TeknoParrot**
- Manages **preview → apply → backup → log** flow for all emulators
- Health checks for config drift detection
- Restore-to-defaults functionality

**What Wizard Does**:
- Reads from `controls.json` (Chuck's output)
- Writes to each emulator's native config format (INI, CFG, XML)
- Always creates backups before mutations
- Logs all changes to `changes.jsonl`

**TeknoParrot Integration** (Phase 2):
- `/api/local/console/teknoparrot/preview` — Preview TP bindings
- `/api/local/console/teknoparrot/apply` — Store TP mapping in baseline
- `/api/local/console/teknoparrot/games` — List supported TP games
- `/api/local/console/teknoparrot/schema/{category}` — Get schema for racing/lightgun

---

## Scorekeeper Sam 📊

**Role**: High Score Historian & Tournament Manager

**Owned Responsibilities**:
- Tracks arcade high scores per game
- Records player initials/names
- Manages tournaments (brackets, rounds, winners)
- Voice-controlled score entry
- Leaderboard display for big-screen mode

**Future Enhancements** (Phase 4 Design):
- Profile-to-initials mapping (link "DAD" to a player profile)
- Hidden/moderated scores (exclude practice runs)
- Household player registry

**What Sam Does NOT Do**:
- Does not configure emulators or controllers
- Does not manage game launching (that's LaunchBox/LoRa)

---

## LED Blinky 💡

**Role**: Button Illumination Controller

**Owned Responsibilities**:
- Manages LED Blinky integration for button RGB lighting
- Per-game LED profiles
- Voice-controlled color changes
- Cascade receiver: applies button colors based on Chuck's mappings

**How It Integrates**:
- Receives cascade events from Chuck
- Maps logical controls (p1.button1) to LED channels
- Uses Chuck's pin mappings to know which physical button to light

---

## LoRa (LaunchBox Panel) 🎮

**Role**: Game Library & Launch Management

**Owned Responsibilities**:
- LaunchBox integration for game library
- Game launching via emulator adapters
- RetroFE frontend integration
- Content & Display Manager for media/artwork

**What LoRa Does NOT Do**:
- Does not configure controller mappings (use Chuck/Wizard)
- Does not track scores (use Sam)

---

## Doc (System Health) 🏥

**Role**: System Diagnostics & Health Monitoring

**Owned Responsibilities**:
- System health checks
- Emulator status monitoring
- File system health
- Backend connectivity testing

---

## Dewey 🧠

**Role**: AI Concierge & Router

**Owned Responsibilities**:
- Natural language understanding for routing to appropriate panels
- Context handoff between panels
- General arcade assistant Q&A

---

## Panel Integration Matrix

| From \ To | Chuck | Wizard | Sam | LED | LoRa | Doc |
|-----------|-------|--------|-----|-----|------|-----|
| **Chuck** | — | Cascade | — | Cascade | — | Health |
| **Wizard** | Reads controls.json | — | — | — | — | — |
| **Sam** | — | — | — | — | Leaderboard overlay | — |
| **LED** | Receives cascade | — | — | — | Game launch events | — |
| **LoRa** | — | — | Score handoff | Lighting triggers | — | — |
| **Doc** | Health check | Health check | — | — | — | — |

---

## Cascade Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Chuck (controls.json)                                                 │
│    └── defines: p1.button1 = pin 8, p1.up = pin 10, etc.              │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Cascade Job                                                           │
│    ├── MAME: write default.cfg                                        │
│    ├── RetroArch: write retroarch.cfg                                  │
│    ├── Dolphin: write Dolphin.ini                                      │
│    ├── TeknoParrot: store mapping (XML write coming)                   │
│    └── LED Blinky: apply LED colors                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Each Emulator                                                         │
│    └── reads its native config format at game launch                   │
└─────────────────────────────────────────────────────────────────────────┘
```
