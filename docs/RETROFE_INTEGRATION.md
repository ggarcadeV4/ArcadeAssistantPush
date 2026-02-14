# RetroFE Integration

> **Location**: `A:\Tools\RetroFE\RetroFE\`
> **Version**: 0.10.31
> **License**: MIT (Open Source)
> **Installed**: 2025-12-07

---

## Directory Structure

```
A:\Tools\RetroFE\
└── RetroFE/                      # Main application folder
    ├── core/                     # RetroFE executable and libs
    │   └── retrofe.exe           # ⭐ Main executable
    ├── collections/              # Game collections (we generate these)
    │   ├── Main/                 # Main menu
    │   │   ├── menu.txt          # List of sub-collections
    │   │   └── settings.conf     # Collection settings
    │   ├── Arcade/               # Example collection
    │   │   ├── menu.txt          # List of games
    │   │   └── settings.conf     # Emulator/launcher settings
    │   └── ...
    ├── layouts/                  # Themes/visual layouts
    │   └── Starter/              # Default theme
    ├── launchers.windows/        # Launch scripts (we customize these)
    │   └── *.conf                # Launcher configurations
    ├── meta/                     # Artwork folders
    │   └── [platform]/
    │       ├── artwork_front/
    │       ├── artwork_back/
    │       └── video/
    ├── controls.conf             # Controller mappings
    └── settings.conf             # Global settings
```

---

## How RetroFE Works

### Collections
Each collection (platform) has:
- `menu.txt` - List of games (one per line, filename without extension)
- `settings.conf` - Configuration including launcher

### Launchers
Located in `launchers.windows/`:
```ini
# Example: arcade.conf
executable = A:\Arcade Assistant Local\scripts\aa_launch.bat
arguments = %ITEM%
```

### Artwork
RetroFE looks for artwork in `meta/[collection]/artwork_front/[gamename].png`

---

## Integration with Arcade Assistant

### 1. Collection Generator
Script: `scripts/generate_retrofe_collections.py`

Reads `A:\.aa\game_library.json` and generates:
- `collections/` folders for each platform
- `menu.txt` files with game lists
- `settings.conf` pointing to AA launcher

### 2. Launch Bridge
Script: `scripts/aa_launch.bat` (or `aa_launch.py`)

RetroFE calls this with game name → We resolve to game ID → Call backend launch API

### 3. Artwork Mapping
Option A: Symlink `meta/` to existing LaunchBox Images
Option B: Copy/convert artwork to RetroFE structure

---

## Running RetroFE

```powershell
# From command line
cd "A:\Tools\RetroFE\RetroFE"
.\core\retrofe.exe

# Or use shortcut
A:\Tools\RetroFE\RetroFE\RetroFE.lnk
```

---

## Configuration Files to Customize

| File | Purpose | Priority |
|------|---------|----------|
| `settings.conf` | Global settings, exit key | High |
| `controls.conf` | Controller mappings | Medium |
| `collections/Main/menu.txt` | Main menu items | High |
| `launchers.windows/*.conf` | How games launch | High |

---

## Next Steps

1. [ ] Create `scripts/generate_retrofe_collections.py`
2. [ ] Create `scripts/aa_launch.bat` launch bridge
3. [ ] Configure `settings.conf` for our setup
4. [ ] Link or copy artwork
5. [ ] Add toggle button in web panel to launch RetroFE
6. [ ] Test end-to-end launch flow
