# Arcade Assistant — Project README
**Last Updated:** 2026-03-05 (evening) | **Build:** Console Wizard RAG KB + LED Priority Arbiter | **Branch:** `master` | **Commit:** `1d3993d`

> **For AI Agents:** Read `ROLLING_LOG.md` first for net-progress history. Read `ARCHITECTURE.md` for backend deep-dives. This README is the quick-reference entry point.

---

## What Is Arcade Assistant?

A **self-hosted AI control hub** for a physical arcade cabinet. It runs locally on a Windows PC (A: drive) and provides:
- A React frontend served via a Node.js gateway
- A FastAPI Python backend
- 9 specialized AI personas, each with their own panel, chat sidebar, and hardware hooks
- Hardware integrations: LED-Wiz boards (3x), encoder boards, LaunchBox, light guns

---

## Quick Start

```powershell
# From A:\Arcade Assistant Local\
.\start-aa.bat

# Or manually:
# Terminal 1 — Gateway (Node)
cd gateway && node server.js

# Terminal 2 — Backend (Python)
cd backend && python app.py

# Terminal 3 — Frontend (Vite dev server)
cd frontend && npm run dev
```

**Access:** `http://127.0.0.1:8787`

---

## Infrastructure

| Component | Location | Port | Notes |
|-----------|----------|------|-------|
| Gateway (Node.js) | `gateway/server.js` | 8787 | Serves frontend static, proxies to backend |
| Backend (FastAPI) | `backend/app.py` | 8000 | AI, LED, scoring, hotkey APIs |
| Frontend (Vite/React) | `frontend/` | 5173 (dev) | Built to `dist/` for prod |
| Supabase | Cloud | — | Ref: `zlkhsxacfyxsctqpvbsh` (**Arcade Assistant only**) |

> ⚠️ **NEVER** use Supabase ref `hjxzbicsjzyzalwilmlj` — that is the G&G Website project.

---

## Persona Roster

| # | Persona | Panel File | EB Sidebar | TTS |
|---|---------|-----------|------------|-----|
| 1 | **Dewey** (Arcade Historian) | `panels/dewey/` | N/A (custom) | ✅ ElevenLabs |
| 2 | **LaunchBox LoRa** | `panels/launchbox/` | 🔶 Stub | ✅ ElevenLabs |
| 3 | **ScoreKeeper Sam** | `panels/scorekeeper/` | N/A | ✅ ElevenLabs |
| 4 | **Controller Chuck** | `panels/controller/` | ✅ Standardized | ✅ ElevenLabs |
| 5 | **LED Blinky** | `components/led-blinky/` | ✅ Standardized | ✅ ElevenLabs |
| 6 | **Gunner** | `components/gunner/` | ✅ Standardized | ✅ ElevenLabs |
| 7 | **Console Wizard** | `panels/console-wizard/` | ✅ Standardized | ✅ ElevenLabs |
| 8 | **Vicky** (Voice) | `panels/voice/` | ✅ Standardized | ✅ ElevenLabs |
| 9 | **Doc** (Diagnostics) | `panels/system-health/` | ✅ Standardized | ✅ ElevenLabs |

Route: `http://127.0.0.1:8787/assistants?agent=chuck` (replace `chuck` with persona ID)

---

## Controller Chuck — Current State (as of 2026-03-03)

The most actively developed panel. Status: **Diagnosis Mode Phase 1 + Standardized Sidebar + Gemini AI.**

### Implemented
- **4P / 2P mode switcher** — identical compact card sizing in both modes
- **FLIP focus animation** — click any player card, it springs from its exact grid corner to the panel center (`getBoundingClientRect()` + CSS vars `--flip-x/y/w`, spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)`)
- **Premium return animation** — card breathes out to scale(1.52) then dissolves back to its grid corner
- **Directional arrow overlay + Button click-to-map** — SVG arrows, cyan pulse while waiting for cabinet input
- **Mapping confirmation animations** — physical press → `latestInput` → white flash → green ring burst → `✓ GPIO XX` badge
- **Top strip** — SCAN + DETECT buttons visible in both 2P and 4P modes

### Diagnosis Mode (Phase 1 — 2026-03-02)
Diagnosis Mode is a context-aware, config-writing co-pilot mode. Toggle the amber pill in the Chuck sidebar header to activate.

**Frontend:**
| File | Role |
|------|------|
| `hooks/useDiagnosisMode.js` | Shared hook — toggle, TTS greeting, 30s context refresh, 5-min soft-lock |
| `chuckContextAssembler.js` | 3-tier context payload (<1500 tokens, Chuck-only) |
| `chuckChips.js` | 6 suggestion chips |
| `DiagnosisToggle.jsx/.css` | Amber pill toggle with animated thumb |
| `ContextChips.jsx/.css` | Horizontal scrollable amber chip bar |
| `MicButton.jsx/.css` | Push-to-talk, 0.7 confidence threshold, ripple rings |
| `ChuckSidebar.jsx` | Full chat panel — assembles all components |
| `chuck-sidebar.css` | Amber left-border pulse in Diagnosis Mode |
| `chuck-layout.css` | Flex layout: player grid + sidebar side-by-side |

**Backend:**
| File | Role |
|------|------|
| `services/controller_bridge.py` | `ControllerBridge` — sole GPIO merge authority, 5-step atomic commit, 4 conflict types, sacred law validation, rollback |
| `routers/controller.py` | `POST /api/profiles/mapping-override` — 2-phase proposal+commit |
| `services/chuck/ai.py` | `remediate_controller_config()` — Gemini 2.0 Flash AI tool |

**Sacred Button Law (immutable):**
```
P1/P2: Top row → 1, 2, 3, 7  |  Bottom row → 4, 5, 6, 8
P3/P4: Top row → 1, 2         |  Bottom row → 3, 4
```
This is the Rosetta Stone for all 45+ emulator configs. `ControllerBridge` hard-blocks any deviation.

### Pending / Next
- Assign correct ElevenLabs voice ID for Chuck (`CHUCK_VOICE_ID` in `.env`)
- Diagnosis Mode Phase 2: Supabase tables (`controller_mappings`, `encoder_devices`, `controller_mappings_history`)
- Cascade diff UI inside the Diagnosis Mode sidebar
- Wire real hardware data into `chuckContextAssembler.js`

### Key Files
```
frontend/src/panels/controller/
  ├── ControllerChuckPanel.jsx     ← Main component (FLIP, state machine, PlayerCard)
  ├── ChuckSidebar.jsx             ← Chat panel + Diagnosis Mode
  ├── controller-chuck.css         ← All animations, 2P/4P layout
  ├── chuck-sidebar.css            ← Sidebar styles (amber in diag mode)
  ├── chuck-layout.css             ← Flex layout wrapper
  ├── DiagnosisToggle.jsx/.css     ← Amber pill toggle
  ├── ContextChips.jsx/.css        ← Suggestion chips
  ├── MicButton.jsx/.css           ← Push-to-talk
  ├── chuckContextAssembler.js     ← 3-tier context builder
  └── chuckChips.js                ← Chip definitions

backend/
  ├── services/controller_bridge.py   ← GPIO merge authority
  ├── routers/controller.py           ← mapping-override endpoint
  └── services/chuck/ai.py            ← remediate_controller_config tool
```

---

## LED System

- **Stack**: Python ctypes driver (`ledwiz_direct.py`) speaks directly to Windows HID — **no node-hid, no LEDBlinky dependency for color control**
- **LEDBlinky.exe**: Still used for per-game profiles via subprocess call
- **PWM Safety**: All values clamped 0–48 (49–129 triggers strobe/crash modes)
- **Boards**: 3× LED-Wiz units auto-discovered on startup
- **Gamma**: 2.5 correction + Electric Ice color balance (Red 65%, Blue 75%, Green 100%)

---

## Supabase Edge Functions

| Function | JWT Verify | Purpose |
|----------|-----------|---------| 
| `anthropic-proxy` | OFF | Claude API proxy |
| `elevenlabs-proxy` | OFF | TTS proxy |
| `openai-proxy` | OFF | GPT proxy |
| `gemini-proxy` | OFF | Gemini proxy |
| `admin-gateway` | ON | Admin operations |

---

## Known Issues / Open Items

| Issue | Priority | Notes |
|-------|----------|-------|
| LED Blinky panel + RAG KB | 🔴 Next Session | Primary target — arbiter built, needs frontend + sidebar |
| Gunner Phase 2 | 🟡 After LED Blinky | Calibration tab, profiles tab, retro modes |
| Doc (Diagnostics) panel | 🟡 After Gunner | Full system diagnostic panel |
| B6/B7 Wake Word & TTS Dropping | 🟡 Medium | Voice panel fixes |
| Handoff Protocol URL standard | 🟡 Medium | Inter-panel communication |
| Diagnosis Mode Phase 2 (Supabase tables) | 🟡 Medium | `controller_mappings`, `encoder_devices`, `controller_mappings_history` |
| `blinky/__init__.py` lazy exports | 🟡 Medium | Eagerly parses XML + HID on import → blocking |
| F9 Overlay Z-Index | 🟢 Backlog | Electron `setAlwaysOnTop` |
| LaunchBox LoRa deep build | 🟢 Backlog | Most complex panel — future session |

### Recently Closed Blockers (2026-03-05)
| Blocker | Fix | File |
|---------|-----|------|
| B2 — HttpBridge outbound | `NotifyBackendGameStart()` fire-and-forget POST | `HttpBridge.cs` |
| B4 — Voice Hardware Unlock | `_sync_led_state()` + Supabase fleet mirroring | `voice/service.py` |
| B5 — Genre LED Animation | `GENRE_ANIMATION_MAP` (8 genre codes) | `game_lifecycle.py` |
| Console Wizard RAG KB | `wiz_knowledge.md` (500+ lines) + enhanced prompt | `prompts/` |
| LED Priority Arbiter | Circuit breaker (VOICE>GAME>ATTRACT>IDLE) + throttle | `led_priority_arbiter.py` |

---

## Git / Deployment

```powershell
# Standard commit + push
git add .
git commit -m "Description"
git push origin master
```

**Remote:** `https://github.com/ggarcadeV4/Arcade-Assistant-Basement-Build.git`
**Branch:** `master` (always)

> ⚠️ A: drive is a USB drive — large `git commit` operations can take 5+ minutes. This is normal.

---

## Session History

See `ROLLING_LOG.md` for a reverse-chronological log of all sessions and net progress.
See `logs/` directory for daily session logs.

---

*Arcade Assistant — Built for G&G Arcade, one commit at a time.*