# drive-map.json — Schema (Generated)

Purpose: Canonical, static snapshot of A: drive emulator and content layout for AI-first routing and diagnostics. Generated via backend `/drive-map/*` routes and stored under `A:/configs/drive-map.json`.

---

## Generation
- Endpoint: `POST /drive-map/preview` → returns diff and JSON without writing
- Endpoint: `POST /drive-map/apply` → writes file with automatic backup and logs to `/logs/changes.jsonl`
- Sanctioned path: `configs/drive-map.json` (under `AA_DRIVE_ROOT`)

---

## JSON Structure

```json
{
  "generated_at": "2025-10-13T22:45:12Z",
  "host": "windows|wsl|linux",
  "is_on_a_drive": true,
  "status": "human-readable status of LaunchBox structure",
  "emulators": [
    {
      "name": "RetroArch",
      "exe": "A:/LaunchBox/Emulators/RetroArch/retroarch.exe",
      "type": "retroarch",
      "cores": ["stella2014_libretro.dll", "snes9x_libretro.dll"],
      "info": { "stella2014": { "zip": true, "firmware": [] } }
    },
    {
      "name": "PCSX2",
      "exe": "A:/LaunchBox/Emulators/PCSX2/pcsx2.exe",
      "type": "native",
      "supports": { "ext": ["bin", "cue", "iso", "chd"], "lightgun_profile": false }
    }
  ],
  "rom_roots": ["A:/Console ROMs", "A:/Roms"],
  "lb_platforms": ["Atari 2600", "Nintendo Entertainment System", "Arcade"],
  "lightgun_panels": ["Light Guns"]
}
```

Notes
- This is read-only input for policy and diagnostics. Runtime should not dynamically rescan; regenerate the file when the environment changes.
- All paths derive from `AA_DRIVE_ROOT` and `LaunchBoxPaths` constants to maintain fixed-structure guarantees. Emulator directories are discovered only under fixed roots: `A:/LaunchBox/Emulators` and `A:/Emulators`.

---

## Alignment
- Follows ARCHITECTURE.md (no dynamic discovery at runtime; static artifact only).
- Complements `docs/A_DRIVE_INTENT_MAP.md` and `docs/ROUTING_POLICY_SCHEMA.md`.
