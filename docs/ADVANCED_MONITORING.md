# Advanced Monitoring Fields (v2.1.1)

## 🎯 Amaç

Production-grade monitoring için 3 kritik alan eklendi:
1. **host** - Hangi sunucuda çalıştı?
2. **agent_version** - Hangi kod versiyonu?
3. **batch_count** - Kaç batch işlendi?

---

## 📊 Schema Updates

### agent_runs Tablosu (v2.1.1)

```sql
CREATE TABLE agent_runs (
    -- ... existing fields ...
    
    -- NEW: Environment tracking
    host TEXT,                  -- Hostname (socket.gethostname())
    agent_version TEXT,         -- Code version (e.g., "2.1.1")
    batch_count INTEGER,        -- Number of batches processed
    
    -- ... metadata, timestamps ...
);

CREATE INDEX idx_agent_runs_host ON agent_runs(host);
CREATE INDEX idx_agent_runs_version ON agent_runs(agent_version);
```

---

## 🔧 Implementation

### 1. Host Tracking (socket.gethostname())

**Dosya:** `backend/core/agent_run_logger.py`

```python
import socket

class AgentRunLogger:
    def __init__(self, agent_name, run_id):
        self.host = socket.gethostname()  # e.g., "prod-server-01"
    
    def start_run(self, metadata=None):
        query = """
            INSERT INTO agent_runs (agent_name, run_id, host, ...)
            VALUES (%s, %s, %s, ...)
        """
        db.execute(query, (agent_name, run_id, self.host, ...))
```

**Faydası:**
```sql
-- Hangi sunucuda hata var?
SELECT host, COUNT(*) 
FROM agent_runs 
WHERE status = 'failed' 
GROUP BY host;

-- Output:
-- prod-server-01 | 0  ✅
-- prod-server-02 | 5  ❌ Bu sunucuda sorun var!
-- staging-01     | 1
```

**Use Case:**
- Multi-node deployment (load balancer arkasında birden fazla worker)
- Staging vs Production ayırımı
- VPS migration tracking
- Server-specific bug isolation

---

### 2. Version Tracking (agent_version)

**Dosya:** `backend/core/agent_run_logger.py`

```python
# Agent version constant
AGENT_VERSION = "2.1.1"

class AgentRunLogger:
    def __init__(self, agent_name, run_id, version=None):
        self.version = version or AGENT_VERSION
```

**Güncelleme:**
```python
# Yeni versiyon çıktığında
AGENT_VERSION = "2.2.0"  # Update here
```

**Faydası:**
```sql
-- Hangi versiyon hata verdi?
SELECT agent_version, status, COUNT(*) 
FROM agent_runs 
GROUP BY agent_version, status 
ORDER BY agent_version DESC;

-- Output:
-- 2.2.0 | failed  | 10  ❌ Yeni versiyon problematic!
-- 2.1.1 | success | 50  ✅ Eski versiyon stable
-- 2.1.0 | success | 100 ✅
```

**Use Case:**
- Regression detection ("v2.2.0 hatalı, v2.1.1'e dön")
- A/B testing (farklı versiyonları karşılaştır)
- Rollback decision ("hangi versiyona döneyim?")
- Performance comparison across versions

---

### 3. Batch Count Tracking

**Dosya:** `backend/agents/incoming_agent.py`, `outgoing_agent.py`

```python
def upsert_invoice_batch(self, invoices):
    batch_count = 0
    
    if to_insert:
        num_insert_batches = (len(to_insert) + BATCH_SIZE - 1) // BATCH_SIZE
        batch_count += num_insert_batches
        db.execute_batch(...)
    
    if to_update:
        num_update_batches = (len(to_update) + BATCH_SIZE - 1) // BATCH_SIZE
        batch_count += num_update_batches
        db.execute_batch(...)
    
    counts['batch_count'] = batch_count
    return counts
```

**Faydası:**
```sql
-- Performance düşüşü var mı?
SELECT 
    DATE(start_time) as date,
    AVG(batch_count) as avg_batches,
    AVG(duration_sec) as avg_duration,
    AVG(total_fetched::NUMERIC / NULLIF(batch_count, 0)) as avg_rows_per_batch
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND start_time > NOW() - INTERVAL '30 days'
GROUP BY DATE(start_time)
ORDER BY date DESC;

-- Output:
-- 2026-02-10 | 5   | 45.3s | 100  ✅ Normal
-- 2026-02-09 | 5   | 44.1s | 100  ✅ Normal
-- 2026-02-08 | 15  | 78.5s | 100  ❌ Çok fazla batch! (yavaş)
```

**Use Case:**
- Performance anomaly detection
- Batch size optimization
- Data volume trends
- Transaction overhead analysis

---

## 📊 Monitoring Queries

### Multi-Node Deployment

```sql
-- Hangi sunucu en çok çalışıyor?
SELECT 
    host,
    COUNT(*) as runs,
    AVG(duration_sec) as avg_duration
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY host
ORDER BY runs DESC;
```

### Version Comparison

```sql
-- Versiyon bazlı başarı oranı
SELECT 
    agent_version,
    COUNT(*) as total_runs,
    COUNT(*) FILTER (WHERE status = 'success') as successful,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    COUNT(*) FILTER (WHERE status = 'success') * 100.0 / COUNT(*) as success_rate
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '30 days'
GROUP BY agent_version
ORDER BY agent_version DESC;

-- Output:
-- 2.2.0 | 50  | 40  | 10 | 80.0%  ❌ Regression!
-- 2.1.1 | 100 | 98  | 2  | 98.0%  ✅ Stable
-- 2.1.0 | 200 | 195 | 5  | 97.5%  ✅ Stable
```

### Performance Trends

```sql
-- Batch count trends (data volume indicator)
SELECT 
    DATE(start_time) as date,
    agent_name,
    AVG(batch_count) as avg_batches,
    MAX(batch_count) as max_batches,
    AVG(total_fetched) as avg_fetched
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '30 days'
GROUP BY DATE(start_time), agent_name
ORDER BY date DESC;
```

### Cross-Host Comparison

```sql
-- Host performance comparison
SELECT 
    host,
    agent_name,
    AVG(duration_sec) as avg_duration,
    AVG(total_fetched::NUMERIC / NULLIF(duration_sec, 0)) as avg_throughput
FROM agent_runs
WHERE status = 'success'
  AND start_time > NOW() - INTERVAL '7 days'
GROUP BY host, agent_name
ORDER BY host, agent_name;

-- Output:
-- prod-01 | incoming | 45.3s | 10.5 rows/sec  ✅
-- prod-02 | incoming | 68.7s | 6.9 rows/sec   ❌ Yavaş!
-- staging | incoming | 42.1s | 11.2 rows/sec  ✅
```

---

## 📈 CLI Monitoring

### Enhanced Output

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
  └─ Error: 2 rows failed validation
outgoing_agent  2026-02-09 13:30:08  15.2s    2075   10     5      21    staging-01   2.1.1    ⚠️ partial
incoming_agent  2026-02-08 14:30:05  78.5s    450    20     0      15    prod-02      2.1.0    ✅ success
====================================================================
Legend: I=Inserted, U=Updated, E=Errors, B=Batches
```

**Insight:**
- ✅ prod-01 çalışıyor (son run 1 saat önce)
- ⚠️ prod-02'de 2026-02-09'da error var
- ✅ v2.1.1 stable görünüyor
- ⚠️ 2026-02-08'de 15 batch var (normalden fazla → data spike)

---

## 🚨 Alerting Scenarios

### Scenario 1: Version-Specific Bug

```sql
-- v2.2.0 hatalar veriyor mu?
SELECT agent_version, status, COUNT(*) 
FROM agent_runs 
WHERE agent_version = '2.2.0' 
GROUP BY agent_version, status;

-- Output:
-- 2.2.0 | failed | 10  ❌ ALERT! Rollback to v2.1.1
```

**Action:** Rollback to v2.1.1, investigate v2.2.0 bug

### Scenario 2: Server Performance Degradation

```sql
-- prod-02 yavaşladı mı?
SELECT 
    host,
    DATE(start_time) as date,
    AVG(duration_sec) as avg_duration
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND start_time > NOW() - INTERVAL '7 days'
GROUP BY host, DATE(start_time)
ORDER BY host, date DESC;

-- Output:
-- prod-01 | 2026-02-10 | 45s  ✅ Normal
-- prod-02 | 2026-02-10 | 85s  ❌ ALERT! 2x slower
```

**Action:** Check prod-02 resources (CPU, memory, network)

### Scenario 3: Data Volume Spike

```sql
-- Anormal batch count var mı?
SELECT 
    DATE(start_time) as date,
    AVG(batch_count) as avg_batches,
    MAX(batch_count) as max_batches
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND start_time > NOW() - INTERVAL '14 days'
GROUP BY DATE(start_time)
ORDER BY date DESC;

-- Output:
-- 2026-02-10 | 3   | 3   ✅ Normal
-- 2026-02-09 | 3   | 3   ✅ Normal
-- 2026-02-08 | 25  | 25  ❌ ALERT! 8x increase
```

**Action:** Investigate why 2500 invoices on 2026-02-08 (vs normal 300)

---

## 🖥️ Multi-Node Deployment Example

### Scenario: 3 Servers

```
prod-server-01  → incoming_agent (cron 02:00)
prod-server-02  → outgoing_agent (cron 03:00)
staging-01      → both agents (cron 04:00, test data)
```

**Health Check:**
```sql
SELECT host, agent_name, MAX(start_time) as last_run, status
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '2 days'
GROUP BY host, agent_name, status
ORDER BY host, agent_name;
```

**Output:**
```
Host            Agent           Last Run            Status
----------------------------------------------------------------
prod-server-01  incoming_agent  2026-02-10 02:00    success  ✅
prod-server-02  outgoing_agent  2026-02-10 03:00    success  ✅
staging-01      incoming_agent  2026-02-10 04:00    success  ✅
staging-01      outgoing_agent  2026-02-10 04:05    failed   ❌
                                                     ↑ Staging'de sorun var!
```

---

## 📈 Performance Analysis

### Batch Count vs Duration

```sql
-- Batch count ile duration korelasyonu
SELECT 
    batch_count,
    AVG(duration_sec) as avg_duration,
    COUNT(*) as sample_size
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND status = 'success'
  AND batch_count > 0
GROUP BY batch_count
ORDER BY batch_count;

-- Output:
-- 1  | 15.2s | 50   (100 rows)
-- 2  | 28.5s | 40   (200 rows)
-- 3  | 45.3s | 100  (300 rows) ← Normal
-- 10 | 145s  | 5    (1000 rows) ← Spike günleri
```

**Insight:** Linear scaling → Good! (~15s per batch)

### Version Performance Comparison

```sql
-- Versiyon bazlı performans
SELECT 
    agent_version,
    AVG(duration_sec) as avg_duration,
    AVG(total_fetched::NUMERIC / NULLIF(duration_sec, 0)) as avg_throughput,
    COUNT(*) as runs
FROM agent_runs
WHERE status = 'success'
  AND start_time > NOW() - INTERVAL '30 days'
GROUP BY agent_version
ORDER BY agent_version DESC;

-- Output:
-- 2.2.0 | 35.2s | 14.2 rows/sec | 50  ✅ Faster!
-- 2.1.1 | 45.3s | 11.0 rows/sec | 100 
-- 2.1.0 | 48.7s | 10.3 rows/sec | 200
```

**Insight:** v2.2.0 has 30% better throughput!

---

## 🔍 Debugging Scenarios

### Scenario 1: "Hangi sürüm hata verdi?"

```sql
SELECT agent_version, run_id, error_message, start_time
FROM agent_runs
WHERE status = 'failed'
ORDER BY start_time DESC
LIMIT 10;

-- Output:
-- 2.2.0 | incoming_20260210_... | NoneType has no attribute 'get' | ...
```

**Action:** Bug in v2.2.0, rollback to v2.1.1

### Scenario 2: "prod-02 neden yavaş?"

```sql
SELECT 
    host,
    AVG(batch_count) as avg_batches,
    AVG(duration_sec) as avg_duration,
    AVG(duration_sec::NUMERIC / NULLIF(batch_count, 0)) as sec_per_batch
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND status = 'success'
  AND start_time > NOW() - INTERVAL '7 days'
GROUP BY host;

-- Output:
-- prod-01 | 3 | 45s  | 15s/batch ✅
-- prod-02 | 3 | 85s  | 28s/batch ❌ 2x slower per batch!
```

**Action:** prod-02 has resource contention (disk I/O, CPU)

### Scenario 3: "Performans düşüşü mü var?"

```sql
-- 30 günlük trend
SELECT 
    DATE(start_time) as date,
    AVG(batch_count) as avg_batches,
    AVG(total_fetched) as avg_fetched,
    AVG(duration_sec) as avg_duration
FROM agent_runs
WHERE agent_name = 'incoming_agent'
  AND status = 'success'
  AND start_time > NOW() - INTERVAL '30 days'
GROUP BY DATE(start_time)
ORDER BY date DESC;
```

**Chart:**
```
Avg Duration (sec)
60 │                                      ╭─ Spike (78s)
50 │     ╭─────────────────────────────╮  │
40 │─────╯                             ╰──╯
   └────────────────────────────────────────────> Date
       Feb 1      Feb 5      Feb 8     Feb 10
```

**Insight:** 2026-02-08 spike (data volume increase)

---

## 📊 Dashboard Queries (UI için)

### System Overview

```sql
-- Son 24 saat özeti
SELECT 
    agent_name,
    host,
    agent_version,
    COUNT(*) as runs,
    COUNT(*) FILTER (WHERE status = 'success') as successful,
    SUM(insert_count) as total_inserts,
    SUM(batch_count) as total_batches,
    MAX(end_time) as last_run
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '24 hours'
GROUP BY agent_name, host, agent_version
ORDER BY agent_name, host;
```

### Performance Heatmap

```sql
-- Host × Agent performance matrix
SELECT 
    host,
    agent_name,
    AVG(duration_sec) as avg_duration,
    STDDEV(duration_sec) as stddev_duration
FROM agent_runs
WHERE status = 'success'
  AND start_time > NOW() - INTERVAL '7 days'
GROUP BY host, agent_name
ORDER BY host, agent_name;
```

---

## 🎨 CLI Output Example

```bash
$ python scripts/agent_monitor.py --command recent
```

**Output (Enhanced with host, version, batch_count):**
```
📋 Recent Runs (10 total)
================================================================================
Agent           Start                Dur      I      U      E      B     Host         Ver      Status  
--------------------------------------------------------------------------------
incoming_agent  2026-02-10 14:30:22  45.3s    150    6      0      3     prod-01      2.1.1    ✅ success
outgoing_agent  2026-02-10 13:30:15  12.7s    2080   15     0      21    prod-01      2.1.1    ✅ success
incoming_agent  2026-02-09 14:30:11  44.1s    148    8      2      3     prod-02      2.1.0    ⚠️ partial
outgoing_agent  2026-02-09 13:30:08  15.2s    2075   10     5      21    staging-01   2.1.1    ⚠️ partial
incoming_agent  2026-02-08 14:30:05  78.5s    450    20     0      15    prod-02      2.1.0    ✅ success
                                                                    ↑ Spike! (15 batches vs normal 3)
================================================================================
Legend: I=Inserted, U=Updated, E=Errors, B=Batches
```

**Insights from output:**
- prod-01 healthy (v2.1.1, normal batch count)
- prod-02 slower (44-78s vs 45s on prod-01)
- staging-01 has errors (partial status)
- 2026-02-08 data spike (15 batches, 450 inserts)

---

## ✅ Benefits

| Field | Benefit | Example Use Case |
|-------|---------|------------------|
| **host** | Server isolation | "prod-02'de hata var, prod-01'e yönlendir" |
| **agent_version** | Regression detection | "v2.2.0 buggy, v2.1.1'e rollback" |
| **batch_count** | Performance analysis | "15 batch normal mı? Data spike mı?" |

---

## 🔄 Migration

### v2.1.0 → v2.1.1

```sql
-- Auto-migration in schema v2.sql
-- Columns added if not exist:
ALTER TABLE agent_runs ADD COLUMN host TEXT;
ALTER TABLE agent_runs ADD COLUMN agent_version TEXT;
ALTER TABLE agent_runs ADD COLUMN batch_count INTEGER DEFAULT 0;

CREATE INDEX idx_agent_runs_host ON agent_runs(host);
CREATE INDEX idx_agent_runs_version ON agent_runs(agent_version);
```

**No data loss:** Existing runs get NULL for new fields (acceptable)

---

## 🚀 Production Deployment

### Cron with Version Tracking

```bash
# /etc/cron.d/invoice_agents
# Version automatically tracked from code

0 2 * * * app python /path/to/backend/agents/incoming_agent.py
0 3 * * * app python /path/to/backend/agents/outgoing_agent.py
```

**After each deployment:**
```python
# Update version in code
# backend/core/agent_run_logger.py
AGENT_VERSION = "2.2.0"  # ← Update here
```

**Verification:**
```sql
SELECT DISTINCT agent_version 
FROM agent_runs 
WHERE start_time > NOW() - INTERVAL '1 hour';

-- Should show: 2.2.0
```

---

## 📝 Checklist

- [x] ✅ host field added (socket.gethostname())
- [x] ✅ agent_version field added (AGENT_VERSION constant)
- [x] ✅ batch_count field added (computed during upsert)
- [x] ✅ Schema updated with indexes
- [x] ✅ AgentRunLogger updated
- [x] ✅ Both agents updated
- [x] ✅ CLI monitoring updated
- [x] ✅ Documentation complete

---

**Status:** ✅ IMPLEMENTED  
**Version:** 2.1.1  
**Date:** 2026-02-10  
**Type:** Advanced Monitoring Enhancement
