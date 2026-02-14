-- Arcade Assistant - Schema Migration: Align with Runtime Names
-- Run this in Supabase SQL Editor
-- Date: 2026-01-07

-- =============================
-- Part 1: Rename Tables to Match Runtime Code
-- =============================

-- Rename 'devices' to 'cabinet'
ALTER TABLE IF EXISTS public.devices RENAME TO cabinet;

-- Rename 'scores' to 'cabinet_game_score'
ALTER TABLE IF EXISTS public.scores RENAME TO cabinet_game_score;

-- Rename 'telemetry' to 'cabinet_telemetry'
ALTER TABLE IF EXISTS public.telemetry RENAME TO cabinet_telemetry;

-- Rename 'commands' to 'command_queue'
ALTER TABLE IF EXISTS public.commands RENAME TO command_queue;

-- =============================
-- Part 2: Add Missing Tournaments Table
-- =============================

CREATE TABLE IF NOT EXISTS public.tournaments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  mode TEXT NOT NULL,  -- bracket_8, round_robin, etc.
  players JSONB DEFAULT '[]'::jsonb,
  bracket_data JSONB DEFAULT '{}'::jsonb,
  current_round INTEGER DEFAULT 0,
  completed_matches INTEGER DEFAULT 0,
  active BOOLEAN DEFAULT true,
  fairness_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for tournaments
CREATE INDEX IF NOT EXISTS idx_tournaments_active ON public.tournaments(active);
CREATE INDEX IF NOT EXISTS idx_tournaments_created ON public.tournaments(created_at DESC);

-- updated_at trigger
DROP TRIGGER IF EXISTS trg_tournaments_updated ON public.tournaments;
CREATE TRIGGER trg_tournaments_updated
BEFORE UPDATE ON public.tournaments
FOR EACH ROW EXECUTE PROCEDURE public.touch_updated_at();

-- RLS for tournaments
ALTER TABLE public.tournaments ENABLE ROW LEVEL SECURITY;

-- Anon can insert/read tournaments
DROP POLICY IF EXISTS anon_insert_tournaments ON public.tournaments;
CREATE POLICY anon_insert_tournaments ON public.tournaments
FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS anon_select_tournaments ON public.tournaments;
CREATE POLICY anon_select_tournaments ON public.tournaments
FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS anon_update_tournaments ON public.tournaments;
CREATE POLICY anon_update_tournaments ON public.tournaments
FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- =============================
-- Part 3: Update Index Names (optional, for clarity)
-- =============================

-- These will fail silently if indices don't exist with old names
-- ALTER INDEX IF EXISTS idx_devices_owner RENAME TO idx_cabinet_owner;
-- ALTER INDEX IF EXISTS idx_devices_last_seen RENAME TO idx_cabinet_last_seen;
-- ALTER INDEX IF EXISTS idx_scores_game RENAME TO idx_cabinet_game_score_game;

-- =============================
-- Part 4: Grant Permissions
-- =============================

GRANT SELECT, INSERT, UPDATE ON public.tournaments TO anon;
GRANT SELECT, INSERT, UPDATE ON public.tournaments TO authenticated;

-- =============================
-- Complete
-- =============================

DO $$
BEGIN
  RAISE NOTICE 'Schema migration complete!';
  RAISE NOTICE 'Tables renamed: devices→cabinet, scores→cabinet_game_score, telemetry→cabinet_telemetry, commands→command_queue';
  RAISE NOTICE 'New table created: tournaments';
END $$;
