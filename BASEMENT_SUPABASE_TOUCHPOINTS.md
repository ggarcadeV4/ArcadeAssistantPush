# Basement Supabase Touchpoints

## Scope
- Runtime code in `backend/`, `gateway/`, `frontend/`, and `supabase/functions/`
- Utility scripts in `scripts/`, plus `check_db.py`, `install_supabase.sh`, and `install_supabase.ps1`
- Excludes `node_modules/`, `dist/`, backups/logs, `.bak` files, and docs/tests

## Supabase env vars (name -> references)
- `SUPABASE_URL`: `backend/main.py:21`, `backend/services/supabase_client.py:161`, `backend/services/gunner_config.py:90`, `backend/services/drive_a_ai_client.py:17`, `backend/routers/supabase_health.py:169`, `backend/services/dewey/trivia_scheduler.py:189`, `gateway/services/supabase_client.js:20`, `gateway/config/env.js:36`, `gateway/config/env.js:40`, `gateway/ws/audio.js:368`, `gateway/ws/audio.js:371`, `gateway/adapters/anthropic.js:28`, `gateway/adapters/anthropic.js:31`, `gateway/adapters/anthropic.js:119`, `gateway/adapters/anthropic.js:121`, `gateway/adapters/openai.js:27`, `gateway/adapters/openai.js:30`, `gateway/adapters/openai.js:155`, `gateway/adapters/openai.js:159`, `gateway/routes/tts.js:44`, `gateway/routes/tts.js:86`, `gateway/routes/tts.js:88`, `gateway/routes/launchboxAI.js:30`, `gateway/routes/launchboxAI.js:1048`, `gateway/routes/launchboxAI.js:1079`, `gateway/routes/launchboxAI.js:1102`, `supabase/functions/register_device/index.ts:33`, `supabase/functions/send_command/index.ts:36`, `supabase/functions/sign_url/index.ts:31`, `scripts/start_backend.py:90`, `scripts/migrate_a_drive.py:535`, `scripts/provision_and_verify.ps1:47`, `scripts/provision_and_verify.ps1:57`, `scripts/provision_and_verify.ps1:84`, `check_db.py:9`, `install_supabase.sh:19`, `install_supabase.ps1:16`
- `SUPABASE_ANON_KEY`: `backend/main.py:22`, `backend/services/supabase_client.py:162`, `backend/services/gunner_config.py:91`, `gateway/services/supabase_client.js:21`, `gateway/services/supabase_client.js:24`, `backend/routers/supabase_health.py:170`, `backend/routers/supabase_health.py:198`, `check_db.py:10`, `scripts/migrate_a_drive.py:536`, `scripts/provision_and_verify.ps1:49`, `install_supabase.sh:20`, `install_supabase.ps1:17`
- `SUPABASE_SERVICE_KEY`: `backend/main.py:23`, `backend/services/supabase_client.py:164`, `backend/services/drive_a_ai_client.py:18`, `backend/services/drive_a_ai_client.py:23`, `check_db.py:11`, `scripts/migrate_a_drive.py:537`, `scripts/provision_and_verify.ps1:48`, `scripts/provision_and_verify.ps1:57`, `scripts/provision_and_verify.ps1:86`, `scripts/provision_and_verify.ps1:87`
- `SUPABASE_SERVICE_ROLE_KEY`: `gateway/config/env.js:37`, `gateway/config/env.js:40`, `gateway/ws/audio.js:354`, `gateway/ws/audio.js:368`, `gateway/ws/audio.js:371`, `gateway/ws/audio.js:391`, `gateway/adapters/anthropic.js:31`, `gateway/adapters/anthropic.js:32`, `gateway/adapters/anthropic.js:59`, `gateway/adapters/anthropic.js:121`, `gateway/adapters/anthropic.js:122`, `gateway/adapters/anthropic.js:137`, `gateway/adapters/openai.js:30`, `gateway/adapters/openai.js:31`, `gateway/adapters/openai.js:63`, `gateway/adapters/openai.js:155`, `gateway/adapters/openai.js:156`, `gateway/adapters/openai.js:173`, `gateway/routes/tts.js:44`, `gateway/routes/tts.js:86`, `gateway/routes/tts.js:88`, `gateway/routes/tts.js:91`, `gateway/routes/launchboxAI.js:30`, `gateway/routes/launchboxAI.js:1048`, `gateway/routes/launchboxAI.js:1084`, `gateway/routes/launchboxAI.js:1102`, `backend/routers/supabase_health.py:176`, `backend/routers/supabase_health.py:198`, `supabase/functions/register_device/index.ts:34`, `supabase/functions/send_command/index.ts:37`, `supabase/functions/sign_url/index.ts:32`, `install_supabase.sh:21`, `install_supabase.ps1:18`
- `SUPABASE_KEY` (fallback): `backend/routers/supabase_health.py:174`
- `VITE_SUPABASE_URL`: `frontend/src/services/supabaseClient.js:3`
- `VITE_SUPABASE_ANON_KEY`: `frontend/src/services/supabaseClient.js:4`

## Supabase tables (with operations and references)
### Runtime tables
- `devices`
  - Operations: select, update, insert, upsert
  - References: `gateway/services/supabase_client.js:56`, `gateway/services/supabase_client.js:94`, `backend/services/supabase_client.py:260`, `backend/services/supabase_client.py:401`, `backend/services/supabase_client.py:425`, `backend/services/supabase_client.py:428`, `backend/services/supabase_client.py:432`, `supabase/functions/register_device/index.ts:62`, `supabase/functions/register_device/index.ts:80`, `supabase/functions/register_device/index.ts:99`, `supabase/functions/send_command/index.ts:95`, `scripts/provision_and_verify.ps1:91`, `scripts/provision_and_verify.ps1:96`, `check_db.py:36`
- `telemetry`
  - Operations: insert
  - References: `gateway/services/supabase_client.js:130`, `backend/services/supabase_client.py:311`, `backend/services/supabase_client.py:332`, `backend/services/supabase_client.py:611`, `supabase/functions/register_device/index.ts:121`, `supabase/functions/send_command/index.ts:146`
- `commands`
  - Operations: select, insert, update
  - References: `gateway/services/supabase_client.js:164`, `gateway/services/supabase_client.js:206`, `backend/services/supabase_client.py:460`, `backend/services/supabase_client.py:514`, `supabase/functions/send_command/index.ts:126`
- `scores`
  - Operations: insert
  - References: `gateway/services/supabase_client.js:239`, `backend/services/supabase_client.py:562`, `backend/services/supabase_client.py:625`
- `user_tendencies`
  - Operations: select, upsert
  - References: `gateway/services/supabase_client.js:275`, `gateway/services/supabase_client.js:308`
- `gun_profiles`
  - Operations: select, upsert, delete
  - References: `backend/services/gunner_config.py:161`, `backend/services/gunner_config.py:187`, `backend/services/gunner_config.py:220`, `backend/services/gunner_config.py:258`
- `device_heartbeat`
  - Operations: insert
  - References: `backend/services/supabase_client.py:389`
- `chat_history`
  - Operations: insert
  - References: `frontend/src/services/supabaseClient.js:28`

### Probe-only candidates (check_db.py)
- `device`
  - Operations: select (probe)
  - References: `check_db.py:36`
- `cabinet`
  - Operations: select (probe)
  - References: `check_db.py:36`
- `cabinets`
  - Operations: select (probe)
  - References: `check_db.py:36`
- `arcade_cabinets`
  - Operations: select (probe)
  - References: `check_db.py:36`
- `profiles`
  - Operations: select (probe)
  - References: `check_db.py:36`
- `users`
  - Operations: select (probe)
  - References: `check_db.py:36`

## Invoked Supabase Edge Functions
- `anthropic-proxy`: `backend/services/drive_a_ai_client.py:60`, `gateway/adapters/anthropic.js:28`, `gateway/adapters/anthropic.js:119`, `gateway/routes/launchboxAI.js:1079`
- `openai-proxy`: `backend/services/drive_a_ai_client.py:106`, `gateway/adapters/openai.js:27`, `gateway/adapters/openai.js:159`, `gateway/ws/audio.js:371`
- `elevenlabs-proxy`: `backend/services/drive_a_ai_client.py:154`, `gateway/routes/tts.js:88`

## Mismatch vs Prompt 1 Supabase inventory (missing tables)
- Prompt 1 inventory not available in the current context, so a missing-table diff cannot be computed yet.
- Provide the Prompt 1 inventory list to generate an explicit mismatch table.
