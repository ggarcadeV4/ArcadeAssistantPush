#!/usr/bin/env bash
# Opt-in pre-commit hook to verify backend health + cache without restarting
# Usage: ln -s ../../scripts/pre-commit-smoke.sh .git/hooks/pre-commit

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

NOSTART=1 bash scripts/verify-cache.sh || {
  echo "\n[pre-commit] Smoke check failed (RED). Commit blocked." >&2
  echo "Hint: Start backend locally, then retry commit; or run NOSTART=1 bash scripts/verify-cache.sh to see details." >&2
  exit 1
}

echo "[pre-commit] Smoke check GREEN. Proceeding with commit."

