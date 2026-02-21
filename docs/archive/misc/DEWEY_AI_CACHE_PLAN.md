# Dewey AI Conversation History Cache Plan
**Status:** Template - Not Yet Started
**Priority:** Low (Nice to Have)
**Pattern:** Option C Checkpoint (follows LaunchBox image cache model)

---

## Problem Statement

### Current Issue
- Dewey AI starts fresh conversation on every session
- No memory of previous interactions
- Cannot reference past conversations or learn user preferences
- Lost context when backend restarts

### Performance Goal
- Cache recent conversation history to disk
- Restore context on Dewey initialization
- Limit cache size (e.g., last 50 messages or 7 days)
- Enable "continue previous conversation" feature

---

## Proposed Architecture

### Cache Structure
```json
{
  "version": "1.0",
  "created_at": "2025-10-08T12:34:56.789Z",
  "max_messages": 50,
  "max_age_days": 7,
  "conversations": [
    {
      "timestamp": "2025-10-08T12:00:00.000Z",
      "role": "user",
      "content": "Tell me about Street Fighter"
    },
    {
      "timestamp": "2025-10-08T12:00:05.000Z",
      "role": "assistant",
      "content": "Street Fighter II is a legendary 1991 fighting game..."
    }
  ]
}
```

### Cache Location
`backend/cache/dewey_conversation_cache.json`

---

## Implementation Checklist

### Step 1: Create Conversation Cache Service
- [ ] Create `backend/services/conversation_cache.py`
- [ ] Add cache save/load methods
- [ ] Implement rolling window (keep last N messages)
- [ ] Add age-based expiration

### Step 2: Integrate with Dewey Panel
- [ ] Update Dewey to load recent history on startup
- [ ] Add "Clear History" button for privacy
- [ ] Save messages after each AI response

### Step 3: Testing
- [ ] Test conversation persistence across restarts
- [ ] Test rolling window (oldest messages removed)
- [ ] Test age-based cleanup

---

## Success Criteria
- Dewey remembers recent conversation context
- User can continue previous discussion after restart
- Privacy controls allow clearing history

---

**Status:** Template ready for future implementation
**Estimated Effort:** 20-25 minutes implementation + 10 minutes testing
**Dependencies:** AI chat integration must be implemented first
**Privacy Note:** Should include user consent/clear history option
