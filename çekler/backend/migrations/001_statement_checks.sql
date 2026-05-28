CREATE TABLE IF NOT EXISTS checks (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NULL,
    account_code VARCHAR(64) NULL,
    account_name VARCHAR(255) NULL,
    company_name VARCHAR(255) NULL,
    movement_type VARCHAR(64) NOT NULL,
    check_no VARCHAR(64) NOT NULL,
    bank_name VARCHAR(128) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT checks_status_allowed CHECK (
        status IN ('PORTFOLIO', 'ENDORSED', 'BANK', 'CASHED', 'RETURNED', 'CANCELLED')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_checks_statement_duplicate
ON checks (
    COALESCE(account_name, ''),
    check_no,
    bank_name,
    maturity_date,
    amount
);
