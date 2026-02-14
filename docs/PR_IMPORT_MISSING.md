# feat(import): plugin-powered Import Missing + cache revalidate

## Summary of Changes
- C# LaunchBox plugin (Bridge + Importer)
  - Adds safe importer using LaunchBox plugin APIs (no XML edits).
  - Endpoints:
    - `GET /import/missing?platform=...&folder=...` — list files not yet in LaunchBox.
    - `POST /import/apply { platform, folder }` — add entries; returns `{added, skipped, duplicates, errors}`.
  - Titles from filename; platform set; emulator mappings unchanged.
  - Extensions:
    - Arcade/MAME: `.zip, .7z`
    - PS2: `.iso,.bin,.cue,.img,.chd,.7z,.zip,.gz`
  - Logs on apply: `import: platform=<p> added=<n> skipped=<m> folder=<path>`.
- Backend API
  - `GET /api/launchbox/import/missing` — proxies to plugin list.
  - `POST /api/launchbox/import/apply` — proxies to plugin add, logs summary, auto `POST /api/launchbox/cache/revalidate`.

## Env/Config Touched
- `LB_PLUGIN_PORT` — backend plugin port (defaulted to `10099`).
- LaunchBox plugin config at `A:/LaunchBox/Plugins/ArcadeAssistant/config.json` should match (e.g., `{ "port": 10099, "logLevel": "info" }`).

## Test Transcript (paste exact live outputs)
1) List Missing
- Arcade
```
GET /api/launchbox/import/missing?platform=Arcade&folder=A:\\Console ROMs\\MAME
HTTP/1.1 200
{ "platform":"Arcade", "counts": {"missing": 2, "existing": N}, "missing": [
  {"path":"A:\\Console ROMs\\MAME\\new1.zip","name":"new1"},
  {"path":"A:\\Console ROMs\\MAME\\new2.zip","name":"new2"}
]}
```
- PS2
```
GET /api/launchbox/import/missing?platform=Sony PlayStation 2&folder=A:\\Console ROMs\\PlayStation 2
HTTP/1.1 200
{ "platform":"Sony PlayStation 2", "counts": {"missing": 2, "existing": N}, "missing": [
  {"path":"A:\\Console ROMs\\PlayStation 2\\ps2a.7z","name":"ps2a"},
  {"path":"A:\\Console ROMs\\PlayStation 2\\ps2b.zip","name":"ps2b"}
]}
```

2) Apply
```
POST /api/launchbox/import/apply {"platform":"Arcade","folder":"A:\\Console ROMs\\MAME"}
HTTP/1.1 200
{ "added": 2, "skipped": 0, "duplicates": 0, "errors": [] }

POST /api/launchbox/import/apply {"platform":"Sony PlayStation 2","folder":"A:\\Console ROMs\\PlayStation 2"}
HTTP/1.1 200
{ "added": 2, "skipped": 0, "duplicates": 0, "errors": [] }
```

3) Cache Revalidate
```
POST /api/launchbox/cache/revalidate
HTTP/1.1 200
{ "reloaded": true }
```

4) Launch Proof
```
Launch MAME: success=true, path_used="plugin" | title=<title>
Launch PS2:  success=true, path_used="plugin" | temp_extract=ok | cleanup=ok
```

## Attach Logs (tails)
- LaunchBox log: lines containing `import: platform=`
- Backend `logs/changes.jsonl`: corresponding import entries
- PCSX2 extractor logs (if available): temp path cleanup confirmed

---

## Minimal UI (nice-to-have)
A small `ImportSection` in LaunchBox LoRa panel with a dropdown for Platform, Folder input with sensible defaults, and a button that:
- POSTs `/api/launchbox/import/apply` and shows a toast with `Imported X, skipped Y`.
- Calls `POST /api/launchbox/cache/revalidate` and refreshes list.
- Disabled while running; concise error toast on failure.

