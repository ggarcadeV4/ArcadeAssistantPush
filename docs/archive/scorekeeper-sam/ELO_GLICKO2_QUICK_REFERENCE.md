# Elo/Glicko-2 Quick Reference Guide

**Quick lookup for ScoreKeeper Sam rating system integration**

---

## 🎯 API Quick Reference

### Create Tournament with Rating Variant
```python
from backend.services.scorekeeper.service import TournamentService, TournamentData

service = TournamentService(supabase_client, tau=0.5)

tournament = TournamentData(
    name="My Tournament",
    mode="elo_glicko",  # or "elo_standard", "elo_family"
    rating_variant="glicko",  # or "standard", "family_adjusted"
    players=["Alice", "Bob", "Charlie", "David"]
)

async for event in service.generate_bracket_stream(tournament):
    print(event)
```

### Submit Match with Rating Update
```python
result = await service.submit_match_result(
    tournament_id="t123",
    match_id="m1",
    winner="Alice",
    player1="Alice",
    player2="Bob",
    update_ratings=True
)

# Returns:
# {
#     "ratings_updated": True,
#     "rating_changes": {
#         "Alice": {"old_elo": 1600, "new_elo": 1625, "change": +25},
#         "Bob": {"old_elo": 1400, "new_elo": 1375, "change": -25}
#     }
# }
```

### Fetch Player Rating History
```python
history = await service.get_player_rating_evolution("Alice", limit=50)
# Returns list of rating changes with timestamps for charting
```

---

## 📋 Rating Variant Comparison

| Variant | Formula | Best For | Effect |
|---------|---------|----------|--------|
| **standard** | Sort by Elo | Competitive tournaments | Pure skill-based seeding |
| **glicko** | Elo - 2*deviation | New/inactive players | Lower seed for uncertainty |
| **family_adjusted** | Elo + 1000/(games+1) | Family tournaments | Boost for new players |

---

## 🔧 Configuration Cheat Sheet

### Tau Values (Volatility Control)
```python
tau=0.3  # Precise/competitive (slow rating changes)
tau=0.5  # Balanced (default)
tau=0.7  # Volatile (family/casual)
tau=1.0  # Very volatile (kids/beginners)
```

### Default Rating Values
```python
new_player = {
    "elo": 1500,
    "deviation": 350,  # High uncertainty
    "volatility": 0.06,
    "games": 0
}
```

---

## 🧪 Testing Quick Commands

```bash
# Run all rating system tests
cd backend
pytest tests/test_rating_system.py -v --asyncio-mode=auto

# Run specific test class
pytest tests/test_rating_system.py::TestGlicko2Calculator -v

# Run with coverage
pytest tests/test_rating_system.py --cov=services.scorekeeper.service

# Run performance tests only
pytest tests/test_rating_system.py::TestPerformance -v
```

---

## 🗄️ Supabase Quick Setup

### Add Columns to Profiles
```sql
-- Run in Supabase SQL editor
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS elo_score INTEGER DEFAULT 1200,
ADD COLUMN IF NOT EXISTS games_played INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS volatility FLOAT DEFAULT 0.06,
ADD COLUMN IF NOT EXISTS deviation FLOAT DEFAULT 350.0;
```

### Create Rating History Table
```sql
CREATE TABLE IF NOT EXISTS rating_history (
    id SERIAL PRIMARY KEY,
    tournament_id TEXT NOT NULL,
    match_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    old_elo INTEGER NOT NULL,
    new_elo INTEGER NOT NULL,
    old_deviation FLOAT NOT NULL,
    new_deviation FLOAT NOT NULL,
    old_volatility FLOAT NOT NULL,
    new_volatility FLOAT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rating_history_player ON rating_history(player_name, timestamp DESC);
```

---

## 🐛 Common Issues & Fixes

### Issue: Cache Not Working
**Symptom:** Every fetch queries Supabase
**Fix:**
```python
# ❌ Wrong (list not hashable)
await service._fetch_ratings(players, tournament_id)

# ✅ Correct (tuple is hashable)
await service._fetch_ratings(tuple(players), tournament_id)
```

### Issue: Rating Updates Not Persisting
**Symptom:** Ratings show in response but not in database
**Fix:** Check Supabase columns exist:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'profiles'
AND column_name IN ('volatility', 'deviation', 'games_played');
```

### Issue: Tests Import Error
**Symptom:** `ModuleNotFoundError: No module named 'services'`
**Fix:** Run from backend directory:
```bash
cd backend
pytest tests/test_rating_system.py
```

---

## 📊 Performance Optimization Tips

### Enable Caching
```python
# Clear cache if needed
service._fetch_ratings.cache_clear()

# Check cache stats
cache_info = service._fetch_ratings.cache_info()
print(f"Hits: {cache_info.hits}, Misses: {cache_info.misses}")
```

### Batch Rating Updates
```python
# ✅ Good: Batch multiple matches
matches = [
    MatchResult(player_a='P1', player_b='P2', score_a=1.0),
    MatchResult(player_a='P3', player_b='P4', score_a=0.0),
]
updated = await glicko2.update_ratings(matches, ratings)

# ❌ Avoid: Sequential single updates
for match in matches:
    await glicko2.update_ratings([match], ratings)  # Slower
```

---

## 🎨 Frontend Integration Snippets

### Rating Variant Selector (React)
```jsx
<select
    value={ratingVariant}
    onChange={(e) => setRatingVariant(e.target.value)}
>
    <option value="standard">Standard Elo (Competitive)</option>
    <option value="glicko">Glicko-2 Conservative</option>
    <option value="family_adjusted">Family Adjusted</option>
</select>
```

### Display Rating Changes
```jsx
{result.ratings_updated && (
    <div className="rating-changes">
        {Object.entries(result.rating_changes).map(([player, change]) => (
            <div key={player} className={change.change > 0 ? "gain" : "loss"}>
                <span>{player}:</span>
                <span>{change.old_elo} → {change.new_elo}</span>
                <span className="change">
                    {change.change > 0 ? '+' : ''}{change.change}
                </span>
            </div>
        ))}
    </div>
)}
```

### Fetch Rating Evolution (Chart.js)
```javascript
async function fetchRatingHistory(playerName) {
    const response = await fetch(`/api/scorekeeper/rating_evolution/${playerName}`);
    const history = await response.json();

    const chartData = {
        labels: history.map(h => new Date(h.timestamp).toLocaleDateString()),
        datasets: [{
            label: 'Elo Rating',
            data: history.map(h => h.new_elo),
            borderColor: 'rgb(200, 255, 0)',
            tension: 0.1
        }]
    };

    new Chart(ctx, { type: 'line', data: chartData });
}
```

---

## 🔍 Debug Logging

### Enable Verbose Logging
```python
import structlog
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```

### Key Log Events
- `ratings_fetched` - Supabase fetch completed
- `ratings_updated_batch` - Glicko-2 batch update completed
- `ratings_persisted` - Supabase persistence completed
- `rating_history_logged` - History table updated
- `missing_ratings` - Players not found in profiles
- `rating_update_failed` - Non-critical failure (match still completes)

---

## 📈 Expected Performance

| Operation | Latency | Cache Hit |
|-----------|---------|-----------|
| Fetch ratings (first time) | 100-200ms | 0% |
| Fetch ratings (cached) | 0-1ms | 95%+ |
| Glicko-2 single update | 5-10ms | N/A |
| Glicko-2 batch (32 matches) | 300ms | N/A |
| Supabase persist | 50-100ms | N/A |

---

## 🎯 Testing Checklist

### Before Deployment
- [ ] Run full test suite: `pytest tests/test_rating_system.py -v`
- [ ] Verify Supabase columns exist
- [ ] Test with real player profiles
- [ ] Check cache hit rate >80% in logs
- [ ] Verify rating history table populates
- [ ] Test all 3 variants (standard, glicko, family_adjusted)
- [ ] Test edge cases: new players, draws, upsets
- [ ] Performance test with 128-player tournament

### Post-Deployment
- [ ] Monitor rating update latency
- [ ] Check Supabase query volume
- [ ] Verify frontend displays rating changes
- [ ] Test cross-panel integration (Dewey, LED Blinky)
- [ ] Gather user feedback on seeding fairness

---

## 🚀 Deployment Steps

1. **Database Migration:**
   ```sql
   -- Run Supabase migration
   ALTER TABLE profiles ADD COLUMN elo_score INTEGER DEFAULT 1200;
   -- ... (see Supabase Quick Setup above)
   ```

2. **Backend Deployment:**
   ```bash
   # Verify syntax
   python3 -m py_compile backend/services/scorekeeper/service.py

   # Run tests
   pytest backend/tests/test_rating_system.py -v

   # Deploy
   # (restart backend server)
   ```

3. **Frontend Integration:**
   - Update ScoreKeeper panel UI with rating variant selector
   - Add rating change display to match result modal
   - Test end-to-end tournament flow

4. **Monitoring:**
   - Watch structured logs for rating update events
   - Monitor Supabase query volume
   - Check cache hit rates in production

---

## 📞 Support References

- **Full Documentation:** `ELO_GLICKO2_IMPLEMENTATION_SUMMARY.md`
- **Code Location:** `backend/services/scorekeeper/service.py` (lines 124-1315)
- **Test Suite:** `backend/tests/test_rating_system.py`
- **Glicko-2 Spec:** Mark Glickman (2012) - http://www.glicko.net/glicko/glicko2.pdf

---

**Quick Reference Version:** 1.0.0
**Last Updated:** 2025-10-28
**Status:** Production-Ready ✅
