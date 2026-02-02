import json
from pathlib import Path


CFG = Path('configs/emulator_paths.json')


def main():
    if not CFG.exists():
        print(f"Missing {CFG}")
        return 1
    try:
        data = json.loads(CFG.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Failed to parse {CFG}: {e}")
        return 1

    emus = data.get('emulators')
    if not isinstance(emus, dict):
        data['emulators'] = emus = {}

    # Desired entries (Windows A:\ paths)
    desired = {
        'dolphin': {
            'title': 'Dolphin',
            'executable_path': r"A:\\Emulators\\Dolphin\\Dolphin.exe",
            'args': ['-b', '-e'],
            'source': 'manual',
        },
        'duckstation': {
            'title': 'DuckStation',
            'executable_path': r"A:\\Emulators\\DuckStation\\duckstation-qt-x64-ReleaseLTCG.exe",
            'args': ['-batch', '-fullscreen'],
            'source': 'manual',
        },
        'flycast': {
            'title': 'Flycast',
            'executable_path': r"A:\\Emulators\\Flycast\\flycast.exe",
            'args': ['-fullscreen'],
            'source': 'manual',
        },
        'model2': {
            'title': 'Model 2 Emulator',
            'executable_path': r"A:\\Emulators\\Model2\\emulator.exe",
            'args': [],
            'source': 'manual',
        },
        'supermodel': {
            'title': 'Supermodel',
            'executable_path': r"A:\\Emulators\\Supermodel\\supermodel.exe",
            'args': ['-fullscreen'],
            'source': 'manual',
        },
    }

    changed = False
    for key, obj in desired.items():
        cur = emus.get(key)
        if cur != obj:
            emus[key] = obj
            changed = True

    if changed:
        CFG.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(f"Updated {CFG} with: {', '.join(desired.keys())}")
    else:
        print("No changes needed")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
