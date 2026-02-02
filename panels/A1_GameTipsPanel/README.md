# 📘 Game Tips Panel (A1)

**Grid Slot:** Row 1, Column A (`col-span-1 row-span-1`)
**Agent Owner:** Hera
**Design Authority:** Promethea
**Connected Agents:** Claude (layout), Hephaestus (game context), Hermes (cloud tips)

---

## 🎯 Purpose

This panel displays game-specific tips, codes, and strategies based on the currently running title. It queries the local knowledgebase or Firebase (if online) and surfaces contextual help like combos, unlockables, cheat codes, or secret moves.

---

## 🎨 Visual Blueprint

| Zone     | Elements                                                           |
|----------|--------------------------------------------------------------------|
| Header   | `Book` Icon, `"Game Tips"` title, `StatusChip` (Idle / Found / N/A) |
| Toolbar  | (Optional: Refresh Button)                                         |
| Content  | `<TipsList>` with bullet items based on game context               |
| Footer   | Data source label (e.g. "Local", "Firebase", "Manual Entry")       |

---

## 🧩 Required Components (Hera)

- `TipsList.tsx`
  - Accepts an array of tips as strings
  - Formats as `list-disc` bullet points

- `StatusChip.tsx`
  - Shows `"Idle"` (no game), `"Found"` (game matched), or `"Unknown"`

- (Optional) `RefreshButton.tsx`
  - Calls context detection service again (via Hephaestus)

---

## 🔁 Connected Agents

| Agent        | Purpose                                         |
|--------------|--------------------------------------------------|
| **Claude**       | Panel layout creation (via Promethea)           |
| **Hephaestus**   | Game process detection + context resolution     |
| **Hermes**       | Cloud-based tip sourcing (Firebase fallback)    |

---

## ⚠️ Rules

- Must never error out if no game detected
- Must gracefully show "No tips found" empty state
- Tips may not exceed 5 lines per panel view (paginate if needed)

---

## ✅ Status

- [x] Design complete (Promethea layout)
- [ ] `index.tsx` ready for implementation
- [ ] Connected to context service (Hephaestus)
- [ ] Firebase fallback (Hermes)

---