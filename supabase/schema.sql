-- Arcade Assistant - Complete Supabase Schema
-- Run this in your Supabase SQL Editor to create all tables, indexes, RLS policies, and triggers
-- Updated: 2025-10-27

-- Enable pgcrypto for UUIDs if not already enabled
create extension if not exists "pgcrypto";

-- =============================
-- Tables
-- =============================

-- Devices table: One row per licensed cabinet
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
create index if not exists idx_devices_status on public.devices(status);

-- Commands table: Command queue for remote actions
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

-- Telemetry table: Logs sent from cabinets
create table if not exists public.telemetry (
  id         bigserial primary key,
  device_id  uuid not null references public.devices(id) on delete cascade,
  level      text,                          -- INFO | WARN | ERROR
  code       text,
  message    text,
  created_at timestamptz default now()
);

create index if not exists idx_telemetry_device_time on public.telemetry(device_id, created_at desc);
create index if not exists idx_telemetry_level on public.telemetry(level);

-- Scores table: Tournament and leaderboard data
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
create index if not exists idx_scores_device on public.scores(device_id);
create index if not exists idx_scores_player on public.scores(player);

-- User tendencies table: Player preferences and behavior patterns
create table if not exists public.user_tendencies (
  id         uuid primary key default gen_random_uuid(),
  user_id    text not null,                 -- guest | dad | mom | tim | sarah | custom
  device_id  uuid references public.devices(id) on delete cascade,
  preferences jsonb default '{}'::jsonb,    -- genres, franchises, keywords
  play_history jsonb default '[]'::jsonb,   -- recent games played
  favorites  jsonb default '[]'::jsonb,     -- favorite game IDs
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_user_tendencies_user on public.user_tendencies(user_id);
create index if not exists idx_user_tendencies_device on public.user_tendencies(device_id);

-- LED configurations table: LED Blinky patterns and configurations
create table if not exists public.led_configs (
  id         uuid primary key default gen_random_uuid(),
  device_id  uuid not null references public.devices(id) on delete cascade,
  name       text not null,
  pattern    text not null,                 -- solid | pulse | chase | rainbow | etc
  colors     jsonb not null,                -- array of color values
  speed      integer default 5,
  brightness integer default 255,
  is_active  boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_led_configs_device on public.led_configs(device_id);
create index if not exists idx_led_configs_active on public.led_configs(device_id, is_active);

-- LED button mappings table: Game-specific LED configurations
create table if not exists public.led_maps (
  id         uuid primary key default gen_random_uuid(),
  device_id  uuid not null references public.devices(id) on delete cascade,
  game_id    text not null,
  button_map jsonb not null,                -- button -> LED color mappings
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_led_maps_device_game on public.led_maps(device_id, game_id);

-- =============================
-- Row Level Security (RLS)
-- =============================
alter table public.devices           enable row level security;
alter table public.commands          enable row level security;
alter table public.telemetry         enable row level security;
alter table public.scores            enable row level security;
alter table public.user_tendencies   enable row level security;
alter table public.led_configs       enable row level security;
alter table public.led_maps          enable row level security;

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

-- USER_TENDENCIES: devices can read/write their own user data
drop policy if exists p_user_tendencies_device on public.user_tendencies;
create policy p_user_tendencies_device
on public.user_tendencies
for all using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_user_tendencies_admin on public.user_tendencies;
create policy p_user_tendencies_admin
on public.user_tendencies
for all using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- LED_CONFIGS: devices can manage their own LED configurations
drop policy if exists p_led_configs_device on public.led_configs;
create policy p_led_configs_device
on public.led_configs
for all using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_led_configs_admin on public.led_configs;
create policy p_led_configs_admin
on public.led_configs
for all using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- LED_MAPS: devices can manage their own game-LED mappings
drop policy if exists p_led_maps_device on public.led_maps;
create policy p_led_maps_device
on public.led_maps
for all using (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

drop policy if exists p_led_maps_admin on public.led_maps;
create policy p_led_maps_admin
on public.led_maps
for all using (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  or (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

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

drop trigger if exists trg_user_tendencies_updated on public.user_tendencies;
create trigger trg_user_tendencies_updated
before update on public.user_tendencies
for each row execute procedure public.touch_updated_at();

drop trigger if exists trg_led_configs_updated on public.led_configs;
create trigger trg_led_configs_updated
before update on public.led_configs
for each row execute procedure public.touch_updated_at();

drop trigger if exists trg_led_maps_updated on public.led_maps;
create trigger trg_led_maps_updated
before update on public.led_maps
for each row execute procedure public.touch_updated_at();

-- =============================
-- Helpful Views (Optional)
-- =============================

-- Active devices view
create or replace view public.active_devices as
select
  id,
  serial,
  status,
  version,
  last_seen,
  extract(epoch from (now() - last_seen)) as seconds_since_seen
from public.devices
where status = 'online'
  and last_seen > now() - interval '10 minutes';

-- Recent telemetry view (last 24 hours)
create or replace view public.recent_telemetry as
select
  t.id,
  t.device_id,
  d.serial,
  t.level,
  t.code,
  t.message,
  t.created_at
from public.telemetry t
join public.devices d on t.device_id = d.id
where t.created_at > now() - interval '24 hours'
order by t.created_at desc;

-- Top scores leaderboard view
create or replace view public.leaderboard as
select
  s.game_id,
  s.player,
  s.score,
  s.created_at,
  d.serial as device_serial,
  row_number() over (partition by s.game_id order by s.score desc) as rank
from public.scores s
join public.devices d on s.device_id = d.id
order by s.game_id, s.score desc;

-- =============================
-- Complete!
-- =============================

-- Grant necessary permissions (adjust as needed)
grant usage on schema public to anon, authenticated;
grant all on all tables in schema public to anon, authenticated;
grant all on all sequences in schema public to anon, authenticated;
grant all on all functions in schema public to anon, authenticated;

-- Success message
do $$
begin
  raise notice 'Arcade Assistant Supabase schema deployed successfully!';
  raise notice 'Tables created: devices, commands, telemetry, scores, user_tendencies, led_configs, led_maps';
  raise notice 'Next steps:';
  raise notice '  1. Create storage buckets: updates, assets';
  raise notice '  2. Deploy Edge Functions: register_device, send_command, sign_url';
  raise notice '  3. Update .env with SUPABASE_URL and SUPABASE_ANON_KEY';
end $$;
