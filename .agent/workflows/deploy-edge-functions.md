# Supabase Edge Functions Deployment Workflow

## Overview

This document describes the recommended approach for deploying Supabase Edge Functions for the Arcade Assistant project.

## Recommended Long-Term Solution: GitHub Actions CI/CD

The easiest and most effective long-term solution is **GitHub Actions** for automatic deployment on push. This provides:

- ✅ **Zero manual intervention** - Functions deploy automatically when code changes
- ✅ **Consistent deployments** - Same process every time
- ✅ **Audit trail** - GitHub Actions logs show when/why things deployed
- ✅ **No local auth issues** - Token stored securely in GitHub Secrets

### Setup Steps

1. **Store SUPABASE_ACCESS_TOKEN in GitHub Secrets**
   - Go to: `https://github.com/[your-repo]/settings/secrets/actions`
   - Add `SUPABASE_ACCESS_TOKEN` from your Supabase dashboard

2. **Create `.github/workflows/deploy-edge-functions.yml`**

```yaml
name: Deploy Supabase Edge Functions

on:
  push:
    branches: [main]
    paths:
      - 'supabase/functions/**'
  workflow_dispatch:  # Manual trigger

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: supabase/setup-cli@v1
        with:
          version: latest
      
      - name: Deploy Edge Functions
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
        run: |
          supabase functions deploy gemini-proxy --project-ref zlkhsxacfyxsctqpvbsh
          supabase functions deploy anthropic-proxy --project-ref zlkhsxacfyxsctqpvbsh
          supabase functions deploy elevenlabs-proxy --project-ref zlkhsxacfyxsctqpvbsh
          supabase functions deploy openai-proxy --project-ref zlkhsxacfyxsctqpvbsh
          supabase functions deploy admin-gateway --project-ref zlkhsxacfyxsctqpvbsh
```

### Alternative: Local Deployment Script

For quick local deployments without CLI login issues:

```powershell
# scripts/deploy-functions.ps1
$env:SUPABASE_ACCESS_TOKEN = (Get-Content .env | Where-Object { $_ -match '^SUPABASE_ACCESS_TOKEN=' } | ForEach-Object { $_.Split('=')[1] })
npx supabase functions deploy gemini-proxy --project-ref zlkhsxacfyxsctqpvbsh
```

Store the token in `.env`:
```
SUPABASE_ACCESS_TOKEN=sbp_xxx...
```

## Current Edge Functions

| Function | Purpose | Last Updated |
|----------|---------|--------------|
| `gemini-proxy` | Gemini AI with function calling | 2026-01-04 |
| `anthropic-proxy` | Claude AI fallback | 2026-01-02 |
| `elevenlabs-proxy` | Text-to-speech | 2025-12-30 |
| `openai-proxy` | GPT fallback | 2025-12-04 |
| `admin-gateway` | Fleet admin operations | 2025-12-27 |

## Testing Deployed Functions

```bash
# Test Gemini proxy
curl -X POST "https://zlkhsxacfyxsctqpvbsh.supabase.co/functions/v1/gemini-proxy" \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```
