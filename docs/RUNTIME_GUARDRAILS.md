Runtime Guardrails & Pathing
============================

- `.aa/manifest.json` is required for writes. It must include a non-empty `sanctioned_paths` array; empty means every write target is rejected by `is_allowed_file`.
- `drive_root` comes from `AA_DRIVE_ROOT` (see `backend/startup_manager.py`). If it is missing or invalid, the app sets `writes_allowed = false`, surfaces a blocking message, and treats paths as non-writable.
- When `AA_DRIVE_ROOT` is unset/invalid, write endpoints return HTTP 503 with the explicit block reason; this is intentional to prevent silent fallback to the repo directory.
- Resolved paths for emulator configs are derived from `drive_root` plus known defaults in `backend/services/controller_cascade.py` (`DEFAULT_CONFIG_PATHS` and `_default_config_hint_for_emulator`). These are displayed via `GET /api/local/controller/effective-paths`:
  - Shows `drive_root`, `sanctioned_paths`, and per-emulator `resolved_path`.
  - `allowed: false` means the resolved path is outside `sanctioned_paths`, so writes will be blocked.
  - `writes_allowed` reports whether startup marked the instance writable (true only when `AA_DRIVE_ROOT` is valid).
- Autoconfig status is exposed at `GET /api/controllers/autoconfig/status`:
  - It is disabled by default; enable with `CONTROLLER_AUTOCONFIG_ENABLED=true`.
  - When disabled, the endpoint returns `enabled: false` with the reason; when enabled it also reports path validation and detected profiles/devices.
- Mapping apply (`POST /api/local/controller/mapping/apply`) can fail for:
  - Missing or invalid `x-scope: config`.
  - `writes_allowed = false` (invalid `AA_DRIVE_ROOT`).
  - Target file outside `sanctioned_paths`.
  - Validation errors on the mapping payload.
  Errors return explicit HTTP 4xx/5xx messages; no silent failures.
- Cascade apply (`POST /api/local/controller/cascade/apply`) emits audit log entries named `cascade_component_result` (see `backend/services/controller_cascade.py`), one per emulator component, capturing `emulator`, `status`, `config_path`, and `mapping_keys` to verify what was written. The queueing itself logs `controller_cascade_queued`.

Key references
- Guardrail checks and drive root handling: `backend/startup_manager.py`
- Path allowance check: `backend/services/policies.py::is_allowed_file`
- Effective paths endpoint: `backend/routers/controller.py::effective_paths`
- Cascade/emulator targets: `backend/services/controller_cascade.py`
- Autoconfig status endpoint and flag: `backend/routers/autoconfig.py` (`CONTROLLER_AUTOCONFIG_ENABLED`)
- Mapping apply flow and failures: `backend/routers/controller.py::apply_controller_mapping`
