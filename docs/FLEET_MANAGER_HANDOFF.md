# 🎮 Arcade Assistant Fleet Manager — Handoff Document

**Version:** 1.0.0  
**Date:** December 13, 2025  
**Purpose:** Complete technical handoff for building the Fleet Manager desktop application

---

## 1. Executive Summary

The Arcade Assistant is a **duplicatable drive image** that powers arcade cabinets. Each cabinet runs independently but reports to a central **Fleet Manager** on your desktop via Supabase.

This document provides everything needed to build the Fleet Manager that:
- Monitors all cabinets in real-time
- Pushes updates to the fleet
- Manages device registration and naming
- Tracks usage, costs, and health across all units

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     YOUR DESKTOP                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              FLEET MANAGER APP                           │   │
│  │  - Dashboard showing all cabinets                        │   │
│  │  - Push updates to fleet                                 │   │
│  │  - View telemetry and health                             │   │
│  │  - Manage device names and serials                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│                    ┌──────────────┐                             │
│                    │   SUPABASE   │ ◄── Cloud Hub               │
│                    └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  CABINET #1  │    │  CABINET #2  │    │  CABINET #N  │
│  "StarJab"   │    │  "NeoBlast"  │    │  "RetroKing" │
│  Omaha, NE   │    │  Denver, CO  │    │  Austin, TX  │
└──────────────┘    └──────────────┘    └──────────────┘
     A: Drive            A: Drive            A: Drive
   (duplicated)        (duplicated)        (duplicated)
```

---

## 3. Supabase Schema (Already Deployed)

### 3.1 `devices` Table

```sql
CREATE TABLE devices (
  id UUID PRIMARY KEY,                    -- AA_DEVICE_ID (generated on first boot)
  serial TEXT UNIQUE NOT NULL,            -- AA-YYYYMMDD-XXXXXXXX format
  name TEXT NOT NULL,                     -- User-assigned cabinet name
  status TEXT DEFAULT 'offline',          -- online, offline, maintenance
  version TEXT,                           -- Current AA version
  last_seen TIMESTAMPTZ,                  -- Last heartbeat
  tags JSONB DEFAULT '{}',                -- Hardware info, custom metadata
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Key fields in `tags` JSONB:**
```json
{
  "hostname": "DESKTOP-E4SEJRR",
  "os": "Windows",
  "os_version": "10.0.19045",
  "motherboard_serial": "PF3RXXXXXX",
  "bios_serial": "XXXXXXXX",
  "cpu_id": "BFEBFBFF000906EA",
  "processor": "Intel64 Family 6..."
}
```

### 3.2 `telemetry` Table

```sql
CREATE TABLE telemetry (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id),
  level TEXT NOT NULL,                    -- INFO, WARN, ERROR, CRITICAL
  code TEXT NOT NULL,                     -- Event code (e.g., GAME_LAUNCHED)
  message TEXT,
  payload JSONB DEFAULT '{}',
  tenant_id TEXT DEFAULT 'default',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 `command_queue` Table

```sql
CREATE TABLE command_queue (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id),
  command TEXT NOT NULL,                  -- Command type
  payload JSONB DEFAULT '{}',
  status TEXT DEFAULT 'pending',          -- pending, processing, done, failed
  result JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);
```

### 3.4 `scores` Table

```sql
CREATE TABLE scores (
  id BIGSERIAL PRIMARY KEY,
  device_id UUID REFERENCES devices(id),
  game_id TEXT NOT NULL,
  player TEXT NOT NULL,
  score BIGINT NOT NULL,
  meta JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. Cabinet Lifecycle

### 4.1 First Boot (Provisioning)

When a duplicated drive boots on a new PC for the first time:

1. **No manifest exists** → Frontend shows provisioning overlay
2. **User enters cabinet name** (e.g., "StarJab")
3. **Backend generates:**
   - `device_id`: UUID v4 (unique per cabinet)
   - `serial`: `AA-YYYYMMDD-XXXXXXXX` format
4. **Hardware info captured:**
   - Hostname, motherboard serial, BIOS serial, CPU ID
5. **Saved to:** `.aa/cabinet_manifest.json`
6. **Pushed to Supabase** → Appears in Fleet Manager immediately

**Provisioning API:**
```
GET  /api/local/system/provisioning_status
POST /api/local/system/provision
     Body: { "name": "StarJab" }
     Headers: x-scope: state
```

### 4.2 Heartbeat Loop

Each cabinet sends heartbeats every 5 minutes (±30s jitter):

```python
# backend/app.py - Already implemented
async def _heartbeat_loop():
    while True:
        await update_device_heartbeat(device_id)
        await asyncio.sleep(300 + random.randint(-30, 30))
```

**What's sent:**
- `device_id`
- `status: "online"`
- `last_seen: <timestamp>`
- Current `version`

**Fleet Manager should:**
- Mark devices `offline` if `last_seen > 10 minutes ago`
- Show visual indicator for stale heartbeats

### 4.3 Update Flow

```
Fleet Manager                    Supabase                    Cabinet
     │                              │                           │
     │  1. Upload bundle to         │                           │
     │     storage bucket           │                           │
     │─────────────────────────────►│                           │
     │                              │                           │
     │  2. Insert command:          │                           │
     │     DOWNLOAD_UPDATE          │                           │
     │─────────────────────────────►│                           │
     │                              │                           │
     │                              │  3. Cabinet polls queue   │
     │                              │◄──────────────────────────│
     │                              │                           │
     │                              │  4. Download bundle       │
     │                              │◄──────────────────────────│
     │                              │                           │
     │                              │  5. Stage update          │
     │                              │     (validates manifest)  │
     │                              │                           │
     │                              │  6. Apply update          │
     │                              │     (with backup)         │
     │                              │                           │
     │                              │  7. Report result         │
     │                              │◄──────────────────────────│
```

**Update API on Cabinet:**
```
GET  /api/local/updates/status
POST /api/local/updates/stage      # Stage bundle from inbox
POST /api/local/updates/apply      # Apply staged update
POST /api/local/updates/rollback   # Rollback if needed
```

**Environment flag:** `AA_UPDATES_ENABLED=1` must be set for updates to work.

---

## 5. Key API Endpoints for Fleet Manager

### 5.1 Device Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/local/system/provisioning_status` | GET | Check if cabinet is provisioned |
| `/api/local/system/provision` | POST | Register cabinet (first boot) |
| `/health` | GET | Basic health check |
| `/health/status` | GET | Detailed health with metrics |
| `/api/local/diagnose-all` | GET | "What's wrong?" diagnostic |

### 5.2 Telemetry

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/local/ai/usage` | GET | AI model usage and costs |
| `/api/local/ai/budget` | GET | Budget status |
| `/api/local/tendencies/profile/{id}` | GET | User profile data |

### 5.3 Updates

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/local/updates/status` | GET | Update system status |
| `/api/local/updates/stage` | POST | Stage update bundle |
| `/api/local/updates/apply` | POST | Apply staged update |

---

## 6. Fleet Manager Features to Build

### 6.1 Dashboard

```
┌────────────────────────────────────────────────────────────────┐
│  ARCADE ASSISTANT FLEET MANAGER                    [Settings]  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  FLEET OVERVIEW                              AI COSTS TODAY    │
│  ┌──────────────────────────────────┐      ┌────────────────┐ │
│  │  ● 18 Online   ○ 2 Offline      │      │  $1.47 / $5.00 │ │
│  │  ▲ 1 Needs Update               │      │  [████████░░]  │ │
│  └──────────────────────────────────┘      └────────────────┘ │
│                                                                │
│  CABINETS                                                      │
│  ┌──────────┬──────────┬──────────┬──────────┬───────────────┐│
│  │ Name     │ Serial   │ Status   │ Version  │ Last Seen     ││
│  ├──────────┼──────────┼──────────┼──────────┼───────────────┤│
│  │ StarJab  │ AA-2025..│ ● Online │ 1.2.0    │ 2 min ago     ││
│  │ NeoBlast │ AA-2025..│ ● Online │ 1.2.0    │ 4 min ago     ││
│  │ RetroKing│ AA-2025..│ ○ Offline│ 1.1.0    │ 3 hours ago   ││
│  └──────────┴──────────┴──────────┴──────────┴───────────────┘│
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 6.2 Device Detail View

- Hardware info (motherboard, CPU, etc.)
- Current version and update history
- Recent telemetry events
- AI usage for this device
- Remote commands (restart, push update)

### 6.3 Update Management

- Upload update bundle (.zip with manifest)
- Select target devices (all, by tag, individual)
- Schedule deployment (now, maintenance window)
- Monitor rollout progress
- One-click rollback

### 6.4 Cost Tracking

- Real-time AI costs across fleet
- Daily/weekly/monthly reports
- Per-cabinet breakdown
- Budget alerts

---

## 7. Supabase Queries for Fleet Manager

### 7.1 Get All Devices

```javascript
const { data: devices } = await supabase
  .from('devices')
  .select('*')
  .order('last_seen', { ascending: false });
```

### 7.2 Get Online Devices

```javascript
const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
const { data: online } = await supabase
  .from('devices')
  .select('*')
  .gte('last_seen', tenMinutesAgo);
```

### 7.3 Send Command to Device

```javascript
const { data } = await supabase
  .from('command_queue')
  .insert({
    device_id: 'uuid-here',
    command: 'DOWNLOAD_UPDATE',
    payload: { bundle_url: 'https://...', version: '1.2.1' }
  });
```

### 7.4 Get Device Telemetry

```javascript
const { data: events } = await supabase
  .from('telemetry')
  .select('*')
  .eq('device_id', 'uuid-here')
  .order('created_at', { ascending: false })
  .limit(100);
```

### 7.5 Get Fleet AI Costs (Today)

```javascript
const today = new Date().toISOString().split('T')[0];
const { data } = await supabase
  .from('telemetry')
  .select('payload')
  .eq('code', 'AI_USAGE')
  .gte('created_at', today);

const totalCost = data.reduce((sum, e) => sum + (e.payload?.cost_cents || 0), 0);
```

---

## 8. Environment Variables

### 8.1 On Each Cabinet (.env)

```bash
# Required
AA_DRIVE_ROOT=A:\Arcade Assistant Local

# Generated on first boot
AA_DEVICE_ID=<auto-generated-uuid>

# Supabase connection
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...  # Optional, for admin ops

# Feature flags
AA_AUTO_TRIVIA=1                    # Enable auto-trivia generation
AA_TRIVIA_INTERVAL_HOURS=24         # Daily trivia refresh
AA_UPDATES_ENABLED=0                # Disabled by default (safety)
AA_AI_DAILY_BUDGET_CENTS=100        # Cost cap per cabinet
```

### 8.2 On Fleet Manager

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...         # Service role for admin ops
```

---

## 9. Update Bundle Format

### 9.1 Structure

```
update-1.2.1.zip
├── manifest.json           # Required: version, files, checksums
├── backend/
│   └── ... (delta files)
├── frontend/
│   └── ... (delta files)
└── migrations/
    └── ... (if any)
```

### 9.2 Manifest Schema

```json
{
  "version": "1.2.1",
  "previous_version": "1.2.0",
  "release_notes": "Bug fixes and performance improvements",
  "files": [
    {
      "path": "backend/services/dewey/trivia_generator.py",
      "action": "replace",
      "sha256": "abc123..."
    }
  ],
  "pre_scripts": [],
  "post_scripts": [],
  "rollback_supported": true
}
```

---

## 10. Security Considerations

### 10.1 Already Implemented

- **x-scope headers**: All mutating operations require `x-scope: state` or `x-scope: config`
- **Dry-run first**: Config changes preview before apply
- **Automatic backups**: Every config write creates timestamped backup
- **Audit logging**: All operations logged to `.aa/logs/`
- **Supabase RLS**: Row-level security on all tables

### 10.2 For Fleet Manager

- Use **service role key** only server-side
- Never expose service key to frontend
- Validate update bundles before pushing
- Rate limit command queue inserts
- Monitor for anomalous telemetry patterns

---

## 11. Troubleshooting Guide

### 11.1 Cabinet Not Appearing in Fleet

1. Check provisioning: `GET /api/local/system/provisioning_status`
2. Verify Supabase config in `.env`
3. Check network connectivity
4. Look for errors in `.aa/logs/`

### 11.2 Heartbeat Not Updating

1. Check backend is running
2. Verify `AA_DEVICE_ID` is set
3. Check Supabase connection: `GET /api/local/supabase/health`

### 11.3 Update Not Applying

1. Verify `AA_UPDATES_ENABLED=1`
2. Check bundle is in `.aa/updates/inbox/`
3. Review update logs: `.aa/logs/updates/events.jsonl`

---

## 12. Files Created/Modified This Session

### New Services
- `backend/services/model_router.py` - Smart AI model routing
- `backend/services/tendency_service.py` - Unified user preferences
- `backend/services/dewey/trivia_scheduler.py` - Auto-trivia generation
- `backend/services/dewey/trivia_generator.py` - News-to-trivia conversion

### New Routers
- `backend/routers/model_router.py` - AI routing API
- `backend/routers/tendencies.py` - Tendency file API

### Modified for Fleet
- `backend/routers/provisioning.py` - Added hardware info capture
- `backend/app.py` - Added trivia scheduler, new routers

---

## 13. Recommended Tech Stack for Fleet Manager

### Desktop App
- **Electron** + **React** (cross-platform desktop)
- Or **Tauri** + **React** (smaller, Rust-based)

### Backend (if needed)
- Could be purely client-side hitting Supabase directly
- Or lightweight Express server for sensitive operations

### Real-time Updates
- Supabase Realtime subscriptions for live device status

---

## 14. Next Steps for Fleet Manager Development

1. **Set up Supabase project** with schema from Section 3
2. **Build dashboard UI** showing device list
3. **Implement real-time status** via Supabase subscriptions
4. **Add update management** (upload, deploy, monitor)
5. **Add cost tracking** aggregating AI usage telemetry
6. **Build device detail view** with hardware info
7. **Test with 2-3 cabinets** before full rollout

---

## 15. Contact & Support

This handoff document was generated on December 13, 2025.

The codebase is production-ready for duplication. All imports verified, all services tested.

**Key mantra:** "Click Start and it just works."

---

*End of Fleet Manager Handoff Document*
