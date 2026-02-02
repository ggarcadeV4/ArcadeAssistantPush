#!/usr/bin/env python3
"""
Schema + RLS Policy Audit for Cabinet Tables
=============================================
READ-ONLY queries to inspect table structure and policies.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

def run_query(client, name, sql):
    """Run a SQL query via RPC and print results."""
    print(f"\n{'='*60}")
    print(f"{name}")
    print('='*60)
    try:
        # Use the rpc method to call a function, or direct query
        # Since we can't run raw SQL via anon client, we'll need service_role
        # Let's try using postgrest to query information_schema
        result = client.rpc('run_sql', {'query': sql}).execute()
        if result.data:
            for row in result.data:
                print(row)
        else:
            print("(no results)")
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("Schema + RLS Audit")
    print("="*60)
    
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("ERROR: Missing SUPABASE_URL or SUPABASE_ANON_KEY")
        return
    
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    
    # A) Table Columns
    tables = ['cabinet', 'cabinet_heartbeat', 'cabinet_telemetry']
    
    print("\n" + "="*60)
    print("A) TABLE COLUMNS")
    print("="*60)
    
    for table in tables:
        print(f"\n--- {table} columns ---")
        try:
            # Query information_schema directly via postgrest isn't possible
            # We need to use a different approach
            # Let's just try to get a sample row to see the columns
            result = client.table(table).select("*").limit(0).execute()
            # This won't show us the schema, but we can check the REST API schema
            print(f"Table exists, checking via API...")
        except Exception as e:
            print(f"Error: {e}")
    
    print("\nNOTE: Raw SQL queries to information_schema require service_role key.")
    print("Please run these queries directly in Supabase SQL Editor:")
    
    print("""
-- A) CABINET COLUMNS
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name='cabinet'
ORDER BY ordinal_position;

-- CABINET_HEARTBEAT COLUMNS  
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name='cabinet_heartbeat'
ORDER BY ordinal_position;

-- CABINET_TELEMETRY COLUMNS
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name='cabinet_telemetry'
ORDER BY ordinal_position;

-- B) PRIMARY/FOREIGN KEYS
SELECT tc.table_name, kcu.column_name, tc.constraint_type
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
WHERE tc.table_schema='public'
  AND tc.table_name IN ('cabinet','cabinet_heartbeat','cabinet_telemetry')
  AND tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')
ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position;

-- C) RLS ENABLED?
SELECT relname AS table, relrowsecurity AS rls_enabled, relforcerowsecurity AS rls_forced
FROM pg_class
JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
WHERE nspname='public'
  AND relname IN ('cabinet','cabinet_heartbeat','cabinet_telemetry');

-- D) POLICIES
SELECT tablename, policyname, cmd, roles, qual::text AS using_expr, with_check::text AS check_expr
FROM pg_policies
WHERE schemaname='public'
  AND tablename IN ('cabinet','cabinet_heartbeat','cabinet_telemetry')
ORDER BY tablename, policyname, cmd;
""")

if __name__ == "__main__":
    main()
