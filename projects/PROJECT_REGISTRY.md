# G&G Arcade Ecosystem — Project Registry

> **Last Updated:** February 18, 2026
> **Maintained by:** AI-Hub (Mission Control)

---

## 📍 Active Repositories

| # | Project | GitHub Repo | Local Path | Branch | Supabase |
|---|---------|------------|------------|--------|----------|
| 1 | **AI-Hub** (Arcade Assistant) | [Arcade-Assistant-Basement-Build](https://github.com/ggarcadeV4/Arcade-Assistant-Basement-Build) | `C:\Users\Dad's PC\Desktop\AI-Hub` | `master` | `zlkhsxacfyxsctqpvbsh` |
| 2 | **Customer Hub** (Salesforce/CRM) | [GG-Arcade-Customer-Hub](https://github.com/ggarcadeV4/GG-Arcade-Customer-Hub) | `C:\Users\Dad's PC\Desktop\G and G Arcade Sass Salesforce` | `main` | Shared |
| 3 | **Arcade Network** (Fleet Manager) | [Arcade-Network-Fleet-Manager](https://github.com/ggarcadeV4/Arcade-Network-Fleet-Manager) | `C:\Users\Dad's PC\Desktop\Arcade Network 12-03-2025` | `main` | Shared |
| 4 | **InventoryGG** | [InventoryGG](https://github.com/ggarcadeV4/InventoryGG) | `C:\Users\Dad's PC\Desktop\InventoryGG` | `main` | Shared |

---

## 🔗 Shared Infrastructure

### Supabase (Shared Instance)
All projects connect to the same Supabase instance. Key shared tables:

| Table | Used By | Purpose |
|-------|---------|---------|
| `cabinet` | Fleet Manager, Arcade Assistant | Cabinet hardware, MAC addresses |
| `cabinet_heartbeat` | Fleet Manager | Heartbeat telemetry |
| `inventory` | InventoryGG | Parts catalog, stock levels |
| `builds` | InventoryGG, Customer Hub | Build profiles / customer builds |
| `customers` | Customer Hub | Customer contact info |
| `ai_usage` | All | AI call logging |

### AI Provider
- **Google Gemini 2.0 Flash** — shared across all projects

---

## 🤖 Jules Task Routing

| Task Domain | Target Repo |
|-------------|-------------|
| Cabinet AI / Playnite / local scripts | `Arcade-Assistant-Basement-Build` |
| CRM / customer workflows / Vector AI | `GG-Arcade-Customer-Hub` |
| Fleet telemetry / cabinet monitoring | `Arcade-Network-Fleet-Manager` |
| Parts inventory / purchasing / BOM | `InventoryGG` |

---

## 📋 Agent Instruction Files

Each project has an `AGENTS.md` at its root providing context for any AI agent (Jules, Claude, Gemini, etc.).
