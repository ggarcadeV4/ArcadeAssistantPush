"""
Port Roll Call - LED-Wiz Port Mapping Diagnostic
Part of: Phase 5 Blinky Gem Pivot

Lights up each port 1-32 one at a time so you can map physical wiring.
Watch the cabinet and note which LED lights up for each port number.

Usage:
    python roll_call.py
"""
from __future__ import annotations

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledwiz_direct import discover_boards, PWM_MAX

import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [RollCall] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("roll_call")


def run_roll_call(dwell_seconds: float = 3.0):
    """
    Light up each port 1-32 one at a time.
    User watches cabinet to map physical location of each port.
    """
    logger.info("=" * 60)
    logger.info("PORT ROLL CALL - LED-Wiz Wiring Diagnostic")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Watch the cabinet and note which LED lights up")
    logger.info(f"Each port will be lit for {dwell_seconds} seconds")
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
    logger.info("-" * 60)
    logger.info("STARTING ROLL CALL...")
    logger.info("-" * 60)
    
    try:
        # Turn ALL lights OFF first
        for board in boards:
            board.all_off()
        time.sleep(0.5)
        
        # Loop through all 32 ports per board
        for board in boards:
            logger.info(f"\n>>> BOARD {board.unit_id} <<<")
            
            for port in range(1, 33):  # Ports 1-32
                port_idx = port - 1  # 0-indexed
                
                # Create frame with just this port ON
                frame = [0] * 32
                frame[port_idx] = PWM_MAX  # Max brightness (48)
                
                # Light it up
                board.set_channels(frame)
                
                logger.info(f"--> LIGHTING UP PORT [ {port:2d} ]  (Board {board.unit_id})")
                
                time.sleep(dwell_seconds)
                
                # Turn off
                board.all_off()
                time.sleep(0.2)  # Brief pause between ports
        
        logger.info("")
        logger.info("-" * 60)
        logger.info("ROLL CALL COMPLETE")
        logger.info("-" * 60)
        
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
    
    finally:
        for board in boards:
            board.all_off()
            board.close()
    
    return True


def main():
    logger.info("Port Roll Call - Starting...")
    logger.info("")
    
    # 3 seconds per port
    run_roll_call(dwell_seconds=3.0)


if __name__ == "__main__":
    main()
