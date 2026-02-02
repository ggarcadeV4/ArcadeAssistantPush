import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

API = 'http://127.0.0.1:8000'
IN_JSONL = Path('logs/live_adapters_audit.jsonl')
OUT_TXT = Path('logs/dry_run_acceptance.txt')
OUT_JSONL = Path('logs/dry_run_acceptance.jsonl')

ADAPTERS = {'duckstation', 'dolphin', 'flycast', 'model2', 'supermodel'}


def post_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-panel': 'launchbox',
    }
    req = Request(url, data=data, headers=headers, method='POST')
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8') or '{}')


def classify(result: dict) -> str:
    if result.get('success'):
        return 'DRY-RUN-OK'
    msg = (result.get('message') or '').lower()
    if 'not found' in msg or 'not found in emulator_paths' in msg or 'emulator' in msg and 'missing' in msg:
        return 'MISSING-EMU'
    if 'rom' in msg and ('missing' in msg or 'path' in msg):
        return 'MISSING-ROM'
    return 'ERROR'


def main():
    if not IN_JSONL.exists():
        print(f"Input {IN_JSONL} not found. Run live_audit_platforms.py first.")
        return

    rows = []
    for line in IN_JSONL.read_text(encoding='utf-8').splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get('adapter') in ADAPTERS:
            rows.append(rec)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    out_lines = []
    out_jsonl = []

    for rec in rows:
        adapter = rec.get('adapter')
        for gid in (rec.get('sample_ids') or [])[:3]:
            if not gid:
                continue
            url = f"{API}/api/launchbox/launch/{gid}"
            try:
                result = post_json(url, {"force_method": "direct"})
                cmd = result.get('command') or ''
                label = classify(result)
                reason = result.get('message') or ''
            except HTTPError as e:
                try:
                    payload = e.read().decode('utf-8')
                    result = json.loads(payload)
                except Exception:
                    result = {"message": str(e)}
                cmd = ''
                label = classify(result)
                reason = result.get('message') or ''
            except URLError as e:
                cmd = ''
                label = 'ERROR'
                reason = str(e.reason)
            out_lines.append(f"{adapter} | {gid} | {label} | {reason} | {cmd}")
            out_jsonl.append({
                "adapter": adapter,
                "game_id": gid,
                "command": cmd,
                "result": label,
                "message": reason
            })

    OUT_TXT.write_text('\n'.join(out_lines), encoding='utf-8')
    with OUT_JSONL.open('w', encoding='utf-8') as f:
        for r in out_jsonl:
            f.write(json.dumps(r) + '\n')
    print(f"Wrote {len(out_jsonl)} dry-run results to {OUT_TXT} and {OUT_JSONL}")


if __name__ == '__main__':
    main()
