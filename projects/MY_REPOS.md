# G&G Arcade — My GitHub Repos (Personal Reference)

> **Created:** February 18, 2026
> **Owner:** Greg (Dad's PC)
> **GitHub Org:** https://github.com/ggarcadeV4

---

## My Repositories

### 1. 🎰 Arcade Assistant (AI-Hub)
- **Repo:** https://github.com/ggarcadeV4/Arcade-Assistant-Basement-Build
- **Local:** `C:\Users\Dad's PC\Desktop\AI-Hub`
- **Branch:** `master`
- **What it is:** The main mission control — AI on the cabinets, Playnite integration, local scripts, frontend panels
- **Agent file:** `GEMINI.md`

### 2. 👥 Customer Hub (Salesforce/CRM)
- **Repo:** https://github.com/ggarcadeV4/GG-Arcade-Customer-Hub
- **Local:** `C:\Users\Dad's PC\Desktop\G and G Arcade Sass Salesforce`
- **Branch:** `main`
- **What it is:** Customer management, build workflows (7-day pipeline), Vector AI assistant, JotForm/Wix/Google Sheets integrations
- **Agent file:** `AGENTS.md`

### 3. 🌐 Arcade Network (Fleet Manager)
- **Repo:** https://github.com/ggarcadeV4/Arcade-Network-Fleet-Manager
- **Local:** `C:\Users\Dad's PC\Desktop\Arcade Network 12-03-2025`
- **Branch:** `main`
- **What it is:** Fleet console for monitoring deployed cabinets — telemetry, heartbeat, MAC allowlisting
- **Agent file:** `AGENTS.md`

### 4. 📦 InventoryGG
- **Repo:** https://github.com/ggarcadeV4/InventoryGG
- **Local:** `C:\Users\Dad's PC\Desktop\InventoryGG`
- **Branch:** `main`
- **What it is:** Parts inventory, BOM templates, purchasing workflows, Amazon cart import extension
- **Agent file:** `AGENTS.md`

---

## Quick Reference

| Action | Command |
|--------|---------|
| Push changes | `git add . && git commit -m "message" && git push` |
| Pull latest | `git pull origin main` |
| Check status | `git status` |
| View remotes | `git remote -v` |
| Assign Jules | Go to repo on GitHub → Issues → Create issue and assign Jules |

---

## What's Where

- **AGENTS.md** — In each project root. Instructions for AI agents (Jules, Claude, Gemini) so they understand the project
- **PROJECT_REGISTRY.md** — In `AI-Hub/projects/`. Master list linking all repos together
- **.gitignore** — In each project root. Prevents secrets and junk from being committed

---

## Notes
- All projects share the same **Supabase** database (some tables are shared)
- Jules can work on any of these repos asynchronously
- Each repo has its own `AGENTS.md` so Jules knows the rules for that specific project
