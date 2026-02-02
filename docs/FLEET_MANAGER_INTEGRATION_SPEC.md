# 🔌 Fleet Manager Integration Specification

**Version:** 1.0.0  
**Date:** December 13, 2025  
**Purpose:** Everything needed to build Fleet Manager ↔ Cabinet communication

---

## 1. Quick Start Checklist

Before you write a single line of code, you need:

```
□ Supabase project URL
□ Supabase service role key (for admin operations)
□ Supabase anon key (for realtime subscriptions)
□ Database tables created (schema below)
□ Realtime enabled on key tables
```

---

## 2. Supabase Schema (Copy-Paste Ready)

```sql
-- ============================================================================
-- DEVICES TABLE - Every cabinet registers here
-- ============================================================================
CREATE TABLE devices (
  id UUID PRIMARY KEY,
  serial TEXT UNIQUE NOT NULL,           -- Format: AA-YYYYMMDD-XXXXXXXX
  name TEXT NOT NULL,                    -- User-assigned name (e.g., "StarJab")
  status TEXT DEFAULT 'offline',         -- online, offline, maintenance, updating
  version TEXT,                          -- Current AA version (e.g., "1.2.0")
  last_seen TIMESTAMPTZ,                 -- Last heartbeat timestamp
  tags JSONB DEFAULT '{}',               -- Hardware info, custom metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick online device queries
CREATE INDEX idx_devices_last_seen ON devices(last_seen DESC);
CREATE INDEX idx_devices_status ON devices(status);

-- ============================================================================
-- TELEMETRY TABLE - All cabinet events flow here
-- ============================================================================
CREATE TABLE telemetry (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  level TEXT NOT NULL,                   -- INFO, WARN, ERROR, CRITICAL
  code TEXT NOT NULL,                    -- Event code (see Section 5)
  message TEXT,
  payload JSONB DEFAULT '{}',            -- Event-specific data
  tenant_id TEXT DEFAULT 'default',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick device telemetry queries
CREATE INDEX idx_telemetry_device_created ON telemetry(device_id, created_at DESC);
CREATE INDEX idx_telemetry_code ON telemetry(code);

-- ============================================================================
-- COMMAND_QUEUE TABLE - Fleet Manager → Cabinet commands
-- ============================================================================
CREATE TABLE command_queue (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  command TEXT NOT NULL,                 -- Command type (see Section 6)
  payload JSONB DEFAULT '{}',            -- Command parameters
  status TEXT DEFAULT 'pending',         -- pending, processing, done, failed
  result JSONB,                          -- Execution result
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ                 -- Optional: auto-expire old commands
);

-- Index for cabinet polling
CREATE INDEX idx_command_queue_device_status ON command_queue(device_id, status);

-- ============================================================================
-- ESCALATIONS TABLE - Cabinet AI → Fleet Manager AI
-- ============================================================================
CREATE TABLE escalations (
  id UUID PRIMARY KEY,
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  cabinet_name TEXT,
  cabinet_serial TEXT,
  
  -- Problem details
  category TEXT NOT NULL,                -- update, hardware, config, emulator, network
  title TEXT NOT NULL,
  description TEXT,
  error_messages JSONB DEFAULT '[]',
  logs_snippet TEXT,
  
  -- Local AI context
  local_ai_analysis TEXT,
  local_ai_attempts JSONB DEFAULT '[]',
  
  -- System state at time of escalation
  system_info JSONB DEFAULT '{}',
  affected_components JSONB DEFAULT '[]',
  
  -- Status tracking
  priority TEXT DEFAULT 'medium',        -- low, medium, high, critical
  status TEXT DEFAULT 'pending',         -- See Section 7
  
  -- Solution (Fleet Manager fills this)
  solution JSONB,
  resolution_notes TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for Fleet Manager dashboard
CREATE INDEX idx_escalations_status ON escalations(status);
CREATE INDEX idx_escalations_priority ON escalations(priority);

-- ============================================================================
-- SCORES TABLE - High scores from all cabinets
-- ============================================================================
CREATE TABLE scores (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
  game_id TEXT NOT NULL,
  player TEXT NOT NULL,
  score BIGINT NOT NULL,
  meta JSONB DEFAULT '{}',               -- Extra data (time, difficulty, etc.)
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scores_game ON scores(game_id, score DESC);

-- ============================================================================
-- ENABLE REALTIME (Required for live updates)
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE devices;
ALTER PUBLICATION supabase_realtime ADD TABLE command_queue;
ALTER PUBLICATION supabase_realtime ADD TABLE escalations;
ALTER PUBLICATION supabase_realtime ADD TABLE telemetry;
```

---

## 3. Communication Patterns

### 3.1 Cabinet → Supabase (Push)

Cabinets push data to Supabase. Fleet Manager reads it.

| Data Type | Table | Frequency | Trigger |
|-----------|-------|-----------|---------|
| Heartbeat | `devices` (update) | Every 5 min | Timer |
| Game launch | `telemetry` | On event | User action |
| AI usage | `telemetry` | On event | AI call |
| Escalation | `escalations` | On event | AI decision |
| High score | `scores` | On event | Game end |

### 3.2 Fleet Manager → Cabinet (Pull)

Cabinets poll Supabase for commands. Fleet Manager writes them.

```
Fleet Manager writes to command_queue
         ↓
Cabinet polls every 60 seconds
         ↓
Cabinet executes command
         ↓
Cabinet updates command status to "done"
```

### 3.3 Realtime (Recommended)

Use Supabase Realtime for instant updates:

```javascript
// Fleet Manager subscribes to device changes
const subscription = supabase
  .channel('devices')
  .on('postgres_changes', 
    { event: '*', schema: 'public', table: 'devices' },
    (payload) => {
      console.log('Device changed:', payload);
      updateDashboard(payload.new);
    }
  )
  .subscribe();

// Fleet Manager subscribes to new escalations
const escalationSub = supabase
  .channel('escalations')
  .on('postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'escalations' },
    (payload) => {
      console.log('New escalation:', payload.new);
      notifyOperator(payload.new);
      queueForAIAnalysis(payload.new);
    }
  )
  .subscribe();
```

---

## 4. Device Data Structure

### 4.1 Device Record

```typescript
interface Device {
  id: string;              // UUID - unique device identifier
  serial: string;          // "AA-20251213-ABCD1234"
  name: string;            // "StarJab"
  status: "online" | "offline" | "maintenance" | "updating";
  version: string;         // "1.2.0"
  last_seen: string;       // ISO 8601 timestamp
  tags: {
    // Hardware info (captured during provisioning)
    hostname: string;
    os: string;
    os_version: string;
    motherboard_serial?: string;
    bios_serial?: string;
    cpu_id?: string;
    processor?: string;
    
    // Custom tags you can add
    location?: string;     // "Omaha, NE"
    owner?: string;        // "Bob's Arcade"
    notes?: string;
  };
  created_at: string;
  updated_at: string;
}
```

### 4.2 Determining Online Status

```javascript
function isOnline(device) {
  const lastSeen = new Date(device.last_seen);
  const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000);
  return lastSeen > tenMinutesAgo;
}

function getStatusColor(device) {
  if (device.status === 'updating') return 'yellow';
  if (device.status === 'maintenance') return 'orange';
  if (isOnline(device)) return 'green';
  return 'red';
}
```

---

## 5. Telemetry Event Codes

Cabinets send these event codes. Use them for filtering and dashboards.

### 5.1 System Events

| Code | Level | Description |
|------|-------|-------------|
| `STARTUP` | INFO | Backend started |
| `SHUTDOWN` | INFO | Backend shutting down |
| `HEARTBEAT` | INFO | Periodic heartbeat |
| `ERROR` | ERROR | General error |
| `HEALTH_CHECK` | INFO | Health check result |

### 5.2 Game Events

| Code | Level | Payload |
|------|-------|---------|
| `GAME_LAUNCHED` | INFO | `{game_id, title, platform, player}` |
| `GAME_ENDED` | INFO | `{game_id, duration_mins, score}` |
| `HIGH_SCORE` | INFO | `{game_id, player, score, rank}` |

### 5.3 AI Events

| Code | Level | Payload |
|------|-------|---------|
| `AI_USAGE` | INFO | `{tier, model, input_tokens, output_tokens, cost_cents, panel}` |
| `AI_BUDGET_WARNING` | WARN | `{daily_spent, daily_budget, percent_used}` |
| `AI_ESCALATED` | INFO | `{ticket_id, category, title}` |

### 5.4 Update Events

| Code | Level | Payload |
|------|-------|---------|
| `UPDATE_STAGED` | INFO | `{bundle_id, version}` |
| `UPDATE_APPLIED` | INFO | `{version_before, version_after, ai_assisted}` |
| `UPDATE_FAILED` | ERROR | `{version, error, rolled_back}` |
| `UPDATE_ROLLBACK` | WARN | `{version, reason}` |

### 5.5 Query Examples

```javascript
// Get all errors from a device in last 24 hours
const { data } = await supabase
  .from('telemetry')
  .select('*')
  .eq('device_id', deviceId)
  .eq('level', 'ERROR')
  .gte('created_at', new Date(Date.now() - 86400000).toISOString())
  .order('created_at', { ascending: false });

// Get AI costs for today across fleet
const today = new Date().toISOString().split('T')[0];
const { data } = await supabase
  .from('telemetry')
  .select('payload')
  .eq('code', 'AI_USAGE')
  .gte('created_at', today);

const totalCost = data.reduce((sum, e) => sum + (e.payload?.cost_cents || 0), 0);
```

---

## 6. Command Queue Protocol

### 6.1 Command Types

| Command | Payload | Description |
|---------|---------|-------------|
| `PING` | `{}` | Test connectivity |
| `RESTART_BACKEND` | `{}` | Restart the Python backend |
| `DOWNLOAD_UPDATE` | `{bundle_url, version, sha256}` | Download update bundle |
| `APPLY_UPDATE` | `{bundle_id}` | Apply staged update |
| `ROLLBACK` | `{}` | Rollback to previous version |
| `RUN_DIAGNOSTIC` | `{type: "full" \| "quick"}` | Run diagnostics |
| `SYNC_CONFIG` | `{config_path, content}` | Push config to cabinet |
| `CLEAR_CACHE` | `{cache_type}` | Clear specific cache |
| `SEND_SOLUTION` | `{ticket_id, solution}` | Send escalation solution |

### 6.2 Sending a Command

```javascript
async function sendCommand(deviceId, command, payload = {}) {
  const { data, error } = await supabase
    .from('command_queue')
    .insert({
      device_id: deviceId,
      command: command,
      payload: payload,
      status: 'pending',
      expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() // 24h expiry
    })
    .select()
    .single();
  
  if (error) throw error;
  return data.id;
}

// Example: Push update to cabinet
await sendCommand(deviceId, 'DOWNLOAD_UPDATE', {
  bundle_url: 'https://storage.example.com/updates/aa-1.2.1.zip',
  version: '1.2.1',
  sha256: 'abc123...'
});
```

### 6.3 Monitoring Command Execution

```javascript
// Subscribe to command status changes
const commandSub = supabase
  .channel('commands')
  .on('postgres_changes',
    { event: 'UPDATE', schema: 'public', table: 'command_queue' },
    (payload) => {
      if (payload.new.status === 'done') {
        console.log('Command completed:', payload.new.result);
      } else if (payload.new.status === 'failed') {
        console.error('Command failed:', payload.new.result);
      }
    }
  )
  .subscribe();

// Or poll for specific command
async function waitForCommand(commandId, timeoutMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const { data } = await supabase
      .from('command_queue')
      .select('status, result')
      .eq('id', commandId)
      .single();
    
    if (data.status === 'done' || data.status === 'failed') {
      return data;
    }
    
    await new Promise(r => setTimeout(r, 2000)); // Poll every 2s
  }
  throw new Error('Command timed out');
}
```

---

## 7. Escalation Protocol

### 7.1 Escalation Statuses

```
pending → acknowledged → analyzing → solution_ready → applied → resolved
                                  ↘ human_needed
                                  ↘ failed
```

| Status | Who Sets It | Meaning |
|--------|-------------|---------|
| `pending` | Cabinet | Waiting for Fleet Manager |
| `acknowledged` | Fleet Manager | Received, queued for AI |
| `analyzing` | Fleet Manager | AI is working on it |
| `solution_ready` | Fleet Manager | Solution available |
| `applied` | Cabinet | Cabinet applied solution |
| `resolved` | Cabinet | Issue confirmed fixed |
| `failed` | Either | Could not resolve |
| `human_needed` | Fleet Manager | Requires human intervention |

### 7.2 Fleet Manager AI Workflow

```javascript
async function processEscalation(escalation) {
  // 1. Acknowledge
  await updateEscalationStatus(escalation.id, 'acknowledged');
  
  // 2. Analyze with AI
  await updateEscalationStatus(escalation.id, 'analyzing');
  
  const analysis = await fleetAI.analyze({
    problem: escalation.description,
    localAnalysis: escalation.local_ai_analysis,
    localAttempts: escalation.local_ai_attempts,
    systemInfo: escalation.system_info,
    logs: escalation.logs_snippet,
    
    // Fleet Manager has extra context:
    fleetPatterns: await getFleetPatterns(escalation.category),
    historicalSolutions: await getSimilarSolutions(escalation.title)
  });
  
  // 3. Generate solution
  if (analysis.canSolve) {
    const solution = await fleetAI.generateSolution(analysis);
    
    await supabase
      .from('escalations')
      .update({
        status: 'solution_ready',
        solution: solution,
        resolution_notes: analysis.explanation
      })
      .eq('id', escalation.id);
    
    // Also send via command queue for faster delivery
    await sendCommand(escalation.device_id, 'SEND_SOLUTION', {
      ticket_id: escalation.id,
      solution: solution
    });
  } else {
    await updateEscalationStatus(escalation.id, 'human_needed', {
      resolution_notes: analysis.whyHumanNeeded
    });
    notifyOperator(escalation);
  }
}
```

### 7.3 Solution Format

```typescript
interface Solution {
  type: "config_change" | "run_command" | "restart_service" | "download_fix" | "manual_steps";
  
  // For config_change
  config_path?: string;
  changes?: Record<string, any>;
  
  // For run_command
  command?: string;
  
  // For restart_service
  service?: string;
  
  // For download_fix
  url?: string;
  target_path?: string;
  
  // For manual_steps
  steps?: string[];
  
  // Common
  explanation: string;
  confidence: number;  // 0-1
  rollback_possible: boolean;
}
```

---

## 8. Fleet Manager Dashboard Data Queries

### 8.1 Dashboard Overview

```javascript
async function getDashboardData() {
  const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
  const today = new Date().toISOString().split('T')[0];
  
  // Get all devices
  const { data: devices } = await supabase
    .from('devices')
    .select('*')
    .order('last_seen', { ascending: false });
  
  // Count online/offline
  const online = devices.filter(d => new Date(d.last_seen) > new Date(tenMinutesAgo));
  const offline = devices.filter(d => new Date(d.last_seen) <= new Date(tenMinutesAgo));
  
  // Get pending escalations
  const { data: escalations } = await supabase
    .from('escalations')
    .select('*')
    .in('status', ['pending', 'acknowledged', 'analyzing']);
  
  // Get today's AI costs
  const { data: aiEvents } = await supabase
    .from('telemetry')
    .select('payload')
    .eq('code', 'AI_USAGE')
    .gte('created_at', today);
  
  const aiCostCents = aiEvents.reduce((sum, e) => sum + (e.payload?.cost_cents || 0), 0);
  
  return {
    devices: {
      total: devices.length,
      online: online.length,
      offline: offline.length,
      list: devices
    },
    escalations: {
      pending: escalations.length,
      list: escalations
    },
    aiCosts: {
      todayCents: aiCostCents,
      todayDollars: (aiCostCents / 100).toFixed(2)
    }
  };
}
```

### 8.2 Device Detail View

```javascript
async function getDeviceDetail(deviceId) {
  // Get device
  const { data: device } = await supabase
    .from('devices')
    .select('*')
    .eq('id', deviceId)
    .single();
  
  // Get recent telemetry
  const { data: telemetry } = await supabase
    .from('telemetry')
    .select('*')
    .eq('device_id', deviceId)
    .order('created_at', { ascending: false })
    .limit(100);
  
  // Get pending commands
  const { data: commands } = await supabase
    .from('command_queue')
    .select('*')
    .eq('device_id', deviceId)
    .in('status', ['pending', 'processing'])
    .order('created_at', { ascending: false });
  
  // Get escalation history
  const { data: escalations } = await supabase
    .from('escalations')
    .select('*')
    .eq('device_id', deviceId)
    .order('created_at', { ascending: false })
    .limit(20);
  
  // Calculate AI costs for this device (this month)
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);
  
  const { data: aiEvents } = await supabase
    .from('telemetry')
    .select('payload')
    .eq('device_id', deviceId)
    .eq('code', 'AI_USAGE')
    .gte('created_at', monthStart.toISOString());
  
  const monthlyAiCost = aiEvents.reduce((sum, e) => sum + (e.payload?.cost_cents || 0), 0);
  
  return {
    device,
    telemetry,
    commands,
    escalations,
    stats: {
      monthlyAiCostCents: monthlyAiCost
    }
  };
}
```

---

## 9. Update Deployment Flow

### 9.1 Push Update to Single Cabinet

```javascript
async function deployUpdateToCabinet(deviceId, bundleUrl, version) {
  // 1. Set device status
  await supabase
    .from('devices')
    .update({ status: 'updating' })
    .eq('id', deviceId);
  
  // 2. Send download command
  const downloadCmd = await sendCommand(deviceId, 'DOWNLOAD_UPDATE', {
    bundle_url: bundleUrl,
    version: version
  });
  
  // 3. Wait for download
  const downloadResult = await waitForCommand(downloadCmd, 300000); // 5 min timeout
  
  if (downloadResult.status !== 'done') {
    throw new Error('Download failed: ' + JSON.stringify(downloadResult.result));
  }
  
  // 4. Send apply command (AI-assisted)
  const applyCmd = await sendCommand(deviceId, 'APPLY_UPDATE', {
    bundle_id: downloadResult.result.bundle_id,
    ai_assisted: true
  });
  
  // 5. Wait for apply
  const applyResult = await waitForCommand(applyCmd, 600000); // 10 min timeout
  
  // 6. Update device status
  await supabase
    .from('devices')
    .update({ 
      status: applyResult.status === 'done' ? 'online' : 'maintenance',
      version: applyResult.status === 'done' ? version : undefined
    })
    .eq('id', deviceId);
  
  return applyResult;
}
```

### 9.2 Fleet-Wide Rollout

```javascript
async function deployUpdateToFleet(bundleUrl, version, options = {}) {
  const { 
    batchSize = 5,           // Cabinets at a time
    delayBetweenBatches = 60000,  // 1 minute between batches
    skipOffline = true
  } = options;
  
  // Get all devices
  let query = supabase.from('devices').select('id, name, status');
  if (skipOffline) {
    const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    query = query.gte('last_seen', tenMinutesAgo);
  }
  
  const { data: devices } = await query;
  
  const results = [];
  
  // Process in batches
  for (let i = 0; i < devices.length; i += batchSize) {
    const batch = devices.slice(i, i + batchSize);
    
    console.log(`Deploying to batch ${i/batchSize + 1}: ${batch.map(d => d.name).join(', ')}`);
    
    const batchResults = await Promise.allSettled(
      batch.map(device => deployUpdateToCabinet(device.id, bundleUrl, version))
    );
    
    results.push(...batchResults.map((r, idx) => ({
      device: batch[idx].name,
      success: r.status === 'fulfilled',
      result: r.status === 'fulfilled' ? r.value : r.reason.message
    })));
    
    // Wait before next batch
    if (i + batchSize < devices.length) {
      await new Promise(r => setTimeout(r, delayBetweenBatches));
    }
  }
  
  return {
    total: devices.length,
    succeeded: results.filter(r => r.success).length,
    failed: results.filter(r => !r.success).length,
    details: results
  };
}
```

---

## 10. Environment Variables Reference

### 10.1 Fleet Manager Needs

```bash
# Supabase connection (required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...  # Service role key for admin operations
SUPABASE_ANON_KEY=eyJ...     # For realtime subscriptions

# AI configuration (if using Claude for Fleet Manager AI)
ANTHROPIC_API_KEY=sk-ant-...
FLEET_AI_MODEL=claude-3-5-sonnet-20241022  # Smarter model for fleet-level analysis

# Optional
FLEET_MANAGER_PORT=3000
LOG_LEVEL=info
```

### 10.2 Cabinet Has (For Reference)

```bash
AA_DRIVE_ROOT=A:\Arcade Assistant Local
AA_DEVICE_ID=<auto-generated-uuid>
AA_VERSION=1.2.0

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...  # Optional

AA_AUTO_TRIVIA=1
AA_AI_DAILY_BUDGET_CENTS=100
AA_UPDATES_ENABLED=0  # Disabled by default for safety
```

---

## 11. Security Checklist

```
□ Service role key is NEVER exposed to frontend
□ Cabinets use anon key (limited permissions)
□ Row Level Security (RLS) enabled on all tables
□ Cabinets can only read/write their own data
□ Command whitelist enforced on cabinet
□ Update bundles validated before apply
□ All communications over HTTPS
```

### 11.1 RLS Policies

```sql
-- Devices: Cabinets can only update their own record
CREATE POLICY "Cabinets update own device" ON devices
  FOR UPDATE USING (id = auth.uid()::uuid);

-- Telemetry: Cabinets can only insert their own events
CREATE POLICY "Cabinets insert own telemetry" ON telemetry
  FOR INSERT WITH CHECK (device_id = auth.uid()::uuid);

-- Commands: Cabinets can only read/update their own commands
CREATE POLICY "Cabinets read own commands" ON command_queue
  FOR SELECT USING (device_id = auth.uid()::uuid);

CREATE POLICY "Cabinets update own commands" ON command_queue
  FOR UPDATE USING (device_id = auth.uid()::uuid);

-- Fleet Manager (service role) bypasses RLS
```

---

## 12. Recommended Tech Stack

### 12.1 For Desktop App

| Option | Pros | Cons |
|--------|------|------|
| **Electron + React** | Familiar, cross-platform, rich ecosystem | Larger bundle size |
| **Tauri + React** | Smaller, faster, Rust-based | Newer, smaller ecosystem |
| **Flutter Desktop** | Single codebase for mobile too | Dart learning curve |

### 12.2 Recommended Libraries

```json
{
  "dependencies": {
    "@supabase/supabase-js": "^2.x",
    "react": "^18.x",
    "recharts": "^2.x",          // For dashboard charts
    "@tanstack/react-query": "^5.x",  // For data fetching
    "date-fns": "^3.x",          // For date handling
    "zustand": "^4.x"            // For state management
  }
}
```

---

## 13. Testing Your Integration

### 13.1 Connectivity Test

```javascript
async function testConnection() {
  try {
    const { data, error } = await supabase.from('devices').select('count');
    if (error) throw error;
    console.log('✅ Supabase connection OK');
    return true;
  } catch (e) {
    console.error('❌ Supabase connection failed:', e);
    return false;
  }
}
```

### 13.2 Command Queue Test

```javascript
async function testCommandQueue(testDeviceId) {
  // Send ping command
  const cmdId = await sendCommand(testDeviceId, 'PING', {});
  console.log('📤 Sent PING command:', cmdId);
  
  // Wait for response
  const result = await waitForCommand(cmdId, 30000);
  console.log('📥 Response:', result);
  
  return result.status === 'done';
}
```

### 13.3 Realtime Test

```javascript
async function testRealtime() {
  return new Promise((resolve) => {
    const channel = supabase
      .channel('test')
      .on('postgres_changes',
        { event: '*', schema: 'public', table: 'devices' },
        () => {
          console.log('✅ Realtime working');
          channel.unsubscribe();
          resolve(true);
        }
      )
      .subscribe();
    
    // Timeout after 10s
    setTimeout(() => {
      channel.unsubscribe();
      console.log('❌ Realtime timeout');
      resolve(false);
    }, 10000);
  });
}
```

---

## 14. Common Gotchas

### 14.1 Time Zones

All timestamps are **UTC**. Convert for display:

```javascript
import { formatDistanceToNow } from 'date-fns';

function formatLastSeen(isoString) {
  return formatDistanceToNow(new Date(isoString), { addSuffix: true });
  // → "5 minutes ago"
}
```

### 14.2 Heartbeat Jitter

Cabinets add ±30s jitter to heartbeats. Don't assume exactly 5-minute intervals.

### 14.3 Offline Detection

Use **10 minutes** as the threshold for "offline", not 5:

```javascript
const OFFLINE_THRESHOLD_MS = 10 * 60 * 1000;
```

### 14.4 Command Expiration

Always set `expires_at` on commands. Stale commands are ignored:

```javascript
expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
```

---

## 15. Support Contact

If the Fleet Manager AI needs clarification on cabinet behavior, it can read:

- `docs/FLEET_MANAGER_HANDOFF.md` - General architecture
- `docs/FLEET_MANAGER_INTEGRATION_SPEC.md` - This document
- `backend/services/supabase_client.py` - How cabinet talks to Supabase
- `backend/services/escalation_service.py` - Escalation protocol implementation
- `backend/routers/updates.py` - Update protocol implementation

---

*End of Fleet Manager Integration Specification*
