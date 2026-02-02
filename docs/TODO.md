Next (P1):

 Pairing: implement resolve_rom_for_launch() and wire DuckStation/Dolphin/Flycast/Model2/Supermodel.

 PS1: prefer .cue then .chd then .bin; temp-extract archives first.

 Flycast: prefer .gdi; ensure companion files resolved; extract archives first.

 Model2/Supermodel: temp-extract zip; pass correct ROM arg to CLI.

 Add AA_LAUNCH_TRACE JSON line per launch; add scripts/verify_pairing.py.

 Add friendly errors for MISSING-EMU (which key) and MISSING-ROM (which stem/exts).

 Run verify-pairing (dry-run) for 3 titles per adapter; paste summary.

 If all green, flip AA_ADAPTER_DRY_RUN=0 and real-launch one title per adapter.


Session 2025-10-16 — Pending To‑Dos (Stabilization)

- Add resolver diagnostics: GET /api/launchbox/diagnostics/resolve?game_id=...&adapter=... to dump exe|args|cwd for a single game (speed up Model2/Supermodel tuning).
- Flycast decision: provide flycast.exe path (e.g., A:\Emulators\Flycast\flycast.exe) or keep Naomi/Atomiswave on RetroArch; update configs/emulator_paths.json accordingly and re‑verify.
- Finish Model2 pairing: zip→AA_TMP_DIR/<stem>, cwd to extracted folder (or single inner folder), -rom=<romname>; confirm on known‑good title; ensure temp cleaned (trace shows "temp cleaned").
- Finish Supermodel pairing: zip→AA_TMP_DIR/<stem>, cwd to extracted folder, <romname> -fullscreen; confirm on known‑good title; ensure temp cleaned.
- Detected‑emulator leg: investigate and fix Windows path issue (e.g., C:\mnt\a\...). Optionally set AA_DIRECT_FIRST=true while plugin offline to avoid detected path glitches during testing.
- Verify scripts: add short backoff for Model2/Supermodel to avoid throttle collisions; keep claimed_ok in summaries.
- Proof run: live_audit → dry_run_acceptance → verify_pairing; target ok=3 and claimed_ok=3 for DuckStation/Dolphin/Flycast/Model2/Supermodel.
- Acceptance run: flip AA_ADAPTER_DRY_RUN=0 and live‑launch one known‑good title per adapter; paste 5 trace lines {game_id, adapter, resolved_file, command, notes, dry_run:0}.
