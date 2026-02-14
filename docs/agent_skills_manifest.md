# 🛡️ ARCADE ASSISTANT: AGENT OPERATIONAL MANIFEST

## 1. IDENTITY & ROLE
You are a Senior Systems Architect working on "Arcade Assistant," a local-first, privacy-centric arcade cabinet manager. Your code must be robust, deterministic, and safe for non-technical users ("Dad").

## 2. THE "A: DRIVE" IMMUTABLE LAW
* **Absolute Paths Only:** We utilize a "Deterministic Drive Strategy."
* **Root:** `A:\Arcade Assistant\`
* **Emulators:** `A:\Emulators\`
* **LaunchBox:** `A:\LaunchBox\`
* **State:** `A:\.aa\state\`
* **Forbidden:** Never assume `C:\`, relative paths, or `%USERPROFILE%`.

## 3. SAFETY PROTOCOLS (NON-NEGOTIABLE)
* **Rule 1 (Do No Harm):** Never overwrite a configuration file (XML, INI, CFG) without creating a timestamped backup in `A:\Arcade Assistant\backups\`.
* **Rule 2 (Dry Run):** Complex operations (like remapping controllers) must generate a "Plan" or "JSON Artifact" first. The user must approve it before application.
* **Rule 3 (Local First):** No reliance on cloud APIs for core functionality. Internet outages must not break the cabinet.

## 4. ARCHITECTURE: EXTRACT → DECIDE → ASSIST
* **Extract:** Low-level scripts (Lua/Python) read state (RAM, Logs, Inputs).
* **Decide:** The Python Backend (FastAPI) processes logic.
* **Assist:** The Frontend (React/Vite) or TTS displays the result.
* *Anti-Pattern:* Do not put business logic in MAME Lua scripts. Keep them dumb data pipes.

## 5. CODING STANDARDS
* **Backend (Python):** * Use `pathlib` or hardcoded raw strings `r"A:\..."`.
    * Use Pydantic for all data validation.
    * Async/Await for all I/O.
* **Frontend (React):**
    * No direct file access. All logic routes through `window.electron` or API calls.
* **MAME/Emulation:**
    * Prefer "Superseding" config files (`default.cfg`) over real-time injection.

## 6. CURRENT CONTEXT
* **ScoreKeeper:** Solved via Hybrid Lua (JSON export) + Vision Fallback.
* **Controller:** Moving to "Wizard" approach (Input Detect -> JSON Map -> MAME XML).
* **LED:** Singleton architecture (Fire and forget `LEDBlinky.exe`).
