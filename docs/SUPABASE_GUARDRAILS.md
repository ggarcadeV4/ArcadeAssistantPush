# Supabase Integration Guardrails – Arcade Assistant

This document defines the Supabase schema, security, and usage rules for the Arcade Assistant.
All AI agents (Claude Code, ChatGPT) and human developers **must follow this spec** when writing backend logic.

---

## 🎯 Purpose
- Provide a cloud backbone for **licensing, telemetry, commands, and updates**.
- Keep **local-first** for configuration edits; use cloud for coordination, sync, and licensing.
- Ensure consistent structure across all agents and code.

---

## 📂 Tables & Schema

### Complete SQL Schema

Run this in your Supabase SQL Editor to create all tables, indexes, RLS policies, and triggers:

```sql
-- Enable pgcrypto for UUIDs if not already enabled
create extension if not exists "pgcrypto";

-- =============================
-- Tables
-- =============================

create table if not exists public.devices (
  id         uuid primary key default gen_random_uuid(),
  serial     text unique not null,
  owner_id   uuid not null,                 -- points to auth.users.id or your own UUID system
  status     text default 'online',         -- online | offline | paused | revoked
  version    text,
  last_seen  timestamptz default now(),
  tags       jsonb default '{}'::jsonb,
  inserted_at timestamptz default now(),
  updated_at  timestamptz default now()
);

create index if not exists idx_devices_owner on public.devices(owner_id);
create index if not exists idx_devices_last_seen on public.devices(last_seen);

create table if not exists public.commands (
  id          uuid primary key default gen_random_uuid(),
  device_id   uuid not null references public.devices(id) on delete cascade,
  type        text not null,                -- APPLY_PATCH | RUN_DIAG | REFRESH_CONFIG | MESSAGE
  payload     jsonb not null,               -- arbitrary params, URLs, checksums, etc
  status      text default 'NEW',           -- NEW | RUNNING | DONE | ERROR
  created_at  timestamptz default now(),
  executed_at timestamptz,
  result      jsonb
);

create index if not exists idx_commands_device_status on public.commands(device_id, status);
create index if not exists idx_commands_created on public.commands(created_at);

create table if not exists public.telemetry (
  id         bigserial primary key,
  device_id  uuid not null references public.devices(id) on delete cascade,
  level      text,                          -- INFO | WARN | ERROR
  code       text,
  message    text,
  created_at timestamptz default now()
);

create index if not exists idx_telemetry_device_time on public.telemetry(device_id, created_at desc);

-- Optional: tournament scores
create table if not exists public.scores (
  id         bigserial primary key,
  device_id  uuid not null references public.devices(id) on delete cascade,
  game_id    text not null,
  player     text not null,
  score      bigint not null,
  meta       jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_scores_game on public.scores(game_id, score desc);

-- =============================
-- Row Level Security
-- =============================
alter table public.devices   enable row level security;
alter table public.commands  enable row level security;
alter table public.telemetry enable row level security;
alter table public.scores    enable row level security;

-- Device isolation: JWT claim 'device_id' must match devices.id
-- Set this when minting device tokens via Edge Function

-- DEVICES: read/update own row
drop policy if exists p_devices_device_access on public.devices;
create policy p_devices_device_access
on public.devices
for select using (id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id');

drop policy if exists p_devices_device_update_self on public.devices;
create policy p_devices_device_update_self
on public.devices
for update using (id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id');

-- Admin bypass (service_role or is_admin=true claim)
drop policy if exists p_devices_admin on public.devices;
create policy p_devices_admin
on public.devices
for all
using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- COMMANDS: devices read/update own commands
drop policy if exists p_commands_device_select on public.commands;
create policy p_commands_device_select
on public.commands
for select using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_commands_device_update_result on public.commands;
create policy p_commands_device_update_result
on public.commands
for update using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_commands_admin on public.commands;
create policy p_commands_admin
on public.commands
for all using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- TELEMETRY: devices insert/read own logs only
drop policy if exists p_telemetry_insert_device on public.telemetry;
create policy p_telemetry_insert_device
on public.telemetry
for insert
to public
with check (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_telemetry_select_self on public.telemetry;
create policy p_telemetry_select_self
on public.telemetry
for select using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_telemetry_admin on public.telemetry;
create policy p_telemetry_admin
on public.telemetry
for all using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- SCORES: devices can insert; everyone can read (public leaderboard)
drop policy if exists p_scores_insert_device on public.scores;
create policy p_scores_insert_device
on public.scores
for insert with check (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_scores_select_public on public.scores;
create policy p_scores_select_public
on public.scores
for select using (true);

-- =============================
-- Triggers to keep updated_at fresh
-- =============================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_devices_updated on public.devices;
create trigger trg_devices_updated
before update on public.devices
for each row execute procedure public.touch_updated_at();
```

---

## 🗄️ Storage Buckets

Create these buckets in Supabase → Storage (both should be **private**, not public):
- `updates` → patch bundles organized by semver (e.g., `updates/1.2.3/patch.zip`)
- `assets` → cabinet assets (marquee art, screenshots, etc.)

Files are served via short-lived signed URLs from Edge Functions.

---

## ⚙️ Edge Functions

### Setup Instructions
1. Install Supabase CLI: `npm install -g supabase`
2. Create functions: `supabase functions new <function-name>`
3. Deploy: `supabase functions deploy <function-name>`
4. Set secrets: `supabase secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...`

### 1. `register_device.ts`

**Purpose:** First-boot registration. Creates (or finds) device row by serial, returns device_id.

**Location:** `supabase/functions/register_device/index.ts`

```typescript
// register_device.ts
// Deno runtime (Supabase Functions)
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

type RegisterBody = {
  serial: string;
  owner_id: string;
  version?: string;
  tags?: Record<string, unknown>
};

Deno.serve(async (req) => {
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const { createClient } = await import("npm:@supabase/supabase-js@2");
    const admin = createClient(supabaseUrl, supabaseServiceKey, {
      auth: { persistSession: false }
    });

    const body = (await req.json()) as RegisterBody;
    if (!body?.serial || !body?.owner_id) {
      return new Response(
        JSON.stringify({ error: "serial and owner_id required" }),
        { status: 400 }
      );
    }

    // Upsert device by serial
    const { data: existing, error: selErr } = await admin
      .from("devices")
      .select("id")
      .eq("serial", body.serial)
      .maybeSingle();

    let deviceId = existing?.id;
    if (!deviceId) {
      const { data: ins, error: insErr } = await admin
        .from("devices")
        .insert({
          serial: body.serial,
          owner_id: body.owner_id,
          version: body.version ?? null,
          tags: body.tags ?? {},
        })
        .select("id")
        .single();
      if (insErr) throw insErr;
      deviceId = ins.id;
    }

    return new Response(
      JSON.stringify({ device_id: deviceId }),
      { status: 200 }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: String(e) }),
      { status: 500 }
    );
  }
});
```

**Note:** For production, consider creating a GoTrue user per device and embedding `device_id` in JWT `app_metadata` for proper authentication flow.

### 2. `send_command.ts`

**Purpose:** Admin-only. Enqueues commands for one or many devices.

**Location:** `supabase/functions/send_command/index.ts`

```typescript
// send_command.ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

type Cmd = {
  device_id: string;
  type: string;  // APPLY_PATCH | RUN_DIAG | REFRESH_CONFIG | MESSAGE
  payload: Record<string, unknown>;
};

type Body = { commands: Cmd[] };

Deno.serve(async (req) => {
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const { createClient } = await import("npm:@supabase/supabase-js@2");
    const admin = createClient(supabaseUrl, supabaseServiceKey, {
      auth: { persistSession: false }
    });

    const body = (await req.json()) as Body;
    if (!body?.commands?.length) {
      return new Response(
        JSON.stringify({ error: "commands array required" }),
        { status: 400 }
      );
    }

    const { error } = await admin.from("commands").insert(
      body.commands.map((c) => ({
        device_id: c.device_id,
        type: c.type,
        payload: c.payload,
        status: "NEW",
      }))
    );
    if (error) throw error;

    return new Response(
      JSON.stringify({ ok: true }),
      { status: 200 }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: String(e) }),
      { status: 500 }
    );
  }
});
```

### 3. `sign_url.ts`

**Purpose:** Returns temporary signed URL to files in `updates/` or `assets/` buckets.

**Location:** `supabase/functions/sign_url/index.ts`

```typescript
// sign_url.ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

type Body = {
  bucket: "updates" | "assets";
  path: string;
  expiresIn?: number
};

Deno.serve(async (req) => {
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const { createClient } = await import("npm:@supabase/supabase-js@2");
    const admin = createClient(supabaseUrl, supabaseServiceKey, {
      auth: { persistSession: false }
    });

    const { bucket, path, expiresIn = 60 * 10 } = (await req.json()) as Body;
    if (!bucket || !path) {
      return new Response(
        JSON.stringify({ error: "bucket and path required" }),
        { status: 400 }
      );
    }

    const { data, error } = await admin.storage
      .from(bucket)
      .createSignedUrl(path, expiresIn);
    if (error) throw error;

    return new Response(
      JSON.stringify({ url: data.signedUrl }),
      { status: 200 }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: String(e) }),
      { status: 500 }
    );
  }
});
```

**Required secrets for all functions:**
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

---

## 🔒 Row-Level Security (RLS)

**Important:** All RLS policies are included in the SQL schema above. Key points:
- Devices can read only their own row in `devices`.
- Devices can insert `telemetry` but cannot read others' data.
- Devices can see only `commands` where `device_id = self`.
- Admin role bypass via `service_role` or `is_admin=true` JWT claim.

---

## 🖥️ Client (Cabinet) Responsibilities
1. **Register on first boot** → stores JWT locally.
2. **Heartbeat**: every 5 min update `last_seen`.
3. **Telemetry**: batch and insert logs (not chatty).
4. **Subscribe to commands** (NEW only).
5. **On command**: validate payload → apply locally (safe-write + rollback) → update status + result.

---

## 🛠️ Admin Console Responsibilities
- Upload update bundles to `updates/`.
- Insert commands via `send_command.ts`.
- View telemetry dashboards.
- Manage licensing (activate, revoke, pause devices).

---

## 🧭 Client Implementation Examples

### Electron Preload: `preload/supabase.ts`

Minimal Supabase client with command subscription pattern:

```typescript
// preload/supabase.ts
import { contextBridge } from "electron";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY!;

let sb: SupabaseClient;

function init() {
  sb = createClient(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: true }
  });
}

async function heartbeat(device_id: string) {
  await sb
    .from("devices")
    .update({ last_seen: new Date().toISOString() })
    .eq("id", device_id);
}

async function fetchNewCommands(device_id: string) {
  return sb
    .from("commands")
    .select("*")
    .eq("device_id", device_id)
    .eq("status", "NEW")
    .order("created_at", { ascending: true });
}

async function setCommandStatus(
  id: string,
  status: "RUNNING" | "DONE" | "ERROR",
  result?: unknown
) {
  return sb
    .from("commands")
    .update({
      status,
      executed_at: new Date().toISOString(),
      result
    })
    .eq("id", id);
}

contextBridge.exposeInMainWorld("supabaseAPI", {
  init,
  heartbeat,
  fetchNewCommands,
  setCommandStatus
});
```

**Important:** UI panels should NOT call this directly. Route through your agent layer to maintain guardrails.

---

### Python Agent: `services/supabase_client.py`

Minimal client for telemetry and command status updates:

```python
# services/supabase_client.py
from datetime import datetime
from supabase import create_client, Client  # pip install supabase
import os
import typing as t

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

_sb: Client | None = None

def sb() -> Client:
    global _sb
    if _sb is None:
        _sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _sb

def send_telemetry(device_id: str, level: str, code: str, message: str):
    payload = {
        "device_id": device_id,
        "level": level,
        "code": code,
        "message": message,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    sb().table("telemetry").insert(payload).execute()

def set_command_status(command_id: str, status: str, result: dict | None = None):
    payload = {
        "status": status,
        "executed_at": datetime.utcnow().isoformat() + "Z"
    }
    if result is not None:
        payload["result"] = result
    sb().table("commands").update(payload).eq("id", command_id).execute()
```

---

## 🔧 Environment Variables

### Required for Arcade Assistant Application

Set these in your Electron build and local dev environment:

```ini
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-public-key

# SERVICE ROLE KEY should NEVER be in Electron or Python agent
# Only in Edge Functions!
```

### Required for Edge Functions

Set via Supabase CLI:

```bash
supabase secrets set SUPABASE_URL=https://your-project.supabase.co
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

---

## ✅ Quick Test Checklist (10 minutes)

1. **Run SQL** in Supabase SQL Editor
2. **Create buckets**: `updates`, `assets` (both private)
3. **Deploy functions**: `register_device`, `send_command`, `sign_url` (add secrets)
4. **Test registration**: Call `register_device` with `{ serial, owner_id }` → note `device_id`
5. **Test heartbeat**: In app, set `device_id` and call `heartbeat(device_id)`
6. **Insert command**: Manually insert row in `commands` table (status='NEW')
7. **Fetch commands**: From Electron preload/agent, call `fetchNewCommands(device_id)`
8. **Update status**: Call `setCommandStatus` to mark command as DONE
9. **Verify RLS**: Try to read another device's commands (should be blocked)
10. **Send telemetry**: Insert test log, verify it appears in Supabase dashboard

---

## 🚨 Security Rules

- Never embed service role keys in clients.
- Only Edge Functions hold service role keys.
- Clients use per-device JWTs with limited scope.
- Signed URLs expire; must be reissued per session.

---

## 🧭 Style & Implementation Rules

All Supabase client code lives under:
- `services/supabase_client.py` (Python agent)
- `preload/supabase.js` (Electron preload)

**Panels must not call Supabase directly.**
They invoke agent functions which route through `supabase_client`.

---

## 📝 Summary

- Supabase is used for coordination, not core arcade logic.
- All config edits, file repairs, and gameplay remain local-first.
- Supabase ensures licensing, updates, and sync scale reliably across fleets.
