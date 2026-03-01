# Arcade Assistant — Project README
**Last Updated:** 2026-03-01 | **Build:** 234 modules, 0 errors | **Branch:** `master`

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

| # | Persona | Panel File | Status |
|---|---------|-----------|--------|
| 1 | **Dewey** (Arcade Historian) | `panels/dewey/` | ✅ V2.5 |
| 2 | **LaunchBox LoRa** | `panels/launchbox/` | 🔶 Stub |
| 3 | **ScoreKeeper Sam** | `panels/scorekeeper/` | ✅ Supabase realtime + TTS |
| 4 | **Controller Chuck** | `panels/controller/` | ✅ Full FLIP UI + mapping confirmation |
| 5 | **LED Blinky** | `components/led-blinky/LEDBlinkyPanelNew.jsx` | ✅ Refactored |
| 6 | **Gunner** | `panels/lightguns/` | ✅ Phase 1 UI |
| 7 | **Console Wizard** | `panels/consolewizard/` | 🔶 Stub |
| 8 | **Vicky** (Voice) | `panels/voice/` | 🔶 Partial |
| 9 | **Doc** (Diagnostics) | `panels/doc/` | 🔶 Partial |

Route: `http://127.0.0.1:8787/assistants?agent=chuck` (replace `chuck` with persona ID)

---

## Controller Chuck — Current State (as of 2026-03-01)

The most actively developed panel. Status: **production-ready UX shell, hardware mapping in progress.**

### Implemented
- **4P / 2P mode switcher** — identical compact card sizing in both modes, `justify-content: center` layout
- **FLIP focus animation** — click any player card, it springs from its exact grid corner to the panel center (`getBoundingClientRect()` + CSS vars `--flip-x/y/w`, spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)`)
- **Premium return animation** — card breathes out to scale(1.52) then dissolves back to its grid corner via `@keyframes return-to-grid`
- **Directional arrow overlay** — SVG arrows on joystick, click to enter mapping mode (flow-toward-center waiting animation)
- **Button click-to-map** — click any arcade button, it pulses cyan while waiting for cabinet input
- **Mapping confirmation animations** — physical press triggers `latestInput` → white flash → green ring burst → `✓ GPIO XX` badge
- **Top strip** — SCAN + DETECT buttons visible in both 2P and 4P modes

### Pending / Next
- Microphone support in Chuck's chat sidebar
- Actual GPIO pin write-back to config files (confirmation animation fires but doesn't persist yet — backend endpoint needed)
- Cascade to Vicky Voice panel

### Key Files
```
frontend/src/panels/controller/
  ├── ControllerChuckPanel.jsx   ← Main component (FLIP logic, state machine, PlayerCard)
  └── controller-chuck.css      ← All animations, 2P/4P layout, confirmation styles
```

### Architecture Notes
- `returningPlayer` state machine: on dismiss, `activePlayer=null`, card keeps `position:absolute` via `.focus-returning`, `onAnimationEnd` fires `handleReturnEnd` → clears state
- `latestInput` from `useInputDetection` is passed as prop to each `PlayerCard`; each card independently reacts while in waiting state
- 4P compact sizing anchor: `.chuck-shell[data-mode="4p"] .chuck-main { justify-content: center }` — 2P mirrors this exactly

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
| Mic in Chuck chat sidebar | 🔴 Next | Web Speech API, same pattern as ScoreKeeper Sam |
| Chuck GPIO write-back | 🔴 Next | Confirmation animation shows pin but doesn't persist to config |
| `blinky/__init__.py` lazy exports | 🟡 Medium | Eagerly parses XML + HID on import → blocking |
| Console Wizard, LaunchBox LoRa | 🟡 Medium | Stubs only |
| ScoreKeeper gateway endpoints | 🟡 Medium | `/api/scorekeeper/supabase-sync`, `/scorekeeper/ws` — assumed to exist, not verified |
| Gunner Phase 2 | 🟢 Backlog | Calibration tab, profiles tab, retro modes |

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