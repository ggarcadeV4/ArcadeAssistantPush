# Claude Rules (Anthropic) — Arcade Assistant

## Role
Primary reasoning + instruction-following model for routing, planning, and structured edits through approved APIs.

---

## Hard Boundaries
- Use **only** approved endpoints via Node BFF + FastAPI (never raw file I/O).
- For config edits: call **preview first** → show diff → only on approval, call **apply with backup**.
- Do **not** edit GUI bundles, assets, or Builder.io exports (immutable at runtime).
- Do **not** modify `README.md` except via the Session Closure Mandate.

---

## Required Behaviors
1. **Cite Scope in Requests:** Always include `x-scope` header that matches domain (`config|state|backup`).
2. **Constrain Keys:** Only propose patches for keys allowed by emulator's policy schema; reject unknown keys.
3. **Explainability:** Summarize the change and rationale before applying.
4. **Fail Safe:** If preview and apply differ, abort and surface mismatch.

---

## Response Template (for mutating ops)
- **Intent:** what we're changing and why
- **Preview:** diff snippet from `/config/preview`
- **Risks:** one-liner warnings
- **Apply Plan:** endpoint + scope + backup expectation
- **Result:** backup_path, affected files
- **Rollback:** explicit restore command with backup_path

---

## Preferences
- Use schema-validated patch endpoints over generic writes.
- Favor minimal targeted diffs, not whole-file rewrites.
- Additive doc changes only if user explicitly asks.