# AI HELPERS — READ FIRST (Golden Drive)

> **If you are an AI model (Codex, Claude, Gemini, GPT, etc.), read this file before doing anything else.**

---

## What This Is

This drive is the **Golden Drive master** for Arcade Assistant. It will be duplicated via a physical drive duplicator. Changes must be **deliberate**, **minimal**, and **verified**.

---

## Non-Negotiables

- ❌ **Do not "clean up" or refactor.** Only implement the specific task requested.
- ❌ **Do not delete or rename folders** unless explicitly instructed.
- ❌ **Do not change ports, base URLs, or startup flow** unless explicitly instructed.
- ❌ **Do not move files to "better structure."** The structure is the product.
- ❌ **No breaking changes.** If something is uncertain, audit first and report.

---

## Required Workflow (Always)

### 1. Pre-Audit First (Codex-style)

- Locate files involved
- Identify exact call paths
- List risks and blast radius
- Provide a minimal fix plan

### 2. Then Implement (Claude-style)

- Smallest possible changes
- No unrelated edits
- Verification steps included

### 3. Then Verify

- Smoke test launcher
- Validate UI loads
- Validate critical endpoints

---

## Golden Drive Safety Rules

- Treat this drive like **firmware**.
- Prefer **additive changes** over modifications.
- If a change touches **routing**, **startup**, or **I/O**, require a test checklist.

---

## "Gateway Is The Law"

Any UI/service that needs backend data **must use the gateway API route** (not direct backend access), unless explicitly authorized.

This prevents future migration breakage.

---

## Supabase Keys and Security

- ❌ **Never print or expose keys** in logs or UI.
- ❌ **Never add secrets to git** or plaintext in new files.
- ⚠️ If asked to touch Supabase auth/RLS/functions, **propose changes first** — do not apply silently.

---

## What "Done" Means

A task is **not done** until you provide:

| Requirement | Description |
|-------------|-------------|
| **Files changed/created** | Exact list of paths |
| **What was tested** | Exact commands or clicks |
| **What to watch for** | Failure modes and recovery steps |

---

## Quick Reference

| Item | Value |
|------|-------|
| Repo root | `A:\Arcade Assistant Local` |
| Production launcher | `start-aa.bat` |
| Dev launcher | `start-aa-dev.bat` |
| Backend port | `8000` |
| Gateway port | `8787` |
| Logs location | `A:\.aa\logs\` |
| Contract doc | `GOLDEN_DRIVE_CONTRACT.md` |
