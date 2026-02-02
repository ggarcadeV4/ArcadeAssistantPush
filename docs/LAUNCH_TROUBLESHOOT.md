# Launch Troubleshooting

If an emulator UI opens instead of launching the game directly:

- Enable trace for one request: set `AA_LAUNCH_TRACE=1` and relaunch.
- Inspect `logs/launch_attempts.jsonl` for the entry:
  - Confirm `resolved_file` points to the actual content (e.g., `.cue`, `.gdi`).
  - Verify `command` includes the correct flags (e.g., `dolphin -b -e <file>`).
- Check `configs/emulator_paths.json` for the emulator’s `executable_path`.
- For archives, ensure `AA_TMP_DIR` has free space; adjust `AA_EXTRACT_MIN_FREE_GB` as needed.
- For PS1, prefer `.cue`; for Flycast, prefer `.gdi` and ensure companion files are present.

Use `scripts/verify_pairing.py` to dry-run three titles per enabled adapter and print a one-line summary.

