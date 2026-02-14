# Gateway Bypass Closure Evidence (2025-11-09)

## Verified
- Frontend LED/Scorekeeper/Lightguns clients now call /api/local/... (see grep_after.txt)
- Temporary /api/gunner/* proxy added for Lightguns with header forwarding

## Partial/Drift
- curl verification pending: gateway service not running on localhost:3000 during this session (requests failed to connect)
- Backup/log inspection pending until gateway/backend are online

## Missing
- Need real responses for LED/Scorekeeper/Lightguns apply calls once services are running
- Need changes.jsonl excerpts + backup directory listings for the same calls

### Artifacts
- grep_after.txt
- curl_led_apply.txt (connection failed; rerun after gateway starts)
- (Placeholder for Scorekeeper/Lightguns curl outputs)
- (Placeholder) ls_backups_led.txt, ls_backups_scorekeeper.txt, ls_backups_lightguns.txt
- (Pending) changes.jsonl excerpt once operations run
