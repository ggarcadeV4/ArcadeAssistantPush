# ☁️ CLOUD_STARTUP.md

**Purpose:** Enforce AI agent startup behavior across all Arcadia System environments.
**Scope:** Applies to any cloud-based LLM or embedded agent acting within Arcade Assistant, ArcadiaOS, or related tools.
**Status:** Binding contract at runtime.

---

## 🚦 Startup Requirements for All Agents

Before performing any task — including design, code, or configuration — every AI agent must:

1. **Acknowledge current environment**
   - Project = Arcade Assistant / ArcadiaOS
   - Context = GUI-first architecture, visual feedback loop required

2. **Initialize project constraints**
   - ✅ 3×3 fixed layout grid
   - ✅ GUI must render under all conditions
   - ✅ Panels must be self-contained and resilient

3. **Load enforcement files**
   - `docs/PROMETHEA_GUI_STYLE_GUIDE.md`
   - `UNIVERSAL_AGENT_RULES.md`

If these files are not present, halt execution and display an inline alert:
**"Missing agent policy files. Cannot proceed safely."**

---

## 🔐 Runtime Agent Behavior Contract

At runtime, agents must:

- Respect fixed layout zones (`col-span-1 row-span-1`)
- Maintain visible GUI even during load/fail states
- Never modify layout grid or inject global styles
- Fail gracefully with `<InlineError />` or `<EmptyState />`
- Defer to Claude Browser for structural interpretation
- Defer to Promethea as style authority

---

## 🧭 Claude-Specific Directives

Claude Browser and Claude Terminal must:

- Always begin by interpreting the current goal into a **BasePanel layout schema**
- Use **Arcade Assistant vocabulary** (Panel, Toolbar, CardHeader, etc.)
- Never output raw code — only structured, styled layout instructions

---

## 🧪 Validation & Logging

Agents must log:

- Which guides were loaded
- Whether GUI startup passed structural integrity checks
- Any violations of `PROMETHEA_GUI_STYLE_GUIDE.md`

Logs should be stored under:

```
/system/logs/agent_init/
└── {timestamp}_agent_boot.log
```

Example:

```
✔️ Loaded PROMETHEA_GUI_STYLE_GUIDE.md
✔️ Verified panel integrity (9 of 9 visible)
⚠️ Found 1 warning: Missing mic button in Control Panel C
```

---

## 🚫 Startup Aborts If...

- Missing or unreadable guide files
- Critical layout violations detected
- GUI is not renderable at boot

Agents must refuse to proceed and render:
> **"Startup validation failed. Visual interface could not initialize safely. Please fix layout or consult style guide."**

---

## ✅ Summary: Agent Oath of Operation

Every AI agent operating inside the Arcade Assistant ecosystem must:

> 📜 "Read the guides. Respect the grid. Keep the GUI alive. Always design with visibility, resilience, and respect for the user."

---

## 📞 Agent Invocation Enforcement

Before any AI-generated change is accepted into the system:

- `AGENT_CALL_MATRIX.md` must be consulted
- Required agents must be invoked per task type
- Task logs must be written to `/logs/agent_calls/`

If any agent is skipped, the output must be rejected with this error:

> ❌ Agent call incomplete. Required specialist not invoked. See AGENT_CALL_MATRIX.md for valid task delegation.

---

## 🔗 Required Reads at Agent Boot

| File | Purpose |
|------|---------|
| `PROMETHEA_GUI_STYLE_GUIDE.md` | Enforces all GUI layout/design constraints |
| `UNIVERSAL_AGENT_RULES.md`    | Core behavior, scope, sandbox rules |
| `AGENT_CALL_MATRIX.md`        | Defines task-specific agent delegation |
| `CLAUDE_CREW.md`              | Lists all known agents and their domains |

---