# Codex Task: Daphne / Badlands Live Launch Test from LoRa Panel

## Summary
Test launching Daphne/Hypseus/Singe games from the LoRa panel. The AHK bypass fix has been compiled into `direct_app_adapter.py` but has never been live-tested. This task validates the complete chain.

## Background
- Daphne/Singe/Hypseus games use direct-app launch (no emulator ROM pattern)
- Previous issue: `daphne.exe` was failing because Firefox browser was listed in `Daphne.xml` as the emulator (removed by Codex)
- An AHK bypass fix was applied in `backend/services/direct_app_adapter.py` to handle Daphne's window management quirks
- Bytecode compilation passed but launch was never tested on live hardware

## Games to Test (in order)
1. **Badlands** — Daphne direct launch (`daphne.exe`)
2. **Conan** — Singe2 direct launch (`Singe.exe` or `Singe2.exe`)
3. **Rollercoaster** — Hypseus direct launch (`hypseus.exe`)

## Test Steps
1. Start the backend (`python -m uvicorn backend.app:app`) and gateway (`node gateway/server.js`)
2. Open the LoRa panel in browser at `http://127.0.0.1:8787/assistants?agent=launchbox`
3. Filter to Daphne platform
4. Click the play button on **Badlands**
5. Check:
   - Does the game window open?
   - Does `routing-decisions.jsonl` show a new launch entry?
   - Does the backend log show the full command being executed?
   - Does the game accept input?
6. Close the game and repeat for Conan (Singe) and Rollercoaster (Hypseus)

## Key Files
| File | Role |
|------|------|
| `backend/services/direct_app_adapter.py` | AHK bypass, direct exe launch logic |
| `backend/services/launcher.py` | Launch chain: plugin → detected emulator → direct |
| `backend/routers/launchbox.py` | `/api/launchbox/launch/{game_id}` endpoint |
| `logs/routing-decisions.jsonl` | Launch decision audit trail |

## Expected Outcomes
- **Success**: Game launches, plays, and exits cleanly. Entry appears in `routing-decisions.jsonl`.
- **Partial**: Game launches but has window focus or input issues → AHK bypass may need tuning
- **Failure**: Game doesn't launch → check `direct_app_adapter.py` error logs and the resolved command path

## If Launch Fails
1. Check backend terminal for error output
2. Check `logs/routing-decisions.jsonl` for the decision entry
3. Verify the `ApplicationPath` in `A:/LaunchBox/Data/Platforms/Daphne.xml` points to a real executable
4. Check if `daphne.exe` runs when double-clicked directly from Explorer
