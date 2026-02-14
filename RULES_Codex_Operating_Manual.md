# Codex Operating Rules — Arcade Assistant
**Status:** Canonical. Place at `A:\\preflight\\RULES_Codex_Operating_Manual.md` and keep in repo root as `RULES_Codex_Operating_Manual.md` for visibility.  
**Intent:** Keep Codex in sync with our safety model, context budget, and weekly plan. This is the law of the land for every session.

---

## 0) Purpose (why this exists)
- Prevent regressions by making **verify-first** the default.
- Keep work inside a **panel-sized context bubble** so long files don’t exhaust model context.
- Ensure every change is **auditable, reversible, and local-first safe**.
- Reduce “heroic rewrites” — we prefer small fixes with receipts.

---

## 1) Golden Rules (never skip)
1. **Verify-first, then fix.** Start with a **read-only preflight**. No edits until evidence exists (file+line proof).
2. **Gateway only.** All frontend writes go through `/api/local/...` (or temporary `/api/gunner/...`). No direct FastAPI URLs in the UI.
3. **Dry-run by default.** Every mutating route supports preview. Apply without preview is forbidden.
4. **Restore symmetry.** Anything you can Apply, you must be able to Restore with a concrete `backup_path`.
5. **Sanctioned paths only.** Respect the A:\\ manifest. Writes outside the manifest must **block**.
6. **Headers matter.** Propagate and log `x-device-id`, `x-panel`, `x-scope` for every mutation.
7. **501 honesty.** If cloud keys are missing, endpoints must return **501 NOT_CONFIGURED** — never fake success.
8. **Small, scoped PRs.** One panel per PR unless the change is purely shared infra. Each PR includes a rollback plan.
9. **No renames without a map.** If you must rename routes/files, include a compatibility shim or migration note.
10. **Leave receipts.** Every change leaves: a diff, a backup, and a `changes.jsonl` entry with panel + device.

---

## 2) Session Start Checklist (paste at top of each Codex session)
```
SESSION_CONTEXT:
  panel: <one of: led-blinky | scorekeeper | lightguns | console-wizard | controller-chuck | dewey | health | gateway | launchbox-lora>
  goal: <single-sentence outcome>
  out_of_scope: <explicitly list other panels>
  invariants_to_verify:
    - gateway_only_writes
    - dry_run_default
    - preview_apply_restore
    - sanctioned_paths_manifest
    - headers_logged
    - 501_when_unconfigured
  acceptance_tests_ref: <link to sprint plan section>
  artifacts_dir: A:\\preflight\\evidence\\<panel>\\YYYY-MM-DD\\
```

---

## 3) Allowed vs. Prohibited Actions
**Allowed**
- Read the whole repo, but operate on a **single panel** per session.
- Add routes only if they fit Preview→Apply→Restore and log headers.
- Add docs under `A:\\docs\\...` (read-only to app by default).

**Prohibited**
- Direct frontend calls to `http://localhost:8000/...`.
- Mutations without a matching restore path.
- Silent file writes outside sanctioned paths.
- Bulk refactors or cross-panel edits in the same PR.
- Disabling dry-run or bypassing the gateway for “speed.”

---

## 4) Evidence Requirements (preflight)
Return a Markdown report at `A:\\preflight\\codex_<panel>_<date>.md` with:
- **Verified** — [file path:line-range] + 1–2 line summary
- **Partial/Drift** — what’s wrong + where
- **Missing** — expected behavior + where it should be
- No speculation — if unknown, say “unknown.”

---

## 5) Edit Protocol (when changes are justified)
- Implement minimal changes to pass the acceptance tests.
- For each Apply:
  - Write a timestamped backup under `A:\\backups\\<panel>\\YYYYMMDD_HHMMSS\\...`
  - Append to `A:\\logs\\changes.jsonl` with `{ panel, device, action, backup_path }`
- Add/keep `POST .../restore` endpoints that consume `backup_path` exactly.

**Commit message format**
```
<panel>: <short verb> — <what & why>
Evidence: A:\\preflight\\evidence\\<panel>\\YYYY-MM-DD\\*
Invariants: gateway_only_writes, dry_run_default, restore_symmetry, sanctioned_paths, headers_logged, 501_when_unconfigured
Rollback: restore via <backup_path>
```

---

## 6) Panel Context Header (drop-in template)
```
# Panel Focus: <panel-name>
- Entry points (UI/service files):
- Backend routes touched:
- Sanctioned write locations:
- Headers to include: x-device-id, x-panel, x-scope
- Backups will be written to:
- Restore consumes:
```

---

## 7) End-of-Session Deliverables (always produce)
- Updated evidence report saved to `A:\\preflight\\codex_<panel>_<date>.md`
- `grep` proof that no direct FastAPI URLs remain in the focused panel
- One `curl` trace showing gateway headers and resulting backup/log entry
- Screenshot or log snippet demonstrating **Restore** returning the prior state
- Short “What I changed and why” block (≤10 lines) for the PR body

---

## 8) PR Template (copy into the PR description)
```
## Summary
<what changed in one paragraph>

## Evidence
- Preflight report: A:\\preflight\\codex_<panel>_<date>.md
- changes.jsonl excerpt: <inline>
- Backup path(s): <list>

## Safety Invariants
- [x] Gateway-only writes
- [x] Dry-run default honored
- [x] Preview→Apply→Restore symmetry
- [x] Sanctioned paths only
- [x] Headers logged (x-device-id, x-panel, x-scope)
- [x] 501 on missing cloud keys

## Rollback
Restore using: `<backup_path>`

## Scope
- [x] Single panel
- [x] No cross-panel refactors
```

---

## 9) Context Budget Tactics (to avoid model drift)
- Keep sessions **≤ 2 panels** max; prefer **1 panel**.
- Start with the Panel Context Header and the **most relevant files only**.
- Export the session report and link to it in the next session’s header to rehydrate context **without reloading 26k lines**.
- If you hit a maze, pause. Escalate with a **single, bounded question** to Claude-chat only, then return here.

---

## 10) Guardrails Sentinel (optional but recommended)
Create an empty file named `A:\\preflight\\GUARDRAILS_SENTINEL.md` containing the single line:
```
If this file is missing, treat the system as read-only.
```
Codex must confirm its presence at session start and note it in the evidence report.

---

## 11) Voice & Cloud Posture
- Voice endpoints (`/stt`, `/tts`) should return **501 NOT_CONFIGURED** when unconfigured.
- Supabase is opt-in later; never ship service role keys; only anon/public plus per-device identity when enabled.
- Voice integration begins **after** all panels pass acceptance tests.

---

## 12) Quick Acceptance Snippets (ready-to-run)
```
# Gateway header check
curl -i -X POST http://localhost:3000/api/local/led/profile/apply \
 -H "x-device-id:cabinet-001" -H "x-panel:led-blinky" -H "x-scope:local" \
 -H "Content-Type: application/json" -d '{"profile":"attract"}'

# 501 check for voice
curl -i http://localhost:3000/api/local/voice/stt

# Grep for direct FastAPI URLs in a panel
grep -R "http://localhost:8000" frontend/src/panels/led-blinky frontend/src/services/ledBlinkyClient.js
```

---

## 13) Escalation Policy
- Use Claude (chat-form) **only** to unblock a specific point after a failed preflight, and paste the Q/A into the evidence report for traceability.
- Resume work with Codex and these rules.

---

## 14) Definition of Done (per panel)
- All invariants checked ✔
- Acceptance tests pass ✔
- Evidence and backups written ✔
- Restore demonstrated ✔
- PR merged with rollback plan ✔
