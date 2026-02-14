# Launch Verification Runbook (Plugin-First with Fallbacks)

This runbook verifies game launching via the backend, with or without the LaunchBox plugin. Default flow prefers the plugin; if offline, it falls back to detected emulator, LaunchBox.exe, or direct (MAME), in that order.

## Prereqs
- Backend: http://localhost:8000
- Gateway: http://localhost:8787
- Header required: `x-panel: launchbox`

Feature flag (fallback enablement):
- `AA_ALLOW_DIRECT_EMULATOR=true` (supported)
- Alias accepted: `AA_ALLOW_DIRECT_MAME=true`

## 1) Grab a game_id and title

### Bash
```bash
set -euo pipefail
COUNT=$(curl -fsS --connect-timeout 3 --max-time 10 "http://localhost:8000/api/launchbox/games?limit=1" | jq 'length')
if [ "$COUNT" -lt 1 ]; then echo "No games found — populate LB first"; exit 2; fi
GID=$(curl -fsS --connect-timeout 3 --max-time 10 "http://localhost:8000/api/launchbox/games?limit=1" | jq -r '.[0].id')
GTITLE=$(curl -fsS --connect-timeout 3 --max-time 10 "http://localhost:8000/api/launchbox/games?limit=1" | jq -r '.[0].title')
echo "$GID  |  $GTITLE"
```

### PowerShell
```powershell
$resp = curl.exe -fsS "http://localhost:8000/api/launchbox/games?limit=1" | ConvertFrom-Json
if ($resp.Count -lt 1) { throw "No games found — populate LB first" }
$GID   = $resp[0].id
$TITLE = $resp[0].title
"$GID  |  $TITLE"
```

## 2) Default launch (prefers plugin; falls back automatically)

```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{}'
```

```powershell
curl.exe -fsS -X POST "http://localhost:8000/api/launchbox/launch/$GID" -H "x-panel: launchbox" -H "Content-Type: application/json" -d "{}"
```

## 3) Force specific paths (diagnostics)

Detected emulator (uses `A:\LaunchBox\Data\Emulators.xml`):
```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{"force_method":"detected_emulator"}'
```

LaunchBox.exe (opens LB; may not auto-start a game):
```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{"force_method":"launchbox"}'
```

Direct (MAME fallback):
```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{"force_method":"direct"}'
```

## 4) Plugin sanity (optional)
```bash
curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1:9999/health
curl -fsS --connect-timeout 3 --max-time 10 http://localhost:8000/api/launchbox/plugin-status
```
Expect `available: true` for `plugin_bridge`. If offline, default falls through to other methods.

## 4b) Scores bridge smoke (plugin + gateway)

Plugin health and leaderboard (fast, <100ms):
```bash
curl -fsS http://127.0.0.1:9999/health
curl -fsS "http://127.0.0.1:9999/scores/leaderboard?limit=5"
```

Submit a sample score and verify JSONL append (append-only):
```bash
curl -fsS -X POST http://127.0.0.1:9999/scores/submit \
  -H "Content-Type: application/json" \
  -d '{"gameId":"test-gid","player":"sam","score":12345} '

type A:\\LaunchBox\\Logs\\ArcadeAssistant\\scores.jsonl | tail -n 3
# Expect a line like:
# {"ts":"2025-10-13T14:30:15Z","gameId":"test-gid","player":"sam","score":12345,...}
```

Gateway proxy (fresh → cached):
```bash
# Fresh when plugin up
curl -fsS "http://localhost:8787/api/launchbox/scores/leaderboard?limit=5" -H "x-panel: launchbox"

# Stop plugin, call again within 30s: returns cached with {"cached":true}
curl -fsS "http://localhost:8787/api/launchbox/scores/leaderboard?limit=5" -H "x-panel: launchbox"
```

Acceptance:
- Plugin online: 200 with fresh leaderboard (no cached flag)
- Plugin offline: 200 with `cached:true` (if cached) or 503 with friendly message

## 5) Assertions (exit codes)

### Bash — require plugin
```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{}' \
| jq -e '.success==true and .method_used=="plugin_bridge"' >/dev/null
```

### Bash — accept any successful method
```bash
curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" \
  -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{}' \
| jq -e '.success==true and (.method_used=="plugin_bridge" or .method_used=="detected_emulator" or .method_used=="launchbox" or .method_used=="direct")' >/dev/null
```

### PowerShell — require plugin
```powershell
$r = curl.exe -fsS -X POST "http://localhost:8000/api/launchbox/launch/$GID" -H "x-panel: launchbox" -H "Content-Type: application/json" -d "{}" | ConvertFrom-Json
if (!($r.success -and $r.method_used -eq "plugin_bridge")) { $r | ConvertTo-Json -Depth 5; exit 1 }
```

## 6) URLACL for plugin (exact URL)
```powershell
netsh http add urlacl url=http://127.0.0.1:9999/ user=Everyone
curl.exe -fsS http://127.0.0.1:9999/health
```

## 7) Triage by method_used (Bash)
```bash
RES=$(curl -fsS --connect-timeout 3 --max-time 10 -X POST "http://localhost:8000/api/launchbox/launch/${GID}" -H "x-panel: launchbox" -H "Content-Type: application/json" -d '{}')
METHOD=$(echo "$RES" | jq -r '.method_used')
MSG=$(echo "$RES" | jq -r '.message // ""')
case "$METHOD" in
  plugin_bridge) echo "✅ Plugin path";;
  detected_emulator) echo "ℹ Detected emulator — check Emulators.xml paths if issues.";;
  launchbox) echo "ℹ Opened LaunchBox — plugin likely offline. $MSG";;
  direct) echo "🛟 Direct adapter — verify EXE/ROM presence. $MSG";;
  *) echo "❓ Unexpected: $RES"; exit 1;;
esac
```

## 8) Scripts
- Bash: `scripts/smoke_bash.sh` — exits 0 on success, 1 on failure, 2 if library empty
- PowerShell: `scripts/smoke_win.ps1` — same semantics

Scores quick check (PowerShell):
```powershell
curl.exe -fsS http://127.0.0.1:9999/health | ConvertFrom-Json | ConvertTo-Json -Depth 5
curl.exe -fsS "http://127.0.0.1:9999/scores/leaderboard?limit=3" | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

## Notes
- Keep loopback consistent: use `127.0.0.1` for plugin and reserve that exact URLACL.
- Consider logging `duration_ms` for launches to spot slow paths.
