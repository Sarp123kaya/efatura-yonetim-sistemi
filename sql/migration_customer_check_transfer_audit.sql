-- Customer check transfer audit and idempotency table.

CREATE TABLE IF NOT EXISTS customer_check_transfer_audit (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    source_file TEXT,
    source_row INTEGER,
    firm_id TEXT,
    firm_name TEXT,
    tax_id TEXT,
    check_number TEXT,
    due_date DATE,
    amount NUMERIC(18,2),
    currency TEXT,
    status TEXT NOT NULL,
    isbasi_record_id TEXT,
    request_payload JSONB DEFAULT '{}'::jsonb,
    response_payload JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customer_check_transfer_audit_status
    ON customer_check_transfer_audit(status);

CREATE INDEX IF NOT EXISTS idx_customer_check_transfer_audit_tax_check
    ON customer_check_transfer_audit(tax_id, check_number);

CREATE INDEX IF NOT EXISTS idx_customer_check_transfer_audit_due_date
    ON customer_check_transfer_audit(due_date);

COMMENT ON TABLE customer_check_transfer_audit IS
    'Audit and idempotency records for customer check transfer dry-run/import workflow';

COMMENT ON COLUMN customer_check_transfer_audit.idempotency_key IS
    'sha256(tax_id + check_number + due_date + amount + currency), used to prevent duplicate posting';
