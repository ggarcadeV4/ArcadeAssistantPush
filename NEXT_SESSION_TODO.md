# Next Session TODO - LED Blinky Continuation

## Current Status
✅ **LED Blinky Backend Bootstrap COMPLETE** (2025-10-31)
- 9 files created (models, resolver, service, sequencer, router, tests, __init__)
- 8 streaming endpoints implemented
- 50+ tests with Pydantic V2 compatibility
- Integrated with backend/app.py startup
- All critical fixes from mistake-watcher and pythia-python-optimizer applied

## Choose Next Direction:

### **Option A: Document & Reference**
The work is complete - use this session's deliverables as reference/documentation.

**Actions:**
- Review implementation in `backend/services/blinky/`
- Review API docs at `/api/blinky/health`
- Test endpoints with curl or Postman
- No additional coding needed

---

### **Option B: Implement Enhancement Ideas**
Add the optimization suggestions from the brainstorming session.

**Priority Enhancements:**
1. **Background Task Preloading** - Move XML parsing to `app.lifespan` async context
2. **Supabase Hybrid Cache** - Hot ROMs in LRU, cold in Supabase with RLS
3. **Extended Tutor Pipeline** - Add `tutor_mode` param to apply_game_pattern
4. **Quest Guide Mode** - Wizard presets for kid-friendly sequences
5. **Callback Support** - `on_step` bus integration for Vicky TTS

**Estimated Scope:** 3-4 files modified, 2-3 new files, ~20 tests added

---

### **Option C: Frontend Integration**
Build React hooks and LED Blinky panel UI.

**Deliverables:**
1. **LEDBlinkyPanel.jsx** - Main panel with grid visualization
2. **useRomLights hook** - Query `/pattern/{rom}`, mutation for apply
3. **useTutorSequence hook** - Stream consumer for tutor mode
4. **Bus Integration** - LaunchBox launch triggers auto-apply
5. **Memoized Grid** - Active/inactive LED visualization with CSS

**Files:**
- `frontend/src/panels/led-blinky/LEDBlinkyPanel.jsx`
- `frontend/src/hooks/useLEDBlinky.js`
- `frontend/src/services/blinkyClient.js`
- Tests: `frontend/src/panels/led-blinky/__tests__/`

**Estimated Scope:** 5-7 new files, Jest/MSW tests, >85% coverage

---

## Recommendation

**Start with Option C (Frontend Integration)** - The backend is solid and production-ready. The frontend will make it usable and visible to the user. Then circle back to Option B enhancements based on real-world usage patterns.

## Branch
`verify/p0-preflight`

## Context from This Session
- User wants game-aware lighting (active buttons lit, inactive dark)
- Examples: DK (1 red), SF2 (6 multi-color), Pac-Man (all dark)
- Tutor sequences for teaching controls
- Integration with 9-panel ecosystem (Voice Vicky, LaunchBox, Scorekeeper, etc.)
