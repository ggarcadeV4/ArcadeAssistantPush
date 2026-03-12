-- Migration: Fleet Manager bridge tables for Arcade Assistant
-- Date: 2026-03-12
-- Purpose: Add escalations + tournaments with compatibility fields for
--          both the Fleet Manager API contract and the current AA runtime.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE OR REPLACE FUNCTION public.sync_escalation_bridge_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.cabinet_id := COALESCE(NULLIF(NEW.cabinet_id, ''), NULLIF(NEW.device_id, ''));
  NEW.device_id := COALESCE(NULLIF(NEW.device_id, ''), NULLIF(NEW.cabinet_id, ''));
  NEW.escalation_type := COALESCE(NULLIF(NEW.escalation_type, ''), NULLIF(NEW.category, ''), 'general');
  NEW.category := COALESCE(NULLIF(NEW.category, ''), NEW.escalation_type);
  NEW.severity := COALESCE(NULLIF(NEW.severity, ''), NULLIF(NEW.priority, ''), 'medium');
  NEW.priority := COALESCE(NULLIF(NEW.priority, ''), NEW.severity);
  NEW.problem_description := COALESCE(
    NULLIF(NEW.problem_description, ''),
    NULLIF(NEW.description, ''),
    'No problem description provided.'
  );
  NEW.description := COALESCE(NULLIF(NEW.description, ''), NEW.problem_description);
  NEW.context_data := COALESCE(NEW.context_data, '{}'::jsonb);
  NEW.error_messages := COALESCE(NEW.error_messages, '[]'::jsonb);
  NEW.local_ai_attempts := COALESCE(NEW.local_ai_attempts, '[]'::jsonb);
  NEW.system_info := COALESCE(NEW.system_info, '{}'::jsonb);
  NEW.affected_components := COALESCE(NEW.affected_components, '[]'::jsonb);
  NEW.updated_at := now();

  IF NEW.status IN ('resolved', 'dismissed') AND NEW.resolved_at IS NULL THEN
    NEW.resolved_at := now();
  END IF;

  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS public.escalations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cabinet_id text REFERENCES public.cabinet(cabinet_id) ON DELETE SET NULL,
  device_id text,
  escalation_type text NOT NULL DEFAULT 'general',
  category text,
  severity text NOT NULL DEFAULT 'medium',
  priority text,
  title text,
  problem_description text NOT NULL DEFAULT '',
  description text,
  context_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  cabinet_name text,
  cabinet_serial text,
  error_messages jsonb NOT NULL DEFAULT '[]'::jsonb,
  logs_snippet text,
  local_ai_analysis text,
  local_ai_attempts jsonb NOT NULL DEFAULT '[]'::jsonb,
  system_info jsonb NOT NULL DEFAULT '{}'::jsonb,
  affected_components jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'open',
  solution jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by text,
  resolution_notes text
);

DROP TRIGGER IF EXISTS trg_escalations_sync_fields ON public.escalations;
CREATE TRIGGER trg_escalations_sync_fields
BEFORE INSERT OR UPDATE ON public.escalations
FOR EACH ROW EXECUTE PROCEDURE public.sync_escalation_bridge_fields();

ALTER TABLE public.escalations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS escalations_cabinet_insert ON public.escalations;
CREATE POLICY escalations_cabinet_insert
ON public.escalations
FOR INSERT
WITH CHECK (true);

DROP POLICY IF EXISTS escalations_read_all ON public.escalations;
CREATE POLICY escalations_read_all
ON public.escalations
FOR SELECT
USING (true);

DROP POLICY IF EXISTS escalations_update ON public.escalations;
CREATE POLICY escalations_update
ON public.escalations
FOR UPDATE
USING (true)
WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_escalations_status
ON public.escalations(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_escalations_cabinet
ON public.escalations(cabinet_id);

CREATE INDEX IF NOT EXISTS idx_escalations_device
ON public.escalations(device_id);

GRANT ALL ON public.escalations TO anon, authenticated;

CREATE OR REPLACE FUNCTION public.sync_tournament_bridge_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.status := COALESCE(NULLIF(NEW.status, ''), CASE WHEN COALESCE(NEW.active, true) THEN 'active' ELSE 'completed' END);
  NEW.active := COALESCE(
    NEW.active,
    CASE WHEN NEW.status IN ('completed', 'cancelled') THEN false ELSE true END
  );

  IF NEW.status IN ('completed', 'cancelled') AND NEW.end_time IS NULL THEN
    NEW.end_time := now();
  END IF;

  NEW.players := COALESCE(NEW.players, '[]'::jsonb);
  NEW.config := COALESCE(NEW.config, '{}'::jsonb);
  NEW.bracket_data := COALESCE(NEW.bracket_data, '{}'::jsonb);
  NEW.completed_matches := COALESCE(NEW.completed_matches, '[]'::jsonb);
  NEW.updated_at := now();

  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS public.tournaments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id text NOT NULL UNIQUE,
  cabinet_id text REFERENCES public.cabinet(cabinet_id) ON DELETE SET NULL,
  name text NOT NULL,
  mode text NOT NULL DEFAULT 'casual',
  players jsonb NOT NULL DEFAULT '[]'::jsonb,
  game_id text,
  status text NOT NULL DEFAULT 'active',
  active boolean NOT NULL DEFAULT true,
  start_time timestamptz NOT NULL DEFAULT now(),
  end_time timestamptz,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  bracket_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  current_round integer NOT NULL DEFAULT 1,
  completed_matches jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  fairness_score double precision NOT NULL DEFAULT 0
);

DROP TRIGGER IF EXISTS trg_tournaments_sync_fields ON public.tournaments;
CREATE TRIGGER trg_tournaments_sync_fields
BEFORE INSERT OR UPDATE ON public.tournaments
FOR EACH ROW EXECUTE PROCEDURE public.sync_tournament_bridge_fields();

ALTER TABLE public.tournaments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tournaments_insert ON public.tournaments;
CREATE POLICY tournaments_insert
ON public.tournaments
FOR INSERT
WITH CHECK (true);

DROP POLICY IF EXISTS tournaments_read_all ON public.tournaments;
CREATE POLICY tournaments_read_all
ON public.tournaments
FOR SELECT
USING (true);

DROP POLICY IF EXISTS tournaments_update ON public.tournaments;
CREATE POLICY tournaments_update
ON public.tournaments
FOR UPDATE
USING (true)
WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_tournaments_status
ON public.tournaments(status);

CREATE INDEX IF NOT EXISTS idx_tournaments_cabinet
ON public.tournaments(cabinet_id);

CREATE INDEX IF NOT EXISTS idx_tournaments_active
ON public.tournaments(active, updated_at DESC);

GRANT ALL ON public.tournaments TO anon, authenticated;
