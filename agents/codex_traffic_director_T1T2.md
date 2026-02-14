# Codex Traffic Director — T1T2 (Scores + Proxy)

Goal
- Implement T1 (plugin scores bridge) + T2 (gateway proxy + CB) with tests and smokes passing.

Scope (only these files)
- `plugin/src/Bridge/HttpBridge.cs` — add handlers: `GET /health`, `GET /scores/by-game`, `GET /scores/leaderboard`, `POST /scores/submit`, `POST /events/launch-start`, `POST /events/launch-end`; write JSONL to `A:\LaunchBox\Logs\ArcadeAssistant\`.
- `gateway/routes/launchboxScores.js` — proxy `/api/launchbox/scores/*` to plugin with 1s timeout, 30s cache, circuit breaker.
- `gateway/server.js` — ensure route registration.
- Tests: `tests/gateway/launchboxScores.spec.js` (Jest), `tests/backend/test_launch_api.py` (pytest, launch guard + forced method).
- Docs: Update `docs/runbooks/launch-verify.md` with scores smoke.

Guardrails
- Source of truth: `AA_DRIVE_ROOT=A:\\`.
- Plugin loopback: `http://127.0.0.1:9999/` (include URLACL note).
- Header requirement: `x-panel: launchbox` for launch; DO NOT change launch order (plugin-first).
- No silent hard-fails: degrade + log; never block UI.
- Feature flags: `AA_ALLOW_DIRECT_MAME` defaults false (opt-in only).
- Small commits; include tests; run smoke script.

Acceptance
- Plugin online: `curl /health` 200; `curl /scores/leaderboard` <100ms.
- Gateway: returns fresh scores when plugin up; cached:true when plugin down; friendly 503 if no cache.
- JSONL writes are append-only under `A:\\LaunchBox\\Logs\\ArcadeAssistant\\`.
- All Jest tests green; `scripts/smoke_win.ps1` returns 0.

Notes
- Use `127.0.0.1` vs `localhost` to avoid IPv6/ACL quirks.
- Log request_id, panel header, and latency in the proxy.
- Keep diffs minimal; avoid touching unrelated code or launch order.
