# MVP Quick Reference Guide

## ScoreKeeper Sam - API Integration

### Leaderboard (Read-Only)
```javascript
async function fetchLeaderboard(game) {
  const r = await fetch(`http://localhost:8888/scores/leaderboard?game=${encodeURIComponent(game)}&limit=10`);
  return r.json();
}

// Usage:
const { scores, count } = await fetchLeaderboard('Galaga');
// scores = [{ timestamp, game, player, score }, ...]
```

### Submit Score (Preview→Apply)
```javascript
const hdrs = {
  'content-type': 'application/json',
  'x-scope': 'state',
  'x-device-id': 'CAB-001',
  'x-panel': 'scorekeeper'
};

// Step 1: Preview (shows diff, no write)
const preview = await fetch('http://localhost:8888/scores/submit/preview', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ game, player, score })
});
const { diff, has_changes } = await preview.json();

// Step 2: Apply (writes to scores.jsonl)
const apply = await fetch('http://localhost:8888/scores/submit/apply', {
  method: 'POST',
  headers: hdrs,
  body: JSON.stringify({ game, player, score })
});
const { status, backup_path, entry } = await apply.json();
```

### Tournaments

#### Create Tournament
```javascript
// size ∈ {4, 8, 16, 32}
const hdrs = {
  'content-type': 'application/json',
  'x-scope': 'state',
  'x-device-id': 'CAB-001',
  'x-panel': 'scorekeeper'
};

// Preview
const preview = await fetch('http://localhost:8888/scores/tournaments/create/preview', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ name, game, player_count })
});

// Apply
const apply = await fetch('http://localhost:8888/scores/tournaments/create/apply', {
  method: 'POST',
  headers: hdrs,
  body: JSON.stringify({ name, game, player_count })
});
const { tournament } = await apply.json();
// tournament.id, tournament.matches (bracket structure)
```

#### Report Winner
```javascript
// match_index = 0-based index in tournament.matches array
await fetch('http://localhost:8888/scores/tournaments/report/apply', {
  method: 'POST',
  headers: hdrs,
  body: JSON.stringify({
    tournament_id: tournamentId,
    match_index: matchIndex,
    winner_player: 'Player 1'
  })
});
```

#### Get Bracket
```javascript
const bracket = await fetch(`http://localhost:8888/scores/tournaments/${id}`).then(r => r.json());
// bracket.matches = [{ match_index, round, player1, player2, winner, status }, ...]
```

---

## LED Blinky - API Integration

### Test Actions (No Write)
```javascript
await fetch('http://localhost:8888/led/test', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    effect: 'pulse',        // pulse|wave|solid|rainbow|flash|chase|breathe
    durationMs: 1200,
    color: '#ff0000'
  })
});

// Returns: { status: 'test_executed', effect, duration_ms, color, timestamp, note }
```

### Mapping Editor (Preview→Apply)
```javascript
const hdrs = {
  'content-type': 'application/json',
  'x-scope': 'config',
  'x-device-id': 'CAB-001',
  'x-panel': 'led-blinky'
};

const mapping = {
  p1_button1: '#ff0000',
  p1_button2: '#00ff00',
  p2_button1: '#0000ff'
};

// Step 1: Preview (shows diff)
const preview = await fetch('http://localhost:8888/led/mapping/preview', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    scope: 'default',  // or 'game'
    game: null,        // required if scope='game'
    mapping: mapping
  })
});
const { diff, has_changes } = await preview.json();

// Step 2: Apply (writes to profile JSON)
const apply = await fetch('http://localhost:8888/led/mapping/apply', {
  method: 'POST',
  headers: hdrs,
  body: JSON.stringify({
    scope: 'default',
    mapping: mapping
  })
});
const { status, backup_path, changes_count } = await apply.json();
```

### List Profiles
```javascript
const { profiles, count } = await fetch('http://localhost:8888/led/profiles').then(r => r.json());
// profiles = [{ filename, scope, game, mapping_keys }, ...]
```

### Get Profile
```javascript
const profile = await fetch('http://localhost:8888/led/profiles/default').then(r => r.json());
// profile = { filename, scope, game, mapping: {...} }
```

---

## UX Pattern: Preview→Apply Workflow

**Always show the Preview diff before enabling Apply**:

```javascript
// 1. Preview phase
const preview = await previewAction();
setDiff(preview.diff);
setApplyEnabled(preview.has_changes);

// 2. Show diff to user (DiffPreview component)
<DiffPreview diff={diff} />

// 3. Apply button (only enabled if has_changes)
<button disabled={!applyEnabled} onClick={handleApply}>
  Apply Changes
</button>

// 4. On Apply success
const result = await applyAction();
toast(`✅ ${result.status} | Backup: ${result.backup_path}`);

// 5. Optional: Show last change
<button onClick={() => fetchLastChange()}>
  View Last Change
</button>
```

---

## Quick Checklist (Before Full UI Pass)

### ✅ Manifest Verification
```bash
cat .aa/manifest.json
```
**Required paths**:
- ✅ `"state"` (includes `/state/scorekeeper/`)
- ✅ `"config"` (includes `/config/ledblinky/`)
- ✅ `"backups"`
- ✅ `"logs"`

### ✅ Backend Running
```bash
# Start backend
npm run dev:backend

# Verify health
curl http://localhost:8888/health
# Should return: {"status":"healthy",...}
```

### ✅ Environment Variables
```bash
# Check FASTAPI_URL matches running port
echo $FASTAPI_URL
# Should be: http://localhost:8888 (or 8000 if using npm script)
```

### ✅ Headers on All Mutations
Every mutating frontend call must send:
- `x-device-id`: Device identifier (e.g., "CAB-001")
- `x-scope`: `state` (scores/tournaments) or `config` (LED mappings)
- `x-panel`: `scorekeeper` or `led-blinky`

### ✅ Run Acceptance Tests
```bash
./test_mvp_endpoints.sh
```
**Expected**: All green ✅

---

## Next Session Kickoff (Verify-First)

### Preflight (Read-Only)
1. **Confirm manifest** includes `/state/scorekeeper/`, `/config/ledblinky/`
2. **List missing UI pieces**:
   - **ScoreKeeper**: Submit form, leaderboard table, bracket cards with "report winner" buttons
   - **LED Blinky**: Mapping form (per-button color/effect), preview diff pane, Apply bar

### Deliverables (Minimal Diffs)

#### ScoreKeeper Sam
- **Submit Score Form**:
  - Inputs: game (text), player (text), score (number)
  - Button: "Preview" → shows diff → "Apply" → submits
  - Toast: Status + backup path
- **Leaderboard Table**:
  - Columns: Player, Score, Game, Timestamp
  - Filter: Game dropdown
  - Refresh button
- **Bracket View**:
  - Support 4/8/16/32 player brackets
  - Match cards with "Report Winner" buttons
  - Each button POSTs to `/tournaments/report/apply`
  - Updates bracket state after success

#### LED Blinky
- **Mapping Form**:
  - Per-button inputs: Button ID, Color (hex picker), Effect (dropdown)
  - "Preview" button → shows diff in pane
  - "Apply" button → saves to profile
- **Profile Selector**:
  - Dropdown: List profiles (default + game-specific)
  - Load button → populates form
- **Diff Viewer**:
  - Shows preview diff (reuse DiffPreview from Panel Kit)
- **Apply Bar**:
  - "Apply" button (enabled only when has_changes)
  - Toast: Status + backup path
  - Optional: "View Last Change" link

#### Common Pattern
Each action should:
1. Toast status on success
2. Append a "view last change" link that reads the final JSONL line from `A:\logs\changes.jsonl`

---

## Storage Locations

### ScoreKeeper Sam
```
A:\state\scorekeeper\
├── scores.jsonl          # Append-only score log
└── tournaments\
    ├── abc123.json       # Tournament state
    └── def456.json
```

### LED Blinky
```
A:\config\ledblinky\profiles\
├── default.json          # Default mapping
├── Galaga.json           # Game-specific profile
└── Street_Fighter_II.json
```

### Backups & Logs
```
A:\backups\20251011\
├── 123045_state_scorekeeper_scores.jsonl
└── 123046_config_ledblinky_profiles_default.json

A:\logs\
└── changes.jsonl         # All change events
```

---

## Implementation Notes

### No Supabase Needed (Local-First)
- All data stored in sanctioned paths (`A:\state`, `A:\config`)
- Automatic backups before every write
- All changes logged to `changes.jsonl`
- Cross-session persistence via local files
- Future: Add Supabase for quotas/leaderboards/cloud sync

### Error Handling
```javascript
try {
  const result = await applyAction();
  toast(`✅ ${result.status}`);
} catch (err) {
  toast(`❌ ${err.error || err.message}`);
  console.error('Action failed:', err);
}
```

### Rollback Pattern
```javascript
// Show backup path in toast
toast(`Applied! Backup: ${result.backup_path}`);

// Optional: Add rollback button
<button onClick={async () => {
  await fetch('http://localhost:8888/config/restore', {
    method: 'POST',
    headers: { ...hdrs, 'x-scope': 'backup' },
    body: JSON.stringify({
      backup_path: result.backup_path,
      target_file: 'state/scorekeeper/scores.jsonl'
    })
  });
}}>
  Undo
</button>
```

---

## Testing Flow

1. **Start backend**: `npm run dev:backend`
2. **Run acceptance tests**: `./test_mvp_endpoints.sh` → All green ✅
3. **Start frontend**: `npm run dev:frontend`
4. **Navigate to panels**:
   - ScoreKeeper: Click "Test Backend" → Should show connection status
   - LED Blinky: Click "Test All" → Should call backend test endpoint
5. **Verify logs**: Check `A:\logs\changes.jsonl` for entries

---

## Ready for Full UI Integration!

All backend routes are MVP-complete. Panel wiring is straightforward using:
- `frontend/src/services/scorekeeperClient.js`
- `frontend/src/services/ledBlinkyClient.js`

Follow the code snippets above for rapid integration. 🚀
