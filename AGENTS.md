# Repository Guidelines

## Project Structure & Module Organization
- Backend in `backend/` (FastAPI), gateway in `gateway/` (Express), UI in `frontend/`.
- Shared JS/TS utilities in `src/`; scripts in `scripts/`; docs in `docs/`.
- Runtime data: `configs/`, `state/`, `backups/YYYYMMDD/`, `logs/`.
- Tests mirror code by area: `tests/backend/`, `tests/gateway/`, `tests/frontend/`.
- Colocate small helpers near use; larger domains under `backend/<area>/` or `frontend/src/<area>/`.

## Build, Test, and Development Commands
- Install all deps: `npm run install:all`.
- Dev stack (gateway+backend+frontend): `npm run dev` (Windows: `start-gui.bat`, WSL: `scripts/dev-wsl.sh`).
- Backend only: `node scripts/dev-backend.cjs`; Gateway only: `npm start`.
- Frontend build: `npm run build:frontend`.
- Smoke and health checks: `npm run smoke:stack` (or `smoke:stack:no-start`), `npm run test:health`.
- Tests: Node `npm test`; Python `pytest -q backend` or `pytest -q tests`.

## Coding Style & Naming Conventions
- Indentation: 2 spaces (JS/TS), 4 spaces (Python); max line length 100.
- Naming: PascalCase (classes/types), camelCase (functions/vars); Python files use `snake_case`, web assets use `kebab-case`.
- Formatters: Prettier (JS/TS) and Black (Python). Commit only formatted, lint‑clean code.

## Testing Guidelines
- Frameworks: Jest (gateway/frontend) and Pytest (backend). Prefer fast, isolated unit tests.
- Mirror structure; keep fixtures near tests. No network or absolute OS paths.
- Cover dry‑run diffs, backup path creation, rollback, and invalid‑key rejections.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `safe-ops:`, `docs:`, `refactor:`.
- Scope PRs narrowly; keep changes small and self‑contained.
- PRs must include description, linked issues, verification steps; screenshots for UI changes. If config writes occur, include the API‑returned `backup_path`.

## Security & Configuration Tips
- Never commit secrets. Use `.env`; keep `.env.example` updated.
- Validate `AA_DRIVE_ROOT` and `/.aa/manifest.json`. Avoid absolute/OS paths; resolve via drive root + manifest.

## Agent‑Specific Instructions
- Do not edit built frontend artifacts (Builder.io exports are read‑only).
- All writes flow via Node gateway → FastAPI with `x-scope` headers; preview, auto‑backup, and append audit to `/logs/changes.jsonl`.
- Only write under sanctioned paths: `/configs`, `/state`, `/backups/YYYYMMDD`, `/logs`, `/emulators/*` provisioned in `/.aa/manifest.json`.
- Enforce schemas: reject unknown keys, apply minimal patches, and ensure rollback via `/config/restore` using the returned `backup_path`.

