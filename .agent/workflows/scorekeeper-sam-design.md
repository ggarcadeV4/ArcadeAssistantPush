# Scorekeeper Sam — Enhanced Features Design

> Phase 4: Data Models & Conceptual Expansion  
> Created: 2025-12-11

---

## Overview

This document outlines the design for three key enhancements to Scorekeeper Sam:

1. **Profile-to-Initials Mapping** — Link arcade initials (e.g., "DAD") to player profiles
2. **Hidden/Moderated Scores** — Exclude practice runs or inappropriate entries
3. **Household Player Registry** — Manage a family/household of known players

---

## 1. Profile-to-Initials Mapping

### Problem
Arcade games typically only capture 3-letter initials (DAD, MOM, SAR). Sam should be able to:
- Recognize that "DAD" on the Street Fighter leaderboard is the same as "DAD" on Pac-Man
- Link initials to a named profile for richer statistics
- Handle disambiguation when multiple people use the same initials

### Data Model

```typescript
interface InitialsMapping {
  id: string;                    // UUID
  initials: string;              // e.g., "DAD" (1-3 chars, uppercase)
  profile_id: string;            // FK to player_profiles.id
  game_ids: string[] | null;     // Optional: limit to specific games (null = all games)
  created_at: string;            // ISO timestamp
  created_by: string;            // Who created this mapping
  priority: number;              // For disambiguation (higher = preferred)
}

interface PlayerProfile {
  id: string;                    // UUID
  display_name: string;          // e.g., "Dad", "Greg"
  avatar_url: string | null;     // Optional avatar
  household_id: string | null;   // FK to households.id
  external_id: string | null;    // For cloud sync (Supabase user_id)
  created_at: string;
  updated_at: string;
}
```

### Supabase Table: `initials_mapping`

```sql
CREATE TABLE initials_mapping (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  initials VARCHAR(3) NOT NULL,
  profile_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
  game_ids TEXT[] DEFAULT NULL,  -- NULL means applies to all games
  cabinet_id UUID REFERENCES cabinet(id) ON DELETE SET NULL,
  priority INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  created_by TEXT,
  
  UNIQUE(initials, profile_id, cabinet_id)
);

CREATE INDEX idx_initials_mapping_lookup ON initials_mapping(initials, cabinet_id);
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sam/profiles` | GET | List all player profiles |
| `/api/sam/profiles` | POST | Create a new profile |
| `/api/sam/profiles/{id}` | PATCH | Update profile |
| `/api/sam/profiles/{id}/initials` | GET | Get initials linked to this profile |
| `/api/sam/initials-mapping` | POST | Link initials to a profile |
| `/api/sam/initials-mapping` | DELETE | Remove an initials mapping |
| `/api/sam/resolve-initials/{initials}` | GET | Resolve initials to a profile |

### Voice Commands

Sam should understand:
- *"DAD is Greg"* → Create mapping: DAD → Greg's profile
- *"Who is AAA?"* → Resolve initials to profile
- *"Link MOM to Sarah's profile"* → Create mapping

---

## 2. Hidden/Moderated Scores

### Problem
Not all scores should appear on the leaderboard:
- Practice runs that shouldn't count
- Inappropriate initials that need moderation
- Test scores during setup

### Data Model

```typescript
interface ScoreEntry {
  id: string;
  game_id: string;
  player_initials: string;
  score: number;
  achieved_at: string;
  
  // Hidden/moderation fields
  hidden: boolean;               // If true, excluded from public leaderboard
  hidden_reason: HiddenReason | null;
  hidden_at: string | null;
  hidden_by: string | null;      // Who marked it hidden
  moderation_status: 'approved' | 'pending' | 'rejected';
  moderation_note: string | null;
}

type HiddenReason = 
  | 'practice'           // Marked as practice by user
  | 'inappropriate'      // Inappropriate initials
  | 'test'               // Test/setup score
  | 'duplicate'          // Duplicate entry
  | 'manual'             // Manually hidden by operator
  | 'auto_moderated';    // Flagged by auto-moderation
```

### Supabase Table Addition

```sql
ALTER TABLE cabinet_game_score ADD COLUMN hidden BOOLEAN DEFAULT FALSE;
ALTER TABLE cabinet_game_score ADD COLUMN hidden_reason TEXT;
ALTER TABLE cabinet_game_score ADD COLUMN hidden_at TIMESTAMPTZ;
ALTER TABLE cabinet_game_score ADD COLUMN hidden_by TEXT;
ALTER TABLE cabinet_game_score ADD COLUMN moderation_status TEXT DEFAULT 'approved';
ALTER TABLE cabinet_game_score ADD COLUMN moderation_note TEXT;

CREATE INDEX idx_scores_visible ON cabinet_game_score(game_id, hidden) WHERE hidden = FALSE;
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sam/scores/{id}/hide` | POST | Hide a score with reason |
| `/api/sam/scores/{id}/unhide` | POST | Restore a hidden score |
| `/api/sam/scores/hidden` | GET | List hidden scores (admin) |
| `/api/sam/scores/moderate` | POST | Bulk moderation |

### Auto-Moderation Rules

Sam can auto-flag scores that match:
- Initials containing profanity (configurable word list)
- Impossibly high scores (game-specific thresholds)
- Rapid duplicate entries (anti-spam)

### Voice Commands

- *"Hide that last score — it was just practice"*
- *"Mark DAD's Pac-Man score as inappropriate"*
- *"Show me hidden scores"*

---

## 3. Household Player Registry

### Problem
A cabinet typically belongs to a household with known regular players. Sam should:
- Know who the "usual suspects" are
- Suggest initials when a player says their name
- Track per-player statistics across all games

### Data Model

```typescript
interface Household {
  id: string;                    // UUID
  name: string;                  // e.g., "The Smith Family"
  cabinet_ids: string[];         // Cabinets in this household
  created_at: string;
  settings: HouseholdSettings;
}

interface HouseholdSettings {
  auto_moderate: boolean;        // Auto-hide inappropriate scores
  require_approval: boolean;     // New scores need approval
  allow_guest_scores: boolean;   // Allow unlinked initials
  default_visibility: 'public' | 'household_only' | 'private';
}

interface HouseholdMember {
  id: string;
  household_id: string;          // FK to households.id
  profile_id: string;            // FK to player_profiles.id
  role: 'owner' | 'admin' | 'member' | 'guest';
  joined_at: string;
  invited_by: string | null;
}
```

### Supabase Tables

```sql
CREATE TABLE households (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE household_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  profile_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'member',
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  invited_by UUID REFERENCES player_profiles(id),
  
  UNIQUE(household_id, profile_id)
);

CREATE TABLE household_cabinets (
  household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  cabinet_id UUID NOT NULL REFERENCES cabinet(id) ON DELETE CASCADE,
  linked_at TIMESTAMPTZ DEFAULT NOW(),
  
  PRIMARY KEY(household_id, cabinet_id)
);
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sam/household` | GET | Get current cabinet's household |
| `/api/sam/household` | POST | Create household for cabinet |
| `/api/sam/household/members` | GET | List household members |
| `/api/sam/household/members` | POST | Add a member |
| `/api/sam/household/members/{id}` | DELETE | Remove a member |
| `/api/sam/household/stats` | GET | Household-wide statistics |

### Voice Commands

- *"Who's in the family?"* → List household members
- *"Add Tommy to the household"* → Create profile + membership
- *"Show family leaderboard"* → Filter to household members

---

## Implementation Priority

| Feature | Priority | Complexity | Dependencies |
|---------|----------|------------|--------------|
| Profile-to-Initials | HIGH | Medium | player_profiles table |
| Hidden Scores | HIGH | Low | ALTER existing table |
| Household Registry | MEDIUM | Medium | New tables |
| Voice Commands | LOW | Medium | All above + NLU |

---

## UI Mockup Concepts

### Initials Mapping UI
```
┌─────────────────────────────────────────────────────────┐
│ Player Profiles                                        │
├─────────────────────────────────────────────────────────┤
│ ┌──────┐  Greg (Dad)                                   │
│ │ 👤   │  Initials: DAD, GRG                           │
│ └──────┘  47 scores across 12 games                    │
│           ─────────────────────────────────            │
│ ┌──────┐  Sarah                                        │
│ │ 👤   │  Initials: SAR, SAS                           │
│ └──────┘  23 scores across 8 games                     │
└─────────────────────────────────────────────────────────┘
```

### Hidden Scores Admin
```
┌─────────────────────────────────────────────────────────┐
│ Hidden Scores (3)                                      │
├─────────────────────────────────────────────────────────┤
│ ⚠️ Pac-Man | AAA | 999,999,999 | "impossibly high"     │
│    [Unhide] [Delete]                                   │
│                                                        │
│ 🎮 Galaga | TST | 5,000 | "test score"                │
│    [Unhide] [Delete]                                   │
│                                                        │
│ ⚠️ Street Fighter | XXX | 50 | "inappropriate"        │
│    [Unhide] [Delete]                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Create Supabase migrations** for the new tables
2. **Implement backend endpoints** in `backend/routers/scorekeeper.py`
3. **Add voice command handlers** to Sam's NLU
4. **Build UI components** for profile management
5. **Wire up initials resolution** in score display
