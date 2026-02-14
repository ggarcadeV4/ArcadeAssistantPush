# 🎮 Arcade Assistant — **Tendency File Contract (v1)**
A unified per-profile preference system for all 9 panels

## 1. Purpose
The Tendency File is the **long-term memory** of the Arcade Assistant.
It stores everything the system learns about a specific user — their preferences, play style, controller habits, game history, voice settings, and more.

It is not session data. It is not panel-specific state.
It is **the personal profile** for each user.

> **One profile = One Tendency File.**
> Every panel reads from it. Every panel contributes to it.

## 2. Deterministic File Path
All tendency files live under the A: Drive deterministic structure:

    A:\Arcade Assistant\profiles\<profile_id>\tendencies.json

The system never searches dynamically.
Paths are fixed, using the A: Drive Strategy.

## 3. Identity Layers
Three identity layers define Arcade Assistant behavior:

### 3.1 Session Host Profile
Chosen in Vicky Voice ("Primary User").
Stored in:

    A:\Arcade Assistant\session\session.json

### 3.2 Panel Target Profile
Chosen via the dropdown at the top of **each panel**.
Defines which user's tendencies you are reading/editing.

### 3.3 Seat Map (P1–P4)
Defined in Vicky's "Current Session" grid.
Used by Scorekeeper Sam, Gunner, and others to know who is physically standing at P1/P2/etc.

A panel may use all three values simultaneously.

## 4. Why One Universal File
All nine panels must share a single per-profile tendency file.
Panel-specific files create inconsistency, duplicated preferences, sync issues, and break the illusion that "the cabinet knows me."

A single file with panel-specific namespaces ensures unified behavior.

## 5. Universal Tendency File Schema (v1)

{
  "profile_id": "string",

  "core": {
    "display_name": "string",
    "initials": "string",
    "preferred_language": "string"
  },

  "controllers": {
    "owned_devices": [
      { "id": "string", "type": "string", "slots": ["p1","p2","p3","p4"] }
    ],
    "layout": "string",
    "invert_y_axis": false
  },

  "launchbox_lora": {
    "favorite_platforms": [],
    "favorite_tags": [],
    "recently_played": []
  },

  "scorekeeper_sam": {
    "rankings": {}
  },

  "dewey": {
    "tournament_history": []
  },

  "vicky_voice": {
    "custom_vocabulary": [],
    "stt_engine": "string",
    "confidence_threshold": 0.75
  },

  "gunner": {
    "sensitivity": 0.0,
    "handedness": "left/right"
  },

  "led_blinky": {
    "brightness": 0.0,
    "theme": "string"
  },

  "doc": {
    "explanation_style": "short/verbose"
  },

  "meta": {
    "version": 1,
    "last_modified": "ISO 8601 timestamp"
  }
}

Each panel must read/write **only its own namespace**.

## 6. Panel Responsibilities

### Vicky Voice
- Creates/loads profiles
- Writes core preferences
- Sets session_host and seat_map
- Writes voice-related tendencies

### Controller Chuck
- Writes the "controllers" namespace
- Updates identity map for physical controllers

### Console Wizard
- Reads controllers namespace
- Writes wizard-specific metadata (when needed)
- Never touches voice/lightgun sections

### Scorekeeper Sam
- Reads seat_map from session.json
- Writes rankings to "scorekeeper_sam" namespace

### LaunchBox Lora
- Reads favorite platforms/tags
- Writes learned game preferences

### Dewey
- Reads from scorekeeper_sam
- Writes tournament history

### Gunner
- Writes gun calibration and sensitivity

### LED Blinky Panel
- Writes brightness/theme

### Doc Panel
- Reads explanation preferences
- Writes only with confirmation

## 7. Safety & Write Rules
All Tendency writes must:

- Go through FastAPI backend
- Respect sanctioned paths in manifest.json
- Perform dry-run first
- Create timestamped backups
- Log: profile_id, panel, target file, device_id, timestamp, diff
- Never silently auto-apply without user confirmation
- Follow the deterministic A: Drive Strategy

## 8. Session JSON (Short-Term Memory)

    A:\Arcade Assistant\session\session.json

Contains:

{
  "session_host": "profile_id",
  "active_profiles": [],
  "seat_map": {
    "p1": "profile_id",
    "p2": "profile_id",
    "p3": "profile_id",
    "p4": "profile_id"
  }
}

Panels use session.json only for short-lived gameplay state.

## 9. Evolution Rules
- meta.version is incremented when schema changes
- Panels must tolerate unknown keys
- New namespaces may be added without breaking older profiles
