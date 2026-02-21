# PactoTech Smoke Test

Use the helper script `scripts/pactotech_smoke.sh` to exercise the Controller Chuck endpoints end-to-end (sanity, repair, firmware preview, mapping recovery, mapping apply). The script defaults to `DEVICE_ID=CAB-0001`, `PANEL=controller`, and gateway `http://localhost:8787`.

```bash
chmod +x scripts/pactotech_smoke.sh
./scripts/pactotech_smoke.sh
```

It prints each curl request and response (formatted with `jq` when available) so Greg can quickly confirm the stack wiring without modifying state. Override `DEVICE_ID` or `BASE` by exporting environment variables before running if needed.

### PactoTech Board Tools Smoke Test

To quickly verify that the PactoTech board sanity, repair, firmware preflight, and mapping endpoints are wired correctly from Gateway → FastAPI → Chuck UI, run the pactotech_smoke.sh script.

```bash
# From the project root, with Gateway+Backend running:
bash scripts/pactotech_smoke.sh
```

Each step prints JSON so you can manually confirm:

1. **Board Sanity** – returns the FastAPI sanity report/summary; expect `board_detected=true` on real hardware or a clear `board_not_detected` issue when running on a dev machine.
2. **Repair (Dry Run)** – returns a `RepairReport` showing `actions_attempted`/`actions_successful`; no HID writes occur unless you’ve enabled them.
3. **Firmware Preview (Stub)** – returns a `FirmwarePreview` with `compatibility_check`, inferred `new_version`, and any detected `current_version`.
4. **Mapping Recovery Preview** – returns the stub `MappingRecoveryResult` (“Teach mode not implemented yet”).
5. **Mapping Apply (Dry Run)** – returns a `MappingApplyReport` with `changes_count` and summary but no disk writes.

This script is a developer-only harness, handy after restarting Codex or making larger refactors to ensure the PactoTech path still responds before handing controls back to Greg.

### Daily Slice – PactoTech Auto-Recovery

- **Sanity** – `GET /api/local/controller/board/sanity` with `x-scope: state` invokes `BoardSanityScanner` and returns `BoardSanityResponse` ready for Chuck to narrate.
- **Repair** – `POST /board/repair` accepts `{actions, dry_run}` and runs `BoardRepairService`, emitting backup/log metadata without touching hardware when `dry_run=true`.
- **Firmware** – `POST /board/firmware/preview|apply` routes through `FirmwareManager` for sanctioned-path checks, metadata backups, and confirmation-gated apply stubs.
- **Teach Mode** – `POST /board/mapping/preview|recover` returns `MappingRecoveryResult`; `POST /board/mapping/apply` executes the preview → backup → write pipeline via `MappingRecoveryService.apply_mapping`.
- **Smoke Harness** – `bash scripts/pactotech_smoke.sh` exercises all endpoints (sanity/repair/firmware/mapping) so Greg can run an “am I sane?” test after any restart or refactor.

### Daily Summary – 2025-11-21

1. **HID/Repair/Firmware/Mapping cleanups** – Clarified docstrings and removed dead comments in the sanity scanner, repair service, firmware manager, and mapping recovery apply pipeline so future sessions know exactly what is live vs. stubbed.
2. **Controller/Gateway consistency** – Verified we only expose the intended board routes (sanity, repair, firmware preview/apply, mapping preview/recover/apply) and ensured everything routes through FastAPI with sanctioned headers.
3. **Smoke harness + docs** – Added `scripts/pactotech_smoke.sh`, README instructions, and a state capsule so Greg can run a one-command “Am I sane?” check and future Codex sessions understand the subsystem immediately.
