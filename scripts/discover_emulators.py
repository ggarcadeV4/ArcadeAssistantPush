import argparse
import json
from pathlib import Path


TARGETS = {
    'dolphin': ['Dolphin.exe'],
    'flycast': ['flycast.exe'],
    'model2': ['emulator.exe', 'emulator_multicpu.exe'],
    'supermodel': ['supermodel.exe'],
    'duckstation': ['duckstation-qt-x64-ReleaseLTCG.exe', 'duckstation-qt-x64-Release.exe', 'duckstation-qt-x64-Profile.exe'],
}


def scan_emulators(root: Path) -> dict:
    found = {}
    if not root.exists():
        return found
    for key, names in TARGETS.items():
        for name in names:
            cand = root / key.capitalize() / name
            if cand.exists():
                found[key] = str(cand)
                break
        if key not in found:
            # fallback: depth-2 scan for name
            for p in root.glob('**/*'):
                if p.is_file() and p.name.lower() in {n.lower() for n in names}:
                    found[key] = str(p)
                    break
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=r'A:\\Emulators', help='Emulators root (default: A:\\Emulators)')
    ap.add_argument('--apply', action='store_true', help='Write missing keys to configs/emulator_paths.json')
    args = ap.parse_args()

    root = Path(args.root)
    found = scan_emulators(root)
    print(json.dumps(found, indent=2))

    cfg_path = Path('configs/emulator_paths.json')
    if not cfg_path.exists():
        print('configs/emulator_paths.json missing; skipping apply')
        return 0
    data = json.loads(cfg_path.read_text(encoding='utf-8'))
    emus = data.get('emulators') or {}

    patch = {}
    for key, exe in found.items():
        if key not in emus:
            entry = {
                'title': key.capitalize() if key != 'model2' else 'Model 2 Emulator',
                'executable_path': exe,
                'source': 'discover',
            }
            patch[key] = entry
    if patch:
        print('Proposed additions:')
        print(json.dumps(patch, indent=2))
        if args.apply:
            emus.update(patch)
            data['emulators'] = emus
            cfg_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print('Applied changes to configs/emulator_paths.json')
    else:
        print('No missing emulator entries to add')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

