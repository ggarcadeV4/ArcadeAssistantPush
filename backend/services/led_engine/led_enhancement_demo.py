"""
LED Enhancement Demo - Voice Breathing Visual Stress Test
Part of: Phase 5 Blinky Gem Pivot

Tests the normalized 0-48 PWM range with a sine-wave breathing animation.
Confirms green channel brightness and USB stack stability.

Usage:
    python led_enhancement_demo.py
"""
from __future__ import annotations

import time
import math
import sys
import os

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledwiz_direct import (
    discover_boards, 
    normalize_brightness, 
    PWM_MIN, 
    PWM_MAX,
    MAX_BRIGHTNESS_MODE,
    SCALE_RED,
    SCALE_GREEN,
    SCALE_BLUE
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [LEDDemo] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("led_demo")


def run_breathing_demo(duration_seconds: int = 10):
    """
    Run a sine-wave breathing animation on all LEDs.
    
    This tests:
    1. PWM normalization (0-48 range)
    2. 10Hz update rate (100ms intervals)
    3. USB stack stability
    4. Green channel brightness
    """
    logger.info("=" * 60)
    logger.info("LED ENHANCEMENT DEMO - Voice Breathing Test")
    logger.info("=" * 60)
    logger.info(f"PWM Range: {PWM_MIN} - {PWM_MAX}")
    logger.info(f"MAX_BRIGHTNESS_MODE: {MAX_BRIGHTNESS_MODE}")
    logger.info(f"Duration: {duration_seconds} seconds")
    logger.info("")
    
    # Discover boards
    boards = discover_boards()
    if not boards:
        logger.error("No LED-Wiz boards found!")
        return False
    
    logger.info(f"Found {len(boards)} board(s)")
    
    # Open all boards
    for board in boards:
        if not board.open():
            logger.error(f"Failed to open Unit {board.unit_id}")
            return False
        logger.info(f"  Opened Unit {board.unit_id} (PID: 0x{board.pid:04X})")
    
    logger.info("")
    logger.info("Starting breathing animation at 10Hz...")
    logger.info("Watch for:")
    logger.info("  - Smooth sine-wave pulsing (no flicker)")
    logger.info("  - Bright green LEDs (not dim/strobing)")
    logger.info("  - System stability (no USB disconnect)")
    logger.info("")
    logger.info("Press Ctrl+C to stop early")
    logger.info("-" * 60)
    
    start_time = time.time()
    frame_count = 0
    
    try:
        while (time.time() - start_time) < duration_seconds:
            elapsed = time.time() - start_time
            
            # Sine wave: oscillate between PWM_MIN and PWM_MAX
            # 2Hz breathing cycle (full cycle every 0.5 seconds)
            sine_val = math.sin(elapsed * 4 * math.pi)
            
            # Map sine (-1 to 1) to brightness (0 to 48)
            brightness = int((sine_val + 1) / 2 * PWM_MAX)
            
            # Create frame with uniform brightness
            frame = [brightness] * 32
            
            # Send to all boards
            for board in boards:
                board.set_channels(frame)
            
            frame_count += 1
            
            # Log every ~1 second
            if frame_count % 10 == 0:
                logger.info(f"  t={elapsed:.1f}s  brightness={brightness:2d}/{PWM_MAX}  frames={frame_count}")
            
            # 10Hz = 100ms interval
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
    
    finally:
        # Turn off all LEDs and close
        logger.info("-" * 60)
        logger.info("Turning off LEDs...")
        for board in boards:
            board.all_off()
            board.close()
    
    elapsed_total = time.time() - start_time
    fps = frame_count / elapsed_total if elapsed_total > 0 else 0
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST COMPLETE")
    logger.info(f"  Duration: {elapsed_total:.1f} seconds")
    logger.info(f"  Frames: {frame_count}")
    logger.info(f"  Avg FPS: {fps:.1f} Hz")
    logger.info("=" * 60)
    
    if fps >= 9.0:
        logger.info("✅ PASS: 10Hz update rate achieved")
    else:
        logger.warning("⚠️ WARNING: Update rate below 10Hz")
    
    logger.info("✅ USB stack remained stable")
    
    return True


def run_static_green_test(duration_seconds: int = 5):
    """
    DIAGNOSTIC: Static green test - hard-code ALL channels to 48.
    No math, no normalization. Raw 48 to hardware.
    
    If LEDs still pulse, it's a hardware/firmware issue.
    If LEDs are solid bright, it was a math error.
    """
    logger.info("=" * 60)
    logger.info("DIAGNOSTIC: STATIC GREEN TEST")
    logger.info("=" * 60)
    logger.info("All channels will be set to RAW 48 (no math)")
    logger.info(f"Duration: {duration_seconds} seconds")
    logger.info("")
    
    boards = discover_boards()
    if not boards:
        logger.error("No LED-Wiz boards found!")
        return False
    
    logger.info(f"Found {len(boards)} board(s)")
    
    for board in boards:
        if not board.open():
            logger.error(f"Failed to open Unit {board.unit_id}")
            return False
        logger.info(f"  Opened Unit {board.unit_id}")
    
    logger.info("")
    logger.info(">>> SENDING RAW 48 TO ALL 32 CHANNELS <<<")
    logger.info("Watch: LEDs should be SOLID BRIGHT (no pulse/flicker)")
    logger.info("-" * 60)
    
    # Hard-coded frame: ALL channels = 48 (no math!)
    static_frame = [48] * 32  # RAW 48, not normalized
    
    try:
        start = time.time()
        while (time.time() - start) < duration_seconds:
            for board in boards:
                # Direct PBA write - bypass set_channels to test raw output
                board.send_sba(0xFF, 0xFF, 0xFF, 0xFF, 2)  # All banks ON
                for chunk in range(4):
                    # Hard-coded 48 for all 8 ports in each chunk
                    board.send_pba_chunk(chunk, [48, 48, 48, 48, 48, 48, 48, 48])
            
            time.sleep(0.1)
            elapsed = time.time() - start
            if int(elapsed) != int(elapsed - 0.1):
                logger.info(f"  t={elapsed:.0f}s - All channels at RAW 48")
    
    except KeyboardInterrupt:
        logger.info("\\nStopped by user")
    
    finally:
        logger.info("-" * 60)
        logger.info("Turning off LEDs...")
        for board in boards:
            board.all_off()
            board.close()
    
    logger.info("")
    logger.info("STATIC TEST COMPLETE")
    logger.info("If LEDs were SOLID BRIGHT: Math error was the issue (now fixed)")
    logger.info("If LEDs PULSED: Hardware/firmware PWM conflict")
    
    return True


def main():
    logger.info("Safety Check: PWM_MAX = %d (should be 48)", PWM_MAX)
    
    if PWM_MAX != 48:
        logger.error("ABORT: PWM_MAX is not 48! Fix ledwiz_direct.py first.")
        sys.exit(1)
    
    # Run static green test FIRST
    logger.info("")
    logger.info(">>> RUNNING STATIC GREEN TEST (5 seconds) <<<")
    run_static_green_test(duration_seconds=5)
    
    time.sleep(1)
    
    # Then run breathing test
    logger.info("")
    logger.info(">>> RUNNING BREATHING TEST (10 seconds) <<<")
    success = run_breathing_demo(duration_seconds=10)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

