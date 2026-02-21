# Supabase Edge Functions Deployment Guide

## Overview
This guide covers deploying the missing Edge Functions (`anthropic-proxy` and `elevenlabs-proxy`) to fix Chuck and Dewey AI/TTS functionality.

## Prerequisites

### 1. Install Supabase CLI

**Windows (PowerShell)**:
```powershell
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase
```

**Or use npm**:
```bash
npm install -g supabase
```

**Verify installation**:
```bash
supabase --version
```

### 2. Login to Supabase

```bash
supabase login
```

This will open a browser window for authentication.

### 3. Link to Your Project

```bash
cd "a:\Arcade Assistant Local"
supabase link --project-ref zlkhsxacfyxsctqpvbsh
```

(Your project ref is from the Supabase URL: `https://zlkhsxacfyxsctqpvbsh.supabase.co`)

## Deployment Steps

### Step 1: Set Supabase Secrets

Before deploying, set the API keys as Supabase secrets (NOT in .env):

```bash
# Set Anthropic API key
supabase secrets set ANTHROPIC_API_KEY=sk-ant-YOUR-REAL-KEY-HERE

# Set ElevenLabs API key
supabase secrets set ELEVENLABS_API_KEY=YOUR-REAL-KEY-HERE
```

**Verify secrets are set**:
```bash
supabase secrets list
```

### Step 2: Deploy Edge Functions

Deploy both functions:

```bash
# Deploy Anthropic proxy
supabase functions deploy anthropic-proxy

# Deploy ElevenLabs proxy
supabase functions deploy elevenlabs-proxy
```

**Or deploy all functions at once**:
```bash
supabase functions deploy
```

### Step 3: Verify Deployment

Test the functions are live:

```bash
# Test Anthropic proxy (should return 400 - missing messages)
curl https://zlkhsxacfyxsctqpvbsh.supabase.co/functions/v1/anthropic-proxy

# Test ElevenLabs proxy (should return 400 - missing text)
curl https://zlkhsxacfyxsctqpvbsh.supabase.co/functions/v1/elevenlabs-proxy
```

If you get 404, the function isn't deployed yet.
If you get 400, the function is deployed and working (just needs valid input).

### Step 4: Test with Real Request

Test Anthropic proxy with valid request:

```bash
curl -X POST https://zlkhsxacfyxsctqpvbsh.supabase.co/functions/v1/anthropic-proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_SUPABASE_ANON_KEY" \
  -d '{
    "messages": [
      {"role": "user", "content": "Say hello"}
    ]
  }'
```

Expected response:
```json
{
  "message": {
    "role": "assistant",
    "content": "Hello! ..."
  },
  "usage": { ... },
  "model": "claude-3-5-sonnet-20241022"
}
```

## Testing in Application

### 1. Restart Gateway

After deployment, restart your dev stack to pick up the new functions:

```bash
# Stop current dev stack (Ctrl+C)
npm run dev
```

### 2. Test Chuck Chat

1. Navigate to Controller Chuck panel
2. Open chat sidebar (💬 icon)
3. Send a message: "Hello Chuck!"
4. **Expected**: Intelligent response from Claude (not generic fallback)

### 3. Test Dewey Voice

1. Navigate to Dewey panel
2. Enable voice
3. Ask Dewey a question
4. **Expected**: Natural voice from ElevenLabs (not robotic browser TTS)

## Troubleshooting

### Issue: 501 Not Configured

**Symptom**: Functions return `{"error": "..API key not configured..", "code": "NOT_CONFIGURED"}`

**Cause**: Secrets not set in Supabase

**Fix**:
```bash
supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
supabase secrets set ELEVENLABS_API_KEY=...
```

### Issue: 404 Not Found

**Symptom**: `curl` returns 404 for function URL

**Cause**: Function not deployed

**Fix**:
```bash
supabase functions deploy anthropic-proxy
supabase functions deploy elevenlabs-proxy
```

### Issue: 401 Unauthorized

**Symptom**: Request returns unauthorized error

**Cause**: Missing/invalid Supabase anon key in request

**Fix**: Add `Authorization: Bearer <SUPABASE_ANON_KEY>` header

### Issue: Still Getting Fallback Responses

**Symptom**: Chuck still gives generic responses after deployment

**Possible causes**:
1. Gateway not restarted (restart `npm run dev`)
2. Browser cache (hard refresh with Ctrl+Shift+R)
3. Edge Functions deployed but secrets not set
4. Check browser console for actual error

## Monitoring

### View Edge Function Logs

```bash
supabase functions logs anthropic-proxy
supabase functions logs elevenlabs-proxy
```

### Check Function Status

```bash
supabase functions list
```

Should show:
```
┌─────────────────────┬──────────┬─────────────────┐
│ NAME                │ STATUS   │ UPDATED         │
├─────────────────────┼──────────┼─────────────────┤
│ anthropic-proxy     │ ACTIVE   │ 2025-12-30 ... │
│ elevenlabs-proxy    │ ACTIVE   │ 2025-12-30 ... │
│ register_device     │ ACTIVE   │ ...            │
│ send_command        │ ACTIVE   │ ...            │
│ sign_url            │ ACTIVE   │ ...            │
└─────────────────────┴──────────┴─────────────────┘
```

## Cost Considerations

### Anthropic API
- ~$3 per 1M input tokens
- ~$15 per 1M output tokens
- Chuck uses ~500 tokens per chat message

### ElevenLabs API
- Free tier: 10,000 characters/month
- Paid: $5/month for 30,000 characters
- Average voice response: 100-200 characters

**Recommendation**: Set up usage alerts in both services.

## Security Notes

1. **Never commit real API keys** to `.env` files (use placeholders only)
2. **Always use Supabase secrets** for production API keys
3. **Rotate keys regularly** via Supabase dashboard
4. **Monitor usage** to detect unauthorized access

## Files Created

- `supabase/functions/anthropic-proxy/index.ts` - AI chat proxy
- `supabase/functions/elevenlabs-proxy/index.ts` - TTS proxy

## Related Documentation

- **Architecture**: See README.md "AI/TTS Chat" section
- **Supabase Docs**: https://supabase.com/docs/guides/functions
- **Anthropic API**: https://docs.anthropic.com/
- **ElevenLabs API**: https://elevenlabs.io/docs

---

**Last Updated**: 2025-12-30
**Status**: Edge Functions created, awaiting deployment
