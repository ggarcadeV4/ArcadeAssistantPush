# Feature Request: Auto-Detect LaunchBox Installation

**Status:** Planned for Future Session
**Priority:** Medium
**Complexity:** Medium (1-2 hours)
**User Value:** High - "Just works" experience

---

## Problem Statement

Currently, users must manually specify `LAUNCHBOX_ROOT` in `.env` to point to their LaunchBox installation. For users with multiple LaunchBox builds (development, testing, production), this requires:

1. Editing `.env` every time they want to switch
2. Remembering exact paths to each LaunchBox installation
3. Potential errors from typos or incorrect paths

---

## User Story

> "I've got several instances of LaunchBox on my development machine. I want Arcade Assistant to show me which ones it finds and let me choose which one to use. This would be extremely versatile, easy to maintain, and incredibly marketable."
> — User, 2025-10-08

---

## Proposed Solution

### Auto-Detection with User Choice

**On First Startup (or when LAUNCHBOX_ROOT not configured):**

1. **Scan Common Locations:**
   ```
   C:\LaunchBox
   D:\LaunchBox
   E:\LaunchBox
   A:\LaunchBox
   C:\Program Files\LaunchBox
   C:\Games\LaunchBox
   {AA_DRIVE_ROOT}\LaunchBox
   ```

2. **Display Found Installations:**
   ```
   Found 3 LaunchBox installations:
   1. A:\LaunchBox (14,233 games, last modified: 2025-10-05)
   2. D:\LaunchBox-Dev (8,500 games, last modified: 2025-10-08)
   3. E:\LaunchBox-Backup (14,000 games, last modified: 2025-09-15)

   Which LaunchBox would you like to use? [1-3]:
   ```

3. **Save User Choice:**
   - Write selected path to `.env` automatically
   - Remember choice for future startups
   - Allow re-detection via command flag

---

## Technical Implementation

### Detection Logic

**File:** `backend/utils/launchbox_detector.py`

```python
def detect_launchbox_installations() -> List[LaunchBoxInstallation]:
    """
    Scan common locations for LaunchBox installations.

    Returns:
        List of detected installations with metadata
    """
    # Search drives and common paths
    # Validate by checking for LaunchBox.exe + Data/Platforms/*.xml
    # Count games, get last modified time
    # Return sorted by recency
```

### Selection Mechanisms

**Option A: CLI Prompt** (Simplest, 30 min)
- Use `input()` during backend startup
- Blocks until user selects
- Good for development/single-user setups

**Option B: Web UI Selection** (Better UX, 1-2 hours)
- Add `/api/setup/launchbox-installations` endpoint
- Frontend shows modal with options
- User clicks to select
- More user-friendly, professional

**Option C: Config File** (Hybrid)
- Detect and save to `launchbox_installations.json`
- User edits file or uses web UI
- No blocking prompts

### State Persistence

**File:** `.env` (auto-updated)
```bash
# Auto-detected and saved by Arcade Assistant
LAUNCHBOX_ROOT=D:\LaunchBox-Dev
```

**File:** `backend/cache/launchbox_installations.json`
```json
{
  "detected_at": "2025-10-08T18:30:00Z",
  "installations": [
    {
      "path": "A:\\LaunchBox",
      "game_count": 14233,
      "last_modified": "2025-10-05T10:00:00Z",
      "platforms": 53
    }
  ],
  "selected": "A:\\LaunchBox"
}
```

---

## User Experience Flow

### First-Time Setup
1. User starts Arcade Assistant
2. System detects no `LAUNCHBOX_ROOT` configured
3. Auto-scans for installations
4. Presents selection UI (CLI or Web)
5. User selects installation
6. System saves to `.env` and continues startup

### Changing Installation
**Option 1: Re-run Detection**
```bash
npm run detect-launchbox
```

**Option 2: Settings Panel**
- Frontend panel shows current LaunchBox
- "Change Installation" button
- Re-shows selection UI

**Option 3: Manual Edit**
- User edits `LAUNCHBOX_ROOT` in `.env`
- Works as before (manual override)

---

## Benefits

### For Users
- **Zero Configuration:** Works out of the box
- **Multi-Build Support:** Easy switching between dev/prod
- **Discovery:** Finds installations you forgot about
- **Validation:** Confirms installation is valid before using

### For Marketing
- **"No Setup Required"** - Major selling point
- **Professional UX** - Comparable to commercial software
- **Error Prevention** - Validates before startup
- **Flexibility** - Power users can still manual configure

---

## Implementation Phases

### Phase 1: Detection Engine (30 min)
- Implement `detect_launchbox_installations()`
- Validate installations (check for exe + XMLs)
- Gather metadata (game count, last modified)

### Phase 2: CLI Selection (15 min)
- Simple `input()` prompt
- Save selection to `.env`
- Works immediately

### Phase 3: Web UI (1 hour)
- Add detection endpoint
- Frontend modal component
- Better UX than CLI

### Phase 4: Polish (30 min)
- Settings panel integration
- Re-detection command
- Error handling & logging

---

## Risks & Mitigations

### Risk: Slow Scans
- **Mitigation:** Cache detected installations, only re-scan on demand
- **Mitigation:** Scan in background thread, show progress

### Risk: False Positives
- **Mitigation:** Validate strictly (exe + Data/Platforms/ + at least 1 XML)
- **Mitigation:** Show metadata so user can identify correct one

### Risk: User Confusion
- **Mitigation:** Clear instructions in selection UI
- **Mitigation:** Show current selection in status panel
- **Mitigation:** Allow manual override

---

## Dependencies

**Requires #1 (Configurable Path):** ✅ Already implemented
**Optional #2 (Multi-Image Dirs):** ✅ Already implemented

**New Dependencies:**
- None - uses stdlib only

---

## Testing Plan

1. **No LaunchBox found:** Shows helpful error, suggests manual config
2. **One installation:** Auto-selects, logs decision
3. **Multiple installations:** Shows selection UI
4. **Invalid selection:** Re-prompts with error message
5. **Manual override:** Respects `.env` if already set

---

## Future Enhancements

- **Network Shares:** Detect LaunchBox on network drives
- **Recent Activity:** Suggest most-recently-used installation
- **Profile Switching:** Quick-switch between installations
- **Validation Checks:** Warn if ROMs missing, images incomplete

---

## Decision Required

**When implementing, choose:**

1. **CLI or Web UI?**
   - CLI: Faster to implement (30 min), good for MVP
   - Web UI: Better UX (1-2 hours), more professional

2. **Auto-select if only one found?**
   - Yes: Saves time for most users
   - No: Always shows selection for transparency

3. **Re-detection frequency?**
   - On demand only (safer)
   - Auto-scan on startup if cache old (more convenient)

---

## Next Session Checklist

- [ ] Review this document
- [ ] Decide on selection mechanism (CLI vs Web UI)
- [ ] Implement detection engine
- [ ] Test with multiple LaunchBox installations
- [ ] Update documentation
- [ ] Add to `.env.example` comments

---

**Created:** 2025-10-08
**Conversation Reference:** Session with User re: multiple LaunchBox builds on development machine
