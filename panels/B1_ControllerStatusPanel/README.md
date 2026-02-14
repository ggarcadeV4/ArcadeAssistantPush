# 🎮 Controller Status Panel (B1)

**Grid Slot:** Row 2, Column A (`col-span-1 row-span-1`)
**Owner Agent:** Hera
**Data Agent:** Argus (real-time hardware monitor)
**Design Authority:** Promethea
**Render Priority:** High — user must always know current controller state

---

## 🎯 Purpose

This panel displays all connected input devices in real-time. It reflects device names, player assignments, input types (USB, HID, iPAC), and highlights recent activity. It also logs connection/disconnection events and alerts the DebugPanel on unexpected changes.

---

## 🎨 Visual Blueprint

| Zone     | Elements                                                                 |
|----------|--------------------------------------------------------------------------|
| Header   | `Gamepad` Icon, `"Controllers"` title, `StatusChip`: Connected / Error   |
| Toolbar  | (Optional: [Remap All], [Refresh])                                       |
| Content  | `<DeviceList>`: Each row = Controller + Player + Type + Status + Input log |
| Footer   | Detected devices count, Last updated timestamp                           |

---

## 🧩 Required Components (Hera)

- `DeviceList.tsx`
  - Accepts array of `{ name, player, type, status }`
  - Displays scrollable list with compact layout

- `StatusChip.tsx`
  - Green: All connected
  - Yellow: Some missing
  - Red: Drift/error detected

- `ConnectionEvent.tsx` (Optional)
  - Renders: "Player 2 reconnected: 8BitDo SN30 Pro @ 17:14"

---

## ⚙️ Connected Agent

| Agent     | What It Supplies                            |
|-----------|----------------------------------------------|
| **Argus**     | Real-time controller list via USB/HID polling |
| **DebugPanel**| Displays drift or disconnects              |
| **Hephaestus**| Remapping history (optional future use)    |

---

## 🛡️ Rules

- Must update live on connect/disconnect events
- Must not break if no devices present (empty state shown)
- All errors must propagate to DebugPanel
- Tooltips should show full device ID if truncated

---

## ✅ Status

- [x] Layout spec complete
- [ ] `index.tsx` scaffold pending
- [ ] Argus hook pending
- [ ] StatusChip wired to Argus stream

---