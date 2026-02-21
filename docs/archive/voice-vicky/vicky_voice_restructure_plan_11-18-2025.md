## Implementation Plan — Vicky Voice Restructure

### Checklist
- [ ] Remove the entire Quick Start UI block (Dad Solo/Dad + Kid/Full Family/Custom/Permissions row).
- [ ] Ensure all preset-specific logic (`applyFavorite`, preset constants, API hooks) is deleted or disabled.
- [ ] Insert a new **Player Overview** row where Quick Start lived.
  - [ ] Add the **Tendencies** tile (read-only UI).
  - [ ] Wire the Tendencies tile to read `/profiles/<primary-user-id>/tendencies.json`.
  - [ ] Keep the **Permissions** tile exactly as-is and left beside Tendencies.
- [ ] Leave the Current Session table structure intact, but add `+ Add user` to each User dropdown.
- [ ] Rename the bottom “Personal Contacts & Training” section to **Primary User** and update its messaging (fields stay the same).
- [ ] Confirm no other panel regions change unintentionally.

### Do Not Implement (Version 2 scope)
- Gameplay commentary / narration / coaching.
- Multi-profile contact lists or family unit logic.
- Session favorites or preset logic reintroductions.
- Cross-panel auto-routing or wizard flows.
- Any “Quick Start” behaviors beyond the removal described above.

### Intended Outcomes
- Vicky Voice becomes purposeful and aligned with Version 1 requirements.
- The panel reflects session truth (primary user, tendencies, permissions) without redundant preset UI.
- Primary user identity gains a clear logical home that all agents can reference through `primary_user_id`.

### Guardrail
Before modifying any file, I will re-open `vicky_voice_restructure_11-18-2025_1-45am.md` and confirm each planned change matches the documented requirements.
