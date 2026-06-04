-- ============================================================================
-- Migration: Outgoing Invoice XML Cache
-- ============================================================================
-- Purpose:
--   - Cache outgoing invoice UBL/XML content so customer product/price reports
--     can be generated without refetching every invoice XML on each run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS outgoing_invoice_xml_cache (
    id TEXT PRIMARY KEY,
    invoice_no TEXT,
    firm_name TEXT,
    xml_content TEXT NOT NULL,
    xml_hash TEXT NOT NULL,
    line_items JSONB DEFAULT '[]'::jsonb,
    fetch_key TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_invoice_no
ON outgoing_invoice_xml_cache(invoice_no);

CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_firm_name
ON outgoing_invoice_xml_cache(firm_name);

CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_updated_at
ON outgoing_invoice_xml_cache(updated_at);

COMMENT ON TABLE outgoing_invoice_xml_cache IS
'Caches outgoing invoice UBL/XML payloads for customer product price reporting.';

COMMENT ON COLUMN outgoing_invoice_xml_cache.line_items IS
'Parsed InvoiceLine product/quantity/price rows from cached outgoing invoice XML.';
