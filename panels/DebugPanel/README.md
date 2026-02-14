# 🧰 Debug Panel (C3)

This panel acts as the system-level diagnostic console for all agents.

## Always Displays:
- Mic state (idle/listening/muted/error)
- API key health (OpenAI, Claude, Gemini)
- USB device presence
- Last agent error (human-readable)

## Design:
- Uses `PanelTemplate`
- Color: `bg-orange-500`
- Accessible at all times

## Notes:
- All panels should forward critical errors here
- Claude must validate this panel renders cleanly before layout approval