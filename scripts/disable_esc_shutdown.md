# Fixing ESC Key Shutdown Issue in Pegasus

## Problem
Pressing ESC while in a game causes the entire system to shut down instead of just exiting the game.

## Likely Causes

### 1. BigBox Running in Background
If BigBox is still running, it has a global ESC hotkey that exits/shuts down.

**Fix:**
- Make sure BigBox is NOT running when using Pegasus
- Check Task Manager for `BigBox.exe`
- Remove BigBox from Windows startup

### 2. Pegasus Theme ESC Behavior
Some Pegasus themes map ESC to quit the entire application.

**Fix:** Edit `A:\Tools\Pegasus\config\settings.txt`:
```ini
# Change this line to remove ESC from cancel (use only Backspace and GamepadB)
keys.cancel: Backspace,GamepadB
```

### 3. Global Hotkey Script
An AutoHotkey or similar script may be intercepting ESC globally.

**Fix:**
- Check system tray for AHK scripts
- Check `shell:startup` folder for hotkey scripts
- Check `A:\Tools\` for any `.ahk` files

### 4. Emulator ESC Behavior
Each emulator handles ESC differently:
- **RetroArch**: ESC opens menu (configurable)
- **MAME**: ESC exits game
- **TeknoParrot**: ESC exits game
- **Model 2/Supermodel**: ESC exits game

This is normal - ESC should exit the game and return to Pegasus, NOT shut down the system.

## Recommended Configuration

### Pegasus Settings (`A:\Tools\Pegasus\config\settings.txt`)
```ini
# Remove ESC from cancel to prevent accidental exits
keys.cancel: Backspace,GamepadB

# Keep other keys as-is
keys.accept: Return,Enter,GamepadA
keys.menu: F1,GamepadStart
```

### Emulator Exit Keys
Configure each emulator to use a consistent exit key (e.g., F10 or a button combo):

| Emulator | Exit Key Config Location |
|----------|-------------------------|
| RetroArch | Settings → Input → Hotkeys → Quit |
| MAME | mame.ini → `ui_cancel` |
| TeknoParrot | Per-game profile |
| Supermodel | Command line args |

## Testing
1. Start Pegasus
2. Launch a game
3. Press ESC - game should exit, return to Pegasus
4. Press ESC in Pegasus menu - should go back one level (not quit)

## If System Still Shuts Down
Check Windows Event Viewer for shutdown triggers:
1. Open Event Viewer
2. Windows Logs → System
3. Look for events around the shutdown time
4. Check for "User32" or "Power" events
