# Codex Rules (Code-Gen Agent) — Arcade Assistant

## Role
Generate **scaffolded code** and tests under strict boundaries. Never directly patch live configs or docs.

---

## Absolute No-Gos
- ❌ No direct filesystem writes outside test fixtures.
- ❌ No runtime edits to React build or Builder.io exports.
- ❌ No modifications to `README.md` or policy files unless explicitly assigned and reviewed.

---

## Musts
1. **Scaffold Only:** Write server code behind interfaces:
   - Node BFF adapters (Claude, ElevenLabs) with timeouts/retries/limits.
   - FastAPI endpoints that implement **dry-run → backup → apply** flow.
2. **Policy-First Endpoints:** Only build endpoints tied to whitelisted schemas (`/mame/config/apply`, `/retroarch/config/patch`). Reject unknown keys.
3. **Tests Before Merge:**
   - Unit tests: diff, backup path creation, rollback.
   - Contract tests: `x-scope` enforcement + path whitelist.
4. **One-Thing PRs:** One panel/service per PR. Include API docs + usage examples.

---

## Safe Coding Patterns
- All paths resolved under `AA_DRIVE_ROOT` + manifest.json. No absolute guessing.
- Logs redact keys + sensitive paths; local only.
- No eval/exec/subprocess without feature flag (off by default).

---

## PR Checklist
- [ ] Endpoint enforces scope
- [ ] Preview endpoint exists and used
- [ ] Backup-before-write confirmed
- [ ] Rollback tested with backup_path
- [ ] Unknown keys rejected by schema/policy