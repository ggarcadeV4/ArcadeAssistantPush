# GEMS_PIVOT_VIGILANCE.md
**Date:** February 3, 2026  
**Purpose:** Primary instruction set for the Gem-Agent refactor

---

## REDLINES — Absolute Hardware Anchors (Do Not Touch)

| File | Protected Element | Rationale |
|------|-------------------|-----------|
| `backend/services/led_engine/ledwiz_driver.py` | `SUPPORTED_IDS` whitelist | Hardware device enumeration must remain stable for LED-Wiz detection |
| `backend/services/mame_pergame_generator.py` | `XINPUT_CLEAN_MAP` | Gamepad mapping integrity for per-game MAME configs |
| `backend/services/mame_config_generator.py` | `JOYCODE` generation logic | Critical for joystick input binding in MAME |
| `config/mappings/controls.json` | Path and schema are **immutable** | Foundation for all control mappings across emulators |

> [!CAUTION]
> Any modification to the above files or elements will break hardware compatibility. These are non-negotiable.

---

## API Contract — GUI Safety

The following JSON keys in `/api/launchbox/chat` responses are **public-stable** and must not be renamed, removed, or have their semantics altered:

```json
{
  "success": true,
  "response": "...",
  "rounds": [...],
  "game_launched": true
}
```

> [!IMPORTANT]
> The frontend GUI depends on these keys. Breaking changes here will cause runtime failures in the React frontend.

---

## Stateless Goal

**Objective:** Migrate `sessionStore` (Lines 66-135 of `gateway/routes/launchboxAI.js`) to the new `aa_lora_sessions` Supabase table.

- Eliminate in-memory session state from the gateway process.
- Enable horizontal scaling and cabinet failover without session loss.
- All session reads/writes must flow through Supabase.

---

## Execution Order

### Phase 1: Implement RemoteConfigService
- Create a service that fetches cabinet configuration from the `cabinet_config` Supabase table.
- This replaces hardcoded model references and feature flags.

### Phase 2: Create Supabase `aa_lora_sessions` Table and State-Sync Logic
- Design table schema for session persistence.
- Implement CRUD operations for session state.
- Migrate `sessionStore` logic to use Supabase.

### Phase 3: Incrementally Extract LoRa Logic into `gems/aa-lora/`
- Create the `gems/aa-lora/` directory structure.
- Move LoRa-specific logic from `launchboxAI.js` into modular gem files.
- Maintain backward compatibility with existing API contract.

---

## Confirmation

✅ This file has been written to the repository root as the primary instruction set for the Gem-Agent refactor. No code changes will be proposed until this document is acknowledged.
