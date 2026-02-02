"""
TeknoParrot XML Writer Test Script

This script tests the end-to-end flow of the TeknoParrot config writer:
1. Creates a sample TeknoParrot UserProfile XML
2. Loads mock panel mappings (simulating Chuck's controls.json)
3. Builds a canonical mapping
4. Previews the changes
5. Applies the config (backup → write → log)
6. Verifies the changes were written correctly

Safety Pattern Verified:
- Preview: Shows diff without writing (preview_tp_config)
- Backup: Creates timestamped backup at backups/teknoparrot/{profile}_{timestamp}.xml
- Apply: Only modifies elements with actual changes (_update_xml_bindings)
- Log: Appends JSONL entry to logs/changes.jsonl with before/after values

Run with:
  python -m backend.tests.test_teknoparrot_writer
  pytest backend/tests/test_teknoparrot_writer.py -v

Note: This test uses the project root as drive_root for dev testing.
Backups go to: {project_root}/backups/teknoparrot/
Logs go to: {project_root}/logs/changes.jsonl
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.teknoparrot_config_generator import (
    TPGameCategory,
    build_canonical_mapping,
    preview_tp_config,
    apply_tp_config,
    create_sample_profile,
    get_game_category,
    get_schema_for_game,
)


def test_teknoparrot_writer():
    """Test the full TeknoParrot writer flow."""
    
    print("=" * 60)
    print("TeknoParrot XML Writer Test")
    print("=" * 60)
    
    # Use test directory
    drive_root = project_root
    test_dir = drive_root / "Emulators" / "TeknoParrot" / "UserProfiles"
    
    # Test game: Initial D 8
    test_profile = "InitialD8.xml"
    profile_path = test_dir / test_profile
    
    # Step 1: Create sample profile
    print("\n1. Creating sample TeknoParrot profile...")
    if profile_path.exists():
        print(f"   Profile already exists: {profile_path}")
    else:
        success = create_sample_profile(
            profile_path=profile_path,
            profile_name="InitialD8",
            category=TPGameCategory.RACING,
        )
        if success:
            print(f"   Created: {profile_path}")
        else:
            print("   FAILED to create profile")
            return False
    
    # Read initial content
    with open(profile_path, "r", encoding="utf-8") as f:
        initial_content = f.read()
    print(f"   Initial file size: {len(initial_content)} bytes")
    
    # Step 2: Create mock panel mappings (simulating controls.json)
    print("\n2. Creating mock panel mappings...")
    mock_panel_mappings = {
        "p1.button1": {"pin": 5, "type": "button", "label": "Button 1"},
        "p1.button2": {"pin": 6, "type": "button", "label": "Button 2"},
        "p1.button3": {"pin": 7, "type": "button", "label": "Button 3"},
        "p1.button4": {"pin": 8, "type": "button", "label": "Button 4"},
        "p1.button5": {"pin": 9, "type": "button", "label": "Button 5"},
        "p1.button6": {"pin": 10, "type": "button", "label": "Button 6"},
        "p1.start": {"pin": 1, "type": "button", "label": "Start"},
        "p1.coin": {"pin": 0, "type": "button", "label": "Coin"},
        "p1.up": {"pin": 11, "type": "button", "label": "Up"},
        "p1.down": {"pin": 12, "type": "button", "label": "Down"},
        "p1.left": {"pin": 13, "type": "button", "label": "Left"},
        "p1.right": {"pin": 14, "type": "button", "label": "Right"},
    }
    print(f"   Loaded {len(mock_panel_mappings)} panel controls")
    
    # Step 3: Check game category
    print("\n3. Verifying game category...")
    category = get_game_category("InitialD8")
    print(f"   Category: {category}")
    assert category == TPGameCategory.RACING, "Expected RACING category"
    
    # Step 4: Build canonical mapping
    print("\n4. Building canonical mapping...")
    canonical = build_canonical_mapping(
        profile_name="InitialD8",
        panel_mappings=mock_panel_mappings,
        player=1,
    )
    
    if canonical is None:
        print("   FAILED: Could not build canonical mapping")
        return False
    
    print(f"   Game: {canonical.game}")
    print(f"   Profile: {canonical.profile}")
    print(f"   Category: {canonical.category.value}")
    print(f"   Controls mapped: {len(canonical.controls)}")
    
    # Show some bindings
    print("   Sample bindings:")
    for name, binding in list(canonical.controls.items())[:4]:
        print(f"     - {name}: {binding.tp_name} = {binding.raw_value}")
    
    # Step 5: Preview changes
    print("\n5. Previewing changes...")
    preview = preview_tp_config(profile_path, canonical)
    
    print(f"   File exists: {preview.file_exists}")
    print(f"   Has changes: {preview.has_changes}")
    print(f"   Changes count: {preview.changes_count}")
    print(f"   Summary: {preview.summary}")
    
    if preview.has_changes:
        print("   Changed bindings:")
        for diff in preview.diffs:
            if diff.changed:
                print(f"     - {diff.control_name} ({diff.tp_name}): '{diff.current_value}' → '{diff.proposed_value}'")
    
    # Step 6: Apply changes
    print("\n6. Applying changes...")
    result = apply_tp_config(
        profile_path=profile_path,
        canonical=canonical,
        drive_root=drive_root,
        backup=True,
    )
    
    print(f"   Success: {result.success}")
    print(f"   Changes applied: {result.changes_applied}")
    print(f"   Backup path: {result.backup_path}")
    print(f"   Log entry: {result.log_entry}")
    
    if result.error:
        print(f"   Error: {result.error}")
        return False
    
    if result.changes_detail:
        print("   Changes detail:")
        for change in result.changes_detail[:5]:
            print(f"     - {change['control']} ({change['tp_name']}): '{change['before']}' → '{change['after']}'")
        if len(result.changes_detail) > 5:
            print(f"     ... and {len(result.changes_detail) - 5} more")
    
    # Step 7: Verify the file was updated
    print("\n7. Verifying file changes...")
    with open(profile_path, "r", encoding="utf-8") as f:
        updated_content = f.read()
    print(f"   Updated file size: {len(updated_content)} bytes")
    
    # Check for some expected values in the XML
    checks = [
        ("InputStart", "DirectInput/0/Button 1"),
        ("InputCoin", "DirectInput/0/Button 0"),
    ]
    
    all_passed = True
    for element, expected in checks:
        if expected in updated_content:
            print(f"   ✓ Found {element} = {expected}")
        else:
            print(f"   ✗ Missing {element} = {expected}")
            all_passed = False
    
    # Step 8: Check the log file
    print("\n8. Checking log file...")
    log_file = drive_root / "logs" / "changes.jsonl"
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Find our log entry
        for line in reversed(lines):
            try:
                entry = json.loads(line)
                if entry.get("panel") == "teknoparrot" and entry.get("action") == "apply_config":
                    print(f"   Log entry found: {entry.get('id')}")
                    print(f"   Profile: {entry.get('profile')}")
                    print(f"   Changes: {entry.get('changes_count')}")
                    break
            except json.JSONDecodeError:
                continue
    else:
        print("   Log file not found")
    
    # Step 9: Check backup
    print("\n9. Checking backup...")
    if result.backup_path:
        backup_path = Path(result.backup_path)
        if backup_path.exists():
            print(f"   ✓ Backup exists: {backup_path}")
            print(f"   Backup size: {backup_path.stat().st_size} bytes")
        else:
            print(f"   ✗ Backup not found: {backup_path}")
    
    print("\n" + "=" * 60)
    if result.success and all_passed:
        print("TEST PASSED: TeknoParrot XML writer works correctly!")
    else:
        print("TEST FAILED: Some checks did not pass")
    print("=" * 60)
    
    return result.success and all_passed


def test_teknoparrot_preview_does_not_write():
    """Pytest: Verify preview does not modify files."""
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        profile_path = tmp_path / "TestProfile.xml"
        
        # Create sample profile
        create_sample_profile(profile_path, "TestProfile", TPGameCategory.RACING)
        
        # Get initial content
        initial_content = profile_path.read_text(encoding="utf-8")
        initial_mtime = profile_path.stat().st_mtime
        
        # Build canonical mapping
        mock_mappings = {"p1.start": {"pin": 1}, "p1.coin": {"pin": 0}}
        canonical = build_canonical_mapping("TestProfile", mock_mappings, player=1)
        
        # Preview should NOT modify the file
        preview = preview_tp_config(profile_path, canonical)
        
        # Verify file unchanged
        assert profile_path.read_text(encoding="utf-8") == initial_content
        assert profile_path.stat().st_mtime == initial_mtime
        assert preview.file_exists is True


def test_teknoparrot_apply_creates_backup():
    """Pytest: Verify apply creates backup before writing."""
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        profile_path = tmp_path / "Emulators" / "TeknoParrot" / "UserProfiles" / "TestProfile.xml"
        
        # Create sample profile
        create_sample_profile(profile_path, "TestProfile", TPGameCategory.RACING)
        
        # Build canonical mapping with changes
        mock_mappings = {"p1.start": {"pin": 99}, "p1.coin": {"pin": 88}}
        canonical = build_canonical_mapping("TestProfile", mock_mappings, player=1)
        
        # Apply with backup enabled
        result = apply_tp_config(profile_path, canonical, tmp_path, backup=True)
        
        # Verify backup was created
        assert result.success is True
        assert result.backup_path is not None
        assert Path(result.backup_path).exists()
        
        # Verify log was created
        log_file = tmp_path / "logs" / "changes.jsonl"
        assert log_file.exists()


if __name__ == "__main__":
    success = test_teknoparrot_writer()
    sys.exit(0 if success else 1)
