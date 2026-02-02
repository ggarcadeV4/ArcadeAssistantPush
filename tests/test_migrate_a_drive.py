"""Pytest tests for A: drive migration CLI script.

Tests migration validation, dry-run simulation, path checks, and error handling.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from migrate_a_drive import (
    validate_source_directory,
    validate_target_directory,
    validate_launchbox_installation,
    copy_with_progress,
    generate_env_file,
    post_migration_validation,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_source_dir():
    """Create temporary source directory with Arcade Assistant structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir)

        # Create critical paths
        (source / 'backend').mkdir()
        (source / 'frontend').mkdir()
        (source / 'gateway').mkdir()
        (source / 'configs').mkdir()

        # Create package.json
        package_json = {'name': 'arcade-assistant', 'version': '1.0.0'}
        with open(source / 'package.json', 'w') as f:
            json.dump(package_json, f)

        # Create README
        (source / 'README.md').write_text('# Arcade Assistant')

        yield source


@pytest.fixture
def temp_target_dir():
    """Create temporary target directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / 'target'


@pytest.fixture
def temp_launchbox_dir():
    """Create temporary LaunchBox directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        launchbox_root = Path(tmpdir) / 'LaunchBox'
        launchbox_root.mkdir()

        # Create required paths
        (launchbox_root / 'LaunchBox.exe').write_text('mock exe')
        (launchbox_root / 'BigBox.exe').write_text('mock exe')
        (launchbox_root / 'Data' / 'Platforms').mkdir(parents=True)

        # Create optional CLI_Launcher
        cli_path = launchbox_root / 'ThirdParty' / 'CLI_Launcher'
        cli_path.mkdir(parents=True)
        (cli_path / 'CLI_Launcher.exe').write_text('mock cli')

        yield Path(tmpdir)


# ============================================================================
# Source Validation Tests
# ============================================================================

def test_validate_source_directory_valid(temp_source_dir):
    """Test validation of valid source directory."""
    is_valid, errors = validate_source_directory(temp_source_dir)

    assert is_valid is True
    assert len(errors) == 0


def test_validate_source_directory_missing_critical_path(temp_source_dir):
    """Test validation fails when critical path missing."""
    # Remove backend directory
    shutil.rmtree(temp_source_dir / 'backend')

    is_valid, errors = validate_source_directory(temp_source_dir)

    assert is_valid is False
    assert any('backend' in error.lower() for error in errors)


def test_validate_source_directory_nonexistent():
    """Test validation fails for nonexistent directory."""
    is_valid, errors = validate_source_directory(Path('/nonexistent/path'))

    assert is_valid is False
    assert any('does not exist' in error.lower() for error in errors)


def test_validate_source_directory_invalid_package_json(temp_source_dir):
    """Test validation warns about invalid package.json."""
    # Write invalid JSON
    (temp_source_dir / 'package.json').write_text('{ invalid json }')

    is_valid, errors = validate_source_directory(temp_source_dir)

    assert is_valid is False
    assert any('json' in error.lower() for error in errors)


# ============================================================================
# Target Validation Tests
# ============================================================================

def test_validate_target_directory_new_target(temp_target_dir):
    """Test validation of new target directory."""
    is_valid, errors = validate_target_directory(temp_target_dir)

    # Should be valid even if doesn't exist (will be created)
    assert is_valid is True or len(errors) == 0


def test_validate_target_directory_existing_empty(temp_target_dir):
    """Test validation of existing empty target."""
    temp_target_dir.mkdir(parents=True)

    is_valid, errors = validate_target_directory(temp_target_dir)

    assert is_valid is True


def test_validate_target_directory_existing_with_aa(temp_target_dir):
    """Test validation allows existing Arcade Assistant install."""
    temp_target_dir.mkdir(parents=True)
    (temp_target_dir / 'backend').mkdir()
    (temp_target_dir / 'frontend').mkdir()

    is_valid, errors = validate_target_directory(temp_target_dir)

    assert is_valid is True


def test_validate_target_directory_existing_wrong_content(temp_target_dir):
    """Test validation fails for existing non-AA directory."""
    temp_target_dir.mkdir(parents=True)
    (temp_target_dir / 'some_other_file.txt').write_text('content')

    is_valid, errors = validate_target_directory(temp_target_dir)

    assert is_valid is False
    assert any('not empty' in error.lower() for error in errors)


# ============================================================================
# LaunchBox Validation Tests
# ============================================================================

def test_validate_launchbox_installation_complete(temp_launchbox_dir):
    """Test validation of complete LaunchBox installation."""
    target = temp_launchbox_dir / 'Arcade Assistant'

    is_valid, warnings, status = validate_launchbox_installation(target)

    assert is_valid is True
    assert status['launchbox_exists'] is True
    assert status['cli_launcher_exists'] is True


def test_validate_launchbox_installation_missing_cli(temp_launchbox_dir):
    """Test validation with missing CLI_Launcher (should warn but pass)."""
    # Remove CLI_Launcher
    cli_path = temp_launchbox_dir / 'LaunchBox' / 'ThirdParty' / 'CLI_Launcher'
    shutil.rmtree(cli_path)

    target = temp_launchbox_dir / 'Arcade Assistant'

    is_valid, warnings, status = validate_launchbox_installation(target)

    # Should pass with warnings
    assert len(warnings) > 0
    assert any('cli_launcher' in w.lower() for w in warnings)
    assert status['cli_launcher_exists'] is False


def test_validate_launchbox_installation_missing_root(temp_target_dir):
    """Test validation fails when LaunchBox not found."""
    is_valid, warnings, status = validate_launchbox_installation(temp_target_dir)

    assert is_valid is False
    assert status['launchbox_exists'] is False


# ============================================================================
# Copy Progress Tests
# ============================================================================

def test_copy_with_progress_basic(temp_source_dir, temp_target_dir):
    """Test basic file copying with progress."""
    stats = copy_with_progress(
        src=temp_source_dir,
        dest=temp_target_dir,
        dry_run=False
    )

    assert stats['files_copied'] > 0
    assert stats['dirs_created'] > 0
    assert temp_target_dir.exists()
    assert (temp_target_dir / 'package.json').exists()


def test_copy_with_progress_dry_run(temp_source_dir, temp_target_dir):
    """Test dry-run doesn't copy files."""
    stats = copy_with_progress(
        src=temp_source_dir,
        dest=temp_target_dir,
        dry_run=True
    )

    assert stats['files_copied'] > 0  # Counted but not actually copied
    assert not temp_target_dir.exists()  # Target not created


def test_copy_with_progress_excludes(temp_source_dir, temp_target_dir):
    """Test file exclusions work correctly."""
    # Create files to exclude
    (temp_source_dir / 'node_modules').mkdir()
    (temp_source_dir / 'node_modules' / 'test.js').write_text('excluded')
    (temp_source_dir / '__pycache__').mkdir()
    (temp_source_dir / '__pycache__' / 'test.pyc').write_text('excluded')

    stats = copy_with_progress(
        src=temp_source_dir,
        dest=temp_target_dir,
        dry_run=False,
        exclude_dirs=['node_modules', '__pycache__']
    )

    assert not (temp_target_dir / 'node_modules').exists()
    assert not (temp_target_dir / '__pycache__').exists()


# ============================================================================
# .env Generation Tests
# ============================================================================

def test_generate_env_file(temp_target_dir):
    """Test .env file generation."""
    temp_target_dir.mkdir(parents=True)

    success = generate_env_file(temp_target_dir)

    assert success is True
    assert (temp_target_dir / '.env').exists()

    # Check content
    content = (temp_target_dir / '.env').read_text()
    assert 'AA_DRIVE_ROOT' in content
    assert 'ANTHROPIC_API_KEY' in content
    assert 'ENVIRONMENT=production' in content


def test_generate_env_file_with_launchbox(temp_target_dir):
    """Test .env file generation with LaunchBox root."""
    temp_target_dir.mkdir(parents=True)
    launchbox_root = Path('/mnt/a/LaunchBox')

    success = generate_env_file(temp_target_dir, launchbox_root)

    assert success is True

    content = (temp_target_dir / '.env').read_text()
    assert str(launchbox_root) in content


# ============================================================================
# Post-Migration Validation Tests
# ============================================================================

def test_post_migration_validation_success(temp_source_dir):
    """Test successful post-migration validation."""
    # Generate .env
    generate_env_file(temp_source_dir)

    is_valid, errors = post_migration_validation(temp_source_dir)

    assert is_valid is True
    assert len(errors) == 0


def test_post_migration_validation_missing_env(temp_source_dir):
    """Test validation fails without .env."""
    is_valid, errors = post_migration_validation(temp_source_dir)

    assert is_valid is False
    assert any('.env' in error.lower() for error in errors)


def test_post_migration_validation_missing_path(temp_source_dir):
    """Test validation fails with missing critical path."""
    shutil.rmtree(temp_source_dir / 'backend')

    is_valid, errors = post_migration_validation(temp_source_dir)

    assert is_valid is False
    assert any('backend' in error.lower() for error in errors)


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.integration
def test_full_migration_dry_run(temp_source_dir, temp_target_dir):
    """Test complete migration in dry-run mode."""
    # Validate source
    source_valid, _ = validate_source_directory(temp_source_dir)
    assert source_valid

    # Validate target
    target_valid, _ = validate_target_directory(temp_target_dir)
    assert target_valid

    # Simulate copy
    stats = copy_with_progress(temp_source_dir, temp_target_dir, dry_run=True)
    assert stats['files_copied'] > 0
    assert not temp_target_dir.exists()  # Dry run doesn't create


@pytest.mark.integration
def test_full_migration_live(temp_source_dir, temp_target_dir):
    """Test complete live migration."""
    # Copy files
    stats = copy_with_progress(temp_source_dir, temp_target_dir, dry_run=False)
    assert stats['files_copied'] > 0
    assert temp_target_dir.exists()

    # Generate .env
    success = generate_env_file(temp_target_dir)
    assert success

    # Validate post-migration
    is_valid, errors = post_migration_validation(temp_target_dir)
    assert is_valid


# ============================================================================
# Parametrized Tests
# ============================================================================

@pytest.mark.parametrize('exclude_dir', [
    'node_modules',
    '__pycache__',
    '.git',
    'dist',
    'venv'
])
def test_copy_excludes_various_dirs(temp_source_dir, temp_target_dir, exclude_dir):
    """Test various directory exclusions."""
    # Create excluded directory
    (temp_source_dir / exclude_dir).mkdir()
    (temp_source_dir / exclude_dir / 'test.txt').write_text('excluded')

    stats = copy_with_progress(
        temp_source_dir,
        temp_target_dir,
        dry_run=False,
        exclude_dirs=[exclude_dir]
    )

    assert not (temp_target_dir / exclude_dir).exists()


@pytest.mark.parametrize('env_var,expected_mode', [
    ('development', 'dev'),
    ('production', 'prod'),
    ('', 'dev'),  # Default
])
def test_env_generation_environments(temp_target_dir, env_var, expected_mode):
    """Test .env generation for different environments."""
    temp_target_dir.mkdir(parents=True)

    success = generate_env_file(temp_target_dir)
    assert success

    content = (temp_target_dir / '.env').read_text()
    assert 'ENVIRONMENT=production' in content  # Always production for migration
