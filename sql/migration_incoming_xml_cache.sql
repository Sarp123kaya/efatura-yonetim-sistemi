-- ============================================================================
-- Migration: Incoming Invoice XML Cache
-- ============================================================================
-- Purpose:
--   - Cache incoming invoice UBL/XML content by UUID so it is not fetched on
--     every run.
--   - Add an incoming-side despatch override column for manual corrections.
-- ============================================================================

CREATE TABLE IF NOT EXISTS incoming_invoice_xml_cache (
    uuid TEXT PRIMARY KEY,
    invoice_id TEXT,
    supplier TEXT,
    xml_content TEXT NOT NULL,
    xml_hash TEXT NOT NULL,
    despatch_documents JSONB DEFAULT '[]'::jsonb,
    despatch_ids JSONB DEFAULT '[]'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incoming_xml_cache_invoice_id
ON incoming_invoice_xml_cache(invoice_id);

CREATE INDEX IF NOT EXISTS idx_incoming_xml_cache_updated_at
ON incoming_invoice_xml_cache(updated_at);

COMMENT ON TABLE incoming_invoice_xml_cache IS
'Caches incoming invoice UBL/XML payloads by UUID to avoid refetching XML on every run.';

COMMENT ON COLUMN incoming_invoice_xml_cache.despatch_documents IS
'Parsed DespatchDocumentReference objects from the cached XML.';

COMMENT ON COLUMN incoming_invoice_xml_cache.despatch_ids IS
'Normalized despatch IDs derived from cached XML for quick reuse.';

ALTER TABLE incoming_invoices
ADD COLUMN IF NOT EXISTS despatch_ids_override JSONB;

COMMENT ON COLUMN incoming_invoices.despatch_ids_override IS
'Manual incoming despatch correction. If present, matchers use this instead of despatch_ids.';
