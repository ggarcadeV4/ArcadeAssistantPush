# Supabase Fleet Manager Readiness

Scope & method. Read-only audit of Supabase Fleet Manager integration for Golden Drive migration.
Findings use the repo's Supabase schema and shipped platform references. When no project evidence
exists, the item is marked NOT IMPLEMENTED or NOT EVIDENCED and treated as optional by default.

Evidence IDs
- E1: supabase/schema.sql (tables, RLS, views).
- E2: supabase/functions/register_device/index.ts (device bootstrap).
- E3: supabase/functions/send_command/index.ts (command queue enqueue).
- E4: supabase/functions/sign_url/index.ts (signed storage URLs).
- E5: backend/services/supabase_client.py (heartbeat, telemetry, commands client).
- E6: backend/app.py (AA_DEVICE_ID generation, manifest write, heartbeat loop, auto-insert device).
- E7: backend/routers/supabase_device.py (queries cabinet table not in E1).
- P2-P5: Supabase platform behavior references (error/auth edges, Realtime limits, auth/RLS
  overview, repo/DB best practices) provided in prompt for background only.

## SECTION 1  Supabase's role in Arcade Assistant (Q1)

Primary role is fleet-style device management plus optional gameplay data. Schema covers devices,
command queue, telemetry, scores, user tendencies, and LED patterns. Backend client polls for
commands and pushes telemetry/heartbeats; edge functions handle registration, command enqueue, and
signed URLs. No schema evidence of AI usage or tournaments beyond scores.

| Use case | Status | Golden Drive | Evidence |
| --- | --- | --- | --- |
| Device registry | IMPLEMENTED (devices; register_device) | Required | E1,E2,E6 |
| Heartbeats | PARTIAL (last_seen; client writes missing device_heartbeat) | Required | E1,E5,E6 |
| Command queue | IMPLEMENTED (commands; send_command) | Required | E1,E3,E5 |
| Telemetry | IMPLEMENTED; client expects payload/tenant_id not in schema | Required | E1,E2,E5 |
| Scores/leaderboard | IMPLEMENTED | Optional | E1,E5 |
| User tendencies | SCHEMA ONLY (no code references) | Optional | E1 |
| LED configs/maps | SCHEMA ONLY (no code references) | Optional | E1 |
| Storage signed URLs | IMPLEMENTED (sign_url) | Optional | E4 |
| Tournaments | NOT IMPLEMENTED (no table) | Optional | E1 |
| AI usage tracking | NOT IMPLEMENTED (no table) | Optional | E1 |
| Device status API | NOT IMPLEMENTED (route queries missing cabinet table) | Risk | E7 |

Notes
- RLS is enabled for all tables in E1 with device-scoped policies and admin bypass via
  `role=service_role` or `is_admin=true`.
- Scores are world-readable via `p_scores_select_public`. Restrict if scores are sensitive.
- Command fetch is polling-based; no evidence of Realtime subscriptions.

## SECTION 2  Source of cabinet identity (Q2)

- Where device_id originates: Backend generates `AA_DEVICE_ID` locally from env/manifest or UUID on
  first boot, writes it to `.aa/device_id.txt` and `.aa/cabinet_manifest.json`, and sets env for
  reuse (E6). Edge function `register_device` upserts Supabase `devices` by serial+owner (E2).
- Supabase override: Backend best-effort inserts/updates `devices` using service role if configured,
  but local `AA_DEVICE_ID` remains the seed; no Supabase-driven override path is present (E6).
- Unreachable Supabase: Heartbeat/auto-insert is wrapped in try/except; failures warn and continue
  (E6). Supabase client calls return errors/False; startup does not depend on Supabase reads.
- Verdict: Local (Golden Drive) is the authority for cabinet identity; Supabase holds a mirrored
  record when configured.

## SECTION 3  Schema & data guarantees (Q3-Q5)

Tables defined (E1); write frequency not evidenced:
- `devices` — PK `id` uuid; unique `serial`; cols owner_id, status, version, last_seen, tags.
- `commands` — PK `id` uuid; FK `device_id`→devices; fields type, payload, status, result, timestamps.
- `telemetry` — PK `id` bigserial; FK `device_id`→devices; level, code, message, created_at.
- `scores` — PK `id` bigserial; FK `device_id`→devices; game_id, player, score, meta, created_at.
- `user_tendencies` — PK `id` uuid; FK `device_id`→devices; prefs/history/favorites jsonb.
- `led_configs` — PK `id` uuid; FK `device_id`→devices; pattern/colors/speed/brightness/is_active.
- `led_maps` — PK `id` uuid; FK `device_id`→devices; game_id, button_map.
- Views: `active_devices`, `recent_telemetry`, `leaderboard`.
- No tournament, gun_profiles, rating_history, voice_commands, or device_heartbeat tables in E1.

Golden Drive required vs optional (evidence shows no boot-time Supabase dependency):
- Required to ship base drive: None (local boot proceeds without Supabase).
- Required for Fleet Manager features: devices, commands, telemetry, scores (leaderboard), plus RLS.
- Optional/deferred: user_tendencies, led_configs/maps, future tournaments/AI tracking.

Schema gaps/TODOs:
- Missing `device_heartbeat` table while client writes to it (E5); add table or remove write.
- Telemetry payload/tenant_id fields used in client but absent in schema (E5 vs E1); reconcile.
- Supabase device route queries `cabinet` table/columns not present (E7 vs E1); point to `devices`
  or add a view/table.
- Tables referenced elsewhere (gun_profiles, tournaments, rating_history, voice_commands) are absent
  (E5), so those flows cannot sync to Supabase.
- Ops: no retention/TTL for telemetry/commands; no backpressure/redrive; no Realtime subscriptions.

## SECTION 4  Fleet Manager data flow (Q6-Q8)

- Expected from cabinet: heartbeats (`update_device_heartbeat` throttled to 5m, best-effort insert
  to devices and non-existent device_heartbeat), telemetry (`send_telemetry` with code/message),
  scores (`insert_score`), command polling (`fetch_new_commands` + `update_command_status`) (E5).
- Error handling and retries: supabase_client wraps calls in try/except, returns bool/None, and uses
  `retry_on_failure` with exponential backoff for heartbeats/commands (E5).
- Buffering/failure handling: telemetry/scores spool to `state/outbox` jsonl when inserts fail; flush
  retried on heartbeat loop; commands are not spooled (E5, E6).
- Authority today: Supabase is observational; no code shows remote commands being enforced as the
  source of truth for local state. Command queue exists but execution path is not evidenced.
- Minimum viable for Golden Drive: treat Supabase as optional/best-effort. If enabling Fleet Manager,
  deploy E1 schema with RLS, configure service/anon keys, run edge functions for registration and
  command enqueue, and ensure device tokens carry `device_id` or use service role for server calls.

## SECTION 5  Offline, degraded, and silent-failure modes (Q9-Q11)

- Boot without Supabase: supported; identity is local and heartbeat loop failures are non-fatal (E6).
- Write failures: telemetry/scores spool locally; heartbeats return False; command fetch returns
  None on errors (E5).
- No mandatory Supabase reads at startup; Supabase unavailability should not block Golden Drive.
- Local queueing when offline (Q10): telemetry and scores are buffered to `state/outbox/*.jsonl`
  and flushed later (E5, E6). Commands and heartbeats are not queued.
- Supabase-dependent silent failure risks (Q11): RLS requires a device_id claim; missing claims
  yield empty result sets. Realtime is not configured; subscriptions would no-op. Command execution
  relies on polling; if the executor is absent, commands pile up silently. Edge functions carry
  platform CPU/runtime limits (P2-P5); heavy use without backoff could be flaky.

## SECTION 6  Security & boundaries (Q12-Q13)

- Credentials needed on cabinet/server: SUPABASE_URL and SUPABASE_ANON_KEY for client calls; optional
  SUPABASE_SERVICE_KEY for admin/device auto-insert/heartbeats; edge functions need
  SUPABASE_SERVICE_ROLE_KEY (E2, E3, E4, E5, E6).
- RLS: Enabled on all E1 tables with device-scoped policies; scores are public read. Ensure tokens
  carry `device_id`; tighten if broader data added.

## SECTION 7  Migration readiness verdict (Q14-Q17)

- Must-complete before migration: confirm identity authority is local (AA_DEVICE_ID) and that cabinet
  boots with Supabase offline; keep Supabase calls best-effort with error handling (E5, E6).
- Can defer: Fleet Manager dashboards, Realtime, remote commands enforcement, leaderboards,
  telemetry pipelines, extra Edge Functions.
- Top risks (ranked): identity ambiguity if future imports assume DB authority; security exposure if
  RLS is misconfigured or keys leaked; silent telemetry loss if outbox unavailable; expectations
  mismatch for Realtime; scale headwinds (indexes/retention); edge-function limits if expanded.
- Final verdict: GO WITH LIMITATIONS. Supabase is optional for boot; identity is local; reconcile
  schema/client drift before turning on Fleet features at scale.

## Recommended next steps

1) Reconcile schema vs clients: add `device_heartbeat` or drop its insert; add telemetry payload and
   tenant_id columns or trim client payload; fix supabase_device router to read `devices`.
2) Clarify auth: document device token minting (`device_id` claim) or server-side service-role use
   for commands/registration; lock down edge function CORS.
3) Validate fleet smoke tests: register_device, auto-insert via service role, heartbeat throttling,
   telemetry with payload, command enqueue/fetch/update, score insert.
4) Add ops guardrails: retention/TTL on telemetry/commands, decide on Realtime vs polling for
   commands, and create missing tables if cloud sync is expected (gun profiles, tournaments, etc.).
