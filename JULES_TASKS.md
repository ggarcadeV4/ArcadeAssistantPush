# Jules Overnight Tasks — 2026-03-04

> **Repo**: `Arcade-Assistant-0304-2026` (branch: `master`)
> **Rule**: Do each task in order. Commit after each one. Do NOT change architecture, routing, or AI logic.

---

## Task 1: Sidebar CSS — Solid Backgrounds + Per-Persona Accents

**File**: `frontend/src/components/engineering-bay/EngineeringBaySidebar.css`

The shared Engineering Bay sidebar is too transparent and has no per-persona identity. Fix it:

1. Find the main sidebar container's `background` property (likely using `rgba` with transparency or `backdrop-filter: blur`)
2. Change the background to solid `#0a0c10`
3. Remove any `backdrop-filter: blur(...)` on the sidebar container
4. Ensure the sidebar still slides in/out correctly after the change

Then update the per-panel CSS accent overrides. Each panel that uses `EngineeringBaySidebar` passes a CSS custom property `--eb-accent`. Verify these files set the correct accent:

| Panel File | Accent Color | Variable |
|-----------|-------------|----------|
| `frontend/src/panels/controller/chuck-sidebar.css` | `#22c55e` (Green) | `--eb-accent` |
| `frontend/src/panels/wizard/*.css` (or inline) | `#a78bfa` (Purple) | `--eb-accent` |
| `frontend/src/panels/led-blinky/*.css` (or inline) | `#A855F7` (Purple) | `--eb-accent` |
| `frontend/src/panels/gunner/*.css` (or inline) | `#A855F7` (Purple) | `--eb-accent` |
| `frontend/src/panels/voice/*.css` (or inline) | keep existing | `--eb-accent` |

If a panel does not have a CSS file setting `--eb-accent`, create one or add the variable inline where the `<EngineeringBaySidebar>` is rendered.

**Commit message**: `fix: solid sidebar backgrounds + per-persona accent colors`

---

## Task 2: Scrub Mojibake from ScoreKeeper Sam

**File**: `frontend/src/panels/scorekeeper/ScoreKeeperPanel.jsx`

This file has corrupted encoding characters scattered throughout (artifacts from copy-paste or encoding issues). Find and replace ALL instances of:

- `??` → remove or replace with appropriate clean text
- `` (backtick pairs with nothing) → remove
- `ðŸ'¬` → replace with empty string or an appropriate emoji if context is clear
- `â¹ï¸` → replace with empty string
- Any other mojibake (garbled multi-byte characters that look like `Ã©`, `â€™`, `Ã¼`, etc.)

Replace fallback/placeholder values with clean strings like `"N/A"` or `"--"`.

Do NOT change any logic, state management, or component structure. Only fix display strings.

**Commit message**: `fix: scrub mojibake from ScoreKeeperPanel`

---

## Task 3: Scrub Mojibake from Vicky Voice Panel

**Files**: `frontend/src/panels/voice/VickyVoicePanel.jsx` (or similar)

Same as Task 2 — find and remove all mojibake characters:
- `ðŸ'¬` → replace with clean SVG icon or empty string
- `â¹ï¸` → remove
- Any garbled encoding artifacts

Also fix the `buildDefaultPlayers` array ordering to be exactly players 1, 2, 3, 4 in that order.

**Commit message**: `fix: scrub mojibake from VickyVoicePanel`

---

## Task 4: Remove Mock Data from Gunner

**File**: `frontend/src/panels/gunner/DevicesTab.jsx` (or `GunnerPanel.jsx`)

Find and remove all hardcoded mock data:
- Fake "20% battery alert" — remove the hardcoded battery percentage and alert
- Any hardcoded device arrays with fake device names/IDs
- Replace removed mock data with empty state displays (e.g., "No devices detected" placeholder)

Do NOT delete the component structure or UI layout. Just remove the fake data and show empty/placeholder states instead.

**Commit message**: `fix: remove hardcoded mock data from Gunner DevicesTab`

---

## Task 5: Wiz Slide-Out Drawer Fix

**File**: `frontend/src/panels/wizard/ConsoleWizardPanel.jsx` (or similar)

The Engineering Bay sidebar slide-out drawer does not retract properly when the close button or backdrop is clicked.

1. Find where `<EngineeringBaySidebar>` is rendered
2. Ensure `isOpen` and `onClose` props are passed correctly
3. The `onClose` handler should set the sidebar's open state to `false`
4. If there's a backdrop overlay, clicking it should also trigger `onClose`
5. Test by verifying the close button click toggles the state variable that controls `isOpen`

**Commit message**: `fix: Wiz sidebar drawer retraction on close`

---

## Task 6: LED Blinky Panel Identity

**File**: `frontend/src/panels/led-blinky/LEDBlinkyPanelNew.jsx` (or `LEDBlinkyPanel.jsx`)

1. Find the `BLINKY_PERSONA` constant or config object
2. Update the accent color to `#A855F7` (Purple)
3. If there's a background set, change it to `#0a0c10`
4. Fix any incorrect icon references (the panel icon should be a lightbulb or LED-related icon)
5. Ensure the sidebar uses standard slide-in CSS transitions (same `transition` properties as other panels)

**Commit message**: `fix: Blinky panel identity — purple accent + solid bg`

---

## Task 7: Gunner Panel Theme

**Files**: `frontend/src/panels/gunner/GunnerPanel.jsx` and related CSS

1. Apply Purple theme: accent `#A855F7`
2. Set solid `#0a0c10` background (remove transparency)
3. If "Coming Soon" stubs exist on Calibration/Profiles/Retro tabs, leave them for now (we'll recover the content separately)

**Commit message**: `fix: Gunner panel theme — purple accent + solid bg`

---

## General Rules for Jules

1. **Run `npx vite build` after EVERY task** to verify no build errors
2. **Do NOT modify**: `backend/` files, `.env`, `ai.py`, `tts.py`, prompt files
3. **Do NOT change**: routing in `App.jsx`, component imports, state management logic
4. **Do NOT install** new npm packages
5. **Commit after each task** with the specified commit message
6. If unsure about a file location, search with `grep -r "searchterm" frontend/src/`
