# Roadmap: LaunchBox Performance and Stability Refactor

**Date:** 2026-01-21

## 1. Objective

This document outlines a phased plan to resolve two critical issues degrading the Arcade Assistant's performance and stability:

1.  **Frontend Performance:** The `LaunchBoxPanel.jsx` UI is slow and unresponsive due to loading the entire 14,000+ game library into the browser's memory at once.
2.  **Backend Data Staleness:** The game data becomes outdated the moment a change is made in LaunchBox, as the backend only parses the source XML files on its initial startup.

This refactor will result in a fast, responsive UI that reflects data changes in near real-time.

---

## 2. Problem Analysis

Our investigation confirmed two independent sources of "friction":

### Frontend Bottleneck
- **File:** `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
- **Issue:** The component fetches all games via `/api/launchbox/games` and stores them in a client-side array. All filtering, sorting, and pagination operations are then performed on this massive array within the browser, causing significant UI lag.

### Backend Data Inconsistency
- **File:** `backend/services/launchbox_parser.py`
- **Issue:** This service builds the game cache, but it only runs once when the main application starts. It has no mechanism to detect when games are added, removed, or modified in LaunchBox post-startup, leading to a stale and inconsistent user experience.

---

## 3. Recommended Plan of Action

This plan is broken into three sequential phases. Each phase is a logical unit that can be implemented and tested independently.

### Phase 1: Implement Backend-Driven API
This is the most critical phase. We will change the backend to handle the heavy lifting of sorting and filtering, sending only a small, digestible chunk of data to the frontend.

- **File to Modify:** `backend/routers/launchbox.py`
- **Action:** Modify the `GET /api/launchbox/games` endpoint to accept pagination, filtering, and sorting parameters.

- **Current Endpoint Signature (Conceptual):**
  ```python
  @router.get("/games")
  def get_games():
      # Returns all 14,000+ games
      return launchbox_parser.get_all_games()
  ```

- **Proposed Endpoint Signature:**
  ```python
  from typing import Optional
  from fastapi import Query

  @router.get("/games")
  def get_games(
      page: int = 1,
      limit: int = 50,
      platform: Optional[str] = None,
      genre: Optional[str] = None,
      search: Optional[str] = None,
      sort_by: str = 'Title',
      sort_order: str = 'asc'
  ):
      # New logic will be added here to filter the master game list
      # based on the query parameters before slicing for pagination.
      # It will return only `limit` number of games.
      return launchbox_parser.get_paginated_games(...)
  ```

- **Artwork Handling:** The logic for transforming image file paths into web-accessible URLs (e.g., `http://host/images/...`) must be preserved and applied to the paginated results before they are returned.

### Phase 2: Refactor Frontend to Use the New API
With the powerful new backend API in place, we will refactor the `LaunchBoxPanel` to be a lightweight client.

- **File to Modify:** `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`
- **Action:** Remove the large client-side game state and all associated filtering/sorting logic. State will now be used to track query parameters (`page`, `filter`, etc.) instead of the game list itself.

- **Current Logic (Conceptual):**
  ```jsx
  const [allGames, setAllGames] = useState([]);
  const [filteredGames, setFilteredGames] = useState([]);

  useEffect(() => {
    // 1. Fetch ALL games
    api.get("/games").then(response => setAllGames(response.data));
  }, []);

  useEffect(() => {
    // 2. Filter locally
    const result = allGames.filter(game => game.platform === 'Arcade');
    setFilteredGames(result);
  }, [allGames]);
  ```

- **Proposed Logic (Conceptual):**
  ```jsx
  const [games, setGames] = useState([]); // Will only hold one page of data
  const [page, setPage] = useState(1);
  const [platformFilter, setPlatformFilter] = useState('Arcade');
  const [totalGames, setTotalGames] = useState(0);

  useEffect(() => {
    // Fetch only the data needed for the current view
    const params = { page, platform: platformFilter };
    api.get("/games", { params }).then(response => {
      setGames(response.data.games); // The API will now return an object with game data and total count
      setTotalGames(response.data.total);
    });
  }, [page, platformFilter]); // Re-fetch when page or filter changes
  ```

### Phase 3: Implement Real-Time Backend Data Sync
To solve data staleness, we will create a background service that watches for changes in the LaunchBox data directory.

- **File to Create:** `backend/services/launchbox_watcher.py`
- **Action:** Create a new service that uses a file system watching library (e.g., `watchdog`).
- **Implementation Details:**
  1. The service will monitor `A:\LaunchBox\Data` for any changes to `.xml` files.
  2. Upon detecting a change, it will call a method in `launchbox_parser.py` (e.g., `revalidate_cache()`).
  3. This ensures the master game list used by the API in Phase 1 is always up-to-date.
  4. This service will be started as a background task when the main application boots up.

---

## 4. Alternative Approaches

While the plan above is strongly recommended, other options exist.

- **Alternative A: The Sidecar Database**
  - **Description:** Instead of parsing XML into an in-memory list, the file watcher from Phase 3 could populate a dedicated SQLite database. The API from Phase 1 would then query this database.
  - **Pros:** Extremely fast and powerful for complex queries. Creates a robust, persistent data source.
  - **Cons:** Higher implementation complexity than the recommended approach. Adds another moving part (the database file) to the system.

- **Alternative B: Enhanced Manual Refresh**
  - **Description:** Forgo the file watcher (Phase 3). Keep the existing `POST /api/launchbox/cache/revalidate` endpoint but make the "Refresh" button in the UI much more prominent.
  - **Pros:** Very simple to implement. Requires no new background processes.
  - **Cons:** Does not solve the core data staleness issue; it merely makes the manual workaround easier for the user. Provides a poor user experience compared to an automated solution.
