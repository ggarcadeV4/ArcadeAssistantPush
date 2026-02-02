# Controller System Context (For Chuck AI)

## Overview
The arcade cabinet has a two-layer control system:
1. **Cabinet Layer** - Hardware wiring (physical buttons to pins)
2. **Player Layer** - Personal preferences (coming in Phase 2)

---

## Cabinet Reset (Hardware Layer)

### What It Does
- Clears `controls.json` to factory template
- Regenerates MAME `default.cfg` from factory controls
- Prepares cabinet for Learn Wizard recalibration

### When to Recommend
- "My controls are messed up"
- "I rewired my cabinet"
- "Setting up a new cabinet"
- "Nothing is working right"

### User Guidance
```
"I'll reset your cabinet controls to factory defaults and regenerate the 
MAME config. After this, you can use the Learn Wizard to recalibrate 
your buttons to match your wiring."
```

## On-Demand Custom Control Layouts

### How It Works
Instead of automatic profile switching, Chuck generates custom configs when asked:

```
Player: "I want shmups to use row 1 buttons instead of row 2"
Chuck: Generates per-game/genre config with requested layout
       + Updates LED config to match (row 1 LEDs light up)
```

### What Chuck Can Do
1. Generate custom MAME per-game configs (`<romname>.cfg`)
2. Apply genre-based button layouts
3. **Sync LED lighting to match control layout**

### When to Offer
- "I want a different button layout for fighting games"
- "Can you set up Tekken like a real arcade?"
- "Make shmups use the top row buttons"

### User Guidance
```
"I can set up a custom button layout for that game. I'll configure 
the controls AND make sure the LEDs light up the right buttons 
so you know exactly which ones to use."
```

### Important: LED Sync
**Always update LEDs when changing control layouts!**
- If controls move to row 1, LEDs should light up row 1
- This maintains the "magical" experience
- Player sees exactly which buttons are active

---

## Key Files

| File | Purpose |
|------|---------|
| `config/mappings/controls.json` | Current cabinet controls (source of truth) |
| `config/mappings/factory-default.json` | Factory reset template |
| `Emulators/MAME/cfg/default.cfg` | MAME config (auto-generated from controls.json) |
| `state/controller/player_identity.json` | Maps physical stations to P1/P2/P3/P4 |

---

## API Endpoints

| Endpoint | Action |
|----------|--------|
| `POST /mapping/apply` | Save control changes (also regenerates MAME) |
| `POST /mapping/reset` | Reset to factory (also regenerates MAME) |
| `POST /admin/golden-reset` | **Master wipe** for drive cloning (clears all player data) |
| `POST /learn-wizard/start` | Start control calibration wizard |

---

## Golden Drive Reset (For Cloning)

### What It Does
- Resets `controls.json` to factory
- Regenerates MAME `default.cfg`
- Deletes `player_identity.json`
- Deletes all player profiles and tendencies
- (Optional) Clears MAME high scores

### When to Use
- Preparing drive for cloning to other cabinets
- Starting completely fresh
- Testing cleanup

### Requires
- `confirm: true` in request body
- `clear_high_scores: true` to also wipe scores (optional)

### User Guidance
```
"I'll perform a Golden Drive Reset - this clears all player data and 
resets controls to factory. After cloning, each new cabinet can run 
the Learn Wizard to calibrate its own wiring."
```

## Troubleshooting Guidance

### "Controls aren't working"
1. Check if Learn Wizard completed successfully
2. Suggest Cabinet Reset if mappings are corrupted
3. Verify MAME config was regenerated

### "Wrong buttons do things"
1. Cabinet wiring may differ from config
2. Run Learn Wizard to recalibrate
3. Check player_identity.json for swapped players

### "MAME controls don't match"
1. Verify controls.json and MAME default.cfg are in sync
2. If out of sync, suggest saving controls again (triggers regeneration)
