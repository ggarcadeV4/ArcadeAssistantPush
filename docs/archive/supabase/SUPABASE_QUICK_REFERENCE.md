# Supabase Quick Reference Card

**Arcade Assistant - Cloud Integration**

---

## 🔑 Environment Variables

```env
# .env file
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...    # Safe for clients
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...  # Backend/Edge Functions only
```

---

## 📊 Database Tables

| Table | Purpose | RLS |
|-------|---------|-----|
| `devices` | Cabinet registration and status | ✅ Device-scoped |
| `commands` | Command queue for remote actions | ✅ Device-scoped |
| `telemetry` | Application logs and events | ✅ Device-scoped |
| `scores` | Tournament leaderboards | ✅ Public read |
| `user_tendencies` | Player profiles and preferences | ✅ Device-scoped |
| `led_configs` | LED Blinky patterns | ✅ Device-scoped |
| `led_maps` | Game-specific LED mappings | ✅ Device-scoped |

---

## 🐍 Python Client Usage

```python
from backend.services import supabase_client

# Health check
if supabase_client.health_check():
    print("✅ Connected!")

# Send telemetry
supabase_client.send_telemetry(
    device_id="cabinet-uuid",
    level="INFO",
    code="GAME_LAUNCHED",
    message="Street Fighter II started"
)

# Update heartbeat (auto rate-limited to 5 min)
supabase_client.update_device_heartbeat("cabinet-uuid")

# Fetch commands
commands = supabase_client.fetch_new_commands("cabinet-uuid")
for cmd in commands:
    # Process command...
    supabase_client.update_command_status(
        cmd["id"],
        "DONE",
        {"result": "success"}
    )

# Insert score
supabase_client.insert_score(
    device_id="cabinet-uuid",
    game_id="sf2",
    player="Dad",
    score=1250000
)
```

---

## 🟢 Node.js Client Usage

```javascript
const supabase = require('./gateway/services/supabase_client');

// Health check
const isHealthy = await supabase.healthCheck();

// Send telemetry
await supabase.sendTelemetry(
    'cabinet-uuid',
    'INFO',
    'GAME_LAUNCHED',
    'Street Fighter II started'
);

// Update heartbeat
await supabase.updateHeartbeat('cabinet-uuid');

// Get user tendencies
const tendencies = await supabase.getUserTendencies('cabinet-uuid', 'dad');

// Save user tendencies
await supabase.saveUserTendencies('cabinet-uuid', 'dad', {
    preferences: { genres: ['fighting', 'arcade'] },
    play_history: ['sf2', 'mk2'],
    favorites: ['sf2']
});
```

---

## 🔌 API Endpoints

### Backend Endpoints

```bash
# Health check
GET http://localhost:8888/api/supabase/health
→ {"status": "connected", "supabase": true}

# Configuration status
GET http://localhost:8888/api/supabase/status
→ {"configured": true, "url_set": true, "key_set": true}

# Ping
GET http://localhost:8888/api/supabase/ping
→ {"status": "ok", "endpoints": [...]}
```

---

## ⚡ Edge Functions

### Register Device

```bash
curl -X POST https://xxxxx.supabase.co/functions/v1/register_device \
  -H "Authorization: Bearer <anon-key>" \
  -H "Content-Type: application/json" \
  -d '{"serial": "CAB-001", "owner_id": "user-uuid"}'
```

Response:
```json
{
  "device_id": "device-uuid",
  "serial": "CAB-001",
  "is_new": true
}
```

### Send Command

```bash
curl -X POST https://xxxxx.supabase.co/functions/v1/send_command \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "commands": [{
      "device_id": "device-uuid",
      "type": "MESSAGE",
      "payload": {"text": "Hello!"}
    }]
  }'
```

### Sign URL

```bash
curl -X POST https://xxxxx.supabase.co/functions/v1/sign_url \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{"bucket": "updates", "path": "1.0.0/patch.zip"}'
```

---

## 🗂️ Storage Buckets

| Bucket | Purpose | Public |
|--------|---------|--------|
| `updates` | Patch bundles by version | ❌ Private |
| `assets` | Marquee art, screenshots | ❌ Private |

Access via signed URLs only.

---

## 🧪 Testing Commands

```bash
# Test Python client
python -c "from backend.services import supabase_client; print(supabase_client.health_check())"

# Test backend endpoint
curl http://localhost:8888/api/supabase/health

# Test Edge Function
curl https://xxxxx.supabase.co/functions/v1/register_device \
  -H "Authorization: Bearer <anon-key>" \
  -H "Content-Type: application/json" \
  -d '{"serial": "TEST-001", "owner_id": "00000000-0000-0000-0000-000000000000"}'
```

---

## 🛠️ CLI Commands

```bash
# Login
supabase login

# Link project
supabase link --project-ref <project-id>

# Set secrets
supabase secrets set SUPABASE_URL=https://...
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=...

# Deploy function
supabase functions deploy register_device

# List functions
supabase functions list

# View logs
supabase functions logs register_device

# Run SQL
supabase db push
```

---

## 🔒 Security Rules

✅ **DO:**
- Use `SUPABASE_ANON_KEY` for client operations
- Use `SUPABASE_SERVICE_ROLE_KEY` for Edge Functions/admin only
- Rely on RLS policies for access control
- Use signed URLs for storage access

❌ **DON'T:**
- Expose service role key to clients
- Commit API keys to git (use `.env`)
- Bypass RLS in client code
- Make storage buckets public

---

## 📁 File Locations

```
backend/
├── services/
│   └── supabase_client.py        # Python client
└── routers/
    └── supabase_health.py         # Health check API

gateway/
└── services/
    └── supabase_client.js         # Node.js client

supabase/
├── schema.sql                     # Complete DB schema
└── functions/
    ├── register_device/index.ts
    ├── send_command/index.ts
    └── sign_url/index.ts

.env                               # Environment variables (not committed)
.env.example                       # Template with placeholders
```

---

## 🆘 Troubleshooting

### "Could not connect to Supabase"
1. Check `.env` has correct `SUPABASE_URL` and `SUPABASE_ANON_KEY`
2. Restart backend: `npm run dev:backend`
3. Verify project is active in Supabase dashboard

### "RLS policy violation"
1. Check you're using correct key (anon vs service_role)
2. Verify policies exist: re-run `supabase/schema.sql`
3. Check device_id matches JWT claim

### "Module not found: supabase"
1. Backend: `pip install supabase>=2.0.0`
2. Gateway: `npm install @supabase/supabase-js`

### "Edge Function not found"
1. Verify deployment: `supabase functions list`
2. Re-deploy: `supabase functions deploy <function-name>`

---

## 📚 Documentation

- **Full Setup Guide**: `SUPABASE_SETUP_GUIDE.md`
- **Architecture Details**: `docs/SUPABASE_GUARDRAILS.md`
- **Supabase Docs**: https://supabase.com/docs
- **Edge Functions Guide**: https://supabase.com/docs/guides/functions

---

## 🎯 Common Tasks

### Add New Device
```python
# Use Edge Function or direct insert with service role
```

### Poll Commands
```python
commands = supabase_client.fetch_new_commands(device_id)
for cmd in commands:
    # Execute command
    supabase_client.update_command_status(cmd['id'], 'DONE')
```

### Log Event
```python
supabase_client.send_telemetry(
    device_id, 'INFO', 'EVENT_CODE', 'Message'
)
```

### Update User Preferences
```javascript
await supabase.saveUserTendencies(deviceId, userId, {
    preferences: {...},
    play_history: [...],
    favorites: [...]
});
```

---

**Last Updated**: 2025-10-27
**Version**: 1.0.0
