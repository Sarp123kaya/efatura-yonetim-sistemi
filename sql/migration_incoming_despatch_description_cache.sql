-- Cache incoming e-despatch PDF/UBL description extraction by UUID.

CREATE TABLE IF NOT EXISTS incoming_despatch_description_cache (
    uuid TEXT PRIMARY KEY,
    dispatch_id TEXT,
    supplier TEXT,
    description TEXT DEFAULT '',
    document_text TEXT DEFAULT '',
    fetch_source TEXT DEFAULT '',
    fetch_status TEXT NOT NULL DEFAULT 'success',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incoming_despatch_desc_dispatch_id
ON incoming_despatch_description_cache(dispatch_id);

CREATE INDEX IF NOT EXISTS idx_incoming_despatch_desc_updated_at
ON incoming_despatch_description_cache(updated_at);

COMMENT ON TABLE incoming_despatch_description_cache IS
'Incoming e-despatch description text extracted from UBL/PDF documents by UUID.';
