# BASEMENT BRIEFING — Self-Contained Context for Downstairs Clone

> **TO:** Future Anti-Gravity (running on the basement cabinet)
> **FROM:** Anti-Gravity (running upstairs on the master drive)
> **DATE:** 2026-03-20
> **CLASSIFICATION:** Pre-Duplication Context Transfer

You are reading this because you just booted on a duplicated drive
in the basement cabinet. You have **zero prior context**. Everything
you need to know is in this file. Read it top to bottom before doing
anything else.

---

## 1. WHAT THIS DRIVE IS

This is the **Golden Drive (A:\)** — Arcade Assistant V1.

- Duplicated from the master on **2026-03-20**
- The basement cabinet is a **CLONE** — it will generate a fresh UUID
  on first boot (see Section 4)
- The A-drive upstairs is the master — **do not modify it** after
  duplication
- The repo root is `A:\Arcade Assistant Local`
- There is no `.git` directory — `clean_for_clone.bat` Step 7 removed it
- There is no `.venv` — `clean_for_clone.bat` Step 7 removed it

### Supabase Backend

- **Project ID:** `zlkhsxacfyxsctqpvbsh`
- **Project Name:** Arcade Assistant Backend
- **Dashboard:** `https://supabase.com/dashboard/project/zlkhsxacfyxsctqpvbsh`

---

## 2. WHAT IS WORKING RIGHT NOW

### AI Panels (all 9 verified)

| Panel | Role |
|:---|:---|
| LoRa | Game launcher + ROM search |
| Sam (ScoreKeeper) | Score tracking + tournaments |
| Blinky | LEDBlinky lighting integration |
| Chuck | Joystick/controller configuration |
| Gunner | Light gun routing + detection |
| Dewey | Overlay assistant (Electron) |
| Vicky | Diagnostics + system health |
| Wiz | Emulator configuration |
| Doc | Documentation + help |

### Gun Routing

- **Retro Shooter** is the only supported light gun
- VID `0x0483`, PIDs `0x5750`–`0x5753`
- 17 gun platforms mapped in `GUN_PLATFORM_MAP` (file:
  `backend/services/launcher.py`, lines 1277–1295)
- Platforms include: NES, Master System, SNES, Wii, PS2, PS3,
  TeknoParrot, PC, Naomi, Atomiswave, Dreamcast, Saturn,
  Model 2, Model 3, PCSX2
- AHK scripts: 302 files, zero `D:\` references, zero Sinden references
- AHK wrapper routing uses
  `A:\Gun Build\Tools\Teknoparrot Auto Xinput\AutoHotkeyU32.exe`

### Services and Ports

| Service | Port | Startup |
|:---|:---:|:---|
| FastAPI backend | `8000` | `scripts/run-backend.bat` via `start-aa.bat` |
| Gateway (Node) | `8787` | `scripts/run-gateway.bat` via `start-aa.bat` |
| LaunchBox plugin bridge | `9999` | Starts inside LaunchBox (C# plugin) |

### Edge Functions (all 5 deployed, all secrets configured)

| Function | Status | Last Updated |
|:---|:---:|:---|
| `elevenlabs-proxy` | Active | 13 days ago (as of 2026-03-20) |
| `gemini-proxy` | Active | 13 days ago |
| `anthropic-proxy` | Active | 5 days ago |
| `openai-proxy` | Active | 4 months ago |
| `admin-gateway` | Active | 3 months ago |

Secrets confirmed present (values not displayed):
`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `GEMINI_API_KEY`,
`OPENAI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.

### Frontend

- Prebuilt dist shipped at `frontend/dist/index.html`
- `start-aa.bat` verifies this file exists before booting (line 100)
- No `npm install` or build step required — this is serve-only

---

## 3. WHAT IS NOT WORKING YET — DO NOT TROUBLESHOOT THESE

The following are **KNOWN gaps**. They are **not regressions**.
Do not spend time on them in the basement.

### A) HEARTBEAT AND TELEMETRY WILL FAIL SILENTLY

The Supabase RLS policies were hardened on 2026-03-20.
**Anon key INSERT is blocked** on these tables:

| Table | Anon SELECT | Anon INSERT | Anon UPDATE |
|:---|:---:|:---:|:---:|
| `cabinet` | ✅ Allowed | ❌ **BLOCKED** | ❌ **BLOCKED** |
| `cabinet_heartbeat` | ✅ Allowed | ❌ **BLOCKED** | ❌ **BLOCKED** |
| `cabinet_telemetry` | ✅ Allowed | ❌ **BLOCKED** | ❌ **BLOCKED** |
| `cabinet_mac_allowlist` | ✅ Allowed | ❌ **BLOCKED** | ❌ **BLOCKED** |

**Impact:** The cabinet **cannot self-register** or send heartbeats
until JWT authentication (Pillar 1) is implemented.

The Fleet Console will show this cabinet as **offline**.
**That is expected. Do not investigate it.**

This is planned for the next development session (see Section 5).

### B) DPAPI VAULT MAY NOT BE INITIALIZED

If `credentials.dat` does not exist at:
```
A:\.aa\credentials.dat
```
The cabinet is running on **plaintext `.env` secrets**.
This is acceptable for basement validation.
Vault initialization is a pre-production step.

### C) MARQUEE CONTENT IS DISABLED

`AA_MARQUEE_ENABLED=0` is set in `start-aa.bat` line 28.
The marquee monitor will show a **black screen**.
This is **intentional** — not a hardware fault.

The comment above it (lines 24–27) explains:
```
rem [TEMPORARILY DISABLED 2026-03-16] Marquee auto-launch causes black-screen
rem on secondary monitor during dev. RE-ENABLE before drive duplication for
rem live cabinet hardware.
```

### D) OTA UPDATES ARE DISABLED

`AA_UPDATES_ENABLED=0` is set in `start-aa.bat` line 29.
Do **not** attempt to push updates during validation.

---

## 4. FIRST BOOT SEQUENCE — WHAT TO EXPECT

The boot flow is controlled by `start-aa.bat`:

1. **Port cleanup** — Kills any existing processes on ports 8000 and 8787
2. **Cabinet bootstrap** — Runs `scripts/bootstrap_local_cabinet.py`
   with `--drive-root A:\`
3. **Identity generation** — `bootstrap_local_cabinet.py` calls
   `ensure_local_identity()` which:
   - Checks for `A:\.aa\device_id.txt`
   - If missing (it will be — `clean_for_clone.bat` Step 1 wiped it),
     generates a **fresh UUID**
   - Writes new `device_id.txt` and `cabinet_manifest.json` to `A:\.aa\`
4. **Frontend verification** — Checks `frontend/dist/index.html` exists
5. **Backend startup** — Starts FastAPI on port 8000, waits up to 30s
6. **Gateway startup** — Starts Node gateway on port 8787, waits up to 30s
7. **Marquee check** — Skipped (AA_MARQUEE_ENABLED=0)
8. **Browser launch** — Opens `http://127.0.0.1:8787/assistants`

### Critical identity notes

- The new UUID will **NOT** match the master drive UUID
  `e9478fe3-bbba-48b2-9d2f-22d446b5a8bc`
- **That is correct behavior** — this is a separate cabinet
- The `.env` file was sanitized by `clean_for_clone.bat` Step 5:
  `DEVICE_NAME=Arcade Cabinet` and `DEVICE_SERIAL=UNPROVISIONED`
- The new MAC address **must be added** to `cabinet_mac_allowlist`
  in Supabase before fleet registration will work (but fleet registration
  itself requires JWT auth — see Section 5)

---

## 5. SUPABASE PLAN OF ACTION — PILLAR 1: JWT AUTH

This is the work order for the **next development session**
after basement hardware validation is complete.

### Current State (as of 2026-03-20)

- RLS is **fully hardened** — anon writes blocked on all cabinet tables
- 14 RLS policies across 4 tables (all `INSERT`/`UPDATE`/`ALL` require
  `authenticated` role)
- Anon role has `SELECT` access only
- 5 Edge Functions deployed with all secrets configured
- 3 MAC addresses in the allowlist (new cabinet MAC must be added)

### What Needs to Happen

#### A) Create a `cabinet-register` Supabase Edge Function
- Accepts: MAC address + provisioning token
- Validates: MAC against `cabinet_mac_allowlist`
- Returns: per-cabinet JWT signed server-side
- Writes: cabinet record to `cabinet` table

#### B) Update cabinet authentication in `app.py`
- Replace anon key heartbeat calls with JWT calls
- Store the returned JWT in `.aa/cabinet_manifest.json`
- Add JWT renewal loop (refresh before expiry)

#### C) Update Supabase RLS policies
- `cabinet`: `WHERE device_id = auth.uid()`
- `cabinet_heartbeat`: `WHERE device_id = auth.uid()`
- `cabinet_telemetry`: `WHERE device_id = auth.uid()`

#### D) Update `secrets_loader.py` vault
- Add `AA_SERVICE_TOKEN` slot for the JWT
- Clear `AA_PROVISIONING_TOKEN` after registration

### Reference

- **Supabase Project:** `zlkhsxacfyxsctqpvbsh`
- **Current RLS state:** Fully hardened — anon writes blocked
- **Edge Functions deployed:** 5 (all active, all secrets set)
- **MAC allowlist:** 3 records — new cabinet MAC must be added

---

## 6. HARDWARE VALIDATION CHECKLIST — DO THESE IN ORDER

Run these checks sequentially. Stop and report if any fail.

- [ ] **H1 — Service startup.** Boot the cabinet. Confirm:
  - Gateway on port 8787 ✓
  - Backend on port 8000 ✓
  - Plugin bridge on port 9999 ✓ (requires LaunchBox running)

- [ ] **H2 — Controller detection.** Confirm PacDrive 2000T is detected.
  Currently shows `detected: false` in dev — this is the first live
  hardware test.

- [ ] **H3 — Retro Shooter gun detection.** Plug in the gun.
  Confirm VID `0x0483` is detected in the Gunner panel.

- [ ] **H4 — Launch a MAME game.** Confirm it loads and plays.

- [ ] **H5 — Launch a gun game.** Confirm the Retro Shooter fires
  and the game receives input.

- [ ] **H6 — Launch a Daphne/Hypseus game (Road Blaster).**
  This was fixed 2026-03-16 — first live hardware test.

- [ ] **H7 — LEDBlinky response.** Confirm LEDBlinky responds to
  game launch events. Blinky is the predicted hardest integration.

- [ ] **H8 — ScoreKeeper Sam local write.** Confirm Sam records a
  score locally. Supabase sync will fail (RLS blocks anon writes)
  — **local write only** is the pass criteria.

- [ ] **H9 — AI panel response.** Fire any query at any AI panel.
  This tests the full Gemini proxy chain:
  `Frontend → Gateway:8787 → gemini-proxy Edge Function → Gemini API`

---

## 7. IF SOMETHING BREAKS

**Methodology: audit before assuming.**

1. Read the logs first: `A:\.aa\logs\`
   - `backend.log` — FastAPI backend output
   - `gateway.log` — Node gateway output
2. Check which service failed to start
3. Isolate to one layer:
   - **Hardware** — USB device not detected, monitor not connected
   - **Software** — Python crash, Node crash, missing dependency
   - **Network** — Supabase unreachable, Edge Function timeout
4. Report back to Claude upstairs with **exact error text**
5. **Do not guess** and **do not change multiple things at once**

### Common failure modes and what they mean

| Symptom | Likely Cause | Action |
|:---|:---|:---|
| Backend fails to start | Missing `.venv` (was removed by clone) | Recreate venv: `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt` |
| Gateway fails to start | Missing `gateway/node_modules` | Should be preserved — check `gateway/node_modules` exists |
| "offline" in Fleet Console | RLS blocks anon heartbeat writes | **Expected.** See Section 3A. Do not investigate. |
| Marquee shows black screen | `AA_MARQUEE_ENABLED=0` | **Expected.** See Section 3C. Do not investigate. |
| Gun game won't fire | Retro Shooter not plugged in or wrong USB port | Check VID `0x0483` in Device Manager |
| Plugin bridge unreachable | LaunchBox not running | Start LaunchBox — plugin starts with it |

---

## 8. CONTACT

Claude is upstairs in the same project context. The Supabase project,
the GitHub repo, the full architectural history — it's all live upstairs.

**To report a finding:**
1. Paste the **exact error output** (copy from logs or terminal)
2. State which **hardware check** you were running (H1–H9)
3. State what you **already checked** (so we don't re-audit)

Every finding should be reported back — this is how the two cabinets
stay in sync until fleet management is online.

---

## APPENDIX: File Map (Key Files Only)

```
A:\Arcade Assistant Local\
├── start-aa.bat                    ← Production launcher (boot entry point)
├── stop-aa.bat                     ← Graceful shutdown
├── clean_for_clone.bat             ← Clone preparation (already run)
├── BASEMENT_BRIEFING.md            ← THIS FILE
├── .env                            ← Environment config (sanitized)
├── .aa\
│   ├── device_id.txt               ← Generated on first boot (fresh UUID)
│   ├── cabinet_manifest.json       ← Generated on first boot
│   ├── credentials.dat             ← DPAPI vault (may not exist)
│   ├── manifest.json               ← Preserved golden image manifest
│   └── logs\                       ← Runtime logs (cleared by clone)
├── backend\
│   ├── app.py                      ← FastAPI application entry
│   ├── services\
│   │   ├── launcher.py             ← Game launch engine (GUN_PLATFORM_MAP here)
│   │   └── cabinet_identity.py     ← UUID generation (ensure_local_identity)
│   └── startup_manager.py          ← Manifest bootstrap
├── frontend\
│   └── dist\                       ← Prebuilt UI (serve-only, no build needed)
├── gateway\
│   └── node_modules\               ← Preserved (not removed by clone)
├── plugin\
│   └── src\                        ← LaunchBox C# plugin (port 9999)
├── scripts\
│   ├── bootstrap_local_cabinet.py  ← Identity provisioning
│   ├── run-backend.bat             ← Backend startup script
│   ├── run-gateway.bat             ← Gateway startup script
│   └── marquee_display.py          ← Marquee renderer (disabled)
└── secrets_loader.py               ← DPAPI vault + .env fallback
```

---

*End of briefing. Good luck downstairs.*
