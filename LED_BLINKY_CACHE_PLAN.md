# LED Blinky Hardware State Cache Plan
**Status:** Template - Not Yet Started
**Priority:** Medium
**Pattern:** Option C Checkpoint (follows LaunchBox image cache model)

---

## Problem Statement

### Current Issue
- LED Blinky communicates with USB/HID devices
- Device state queries can be slow or blocking
- No persistence of last-known device states
- Panel must rediscover hardware on every backend restart

### Performance Goal
- Cache last-known device states to disk
- Instant load on startup instead of hardware enumeration
- Background refresh for actual device changes
- Reduce LED panel initialization time

---

## Proposed Architecture

### Cache Structure
```json
{
  "version": "1.0",
  "created_at": "2025-10-08T12:34:56.789Z",
  "devices": {
    "led_blinky_v1": {
      "vendor_id": "0x1234",
      "product_id": "0x5678",
      "last_known_state": { ... },
      "last_seen": "2025-10-08T12:30:00.000Z"
    }
  }
}
```

### Cache Location
`backend/cache/led_hardware_cache.json`

---

## Implementation Checklist

### Step 1: Create Hardware State Service
- [ ] Create `backend/services/hardware_state_cache.py`
- [ ] Add cache save/load methods
- [ ] Add auto-refresh logic (check actual hardware vs. cache)

### Step 2: Integrate with LED Blinky Panel
- [ ] Update LED Blinky initialization to check cache first
- [ ] Add fallback to hardware enumeration if cache stale
- [ ] Save state changes to cache on LED updates

### Step 3: Testing
- [ ] Test with LED Blinky connected
- [ ] Test with LED Blinky disconnected (cache should persist)
- [ ] Test cache invalidation after X days

---

## Success Criteria
- LED panel loads instantly from cache when hardware unchanged
- Graceful degradation if hardware actually changed
- User doesn't notice any difference except faster load times

---

**Status:** Template ready for future implementation
**Estimated Effort:** 15-20 minutes implementation + 10 minutes testing
**Dependencies:** None (can be implemented independently)
