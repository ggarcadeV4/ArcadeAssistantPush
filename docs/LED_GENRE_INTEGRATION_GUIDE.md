# LED Blinky Genre Profile Integration Guide

## Overview

This document explains how LED Blinky uses genre profiles to automatically light buttons according to game type. When a game launches, LED Blinky reads the genre profile and sets LED colors to help players understand button functions.

## How It Works

1. **Game Launch** → System detects game genre (from LaunchBox metadata)
2. **Profile Lookup** → Loads corresponding genre profile from `config/mappings/genre_profiles.json`
3. **LED Mapping** → Applies LED colors defined in `led_profile` section
4. **Visual Feedback** → Players see color-coded buttons matching game type

## Fighting Game LED Layout

### Standard 6-Button Fighting Games
Traditional fighting game layout (Street Fighter, Mortal Kombat, etc.):

**Top Row (Punches):**
- **Button 1 (LP)**: Cyan `#00FFFF` - Light Punch
- **Button 2 (MP)**: Yellow `#FFFF00` - Medium Punch
- **Button 3 (HP)**: Red `#FF0000` - Heavy Punch

**Bottom Row (Kicks):**
- **Button 4 (LK)**: Cyan `#00FFFF` - Light Kick
- **Button 5 (MK)**: Yellow `#FFFF00` - Medium Kick
- **Button 6 (HK)**: Red `#FF0000` - Heavy Kick

**Visual Pattern**: Cyan → Yellow → Red creates strength progression players can learn instantly.

### 8-Button Fighting Games with Macros
Modern fighting games (Marvel vs. Capcom, Capcom vs SNK, etc.) with macro buttons:

**Additional Macro Buttons:**
- **Button 7 (3P)**: Magenta `#FF00FF` - All Punches Macro (LP+MP+HP)
- **Button 8 (3K)**: Teal `#00FF88` - All Kicks Macro (LK+MK+HK)

**Why Macros Matter:**
- **3P Button**: Used for throws, some supers, character select shortcuts
- **3K Button**: Used for certain special moves, supers, assists
- **Beginner Friendly**: New players can execute complex moves without learning 3-button combinations
- **Tournament Standard**: Many arcade cabinets include these buttons

**Color Strategy**: Magenta and Teal stand out as "special" buttons distinct from the main 6-button layout.

## Other Genre LED Profiles

### Racing Games
- Button 1 (Nitro): Magenta `#FF00FF`
- Button 2 (Gas): Green `#00FF00`
- Button 3 (Brake): Red `#FF0000`
- Button 4 (View): Cyan `#00FFFF`
- Button 5 (Gear Up): White `#FFFFFF`
- Button 6 (Gear Down): Gray `#888888`

### Shoot 'Em Ups (Shmups)
- Button 1 (Fire): Red `#FF0000`
- Button 2 (Bomb): Orange `#FFAA00`
- Button 3 (Rapid Fire): Orange-Red `#FF4400`
- Button 4 (Focus/Slow): Cyan `#00FFFF`

### Light Gun Games
- Button 1 (Trigger): Red `#FF0000`
- Button 2 (Reload): Orange `#FFAA00`
- Button 3 (Grenade): Green `#00FF00`
- Button 4 (Cover): Blue `#0088FF`

### Platformers
- Button 1 (Jump): Green `#00FF00`
- Button 2 (Attack): Red `#FF0000`
- Button 3 (Special/Run): Blue `#0088FF`

## LED Blinky Integration Checklist

When implementing genre-aware LED lighting:

- [ ] **Read genre from game metadata** (LaunchBox XML or API)
- [ ] **Load genre profile** from `config/mappings/genre_profiles.json`
- [ ] **Check genre aliases** (line 539-553) for alternate genre names
- [ ] **Apply LED colors** from `led_profile` section
- [ ] **Handle missing buttons** (some genres use fewer buttons - turn unused LEDs off or dim)
- [ ] **Fallback to default** if genre not recognized
- [ ] **Support per-game overrides** (allow custom LED profiles for specific games)
- [ ] **Persist across sessions** (remember player preferences)

## Example: Loading Fighting Game LED Profile

```python
import json

# Load genre profiles
with open('config/mappings/genre_profiles.json') as f:
    profiles = json.load(f)

# Get fighting game profile
fighting_profile = profiles['profiles']['fighting']
led_config = fighting_profile['led_profile']

# Apply to LED-Wiz channels
for control_key, led_settings in led_config.items():
    color = led_settings['color']
    label = led_settings.get('label', '')

    # Map control_key (p1.button1) to LED channel
    led_channel = map_control_to_channel(control_key)

    # Set LED color
    set_led_color(led_channel, color)

    print(f"Set {control_key} to {color} ({label})")
```

## Per-Game Overrides

Some games may need custom LED configurations beyond genre defaults:

1. **Create game-specific LED profile** in `config/mappings/game_led_overrides/`
2. **Reference by game ID** (LaunchBox ID or ROM name)
3. **LED Blinky checks for override first**, falls back to genre profile
4. **Example use case**: Street Fighter II (strict 6-button) vs Marvel vs. Capcom (8-button with macros)

## Visual Design Principles

**Color Psychology:**
- **Red**: Attack, danger, heavy/strong
- **Yellow**: Medium strength, caution
- **Cyan**: Light, weak, utility
- **Green**: Positive action (jump, start, gas pedal)
- **Magenta/Purple**: Special/macro functions
- **Blue**: Defensive (cover, brake, focus)

**Accessibility:**
- High contrast colors for visibility
- Avoid red/green only distinctions (colorblind consideration)
- Use brightness/saturation to indicate strength progression

**Consistency:**
- Same color = same function type across genres
- Red always means "strong/dangerous"
- Cyan always means "light/weak"
- Green always means "positive action"

## Future Enhancements

- **Animated LEDs**: Pulse or fade effects based on game events
- **Dynamic brightness**: Adjust based on game health/power meter
- **Color themes**: Allow players to choose color schemes (classic arcade, modern RGB, etc.)
- **Learning mode**: Flash correct button when player makes input errors
- **Attract mode**: Cycle through genre-specific light shows when idle

## Related Files

- **Genre Profiles**: [config/mappings/genre_profiles.json](../config/mappings/genre_profiles.json)
- **LED Blinky Panel**: [frontend/src/components/LEDBlinkyPanel.jsx](../frontend/src/components/LEDBlinkyPanel.jsx)
- **LED Mapping Service**: [backend/services/led_mapping_service.py](../backend/services/led_mapping_service.py)
- **Controller Chuck**: [backend/routers/controller.py](../backend/routers/controller.py)

---

**Last Updated**: 2025-12-30
**Status**: Ready for LED Blinky integration
**Next Steps**: Implement genre detection in LED Blinky workflow
