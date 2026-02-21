# LaunchBox Image Cache Implementation Plan
**Status:** Ready to Implement
**Priority:** High (blocks other panels from accessing game data during 35-40s startup)
**Created:** 2025-10-08
**Session Context:** Image loading + GUI polish complete, disk cache next

---

## Problem Statement

### Current Performance Issue
**Backend Startup Time:** 35-40 seconds
- XML Parsing: ~5s (10,112 games across 53 platform XMLs)
- **Image Scanner:** ~30-35s (walks entire `A:\LaunchBox\Images\` directory tree)
- Total: Blocks other panels from functioning during this window

### Cross-Panel Impact
- **Dewey** routes users to other panels (Controller Chuck, etc.)
- **Other panels** need game data but LaunchBox parser isn't ready
- **User Experience:** 35-40s blank/loading state on first interaction

### Target Performance
- **After Disk Cache:** 8-12s backend startup (20-25s improvement)
- **Cache Load:** ~2-3s to read JSON from disk
- **Benefit:** Other panels get game data in 8-12s instead of 40s

---

## Current Architecture (Completed Today)

### What Works ✅
1. **Image Scanner Service** (`backend/services/image_scanner.py`)
   - Pre-scans all image directories on startup
   - Fuzzy matching with 85% similarity threshold
   - Handles filename sanitization (colons → underscores, etc.)
   - In-memory cache: `{platform: {image_type: {sanitized_title: full_path}}}`
   - Performance: <5ms lookups, ~30s scan time

2. **Parser Integration** (`backend/services/launchbox_parser.py`)
   - Lines 142-144: Uses `image_scanner.get_image_path()` with fuzzy matching
   - Falls back to constructed paths if scanner not initialized

3. **Frontend Integration** (`frontend/src/panels/launchbox/LaunchBoxPanel.jsx`)
   - Displays game images with fallback to placeholder
   - Browser caches images (24-hour cache headers)
   - Smart error handling (no console spam on 404)

4. **Gateway Proxy** (`gateway/routes/launchboxProxy.js`)
   - Handles binary image data correctly (lines 66-69)
   - Prevents image corruption

### What's Next 🔄
- **Disk Cache:** Persist image scanner results to JSON file
- **Fast Reload:** Load from disk instead of re-scanning on subsequent startups
- **Auto-Refresh:** Smart cache invalidation based on age

---

## Disk Cache Design

### File Structure
```
backend/
├── cache/                        # New directory (create if not exists)
│   └── image_cache.json          # Persistent cache file
├── services/
│   └── image_scanner.py          # Add disk caching logic
```

### JSON Cache Format
```json
{
  "version": "1.0",
  "created_at": "2025-10-08T12:34:56.789Z",
  "scan_duration_seconds": 29.3,
  "platforms_scanned": 50,
  "images_found": 17906,
  "cache": {
    "Arcade": {
      "clear_logo": {
        "street_fighter_ii": "A:\\LaunchBox\\Images\\Arcade\\Clear Logo\\Street Fighter II-01.png",
        "pac_man": "A:\\LaunchBox\\Images\\Arcade\\Clear Logo\\Pac-Man-01.png"
      },
      "box_front": { ... },
      "screenshot": { ... }
    },
    "Nintendo Entertainment System": { ... }
  }
}
```

### Cache Invalidation Strategy
1. **Age-Based:** Auto-refresh if cache file older than 7 days
2. **Manual:** POST `/api/launchbox/images/refresh` forces rescan
3. **Missing File:** If `image_cache.json` doesn't exist, scan and create

---

## Implementation Checklist

### Step 1: Update Image Scanner Service
**File:** `backend/services/image_scanner.py`

- [ ] **Add cache directory constant**
  ```python
  CACHE_DIR = Path(__file__).parent.parent / "cache"
  CACHE_FILE = CACHE_DIR / "image_cache.json"
  CACHE_MAX_AGE_DAYS = 7
  ```

- [ ] **Add cache save method**
  ```python
  def _save_cache_to_disk(self):
      """Save current image cache to disk as JSON."""
      CACHE_DIR.mkdir(exist_ok=True)
      cache_data = {
          "version": "1.0",
          "created_at": datetime.now().isoformat(),
          "scan_duration_seconds": self._scan_stats["scan_duration"],
          "platforms_scanned": self._scan_stats["platforms_scanned"],
          "images_found": self._scan_stats["images_found"],
          "cache": self._image_cache
      }
      with open(CACHE_FILE, 'w', encoding='utf-8') as f:
          json.dump(cache_data, f, indent=2)
      logger.info(f"💾 Image cache saved to disk: {CACHE_FILE}")
  ```

- [ ] **Add cache load method**
  ```python
  def _load_cache_from_disk(self) -> bool:
      """Load image cache from disk if available and fresh."""
      if not CACHE_FILE.exists():
          logger.info("No disk cache found, will perform full scan")
          return False

      try:
          with open(CACHE_FILE, 'r', encoding='utf-8') as f:
              cache_data = json.load(f)

          # Check cache age
          created_at = datetime.fromisoformat(cache_data["created_at"])
          age_days = (datetime.now() - created_at).days

          if age_days > CACHE_MAX_AGE_DAYS:
              logger.info(f"Cache is {age_days} days old (max {CACHE_MAX_AGE_DAYS}), will rescan")
              return False

          # Load cache into memory
          self._image_cache = cache_data["cache"]
          self._scan_stats = {
              "platforms_scanned": cache_data["platforms_scanned"],
              "images_found": cache_data["images_found"],
              "scan_duration": cache_data["scan_duration_seconds"],
              "last_scan": created_at
          }

          logger.info(f"✅ Loaded image cache from disk ({age_days} days old, {cache_data['images_found']} images)")
          return True

      except Exception as e:
          logger.error(f"Failed to load cache from disk: {e}")
          return False
  ```

- [ ] **Update `_scan_all_images()` to use cache**
  ```python
  def _scan_all_images(self):
      """Scan all image directories or load from cache."""

      if not is_on_a_drive():
          logger.warning("Not on A: drive - skipping image scan")
          return

      # Try loading from disk cache first
      if self._load_cache_from_disk():
          return  # Cache loaded successfully, skip scan

      # No cache or stale cache - perform full scan
      logger.info("Performing full image directory scan...")

      # ... existing scan logic ...

      # After successful scan, save to disk
      self._save_cache_to_disk()
  ```

- [ ] **Add refresh method for manual cache refresh**
  ```python
  def refresh_cache(self):
      """Force a fresh scan and update disk cache."""
      logger.info("Manual cache refresh requested")
      self._image_cache = {}
      self._title_lists = {}
      self._scan_all_images()
  ```

### Step 2: Update API Endpoints
**File:** `backend/routers/launchbox.py`

- [ ] **Update `/images/refresh` endpoint** (already exists, just ensure it calls new method)
  ```python
  @router.post("/images/refresh")
  async def refresh_image_cache():
      """Force refresh of image scanner cache and save to disk."""
      try:
          image_scanner.refresh_cache()  # This will rescan + save to disk
          stats = image_scanner.get_cache_stats()
          return {
              "success": True,
              "message": "Image cache refreshed and saved to disk",
              "images_found": stats.get("images_found", 0),
              "scan_duration": stats.get("scan_duration", 0),
              "cache_file": str(image_scanner.CACHE_FILE)
          }
      except Exception as e:
          logger.error(f"Failed to refresh image cache: {e}")
          raise HTTPException(status_code=500, detail=str(e))
  ```

- [ ] **Update `/images/stats` endpoint** to show cache source
  ```python
  @router.get("/images/stats")
  async def get_image_scanner_stats():
      """Get image scanner statistics including cache source."""
      stats = image_scanner.get_cache_stats()

      return {
          "platforms_scanned": stats.get("platforms_scanned", 0),
          "total_images": stats.get("images_found", 0),
          "scan_duration_seconds": stats.get("scan_duration", 0),
          "cache_source": "disk" if image_scanner._loaded_from_disk else "memory_scan",
          "cache_file_exists": image_scanner.CACHE_FILE.exists(),
          "cache_age_days": stats.get("cache_age_days", None),
          "fuzzy_threshold": stats.get("fuzzy_threshold", 0.85),
          "is_initialized": stats.get("is_initialized", False),
          "last_scan": stats.get("last_scan").isoformat() if stats.get("last_scan") else None,
          "top_platforms": sorted(
              [(platform, count) for platform, count in stats.get("platforms", {}).items()],
              key=lambda x: x[1],
              reverse=True
          )[:10] if stats.get("platforms") else []
      }
  ```

### Step 3: Add `.gitignore` Entry
**File:** `.gitignore`

- [ ] **Add cache directory to gitignore**
  ```
  # Backend cache (auto-generated)
  backend/cache/
  ```

### Step 4: Testing & Verification

- [ ] **Test 1: First Startup (No Cache)**
  ```bash
  # Delete cache if exists
  rm -f backend/cache/image_cache.json

  # Start backend
  npm run dev:backend

  # Verify logs show:
  # "No disk cache found, will perform full scan"
  # "Performing full image directory scan..."
  # "💾 Image cache saved to disk: backend/cache/image_cache.json"
  # Time: ~30-35s
  ```

- [ ] **Test 2: Second Startup (Cache Exists)**
  ```bash
  # Restart backend (cache file should exist)
  npm run dev:backend

  # Verify logs show:
  # "✅ Loaded image cache from disk (0 days old, 17906 images)"
  # Time: ~2-3s (much faster!)
  ```

- [ ] **Test 3: Stale Cache (>7 days)**
  ```bash
  # Manually edit image_cache.json "created_at" to 8 days ago
  # Restart backend

  # Verify logs show:
  # "Cache is 8 days old (max 7), will rescan"
  # "Performing full image directory scan..."
  ```

- [ ] **Test 4: Manual Refresh**
  ```bash
  # With backend running:
  curl -X POST http://localhost:8888/api/launchbox/images/refresh

  # Verify response:
  # {"success": true, "message": "Image cache refreshed and saved to disk", ...}
  ```

- [ ] **Test 5: Cache Stats Endpoint**
  ```bash
  curl http://localhost:8888/api/launchbox/images/stats

  # Verify response includes:
  # "cache_source": "disk"
  # "cache_file_exists": true
  # "cache_age_days": 0
  ```

- [ ] **Test 6: Other Panels Access Game Data**
  ```bash
  # With backend running (should be fast now, 8-12s):
  # 1. Open Dewey panel
  # 2. Ask: "Tell me about Street Fighter"
  # 3. Verify Dewey can access game data immediately
  ```

---

## Rollback Plan

If disk caching causes issues:

### Quick Rollback (Disable Cache)
```python
# In image_scanner.py _scan_all_images():
# Comment out these lines:
# if self._load_cache_from_disk():
#     return
```

### Full Rollback (Revert Changes)
```bash
# Revert image_scanner.py to previous version
git checkout HEAD~1 backend/services/image_scanner.py

# Delete cache file
rm -f backend/cache/image_cache.json
```

### Fallback Behavior
- System continues to work as before (30-35s startup)
- No breaking changes - cache is purely an optimization

---

## Success Criteria

✅ **Performance:**
- Backend startup: ≤12s (down from 35-40s)
- Cache load time: ≤3s
- First scan still ~30s (one-time cost)

✅ **Reliability:**
- Auto-refresh stale cache (>7 days)
- Graceful fallback if cache load fails
- Manual refresh endpoint works

✅ **Cross-Panel:**
- Dewey can access game data in <15s
- Other panels no longer blocked by LaunchBox initialization

✅ **Observability:**
- Stats endpoint shows cache source
- Logs clearly indicate cache vs. scan
- Cache age visible in stats

---

## Future Enhancements (Post-Implementation)

### v2.0 Improvements
- **Incremental Updates:** Only rescan changed directories
- **Cache Versioning:** Support schema upgrades without full rescan
- **Compression:** GZIP cache file to reduce disk usage
- **Background Refresh:** Periodic auto-refresh in background thread

### Panel Template Pattern
This checkpoint/implementation pattern should be replicated for:
- LED Blinky (hardware state caching)
- Controller Chuck (mapping cache)
- Dewey AI (conversation history)
- Voice Assistant (audio profiles)

---

## Context for Future Sessions

### If Starting Fresh
1. Read this document first
2. Check current state: Does `backend/cache/image_cache.json` exist?
3. Review `backend/services/image_scanner.py` for existing cache logic
4. Follow implementation checklist step-by-step

### If Context Lost Mid-Implementation
- Check which checklist items are complete (look for TODOs in code)
- Run tests to verify current state
- Continue from first unchecked item

### Key Files to Review
- `backend/services/image_scanner.py` (primary changes)
- `backend/routers/launchbox.py` (API endpoint updates)
- `backend/services/launchbox_parser.py` (integration point)

---

## Notes & Decisions

**Why JSON over SQLite?**
- Simple key-value structure doesn't need SQL
- Easier to inspect/debug (human-readable)
- Faster for our use case (single write, many reads)

**Why 7-day max age?**
- Users unlikely to add >1000 new images in a week
- Balances freshness vs. performance
- Can be adjusted via constant if needed

**Why not cache XML parsing?**
- XML parse is only ~5s (not worth complexity)
- Game metadata changes more frequently than images
- Image scan is 30s (6x longer) - bigger ROI

---

**Status:** ✅ Ready to implement
**Estimated Time:** 20-25 minutes implementation + 10 minutes testing
**Risk Level:** Low (pure optimization, no breaking changes)
**Next Step:** Follow Step 1 checklist above
