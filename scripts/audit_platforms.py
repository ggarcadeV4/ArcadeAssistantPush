import json
from pathlib import Path
import re

CONFIG = Path('configs/emulator_paths.json')
OUT = Path('logs/adapters_audit.jsonl')


def load_config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding='utf-8'))
    return {"emulators": {}, "platform_mappings": []}


KNOWN_ADAPTERS = {
    'retroarch': 'retroarch',
    'pcsx2': 'pcsx2',
    'redream': 'redream',
    'rpcs3': 'rpcs3',
    'teknoparrot': 'teknoparrot',
    'duckstation': 'duckstation',
    'ppsspp': 'ppsspp',
    'dolphin': 'dolphin',
    'flycast': 'flycast',
    'supermodel': 'supermodel',
    'model2': 'model2',
    'melonds': 'melonds',
    'daphne': 'daphne',
    'pinballfx': 'pinballfx',
}


CODE_ADAPTERS = {
    # existing code-backed adapters
    'retroarch', 'pcsx2', 'redream', 'rpcs3', 'teknoparrot'
}


def detect_adapter(emulator_title: str, exe_path: str) -> str:
    s = f"{emulator_title} {exe_path}".lower()
    for key in KNOWN_ADAPTERS:
        if key in s:
            return KNOWN_ADAPTERS[key]
    # heuristics
    if 'super model' in s:
        return 'supermodel'
    if 'model 2' in s or 'model2' in s:
        return 'model2'
    if re.search(r'duck\s*station', s):
        return 'duckstation'
    return 'unknown'


def main():
    cfg = load_config()
    emulators = cfg.get('emulators') or {}
    mappings = cfg.get('platform_mappings') or []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for m in mappings:
        plat = (m.get('platform') or '').strip()
        emu_id = m.get('emulator_id')
        emu = emulators.get(emu_id) or {}
        title = emu.get('title') or ''
        exe = emu.get('executable_path') or ''
        adapter = detect_adapter(title, exe)
        if adapter == 'unknown':
            status = 'missing'
            notes = 'No adapter mapped (unknown emulator)'
        else:
            status = 'ok' if adapter in CODE_ADAPTERS else 'missing'
            if status == 'ok':
                notes = ''
            else:
                notes = 'Adapter stub required'
        line = {
            'platform': plat,
            'adapter': adapter,
            'status': status,
            'notes': notes,
        }
        lines.append(line)
    # write JSONL
    with OUT.open('w', encoding='utf-8') as f:
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"wrote {len(lines)} audit lines to {OUT}")


if __name__ == '__main__':
    main()

