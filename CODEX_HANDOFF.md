# Codex - Execute Information Gathering

**From:** Implementation Agent
**To:** Codex
**Purpose:** Gather 4 pieces of information to boost confidence from 7.0 → 8.5

---

## Context

I've fixed 3 bugs in the hotkey system:
1. ✅ Gateway feature flag timing
2. ✅ Backend port mismatch
3. ✅ JSON parse error on "pong"

Backend and gateway are running cleanly with no errors. But I have 3 unknowns that are blocking me from high confidence.

**You need to verify:**
1. Is HotkeyOverlay mounted in App.jsx?
2. Does Python keyboard library work on this machine?
3. Does HotkeyOverlay.css exist?
4. Are there port conflicts?

---

## YOUR INSTRUCTIONS

**Read:** [CODEX_INFO_REQUEST.md](CODEX_INFO_REQUEST.md)

**Execute:** All 4 checks exactly as written

**Report:** Use the format template at the bottom of that file

**Do NOT:**
- Skip any checks
- Modify the test scripts
- Interpret results - just report exact output
- Make any code changes yet (we'll decide after seeing results)

---

## Expected Timeline

- CHECK 1: 30 seconds (grep commands)
- CHECK 2: 2 minutes (create and run Python test)
- CHECK 3: 30 seconds (file checks)
- CHECK 4: 1 minute (process/port checks)

**Total: ~4 minutes**

---

## After You Report

Implementation Agent will:
1. Analyze your findings
2. Update confidence score
3. Fix any issues found (missing CSS, duplicate processes, etc.)
4. Hand back to user with clear go/no-go decision

---

## Questions?

If any command doesn't work on Windows, report the exact error and I'll provide Windows equivalent.

**Ready to execute? Read CODEX_INFO_REQUEST.md and begin.**
