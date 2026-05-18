-- Consolidated check pool adapted from cek-takip.

CREATE TABLE IF NOT EXISTS checks (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NULL,
    account_code VARCHAR(64) NULL,
    account_name VARCHAR(255) NULL,
    company_name VARCHAR(255) NULL,
    movement_type VARCHAR(64) NOT NULL,
    check_no VARCHAR(64) NOT NULL,
    bank_name VARCHAR(128) NOT NULL,
    sent_to VARCHAR(255) NULL,
    amount NUMERIC(18, 2) NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'TRY',
    maturity_date DATE NOT NULL,
    transaction_date DATE NULL,
    document_date DATE NULL,
    voucher_no VARCHAR(64) NULL,
    document_no VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PORTFOLIO',
    source_file VARCHAR(255) NULL,
    source_page INTEGER NULL,
    raw_description TEXT NULL,
    raw_line TEXT NULL,
    parse_warning TEXT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'EXCEL',
    import_session_id UUID NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
    source_row_index INTEGER NULL,
    source_sheet VARCHAR(128) NULL,
    source_image_region VARCHAR(128) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT checks_status_allowed CHECK (
        status IN ('PORTFOLIO', 'ENDORSED', 'BANK', 'CASHED', 'RETURNED', 'CANCELLED')
    ),
    CONSTRAINT checks_review_status_allowed CHECK (
        review_status IN ('DRAFT', 'NEEDS_REVIEW', 'APPROVED', 'IMPORTED', 'REJECTED')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_checks_statement_duplicate
ON checks (
    COALESCE(account_name, ''),
    check_no,
    bank_name,
    maturity_date,
    COALESCE(amount, 0)
);

CREATE INDEX IF NOT EXISTS idx_checks_maturity_date ON checks(maturity_date);
CREATE INDEX IF NOT EXISTS idx_checks_account_name ON checks(account_name);
CREATE INDEX IF NOT EXISTS idx_checks_source_type ON checks(source_type);
CREATE INDEX IF NOT EXISTS idx_checks_review_status ON checks(review_status);
CREATE INDEX IF NOT EXISTS idx_checks_import_session_id ON checks(import_session_id);

CREATE TABLE IF NOT EXISTS check_import_sessions (
    id UUID PRIMARY KEY,
    source_type VARCHAR(32) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    account_code VARCHAR(64) NULL,
    account_name VARCHAR(255) NULL,
    company_name VARCHAR(255) NULL,
    total_rows INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS check_source_files (
    id BIGSERIAL PRIMARY KEY,
    import_session_id UUID NULL REFERENCES check_import_sessions(id),
    source_type VARCHAR(32) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NULL,
    file_hash VARCHAR(128) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS check_review_events (
    id BIGSERIAL PRIMARY KEY,
    import_session_id UUID NULL REFERENCES check_import_sessions(id),
    check_no VARCHAR(64) NULL,
    event_type VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NULL,
    old_value TEXT NULL,
    new_value TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS check_import_rows (
    id BIGSERIAL PRIMARY KEY,
    import_session_id UUID NOT NULL REFERENCES check_import_sessions(id),
    canonical_check_id BIGINT NULL REFERENCES checks(id),
    source_type VARCHAR(32) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row_index INTEGER NULL,
    check_no VARCHAR(64) NULL,
    bank_name VARCHAR(128) NULL,
    amount NUMERIC(18, 2) NULL,
    currency VARCHAR(8) NULL,
    maturity_date DATE NULL,
    transaction_date DATE NULL,
    document_date DATE NULL,
    account_name VARCHAR(255) NULL,
    company_name VARCHAR(255) NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    sent_to VARCHAR(255) NULL,
    raw_description TEXT NULL,
    raw_line TEXT NULL,
    parse_warning TEXT NULL,
    duplicate_of_check_id BIGINT NULL REFERENCES checks(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_check_import_rows_session_id ON check_import_rows(import_session_id);
CREATE INDEX IF NOT EXISTS idx_check_import_rows_duplicate_of ON check_import_rows(duplicate_of_check_id);

COMMENT ON TABLE checks IS 'Consolidated check pool from PDF, Excel, text and OCR sources';
COMMENT ON TABLE check_import_sessions IS 'One row per imported check source file';
COMMENT ON TABLE check_import_rows IS 'Raw import rows including duplicates and review status';
