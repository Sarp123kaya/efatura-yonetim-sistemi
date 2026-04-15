-- Stateful Ingestion Schema v2.0 (Production-Ready)
-- Improvements:
--   - lookback_days for watermarking
--   - change_type instead of boolean changed
--   - Technical PK for outgoing_invoices

-- Agent state tracking with lookback support
CREATE TABLE IF NOT EXISTS agent_state (
    agent_name TEXT PRIMARY KEY,
    last_issue_date TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
    lookback_days INTEGER DEFAULT 2,
    metadata JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE agent_state IS 'Tracks last successful extraction date for each agent with lookback support';
COMMENT ON COLUMN agent_state.lookback_days IS 'Number of days to look back from last_issue_date to catch late-arriving invoices';

-- Incoming invoices table (gelen faturalar)
CREATE TABLE IF NOT EXISTS incoming_invoices (
    invoice_id TEXT PRIMARY KEY,
    uuid TEXT UNIQUE NOT NULL,
    issue_date TIMESTAMP NOT NULL,
    supplier TEXT,
    supplier_tckn_vkn TEXT,
    amount NUMERIC(18,2),
    total_vat_base NUMERIC(18,2),
    currency TEXT DEFAULT 'TRY',
    despatch_ids JSONB DEFAULT '[]'::jsonb,
    raw_json JSONB NOT NULL,
    row_hash TEXT NOT NULL,
    change_type TEXT DEFAULT 'insert' CHECK (change_type IN ('insert', 'update', 'nochange')),
    last_change_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incoming_invoices_issue_date ON incoming_invoices(issue_date);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_supplier ON incoming_invoices(supplier);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_uuid ON incoming_invoices(uuid);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_change_type ON incoming_invoices(change_type);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_last_change_at ON incoming_invoices(last_change_at);

COMMENT ON TABLE incoming_invoices IS 'Incoming invoices from Isbasi API (myInvoicesList)';
COMMENT ON COLUMN incoming_invoices.change_type IS 'insert: newly inserted, update: hash changed, nochange: hash unchanged';

-- Outgoing invoices table (giden faturalar) - with technical PK
CREATE TABLE IF NOT EXISTS outgoing_invoices (
    id TEXT PRIMARY KEY,  -- Technical PK: invoiceId or id from API
    invoice_no TEXT NOT NULL,
    issue_date TIMESTAMP NOT NULL,
    firm_name TEXT,
    total_tl NUMERIC(18,2),
    taxable_amount NUMERIC(18,2),
    description TEXT,
    irsaliye_codes JSONB DEFAULT '[]'::jsonb,
    raw_json JSONB NOT NULL,
    row_hash TEXT NOT NULL,
    change_type TEXT DEFAULT 'insert' CHECK (change_type IN ('insert', 'update', 'nochange')),
    last_change_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_outgoing_invoices_invoice_no ON outgoing_invoices(invoice_no);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_issue_date ON outgoing_invoices(issue_date);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_firm_name ON outgoing_invoices(firm_name);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_change_type ON outgoing_invoices(change_type);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_last_change_at ON outgoing_invoices(last_change_at);

COMMENT ON TABLE outgoing_invoices IS 'Outgoing invoices from Isbasi API (invoices endpoint, excluding PURCHASE_INVOICE)';
COMMENT ON COLUMN outgoing_invoices.id IS 'Technical PK from API (invoiceId or id field)';
COMMENT ON COLUMN outgoing_invoices.invoice_no IS 'Business invoice number (may not be unique in API)';

-- Migration from v1: Add new columns if upgrading
DO $$ 
BEGIN
    -- Add lookback_days to agent_state if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='agent_state' AND column_name='lookback_days') THEN
        ALTER TABLE agent_state ADD COLUMN lookback_days INTEGER DEFAULT 2;
    END IF;
    
    -- Migrate incoming_invoices: changed -> change_type
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name='incoming_invoices' AND column_name='changed') THEN
        ALTER TABLE incoming_invoices ADD COLUMN change_type TEXT DEFAULT 'insert';
        UPDATE incoming_invoices SET change_type = CASE WHEN changed THEN 'update' ELSE 'insert' END;
        ALTER TABLE incoming_invoices DROP COLUMN changed;
    END IF;
    
    -- Add last_change_at if not exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='incoming_invoices' AND column_name='last_change_at') THEN
        ALTER TABLE incoming_invoices ADD COLUMN last_change_at TIMESTAMP;
    END IF;
    
    -- Migrate outgoing_invoices: changed -> change_type
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name='outgoing_invoices' AND column_name='changed') THEN
        ALTER TABLE outgoing_invoices ADD COLUMN change_type TEXT DEFAULT 'insert';
        UPDATE outgoing_invoices SET change_type = CASE WHEN changed THEN 'update' ELSE 'insert' END;
        ALTER TABLE outgoing_invoices DROP COLUMN changed;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='outgoing_invoices' AND column_name='last_change_at') THEN
        ALTER TABLE outgoing_invoices ADD COLUMN last_change_at TIMESTAMP;
    END IF;
    
    -- Outgoing PK migration: invoice_no -> id
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name='outgoing_invoices' AND column_name='invoice_no' 
               AND is_nullable='NO') THEN
        -- Old schema had invoice_no as PK, need to migrate
        RAISE NOTICE 'Outgoing invoices PK migration needed - manual intervention required';
        -- Manual migration:
        -- 1. Add id column: ALTER TABLE outgoing_invoices ADD COLUMN id TEXT;
        -- 2. Populate from raw_json: UPDATE outgoing_invoices SET id = raw_json->>'id';
        -- 3. Drop old PK: ALTER TABLE outgoing_invoices DROP CONSTRAINT outgoing_invoices_pkey;
        -- 4. Add new PK: ALTER TABLE outgoing_invoices ADD PRIMARY KEY (id);
        -- 5. Make invoice_no nullable: ALTER TABLE outgoing_invoices ALTER COLUMN invoice_no DROP NOT NULL;
    END IF;
END $$;

-- Agent run history tracking (NEW in v2.1)
CREATE TABLE IF NOT EXISTS agent_runs (
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
    batch_count INTEGER DEFAULT 0,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed', 'partial')),
    error_message TEXT,
    
    -- Environment (v2.1.1)
    host TEXT,
    agent_version TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_start_time ON agent_runs(start_time);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_run_id ON agent_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_host ON agent_runs(host);
CREATE INDEX IF NOT EXISTS idx_agent_runs_version ON agent_runs(agent_version);

COMMENT ON TABLE agent_runs IS 'Agent execution history for monitoring and debugging';
COMMENT ON COLUMN agent_runs.status IS 'running: in progress, success: all ok, failed: crashed, partial: some errors';
COMMENT ON COLUMN agent_runs.duration_sec IS 'Computed from end_time - start_time';
COMMENT ON COLUMN agent_runs.host IS 'Hostname where agent ran (for multi-node deployments)';
COMMENT ON COLUMN agent_runs.agent_version IS 'Agent code version (for debugging version-specific issues)';
COMMENT ON COLUMN agent_runs.batch_count IS 'Number of batches processed (for performance analysis)';

-- Initialize agent state with default starting date
INSERT INTO agent_state (agent_name, last_issue_date, last_run_at, lookback_days)
VALUES 
    ('incoming_agent', '2026-01-01 00:00:00', NOW(), 2),
    ('outgoing_agent', '2026-01-01 00:00:00', NOW(), 2)
ON CONFLICT (agent_name) DO NOTHING;
