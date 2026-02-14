# Evidence Log Format

Each task keeps a JSONL evidence log at the path listed in plan/por.yaml.

One line per run. Fields:
- **timestamp** (ISO8601) - When the verification/action occurred
- **task_id** (e.g., "P1-01") - Task identifier from por.yaml
- **sha** (git commit verified against) - Git commit hash
- **actor** ("planner" | "engineer" | "verifier") - Role performing the action
- **mode** ("preflight" | "apply" | "restore") - Type of operation
- **checks_passed** (bool) - Whether all checks passed
- **findings** (array of {name, result, details}) - Detailed test results
- **artifacts** (array of file paths in repo or build outputs) - Related files

## Example Entry

```json
{"timestamp":"2025-10-23T14:30:00Z","task_id":"P0-01","sha":"abc123def","actor":"engineer","mode":"apply","checks_passed":true,"findings":[{"name":"501_response_test","result":"pass","details":"Gateway returns 501 when ANTHROPIC_API_KEY is unset"}],"artifacts":["gateway/routes/ai.js","tests/gateway/ai.test.js"]}
```

## Workflow

1. **Planner**: Updates task status, appends preflight evidence
2. **Engineer**: Implements changes, appends apply/restore evidence with artifacts
3. **Verifier**: Runs acceptance checks, appends verification evidence, updates last_verified_sha
