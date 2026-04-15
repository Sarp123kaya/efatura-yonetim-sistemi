# Project Structure (v2.1.1)

**Last Updated:** 2026-02-10  
**Status:** ✅ CLEANED & ORGANIZED

---

## 📁 Directory Structure

```
gelen-efaturalar-deneme-kopyasi/
│
├── backend/                    # ✅ NEW: Stateful ingestion system
│   ├── agents/                 # Agent implementations
│   │   ├── incoming_agent.py   # Incoming invoice agent
│   │   └── outgoing_agent.py   # Outgoing invoice agent
│   └── core/                   # Core utilities
│       ├── config.py           # Configuration management
│       ├── db.py               # Database helpers
│       ├── agent_state.py      # Watermark/state tracking
│       ├── normalize.py        # Data normalization
│       └── agent_run_logger.py # Run history logging
│
├── ingestion/                  # ✅ NEW: API extractors (moved from src/api/)
│   ├── api_data_extractor.py            # Outgoing invoice extractor
│   └── api_incoming_invoices_extractor.py # Incoming invoice extractor
│
├── sql/                        # Database schemas
│   ├── stateful_ingestion_schema_v2.sql # Current schema (v2.1.1)
│   ├── stateful_ingestion_schema.sql    # Legacy v1.0
│   └── postgres_schema.sql              # Original schema
│
├── scripts/                    # Utilities and tools
│   ├── agent_monitor.py        # CLI monitoring tool
│   ├── setup_postgres.sh       # Database setup script
│   ├── verify_installation.py  # Installation verification
│   └── tools/                  # Additional tools (moved from /tools)
│       ├── invoice_matcher.py
│       └── README_invoice_matcher.md
│
├── docs/                       # ✅ NEW: All documentation
│   ├── V2_PRODUCTION_READY.md          # Main v2.0 documentation
│   ├── ADVANCED_MONITORING.md          # v2.1.1 monitoring guide
│   ├── AGENT_RUN_LOGGING.md            # v2.1.0 logging guide
│   ├── TRANSACTION_PER_BATCH.md        # v2.0.1 transaction guide
│   ├── PRODUCTION_ENHANCEMENTS.md      # v2.0 enhancements
│   ├── STATEFUL_INGESTION_SUMMARY.md   # v1.0 summary
│   ├── IMPLEMENTATION_COMPLETE.md      # v1.0 implementation
│   ├── CHANGELOG_v2.0.1.md             # v2.0.1 changes
│   └── CHANGELOG_v2.1.1.md             # v2.1.1 changes
│
├── archive/                    # ✅ NEW: Legacy code (not deleted, archived)
│   └── legacy_src/             # Old src/ folder contents
│       ├── api_database.py     # Old database module
│       ├── db/                 # Old DB utilities
│       │   └── pg_writer.py
│       └── parsers/            # Old invoice parsers
│           ├── akgips_parser.py
│           └── fullboard_parser.py
│
├── .gitignore                  # Git ignore rules
├── .env                        # Environment variables (not in repo)
├── env.example                 # Example .env file
├── requirements.txt            # Python dependencies
├── README.md                   # Main project README
├── QUICKSTART.md               # Quick start guide
└── PROJECT_STRUCTURE.md        # This file
```

---

## 🎯 Key Changes (Reorganization)

### Before (Old Structure)
```
src/
  ├── api/                      # Mixed with legacy files
  ├── db/                       # Unused in v2.0
  └── parsers/                  # Unused in v2.0

tools/                          # Scattered location

*.md files at root              # Documentation scattered
```

### After (Clean Structure)
```
backend/                        # ✅ Production ingestion system
ingestion/                      # ✅ API extractors only
archive/legacy_src/             # ✅ Old code preserved
scripts/tools/                  # ✅ All tools in one place
docs/                           # ✅ All docs organized
```

---

## 📦 Module Purposes

### `backend/` - Production Ingestion System

**Purpose:** Core stateful ingestion logic  
**Used by:** Cron jobs, production deployments  
**Version:** 2.1.1

**Key Features:**
- Agents: Orchestrate API extraction → DB upsert
- Core: Shared utilities (config, db, state, normalize)
- Run logging: Track execution history in `agent_runs` table

**Import example:**
```python
from backend.core.config import config
from backend.core.db import db
from backend.agents.incoming_agent import IncomingInvoiceAgent
```

---

### `ingestion/` - API Extractors

**Purpose:** Raw invoice data extraction from Isbasi API  
**Used by:** `backend/agents/` only  
**Version:** Stable (unchanged from src/api/)

**Key Features:**
- `api_data_extractor.py`: Outgoing invoices
- `api_incoming_invoices_extractor.py`: Incoming invoices
- Authentication, pagination, date filtering

**Import example:**
```python
from ingestion.api_data_extractor import IsbasiAPIDataExtractor
from ingestion.api_incoming_invoices_extractor import IsbasiAPIIncomingInvoicesExtractor
```

**⚠️ NOTE:** These extractors are **legacy code** and work as-is. New code should only import, not modify.

---

### `sql/` - Database Schemas

**Purpose:** PostgreSQL table definitions  
**Current:** `stateful_ingestion_schema_v2.sql` (v2.1.1)

**Tables:**
- `agent_state` - Watermark tracking
- `incoming_invoices` - Incoming invoice data
- `outgoing_invoices` - Outgoing invoice data
- `agent_runs` - Execution history (v2.1.0+)

**Usage:**
```bash
psql $DB_URL -f sql/stateful_ingestion_schema_v2.sql
```

---

### `scripts/` - Utilities

**Purpose:** Standalone scripts for management and monitoring  
**Executables:**

1. **agent_monitor.py** - CLI tool for monitoring `agent_runs`
   ```bash
   python scripts/agent_monitor.py --command recent --limit 10
   python scripts/agent_monitor.py --command stats --agent incoming_agent
   python scripts/agent_monitor.py --command health --agent outgoing_agent
   ```

2. **setup_postgres.sh** - Database initialization
   ```bash
   bash scripts/setup_postgres.sh
   ```

3. **verify_installation.py** - Installation verification
   ```bash
   python scripts/verify_installation.py
   ```

4. **tools/** - Additional utilities
   - `invoice_matcher.py` - Invoice matching logic

---

### `docs/` - Documentation

**Purpose:** All technical documentation  
**Organization:**

| File | Description |
|------|-------------|
| `V2_PRODUCTION_READY.md` | **Start here** - Main v2.0 overview |
| `ADVANCED_MONITORING.md` | v2.1.1 - host/version/batch tracking |
| `AGENT_RUN_LOGGING.md` | v2.1.0 - agent_runs table |
| `TRANSACTION_PER_BATCH.md` | v2.0.1 - transaction safety |
| `PRODUCTION_ENHANCEMENTS.md` | v2.0 - all enhancements |
| `CHANGELOG_*.md` | Release notes |
| `STATEFUL_INGESTION_SUMMARY.md` | v1.0 summary |
| `IMPLEMENTATION_COMPLETE.md` | v1.0 completion checklist |

**Reading Order:**
1. `/README.md` (project overview)
2. `/QUICKSTART.md` (setup guide)
3. `docs/V2_PRODUCTION_READY.md` (deep dive)
4. `docs/ADVANCED_MONITORING.md` (monitoring guide)

---

### `archive/legacy_src/` - Legacy Code

**Purpose:** Preserve old `src/` folder code  
**Status:** ⚠️ ARCHIVED - Not used in v2.0+

**Contents:**
- `api_database.py` - Old database wrapper (replaced by `backend/core/db.py`)
- `db/pg_writer.py` - Old PostgreSQL writer (replaced by batch upsert)
- `parsers/` - Old invoice parsers (replaced by API extractors)

**⚠️ DO NOT DELETE:** May be needed for:
- Historical reference
- Legacy data migration
- Understanding old logic

**⚠️ DO NOT USE:** v2.0 system is completely separate

---

## 🔄 Import Path Changes

### Agents Updated

**File:** `backend/agents/incoming_agent.py`

**Before:**
```python
from src.api.api_incoming_invoices_extractor import IsbasiAPIIncomingInvoicesExtractor
```

**After:**
```python
from ingestion.api_incoming_invoices_extractor import IsbasiAPIIncomingInvoicesExtractor
```

---

**File:** `backend/agents/outgoing_agent.py`

**Before:**
```python
from src.api.api_data_extractor import IsbasiAPIDataExtractor
```

**After:**
```python
from ingestion.api_data_extractor import IsbasiAPIDataExtractor
```

---

## 🚀 Usage Examples

### Running Agents

```bash
# Incoming invoices
python backend/agents/incoming_agent.py

# Outgoing invoices
python backend/agents/outgoing_agent.py
```

### Monitoring

```bash
# Recent runs
python scripts/agent_monitor.py --command recent --limit 5

# Stats for specific agent
python scripts/agent_monitor.py --command stats --agent incoming_agent --days 30

# Health check
python scripts/agent_monitor.py --command health --agent incoming_agent
```

### Database Setup

```bash
# Initial setup
bash scripts/setup_postgres.sh

# Verify
python scripts/verify_installation.py
```

---

## 📊 File Count Summary

```
backend/            8 files  (agents + core)
ingestion/          3 files  (extractors + __init__)
sql/                3 files  (schemas)
scripts/            4 files  (3 scripts + tools/)
docs/               9 files  (documentation)
archive/            5 files  (legacy code)
root/               4 files  (.env, requirements.txt, README, QUICKSTART)
```

**Total:** ~36 files (organized, clean structure)

---

## ✅ Benefits of New Structure

| Benefit | Description |
|---------|-------------|
| **Clear Separation** | Production (`backend/`) vs Extractors (`ingestion/`) vs Legacy (`archive/`) |
| **Documentation Hub** | All docs in `docs/`, not scattered at root |
| **Import Clarity** | `from backend.*` (new) vs `from ingestion.*` (legacy extractors) |
| **No Deletion** | Legacy code preserved in `archive/` for reference |
| **Scalability** | Easy to add new agents, extractors, docs without clutter |
| **Onboarding** | New developers understand structure instantly |

---

## 🔍 Finding Files

### "Where is X?"

| Looking for... | Location |
|----------------|----------|
| Agent logic | `backend/agents/` |
| DB helpers | `backend/core/db.py` |
| Config | `backend/core/config.py` |
| API extractors | `ingestion/` |
| Schemas | `sql/` |
| Monitoring | `scripts/agent_monitor.py` |
| Documentation | `docs/` |
| Legacy code | `archive/legacy_src/` |

---

## 📝 Maintenance Notes

### Adding New Agent

```bash
# 1. Create agent file
touch backend/agents/new_agent.py

# 2. Import core utilities
from backend.core.config import config
from backend.core.db import db
from backend.core.agent_run_logger import AgentRunLogger

# 3. Import extractor
from ingestion.some_extractor import SomeExtractor
```

### Adding New Extractor

```bash
# 1. Create in ingestion/
touch ingestion/new_extractor.py

# 2. Use in agents
from ingestion.new_extractor import NewExtractor
```

### Adding New Documentation

```bash
# 1. Create in docs/
touch docs/NEW_FEATURE.md

# 2. Link from V2_PRODUCTION_READY.md
echo "7. NEW_FEATURE.md - Description" >> docs/V2_PRODUCTION_READY.md
```

---

## 🚨 Important Rules

1. **DO NOT delete `archive/`** - Historical reference
2. **DO NOT modify `ingestion/` extractors** - Legacy code, use as-is
3. **DO add new docs to `docs/`** - Keep root clean
4. **DO use `backend/` for new logic** - Production code
5. **DO import from `ingestion.*`** - Not `src.api.*`

---

## 🎯 Quick Navigation

```bash
# Production code
cd backend/

# API extractors
cd ingestion/

# Run an agent
python backend/agents/incoming_agent.py

# Monitor runs
python scripts/agent_monitor.py --command recent

# Read docs
open docs/V2_PRODUCTION_READY.md
```

---

**Status:** ✅ CLEAN & ORGANIZED  
**Version:** 2.1.1  
**Date:** 2026-02-10
