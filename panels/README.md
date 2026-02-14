# 🎛️ Panel Ownership Grid

| Panel ID | Title              | Grid Slot | Status  | Owner  | Last Verified |
|----------|--------------------|-----------|---------|--------|----------------|
| A1       | Game Tips Panel    | Row 1 / A | Ready   | Claude | ✅ 2025-09-26   |
| B2       | Controller Mapper  | Row 2 / B | Draft   | Codex  | ⬜              |
| C3       | Debug Panel        | Row 3 / C | Active  | Codex  | ✅ 2025-09-26   |

## How To Add a Panel

1. Create a folder under `panels/PanelNamePanel/`
2. Use `PanelTemplate` from `PROMETHEA_GUI_STYLE_GUIDE.md`
3. Register it here with a unique ID and slot
4. Assign the responsible agent (`Claude`, `Codex`, or `Human`)