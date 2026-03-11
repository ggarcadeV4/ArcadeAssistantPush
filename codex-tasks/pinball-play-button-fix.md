# Codex Task: Pinball FX — Button Fix + Steam Launch Protocol

## Summary
Pinball FX2/FX3 games show in the LoRa panel grid but: (1) the play button appears disabled (`cursor: not-allowed`), and (2) even if clickable, the backend doesn't know how to launch Steam-based pinball games. This task fixes both.

**Games work perfectly from native LaunchBox.** Our frontend/backend has two gaps.

---

## Issue 1: Play Button Disabled (Frontend)

### What We Know
- `GameCard` renders ▶ unconditionally (line ~206-214 of `LaunchBoxPanel.jsx`)
- `canLaunchHere()` returns `true` for ALL platforms (line ~773)
- `launchDisabled={!canLaunchHere(game) || isLockActive}` (line ~2410)
- In the code, nothing should disable pinball. Yet the user sees `cursor: not-allowed` (CSS for `.game-play-btn:disabled`)

### What We Tried (Didn't Fix)
- Added `always-visible` CSS class with `z-index: 5` → still blocked
- Cache clear + gateway restart → still loading old hash (`912cd317` instead of `6d4990f9`)

### Most Likely Root Cause
**Stale browser bundle.** Console shows `LaunchBoxPanel-912cd317.js` while `frontend/dist` contains `LaunchBoxPanel-6d4990f9.js`. Check:
1. Is `NODE_ENV=production`? If so, hashed assets cache for 1 year (`immutable`)
2. Is there a service worker?
3. Run `ls frontend/dist/assets/LaunchBoxPanel*` — if the old hash file still exists, delete it

### Debugging Steps (Live DOM Required)
1. Open DevTools → Elements on a pinball game card
2. Find the `<button class="game-play-btn">` element
3. Check: does it have `disabled` attribute? What's the computed `opacity`, `z-index`, `pointer-events`?
4. Check: does the wrapper div's `onClick` steal the event? Add `e.stopPropagation()` to the button handler
5. Check: is `overflow: hidden` on `.game-card` clipping the button?

### Fix
In `GameCard` (LaunchBoxPanel.jsx), modify the button handler:

```jsx
const handleLaunch = useCallback((e) => {
  if (e) { e.stopPropagation(); e.preventDefault(); }
  onLaunch(game)
}, [game, onLaunch])
```

In the JSX, for pinball games, force-override the disabled state:

```jsx
<button
  className={`game-play-btn ${isDisabled && !isPinball ? 'disabled' : ''} ${isPinball ? 'always-visible' : ''}`}
  onClick={handleLaunch}
  disabled={isDisabled && !isPinball}
  title={launchTooltip}
>
  ▶
</button>
```

The `isPinball` detection exists at line ~171:
```jsx
const isPinball = (game.platform || '').toLowerCase().includes('pinball')
```

---

## Issue 2: Launch Protocol (Backend)

### The Problem
Pinball FX is NOT an emulated game. It's a Steam/Windows app. Each table is selected via CLI argument, not a ROM file. LaunchBox uses:
- **Pinball FX3**: `steam.exe -applaunch 442120 -table_[TableName]`
- **Pinball FX (2024)**: `steam.exe -applaunch 2328760 -Table [TableID]`

Our backend launch chain (`_launch_via_plugin` → `_launch_via_detected_emulator` → `_launch_via_direct`) doesn't handle Steam URI launches.

### Architecture Context
The C# plugin bridge (port 9999) calls LaunchBox's `PlayGame()` API — which already knows how to launch Pinball FX. **If the plugin bridge is online, no backend changes needed.** But the plugin bridge is currently OFFLINE (console shows `[Plugin Health] Check failed: TimeoutError`).

### Fix Options

**Option A (Recommended): Fix the Plugin Bridge**
Get the C# bridge running. Then the LoRa panel calls `/api/launchbox/launch/{game_id}` → plugin bridge → LaunchBox `PlayGame()` → LaunchBox handles everything. Zero backend code changes needed. This is how ALL games should launch.

**Option B: Steam Launcher Adapter (Backend Fallback)**
If the plugin bridge can't be fixed, add a Steam launch adapter to `backend/services/launcher.py`:

```python
async def _launch_via_steam(game, mapping):
    """Launch a Steam game using steam:// protocol."""
    platform = (game.platform or '').lower()
    
    # Pinball FX3 (Steam AppID 442120)
    if 'pinball fx3' in platform:
        table_name = Path(game.application_path).stem if game.application_path else ''
        cmd = f'steam://run/442120//-table_{table_name}'
        subprocess.Popen(['cmd', '/c', 'start', '', cmd])
        return {'success': True, 'method': 'steam_uri'}
    
    # Pinball FX 2024 (Steam AppID 2328760)  
    if 'pinball fx' in platform:
        # Table ID from CommandLine in LaunchBox XML
        table_id = game.command_line or ''
        cmd = f'steam://run/2328760//-Table {table_id}'
        subprocess.Popen(['cmd', '/c', 'start', '', cmd])
        return {'success': True, 'method': 'steam_uri'}
```

### LaunchBox XML Data Reference
From `Pinball FX3.xml`:
- `<Platform>Pinball FX3</Platform>`
- `<ApplicationPath>..\Roms\PINBALL-FX3\data\steam\MARVEL_Wolverine.pxp</ApplicationPath>`
- Emulator: `Pinball FX3.exe` with CommandLine `-applaunch 442120 -table_`

---

## CSS Changes (launchbox.css)

Already partially in place. Ensure these rules exist:

```css
/* Grid play button: above all card layers */
.games-grid .game-play-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 10;
  pointer-events: auto;
}

/* Image/info containers: behind play button */
.games-grid .game-image-container { z-index: 1; }
.games-grid .game-info { z-index: 1; }

/* Grid card: allow button overflow */
.games-grid .game-card { overflow: visible; }

/* Pinball: always-visible pink button */
.games-grid .game-play-btn.always-visible {
  opacity: 1 !important;
  background: var(--neon-pink);
  box-shadow: 0 0 15px rgba(255, 0, 127, 0.4);
}

/* Card sweep overlay: don't steal clicks */
.game-card::before { pointer-events: none; }
```

---

## Files to Modify
| File | Change |
|------|--------|
| `frontend/src/panels/launchbox/LaunchBoxPanel.jsx` | `stopPropagation` on button, `isPinball` override for disabled state |
| `frontend/src/panels/launchbox/launchbox.css` | z-index stacking, overflow, `always-visible`, `pointer-events` |
| `backend/services/launcher.py` | Steam URI adapter (only if plugin bridge stays offline) |

## Verification
1. `npx vite build` — clean build
2. Restart gateway, FULL browser cache clear
3. Navigate to Pinball FX3 in LoRa grid
4. Pink ▶ button visible without hover
5. Clicking button triggers launch (via plugin bridge or Steam URI)
6. Other games unchanged

## Acceptance Criteria
- [ ] Pinball play buttons are VISIBLE (pink, always shown)
- [ ] Pinball play buttons are CLICKABLE (no `cursor: not-allowed`)
- [ ] Pinball games LAUNCH when clicked
- [ ] Other game buttons retain hover-reveal behavior
- [ ] Build passes clean
