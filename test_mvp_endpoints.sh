#!/usr/bin/env bash
set -euo pipefail

FASTAPI_URL="${FASTAPI_URL:-http://localhost:8888}"
DEV="${DEVICE_ID:-CAB-001}"

json() { jq -r '.' <<<"$1" >/dev/null 2>&1 || echo "$1"; }

step() { printf "\n=== %s ===\n" "$1"; }

# --- ScoreKeeper: submit score (preview -> apply) + leaderboard ---
step "ScoreKeeper: submit score (preview)"
PREV=$(curl -s -X POST "$FASTAPI_URL/scores/submit/preview" \
  -H "content-type: application/json" \
  -d '{"game":"Galaga","player":"Greg","score":120300}')
json "$PREV"

step "ScoreKeeper: submit score (apply)"
APPLY=$(curl -s -X POST "$FASTAPI_URL/scores/submit/apply" \
  -H "content-type: application/json" -H "x-scope: state" -H "x-device-id: $DEV" -H "x-panel: scorekeeper" \
  -d '{"game":"Galaga","player":"Greg","score":120300}')
json "$APPLY"

step "ScoreKeeper: leaderboard"
LB=$(curl -s "$FASTAPI_URL/scores/leaderboard?game=Galaga&limit=10"); json "$LB"

# --- Tournaments: create -> report winner -> get bracket ---
step "Tournament: create (preview)"
TPREV=$(curl -s -X POST "$FASTAPI_URL/scores/tournaments/create/preview" \
  -H "content-type: application/json" \
  -d '{"name":"Demo Tournament","game":"Street Fighter II","player_count":4}')
json "$TPREV"

step "Tournament: create (apply)"
CRT=$(curl -s -X POST "$FASTAPI_URL/scores/tournaments/create/apply" \
  -H "content-type: application/json" -H "x-scope: state" -H "x-device-id: $DEV" -H "x-panel: scorekeeper" \
  -d '{"name":"Demo Tournament","game":"Street Fighter II","player_count":4}')
json "$CRT"

# Extract tournament ID from response
TID=$(echo "$CRT" | jq -r '.tournament.id // empty')
if [ -z "$TID" ]; then
  echo "⚠️  Could not extract tournament ID, using fallback"
  TID="demo-fallback"
fi

step "Tournament: get bracket (ID: $TID)"
BRK=$(curl -s "$FASTAPI_URL/scores/tournaments/$TID" 2>&1); json "$BRK"

step "Tournament: report winner (preview)"
RPREV=$(curl -s -X POST "$FASTAPI_URL/scores/tournaments/report/preview" \
  -H "content-type: application/json" \
  -d "{\"tournament_id\":\"$TID\",\"match_index\":0,\"winner_player\":\"Player 1\"}")
json "$RPREV"

step "Tournament: report winner (apply)"
RPT=$(curl -s -X POST "$FASTAPI_URL/scores/tournaments/report/apply" \
  -H "content-type: application/json" -H "x-scope: state" -H "x-device-id: $DEV" -H "x-panel: scorekeeper" \
  -d "{\"tournament_id\":\"$TID\",\"match_index\":0,\"winner_player\":\"Player 1\"}")
json "$RPT"

# --- LED Blinky: test action (no write) + mapping (preview -> apply) ---
step "LED: pulse test (no-write)"
LEDTEST=$(curl -s -X POST "$FASTAPI_URL/led/test" \
  -H "content-type: application/json" \
  -d '{"effect":"pulse","durationMs":1200,"color":"#ff0000"}')
json "$LEDTEST"

step "LED: mapping preview (default profile)"
MPREV=$(curl -s -X POST "$FASTAPI_URL/led/mapping/preview" \
  -H "content-type: application/json" \
  -d '{"scope":"default","mapping":{"p1_button1":"#ff0000","p1_button2":"#0000ff"}}')
json "$MPREV"

step "LED: mapping apply (default profile)"
MAPPLY=$(curl -s -X POST "$FASTAPI_URL/led/mapping/apply" \
  -H "content-type: application/json" -H "x-scope: config" -H "x-device-id: $DEV" -H "x-panel: led-blinky" \
  -d '{"scope":"default","mapping":{"p1_button1":"#ff0000","p1_button2":"#0000ff"}}')
json "$MAPPLY"

step "LED: list profiles"
PROFILES=$(curl -s "$FASTAPI_URL/led/profiles"); json "$PROFILES"

step "LED: get default profile"
DEFPROF=$(curl -s "$FASTAPI_URL/led/profiles/default" 2>&1); json "$DEFPROF"

# --- Logs tail ---
step "Tail changes log"
DRIVE_ROOT="${AA_DRIVE_ROOT:-/mnt/c/Users/Dad's PC/Desktop/Arcade Assistant Local}"
if [ -f "$DRIVE_ROOT/logs/changes.jsonl" ]; then
  echo "Last 5 changes:"
  tail -n 5 "$DRIVE_ROOT/logs/changes.jsonl" || true
else
  echo "No changes log found at $DRIVE_ROOT/logs/changes.jsonl"
fi

echo -e "\n✅ MVP endpoints exercised."
