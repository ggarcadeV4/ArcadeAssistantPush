-- Migration: Add active_player column for identity hydration
-- Date: 2026-02-03
-- Purpose: Fix Identity Source Mismatch - store active player in Supabase
-- Part of: Phase 4 Sam Gem Pivot (GEMS_PIVOT_VIGILANCE.md)

-- =============================
-- Add active_player column to aa_lora_sessions
-- =============================
-- This enables Sam (ScoreKeeper) to pull identity from Supabase
-- instead of the local active_session.json file.

ALTER TABLE public.aa_lora_sessions 
ADD COLUMN IF NOT EXISTS active_player jsonb DEFAULT NULL;

-- Structure: { "player_name": "...", "player_id": "uuid", "initials": "AAA" }
COMMENT ON COLUMN public.aa_lora_sessions.active_player IS 
  'Active player for score attribution. Set by frontend on profile select. Structure: { player_name, player_id, initials }';

-- =============================
-- Success
-- =============================
DO $$
BEGIN
  RAISE NOTICE 'Phase 4: active_player column added to aa_lora_sessions';
  RAISE NOTICE 'Sam gem can now pull identity from Supabase session';
END $$;
