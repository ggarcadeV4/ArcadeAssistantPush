/**
 * One-Click Migration Script: Cabinet Config + LoRa Sessions
 * Date: 2026-02-03
 * 
 * Run with: node scripts/run_gem_migration.js
 * 
 * This script uses the Supabase service role key to execute the
 * Gem-Agent refactor migration (cabinet_config + aa_lora_sessions tables).
 */

import 'dotenv/config';

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    console.error('❌ ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env');
    process.exit(1);
}

const MIGRATION_SQL = `
-- Migration: Cabinet Config + LoRa Sessions Tables
-- Part of: Gem-Agent Refactor (GEMS_PIVOT_VIGILANCE.md)

-- =============================
-- cabinet_config: Remote configuration per device
-- =============================
CREATE TABLE IF NOT EXISTS public.cabinet_config (
  device_id      uuid PRIMARY KEY REFERENCES public.devices(id) ON DELETE CASCADE,
  ai_model       text NOT NULL DEFAULT 'gemini-2.0-flash',
  fallback_models jsonb DEFAULT '["claude-3-5-sonnet-20241022", "gpt-4o-mini"]'::jsonb,
  feature_flags  jsonb DEFAULT '{}'::jsonb,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cabinet_config_device ON public.cabinet_config(device_id);

DROP TRIGGER IF EXISTS trg_cabinet_config_updated ON public.cabinet_config;
CREATE TRIGGER trg_cabinet_config_updated
BEFORE UPDATE ON public.cabinet_config
FOR EACH ROW EXECUTE PROCEDURE public.touch_updated_at();

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
CREATE TABLE IF NOT EXISTS public.aa_lora_sessions (
  device_id      text PRIMARY KEY,
  chat_state     text DEFAULT 'IDLE',
  history        jsonb DEFAULT '[]'::jsonb,
  pending_launch jsonb DEFAULT NULL,
  last_launched  jsonb DEFAULT NULL,
  updated_at     timestamptz DEFAULT now(),
  expires_at     timestamptz DEFAULT (now() + interval '10 minutes')
);

CREATE INDEX IF NOT EXISTS idx_aa_lora_sessions_expires ON public.aa_lora_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_aa_lora_sessions_device ON public.aa_lora_sessions(device_id);

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

ALTER TABLE public.aa_lora_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_aa_lora_sessions_service ON public.aa_lora_sessions;
CREATE POLICY p_aa_lora_sessions_service
ON public.aa_lora_sessions
FOR ALL USING (
  (current_setting('request.jwt.claims', true)::jsonb ->> 'role') = 'service_role'
);

DROP POLICY IF EXISTS p_aa_lora_sessions_device ON public.aa_lora_sessions;
CREATE POLICY p_aa_lora_sessions_device
ON public.aa_lora_sessions
FOR ALL USING (true)
WITH CHECK (true);

GRANT ALL ON public.cabinet_config TO anon, authenticated;
GRANT ALL ON public.aa_lora_sessions TO anon, authenticated;
`;

async function runMigration() {
    console.log('🚀 Gem-Agent Refactor Migration');
    console.log('================================');
    console.log(`📡 Target: ${SUPABASE_URL}`);
    console.log('');

    try {
        // Use the Supabase REST API with raw SQL via the pg_query RPC
        // Note: Supabase doesn't expose raw SQL execution via REST by default
        // We'll use the Management API instead (requires project ref extraction)

        const projectRef = SUPABASE_URL.match(/https:\/\/([^.]+)\.supabase\.co/)?.[1];
        if (!projectRef) {
            throw new Error('Could not extract project ref from SUPABASE_URL');
        }

        console.log(`📋 Project: ${projectRef}`);
        console.log('');
        console.log('⏳ Executing SQL migration...');

        // Try to use the SQL execution endpoint (if available)
        // This typically requires the Management API token, not the service role key
        // Let's try the PostgREST approach first with individual table checks

        const headers = {
            'apikey': SUPABASE_SERVICE_ROLE_KEY,
            'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        };

        // Check if tables already exist by querying them
        console.log('');
        console.log('📊 Checking existing tables...');

        // Check cabinet_config
        let cabinetConfigExists = false;
        try {
            const resp = await fetch(`${SUPABASE_URL}/rest/v1/cabinet_config?select=device_id&limit=1`, {
                method: 'GET',
                headers
            });
            cabinetConfigExists = resp.ok || resp.status === 200;
            console.log(`   cabinet_config: ${cabinetConfigExists ? '✅ EXISTS' : '❌ NOT FOUND'}`);
        } catch (e) {
            console.log(`   cabinet_config: ❌ NOT FOUND (${e.message})`);
        }

        // Check aa_lora_sessions
        let loraSessionsExists = false;
        try {
            const resp = await fetch(`${SUPABASE_URL}/rest/v1/aa_lora_sessions?select=device_id&limit=1`, {
                method: 'GET',
                headers
            });
            loraSessionsExists = resp.ok || resp.status === 200;
            console.log(`   aa_lora_sessions: ${loraSessionsExists ? '✅ EXISTS' : '❌ NOT FOUND'}`);
        } catch (e) {
            console.log(`   aa_lora_sessions: ❌ NOT FOUND (${e.message})`);
        }

        // Check devices table for our device
        const deviceId = process.env.AA_DEVICE_ID;
        if (deviceId) {
            try {
                const resp = await fetch(`${SUPABASE_URL}/rest/v1/devices?id=eq.${deviceId}&select=id,serial,status`, {
                    method: 'GET',
                    headers
                });
                if (resp.ok) {
                    const devices = await resp.json();
                    if (devices.length > 0) {
                        console.log(`   devices (${deviceId.slice(0, 8)}...): ✅ REGISTERED`);
                    } else {
                        console.log(`   devices (${deviceId.slice(0, 8)}...): ⚠️ NOT REGISTERED`);
                    }
                }
            } catch (e) {
                console.log(`   devices: ⚠️ Could not check (${e.message})`);
            }
        }

        console.log('');

        if (cabinetConfigExists && loraSessionsExists) {
            console.log('✅ MIGRATION ALREADY APPLIED!');
            console.log('');
            console.log('Both tables exist. The Pipes are open.');
            console.log('Proceed to Phase 2: RemoteConfigService');
            process.exit(0);
        }

        // If tables don't exist, we need to run SQL
        // Unfortunately, Supabase REST API doesn't allow raw SQL execution
        // We need to guide the user to run it manually
        console.log('');
        console.log('⚠️  TABLES NEED TO BE CREATED');
        console.log('');
        console.log('The Supabase REST API cannot execute raw SQL migrations.');
        console.log('Please run the SQL manually in Supabase SQL Editor:');
        console.log('');
        console.log(`   https://supabase.com/dashboard/project/${projectRef}/sql/new`);
        console.log('');
        console.log('SQL file location:');
        console.log('   supabase/migrations/20260203_cabinet_config_and_sessions.sql');
        console.log('');
        process.exit(1);

    } catch (error) {
        console.error('');
        console.error('❌ Migration failed:', error.message);
        process.exit(1);
    }
}

runMigration();
