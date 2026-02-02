# 🔒 RESTRICTED_ZONE_README.md

This file lists project zones that AI agents must not modify unless explicitly authorized.

## ❌ DO NOT EDIT These Without Permission

- `config/` → Centralized settings; read-only for agents
- `public/` → Static assets (mic icons, overlays, fonts)
- `firebase/` → Cloud sync logic; backend-only
- `system/launchers/` → Platform boot logic (must preserve GUI visibility)

## 🧠 Agent Instructions

- If your task requires editing these folders:
  - Prompt the user to confirm with full explanation
  - Log justification in `agent_boot.log`

- If in doubt: **fail gracefully and alert the user**

## ✅ Allowed Tasks

Agents **may read but not write** to these folders unless directed by Promethea.