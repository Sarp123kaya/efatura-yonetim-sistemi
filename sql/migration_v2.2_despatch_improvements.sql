-- ============================================================================
-- Migration v2.2: Despatch ID Improvements
-- ============================================================================
-- Date: 2026-02-10
-- Purpose: Add despatch_id column to outgoing_invoices for supplier-based normalization
-- Related: normalize.py v2.2 (normalize_incoming_despatch, extract_despatch_from_description)
-- ============================================================================

-- Add despatch_id column to outgoing_invoices
-- This will store the normalized despatch ID extracted from description
-- Format: A-XXXX or F-XXXX based on description content

ALTER TABLE outgoing_invoices 
ADD COLUMN IF NOT EXISTS despatch_id TEXT;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_outgoing_invoices_despatch_id 
ON outgoing_invoices(despatch_id);

-- Add comment
COMMENT ON COLUMN outgoing_invoices.despatch_id IS 
'Normalized despatch ID extracted from description (A-XXXX or F-XXXX format). Added in v2.2';

-- ============================================================================
-- Optional: Update existing records (if you have data)
-- ============================================================================
-- Note: This requires backend.core.normalize.extract_despatch_from_description
-- Run this AFTER updating the normalize.py module

-- You can update existing records using a Python script:
-- 
-- from backend.core.normalize import extract_despatch_from_description
-- from backend.core.db import db
-- 
-- rows = db.query("SELECT id, description FROM outgoing_invoices WHERE despatch_id IS NULL")
-- for row in rows:
--     despatch_id = extract_despatch_from_description(row['description'])
--     if despatch_id:
--         db.execute("UPDATE outgoing_invoices SET despatch_id = %s WHERE id = %s", 
--                   (despatch_id, row['id']))
--
-- Or run this SQL (if you have a simple pattern):
-- UPDATE outgoing_invoices 
-- SET despatch_id = 
--     CASE 
--         WHEN description ~ '([AF])\s*[-/]\s*(\d{3,6})' THEN
--             (regexp_matches(description, '([AF])\s*[-/]\s*(\d{3,6})', 'i'))[1] || '-' ||
--             (regexp_matches(description, '([AF])\s*[-/]\s*(\d{3,6})', 'i'))[2]
--         ELSE NULL
--     END
-- WHERE despatch_id IS NULL;

-- ============================================================================
-- Verification
-- ============================================================================

-- Check column exists
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'outgoing_invoices' AND column_name = 'despatch_id';

-- Check how many records have despatch_id
SELECT 
    COUNT(*) as total_records,
    COUNT(despatch_id) as records_with_despatch,
    COUNT(*) - COUNT(despatch_id) as records_without_despatch,
    ROUND(COUNT(despatch_id) * 100.0 / COUNT(*), 2) as percentage_with_despatch
FROM outgoing_invoices;

-- Sample records with despatch_id
SELECT invoice_no, issue_date, firm_name, despatch_id, 
       LEFT(description, 50) as description_preview
FROM outgoing_invoices 
WHERE despatch_id IS NOT NULL
ORDER BY issue_date DESC
LIMIT 10;

-- ============================================================================
-- Rollback (if needed)
-- ============================================================================

-- DROP INDEX IF EXISTS idx_outgoing_invoices_despatch_id;
-- ALTER TABLE outgoing_invoices DROP COLUMN IF EXISTS despatch_id;

-- ============================================================================
-- Notes
-- ============================================================================

-- Incoming invoices already use despatch_ids JSONB column, so no changes needed there.
-- The incoming normalization happens at extraction time using normalize_incoming_despatch().
--
-- For outgoing invoices, despatch_id is now extracted during ingestion and stored
-- separately from description for easier querying and matching.
--
-- Benefits:
--   1. Faster despatch matching queries (indexed column)
--   2. Cleaner separation of concerns (description vs despatch_id)
--   3. Consistent format (A-XXXX or F-XXXX)
--   4. No need to regex description every time for matching
