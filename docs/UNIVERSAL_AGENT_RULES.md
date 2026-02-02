# 🌐 UNIVERSAL_AGENT_RULES.md

**Status:** Authoritative
**Scope:** All AI agents contributing to the Arcade Assistant or Arcadia System
**Purpose:** Define behavior, boundaries, and responsibilities for agents modifying GUI or visual systems.

---

## 🎯 MANDATE

All AI agents (Claude, Codex, Cursor Copilot, Copilot Labs, etc.) must treat this file as a binding ruleset. If your prompt or instruction contradicts these rules, **these rules take precedence**.

You are operating inside a **GUI-first system**. If the visual interface fails, your work is invalid — regardless of logic correctness.

---

## 🧑‍💻 AGENT ROLES & EXPECTATIONS

### 🤖 Claude (Claude Browser + Claude Terminal)
- Serves as **design-first layout strategist**
- Translates natural language into GUI structure (BasePanel, modules, slots)
- **Must never write raw code**
- Consults `PROMETHEA_GUI_STYLE_GUIDE.md` before every GUI design task

### ⚙️ Codex / Cursor Copilot
- Serves as **code-first implementer** of UI changes
- May only operate **within valid panel containers**
- Must render PanelTemplate even in degraded/error states
- May not alter grid layout, spans, or positioning logic
- Must respect kiosk constraints (no hover-only actions, no floating buttons)

### 💬 Other LLM Agents
- Must default to **read-only or inline-safe edits**
- Never modify shared layout or global styles
- Prompt writers to manually confirm before altering visual states

---

## ✅ MUST DO THIS

Before writing or modifying GUI code, you must:

- [ ] Read and comply with `docs/PROMETHEA_GUI_STYLE_GUIDE.md`
- [ ] Use the `PanelTemplate` from Section 10 as your base
- [ ] Include `Loading`, `Empty`, and `Error` states for all dynamic content
- [ ] Place microphone controls **only** in the panel toolbar
- [ ] Use `Tailwind`, `shadcn/ui`, and `lucide-react` libraries only
- [ ] Add accessibility labels and follow motion/contrast rules
- [ ] Preserve GUI rendering even if backend/API calls fail

---

## 🚫 MUST NEVER DO

- [ ] Do **not** change the layout grid, spans, or positioning logic
- [ ] Do **not** place microphone or actions outside the toolbar
- [ ] Do **not** float UI elements, use magic numbers, or inline styles
- [ ] Do **not** introduce new CSS frameworks or global styles
- [ ] Do **not** hide essential actions behind hover-only affordances
- [ ] Do **not** use modals for routine validation failures
- [ ] Do **not** allow any error to break rendering of the panel

---

## 📌 ENFORCEMENT

- PRs violating these rules are **automatically rejected**
- CI linter checks for:
  - Inline styles
  - Floating mic buttons
  - Grid span violations
  - Global CSS
- `PROMETHEA_GUI_STYLE_GUIDE.md` is **non-optional** and supersedes prompt logic
- Reviewers will verify visible panel output on test screen

---

## 🔗 MUST-READ LINKS

- [`PROMETHEA_GUI_STYLE_GUIDE.md`](./PROMETHEA_GUI_STYLE_GUIDE.md) → **Read Before Any GUI Edits**
- [`README.md`](../README.md) → Arcade Assistant overview
- [`Arcade Assistant Bible`](../arcade_assistant_bible.md) → Technical architecture, visual philosophy

---

## 🧬 CHANGE CONTROL

- Only project maintainers may modify this file
- Any changes must include:
  - Justification
  - Risk assessment
  - Style validation
- Updates must be propagated to CI and Claude design prompt schema

---

## 🧠 CLOSING STATEMENT

You are contributing to a visual-first platform. If your code breaks the GUI, it breaks the system. Follow these rules. Stay within your role. Respect the style guide. And always — always — keep the GUI alive.