# Arcade Assistant Navigation Guide

## Quick Navigation Map

### Core Metadata Files
- **Component relationships**: `/linkmap.json` - Shows how all components connect
- **Domain terminology**: `/glossary.json` - Key terms and definitions
- **Backend routes**: `/backend/routers/index.json` - All API endpoints
- **Frontend panels**: `/frontend/src/panels/index.json` - Panel organization

### Finding Functionality

#### "Where does X live?"

| Feature | Location |
|---------|----------|
| **Game Library** | `backend/routers/launchbox.py`, `frontend/src/panels/launchbox/` |
| **Voice Recording** | `frontend/src/panels/voice/`, `gateway/ws/audio.js` |
| **LED Control** | `frontend/src/panels/led-blinky/`, WebSocket integration |
| **Config Management** | `backend/routers/config_ops.py`, `frontend/src/panels/_kit/DiffPreview` |
| **AI Chat** | `gateway/routes/ai.js`, `frontend/src/services/aiClient.js` |
| **Tournament Brackets** | `frontend/src/panels/scorekeeper/` |
| **System Health** | `frontend/src/panels/system-health/` |
| **Controller Setup** | `frontend/src/panels/controller/` |
| **Light Guns** | `frontend/src/panels/lightguns/` |

#### "Where should new feature Y go?"

1. **New Panel** → Create directory in `frontend/src/panels/{feature}/`
   - Add `{Feature}Panel.jsx` and `{feature}.css`
   - Register in `frontend/src/components/Assistants.jsx`

2. **New Backend Route** → Create in `backend/routers/{feature}.py`
   - Export `router` variable
   - Register in `backend/app.py`

3. **New Gateway Route** → Create in `gateway/routes/{feature}.js`
   - Export router
   - Register in `gateway/server.js`

4. **Shared Components** → Add to `frontend/src/panels/_kit/`

### File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| **React Components** | PascalCase | `LaunchBoxPanel.jsx` |
| **CSS Files** | kebab-case | `launchbox.css` |
| **Python Files** | snake_case | `launchbox.py` |
| **JavaScript (non-React)** | camelCase | `aiClient.js` |
| **Directories** | kebab-case | `led-blinky/` |

### Request Flow Patterns

#### Standard Data Flow
```
User Action → Panel → Gateway (8787) → Backend (8888) → File System/Database
```

#### AI Integration Flow
```
Panel → useAIAction → aiClient.js → Gateway /api/ai/chat → Anthropic/OpenAI
```

#### WebSocket Flow
```
Panel → WebSocket Manager → ws://localhost:8787/ws/{type} → Hardware/Service
```

#### Config Change Flow
```
1. Preview: Panel → /api/local/config/preview → Show diff
2. Apply: User approves → /api/local/config/apply → Create backup → Update file
3. Log: Changes written to /logs/changes.jsonl
```

### Character to Code Mapping

| Character | Panel Directory | Backend Router | Primary Files |
|-----------|----------------|----------------|---------------|
| **Vicky** | `voice/` | - | VoicePanel.jsx |
| **LoRa** | `launchbox/` | `launchbox.py` | LaunchBoxPanel.jsx |
| **Dewey** | `dewey/` | - | DeweyPanel.jsx |
| **Sam** | `scorekeeper/` | - | ScoreKeeperPanel.jsx |
| **Wiz** | `controller/` | - | ControllerWizardPanel.jsx |
| **LED Blinky** | `led-blinky/` | - | LEDBlinkyPanel.jsx |
| **Gunner** | `lightguns/` | - | LightGunsPanel.jsx |
| **Doc** | `system-health/` | - | SystemHealthPanel.jsx |

### Key Integration Points

#### LaunchBox (Currently Inactive)
- **Activation Required**: Set `AA_DRIVE_ROOT=A:\\`
- **Backend**: Uncomment imports in `backend/app.py` lines 27 & 74-75
- **Data Source**: `A:\\LaunchBox\\Data\\Platforms\\*.xml` (53 files)
- **Launch Method**: CLI_Launcher.exe NOT FOUND - needs alternative

#### Environment Variables
- Configuration: `.env` file (copy from `.env.example`)
- Required: `ANTHROPIC_API_KEY`, `AA_DRIVE_ROOT`
- Optional: `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`

#### Ports
- Frontend Dev: 5173 (Vite)
- Gateway: 8787 (Express)
- Backend: 8000 (npm) or 8888 (direct Python)

### Semantic Annotations

All major files include semantic breadcrumbs for AI navigation:

```javascript
// @panel: PanelName
// @role: Description
// @owner: CharacterName
// @linked: RelatedFiles
```

```python
# @router: router_name
# @role: Description
# @owner: CharacterName
# @linked: RelatedFiles
```

### Quick Commands

#### Find all panels
```bash
ls frontend/src/panels/
```

#### Find all routers
```bash
ls backend/routers/
```

#### Find component usage
```bash
grep -r "ComponentName" frontend/src/
```

#### Check LaunchBox status
```bash
grep -n "is_on_a_drive" backend/routers/launchbox.py
```

#### View metadata
```bash
cat backend/routers/index.json
cat frontend/src/panels/index.json
```

### Development Patterns

1. **Always use Panel Kit** for new panels
2. **Mock data first** when not on A: drive
3. **Semantic breadcrumbs** in all new files
4. **Update metadata** when adding features
5. **Document relationships** in linkmap.json

### Troubleshooting Navigation

**Q: Can't find where a feature is implemented?**
1. Check `/linkmap.json` for component relationships
2. Search for the feature name in `/glossary.json`
3. Use grep to find occurrences

**Q: Not sure where to add new code?**
1. Check similar features in `/linkmap.json`
2. Follow patterns in `index.json` files
3. Look for `@linked` annotations in existing files

**Q: Need to understand data flow?**
1. Start at the panel component
2. Follow `@linked` annotations
3. Check `/linkmap.json` navigation_paths

## Metadata Maintenance

When adding new features:
1. Update `/backend/routers/index.json` for new routes
2. Update `/frontend/src/panels/index.json` for new panels
3. Update `/linkmap.json` with relationships
4. Update `/glossary.json` with new terms
5. Add semantic breadcrumbs to new files