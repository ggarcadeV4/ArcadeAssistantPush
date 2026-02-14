"""
Manual Score Sync Script
Directly parses .hi files using hi2txt and writes to mame_scores.json
"""
import subprocess
import json
from pathlib import Path
from datetime import datetime

DRIVE_ROOT = Path("A:/")
HISCORE_DIRS = [
    DRIVE_ROOT / "Emulators" / "MAME" / "hiscore",
    DRIVE_ROOT / "Emulators" / "MAME Gamepad" / "hiscore",
]
HI2TXT = DRIVE_ROOT / "LaunchBox" / "ThirdParty" / "hi2txt" / "hi2txt.exe"
OUTPUT = DRIVE_ROOT / ".aa" / "state" / "scorekeeper" / "mame_scores.json"

def parse_hi_file(hi_file):
    """Parse a .hi file using hi2txt."""
    result = subprocess.run(
        [str(HI2TXT), "-r", str(hi_file)],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode != 0:
        print(f"  ERROR: hi2txt failed for {hi_file.name}")
        return []
    
    entries = []
    for line in result.stdout.strip().split('\n'):
        if not line or line.startswith("RANK|"):
            continue
        parts = line.split('|')
        if len(parts) >= 3:
            try:
                entries.append({
                    "rank": int(parts[0]),
                    "score": int(parts[1]),
                    "name": parts[2].strip() or "???",
                    "rom": hi_file.stem,
                    "game_name": hi_file.stem,
                    "timestamp": datetime.now().isoformat(),
                    "source": "hi2txt"
                })
            except ValueError:
                continue
    return entries

def main():
    print(f"hi2txt exists: {HI2TXT.exists()}")
    
    # Collect ALL scores from ALL directories (don't overwrite, MERGE)
    all_scores = {}  # rom -> list of all entries
    
    for hiscore_dir in HISCORE_DIRS:
        print(f"\nChecking: {hiscore_dir}")
        if not hiscore_dir.exists():
            print(f"  Directory does not exist!")
            continue
            
        hi_files = list(hiscore_dir.glob("*.hi"))
        print(f"  Found {len(hi_files)} .hi files")
        
        for hi_file in hi_files:
            rom = hi_file.stem
            print(f"  Parsing: {hi_file.name}...", end=" ")
            entries = parse_hi_file(hi_file)
            if entries:
                # MERGE: Add to existing entries for this ROM
                if rom not in all_scores:
                    all_scores[rom] = []
                
                # Check if this hi file has a higher top score
                current_top = max((e['score'] for e in all_scores[rom]), default=0)
                new_top = max((e['score'] for e in entries), default=0)
                
                if new_top > current_top:
                    # This file has better scores - replace
                    all_scores[rom] = entries
                    print(f"OK ({len(entries)} entries, top: {new_top}) [BEST]")
                else:
                    print(f"OK ({len(entries)} entries, top: {new_top}) [keeping {current_top}]")
            else:
                print("no entries")
    
    print(f"\nTotal games parsed: {len(all_scores)}")
    
    # Write output
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(all_scores, f, indent=2)
    
    print(f"Written to: {OUTPUT}")
    
    # Show results
    print("\nLeaderboard:")
    for rom, entries in sorted(all_scores.items()):
        if entries:
            print(f"  {rom}: {entries[0]['score']:,} by {entries[0]['name']}")

if __name__ == "__main__":
    main()

