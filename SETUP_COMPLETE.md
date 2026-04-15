# ✅ Database Setup Complete

**Setup Date:** 2026-02-19 20:46  
**Status:** Ready for data ingestion

---

## 🎯 Database Status

- **Database Name:** invoices
- **Connection:** postgresql://sp383@localhost:5432/invoices
- **Tables Created:** 4 (agent_state, incoming_invoices, outgoing_invoices, agent_runs)
- **Schema Version:** v2.2 (with despatch_id improvements)
- **Agent State:** Initialized (starting from 2026-01-01)

---

## 🚀 Next Steps: Data Ingestion

### Run These Commands (Requires Your API Password)

```bash
# Method 1: Run both agents sequentially
python3 backend/agents/incoming_agent.py && python3 backend/agents/outgoing_agent.py

# Method 2: Run separately
python3 backend/agents/incoming_agent.py  # Incoming invoices
python3 backend/agents/outgoing_agent.py  # Outgoing invoices
```

**Note:** The agent will prompt for your API password interactively.

---

## 📊 After Data Ingestion: View Results

```bash
# View all data (summary)
python3 view_data.py

# View specific data types
python3 view_data.py --type incoming --limit 20
python3 view_data.py --type outgoing --limit 20
python3 view_data.py --type stats
python3 view_data.py --type runs

# Export to Excel
python3 scripts/export_to_excel.py --type all
```

---

## 🔍 Database Queries

```bash
# Connect to database
psql postgresql://sp383@localhost:5432/invoices

# Check record counts
SELECT COUNT(*) FROM incoming_invoices;
SELECT COUNT(*) FROM outgoing_invoices;

# Check agent state
SELECT * FROM agent_state;

# Check recent agent runs
SELECT agent_name, start_time, status, insert_count, update_count 
FROM agent_runs 
ORDER BY start_time DESC 
LIMIT 5;

# Incoming invoices with despatch codes
SELECT invoice_id, supplier, despatch_ids 
FROM incoming_invoices 
WHERE jsonb_array_length(despatch_ids) > 0 
LIMIT 10;

# Outgoing invoices with despatch codes
SELECT invoice_no, firm_name, despatch_id 
FROM outgoing_invoices 
WHERE despatch_id IS NOT NULL 
LIMIT 10;
```

---

## 📈 What to Expect on First Run

### Incoming Agent (incoming_agent.py)
- **Date Range:** 2026-01-01 to today
- **Expected Count:** ~100-200 invoices (depends on your data)
- **Features:**
  - XML parsing for despatch info
  - Supplier-based normalization (AK → A-XXXX, FULL → F-XXXX)
  - Hash-based change detection
  - Progress updates every 50 invoices

### Outgoing Agent (outgoing_agent.py)
- **Date Range:** 2026-01-01 to today
- **Expected Count:** ~2000-3000 invoices (depends on your data)
- **Features:**
  - IBAN removal from description
  - Despatch code extraction (A-XXXX, F-XXXX)
  - Hash-based change detection
  - Progress updates every 50 invoices

### Performance
- **Incoming:** ~150 invoices/minute (XML fetching is slower)
- **Outgoing:** ~500 invoices/minute
- **First Run:** 5-10 minutes (depends on total invoice count)
- **Subsequent Runs:** Seconds (only new/changed invoices)

---

## 🔄 Incremental Updates (After First Run)

After the first successful run, agents become "stateful":

```bash
# Run again - only fetches new invoices since last run
python3 backend/agents/incoming_agent.py
python3 backend/agents/outgoing_agent.py
```

**How it works:**
1. Agent reads `last_issue_date` from `agent_state` table
2. Fetches only invoices after that date (minus lookback_days)
3. Updates existing records if hash changed
4. Updates `agent_state` with new `last_issue_date`

---

## ⏰ Schedule Automatic Runs (Optional)

```bash
# Edit crontab
crontab -e

# Add these lines for daily runs at 2 AM:
0 2 * * * cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası" && .venv/bin/python backend/agents/incoming_agent.py >> /tmp/incoming_agent.log 2>&1
0 3 * * * cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası" && .venv/bin/python backend/agents/outgoing_agent.py >> /tmp/outgoing_agent.log 2>&1
```

**Note:** For cron jobs, you need to set `ISBASI_PASSWORD` in `.env` file to avoid interactive prompts.

---

## 🛠️ Troubleshooting

### "API login failed"
- Check `.env` file has correct `ISBASI_API_KEY` and `ISBASI_USERNAME`
- Enter password correctly when prompted

### "Database connection failed"
- Database is running: `pg_isready`
- Connection string correct: `postgresql://sp383@localhost:5432/invoices`

### "No invoices returned"
- Check date range (agents start from 2026-01-01)
- Check API has data in that range

### Reset Agent State (Re-fetch All Data)
```sql
-- Reset to start date
UPDATE agent_state SET last_issue_date = '2026-01-01 00:00:00' 
WHERE agent_name IN ('incoming_agent', 'outgoing_agent');

-- Then run agents again
```

---

## 📦 System Components

### Created Tables
| Table | Purpose | Records Expected |
|-------|---------|------------------|
| `agent_state` | Agent watermarks | 2 (one per agent) |
| `incoming_invoices` | Received invoices | 100-200 |
| `outgoing_invoices` | Sent invoices | 2000-3000 |
| `agent_runs` | Execution history | Grows with each run |

### Key Features
- ✅ Stateful ingestion (incremental updates)
- ✅ Change detection (hash-based)
- ✅ Despatch normalization (A-XXXX, F-XXXX)
- ✅ IBAN cleaning
- ✅ Agent run logging
- ✅ Lookback support (catch late arrivals)

---

## 🎉 Ready to Go!

Your database is fully set up and ready. Next step:

```bash
python3 backend/agents/incoming_agent.py
```

Enter your API password when prompted, and watch the data flow in! 🚀

---

**Setup By:** Database automation  
**Ready For:** Data ingestion  
**Docs:** See README.md, QUICKSTART.md, PROJECT_STRUCTURE.md
