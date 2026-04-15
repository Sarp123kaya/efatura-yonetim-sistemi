# Changelog v2.1.1 - Advanced Monitoring Fields

**Release Date:** 2026-02-10  
**Type:** Enhancement  
**Status:** ✅ COMPLETE

---

## 🎯 Summary

Added 3 critical fields to `agent_runs` table for production-grade monitoring:
1. **host** - Server/hostname tracking
2. **agent_version** - Code version tracking  
3. **batch_count** - Performance analysis

---

## 📊 Changes

### Database Schema

**File:** `sql/stateful_ingestion_schema_v2.sql`

**Added columns:**
```sql
ALTER TABLE agent_runs ADD COLUMN host TEXT;
ALTER TABLE agent_runs ADD COLUMN agent_version TEXT;
ALTER TABLE agent_runs ADD COLUMN batch_count INTEGER DEFAULT 0;

CREATE INDEX idx_agent_runs_host ON agent_runs(host);
CREATE INDEX idx_agent_runs_version ON agent_runs(agent_version);
```

**Comments:**
```sql
COMMENT ON COLUMN agent_runs.host IS 'Hostname where agent ran (for multi-node deployments)';
COMMENT ON COLUMN agent_runs.agent_version IS 'Agent code version (for debugging version-specific issues)';
COMMENT ON COLUMN agent_runs.batch_count IS 'Number of batches processed (for performance analysis)';
```

---

### Backend Core

**File:** `backend/core/agent_run_logger.py`

**Changes:**

1. **Version constant:**
   ```python
   import socket
   
   AGENT_VERSION = "2.1.1"
   ```

2. **AgentRunLogger.__init__:**
   ```python
   def __init__(self, agent_name: str, run_id: str, version: Optional[str] = None):
       self.agent_name = agent_name
       self.run_id = run_id
       self.db_id: Optional[int] = None
       self.host = socket.gethostname()  # NEW
       self.version = version or AGENT_VERSION  # NEW
   ```

3. **start_run():**
   ```python
   query = """
       INSERT INTO agent_runs (
           agent_name, run_id, start_time, status, metadata, 
           host, agent_version  -- NEW
       ) VALUES (%s, %s, NOW(), 'running', %s, %s, %s)
       RETURNING id
   """
   db.execute(query, (agent_name, run_id, metadata_json, self.host, self.version))
   ```

4. **update_progress() / complete_run():**
   - Added `batch_count` parameter
   - Updated INSERT/UPDATE queries

5. **Helper functions:**
   - `get_recent_runs()` - Returns host, agent_version, batch_count
   - `get_run_stats()` - Returns avg_batch_count
   - `check_agent_health()` - Returns host, agent_version

---

### Backend Agents

**Files:** `backend/agents/incoming_agent.py`, `backend/agents/outgoing_agent.py`

**Changes:**

1. **Stats dictionary:**
   ```python
   self.stats = {
       'insert': 0,
       'update': 0,
       'nochange': 0,
       'error': 0,
       'total_fetched': 0,
       'batch_count': 0  # NEW
   }
   ```

2. **upsert_invoice_batch():**
   ```python
   def upsert_invoice_batch(self, invoices):
       counts = {'insert': 0, 'update': 0, 'nochange': 0, 'error': 0, 'batch_count': 0}
       
       batch_count = 0
       
       if to_insert:
           num_insert_batches = (len(to_insert) + BATCH_SIZE - 1) // BATCH_SIZE
           batch_count += num_insert_batches
           logger.info(f"💾 Inserting {len(to_insert)} new invoices ({num_insert_batches} batches)...")
           db.execute_batch(...)
       
       if to_update:
           num_update_batches = (len(to_update) + BATCH_SIZE - 1) // BATCH_SIZE
           batch_count += num_update_batches
           logger.info(f"🔄 Updating {len(to_update)} changed invoices ({num_update_batches} batches)...")
           db.execute_batch(...)
       
       counts['batch_count'] = batch_count
       return counts
   ```

3. **run() method:**
   ```python
   # Update stats
   for key in ['insert', 'update', 'nochange', 'error', 'batch_count']:
       self.stats[key] += batch_counts[key]
   
   # Log completion
   self.run_logger.complete_run(
       insert_count=self.stats['insert'],
       update_count=self.stats['update'],
       nochange_count=self.stats['nochange'],
       error_count=self.stats['error'],
       total_fetched=self.stats['total_fetched'],
       batch_count=self.stats['batch_count'],  # NEW
       status=status
   )
   ```

4. **Log output:**
   ```python
   logger.info(f"📦 Batches: {self.stats['batch_count']}")
   logger.info(f"🖥️  Host: {self.run_logger.host}")
   logger.info(f"🏷️  Version: {self.run_logger.version}")
   ```

---

### Monitoring Script

**File:** `scripts/agent_monitor.py`

**Changes:**

1. **Recent runs output:**
   ```python
   # Enhanced header
   header = f"{'Agent':<15} {'Start':<20} {'Dur':<8} {'I':<6} {'U':<6} {'E':<6} {'B':<5} {'Host':<12} {'Ver':<8} {'Status':<8}"
   
   # Show new fields
   host_short = (run.get('host') or 'N/A')[:12]
   version_short = (run.get('agent_version') or 'N/A')[:8]
   
   print(f"{run['agent_name']:<15} "
         f"{format_timestamp(run['start_time']):<20} "
         f"{format_duration(run['duration_sec']):<8} "
         f"{run['insert_count']:<6} "
         f"{run['update_count']:<6} "
         f"{run['error_count']:<6} "
         f"{run.get('batch_count', 0):<5} "
         f"{host_short:<12} "
         f"{version_short:<8} "
         f"{status_icon} {run['status']:<8}")
   
   # Legend
   print("Legend: I=Inserted, U=Updated, E=Errors, B=Batches")
   ```

2. **Stats output:**
   ```python
   print(f"Avg Batch Count:  {stats.get('avg_batch_count', 0):.1f}")
   ```

---

## 🚀 Use Cases

### 1. Multi-Node Deployment

**Scenario:** 3 servers running agents (prod-01, prod-02, staging)

**Query:**
```sql
SELECT host, COUNT(*), AVG(duration_sec)
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY host;

-- Output:
-- prod-01   | 50  | 45.3s  ✅
-- prod-02   | 50  | 68.7s  ❌ Slow!
-- staging   | 10  | 42.1s  ✅
```

**Action:** Investigate prod-02 performance

---

### 2. Version-Specific Bug Detection

**Scenario:** New version deployed, errors spike

**Query:**
```sql
SELECT agent_version, status, COUNT(*)
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '24 hours'
GROUP BY agent_version, status;

-- Output:
-- 2.2.0 | failed  | 10  ❌ Regression!
-- 2.1.1 | success | 50  ✅ Stable
```

**Action:** Rollback to v2.1.1, debug v2.2.0

---

### 3. Performance Analysis

**Scenario:** Analyzing batch processing efficiency

**Query:**
```sql
SELECT 
    batch_count,
    AVG(duration_sec) as avg_duration,
    COUNT(*) as samples
FROM agent_runs
WHERE agent_name = 'incoming_agent' AND status = 'success'
GROUP BY batch_count
ORDER BY batch_count;

-- Output:
-- 1  | 15.2s | 50   (100 rows)
-- 2  | 28.5s | 40   (200 rows)
-- 3  | 45.3s | 100  (300 rows) ← Normal
-- 10 | 145s  | 5    (1000 rows) ← Spike days
```

**Insight:** Linear scaling (~15s/batch) = Good performance

---

### 4. Data Volume Spike Detection

**Scenario:** Unusual batch count detected

**Query:**
```sql
SELECT 
    DATE(start_time) as date,
    AVG(batch_count) as avg_batches,
    MAX(batch_count) as max_batches
FROM agent_runs
WHERE agent_name = 'incoming_agent'
GROUP BY DATE(start_time)
ORDER BY date DESC;

-- Output:
-- 2026-02-10 | 3   | 3   ✅ Normal
-- 2026-02-09 | 3   | 3   ✅ Normal
-- 2026-02-08 | 25  | 25  ❌ ALERT! 8x increase
```

**Action:** Investigate why 2500 invoices (vs normal 300)

---

## 📈 Benefits

| Field | Use Case | Example |
|-------|----------|---------|
| **host** | Multi-node monitoring | "prod-02'de hata var" |
| **agent_version** | Regression detection | "v2.2.0 buggy, rollback" |
| **batch_count** | Performance analysis | "15 batch = data spike" |

---

## 🔄 Backward Compatibility

**v2.1.0 → v2.1.1 Migration:**

```sql
-- Auto-applied by schema_v2.sql
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS host TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS agent_version TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS batch_count INTEGER DEFAULT 0;
```

**Existing runs:** Will have NULL for new fields (acceptable)

---

## 📝 Example Output

### CLI Monitor (Enhanced)

```bash
$ python scripts/agent_monitor.py --command recent --limit 5
```

**Output:**
```
📋 Recent Runs (5 total)
====================================================================
Agent           Start                Dur      I      U      E      B     Host         Ver      Status  
--------------------------------------------------------------------
incoming_agent  2026-02-10 14:30:22  45.3s    150    6      0      3     prod-01      2.1.1    ✅ success
outgoing_agent  2026-02-10 13:30:15  12.7s    2080   15     0      21    prod-01      2.1.1    ✅ success
incoming_agent  2026-02-09 14:30:11  44.1s    148    8      2      3     prod-02      2.1.0    ⚠️ partial
outgoing_agent  2026-02-09 13:30:08  15.2s    2075   10     5      21    staging-01   2.1.1    ⚠️ partial
incoming_agent  2026-02-08 14:30:05  78.5s    450    20     0      15    prod-02      2.1.0    ✅ success
====================================================================
Legend: I=Inserted, U=Updated, E=Errors, B=Batches
```

**Insights:**
- prod-01: Healthy (v2.1.1, 3 batches)
- prod-02: Slower (78s vs 45s)
- 2026-02-08: Data spike (15 batches, 450 inserts)

---

### Agent Run Log (Enhanced)

```bash
$ python backend/agents/incoming_agent.py
```

**Output:**
```
===================================================================
🚀 Agent Run Summary
===================================================================
⏱️  Duration: 45.3s
📥 Fetched: 156
✅ Inserted: 150
🔄 Updated: 6
⚪ Unchanged: 0
❌ Errors: 0
📦 Batches: 3                 ← NEW
🖥️  Host: prod-server-01     ← NEW
🏷️  Version: 2.1.1           ← NEW
===================================================================
```

---

## 🧪 Testing

### Verify host tracking
```sql
SELECT DISTINCT host FROM agent_runs WHERE start_time > NOW() - INTERVAL '1 hour';
-- Should show your hostname (e.g., "MacBook-Pro.local" or "prod-server-01")
```

### Verify version tracking
```sql
SELECT DISTINCT agent_version FROM agent_runs WHERE start_time > NOW() - INTERVAL '1 hour';
-- Should show: 2.1.1
```

### Verify batch_count tracking
```sql
SELECT agent_name, batch_count, insert_count, update_count 
FROM agent_runs 
WHERE start_time > NOW() - INTERVAL '1 hour';
-- Should show batch_count > 0 if any inserts/updates occurred
```

---

## 📚 Documentation

**New file:**
- `ADVANCED_MONITORING.md` - Comprehensive guide (monitoring queries, use cases, examples)

**Updated files:**
- `V2_PRODUCTION_READY.md` - Added v2.1.1 to changelog

---

## ✅ Acceptance Criteria

- [x] `host` field added and populated (socket.gethostname())
- [x] `agent_version` field added (AGENT_VERSION constant)
- [x] `batch_count` field computed during upsert
- [x] Database indexes created
- [x] CLI monitoring shows new fields
- [x] Both agents track all 3 fields
- [x] Documentation complete (ADVANCED_MONITORING.md)
- [x] Backward compatible (v2.1.0 runs work)
- [x] Syntax validation passed

---

## 🔗 Related Changes

- **v2.1.0** - Added `agent_runs` table
- **v2.0.1** - Transaction-per-batch safety
- **v2.0** - Production enhancements

---

## 🚀 Next Steps (Optional)

1. **Alerting:** Set up alerts for version-specific errors
2. **Dashboard:** Build Grafana/Metabase dashboard using these fields
3. **Auto-rollback:** Trigger rollback if new version has >5% error rate
4. **Performance SLAs:** Define acceptable batch_count ranges

---

**Status:** ✅ COMPLETE  
**Impact:** High - Critical for production debugging and multi-node deployments  
**Risk:** Low - Backward compatible, additive changes only
