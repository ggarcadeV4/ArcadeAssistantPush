"""
MAME Plugin Installer
=====================
Deploys arcade_assistant_scores plugin to MAME and enables it.

Actions:
1. Copy plugin folder to A:\Emulators\MAME Gamepad\plugins\
2. Ensure plugin.ini has arcade_assistant_scores enabled
3. Create output directory for mame_scores.json

Usage:
    python install_mame_plugin.py
"""

import shutil
import os
from pathlib import Path


# Paths (A: Drive Strategy)
SOURCE_PLUGIN = Path(r"A:\Arcade Assistant Local\backend\mame\plugins\arcade_assistant_scores")
MAME_PLUGINS_DIR = Path(r"A:\Emulators\MAME Gamepad\plugins")
MAME_PLUGIN_INI = Path(r"A:\Emulators\MAME Gamepad\plugin.ini")
SCORES_OUTPUT_DIR = Path(r"A:\.aa\state\scorekeeper")

PLUGIN_NAME = "arcade_assistant_scores"


def install_plugin():
    """Copy plugin to MAME plugins directory."""
    dest = MAME_PLUGINS_DIR / PLUGIN_NAME
    
    print(f"[Installer] Source: {SOURCE_PLUGIN}")
    print(f"[Installer] Destination: {dest}")
    
    if not SOURCE_PLUGIN.exists():
        print(f"[Installer] ERROR: Source plugin not found at {SOURCE_PLUGIN}")
        return False
    
    # Create plugins directory if needed
    MAME_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Remove existing if present
    if dest.exists():
        print(f"[Installer] Removing existing plugin at {dest}")
        shutil.rmtree(dest)
    
    # Copy plugin
    shutil.copytree(SOURCE_PLUGIN, dest)
    print(f"[Installer] ✅ Plugin copied to {dest}")
    
    return True


def enable_plugin():
    """Ensure plugin is enabled in plugin.ini."""
    print(f"[Installer] Checking plugin.ini at {MAME_PLUGIN_INI}")
    
    # Read existing content
    existing_lines = []
    if MAME_PLUGIN_INI.exists():
        with open(MAME_PLUGIN_INI, 'r', encoding='utf-8') as f:
            existing_lines = f.readlines()
    
    # Check if already enabled
    plugin_line = f"{PLUGIN_NAME}                 1\n"
    found = False
    updated_lines = []
    
    for line in existing_lines:
        stripped = line.strip()
        # Check for our plugin (enabled or disabled)
        if stripped.startswith(PLUGIN_NAME):
            found = True
            # Ensure it's enabled
            if "0" in stripped:
                print(f"[Installer] Enabling {PLUGIN_NAME} (was disabled)")
                updated_lines.append(plugin_line)
            else:
                print(f"[Installer] {PLUGIN_NAME} already enabled")
                updated_lines.append(line)
        else:
            updated_lines.append(line)
    
    # Add if not found
    if not found:
        print(f"[Installer] Adding {PLUGIN_NAME} to plugin.ini")
        updated_lines.append(plugin_line)
    
    # Write back
    with open(MAME_PLUGIN_INI, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)
    
    print(f"[Installer] ✅ plugin.ini updated")
    return True


def create_output_dir():
    """Create the scores output directory."""
    print(f"[Installer] Creating output directory: {SCORES_OUTPUT_DIR}")
    SCORES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Installer] ✅ Output directory ready")
    return True


def verify_installation():
    """Verify the plugin is properly installed."""
    checks = []
    
    # Check plugin files
    plugin_dir = MAME_PLUGINS_DIR / PLUGIN_NAME
    init_lua = plugin_dir / "init.lua"
    plugin_json = plugin_dir / "plugin.json"
    
    checks.append(("Plugin directory exists", plugin_dir.exists()))
    checks.append(("init.lua exists", init_lua.exists()))
    checks.append(("plugin.json exists", plugin_json.exists()))
    
    # Check plugin.ini
    if MAME_PLUGIN_INI.exists():
        with open(MAME_PLUGIN_INI, 'r', encoding='utf-8') as f:
            content = f.read()
            checks.append(("Plugin enabled in INI", f"{PLUGIN_NAME}" in content and "1" in content))
    else:
        checks.append(("plugin.ini exists", False))
    
    # Check output dir
    checks.append(("Output directory exists", SCORES_OUTPUT_DIR.exists()))
    
    print("\n[Installer] Verification Results:")
    all_passed = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False
    
    return all_passed


def main():
    print("=" * 60)
    print("MAME PLUGIN INSTALLER - arcade_assistant_scores")
    print("=" * 60)
    print()
    
    # Step 1: Install plugin
    print("[Step 1] Installing plugin...")
    if not install_plugin():
        print("[Installer] FAILED at Step 1")
        return False
    print()
    
    # Step 2: Enable plugin
    print("[Step 2] Enabling plugin...")
    if not enable_plugin():
        print("[Installer] FAILED at Step 2")
        return False
    print()
    
    # Step 3: Create output directory
    print("[Step 3] Creating output directory...")
    if not create_output_dir():
        print("[Installer] FAILED at Step 3")
        return False
    print()
    
    # Verify
    print("[Step 4] Verifying installation...")
    if verify_installation():
        print("\n" + "=" * 60)
        print("✅ INSTALLATION COMPLETE")
        print("=" * 60)
        print(f"\nPlugin installed to: {MAME_PLUGINS_DIR / PLUGIN_NAME}")
        print(f"Scores will be written to: {SCORES_OUTPUT_DIR / 'mame_scores.json'}")
        print("\nRestart MAME to activate the plugin.")
        return True
    else:
        print("\n❌ INSTALLATION VERIFICATION FAILED")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
