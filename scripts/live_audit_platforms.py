import json
from urllib.request import urlopen
from urllib.error import URLError
from pathlib import Path

API = 'http://127.0.0.1:8000'
OUT_JSONL = Path('logs/live_adapters_audit.jsonl')
OUT_TABLE = Path('logs/live_adapters_table.txt')


def fetch_json(url: str):
    with urlopen(url, timeout=5) as r:
        return json.load(r)


def load_static_map():
    audit_path = Path('logs/adapters_audit.jsonl')
    mapping = {}
    if audit_path.exists():
        for line in audit_path.read_text(encoding='utf-8').splitlines():
            try:
                j = json.loads(line)
                mapping[j['platform']] = {k: j.get(k) for k in ('adapter', 'status', 'notes')}
            except Exception:
                pass
    return mapping


def main():
    try:
        plats = fetch_json(f'{API}/api/launchbox/platforms')
        games = fetch_json(f'{API}/api/launchbox/games?limit=20000')
    except URLError as e:
        print(f'Backend not reachable: {e}')
        return

    static = load_static_map()

    # Helper: determine if an adapter is "ok" based on module existence + flags
    def adapter_enabled(name: str) -> bool:
        n = (name or '').lower()
        always_ok = {'retroarch', 'pcsx2', 'redream', 'rpcs3', 'teknoparrot'}
        # Check module file existence for adapters
        adapter_file = Path('backend/services/adapters') / f"{n}_adapter.py"
        module_exists = adapter_file.exists() or n in always_ok
        if not module_exists:
            return False
        if n in always_ok:
            return True
        # Env flags for new adapters
        import os
        env_map = {
            'duckstation': 'AA_ENABLE_ADAPTER_DUCKSTATION',
            'dolphin': 'AA_ENABLE_ADAPTER_DOLPHIN',
            'flycast': 'AA_ENABLE_ADAPTER_FLYCAST',
            'model2': 'AA_ENABLE_ADAPTER_MODEL2',
            'supermodel': 'AA_ENABLE_ADAPTER_SUPERMODEL',
        }
        flag = env_map.get(n)
        if not flag:
            return False
        val = str(os.getenv(flag, '0')).lower()
        return val in {'1','true','yes'}
    # emulator_found detection using configs/emulator_paths.json
    import sys
    sys.path.insert(0, str(Path('.').resolve()))
    try:
        from backend.constants.a_drive_paths import LaunchBoxPaths
    except Exception:
        LaunchBoxPaths = None
    try:
        cfg = json.loads(Path('configs/emulator_paths.json').read_text(encoding='utf-8'))
    except Exception:
        cfg = {"emulators": {}}
    def emulator_found(adapter: str) -> bool:
        hints = {
            'retroarch': 'retroarch',
            'pcsx2': 'pcsx2',
            'redream': 'redream',
            'rpcs3': 'rpcs3',
            'teknoparrot': 'teknoparrot',
            'duckstation': 'duckstation',
            'dolphin': 'dolphin',
            'flycast': 'flycast',
            'model2': 'model 2',
            'supermodel': 'supermodel',
        }
        h = hints.get(adapter)
        if not h:
            return False
        for emu in (cfg.get('emulators') or {}).values():
            title = (emu.get('title') or '').lower()
            exe_rel = emu.get('executable_path') or ''
            if h in title or h in exe_rel.lower():
                p = Path(exe_rel)
                if not p.is_absolute() and LaunchBoxPaths is not None:
                    try:
                        p = (LaunchBoxPaths.LAUNCHBOX_ROOT / p).resolve()
                    except Exception:
                        pass
                return p.exists()
        return False
    by_plat = {}
    for g in games:
        p = g.get('platform')
        if not p:
            continue
        by_plat.setdefault(p, []).append(g)

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in plats:
        info = static.get(p, {'adapter': 'unknown', 'status': 'missing', 'notes': 'no mapping'})
        # If adapter is present and enabled, mark status ok for audit visibility
        a = (info.get('adapter') or '').lower()
        if a and adapter_enabled(a):
            info = {**info, 'status': 'ok'}
        sample = [g.get('id') for g in by_plat.get(p, [])[:3]]
        rec = {
            'platform': p,
            'adapter': info['adapter'],
            'status': info['status'],
            'emulator_found': emulator_found(info['adapter']),
            'sample_ids': sample,
        }
        rows.append(rec)

    with OUT_JSONL.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')

    # Compact table
    lines = [f"platform\tadapter\tstatus\temulator_found\tsample_ids"]
    for r in rows:
        lines.append(f"{r['platform']}\t{r['adapter']}\t{r['status']}\t{r['emulator_found']}\t{', '.join(r['sample_ids'])}")
    OUT_TABLE.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {len(rows)} platforms to {OUT_JSONL} and {OUT_TABLE}')


if __name__ == '__main__':
    main()
