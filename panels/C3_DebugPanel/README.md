# 🧰 Debug Panel (C3)

**Grid Slot:** Row 3, Column C (`col-span-1 row-span-1`)
**Agent Owner:** Hera
**Design Authority:** Promethea
**Render Status:** Always-On — this panel must never be conditionally hidden

---

## 🎯 Purpose

The Debug Panel serves as the **central command console** for system health, voice status, device monitoring, and agent event logs. It is the primary surface for identifying and remediating runtime issues, especially when failures occur silently in other parts of the system.

---

## 🎨 Visual Blueprint (Promethea Layout)

| Zone     | Elements                                                                 |
|----------|--------------------------------------------------------------------------|
| Header   | `Wrench` Icon, `"Debug Console"` title, `StatusChip (Online/Offline/Error)` |
| Toolbar  | (Optional future buttons: [Clear Log], [Download Report])                |
| Content  | - `<AgentLiveLog />`<br>- `<SystemStatus />` grid (Mic, Devices, Cloud, Auditor)<br>- `<InlineError />` (if active issues)<br>- Timestamp footer |

---

## 🧩 Required Components (Hera)

- `AgentLiveLog.tsx`
  - Displays a vertical feed of real-time agent events
  - Should auto-scroll with new entries
  - Source: `logs/agent_calls/` + internal agent events

- `SystemStatus.tsx`
  - Grid-style widget
  - Props: `label`, `value`, `agent`
  - Includes colored badge or icon per agent (Echo, Argus, etc.)

- `InlineError.tsx`
  - Already part of shared system
  - Accepts short message + optional action (e.g. "Click to fix")

---

## 🧠 Connected Agents

| Agent     | Reports Into This Panel                             |
|-----------|------------------------------------------------------|
| **Echo**      | Microphone state, permission errors, wake failures |
| **Argus**     | USB/HID connection issues, remapping drift         |
| **Hermes**    | Firebase key failures, cloud offline states        |
| **Oracle**    | System audit results, layout integrity violations  |
| **Janus**     | Security violations, config write attempts         |

All agents must **fail upward** to this panel if their domain breaks silently.

---

## ⚠️ Rules

- Panel must render even if voice, backend, or input systems fail
- Must never crash on missing data — show "N/A" or fallback states
- Panel must respect `prefers-reduced-motion`
- Voice mic state must remain synchronized with actual `Echo` status

---

## ✅ Status

- [x] Layout Approved by Promethea
- [ ] Connected to `AgentLiveLog`
- [ ] Connected to `SystemStatus`
- [ ] Error pipeline from Echo / Argus functional

---