# CANONICAL_DATA_CONTRACT.md
**Timestamp:** 2025-12-31 (Supabase inventory snapshot)

## Canonical tables (Supabase public schema)
These tables exist in Supabase today and are canonical:
- `cabinet`
- `cabinet_heartbeat`
- `cabinet_telemetry`
- `cabinet_game_score`
- `command_queue`
- `escalations`
- `cabinet_mac_allowlist`
- `devices`
- `ai_usage`
- `game`
- `tournament`
- `issues`
- `coordination_log`

> Canonical tables are defined strictly by the Supabase inventory snapshot above.
> No other tables are canonical unless/ until they exist in Supabase.

## Legacy -> Canonical Crosswalk
| Basement legacy name | Canonical target | Notes |
| --- | --- | --- |
| `telemetry` | `cabinet_telemetry` | Write/read via adapter or Supabase shim if legacy name must remain. |
| `commands` | `command_queue` | Poll + ACK + COMPLETE must update `status`, timestamps, and `result` fields. |
| `scores` | `cabinet_game_score` | Insert score events here (game_id/player/score/achieved_at). |
| `devices` | `devices` and/or `cabinet` | `cabinet` is the fleet-level cabinet identity; `devices` exists for lower-level device registry. Do not duplicate semantics. |

## Canonical identifiers
- `cabinet.pk`: `cabinet.id` (uuid)
- `cabinet_id`: `cabinet.cabinet_id` (text)  stable external cabinet identifier used across related tables
- Foreign-key semantics: other tables primarily join using `cabinet_id` (text), not `cabinet.id`.

## Auth / claims (RLS-relevant)
- `tenant_id`  referenced in RLS policies as a JWT claim (treat as auth context unless verified as a physical column)
- `user_role`  referenced in RLS policies as a JWT claim / role gate

## DO NOT DRIFT rules
- Supabase is the single source of truth for canonical entities.
- Do NOT create parallel truth tables that duplicate canonical meanings.
- If legacy names remain in any client, they must map through:
  - a code adapter layer, OR
  - documented Supabase views/triggers (shim), OR
  - Fleet Manager backend proxy.
- Any schema expansion requires updating this contract first (or in the same change) so all clients stay aligned.
