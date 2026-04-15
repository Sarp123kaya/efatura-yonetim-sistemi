# Agent Run Logging & Monitoring

## 🎯 Amaç

Agent execution history'sini database'de track etmek için `agent_runs` tablosu.

**Faydaları:**
- ✅ "Dün agent çalıştı mı?" → Tek sorgu
- ✅ "Kaç kayıt girdi?" → Stats hazır
- ✅ "Nerede hata verdi?" → Error messages
- ✅ İleride UI'da "Sistem Durumu" ekranı

---

## 📊 Database Schema

### agent_runs Tablosu

```sql
CREATE TABLE agent_runs (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_sec NUMERIC(10,2),
    
    -- Counts
    insert_count INTEGER DEFAULT 0,
    update_count INTEGER DEFAULT 0,
    nochange_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    total_fetched INTEGER DEFAULT 0,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'running' 
        CHECK (status IN ('running', 'success', 'failed', 'partial')),
    error_message TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Status Values:**
- `running`: Agent çalışıyor
- `success`: Başarılı (error_count=0)
- `partial`: Kısmen başarılı (error_count>0)
- `failed`: Crash oldu

---

## 🔧 Implementation

### backend/core/agent_run_logger.py

**AgentRunLogger Class:**
```python
logger = AgentRunLogger('incoming_agent', run_id)

# Run başlangıcı
logger.start_run(metadata={'start_date': '2026-01-01'})

# Progress update (opsiyonel)
logger.update_progress(
    insert_count=50, 
    update_count=5, 
    error_count=0
)

# Run bitişi
logger.complete_run(
    insert_count=150,
    update_count=10,
    error_count=2,
    status='partial',  # or 'success', 'failed'
    error_message="2 rows failed validation"
)
```

**Helper Functions:**
```python
# Son 10 run
runs = get_recent_runs('incoming_agent', limit=10)

# 7 günlük stats
stats = get_run_stats('incoming_agent', days=7)

# Health check
health = check_agent_health('incoming_agent')
```

---

## 🚀 Agent Entegrasyonu

### incoming_agent.py & outgoing_agent.py

```python
class IncomingInvoiceAgent:
    def __init__(self, run_id=None):
        self.run_id = run_id or f"incoming_{timestamp}_{uuid}"
        self.run_logger = AgentRunLogger('incoming_agent', self.run_id)
    
    def run(self):
        # Start logging
        self.run_logger.start_run(metadata={'start_date': start_date})
        
        try:
            # ... agent logic ...
            
            # Success
            status = 'success' if self.stats['error'] == 0 else 'partial'
            self.run_logger.complete_run(
                insert_count=self.stats['insert'],
                update_count=self.stats['update'],
                nochange_count=self.stats['nochange'],
                error_count=self.stats['error'],
                total_fetched=self.stats['total_fetched'],
                status=status
            )
            
        except Exception as e:
            # Failed
            self.run_logger.complete_run(
                insert_count=self.stats['insert'],
                error_count=self.stats['error'],
                status='failed',
                error_message=str(e)
            )
            raise
```

---

## 📊 Monitoring Script

### scripts/agent_monitor.py

**Recent Runs:**
```bash
# Son 10 run (all agents)
python scripts/agent_monitor.py --command recent

# Son 20 run (incoming only)
python scripts/agent_monitor.py --command recent --agent incoming --limit 20
```

**Örnek Çıktı:**
```
📋 Recent Runs (10 total)
========================================================================================
Agent           Run ID                              Start                Duration   I      U      E      Status  
----------------------------------------------------------------------------------------
incoming_agent  incoming_20260210_143022_a1b2c3d4   2026-02-10 14:30:22  45.3s      150    6      0      ✅ success
outgoing_agent  outgoing_20260210_133015_e5f6g7h8   2026-02-10 13:30:15  12.7s      2080   15     0      ✅ success
incoming_agent  incoming_20260209_143011_i9j0k1l2   2026-02-09 14:30:11  44.1s      148    8      2      ⚠️ partial
  └─ Error: 2 rows failed validation
```

**Stats:**
```bash
# 7 günlük stats
python scripts/agent_monitor.py --command stats --agent incoming --days 7
```

**Örnek Çıktı:**
```
📊 Stats for incoming_agent (Last 7 days)
============================================================
Total Runs:       14
  ✅ Successful:  12
  ❌ Failed:      1
  ⚠️  Partial:    1

Total Inserts:    2,100
Total Updates:    140
Total Errors:     8

Avg Duration:     43.2s
Last Run:         2026-02-10 14:30:22
============================================================
```

**Health Check:**
```bash
# Health status
python scripts/agent_monitor.py --command health
```

**Örnek Çıktı:**
```
🏥 Agent Health Status
================================================================================

✅ INCOMING_AGENT
   Status: ok
   Message: incoming_agent is healthy
   Last Run: 2026-02-10 14:30:22
   Result: success (I:150, U:6, E:0)

✅ OUTGOING_AGENT
   Status: ok
   Message: outgoing_agent is healthy
   Last Run: 2026-02-10 13:30:15
   Result: success (I:2080, U:15, E:0)
================================================================================
```

**Unhealthy States:**
```
❌ INCOMING_AGENT
   Status: stale
   Message: incoming_agent has not run in 2 days
   
❌ OUTGOING_AGENT
   Status: failed
   Message: outgoing_agent last run failed: Database connection timeout
   
❌ INCOMING_AGENT
   Status: stuck
   Message: incoming_agent appears stuck (started 2026-02-10 08:00:00)
```

---

## 🔍 SQL Queries

### Manual Queries

**Recent runs:**
```sql
SELECT agent_name, run_id, start_time, end_time, 
       insert_count, update_count, error_count, status
FROM agent_runs
ORDER BY start_time DESC
LIMIT 10;
```

**Today's runs:**
```sql
SELECT agent_name, status, COUNT(*)
FROM agent_runs
WHERE start_time::DATE = CURRENT_DATE
GROUP BY agent_name, status;
```

**Failed runs (last 7 days):**
```sql
SELECT agent_name, run_id, start_time, error_message
FROM agent_runs
WHERE status = 'failed'
  AND start_time > NOW() - INTERVAL '7 days'
ORDER BY start_time DESC;
```

**Performance trends:**
```sql
SELECT 
    DATE(start_time) as date,
    agent_name,
    COUNT(*) as runs,
    AVG(duration_sec) as avg_duration,
    SUM(insert_count) as total_inserts,
    SUM(error_count) as total_errors
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '30 days'
GROUP BY DATE(start_time), agent_name
ORDER BY date DESC, agent_name;
```

**Agent availability (uptime):**
```sql
SELECT 
    agent_name,
    COUNT(*) FILTER (WHERE status = 'success') * 100.0 / COUNT(*) as success_rate,
    COUNT(*) as total_runs
FROM agent_runs
WHERE start_time > NOW() - INTERVAL '7 days'
GROUP BY agent_name;
```

---

## 📈 Future: UI Dashboard

Bu tablo ileride web UI'da kullanılabilir:

### Dashboard Örneği:

```
╔════════════════════════════════════════════════════════════╗
║              AGENT MONITORING DASHBOARD                     ║
╠════════════════════════════════════════════════════════════╣
║                                                             ║
║  📊 System Status                                          ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ║
║                                                             ║
║  ✅ Incoming Agent       Last run: 2 hours ago             ║
║     Status: Healthy      Success rate: 98.5%               ║
║                                                             ║
║  ✅ Outgoing Agent       Last run: 1 hour ago              ║
║     Status: Healthy      Success rate: 100%                ║
║                                                             ║
║  📈 Last 24 Hours                                          ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ║
║                                                             ║
║  Runs:        4                                             ║
║  Inserts:     620                                           ║
║  Updates:     34                                            ║
║  Errors:      0                                             ║
║                                                             ║
║  📋 Recent Runs                                            ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ║
║                                                             ║
║  [Table with last 10 runs...]                              ║
║                                                             ║
╚════════════════════════════════════════════════════════════╝
```

**Endpoint'ler:**
```
GET /api/agents/status        → Health check
GET /api/agents/runs          → Recent runs
GET /api/agents/stats?days=7  → Stats
GET /api/agents/{name}/runs   → Agent-specific runs
```

---

## 🧪 Testing

### Syntax Check
```bash
python3 -m py_compile backend/core/agent_run_logger.py
python3 -m py_compile scripts/agent_monitor.py
```

### Manual Test
```bash
# Run agent (will log to database)
python backend/agents/incoming_agent.py

# Check logs
python scripts/agent_monitor.py --command recent --limit 5

# Check stats
python scripts/agent_monitor.py --command stats --agent incoming

# Health check
python scripts/agent_monitor.py --command health
```

---

## 🔄 Migration

### Schema Update

```bash
# Apply v2.1 schema (includes agent_runs table)
psql invoices < sql/stateful_ingestion_schema_v2.sql
```

**Backward compatible:** Eski agent'lar çalışmaya devam eder (logging olmadan).

---

## 🎯 Use Cases

### 1. Daily Health Check (Cron)

```bash
#!/bin/bash
# /etc/cron.daily/agent-health-check

python /path/to/scripts/agent_monitor.py --command health > /tmp/agent_health.txt

# Email if unhealthy
if grep -q "❌" /tmp/agent_health.txt; then
    mail -s "Agent Health Alert" admin@example.com < /tmp/agent_health.txt
fi
```

### 2. Debugging Failed Runs

```sql
-- Find failed run
SELECT run_id, error_message 
FROM agent_runs 
WHERE status = 'failed' 
ORDER BY start_time DESC 
LIMIT 1;

-- Check what was processed before crash
SELECT insert_count, update_count, total_fetched
FROM agent_runs
WHERE run_id = 'incoming_20260210_143022_a1b2c3d4';
```

### 3. Performance Analysis

```sql
-- Slow runs
SELECT run_id, duration_sec, total_fetched
FROM agent_runs
WHERE duration_sec > 60
  AND status = 'success'
ORDER BY duration_sec DESC;

-- Throughput
SELECT 
    total_fetched / NULLIF(duration_sec, 0) as rows_per_sec
FROM agent_runs
WHERE duration_sec > 0
ORDER BY start_time DESC
LIMIT 10;
```

---

## ✅ Benefits

| Before (v2.0) | After (v2.1) |
|---------------|--------------|
| Logs only in files | ✅ Logs in database |
| Hard to query | ✅ Easy SQL queries |
| No history tracking | ✅ Full history |
| Manual monitoring | ✅ Automated health checks |
| No UI-ready data | ✅ API-ready |

---

## 📚 Files

**New:**
- `backend/core/agent_run_logger.py` - Logger module
- `scripts/agent_monitor.py` - Monitoring CLI
- `AGENT_RUN_LOGGING.md` - This doc

**Updated:**
- `sql/stateful_ingestion_schema_v2.sql` - Added agent_runs table
- `backend/agents/incoming_agent.py` - Integrated logging
- `backend/agents/outgoing_agent.py` - Integrated logging

---

**Status:** ✅ IMPLEMENTED  
**Version:** 2.1.0  
**Date:** 2026-02-10  
**Type:** Monitoring Enhancement
