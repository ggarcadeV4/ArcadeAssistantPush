import json
import time
from pathlib import Path
from urllib.request import urlopen, Request

API = 'http://127.0.0.1:8000'
OUT = Path('logs/verify_pairing.jsonl')
TRACE = Path('logs/launch_attempts.jsonl')


def get(url):
    with urlopen(url, timeout=15) as r:
        return json.load(r)


def post(url, body):
    data = json.dumps(body).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-panel': 'launchbox',
    }
    req = Request(url, data=data, headers=headers, method='POST')
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8') or '{}')


def choose_samples_by_adapter(games):
    buckets = {
        'duckstation': [],
        'dolphin': [],
        'flycast': [],
        'model2': [],
        'supermodel': [],
    }
    for g in games:
        plat = (g.get('platform') or '').lower()
        # DuckStation (PS1): sony playstation | ps1 | psx (exclude PS2/PS3/PSP)
        if (("playstation" in plat) or ("ps1" in plat) or ("psx" in plat)) and ("2" not in plat) and ("3" not in plat) and ("psp" not in plat):
            buckets['duckstation'].append(g['id'])
        # Dolphin: Nintendo GameCube | GameCube | Nintendo Wii | Wii
        if ('gamecube' in plat) or ('wii' in plat):
            buckets['dolphin'].append(g['id'])
        # Flycast: NAOMI / Atomiswave only; leave Dreamcast to Redream
        if any(x in plat for x in ('naomi', 'sega naomi', 'atomiswave', 'sammy atomiswave')):
            buckets['flycast'].append(g['id'])
        # Model 2
        if ('model 2' in plat) or ('sega model 2' in plat):
            buckets['model2'].append(g['id'])
        # Model 3 / Supermodel
        if ('model 3' in plat) or ('sega model 3' in plat) or ('supermodel' in plat):
            buckets['supermodel'].append(g['id'])
    # pick top 3 per adapter
    return {k: v[:3] for k, v in buckets.items()}


def read_latest_trace_for(game_id):
    if not TRACE.exists():
        return {}
    # read last ~200 lines to find match quickly
    try:
        lines = TRACE.read_text(encoding='utf-8', errors='ignore').splitlines()
    except Exception:
        return {}
    for ln in reversed(lines[-200:]):
        try:
            obj = json.loads(ln)
            if obj.get('game_id') == game_id:
                return obj
        except Exception:
            continue
    return {}


def main():
    # fetch games once
    games = get(f"{API}/api/launchbox/games?limit=20000")
    samples = choose_samples_by_adapter(games)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for adapter, ids in samples.items():
        for gid in ids:
            try:
                res = post(f"{API}/api/launchbox/launch/{gid}", {"force_method": "direct"})
            except Exception as e:
                res = {"success": False, "message": str(e)}

            # slight delay to let trace flush
            time.sleep(0.05)
            tr = read_latest_trace_for(gid)
            # diagnostics: who claims this game?
            try:
                diag = get(f"{API}/api/launchbox/diagnostics/claim?game_id={gid}")
            except Exception:
                diag = {}
            selected = (diag.get('selected_adapter') or '').lower() if isinstance(diag, dict) else ''
            rec = {
                'adapter': adapter,
                'game_id': gid,
                'success': bool(res.get('success')),
                'message': res.get('message') or '',
                'command': res.get('command') or (tr.get('command') if isinstance(tr, dict) else ''),
                'resolved_file': tr.get('resolved_file') if isinstance(tr, dict) else None,
                'extracted': tr.get('extracted') if isinstance(tr, dict) else None,
                'trace_message': tr.get('message') if isinstance(tr, dict) else None,
                'selected': selected,
            }
            records.append(rec)

    with OUT.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')

    # Summary
    from collections import defaultdict
    summary = defaultdict(lambda: {'ok': 0, 'missing_emu': 0, 'missing_rom': 0, 'extracted': 0, 'claimed_ok': 0})
    for r in records:
        a = summary[r['adapter']]
        msg = (r.get('message') or r.get('trace_message') or '').upper()
        if r.get('success'):
            a['ok'] += 1
        elif 'MISSING-EMU' in msg:
            a['missing_emu'] += 1
        elif 'MISSING-ROM' in msg:
            a['missing_rom'] += 1
        if r.get('extracted'):
            a['extracted'] += 1
        # Selected adapter matches expected?
        if (r.get('selected') or '').lower() == r['adapter'].lower():
            a['claimed_ok'] += 1
    for k, v in summary.items():
        print(f"adapter={k} ok={v['ok']} missing_emu={v['missing_emu']} missing_rom={v['missing_rom']} extracted={v['extracted']} claimed_ok={v['claimed_ok']}")


if __name__ == '__main__':
    main()
