# 🏁 ARCADIA FINAL RUN: The Completion Roadmap

**Mission:** Complete the Arcade Assistant by strictly adhering to the "Low-Tech Reliability, High-Tech Experience" philosophy.
**Strategy:** "V8 Engine in a Lamborghini Body." Simple, proven backend logic wrapped in a magical UI.
**Workflow:** Define Module -> Code Archaeology (Find existing 90%) -> Audit Logic -> Build -> Verify.

---

## 📅 MODULE A: The Controller "Engine" (The Wizard)
**Focus:** Reliability, Input Detection, MAME Config Generation.
**The "Nova" Engine:** Pure Python. No fancy UI logic here. Just raw input handling.

* **A.1: Code Archaeology**
    * Find `input_detector.py` (Does it handle XInput axes?).
    * Find `mame_config_generator.py` (Does it handle Device IDs?).
    * *Goal:* Identify the "90%" we already have.
* **A.2: The Input Normalizer**
    * *Task:* Build/Refine the detector to return normalized `{"type": "joy", "id": 1, "code": "BUTTON0"}` regardless of hardware (Keyboard vs. Xbox).
    * *Constraint:* Must handle "Triggers as Axes" (XInput Quirk).
* **A.3: The "Rosetta Stone" (controls.json)**
    * *Task:* Define the strict JSON schema that sits between the hardware and MAME.
* **A.4: The MAME Writer**
    * *Task:* Generate `default.cfg` XML.
    * *Safety:* Backup existing `.cfg` before overwrite.

## 🎨 MODULE B: Controller Chuck (The "Lambo" Body)
**Focus:** UX Magic, Visual Feedback, Customer Facing.
**The Experience:** User sees a beautiful controller on screen. They press a button, it lights up.

* **B.1: The Visualizer**
    * *Task:* Wire the React frontend to the `input_detector` WebSocket.
    * *Goal:* Zero-latency visual feedback ("I press A, screen flashes A").
* **B.2: The "Magic" Mapping**
    * *Task:* UX flow for "Press UP... Press DOWN...".
    * *Logic:* Auto-advance to the next button. Error handling if they press the wrong thing.
* **B.3: The Integration**
    * *Task:* The "Apply" button. Calls Module A to write the files.

## 💡 MODULE C: LED Orchestrator (LEDBlinky)
**Focus:** Singleton CLI Management. "Low-Tech" Fire-and-Forget.

* **C.1: The Wrapper**
    * *Task:* Python wrapper for `LEDBlinky.exe`.
    * *Logic:* No process killing. Just subprocess calls.
* **C.2: The "Attract Mode" Hook**
    * *Task:* Trigger lighting profiles on Game Launch/Exit.

## 🏆 MODULE D: ScoreKeeper (The Polish)
**Focus:** GUI Wiring for the Lua Plugin.

* **D.1: The Listener**
    * *Task:* Frontend WebSocket listens for `mame_scores.json` updates.
* **D.2: The Announcer**
    * *Task:* Trigger TTS only on *New High Score*.

## 🔧 MODULE E: "The Mechanic" (AI Auto-Config)
**Focus:** Natural Language to Config File Manipulation.
**The Feature:** "I want scanlines" -> AI edits `mame.ini`.

* **E.1: The Map Maker**
    * *Task:* Map common user intents ("Scanlines", "Volume", "Difficulty") to specific file locations (`mame.ini`, `retroarch.cfg`).
* **E.2: The Safe Editor**
    * *Task:* Regex-based config replacer.
    * *Safety:* Strict "Preview/Apply/Rollback" flow.

---

## 🛑 GOVERNANCE CHECKLIST (Per Session)
1.  **Paste Manifest:** Start session with `agent_skills_manifest.md`.
2.  **Audit:** "Gemini, scan `backend/` for existing code related to [Module]."
3.  **Spec:** "Gemini, audit this logic plan for holes."
4.  **Code:** Claude Code executes the implementation.
