"""
Regenerate scores.jsonl from hi2txt mame_scores.json

This replaces the corrupt scores.jsonl (from broken Lua plugin) with
accurate data from hi2txt parsing of .hi files.
"""
import json
from pathlib import Path
from datetime import datetime

MAME_SCORES = Path("A:/.aa/state/scorekeeper/mame_scores.json")
SCORES_JSONL = Path("A:/.aa/state/scorekeeper/scores.jsonl")
BACKUP_DIR = Path("A:/.aa/backups/scores")

def main():
    # 1. Load mame_scores.json (source of truth from hi2txt)
    if not MAME_SCORES.exists():
        print(f"ERROR: {MAME_SCORES} not found. Run manual_score_sync.py first.")
        return
    
    with open(MAME_SCORES, 'r') as f:
        mame_data = json.load(f)
    
    print(f"Loaded {len(mame_data)} games from mame_scores.json")
    
    # 2. Backup current scores.jsonl
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if SCORES_JSONL.exists():
        backup_name = f"scores_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        backup_path = BACKUP_DIR / backup_name
        import shutil
        shutil.copy(SCORES_JSONL, backup_path)
        print(f"Backed up to: {backup_path}")
    
    # 3. Convert mame_scores.json to scores.jsonl format
    lines = []
    for rom, entries in mame_data.items():
        for entry in entries:
            # Format expected by scorekeeper backend
            line = {
                "timestamp": entry.get("timestamp", datetime.now().isoformat()),
                "game": rom,
                "game_id": f"mame_{rom}",
                "game_rom": rom,
                "player": entry.get("name", "???"),
                "score": entry.get("score", 0),
                "rank": entry.get("rank", 0),
                "source": "hi2txt",  # Clean source marker
                "device_id": "00000000-0000-0000-0000-000000000001",
                "frontend_source": "mame"
            }
            lines.append(json.dumps(line))
    
    # 4. Write new scores.jsonl
    with open(SCORES_JSONL, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Written {len(lines)} score entries to {SCORES_JSONL}")
    
    # 5. Show summary
    print("\nTop scores per game:")
    for rom, entries in sorted(mame_data.items()):
        if entries:
            top = entries[0]
            print(f"  {rom}: {top['score']:,} by {top['name']}")

if __name__ == "__main__":
    main()
