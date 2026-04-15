-- Stateful Ingestion Schema for Isbasi API
-- Creates separate tables for incremental ingestion with row-level change detection

-- Agent state tracking table
CREATE TABLE IF NOT EXISTS agent_state (
    agent_name TEXT PRIMARY KEY,
    last_issue_date TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE agent_state IS 'Tracks last successful extraction date for each agent';
COMMENT ON COLUMN agent_state.last_issue_date IS 'Last issue_date successfully processed';
COMMENT ON COLUMN agent_state.last_run_at IS 'Timestamp of last agent run';

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
    changed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incoming_invoices_issue_date ON incoming_invoices(issue_date);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_supplier ON incoming_invoices(supplier);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_uuid ON incoming_invoices(uuid);
CREATE INDEX IF NOT EXISTS idx_incoming_invoices_changed ON incoming_invoices(changed);

COMMENT ON TABLE incoming_invoices IS 'Incoming invoices from Isbasi API (myInvoicesList)';
COMMENT ON COLUMN incoming_invoices.despatch_ids IS 'Array of normalized despatch IDs (IRS-XXXXX format)';
COMMENT ON COLUMN incoming_invoices.row_hash IS 'SHA256 hash of raw_json for change detection';
COMMENT ON COLUMN incoming_invoices.changed IS 'TRUE if row was updated (hash changed)';

-- Outgoing invoices table (giden faturalar)
CREATE TABLE IF NOT EXISTS outgoing_invoices (
    invoice_no TEXT PRIMARY KEY,
    issue_date TIMESTAMP NOT NULL,
    firm_name TEXT,
    total_tl NUMERIC(18,2),
    taxable_amount NUMERIC(18,2),
    description TEXT,
    irsaliye_codes JSONB DEFAULT '[]'::jsonb,
    raw_json JSONB NOT NULL,
    row_hash TEXT NOT NULL,
    changed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_issue_date ON outgoing_invoices(issue_date);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_firm_name ON outgoing_invoices(firm_name);
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_changed ON outgoing_invoices(changed);

COMMENT ON TABLE outgoing_invoices IS 'Outgoing invoices from Isbasi API (invoices endpoint, excluding PURCHASE_INVOICE)';
COMMENT ON COLUMN outgoing_invoices.irsaliye_codes IS 'Array of normalized irsaliye codes extracted from description (IRS-XXXXX format)';
COMMENT ON COLUMN outgoing_invoices.row_hash IS 'SHA256 hash of raw_json for change detection';
COMMENT ON COLUMN outgoing_invoices.changed IS 'TRUE if row was updated (hash changed)';

-- Initialize agent state with default starting date
INSERT INTO agent_state (agent_name, last_issue_date, last_run_at)
VALUES 
    ('incoming_agent', '2026-01-01 00:00:00', NOW()),
    ('outgoing_agent', '2026-01-01 00:00:00', NOW())
ON CONFLICT (agent_name) DO NOTHING;
