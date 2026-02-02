#!/usr/bin/env bash
set -euo pipefail

status() {
  curl -sS -m 3 -o /dev/null -w "%{http_code}" "$1" || echo 0
}

b=$(status "http://localhost:8000/health")
g=$(status "http://localhost:8787/api/health")

if [[ "$b" == "200" && "$g" == "200" ]]; then
  echo "✅ Dev stack healthy"
  exit 0
else
  echo "⚠️  Degraded: backend=$b gateway=$g"
  exit 2
fi

