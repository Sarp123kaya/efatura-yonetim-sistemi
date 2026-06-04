-- ============================================================================
-- Migration: İrsaliye Kodu Manuel Düzeltme (Override)
-- ============================================================================
-- Date: 2026-02-23
-- Purpose: Allow permanent manual correction of wrongly entered irsaliye codes
-- Usage: correct_irsaliye.py --invoice X --from A-00064 --to F-00064
-- ============================================================================

ALTER TABLE outgoing_invoices 
ADD COLUMN IF NOT EXISTS irsaliye_codes_override JSONB;

COMMENT ON COLUMN outgoing_invoices.irsaliye_codes_override IS 
'Manuel düzeltme: varsa irsaliye_codes yerine kullanılır (A/F/T-XXXXX format). Agent override''a dokunmaz.';
