# routing-policy.json — Schema (Authoritative Draft)

Purpose: Hand-edited policy guiding launch routing and safe fallbacks in an AI-first, plugin-first system. This policy does not override LaunchBox; it annotates preferences and guardrails when the plugin is offline or for diagnostics.

File location (at runtime): `A:/configs/routing-policy.json`

---

## Core Principles
- Plugin-first: Launch via LaunchBox plugin by GameId when available.
- No dynamic path selection at runtime. This policy is static data read by the backend; changes go through preview → backup → apply.
- Never force emulator binaries if LaunchBox can decide. Policy is advisory for fallbacks only.
- Direct/fallback toggles are server-side only. Do not expose via `VITE_*` or client envs.

---

## JSON Structure (minimal)

```json
{
  "policy_version": "1.0",
  "order": ["plugin", "detected_emulator", "direct", "launchbox"],
  "mame_protected": ["Arcade", "MAME", "FinalBurn Neo"],
  "platform_map": {
    "Atari 2600": { "adapter": "retroarch", "core_key": "Atari 2600", "profile": "general" },
    "Sega Genesis": { "adapter": "retroarch", "core_key": "Sega Genesis", "profile": "general" },
    "Sony PlayStation": { "adapter": "pcsx2", "profile": "general" },
    "TeknoParrot (Light Guns)": { "adapter": "teknoparrot", "profile": "lightgun" }
  },
  "profiles": {
    "general": {},
    "lightgun": { "ahk_wrapper": true, "input_profile": "guns", "exclusive_fullscreen": true }
  },
  "diagnostics": { "log_routing": true, "log_to": "logs/routing-decisions.jsonl" }
}
```

Notes
- MAME guard prevents accidental RetroArch direct paths for arcade-first platforms.
- Light-gun is a profile, not a separate emulator; map panels/platforms to profile rather than hardcoding binaries.
- The backend should read this file once at startup and cache it.

---

## Change Control
- Update via backend endpoint (preview/apply) only; take an automatic backup and write to `/logs/changes.jsonl` with `x-scope: config`.
- Reject unknown top-level keys to keep policy stable.

---

## Alignment
- Matches ARCHITECTURE.md fixed-structure doctrine.
- Defers to LaunchBox plugin for actual launch decisions.
- Complements `docs/A_DRIVE_INTENT_MAP.md` and `docs/LAUNCHBOX_PLUGIN_ARCHITECTURE.md`.
