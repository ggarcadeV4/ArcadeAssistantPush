Drive A → Supabase Integration Guide (Unified Schema)

This document is for Codex to update Drive A’s Python backend to the new unified Supabase schema and to verify end‑to‑end cabinet connectivity.

Schema Mapping (Old → New)
- devices → cabinet (main device registry)
- telemetry → cabinet_telemetry (event logs)
- scores → cabinet_game_score (high scores)
- tournaments → tournament (schema enhancements)
- issues → issues (schema enhancements)
- NEW: cabinet_heartbeat (uptime, CPU, RAM, disk %, every 5 minutes)

Column Mapping (Old → New)
- devices.device_id → cabinet.cabinet_id (UUID)
- devices.last_seen → cabinet.updated_at (timestamptz)
- telemetry.details (jsonb) → cabinet_telemetry.payload (jsonb)
- scores.meta (jsonb) → cabinet_game_score.meta (jsonb)
Notes: version/tags remain on cabinet when present.

Supabase Connection (Environment)
- Required
  - SUPABASE_URL
  - SUPABASE_SERVICE_KEY (Option A, approved; Drive A uses service_role for all ops)
  - SUPABASE_ANON_KEY (optional; client falls back to service key when absent)
  - AA_DEVICE_ID (first‑boot: generate UUID; persist under A:\.aa\device_id.txt and A:\.aa\cabinet_manifest.json)

Where to get keys
1) Go to: https://supabase.com/dashboard/project/zlkhsxacfyxsctqpvbsh/settings/api
2) Copy the service_role key (CRITICAL for Drive A)
3) Copy the anon key (optional for backend)

Python Client (Service Role)
```
import os
from supabase import create_client
from supabase.lib.client_options import ClientOptions

SUPABASE_URL = os.environ['SUPABASE_URL']
SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
ANON_KEY = os.getenv('SUPABASE_ANON_KEY')

# Admin client (service_role)
admin = create_client(
    SUPABASE_URL,
    SERVICE_KEY,
    options=ClientOptions(persist_session=False, auto_refresh_token=False)
)

# Optional anon client (fall back to admin when absent)
client = create_client(
    SUPABASE_URL,
    ANON_KEY or SERVICE_KEY,
    options=ClientOptions(persist_session=True, auto_refresh_token=True)
)
```

Operations (Unified Schema)

1) Register (cabinet) — ensure row exists
```
import os, json
from datetime import datetime

def ensure_cabinet(admin, cabinet_id: str) -> bool:
    tags = {
        'build': 'DriveA-v1.0',
        'os': 'Win11',
        'aa_version': os.getenv('AA_VERSION', '1.0.3'),
        'profile': 'prod',
        'channel': 'retail',
    }
    payload = {
        'cabinet_id': cabinet_id,
        'serial': os.getenv('AA_SERIAL_NUMBER') or os.getenv('DEVICE_SERIAL') or cabinet_id,
        'status': 'online',
        'version': os.getenv('AA_VERSION', '1.0.3'),
        'tags': tags,
        'updated_at': datetime.utcnow().isoformat(),
    }
    # Upsert by cabinet_id (merge duplicates)
    admin.table('cabinet').insert(payload, count='exact').execute()
    return True
```

2) Heartbeat (cabinet_heartbeat) — system metrics every 5 minutes
```
import time, os
from datetime import datetime

try:
    import psutil
except Exception:
    psutil = None

def collect_metrics() -> dict:
    ts = datetime.utcnow().isoformat()
    if psutil:
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(os.getenv('AA_DRIVE_ROOT', 'A:\\')).free / (1024**3)
        payload = {'cpu_percent': cpu, 'mem_percent': mem, 'disk_free_gb': round(disk, 2)}
    else:
        payload = {'cpu_percent': None, 'mem_percent': None, 'disk_free_gb': None}
    payload.update({'uptime_s': int(time.time() - psutil.boot_time()) if psutil else None,
                    'aa_version': os.getenv('AA_VERSION', '1.0.3')})
    return payload

def send_heartbeat(admin, cabinet_id: str) -> bool:
    hb = {
        'cabinet_id': cabinet_id,
        'tenant_id': os.getenv('AA_TENANT_ID', 'default'),
        'payload': collect_metrics(),
    }
    admin.table('cabinet_heartbeat').insert(hb).execute()
    # Optional: also update updated_at in cabinet when column exists
    try:
        admin.table('cabinet').update({'updated_at': datetime.utcnow().isoformat()}).eq('cabinet_id', cabinet_id).execute()
    except Exception:
        pass
    return True
```

3) Telemetry (cabinet_telemetry)
```
from datetime import datetime

def send_telemetry(client, cabinet_id: str, level: str, code: str, message: str, details: dict | None = None) -> bool:
    row = {
        'cabinet_id': cabinet_id,
        'tenant_id': os.getenv('AA_TENANT_ID', 'default'),
        'level': level.upper(),
        'code': code,
        'message': message,
        'payload': details or {},
        'created_at': datetime.utcnow().isoformat(),
    }
    client.table('cabinet_telemetry').insert(row).execute()
    return True
```

4) Scores (cabinet_game_score)
```
from datetime import datetime

def insert_score(client, cabinet_id: str, game_id: str, player: str, score: int, meta: dict | None = None) -> bool:
    row = {
        'cabinet_id': cabinet_id,
        'game_id': game_id,
        'tenant_id': os.getenv('AA_TENANT_ID', 'default'),
        'player': player,
        'score': int(score),
        'meta': meta or {},
        'created_at': datetime.utcnow().isoformat(),
    }
    client.table('cabinet_game_score').insert(row).execute()
    return True
```

Best‑Effort + Offline Spooling (recommended)
- Wrap every call with try/except and spool failures to JSONL outbox under `A:\state\outbox\*.jsonl`.
- Flush on heartbeat (5‑minute loop with ±30s jitter).

Verification (Unified Schema)
1) Start stack (`Start-Arcade-Assistant-8787.bat`).
2) First‑boot identity: `A:\.aa\device_id.txt` (UUID), `A:\.aa\cabinet_manifest.json` (device_id matches).
3) Health
   - `GET http://127.0.0.1:8000/api/supabase/status` → configured:true
   - `GET http://127.0.0.1:8000/api/supabase/health` → connected:true with latency
4) Cabinet record
   - Supabase → `cabinet` table contains the UUID row (tags/version/updated_at if present).
5) Heartbeat
   - `cabinet_heartbeat` has new rows each ~5 minutes with payload metrics.
6) Telemetry & Scores
   - `cabinet_telemetry` and `cabinet_game_score` contain new rows for triggered events.

Schema Confirmations (from Manis)
- owner_id is nullable → first‑boot auto‑insert succeeds
- payload JSONB exists for telemetry/heartbeat
- RLS bypass with service_role is approved (Option A)

Code Touchpoints to Update (Drive A repo)
- Replace table/column names in Python:
  - `backend/services/supabase_client.py` — devices→cabinet, telemetry→cabinet_telemetry, scores→cabinet_game_score; details→payload; device_id→cabinet_id; add cabinet_heartbeat inserts.
  - `backend/routers/scorekeeper.py` — mirror scores to `cabinet_game_score` (cabinet_id).
  - `backend/routers/voice.py`, `voice_advanced.py`, `services/launcher.py`, `routers/led.py` — telemetry table rename + payload jsonb.
  - `backend/app.py` — heartbeat: insert into `cabinet_heartbeat`; optional update `cabinet.last_seen`.

Rollout Checklist (Codex)
1) Swap table/column names in backend code per mappings above.
2) Keep first‑boot AA_DEVICE_ID generation and manifest persistence.
3) Maintain device auto‑insert into `cabinet` with default tags and version.
4) Push heartbeat into `cabinet_heartbeat` every 5 minutes with jitter.
5) Keep offline spooling + flush on heartbeat.
6) Validate with the updated verification steps (cabinet/telemetry/heartbeat/game_score tables).

Note: Old tables (devices, telemetry, scores) are dropped. All new writes must target cabinet, cabinet_telemetry, cabinet_game_score, and cabinet_heartbeat.
