/**
 * Direct PostgreSQL Migration Executor
 * Connects directly to Supabase's PostgreSQL and runs the migration
 * 
 * Run with: node scripts/execute_migration_direct.js
 */

import 'dotenv/config';
import pg from 'pg';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Supabase PostgreSQL connection details
// Format: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
const SUPABASE_URL = process.env.SUPABASE_URL;
const projectRef = SUPABASE_URL?.match(/https:\/\/([^.]+)\.supabase\.co/)?.[1];

// Supabase direct connection uses the service role key as password
// Connection string format for Supabase
const DATABASE_URL = process.env.DATABASE_URL ||
    `postgresql://postgres.${projectRef}:${process.env.SUPABASE_SERVICE_ROLE_KEY}@aws-0-us-east-1.pooler.supabase.com:6543/postgres`;

// Alternative: Use Supabase's direct connection (port 5432)
// postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres

async function executeMigration() {
    console.log('🚀 Direct PostgreSQL Migration');
    console.log('==============================');
    console.log(`📋 Project: ${projectRef}`);
    console.log('');

    // Read the migration SQL
    const migrationPath = path.join(__dirname, '..', 'supabase', 'migrations', '20260203_cabinet_config_and_sessions.sql');

    if (!fs.existsSync(migrationPath)) {
        console.error('❌ Migration file not found:', migrationPath);
        process.exit(1);
    }

    const migrationSQL = fs.readFileSync(migrationPath, 'utf-8');
    console.log('📄 Migration file loaded');
    console.log('');

    // Try different connection methods
    const connectionConfigs = [
        {
            name: 'Supabase Pooler (Transaction Mode)',
            connectionString: `postgresql://postgres.${projectRef}:${process.env.SUPABASE_SERVICE_ROLE_KEY}@aws-0-us-east-1.pooler.supabase.com:6543/postgres`,
            ssl: { rejectUnauthorized: false }
        },
        {
            name: 'Supabase Direct',
            connectionString: `postgresql://postgres:${process.env.SUPABASE_SERVICE_ROLE_KEY}@db.${projectRef}.supabase.co:5432/postgres`,
            ssl: { rejectUnauthorized: false }
        }
    ];

    for (const config of connectionConfigs) {
        console.log(`⏳ Trying: ${config.name}...`);

        const client = new pg.Client({
            connectionString: config.connectionString,
            ssl: config.ssl,
            connectionTimeoutMillis: 10000
        });

        try {
            await client.connect();
            console.log('✅ Connected!');
            console.log('');
            console.log('⏳ Executing migration...');

            await client.query(migrationSQL);

            console.log('');
            console.log('✅ MIGRATION SUCCESSFUL!');
            console.log('');

            // Verify tables exist
            const tableCheck = await client.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('cabinet_config', 'aa_lora_sessions')
        ORDER BY table_name
      `);

            console.log('📊 Verification:');
            for (const row of tableCheck.rows) {
                console.log(`   ✅ ${row.table_name}`);
            }

            await client.end();
            console.log('');
            console.log('🎉 THE PIPES ARE OPEN!');
            console.log('   Proceed to Phase 2: RemoteConfigService');
            process.exit(0);

        } catch (error) {
            console.log(`   ❌ Failed: ${error.message}`);
            try { await client.end(); } catch (e) { }
        }
    }

    // If we get here, all connection methods failed
    console.log('');
    console.log('❌ Could not connect to PostgreSQL directly.');
    console.log('');
    console.log('The Supabase service role key cannot be used as a database password.');
    console.log('You need to run the migration manually in the SQL Editor:');
    console.log(`   https://supabase.com/dashboard/project/${projectRef}/sql/new`);
    process.exit(1);
}

executeMigration();
