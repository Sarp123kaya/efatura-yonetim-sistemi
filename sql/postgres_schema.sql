-- Unified PostgreSQL schema (parallel to existing SQLite + Excel outputs)
-- Business rules preserved:
-- - N-to-N invoice <-> dispatch via dispatch_invoice
-- - Allocation method currently always EQUAL_SPLIT
-- - Allocations stored explicitly (2 decimals, TRY); remainder handled in writer logic

CREATE TABLE IF NOT EXISTS invoice (
  id                  BIGSERIAL PRIMARY KEY,

  direction           TEXT NOT NULL CHECK (direction IN ('IN', 'OUT')),
  invoice_no           TEXT NOT NULL,
  total_amount         NUMERIC(18,2) NOT NULL CHECK (total_amount >= 0),
  currency             TEXT NOT NULL DEFAULT 'TRY',

  description_raw      TEXT,
  description_clean    TEXT,

  source              TEXT NOT NULL CHECK (source IN ('XML_AKGIPS', 'XML_FULLBOARD', 'ISBASI_API')),

  -- Optional but strongly recommended for incremental ingestion & dedupe
  external_id          TEXT,
  source_file          TEXT,
  issue_date           DATE,
  raw_payload          JSONB,

  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_invoice_source_direction_no UNIQUE (source, direction, invoice_no),
  CONSTRAINT uq_invoice_source_external UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_invoice_direction ON invoice(direction);
CREATE INDEX IF NOT EXISTS idx_invoice_source ON invoice(source);
CREATE INDEX IF NOT EXISTS idx_invoice_invoice_no ON invoice(invoice_no);

CREATE TABLE IF NOT EXISTS dispatch (
  id      BIGSERIAL PRIMARY KEY,
  code    TEXT NOT NULL UNIQUE CHECK (code ~ '^[AF]-\d{4,5}$'),
  prefix  CHAR(1) GENERATED ALWAYS AS (substring(code from 1 for 1)) STORED,
  number  INTEGER GENERATED ALWAYS AS (substring(code from 3)::int) STORED
);

CREATE INDEX IF NOT EXISTS idx_dispatch_prefix_number ON dispatch(prefix, number);

CREATE TABLE IF NOT EXISTS dispatch_invoice (
  id                BIGSERIAL PRIMARY KEY,

  dispatch_id       BIGINT NOT NULL REFERENCES dispatch(id) ON DELETE RESTRICT,
  invoice_id        BIGINT NOT NULL REFERENCES invoice(id) ON DELETE CASCADE,

  direction         TEXT NOT NULL CHECK (direction IN ('IN', 'OUT')),
  allocated_amount  NUMERIC(18,2) NOT NULL CHECK (allocated_amount >= 0),

  allocation_method TEXT NOT NULL DEFAULT 'EQUAL_SPLIT'
                  CHECK (allocation_method = 'EQUAL_SPLIT'),

  raw_token         TEXT,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_dispatch_invoice UNIQUE (dispatch_id, invoice_id, direction)
);

CREATE INDEX IF NOT EXISTS idx_di_dispatch ON dispatch_invoice(dispatch_id);
CREATE INDEX IF NOT EXISTS idx_di_invoice ON dispatch_invoice(invoice_id);
CREATE INDEX IF NOT EXISTS idx_di_direction ON dispatch_invoice(direction);

CREATE OR REPLACE VIEW v_dispatch_profit AS
SELECT
  d.code AS dispatch_code,
  COALESCE(SUM(di.allocated_amount) FILTER (WHERE di.direction = 'IN'), 0)  AS incoming_allocated_total,
  COALESCE(SUM(di.allocated_amount) FILTER (WHERE di.direction = 'OUT'), 0) AS outgoing_allocated_total,
  COALESCE(SUM(di.allocated_amount) FILTER (WHERE di.direction = 'OUT'), 0)
  - COALESCE(SUM(di.allocated_amount) FILTER (WHERE di.direction = 'IN'), 0) AS profit
FROM dispatch d
LEFT JOIN dispatch_invoice di ON di.dispatch_id = d.id
GROUP BY d.code;


