# A: Drive — Intent & Policy Map (Authoritative)

Status: LOCKED — Architectural contract for folder purposes, ownership, and agent-safe behaviors. Changes require explicit approval.

Why this exists: Prevent breakage across sessions, agents, and panels by freezing path intent and allowed operations. Use this document with ARCHITECTURE.md and A_DRIVE_MAP.md.

---

## Ground Rules

- Fixed structure: Do not rename, move, or dynamically discover paths. Use `AA_DRIVE_ROOT` + documented constants.
- Plugin-first: Game launching and emulator selection flow through LaunchBox (HTTP plugin bridge). No direct executor calls from agents by default.
- Write discipline: AI agents write only to sanctioned paths declared in `/.aa/manifest.json` and scoped via `x-scope` headers; everything else is read-only unless human-approved.
- Backups: Any config mutation goes through preview → backup → apply with `backup_path` logged to `/logs/changes.jsonl`.

---

## Top-Level Folders — Purpose, Owner, Policy

Below paths are relative to `A:\` (Windows) or `/mnt/a/` (WSL).

1) `LaunchBox/`
- Intent: Primary game library (metadata, images, videos), native launcher UI, plugin host.
- Owner: LaunchBox + Human.
- Read/Write: Read-only for AI agents. Exception: Arcade Assistant plugin writes its own logs under `LaunchBox/Logs/ArcadeAssistant/`.
- Panels touching it: LaunchBox LoRa (read-only via backend parsing, plugin bridge).

2) `Emulators/`
- Intent: General-purpose emulator installations for non–light-gun use (RetroArch, MAME, Dolphin, PCSX2, RPCS3, etc.).
- Owner: Human (install/upgrade); Backend reads for health checks only when feature-flagged.
- Read/Write: Read-only for agents. No patching emulator configs here; use sanctioned `/configs` overlays and preview/apply endpoints.
- Notes: This is the “general” emulator set. See duplication policy below.

3) `Roms/`
- Intent: Arcade ROMs (e.g., MAME) organized by system.
- Owner: Human.
- Read/Write: Strictly read-only for agents.
- Panels: LaunchBox LoRa (game metadata correlates to these), System Health (read-only counts).

4) `Console ROMs/`
- Intent: Console ROMs organized by platform (NES, SNES, etc.).
- Owner: Human.
- Read/Write: Read-only for agents.

5) `Bios/`
- Intent: BIOS files for various emulators.
- Owner: Human.
- Read/Write: Read-only for agents.
- Note: Agents must never attempt to “fix” BIOS by writing here.

6) `Gun Build/`
- Intent: Dedicated light-gun environment with its own emulator copies/configs and game collections where applicable.
- Owner: Human (install/upgrade); Backend reads to report health status when flagged.
- Read/Write: Read-only for agents. Treat as a separate “role” from `Emulators/`.
- Panels: LightGuns (Gunner), LaunchBox LoRa (plugin decides actual launcher; agents do not force this path).

7) `ThirdScreen-v5.0.12/`
- Intent: Marquee/tertiary display software and assets.
- Owner: Human.
- Read/Write: Read-only for agents.

8) `Tools/`
- Intent: Utilities (AutoHotkey, reshade tools, controller utilities, etc.).
- Owner: Human.
- Read/Write: Read-only for agents. Agents may reference tool paths for documentation; no execution without feature flag.

9) `_INSTALL/` or `INSTALL/`
- Intent: Installation packages and offline installers (VC++ redistributables, codecs, DirectX, etc.).
- Owner: Human.
- Read/Write: Read-only for agents.

---

## Launching & Selection Policy

- Source of truth: LaunchBox (via plugin bridge) selects emulator and command lines per game/platform. Agents must not override emulator selection with hard-coded binaries.
- Direct fallback: Disabled by default (`AA_ALLOW_DIRECT_EMULATOR=false`). Only used for diagnostics when explicitly enabled.
- Path conversions: When needed, adapters handle `A:\` ↔ `/mnt/a/` translation; however, plugin-first eliminates cross-OS path risk for launches.

---

## Emulator Duplication Policy (Light-Gun vs General)

Problem: Some emulators exist twice — a general build and a light-gun–tuned build.

Policy:
- Roles are distinct and intentional:
  - General emulators live under `A:\Emulators\<Name>`.
  - Light-gun emulators and assets live under `A:\Gun Build\...` (may mirror emulator names with different configs).
- Selection is owned by LaunchBox:
  - Game/platform assignment inside LaunchBox determines which build runs (general vs light-gun).
  - AI agents do not force-switch emulators; they request launch by GameId via the plugin.
- Maintenance discipline:
  - Version parity: When upgrading an emulator, evaluate both builds; document differences in a human-maintained changelog (outside agent scope).
  - Config overlay approach: Any AI-authored config changes must be expressed as overlays via sanctioned endpoints, not edits inside the emulator folders.

Optional metadata (future):
```json
// Example of a read-only descriptor an agent might look for (do not require it):
{
  "emulator": "mame",
  "role": "light-gun",
  "location": "A:/Gun Build/MAME",
  "notes": "Sinden profiles; aim-off calibration"
}
```

---

## Panels → Filesystem Footprint (Read/Write Boundaries)

- LaunchBox LoRa
  - Reads: LaunchBox platform XML metadata, images via backend proxy.
  - Writes: None to A:; launches via plugin.

- LED Blinky
  - Reads: None from A:; drives hardware via gateway.
  - Writes: Only to sanctioned `/configs` (mapping) and `/state` (session tests) through preview/apply.

- Controller (Wizard/Mapper)
  - Reads: None from A:. Optional: controller DB references living in repo.
  - Writes: Only `/configs` overlays and `/state` cache via preview/apply.

- ScoreKeeper Sam
  - Reads: None from A:.
  - Writes: `/state/scores.jsonl` via preview/apply; backup recorded to `/backups/YYYYMMDD` and `/logs/changes.jsonl`.

- Voice Assistant
  - Reads/Writes: Local `/state` for audio/voice profile caches; never writes to A:.

- System Health / Debug
  - Reads: Counts and health checks are read-only on A: (sizes, existence checks).
  - Writes: None to A:.

---

## Sanctioned Write Paths (Agent)

Declared in `/.aa/manifest.json`:

- `/configs` — configuration overlays produced by preview/apply endpoints (schema-validated, reject unknown keys).
- `/state` — ephemeral/local state (scores, caches). Not a source of truth for content.
- `/backups/YYYYMMDD` — automatic backups created before apply.
- `/logs` — JSONL change logs and agent boot/call logs.
- `/emulators/*` — Only when explicitly provisioned by a dedicated endpoint and whitelisted schema (generally avoided; prefer overlays).

Agents must never write to: `A:\LaunchBox\`, `A:\Roms\`, `A:\Console ROMs\`, `A:\Bios\`, `A:\Gun Build\`, `A:\Tools\`, `A:\ThirdScreen-v5.0.12\`, `A:\_INSTALL\`.

---

## Canonical Path Constants

Use these exact constants wherever code refers to A: content (examples shown in Windows and WSL):

- LaunchBox root: `A:\\LaunchBox` (`/mnt/a/LaunchBox`)
- Platform XMLs: `A:\\LaunchBox\\Data\\Platforms\\*.xml`
- MAME ROMs: `A:\\Roms\\MAME\\*.zip`
- BIOS root: `A:\\Bios\\`
- Emulators (general): `A:\\Emulators\\<EmulatorName>\\`
- Light-gun env: `A:\\Gun Build\\<EmulatorName or Subsystem>\\`

---

## Change Control & Ownership

- Human owns physical installs (LaunchBox, emulators, ROMs/BIOS, tools).
- Agents own only overlay configs and local state within sanctioned paths.
- Any proposal to alter top-level A: folders requires an RFC and explicit approval; agents must not generate such changes.

---

## Quick Reference (Do / Don’t)

Do
- Go through LaunchBox plugin to launch by GameId.
- Use preview → backup → apply for any config change.
- Treat `Gun Build` as a separate light-gun role, not a duplicate to merge.

Don’t
- Don’t write inside emulator folders or LaunchBox content.
- Don’t dynamically scan for “best path.” Use constants above.
- Don’t switch emulator binaries in code; LaunchBox is the source of truth.

---

## Appendix: Alignment With Existing Docs

- ARCHITECTURE.md — fixed structure doctrine and path rules (must-read).
- A_DRIVE_MAP.md — inventory and structure overview.
- docs/LAUNCHBOX_PLUGIN_ARCHITECTURE.md — plugin-first flow and endpoints.
- AGENTS.md, docs/CODEX_RULES.md, docs/CLAUDE_RULES.md — agent write boundaries and preview/apply contract.

