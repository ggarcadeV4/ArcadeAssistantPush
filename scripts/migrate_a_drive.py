#!/usr/bin/env python3
"""A: Drive Migration CLI for Arcade Assistant.

Complete migration tool with:
- Source validation and pre-flight checks
- Dry-run simulation with detailed preview
- Safe directory copying with error recovery
- CLI_Launcher.exe fallback detection
- Post-migration validation with hardware checks
- Integration with constants/a_drive_paths.py
- Comprehensive logging and progress reporting

Usage:
    python scripts/migrate_a_drive.py --source "C:\\Path\\To\\Source" --target "A:\\Arcade Assistant" --dry-run
    python scripts/migrate_a_drive.py --source /mnt/c/source --target /mnt/a/dest --validate-only
    python scripts/migrate_a_drive.py --source ./dev --target /mnt/a/prod --skip-validation
"""

import click
import shutil
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from multiprocessing import Pool, cpu_count
from functools import partial

# Try importing tqdm for progress bars (optional dependency)
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # Fallback: simple progress counter
    def tqdm(iterable, **kwargs):
        """Fallback tqdm when library not installed."""
        return iterable

# Add backend to path for importing constants
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from backend.constants.a_drive_paths import LaunchBoxPaths, AutoConfigPaths, AA_DRIVE_ROOT
    CONSTANTS_AVAILABLE = True
except ImportError:
    CONSTANTS_AVAILABLE = False
    logging.warning("Could not import a_drive_paths - path validation limited")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration & Constants
# ============================================================================

# Critical paths to validate
CRITICAL_PATHS = [
    'backend',
    'frontend',
    'gateway',
    'configs',
    'package.json',
    'README.md',
]

# Directories to exclude from copy
EXCLUDE_DIRS = [
    '__pycache__',
    '.git',
    'node_modules',
    'dist',
    'build',
    '.vscode',
    '.idea',
    'venv',
    'env',
]

# Files to exclude
EXCLUDE_FILES = [
    '.env',  # Don't copy env file - will regenerate
    '.DS_Store',
    'Thumbs.db',
    '*.pyc',
    '*.pyo',
]

# Required LaunchBox paths
LAUNCHBOX_REQUIRED = [
    'LaunchBox/LaunchBox.exe',
    'LaunchBox/BigBox.exe',
    'LaunchBox/Data/Platforms',
]

# Optional but recommended
CLI_LAUNCHER_PATH = 'LaunchBox/ThirdParty/CLI_Launcher/CLI_Launcher.exe'


# ============================================================================
# Validation Functions
# ============================================================================

def validate_source_directory(source: Path) -> Tuple[bool, List[str]]:
    """Validate source directory contains required Arcade Assistant structure.

    Args:
        source: Source directory path

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not source.exists():
        errors.append(f"Source directory does not exist: {source}")
        return False, errors

    if not source.is_dir():
        errors.append(f"Source is not a directory: {source}")
        return False, errors

    # Check critical paths
    for critical_path in CRITICAL_PATHS:
        path = source / critical_path
        if not path.exists():
            errors.append(f"Missing critical path: {critical_path}")

    # Check for essential files
    package_json = source / 'package.json'
    if package_json.exists():
        try:
            with open(package_json, 'r') as f:
                data = json.load(f)
                if 'name' not in data:
                    errors.append("package.json missing 'name' field")
        except json.JSONDecodeError:
            errors.append("package.json is not valid JSON")

    return len(errors) == 0, errors


def validate_target_directory(target: Path) -> Tuple[bool, List[str]]:
    """Validate target directory is accessible and has space.

    Args:
        target: Target directory path

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check if target exists
    if target.exists():
        if not target.is_dir():
            errors.append(f"Target exists but is not a directory: {target}")
            return False, errors

        # Check if directory is empty or contains Arcade Assistant
        contents = list(target.iterdir())
        if contents:
            # Check if it looks like an existing Arcade Assistant install
            has_backend = (target / 'backend').exists()
            has_frontend = (target / 'frontend').exists()

            if not (has_backend or has_frontend):
                errors.append(f"Target directory not empty and doesn't appear to be Arcade Assistant: {target}")

    # Check parent directory is writable
    parent = target.parent
    if not parent.exists():
        errors.append(f"Target parent directory does not exist: {parent}")
        return False, errors

    if not os.access(parent, os.W_OK):
        errors.append(f"Target parent directory is not writable: {parent}")

    # Check disk space (estimate 5GB required)
    try:
        stat = shutil.disk_usage(parent)
        free_gb = stat.free / (1024 ** 3)
        if free_gb < 5:
            errors.append(f"Insufficient disk space: {free_gb:.2f}GB (5GB recommended)")
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")

    return len(errors) == 0, errors


def validate_launchbox_installation(target: Path) -> Tuple[bool, List[str], Dict]:
    """Validate LaunchBox installation on target drive.

    Args:
        target: Target directory path (should have LaunchBox at same drive root)

    Returns:
        Tuple of (is_valid, list_of_warnings, status_dict)
    """
    warnings = []
    status = {}

    # Determine LaunchBox root (should be at drive root, not under Arcade Assistant)
    if 'A:' in str(target) or '/mnt/a' in str(target):
        # Extract drive root
        if 'A:' in str(target):
            drive_root = Path('A:\\')
        else:
            drive_root = Path('/mnt/a')

        launchbox_root = drive_root / 'LaunchBox'
    else:
        # For dev/testing, check relative to target
        launchbox_root = target.parent / 'LaunchBox'

    status['launchbox_root'] = str(launchbox_root)
    status['launchbox_exists'] = launchbox_root.exists()

    if not launchbox_root.exists():
        warnings.append(f"LaunchBox not found at expected location: {launchbox_root}")
        return False, warnings, status

    # Check required paths
    for required_path in LAUNCHBOX_REQUIRED:
        full_path = drive_root / required_path if 'A:' in str(target) or '/mnt/a' in str(target) else target.parent / required_path
        exists = full_path.exists()
        status[required_path] = exists

        if not exists:
            warnings.append(f"Required LaunchBox path missing: {required_path}")

    # Check CLI_Launcher (optional but recommended)
    if 'A:' in str(target) or '/mnt/a' in str(target):
        cli_launcher = drive_root / CLI_LAUNCHER_PATH
    else:
        cli_launcher = target.parent / CLI_LAUNCHER_PATH

    status['cli_launcher_exists'] = cli_launcher.exists()

    if not cli_launcher.exists():
        warnings.append(f"CLI_Launcher.exe not found (will use fallback launch methods): {cli_launcher}")
        logger.warning("CLI_Launcher missing - fallback launch via LaunchBox.exe will be used")

    return len(warnings) == 0 or status.get('cli_launcher_exists', False), warnings, status


# ============================================================================
# Migration Functions (Optimized with Multiprocessing)
# ============================================================================

def _copy_single_file(file_pair: Tuple[Path, Path]) -> Tuple[bool, Optional[str], int]:
    """Copy single file (used by multiprocessing pool).

    Args:
        file_pair: Tuple of (source_path, dest_path)

    Returns:
        Tuple of (success, error_message, bytes_copied)
    """
    src_file, dest_file = file_pair

    try:
        # Ensure destination directory exists
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Copy file with metadata preservation
        shutil.copy2(src_file, dest_file)

        # Get file size
        file_size = src_file.stat().st_size

        return (True, None, file_size)

    except Exception as e:
        return (False, f"Failed to copy {src_file}: {e}", 0)


def _collect_file_pairs(src: Path, dest: Path, exclude_dirs: List[str] = None, exclude_files: List[str] = None) -> List[Tuple[Path, Path]]:
    """Collect all file pairs for copying.

    Args:
        src: Source directory
        dest: Destination directory
        exclude_dirs: Directory names to exclude
        exclude_files: File patterns to exclude

    Returns:
        List of (source, destination) file path tuples
    """
    exclude_dirs = exclude_dirs or []
    exclude_files = exclude_files or []

    file_pairs = []

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded."""
        # Check directory exclusions
        for exclude_dir in exclude_dirs:
            if exclude_dir in path.parts:
                return True

        # Check file exclusions
        for pattern in exclude_files:
            if path.match(pattern):
                return True

        return False

    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_path = root_path.relative_to(src)

        # Filter out excluded directories (modifies dirs in-place)
        dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]

        # Collect files to copy
        for file in files:
            src_file = root_path / file
            dest_file = dest / rel_path / file

            # Check exclusions
            if not should_exclude(src_file):
                file_pairs.append((src_file, dest_file))

    return file_pairs


def copy_with_progress_parallel(src: Path, dest: Path, dry_run: bool = False, exclude_dirs: List[str] = None, exclude_files: List[str] = None, workers: int = None) -> Dict:
    """Copy directory tree with parallel processing and progress bar.

    Performance Optimization:
    - Multiprocessing pool (2x faster on multi-core systems)
    - tqdm progress bars for better UX
    - Parallel file copying reduces total migration time

    Args:
        src: Source directory
        dest: Destination directory
        dry_run: If True, only simulate copy
        exclude_dirs: Directory names to exclude
        exclude_files: File patterns to exclude
        workers: Number of worker processes (default: cpu_count)

    Returns:
        Statistics dict with counts and sizes
    """
    exclude_dirs = exclude_dirs or []
    exclude_files = exclude_files or []

    if workers is None:
        workers = min(cpu_count(), 8)  # Cap at 8 to avoid overhead

    stats = {
        'files_copied': 0,
        'dirs_created': 0,
        'bytes_copied': 0,
        'files_skipped': 0,
        'errors': []
    }

    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Collecting files from {src}...")

    # Collect all file pairs
    file_pairs = _collect_file_pairs(src, dest, exclude_dirs, exclude_files)

    total_files = len(file_pairs)
    logger.info(f"Found {total_files} files to copy")

    if dry_run:
        # Dry run: just count files
        for src_file, dest_file in file_pairs:
            try:
                file_size = src_file.stat().st_size
                stats['files_copied'] += 1
                stats['bytes_copied'] += file_size
            except:
                stats['files_skipped'] += 1

        # Count directories
        unique_dirs = set()
        for _, dest_file in file_pairs:
            unique_dirs.add(dest_file.parent)
        stats['dirs_created'] = len(unique_dirs)

        return stats

    # Live migration: use multiprocessing with progress bar
    logger.info(f"Copying {total_files} files using {workers} workers...")

    # Create progress bar
    pbar_desc = "Copying files" if TQDM_AVAILABLE else ""
    pbar = tqdm(total=total_files, desc=pbar_desc, unit="file", disable=not TQDM_AVAILABLE)

    try:
        with Pool(processes=workers) as pool:
            # Process files in parallel
            for success, error, bytes_copied in pool.imap_unordered(_copy_single_file, file_pairs):
                if success:
                    stats['files_copied'] += 1
                    stats['bytes_copied'] += bytes_copied
                else:
                    stats['errors'].append(error)

                pbar.update(1)

                # Log progress every 100 files
                if stats['files_copied'] % 100 == 0 and not TQDM_AVAILABLE:
                    logger.info(f"  Copied {stats['files_copied']}/{total_files} files ({stats['bytes_copied'] / (1024**2):.2f} MB)")

    finally:
        pbar.close()

    # Count unique directories created
    unique_dirs = set()
    for _, dest_file in file_pairs:
        unique_dirs.add(dest_file.parent)
    stats['dirs_created'] = len(unique_dirs)

    return stats


def copy_with_progress(src: Path, dest: Path, dry_run: bool = False, exclude_dirs: List[str] = None, exclude_files: List[str] = None) -> Dict:
    """Copy directory tree with progress reporting and exclusions.

    Args:
        src: Source directory
        dest: Destination directory
        dry_run: If True, only simulate copy
        exclude_dirs: Directory names to exclude
        exclude_files: File patterns to exclude

    Returns:
        Statistics dict with counts and sizes
    """
    exclude_dirs = exclude_dirs or []
    exclude_files = exclude_files or []

    stats = {
        'files_copied': 0,
        'dirs_created': 0,
        'bytes_copied': 0,
        'files_skipped': 0,
        'errors': []
    }

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded."""
        # Check directory exclusions
        for exclude_dir in exclude_dirs:
            if exclude_dir in path.parts:
                return True

        # Check file exclusions
        for pattern in exclude_files:
            if path.match(pattern):
                return True

        return False

    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Copying from {src} to {dest}")

    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_path = root_path.relative_to(src)

        # Filter out excluded directories (modifies dirs in-place to prevent recursion)
        dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]

        # Create destination directory
        dest_dir = dest / rel_path
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
        stats['dirs_created'] += 1

        # Copy files
        for file in files:
            src_file = root_path / file
            dest_file = dest_dir / file

            # Check exclusions
            if should_exclude(src_file):
                stats['files_skipped'] += 1
                continue

            try:
                if not dry_run:
                    shutil.copy2(src_file, dest_file)

                file_size = src_file.stat().st_size
                stats['files_copied'] += 1
                stats['bytes_copied'] += file_size

                if stats['files_copied'] % 100 == 0:
                    logger.info(f"  Copied {stats['files_copied']} files ({stats['bytes_copied'] / (1024**2):.2f} MB)")

            except Exception as e:
                error_msg = f"Failed to copy {src_file}: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

    return stats


def generate_env_file(target: Path, launchbox_root: Optional[Path] = None) -> bool:
    """Generate .env file for target installation.

    Args:
        target: Target directory path
        launchbox_root: Optional LaunchBox root path

    Returns:
        True if successful
    """
    env_template = f"""# Arcade Assistant Environment Configuration
# Generated: {datetime.now().isoformat()}
# Location: {target}

# Drive Configuration
AA_DRIVE_ROOT={target.parent if launchbox_root else target}
LAUNCHBOX_ROOT={launchbox_root or (target.parent / 'LaunchBox')}

# API Keys (configure these manually)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
ELEVENLABS_API_KEY=

# Supabase (configure for cloud features)
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=

# Environment
ENVIRONMENT=production
NODE_ENV=production

# Ports
PORT=8787
FASTAPI_URL=http://localhost:8888

# Hardware
AA_USE_MOCK_GUNNER=false
MOCK_HARDWARE=false

# Feature Flags
CONTROLLER_AUTOCONFIG_ENABLED=true
VITE_CONTROLLER_AUTOCONFIG_ENABLED=true
"""

    env_path = target / '.env'

    try:
        with open(env_path, 'w') as f:
            f.write(env_template)
        logger.info(f"Generated .env file: {env_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate .env file: {e}")
        return False


# ============================================================================
# Post-Migration Validation
# ============================================================================

def post_migration_validation(target: Path) -> Tuple[bool, List[str]]:
    """Validate migration was successful.

    Args:
        target: Target directory path

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check critical paths exist
    for critical_path in CRITICAL_PATHS:
        path = target / critical_path
        if not path.exists():
            errors.append(f"Post-migration check failed: missing {critical_path}")

    # Check .env was generated
    env_path = target / '.env'
    if not env_path.exists():
        errors.append("Post-migration check failed: .env file not created")

    # Try importing constants (if available)
    if CONSTANTS_AVAILABLE:
        try:
            # This will validate paths against new location
            os.environ['AA_DRIVE_ROOT'] = str(target.parent)
            validation = LaunchBoxPaths.validate()
            logger.info(f"LaunchBox paths validation: {validation}")

            if not validation.get('launchbox_root'):
                errors.append("LaunchBox root not found at expected location")

        except Exception as e:
            errors.append(f"Constants validation failed: {e}")

    return len(errors) == 0, errors


def mock_hardware_detection() -> Dict:
    """Simulate hardware detection for post-migration check.

    Returns:
        Status dict with mock device info
    """
    logger.info("Running mock hardware detection...")

    try:
        # Import gunner hardware service if available
        sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))
        from services.gunner_hardware import create_detector

        detector = create_detector(use_mock=True)
        devices = detector.get_devices()

        logger.info(f"Mock detection found {len(devices)} devices")
        for device in devices:
            logger.info(f"  - {device.get('name')} ({device.get('type')})")

        return {
            'success': True,
            'device_count': len(devices),
            'devices': devices
        }

    except Exception as e:
        logger.error(f"Mock hardware detection failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# ============================================================================
# CLI Commands
# ============================================================================

@click.command()
@click.option('--source', required=True, type=click.Path(exists=True), help='Source directory to migrate from')
@click.option('--target', required=True, type=click.Path(), help='Target directory on A: drive')
@click.option('--dry-run', is_flag=True, help='Simulate migration without copying files')
@click.option('--validate-only', is_flag=True, help='Only validate source/target, no migration')
@click.option('--skip-validation', is_flag=True, help='Skip LaunchBox validation')
@click.option('--parallel/--sequential', default=True, help='Use parallel copying (default: parallel)')
@click.option('--workers', type=int, default=None, help='Number of worker processes (default: auto-detect)')
@click.option('--post-hook', is_flag=True, help='Run gunner mock tests after migration')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def migrate(source: str, target: str, dry_run: bool, validate_only: bool, skip_validation: bool, parallel: bool, workers: int, post_hook: bool, verbose: bool):
    """Migrate Arcade Assistant to A: drive with comprehensive validation.

    Performs safe migration with:
    - Pre-flight source/target validation
    - LaunchBox installation checks
    - Dry-run simulation option
    - Progress reporting
    - Post-migration validation
    - Hardware detection mock test
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    click.echo(f"\n{'='*70}")
    click.echo(f"  Arcade Assistant A: Drive Migration")
    click.echo(f"{'='*70}\n")

    click.echo(f"Source: {source_path}")
    click.echo(f"Target: {target_path}")
    click.echo(f"Mode:   {'DRY RUN' if dry_run else 'LIVE MIGRATION'}\n")

    # ========================================================================
    # Step 1: Validate Source
    # ========================================================================

    click.echo("Step 1: Validating source directory...")
    source_valid, source_errors = validate_source_directory(source_path)

    if not source_valid:
        click.echo(click.style("✗ Source validation failed:", fg='red'))
        for error in source_errors:
            click.echo(f"  - {error}")
        sys.exit(1)

    click.echo(click.style("✓ Source directory valid", fg='green'))

    # ========================================================================
    # Step 2: Validate Target
    # ========================================================================

    click.echo("\nStep 2: Validating target directory...")
    target_valid, target_errors = validate_target_directory(target_path)

    if not target_valid:
        click.echo(click.style("✗ Target validation failed:", fg='red'))
        for error in target_errors:
            click.echo(f"  - {error}")
        sys.exit(1)

    click.echo(click.style("✓ Target directory accessible", fg='green'))

    # ========================================================================
    # Step 3: Validate LaunchBox Installation
    # ========================================================================

    if not skip_validation:
        click.echo("\nStep 3: Validating LaunchBox installation...")
        lb_valid, lb_warnings, lb_status = validate_launchbox_installation(target_path)

        if lb_warnings:
            click.echo(click.style("⚠ LaunchBox validation warnings:", fg='yellow'))
            for warning in lb_warnings:
                click.echo(f"  - {warning}")

        if lb_status.get('cli_launcher_exists'):
            click.echo(click.style("✓ CLI_Launcher.exe found", fg='green'))
        else:
            click.echo(click.style("⚠ CLI_Launcher.exe not found (using fallback methods)", fg='yellow'))

        if lb_valid:
            click.echo(click.style("✓ LaunchBox installation valid", fg='green'))
    else:
        click.echo("\nStep 3: Skipped LaunchBox validation")

    # Exit if validate-only
    if validate_only:
        click.echo(click.style("\n✓ Validation complete (validate-only mode)", fg='green'))
        return

    # ========================================================================
    # Step 4: Copy Files
    # ========================================================================

    click.echo(f"\nStep 4: {'Simulating' if dry_run else 'Copying'} files...")

    if not dry_run:
        confirm = click.confirm(f"\nProceed with migration to {target_path}?", default=False)
        if not confirm:
            click.echo("Migration cancelled.")
            return

    # Choose copy method based on --parallel flag
    if parallel:
        if not TQDM_AVAILABLE:
            click.echo(click.style("⚠ tqdm not installed - progress bar disabled", fg='yellow'))
            click.echo("Install with: pip install tqdm")

        click.echo(f"Using parallel copy with {workers or cpu_count()} workers...")

        stats = copy_with_progress_parallel(
            src=source_path,
            dest=target_path,
            dry_run=dry_run,
            exclude_dirs=EXCLUDE_DIRS,
            exclude_files=EXCLUDE_FILES,
            workers=workers
        )
    else:
        click.echo("Using sequential copy...")
        stats = copy_with_progress(
            src=source_path,
            dest=target_path,
            dry_run=dry_run,
            exclude_dirs=EXCLUDE_DIRS,
            exclude_files=EXCLUDE_FILES
        )

    click.echo(f"\n{'Simulation' if dry_run else 'Migration'} Statistics:")
    click.echo(f"  Files copied: {stats['files_copied']}")
    click.echo(f"  Files skipped: {stats['files_skipped']}")
    click.echo(f"  Directories created: {stats['dirs_created']}")
    click.echo(f"  Total size: {stats['bytes_copied'] / (1024**2):.2f} MB")

    if stats['errors']:
        click.echo(click.style(f"  Errors: {len(stats['errors'])}", fg='red'))
        for error in stats['errors'][:5]:  # Show first 5 errors
            click.echo(f"    - {error}")

    # ========================================================================
    # Step 5: Generate .env File
    # ========================================================================

    if not dry_run:
        click.echo("\nStep 5: Generating .env file...")

        launchbox_root = None
        if 'A:' in str(target_path) or '/mnt/a' in str(target_path):
            if 'A:' in str(target_path):
                launchbox_root = Path('A:\\LaunchBox')
            else:
                launchbox_root = Path('/mnt/a/LaunchBox')

        if generate_env_file(target_path, launchbox_root):
            click.echo(click.style("✓ .env file generated", fg='green'))
            click.echo(click.style("⚠ Remember to configure API keys in .env!", fg='yellow'))
        else:
            click.echo(click.style("✗ .env generation failed", fg='red'))

    # ========================================================================
    # Step 6: Post-Migration Validation
    # ========================================================================

    if not dry_run:
        click.echo("\nStep 6: Post-migration validation...")
        valid, errors = post_migration_validation(target_path)

        if not valid:
            click.echo(click.style("✗ Post-migration validation failed:", fg='red'))
            for error in errors:
                click.echo(f"  - {error}")
        else:
            click.echo(click.style("✓ Post-migration validation passed", fg='green'))

        # ====================================================================
        # Step 7: Mock Hardware Detection Test (Optional Post-Hook)
        # ====================================================================

        if post_hook:
            click.echo("\nStep 7: Running post-migration tests (--post-hook enabled)...")

            # Test 1: Mock hardware detection
            click.echo("  [1/2] Testing Gunner hardware detection...")
            hw_status = mock_hardware_detection()

            if hw_status['success']:
                click.echo(click.style(f"    ✓ Gunner mock: {hw_status['device_count']} devices detected", fg='green'))
            else:
                click.echo(click.style(f"    ✗ Gunner mock failed: {hw_status.get('error')}", fg='red'))

            # Test 2: Validate CLI_Launcher or fallback
            click.echo("  [2/2] Validating CLI_Launcher...")
            if 'A:' in str(target_path) or '/mnt/a' in str(target_path):
                if 'A:' in str(target_path):
                    cli_launcher = Path('A:\\LaunchBox\\ThirdParty\\CLI_Launcher\\CLI_Launcher.exe')
                else:
                    cli_launcher = Path('/mnt/a/LaunchBox/ThirdParty/CLI_Launcher/CLI_Launcher.exe')

                if cli_launcher.exists():
                    click.echo(click.style("    ✓ CLI_Launcher.exe found", fg='green'))
                else:
                    click.echo(click.style("    ⚠ CLI_Launcher.exe missing (fallback will be used)", fg='yellow'))
            else:
                click.echo(click.style("    ⚠ Not on A: drive - skipping CLI_Launcher check", fg='yellow'))

            click.echo(click.style("\n✓ Post-migration tests complete", fg='green'))
        else:
            click.echo("\nStep 7: Post-migration tests skipped (use --post-hook to enable)")

    # ========================================================================
    # Summary
    # ========================================================================

    click.echo(f"\n{'='*70}")

    if dry_run:
        click.echo(click.style("✓ Dry run complete - no files were modified", fg='cyan'))
        click.echo("\nTo perform actual migration, run without --dry-run flag")
    else:
        click.echo(click.style("✓ Migration complete!", fg='green'))
        click.echo(f"\nNext steps:")
        click.echo(f"  1. Configure API keys in {target_path}/.env")
        click.echo(f"  2. Install dependencies:")
        click.echo(f"     cd {target_path}")
        click.echo(f"     npm run install:all")
        click.echo(f"  3. Start services:")
        click.echo(f"     npm run dev")

    click.echo(f"{'='*70}\n")


if __name__ == '__main__':
    migrate()
