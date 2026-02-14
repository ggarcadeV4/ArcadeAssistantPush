# Supabase Setup Guide - Arcade Assistant

Complete step-by-step guide to set up live Supabase cloud integration with RLS, tables, clients, and environment configuration.

**Estimated Time**: 30-45 minutes
**Prerequisites**: Supabase account, Supabase CLI installed

---

## Step 1: Create Supabase Project (5 min)

### 1.1 Create New Project

1. Go to [supabase.com](https://supabase.com)
2. Click **"New Project"**
3. Configure:
   - **Name**: `arcade-assistant-prod`
   - **Database Password**: Generate strong password (save it!)
   - **Region**: Choose closest to your location
   - **Pricing Plan**: Start with Free tier
4. Click **"Create new project"**
5. Wait 2-3 minutes for provisioning

### 1.2 Get API Credentials

Once project is ready:

1. Click **"Settings"** (⚙️ icon in sidebar)
2. Go to **"API"** section
3. Copy these values (you'll need them later):
   ```
   Project URL: https://xxxxxxxxxxxxx.supabase.co
   anon/public key: eyJhbGc...
   service_role key: eyJhbGc... (keep secret!)
   ```

---

## Step 2: Run SQL Schema (5 min)

### 2.1 Open SQL Editor

1. In Supabase dashboard, click **"SQL Editor"** in sidebar
2. Click **"New query"**

### 2.2 Execute Schema

1. Open `supabase/schema.sql` from your project
2. Copy entire file contents
3. Paste into SQL Editor
4. Click **"Run"** (or press Ctrl+Enter)
5. Wait for completion (~30 seconds)

**Expected Output:**
```
NOTICE: Arcade Assistant Supabase schema deployed successfully!
NOTICE: Tables created: devices, commands, telemetry, scores, user_tendencies, led_configs, led_maps
```

### 2.3 Verify Tables

1. Click **"Table Editor"** in sidebar
2. You should see 7 tables:
   - `devices`
   - `commands`
   - `telemetry`
   - `scores`
   - `user_tendencies`
   - `led_configs`
   - `led_maps`

---

## Step 3: Create Storage Buckets (3 min)

### 3.1 Create Updates Bucket

1. Click **"Storage"** in sidebar
2. Click **"New bucket"**
3. Configure:
   - **Name**: `updates`
   - **Public**: ❌ **OFF** (must be private)
   - **Allowed MIME types**: Leave default
4. Click **"Create bucket"**

### 3.2 Create Assets Bucket

1. Click **"New bucket"** again
2. Configure:
   - **Name**: `assets`
   - **Public**: ❌ **OFF** (must be private)
3. Click **"Create bucket"**

### 3.3 Verify Buckets

You should see two private buckets:
- 🔒 `updates`
- 🔒 `assets`

---

## Step 4: Deploy Edge Functions (10-15 min)

### 4.1 Install Supabase CLI

If not already installed:

```bash
# Windows (PowerShell)
scoop install supabase

# macOS
brew install supabase/tap/supabase

# Linux
curl -sL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.tar.gz | tar -xz
sudo mv supabase /usr/local/bin/
```

Verify installation:
```bash
supabase --version
```

### 4.2 Login to Supabase

```bash
supabase login
```

Follow browser prompt to authenticate.

### 4.3 Link Project

```bash
cd "C:\Users\Dad's PC\Desktop\Arcade Assistant Local"
supabase link --project-ref xxxxxxxxxxxxx
```

Replace `xxxxxxxxxxxxx` with your project reference (found in Project Settings → General).

### 4.4 Set Secrets

```bash
supabase secrets set SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
```

Replace values with your actual credentials from Step 1.2.

### 4.5 Deploy Functions

Deploy all three Edge Functions:

```bash
# Deploy register_device
supabase functions deploy register_device

# Deploy send_command
supabase functions deploy send_command

# Deploy sign_url
supabase functions deploy sign_url
```

Each deployment takes ~30 seconds.

### 4.6 Verify Functions

1. Go to **"Edge Functions"** in Supabase dashboard
2. You should see 3 functions:
   - ✅ `register_device`
   - ✅ `send_command`
   - ✅ `sign_url`

---

## Step 5: Update Environment Variables (5 min)

### 5.1 Update .env File

1. Copy `.env.example` to `.env` (if not already done):
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and update Supabase section:
   ```env
   # =============================
   # Supabase Cloud Integration
   # =============================
   SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJhbGc...your-anon-key...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...your-service-role-key...
   ```

3. Save file

### 5.2 Update Gateway .env

If you have a separate gateway .env:

```bash
cd gateway
cp .env.example .env
# Edit and add same Supabase variables
```

---

## Step 6: Install Dependencies (3 min)

### 6.1 Backend Dependencies

```bash
cd backend
pip install supabase>=2.0.0
# Or add to requirements.txt and run:
pip install -r requirements.txt
```

### 6.2 Gateway Dependencies

```bash
cd gateway
npm install @supabase/supabase-js
```

---

## Step 7: Test Connectivity (5 min)

### 7.1 Start Backend

```bash
cd "C:\Users\Dad's PC\Desktop\Arcade Assistant Local"
npm run dev:backend
```

Wait for backend to start (~5 seconds).

### 7.2 Test Backend Health

Open new terminal:

```bash
curl http://localhost:8888/api/supabase/health
```

**Expected Response:**
```json
{
  "status": "connected",
  "supabase": true
}
```

If you get `"status": "disconnected"`, check:
- `.env` file has correct `SUPABASE_URL` and `SUPABASE_ANON_KEY`
- Backend was restarted after updating `.env`
- Supabase project is running (check dashboard)

### 7.3 Test Backend Status

```bash
curl http://localhost:8888/api/supabase/status
```

**Expected Response:**
```json
{
  "configured": true,
  "url_set": true,
  "key_set": true
}
```

### 7.4 Start Gateway

```bash
npm run dev:gateway
```

### 7.5 Test Gateway (Optional)

If you added Supabase routes to gateway:

```bash
curl http://localhost:8787/api/supabase/health
```

---

## Step 8: Test Edge Functions (5 min)

### 8.1 Test Device Registration

```bash
curl -X POST https://xxxxxxxxxxxxx.supabase.co/functions/v1/register_device \
  -H "Authorization: Bearer your-anon-key" \
  -H "Content-Type: application/json" \
  -d '{
    "serial": "TEST-CABINET-001",
    "owner_id": "00000000-0000-0000-0000-000000000000"
  }'
```

**Expected Response:**
```json
{
  "device_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "serial": "TEST-CABINET-001",
  "is_new": true
}
```

### 8.2 Verify Device in Database

1. Go to **"Table Editor"** → **"devices"** table
2. You should see one row with serial `TEST-CABINET-001`

### 8.3 Test Command Queue

```bash
curl -X POST https://xxxxxxxxxxxxx.supabase.co/functions/v1/send_command \
  -H "Authorization: Bearer your-service-role-key" \
  -H "Content-Type: application/json" \
  -d '{
    "commands": [{
      "device_id": "your-device-id-from-previous-step",
      "type": "MESSAGE",
      "payload": {"text": "Hello from Edge Function!"}
    }]
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "count": 1,
  "command_ids": ["xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"]
}
```

---

## Step 9: Test Python Client (3 min)

### 9.1 Create Test Script

Create `test_supabase.py`:

```python
from backend.services import supabase_client

# Test health check
print("Testing Supabase connectivity...")
if supabase_client.health_check():
    print("✅ Connected to Supabase!")

    # Test telemetry
    device_id = "your-device-id-here"
    success = supabase_client.send_telemetry(
        device_id=device_id,
        level="INFO",
        code="TEST",
        message="Test from Python client"
    )

    if success:
        print("✅ Telemetry sent successfully!")
    else:
        print("❌ Telemetry failed")
else:
    print("❌ Could not connect to Supabase")
    print("Check .env configuration")
```

### 9.2 Run Test

```bash
python test_supabase.py
```

**Expected Output:**
```
Testing Supabase connectivity...
✅ Connected to Supabase!
✅ Telemetry sent successfully!
```

---

## Step 10: Verify Complete Setup

### Checklist

- ✅ Supabase project created and running
- ✅ 7 tables created with RLS enabled
- ✅ 2 storage buckets created (updates, assets)
- ✅ 3 Edge Functions deployed
- ✅ `.env` file updated with credentials
- ✅ Backend dependencies installed
- ✅ Gateway dependencies installed
- ✅ Backend health check passes
- ✅ Edge Functions respond correctly
- ✅ Python client can connect and send telemetry

---

## Troubleshooting

### Issue: "Could not connect to Supabase"

**Solutions:**
1. Check `.env` file has correct `SUPABASE_URL` and `SUPABASE_ANON_KEY`
2. Restart backend: `npm run dev:backend`
3. Verify Supabase project is active in dashboard
4. Check firewall/proxy settings

### Issue: "RLS policy violation"

**Solutions:**
1. Verify RLS policies were created (Step 2)
2. Check you're using correct key (anon for client, service_role for admin)
3. Re-run schema.sql if policies are missing

### Issue: Edge Function "Not Found"

**Solutions:**
1. Verify function deployed: `supabase functions list`
2. Check function name matches exactly (case-sensitive)
3. Re-deploy function: `supabase functions deploy <function-name>`

### Issue: "Module not found: supabase"

**Solutions:**
1. Install Python package: `pip install supabase>=2.0.0`
2. Verify virtual environment is activated
3. Check `backend/requirements.txt` includes supabase

### Issue: "Invalid JWT" or "Invalid API key"

**Solutions:**
1. Double-check API keys in `.env` (no extra spaces/quotes)
2. Use anon key for client operations
3. Use service_role key for admin operations (Edge Functions only)
4. Regenerate keys if compromised (Project Settings → API)

---

## Next Steps

Now that Supabase is configured, you can:

1. **Integrate Dewey Panel** - Load/save user profiles from `user_tendencies` table
2. **Add ScoreKeeper** - Persist tournament scores to `scores` table
3. **LED Sync** - Save LED configurations to `led_configs` and `led_maps`
4. **Device Registration** - Register cabinet on first boot
5. **Telemetry** - Stream logs to Supabase for monitoring
6. **Command Queue** - Poll and execute remote commands

See `docs/SUPABASE_GUARDRAILS.md` for integration patterns and best practices.

---

## Security Reminders

- ✅ **NEVER commit `.env` to git** - Already in `.gitignore`
- ✅ **NEVER expose `SUPABASE_SERVICE_ROLE_KEY`** - Backend/Edge Functions only
- ✅ **Use `SUPABASE_ANON_KEY` for client-side** - Safe for frontend
- ✅ **RLS policies protect all tables** - Even with leaked anon key, devices can only access their own data
- ✅ **Rotate keys if compromised** - Generate new keys in Project Settings → API

---

## Support

- **Supabase Docs**: https://supabase.com/docs
- **Edge Functions Guide**: https://supabase.com/docs/guides/functions
- **CLI Reference**: https://supabase.com/docs/reference/cli
- **Arcade Assistant Docs**: `docs/SUPABASE_GUARDRAILS.md`
