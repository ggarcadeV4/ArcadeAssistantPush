-- Arcade Assistant - Schema Migration: Add High Score Pipeline Columns
-- Run this in Supabase SQL Editor
-- Date: 2026-01-07
-- Purpose: Add columns documented in supabase/README.md High Score Pipeline section

-- =============================
-- Part 1: Add Missing Columns to cabinet_game_score
-- =============================

-- Add game_title column (human-readable game name)
ALTER TABLE public.cabinet_game_score 
ADD COLUMN IF NOT EXISTS game_title TEXT;

-- Add source column (where the score came from)
ALTER TABLE public.cabinet_game_score 
ADD COLUMN IF NOT EXISTS source TEXT;

-- =============================
-- Part 2: Add Index for Source Filtering
-- =============================

CREATE INDEX IF NOT EXISTS idx_cabinet_game_score_source 
ON public.cabinet_game_score(source);

CREATE INDEX IF NOT EXISTS idx_cabinet_game_score_game_title 
ON public.cabinet_game_score(game_title);

-- =============================
-- Part 3: Update RLS Policies for Anon Insert
-- =============================

-- Ensure anon can insert scores (needed for cabinet score submission)
DROP POLICY IF EXISTS anon_insert_cabinet_game_score ON public.cabinet_game_score;
CREATE POLICY anon_insert_cabinet_game_score ON public.cabinet_game_score
FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS anon_select_cabinet_game_score ON public.cabinet_game_score;
CREATE POLICY anon_select_cabinet_game_score ON public.cabinet_game_score
FOR SELECT TO anon USING (true);

-- =============================
-- Complete
-- =============================

DO $$
BEGIN
  RAISE NOTICE 'High Score Pipeline migration complete!';
  RAISE NOTICE 'Added columns: game_title, source';
  RAISE NOTICE 'Added indexes: idx_cabinet_game_score_source, idx_cabinet_game_score_game_title';
END $$;
