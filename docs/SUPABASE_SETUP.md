# Supabase Setup (Drive A Cabinets)

This guide configures Arcade Assistant cabinets (Drive A image) to send live data to Supabase using Option A (service_role on-device).

## 1) Collect Supabase API Credentials
From Supabase Dashboard → Settings → API:
- SUPABASE_URL (e.g. https://YOUR-PROJECT.supabase.co)
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_KEY (service_role)

Security model: Option A (fastest to ship). RLS still applies; service role bypasses RLS where required (e.g., device heartbeats) and simplifies deployment.

## 2) Prepare .env per Cabinet
- Copy `.env.template` to `.env` in repo root (A:\\Arcade Assistant Local)
- Fill the required values:
  - SUPABASE_URL
  - SUPABASE_ANON_KEY
  - SUPABASE_SERVICE_KEY
  - AA_DEVICE_ID (unique UUID per cabinet)

Recommended: keep your master values for the 3 Supabase keys, but generate a new AA_DEVICE_ID on each cabinet.

PowerShell (generate UUID):
```
[guid]::NewGuid().ToString()
```

## 3) Persist Device Identity to Manifest
Create `/.aa/cabinet_manifest.json` under Drive A so services can read the device id consistently.

PowerShell:
```
$root = 'A:\\'  # adjust if Drive A is mapped differently
$manifestDir = Join-Path $root '.aa'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
$manifestPath = Join-Path $manifestDir 'cabinet_manifest.json'
$deviceId = $env:AA_DEVICE_ID  # set in .env or paste your UUID
@{
  device_id = $deviceId
  name = "Arcade Cabinet"
  version = "1.0"
} | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8
```

## 4) Supabase Tables
Ensure these tables exist (see `docs/SUPABASE_GUARDRAILS.md` for schema):
- public.devices
- public.telemetry
- public.scores
- public.tournaments (used by ScoreKeeper)

Pre-create a devices row for each cabinet, using the same UUID as `AA_DEVICE_ID`:
```sql
insert into public.devices (id, serial, status, tags)
values ('<AA_DEVICE_ID>', '<your-serial>', 'online', '{}'::jsonb)
on conflict (id) do nothing;
```

## 5) Launch Stack (Gateway + Backend)
Use the cabinet-safe launcher (added in this repo):
- `start-aa-dev.bat:1` (opens http://localhost:8787/)

This starts:
- FastAPI backend: http://localhost:8000
- Gateway: http://localhost:8787
- Opens browser to the gateway UI

## 6) Verify Connectivity
- Backend Supabase config:
  - GET `http://127.0.0.1:8000/api/supabase/status` → `configured: true`
- Backend Supabase health:
  - GET `http://127.0.0.1:8000/api/supabase/health` → `{ connected: true, latency_ms, ... }` or 503 with error
- Gateway health:
  - GET `http://localhost:8787/healthz` → `{ status: "ok" }`

## 7) Data Flows
Once configured, cabinets will send:
- Heartbeats: device `last_seen` every 5 minutes
- Telemetry: launcher errors, voice/STT issues, LED apply status
- Scores: manual submit + autosubmit mirrored to Supabase `public.scores` (meta included)
- Tournaments: created/updated via ScoreKeeper services

Note: Ensure the device row exists for heartbeats to update `last_seen`.

## 8) Per‑Cabinet Checklist (Cloning Drive A)
1. Copy Drive A image to the new cabinet
2. Create `.env` from `.env.template` and fill:
   - SUPABASE_URL / ANON / SERVICE
   - Generate a new AA_DEVICE_ID (UUID)
3. Write AA_DEVICE_ID to `/.aa/cabinet_manifest.json`
4. Pre-create the `devices` row in Supabase with that UUID
5. Launch `start-aa-dev.bat`
6. Verify endpoints (status + health) and perform a quick score/telemetry test

## 9) Security Notes
- Keep `.env` off source control and out of support bundles
- Service role key is stored locally (Option A). Physical security and RLS still protect data. Consider rotating keys periodically.
- Device JWTs (Option B) can be adopted later without changing cabinet UI/UX if you add a minting endpoint.

---
If you need, we can provide a small provisioning script to generate AA_DEVICE_ID, create the manifest, pre-create the device in Supabase, and validate health in one pass.

