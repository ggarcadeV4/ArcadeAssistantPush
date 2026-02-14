# Supabase Backend - Arcade Assistant Network

## Overview
This Supabase project serves as the cloud backend for the **Arcade Assistant** ecosystem, connecting:
- **Basement Cabinet** (downstairs dev machine)
- **Upstairs Fleet Console** (management UI)
- **Future Arcade Network** (multi-cabinet deployment)

**Project URL**: `https://zlkhsxacfyxsctqpvbsh.supabase.co`

---

## Table Schema (Canonical Names)

> **Important**: The codebase uses these exact table names. Schema was migrated on 2026-01-07 to align runtime code with database.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `cabinet` | Device registry (one row per cabinet) | `id`, `serial`, `status`, `last_seen` |
| `cabinet_heartbeat` | Heartbeat pings from cabinets | `cabinet_id`, `timestamp` |
| `cabinet_game_score` | High scores from games | `game_id`, `player`, `score`, `device_id` |
| `cabinet_telemetry` | AI usage and event logs | `device_id`, `level`, `message` |
| `command_queue` | Remote commands for cabinets | `device_id`, `type`, `payload`, `status` |
| `tournaments` | ScoreKeeper tournament state | `tournament_id`, `bracket_data`, `active` |
| `user_tendencies` | Player preference profiles | `user_id`, `preferences`, `favorites` |
| `led_configs` | LED Blinky patterns | `device_id`, `pattern`, `colors` |
| `led_maps` | Game-specific LED mappings | `device_id`, `game_id`, `button_map` |

---

## Edge Functions

| Function | Status | Purpose |
|----------|--------|---------|
| `gemini-proxy` | ✅ ACTIVE | Proxies AI requests to Google Gemini 2.0 Flash |
| `anthropic-proxy` | ✅ ACTIVE | Proxies AI requests to Claude (fallback) |
| `elevenlabs-proxy` | ✅ ACTIVE | Proxies TTS requests to ElevenLabs |
| `sign_url` | ✅ ACTIVE | Signs download URLs for updates |
| `register_device` | ⚠️ DEPRECATED | Returns 410 - use direct table insert |
| `send_command` | ⚠️ DEPRECATED | Returns 410 - use direct table insert |

---

## RLS Policies

All tables have Row Level Security enabled with these patterns:

- **anon role**: INSERT, SELECT, UPDATE (cabinets self-register and report)
- **authenticated role**: Full access (Fleet Console operators)
- **service_role**: Bypass RLS (backend services)

Cabinet isolation uses JWT claims:
```sql
device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
```

---

## Secrets (Edge Functions)

These must be set in Supabase Dashboard → Edge Functions → Secrets:

| Secret | Purpose |
|--------|---------|
| `GOOGLE_API_KEY` | Gemini 2.0 Flash API key |
| `ANTHROPIC_API_KEY` | Claude API key (fallback) |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS key |

---

## Migration History

| Date | Change |
|------|--------|
| 2026-01-07 | Added `game_title`, `source` columns to `cabinet_game_score` for High Score Pipeline |
| 2026-01-07 | Aligned table names: `devices`→`cabinet`, `scores`→`cabinet_game_score`, etc. |
| 2026-01-07 | Created `tournaments` table for ScoreKeeper persistence |
| 2026-01-01 | Fixed RLS policies for anon cabinet writes |
| 2025-12-30 | Deployed `gemini-proxy` with function calling support |

---

## Local Development

The backend connects to Supabase using env vars:
```
SUPABASE_URL=https://zlkhsxacfyxsctqpvbsh.supabase.co
SUPABASE_ANON_KEY=<public anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
```

Test connection:
```bash
curl "https://zlkhsxacfyxsctqpvbsh.supabase.co/rest/v1/cabinet?select=id&limit=1" \
  -H "apikey: $SUPABASE_ANON_KEY"
```

---

## Smoke Test

Run from cabinet to verify connectivity:
```bash
python cabinet_smoke_test.py
```

Expected output: 5/5 PASS (connection, registration, heartbeat, telemetry, command poll)

---

## For Future AI Agents

When working on this Supabase backend:

1. **Table names are canonical** - use `cabinet`, `cabinet_game_score`, etc. (not legacy `devices`, `scores`)
2. **RLS is strict** - anon can INSERT/UPDATE but cabinet_id must match JWT claim
3. **Edge Functions use secrets** - never hardcode API keys
4. **Migrations go in `supabase/migrations/`** - prefix with YYYYMMDD
5. **Test with smoke test** before deploying schema changes

---

## Related Files

- `supabase/schema.sql` - Original schema (may be outdated, check migrations)
- `supabase/migrations/` - Incremental schema changes
- `backend/services/supabase_client.py` - Python client wrapper
- `gateway/services/supabase_client.js` - Node.js client wrapper
- `cabinet_smoke_test.py` - Connectivity verification

---

## High Score Pipeline (2026-01-07)

> **FOR FLEET CONSOLE**: This section documents what the cabinet will be sending to `cabinet_game_score`.

### Data Contract

Cabinet pushes high scores to `cabinet_game_score` with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `cabinet_id` | TEXT | Cabinet serial (AA-XXXX) - **NOT** device_id |
| `game_id` | UUID | Deterministic UUID generated from game title |
| `game_title` | TEXT | Human-readable title (e.g., "Donkey Kong") |
| `player` | TEXT | Resolved profile name (via Sam initials mapping) |
| `score` | BIGINT | Integer score value |
| `source` | TEXT | `mame_hiscore` \| `retroachievements` \| `manual` |
| `achieved_at` | TIMESTAMPTZ | When score was achieved - **NOT** created_at |

> [!NOTE]
> FK constraints on `cabinet_id` and `game_id` were removed on 2026-01-08 to allow score inserts without pre-existing cabinet/game records.

### Score Sources

| Source | Description |
|--------|-------------|
| `mame_hiscore` | Parsed from MAME `.hi` files (automatic) |
| `retroachievements` | Pulled from RetroAchievements API (opt-in) |
| `manual` | Entered via ScoreKeeper Sam GUI |

### Fleet Console Display Recommendations

- **Per-cabinet leaderboards**: Filter by `device_id`
- **Cross-cabinet leaderboards**: Group by `game_id`, rank by `score`
- **Source badges**: Show 🕹️ (MAME), 🏆 (RA), ✏️ (Manual)
- **Player resolution**: `player` field is already resolved to profile name (not raw initials)

### Deduplication

Cabinet uses hash of `(game_id, player, score)` to avoid duplicate entries.
Fleet Console can rely on unique `id` column for record identity.

### Offline Behavior

When cabinet loses connectivity:
1. Scores spool to `state/outbox/scores.jsonl`
2. On reconnect, spooled scores batch-insert with original timestamps
3. `created_at` reflects when score was achieved (not when synced)

---

## ScoreKeeper Sam Events (2026-01-07)

> **FOR FLEET CONSOLE**: Tournament lifecycle events the cabinet will publish.

| Event | When | Payload |
|-------|------|---------|
| `TOURNAMENT_STARTED` | Bracket generated | `{tournament_id, name, player_count, mode}` |
| `TOURNAMENT_COMPLETED` | Final match finished | `{tournament_id, winner, total_matches}` |

These events publish to the internal event bus. If Fleet Console wants real-time tournament status, 
cabinet can optionally push to a `cabinet_events` table (not yet implemented).

