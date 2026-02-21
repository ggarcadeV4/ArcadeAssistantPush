## 📌 VICKY VOICE PANEL — RESTRUCTURE SPEC (Version 1)

### 1. Quick Start Section Removal
- The current Quick Start row (Dad Solo, Dad + Kid Y, Full Family, Custom Setup) disappears entirely.
- All preset logic goes with it: `applyFavorite()`, preset-loading helpers, and related API hooks are removed or ignored.
- No hidden replacement or relocation; Version 1 does **not** support these buttons any longer.

### 2. New Top Band: Player Overview
- The space formerly used by Quick Start is now **Player Overview**, containing exactly two tiles side-by-side:
  - **Tendencies Tile**  
    - Title format: `[PrimaryUserName]’s Tendencies`.  
    - Read-only view fed from `/profiles/<primary-user-id>/tendencies.json`.  
    - No editing controls; it simply surfaces the JSON data.
  - **Permissions Tile**  
    - Reuses the existing Permissions tile (same trigger / consent flow).  
    - Shares the row with the Tendencies tile; no other widgets live in this band.

### 3. Current Session Table Updates
- The main Current Session grid (Player 1‑4 rows, User/Controller selectors) remains untouched structurally.
- **New requirement:** Each User dropdown gains a `+ Add user` option that initiates new profile creation. This ties player slots directly to newly created profiles.

### 4. Bottom Section: Primary User
- Rename the existing “Personal Contacts & Training” block to **Primary User**.
- Messaging: “This is the main profile Arcade Assistant will operate under for this session.”
- Field list stays the same (display name, initials, voice assignments, custom vocab, training phrases, STT confidence) but the semantics change to reflect cabinet ownership/operator status.

### 5. Primary User is System-Wide Identity
- All panels/agents (Sam, Dewey, LoRa, Chuck, LED, Gunner, Doc, etc.) should key off **`primary_user_id`** when referencing this profile.
- Tendencies data (see Section 2) will also be tied to this same ID.

### 6. Shared Session Payload (future reference)
```
{
  "session_id": "<uuid>",
  "primary_user_id": "<id>",
  "slots": [
    { "player": 1, "user_id": "dad",   "controller": "Arcade P1" },
    { "player": 2, "user_id": "kid_y", "controller": "8BitDo #1" }
  ]
}
```
- Placeholder schema only—no implementation required in Version 1.

### 7. Out-of-Scope (Version 2+)
- Gameplay voice commentary, coaching mode, voice-over narration.
- Multi-profile contact lists, cross-panel voice scripting, family unit logic, session favorites.
- These features are intentionally deferred; Version 1 focuses solely on the structural changes above.
