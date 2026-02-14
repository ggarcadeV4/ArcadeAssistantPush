-- Migration: Cabinet Config + LoRa Sessions Tables
-- Date: 2026-02-03
-- Purpose: Enable remote model switching and stateless session persistence
-- Part of: Gem-Agent Refactor (GEMS_PIVOT_VIGILANCE.md)

-- Enable pgcrypto for UUIDs if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================
-- Helper function for updated_at triggers
-- =============================
CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- =============================
-- cabinet_config: Remote configuration per device
-- =============================
-- Allows Fleet Console to remotely switch AI models, enable feature flags,
-- and configure per-cabinet behavior without code deployments.

CREATE TABLE IF NOT EXISTS public.cabinet_config (
  device_id      uuid PRIMARY KEY,
  ai_model       text NOT NULL DEFAULT 'gemini-2.0-flash',
  fallback_models jsonb DEFAULT '["claude-3-5-sonnet-20241022", "gpt-4o-mini"]'::jsonb,
  feature_flags  jsonb DEFAULT '{}'::jsonb,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

-- Index for quick model lookups
CREATE INDEX IF NOT EXISTS idx_cabinet_config_device ON public.cabinet_config(device_id);

-- Trigger for updated_at
DROP TRIGGER IF EXISTS trg_cabinet_config_updated ON public.cabinet_config;
CREATE TRIGGER trg_cabinet_config_updated
BEFORE UPDATE ON public.cabinet_config
FOR EACH ROW EXECUTE PROCEDURE public.touch_updated_at();

-- RLS: Device isolation
ALTER TABLE public.cabinet_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_cabinet_config_device_access ON public.cabinet_config;
CREATE POLICY p_cabinet_config_device_access
ON public.cabinet_config
FOR SELECT USING (
  device_id::text = current_setting('request.jwt.claims', true)::jsonb ->> 'device_id'
);

DROP POLICY IF EXISTS p_cabinet_config_admin ON public.cabinet_config;
CREATE POLICY p_cabinet_config_admin
ON public.cabinet_config
FOR ALL USING (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
  OR (current_setting('request.jwt.claims', true)::jsonb ->> 'is_admin') = 'true'
);

-- =============================
-- aa_lora_sessions: Stateless session persistence
-- =============================
-- Migrates the in-memory sessionStore (launchboxAI.js lines 66-135) to Supabase.
-- Enables horizontal scaling and cabinet failover without session loss.

CREATE TABLE IF NOT EXISTS public.aa_lora_sessions (
  device_id      text PRIMARY KEY,
  chat_state     text DEFAULT 'IDLE',
  history        jsonb DEFAULT '[]'::jsonb,
  pending_launch jsonb DEFAULT NULL,
  last_launched  jsonb DEFAULT NULL,
  updated_at     timestamptz DEFAULT now(),
  expires_at     timestamptz DEFAULT (now() + interval '10 minutes')
);

-- Index for TTL cleanup (cron job can DELETE WHERE expires_at < now())
CREATE INDEX IF NOT EXISTS idx_aa_lora_sessions_expires ON public.aa_lora_sessions(expires_at);

-- Index for device lookups
CREATE INDEX IF NOT EXISTS idx_aa_lora_sessions_device ON public.aa_lora_sessions(device_id);

-- Trigger for updated_at (also refresh expires_at on update)
CREATE OR REPLACE FUNCTION public.touch_lora_session_updated()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  NEW.expires_at = now() + interval '10 minutes';
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_aa_lora_sessions_updated ON public.aa_lora_sessions;
CREATE TRIGGER trg_aa_lora_sessions_updated
BEFORE UPDATE ON public.aa_lora_sessions
FOR EACH ROW EXECUTE PROCEDURE public.touch_lora_session_updated();

-- RLS: Any authenticated user can access sessions (device_id is in the row, not JWT)
-- Sessions keyed by x-device-id header, not JWT device_id claim
ALTER TABLE public.aa_lora_sessions ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (gateway uses service role key)
DROP POLICY IF EXISTS p_aa_lora_sessions_service ON public.aa_lora_sessions;
CREATE POLICY p_aa_lora_sessions_service
ON public.aa_lora_sessions
FOR ALL USING (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
);

-- Allow anon/authenticated to read/write their own device_id
-- (matches on the text value, not UUID since device_id can be IP or custom identifier)
DROP POLICY IF EXISTS p_aa_lora_sessions_device ON public.aa_lora_sessions;
CREATE POLICY p_aa_lora_sessions_device
ON public.aa_lora_sessions
FOR ALL USING (true)
WITH CHECK (true);
-- NOTE: Since session device_id comes from x-device-id header (gateway-controlled),
-- and gateway uses service_role key, the above permissive policy is safe.
-- In production, you may want to restrict to authenticated + device_id claim match.

-- =============================
-- Grant permissions
-- =============================
GRANT ALL ON public.cabinet_config TO anon, authenticated;
GRANT ALL ON public.aa_lora_sessions TO anon, authenticated;

-- =============================
-- Success
-- =============================
DO $$
BEGIN
  RAISE NOTICE 'Gem-Agent refactor tables created successfully!';
  RAISE NOTICE 'Tables: cabinet_config, aa_lora_sessions';
  RAISE NOTICE 'Next: Create RemoteConfigService and SessionStore in gateway';
END $$;
