# 🧭 AGENT_CALL_MATRIX.md

**Status:** Authoritative
**Purpose:** Defines mandatory agent involvement per task
**Scope:** All Claude Code, Cursor Copilot, and LLM-based contributions to the Arcadia System
**Location:** /agents/AGENT_CALL_MATRIX.md
**Enforcement:** Referenced by `CLOUD_STARTUP.md`, `UNIVERSAL_AGENT_RULES.md`, and `CLAUDE_CREW.md`

---

## 🔁 Invocation Protocol

When executing any task in the Arcade Assistant or ArcadiaOS codebase, the AI must:

1. Identify task type from this matrix
2. Invoke all **Required Agents**
3. Optionally consult **Advisors** for context
4. Log results to `agent_boot.log` or `task_call.log`

If a required agent is skipped, the output is considered **invalid**.

---

## 📋 Matrix Key

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|

---

### 🎛️ Panel Design & UI Tasks

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| New panel layout (BasePanel structure) | **Promethea** | Lexicon, Oracle | Must follow `PROMETHEA_GUI_STYLE_GUIDE.md`; No raw code |
| Implement panel UI (React) | **Hera** | Promethea, Lexicon | Uses `PanelTemplate`; Must preserve visual structure |
| Update existing panel visuals | **Hera** | Aether, Lexicon | No layout changes; accessibility required |
| Add microphone control | **Echo** | Hera, DebugPanel | Toolbar-only; must propagate mic state |
| Build Debug Panel (C3) | **Hera** | Argus, Oracle | Must render diagnostics in all states |
| Apply dark mode/visual theme changes | **Hera** | Promethea | No global CSS; must use Tailwind tokens |

---

### 🔌 Hardware & Voice Logic

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Detect gamepad/USB connection | **Argus** | DebugPanel | All changes must be broadcast to DebugPanel |
| LED Blinky or RGB lighting sync | **Argus** | None | No blocking calls; fallback if hardware missing |
| Implement mic permission logic | **Echo** | Hera, Janus | Must gracefully handle `getUserMedia` failure |
| Display mic listening state | **Echo** | Hera | Must use `<StatusChip>`; sync with toolbar |

---

### 🧠 System Intelligence & Repair

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Detect broken emulator config | **Hephaestus** | Argus, DebugPanel | Must log error + suggest fix (never apply silently) |
| Suggest fix for controller mapping | **Hephaestus** | Argus | Fix must be user-approved |
| Sync fix to Firebase | **Hermes** | Hephaestus, Janus | User must be online & authenticated |
| Escalate to community knowledgebase | **Hermes** | Lexicon | Entry must be sanitized; no secrets |

---

### ⚙️ Services & Optimization

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Optimize Python config watcher | **Pythia** | Hephaestus, Oracle | May not change public interfaces |
| Refactor hardware service loop | **Pythia** | Argus | Must retain logging and fault recovery |
| Improve React performance | **Aether** | Hera | Can use memoization; must not change behavior |
| Add or reorganize component exports | **Aether** | Lexicon | File tree changes must reflect in index.json |

---

### ☁️ Cloud / Data Integrity

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Push config to Firebase | **Hermes** | Janus | Must support offline fallback |
| Store API key for cloud agent | **Hermes** | Janus | Keys must be encrypted locally |
| Audit config change before push | **Janus** | Oracle | Block if critical fields altered without backup |
| Update remote knowledgebase index | **Hermes** | Lexicon | Ensure field consistency, schema compliance |

---

### 📜 Metadata, Discovery, Navigation

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Create `index.json` for new module | **Lexicon** | Claude | Must include file roles, tags, owner, inputs/outputs |
| Generate glossary or linkmap | **Lexicon** | All | Use consistent vocab per `PROMETHEA_GUI_STYLE_GUIDE.md` |
| Annotate top of new service file | **Lexicon** | Pythia | Use structured comments for other agents |
| Help agent locate relevant file | **Lexicon** | Claude, Hera | Respond with direct path and summary only |

---

### 🔍 Auditing, Errors & Failsafes

| Task | Required Agent(s) | Optional Advisors | Rules/Notes |
|------|-------------------|-------------------|-------------|
| Run full system audit | **Oracle** | All | Logs to `/logs/audits/{date}_report.md` |
| Scan for layout drift / broken panels | **Oracle** | Promethea, Hera | Compares against baseline screenshots |
| Detect security violations in agent output | **Janus** | Oracle | May trigger fail and rollback |
| Log failing panel logic for debugging | **DebugPanel (via Hera)** | Echo, Argus, Hermes | All panels forward critical errors here |

---

### ❌ Forbidden Tasks Without Invocation

If the following tasks are attempted **without the required agents**, the output is invalid and must be discarded:

- Creating a panel layout without Promethea
- Writing visual React code without Hera
- Handling mic behavior without Echo
- Refactoring performance without Aether or Pythia
- Syncing configs without Janus and Hermes
- Discovering file roles without Lexicon

---

## 🧪 Logging Format

All AI task calls must log execution to:

```
/logs/agent_calls/{date}_calls.log
```

Log Format:

```
[Time] ClaudeCode called: Hera → panels/B2_ControllerMapper
[Time] Hera confirmed: used PanelTemplate, followed layout rules
[Time] Hera deferred voice logic to Echo
```

---

## 📌 Final Rule

> "If you don't know who should handle it — **ask Lexicon.**"

---