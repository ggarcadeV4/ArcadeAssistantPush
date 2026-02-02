# LaunchBox Plugin Restore Guide

This document freezes the LaunchBox plugin contract and the backend launch policy so Arcade Assistant always launches via LaunchBox (plugin‑first) and avoids direct emulator fallbacks by default.

## Plugin Contract

- Health: `GET http://127.0.0.1:9999/health`
  - Returns JSON with `plugin`, `version` (bump on each build).
- Search: `GET /search-game?title=...`
  - Returns an array of games (includes `id`/`GameId`, `title`, `platform`, `year` when available).
- Launch (primary): `POST /launch-game`
  - Body: `{ "GameId": "<uuid>" }`
  - Returns `{ success: boolean, message: string }`.
- Optional back‑compat alias: `POST /launch` with `{ "id": "<uuid>" }`.

## Backend Launch Policy (frozen)

- Plugin bridge first (via `/launch-game`).
- Fallbacks inside `GameLauncher`:
  - `detected_emulator` (via LaunchBox config) → `launchbox` (LaunchBox.exe UI).
  - `direct` (MAME) is disabled by default: gate behind `AA_ALLOW_DIRECT_EMULATOR=true` if ever needed.

## Environment

- `.env`:
  - `AA_ALLOW_DIRECT_EMULATOR=false` (default)
  - `FASTAPI_URL=http://localhost:8000`
  - `LAUNCHBOX_ROOT=D:\LaunchBox` (recommended, keeps backend browse/search consistent)

## Deployment Discipline

1. Build plugin in Release.
2. Copy updated DLL(s) into `LaunchBox/Plugins/ArcadeAssistantPlugin`.
3. Restart LaunchBox (ensure no stray `dotnet run` instances).
4. Verify `/health` shows the new `version`.

## Quick Verification (end‑to‑end)

1) Plugin endpoint
```
curl -s -X POST http://127.0.0.1:9999/launch-game \
  -H "Content-Type: application/json" \
  -d '{"GameId":"test-id"}'
```
Should return structured JSON (even if `success:false`).

2) Resolver (plugin‑first)
```
curl -s "http://localhost:8000/api/launchbox/resolve?title=Street%20Fighter%20II"
```
Returns top candidates with UUIDs.

3) Launch via backend
```
curl -s -X POST http://localhost:8000/api/launchbox/launch/<RESOLVED_UUID>
```
Returns `{ success:true, method_used:"plugin_bridge" }` for valid IDs.

## Notes

- The browser should never call the plugin directly; route via the gateway/backend.
- Keep all processes (LaunchBox, plugin, gateway, backend) at the same privilege level.
- Prefer `127.0.0.1` in backend calls or bind the plugin to both IPv4/IPv6.
- If the plugin is down, the backend returns a clear message; it will not fall back to direct emulators unless explicitly enabled.

