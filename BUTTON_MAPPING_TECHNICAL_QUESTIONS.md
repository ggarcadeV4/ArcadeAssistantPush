# Button Mapping Architecture - Technical Questions for Expert Review

## Context
We're building an arcade cabinet controller configuration system that needs to handle arbitrary physical button wiring from PactoTech-2000T XInput encoder boards. The core challenge is creating a translation layer between:
- Physical button positions (what the operator sees/presses)
- Xbox button numbers sent by the encoder hardware (what the OS receives)
- MAME JOYCODE mappings (what the emulator expects)

## Current Architecture Understanding

**Hardware**: PactoTech-2000T boards emulate Xbox 360 controllers with fixed internal wiring
- Physical button position 1 might be internally wired to Xbox Button 5
- Physical button position 2 might be internally wired to Xbox Button 8
- etc.

**Software Layers**:
1. `controls.json` - Stores user's logical button assignments (e.g., "Player 1 Button 1 = Light Punch")
2. MAME config generator - Creates `.cfg` files mapping game functions to JOYCODE_X_BUTTONX

**User Workflow**:
- User clicks GUI button labeled "P1 Button 1"
- User presses the physical button they want to assign
- System should capture which Xbox button number that physical button sends
- MAME config should map the game function to that actual Xbox button number

## Critical Questions for Expert Review

### Question 1: PactoTech Board Wiring Consistency
**Is the internal wiring of PactoTech-2000T boards consistent across all units, or does each board potentially have different physical-to-Xbox-button mappings?**

**Why this matters**:
- If wiring is consistent → we can create a universal lookup table
- If wiring varies per board → each cabinet needs individual calibration

**Follow-up**: If wiring IS consistent, can we obtain the factory wiring diagram from PactoTech to create a definitive mapping table?

---

### Question 2: Architectural Pattern for Translation Layer
**What is the correct architectural pattern for handling this three-layer translation (Physical → Xbox Button → MAME JOYCODE)?**

**Our current approach**:
```
controls.json stores:
{
  "p1.button1": {
    "pin": 8,              // Physical position on board
    "captured_code": "GAMEPAD_BTN_5"  // Xbox button it sends (captured at runtime)
  }
}

MAME config generator uses:
JOYCODE_1_BUTTON5  // Based on captured_code, not the logical button number
```

**Alternative approach considered**:
Create a permanent "board profile" JSON that maps:
```
{
  "physical_pin_8": "XBOX_BUTTON_5",
  "physical_pin_5": "XBOX_BUTTON_2"
}
```

**Question**: Which approach is architecturally sound for a scalable, maintainable system? Should we:
- A) Capture keycodes at configuration time (current approach)
- B) Use a fixed board profile lookup table
- C) Implement both with the lookup table as a fallback/validation

---

### Question 3: MAME Config Generation Logic
**Should the MAME config generator map based on what the hardware ACTUALLY sends, or based on what the logical button assignment SHOULD BE?**

**Scenario**:
- User assigns "Light Punch" to the button they call "P1 Button 1"
- That physical button sends Xbox Button 5 (JOYCODE_1_BUTTON5)
- Street Fighter expects "Light Punch" on a specific button

**Option A - Map to actual hardware**:
```xml
<port tag="P1_BUTTON1" type="P1_BUTTON1">
  <newseq type="standard">JOYCODE_1_BUTTON5</newseq>  <!-- Use what hardware sends -->
</port>
```

**Option B - Map to logical expectation**:
```xml
<port tag="P1_BUTTON1" type="P1_BUTTON1">
  <newseq type="standard">JOYCODE_1_BUTTON1</newseq>  <!-- Use what we wish it sent -->
</port>
```

**Question**: Which approach is correct? Does MAME's JOYCODE system expect hardware-accurate codes or logical button numbers?

---

### Question 4: Scalability Across Different Cabinets
**How do we design this system to work generically across different cabinet configurations without requiring per-cabinet calibration?**

**Constraints**:
- Must support any arbitrary button wiring configuration
- Should work for multiple encoder types (not just PactoTech)
- Needs to handle 2-player, 3-player, and 4-player cabinets
- Should accommodate different game layouts (6-button fighters, 8-button layouts, 4-button classics)

**Question**: What's the minimal set of information we need to store to make this system portable? Should we:
- Store only logical assignments and detect hardware at runtime
- Store complete hardware profiles with fallback to auto-detection
- Use a hybrid approach with user-overridable defaults

---

### Question 5: Validation and Error Handling
**How should we validate that the button mapping translation is working correctly, and what error handling should be in place?**

**Potential failure modes**:
1. User presses wrong button during calibration
2. Hardware sends unexpected button codes
3. MAME config doesn't match hardware reality
4. Board wiring changes after firmware update

**Question**: What validation steps should we implement:
- A) Pre-flight check that verifies all buttons send expected codes
- B) Runtime detection of mapping drift
- C) User-facing diagnostic tool to verify button functionality
- D) Automated testing against known good configurations

---

### Question 6: Data Persistence and Migration
**Where and how should we persist the button mapping data to ensure it survives system updates and hardware changes?**

**Current storage**:
- `controls.json` - User's logical button assignments
- MAME `.cfg` files - Generated configs per game

**Questions**:
- Should we separate "board profile" (hardware wiring) from "user preferences" (button assignments)?
- How do we handle migration when user swaps encoder boards?
- Should hardware profiles be version-controlled separately from user configs?
- What happens if PactoTech releases a firmware update that changes button codes?

**Proposed structure**:
```
/config/
  /board_profiles/
    pactotech_2000t_v1.json      # Factory wiring diagram
    pactotech_2000t_v2.json      # Updated wiring if firmware changes
  /user_assignments/
    cabinet_001_controls.json    # User's button preferences
```

---

## Additional Context for Expert

**Technology Stack**:
- Backend: Python (FastAPI) with pygame for input detection
- Frontend: React for GUI configuration
- Config files: JSON for storage, XML for MAME output
- Hardware: PactoTech-2000T XInput encoders (emulate Xbox 360 controllers)

**Scale**:
- Target: 4-player cabinets (4 joysticks, 32+ buttons total)
- Game library: ~14,000 MAME ROMs with varying button layouts
- Need to support both generic and game-specific configs

**User Skill Level**:
- Cabinet operators (not necessarily programmers)
- Should be able to reconfigure buttons via GUI without editing JSON

**Critical Success Criteria**:
1. User presses a physical button → correct action happens in game
2. System works across different cabinet wiring configurations
3. Mapping persists correctly after system restarts
4. Clear diagnostic path when buttons don't work as expected

---

## What We Need From Expert Review

1. **Validation**: Is our architectural understanding correct?
2. **Recommendation**: Which approach (A, B, or C) should we implement for each question?
3. **Best Practices**: Industry standards for handling input device abstraction layers
4. **Pitfalls**: Common mistakes to avoid in this type of mapping system
5. **Testing Strategy**: How to verify the system works correctly across different configurations

---

## Files for Expert Reference

If expert wants to review actual code:
- `a:\Arcade Assistant Local\config\mappings\controls.json` - Current button assignments
- `a:\Arcade Assistant Local\backend\services\mame_config_generator.py` - MAME config generation logic
- `a:\Arcade Assistant Local\backend\services\chuck\input_detector.py` - Button capture logic (referenced but not yet reviewed in detail)

---

**Prepared by**: Claude (Arcade Assistant AI)
**Date**: 2025-12-30
**Purpose**: Expert review before implementing button mapping translation layer
