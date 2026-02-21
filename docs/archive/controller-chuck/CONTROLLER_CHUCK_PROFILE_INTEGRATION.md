# Controller Chuck Profile Integration - Phase 1

## Implementation Summary

**Date**: 2025-12-30
**Status**: ✅ Phase 1 Complete (Display Only)

## What Was Implemented

### Phase 1: Profile Display (Completed)

Added profile awareness to Controller Chuck panel to show which user is currently active.

#### Frontend Changes:

1. **ControllerChuckPanel.jsx** ([controller/ControllerChuckPanel.jsx](frontend/src/panels/controller/ControllerChuckPanel.jsx)):
   - Added `useProfileContext` import
   - Reads current user from global ProfileContext
   - Displays user name in header subtitle: `"Arcade Encoder Board Mapping • {UserName}"`
   - Defaults to "Guest" if no profile set

2. **controller-chuck.css** ([controller/controller-chuck.css](frontend/src/panels/controller/controller-chuck.css)):
   - Added `.chuck-profile-indicator` styling
   - Subtle lime-green color (`#c8ff00`) matching panel theme
   - Hover effect for visual feedback

### How It Works

**User Flow:**
1. User sets their profile in Voice Panel (Vicky)
2. Profile syncs to global ProfileContext (`.aa/state/profile/user.json`)
3. Controller Chuck reads current user from ProfileContext
4. Header displays: `"Arcade Encoder Board Mapping • Dad"` (or Guest, Mom, Kid Y, etc.)

**Current Behavior:**
- ✅ Shows current primary user from Voice Panel
- ✅ Updates automatically when profile changes
- ❌ Does NOT save mappings per-user yet (all users share global `controls.json`)
- ❌ Does NOT have user selector dropdown

## Architecture Notes

### Profile System (Already Built)

**Global Profile Context:**
- **Location**: `frontend/src/context/ProfileContext.jsx`
- **Backend**: `backend/routers/profile.py`
- **Storage**: `.aa/state/profile/user.json`
- **Hook**: `useProfileContext()` - available to all panels

**Default Users:**
- Guest (default)
- Dad
- Mom
- Kid Y (Tim)
- Kid Z (Sarah)
- Custom users (can be added)

### LED Blinky Integration

**How Profile Preferences Will Flow to LED Blinky:**

1. **Current State** (Global Mapping):
   ```
   User configures Chuck → saves to controls.json
   LED Blinky reads controls.json → lights LEDs based on mapping
   ```

2. **Future State** (Per-User Mapping):
   ```
   User (Dad) configures Chuck → saves to user_mappings/Dad/controls.json
   LED Blinky receives user_id → loads Dad's controls.json
   LEDs light up according to Dad's button preferences
   ```

**Example:**
- **Dad's preference**: Shoot button on TOP row → Chuck maps `p1.button1: pin 4`
- **Kid Y's preference**: Shoot button on BOTTOM row → Chuck maps `p1.button1: pin 7`
- LED Blinky loads the active user's mapping and lights the correct button

## Phase 2 Roadmap (Future)

### Per-User Control Mappings

**Backend Work Needed:**

1. **Storage Structure:**
   ```
   state/controller/
     ├── controls.json              # Global fallback
     └── user_mappings/
         ├── Dad/
         │   └── controls.json
         ├── Mom/
         │   └── controls.json
         └── Kid_Y/
             └── controls.json
   ```

2. **API Changes:**
   - `GET /controller/mapping?user_id=Dad` - Load user-specific mapping
   - `POST /controller/mapping/save?user_id=Dad` - Save user-specific mapping
   - Fallback to global if no user-specific mapping exists

3. **Learn Wizard Integration:**
   - Add "Which user is configuring?" step at wizard start
   - Save wizard results under that user's profile
   - Option to copy from another user

**Frontend Work Needed:**

1. **User Selector:**
   ```jsx
   <select value={selectedUser} onChange={handleUserChange}>
     <option value="Guest">Guest</option>
     <option value="Dad">Dad</option>
     <option value="Mom">Mom</option>
     <option value="Kid_Y">Kid Y</option>
   </select>
   ```

2. **Load/Save Flow:**
   - Load mapping for selected user on change
   - Save mappings under selected user
   - Show indicator: "Editing Dad's controls"

3. **LED Blinky Updates:**
   - Accept `user_id` parameter in LED config endpoints
   - Load that user's control mapping
   - Display: "LEDs configured for: Dad"

### Multi-Player Per-User Assignment (Phase 3)

**Advanced Feature:**
- P1 Station = Dad's profile
- P2 Station = Kid Y's profile
- P3 Station = Mom's profile
- P4 Station = Kid Z's profile

**Use Case:**
- Each family member has their own button layout preference
- System loads correct mapping per physical station
- LED Blinky lights appropriate buttons per station

**Implementation:**
```json
// player_assignments.json
{
  "station_1": { "user": "Dad", "mapping": "user_mappings/Dad/controls.json" },
  "station_2": { "user": "Kid_Y", "mapping": "user_mappings/Kid_Y/controls.json" },
  "station_3": { "user": "Mom", "mapping": "user_mappings/Mom/controls.json" },
  "station_4": { "user": "Guest", "mapping": "controls.json" }
}
```

## Testing Instructions

### Verify Phase 1 Implementation:

1. **Start the development stack:**
   ```bash
   npm run dev
   ```

2. **Navigate to Voice Panel (Vicky):**
   - Open Voice Assistant panel
   - Set profile to "Dad" (or any user)
   - Save profile

3. **Navigate to Controller Chuck:**
   - Header should show: `"Arcade Encoder Board Mapping • Dad"`
   - Hover over "• Dad" to see tooltip: "Current profile: Dad"

4. **Change profile in Voice Panel:**
   - Switch to "Kid Y"
   - Return to Controller Chuck
   - Header should update to: `"Arcade Encoder Board Mapping • Kid Y"`

5. **Verify default behavior:**
   - Clear profile in Voice Panel
   - Chuck should show: `"Arcade Encoder Board Mapping • Guest"`

## Files Modified

### Frontend:
- `frontend/src/panels/controller/ControllerChuckPanel.jsx` - Added ProfileContext integration
- `frontend/src/panels/controller/controller-chuck.css` - Added profile indicator styling

### No Backend Changes:
- Phase 1 is display-only, uses existing profile system
- No new endpoints or storage needed yet

## Related Documentation

- **Voice Panel Profile System**: [VoicePanel.jsx](frontend/src/panels/voice/VoicePanel.jsx)
- **Profile Context**: [ProfileContext.jsx](frontend/src/context/ProfileContext.jsx)
- **Profile Backend**: [profile.py](backend/routers/profile.py)
- **LED Blinky Mapping Spec**: [control_mapping_spec.json](backend/profiles/led_blinky/control_mapping_spec.json)
- **MAME Config Generator**: [mame_config_generator.py](backend/services/mame_config_generator.py)

---

**Next Steps**: User feedback required to proceed with Phase 2 (per-user mapping storage)

**Recommendation**: Test Phase 1, then discuss whether per-user mappings are needed for your use case. Most arcade cabinets have fixed hardware wiring, so global mapping may be sufficient unless different family members want different button layouts.
