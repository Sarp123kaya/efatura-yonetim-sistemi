ALTER TABLE checks
ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) NOT NULL DEFAULT 'PDF',
ADD COLUMN IF NOT EXISTS import_session_id UUID NULL,
ADD COLUMN IF NOT EXISTS review_status VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
ADD COLUMN IF NOT EXISTS source_row_index INTEGER NULL,
ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(128) NULL,
ADD COLUMN IF NOT EXISTS source_image_region VARCHAR(128) NULL;

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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS check_source_files (
    id BIGSERIAL PRIMARY KEY,
    import_session_id UUID NULL REFERENCES check_import_sessions(id),
    source_type VARCHAR(32) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NULL,
    file_hash VARCHAR(128) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS check_review_events (
    id BIGSERIAL PRIMARY KEY,
    import_session_id UUID NULL REFERENCES check_import_sessions(id),
    check_no VARCHAR(64) NULL,
    event_type VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NULL,
    old_value TEXT NULL,
    new_value TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    raw_description TEXT NULL,
    raw_line TEXT NULL,
    parse_warning TEXT NULL,
    duplicate_of_check_id BIGINT NULL REFERENCES checks(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checks_import_session_id ON checks(import_session_id);
CREATE INDEX IF NOT EXISTS idx_checks_source_type ON checks(source_type);
CREATE INDEX IF NOT EXISTS idx_checks_review_status ON checks(review_status);
CREATE INDEX IF NOT EXISTS idx_check_import_rows_session_id ON check_import_rows(import_session_id);
CREATE INDEX IF NOT EXISTS idx_check_import_rows_duplicate_of ON check_import_rows(duplicate_of_check_id);
