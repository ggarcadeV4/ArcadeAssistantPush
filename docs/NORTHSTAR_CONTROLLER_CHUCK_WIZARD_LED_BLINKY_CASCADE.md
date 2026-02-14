## Northstar: ControllerChuck → ConsoleWizard → LEDBlinky Cascade

Purpose: capture the end-to-end plan for persistent controller defaults and automatic propagation across encoder boards, handheld profiles, LED lighting, and emulator configs. Use this as the handoff blueprint for the next implementation session.

---

### 1. Current State (as of 2025-10-29)
- **ControllerChuck panel**
  - Loads encoder mappings from `/api/local/controller/mapping`.
  - Applies updates and restores defaults via backend endpoints.
  - Newly-added chat context includes board, mapping, detected handhelds.
  - No persistent “home profile” metadata beyond the raw mapping file.
  - LEDBlinky sync is manual/out of band.

- **ConsoleWizard panel**
  - Detects handheld controllers and profiles.
  - Applies RetroArch configs and presents staged status for other emulators.
  - Persona overlay shows “pending/staged/applied” but actual cascade is not wired.
  - No shared persistence with Chuck beyond whatever profile the user happens to pick.

- **Backend services**
  - `/api/controllers/autoconfig/detect|mirror` exist behind feature flag.
  - Controller AI service aggregates hints and mapping summaries.
  - No centralized store for “customer baseline controller layout”.
  - No orchestrated job that chains encoder → LEDBlinky → emulator mirrors.

- **LED Blinky**
  - Depends on external scripts or manual invocation.
  - Not tied to controller mapping apply events.

---

### 2. Gaps / What’s Missing
1. **Persistent Baseline**
   - Need a dedicated record (e.g., JSON in `state/` or `config/`) representing the customer-defined “home layout” (pins, labels, handheld profile, flags).
   - Panels should read/write this record consistently so defaults survive restarts and are accessible to both personas.

2. **Apply Cascade**
   - When Chuck applies a mapping:
     - Update encoder mapping file (existing behavior).
     - Update baseline record.
     - Trigger LEDBlinky mapper with the same layout.
     - Kick off handheld/emulator mirror pipeline (RetroArch + others).
   - Need progress tracking + error capture so the UI can report partial failures.

3. **Wizard Integration**
   - Wizard should read the same baseline when it opens (pre-select profile/player, toggles).
   - After RetroArch apply, it should either:
     - Confirm the cascade already ran (if Chuck fired it), or
     - Trigger the remaining emulator mirrors and reconcile status badges automatically.

4. **Backend Wiring**
   - New service layer (e.g., `controller_baseline.py`) handling:
     - Read/write of baseline file.
     - Helper to translate encoder mapping → LEDBlinky input.
     - Helper to hydrate wizard panel state.
   - Orchestration endpoint or background task (FastAPI) that sequences:
     1. LEDBlinky update.
     2. RetroArch staging (if not already done).
     3. Auto-config mirror for each supported emulator.
     4. Status persistence (per emulator) for UI consumption.

5. **UI Feedback**
   - Chuck panel needs a status region similar to the wizard overlay showing cascade progress (LED, RetroArch, etc.).
   - Wizard sidebar should flip badges to “Ready” automatically when cascade completes.
   - Persona responses should reference the shared baseline (“I see your home layout is X; I’ll sync it now.”).

---

### 3. Implementation Plan

#### A. Baseline Persistence
1. **Schema definition**
   - File path suggestion: `state/controller/baseline.json`.
   - Fields: version, timestamp, encoder mapping summary, led profile name, wizard profile id, player, toggle flags (hotkeys/deadzones), last cascade status per system.
2. **Backend helpers**
   - `get_controller_baseline(drive_root)`
   - `set_controller_baseline(drive_root, data)` (with backup + validation).
   - Utility to merge partial updates (e.g., wizard toggles without overwriting pins).
3. **Panel integration**
   - Chuck loads baseline on mount; if absent, prompts user to define one.
   - Wizard loads baseline to pre-select profile and options.

#### B. Cascade Orchestration
1. **API contract**
   - New endpoint: `POST /api/controller/cascade/apply`
     - Input: baseline snapshot + optional flags (e.g., `skip_led`).
     - Output: job id + immediate status summary.
   - Reuse existing apply route to call into cascade helper after encoder write.
2. **Execution flow**
   - Step 1: Validate baseline + current mapping.
   - Step 2: Write encoder mapping (existing).
   - Step 3: Update baseline file.
   - Step 4: Invoke LEDBlinky mapper (ensure guardrails for `x-scope=config`).
   - Step 5: Stage RetroArch config if not already in sync.
   - Step 6: Loop through other emulators (MAME, Dolphin, PCSX2, etc.) using auto-config manager.
   - Step 7: Record per-emulator result (success/failed + messages).
3. **Status tracking**
   - Store last-run summary in baseline file.
   - Optional: expose `GET /api/controller/cascade/status` for UI polling.

#### C. UI Updates
1. **ControllerChuck**
   - Add “Cascade Status” card showing LEDBlinky + emulator states with timestamps.
   - Provide manual “Retry Cascade” button if downstream steps fail.
   - Update persona prompts to reference cascade progress.
2. **ConsoleWizard**
   - Consume baseline to set default profile/toggles.
   - Replace placeholder badges with live data (ready/staged/pending) from baseline status.
   - When user applies from wizard, call cascade endpoint (option to skip encoder if unchanged).
3. **Shared components**
   - Consider a shared `useCascadeStatus()` hook that polls the backend and feeds both panels.
   - Ensure skeleton/loading/error states follow Promethea guide.

#### D. LEDBlinky Sync
1. **Backend integration**
   - Identify existing CLI/script to update LED profiles.
   - Wrap it in a service call (`update_led_blinky_profile`).
   - Log output and capture errors for UI display.
2. **Baseline mapping**
   - Map encoder pins/button labels to LED zones.
   - Store LED profile name/path in baseline for quick reference.

#### E. Testing & Validation
1. **Unit tests**
   - Baseline read/write with invalid data.
   - Cascade orchestrator with mocked LED/emulator calls.
2. **Integration tests**
   - End-to-end apply: encoder mapping -> baseline -> LED -> RetroArch -> emulator mocks.
3. **Manual verification**
   - Run cascade, restart stack, confirm baseline reloads correctly.
   - Simulate partial failure (e.g., LED tool missing) and verify UI guidance.

---

### 4. Prep Work for Next Session
- Confirm which emulator auto-config adapters are production-ready (list endpoints + coverage).
- Decide on baseline schema versioning (include `version` key in JSON).
- Inventory LEDBlinky invocation path (Windows vs WSL vs Linux).
- Clarify whether cascade should block UI (synchronous) or run async with polling.
- Draft user-facing copy for Chuck/Wiz when cascade succeeds or partially fails.

---

### 5. Open Questions
1. Should cascade trigger automatically on every apply, or should users opt-in per panel?
2. Do we need rollback logic if LED or emulator updates fail mid-flight?
3. How do we handle multiple handheld profiles (P1 vs P2) – separate baseline per player or single mapping?
4. Any security considerations when storing baseline in `state/` (e.g., multi-user installs)?

---

### 6. Summary
Deliverable is a unified controller baseline with an automated cascade across encoder hardware, LED lighting, and emulator configs. Achieving it requires backend persistence, an orchestrated apply pipeline, and UI feedback loops in both panels. Use this document as the runbook for the implementation session so we can execute methodically without rediscovering context.
