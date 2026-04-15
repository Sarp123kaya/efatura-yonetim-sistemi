-- ============================================================================
-- Migration: Fabrika Kar Tabloları (A, F, T)
-- ============================================================================
-- Date: 2026-02-19
-- Purpose: Store invoice profit (Fark TL) per factory for receivables tracking
-- Tables: factory_A_kar, factory_F_kar, factory_T_kar
-- ============================================================================

-- Fabrika A (AK GİPS) - irsaliye prefix A
CREATE TABLE IF NOT EXISTS factory_A_kar (
    id BIGSERIAL PRIMARY KEY,
    outgoing_invoice_id TEXT NOT NULL,
    irsaliye_kodu TEXT NOT NULL,
    tarih DATE NOT NULL,
    giden_fatura_no TEXT,
    giden_firma TEXT,
    giden_tutar NUMERIC(18,2),
    gelen_fatura_id TEXT,
    gelen_tedarikci TEXT,
    gelen_tutar NUMERIC(18,2),
    fark_tl NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (outgoing_invoice_id, irsaliye_kodu)
);

CREATE INDEX IF NOT EXISTS idx_factory_A_kar_tarih ON factory_A_kar(tarih);
CREATE INDEX IF NOT EXISTS idx_factory_A_kar_outgoing ON factory_A_kar(outgoing_invoice_id);

COMMENT ON TABLE factory_A_kar IS 'AK GİPS fabrikası - fatura kar (Fark TL) kayıtları';

-- Fabrika F (FULLBOARD) - irsaliye prefix F
CREATE TABLE IF NOT EXISTS factory_F_kar (
    id BIGSERIAL PRIMARY KEY,
    outgoing_invoice_id TEXT NOT NULL,
    irsaliye_kodu TEXT NOT NULL,
    tarih DATE NOT NULL,
    giden_fatura_no TEXT,
    giden_firma TEXT,
    giden_tutar NUMERIC(18,2),
    gelen_fatura_id TEXT,
    gelen_tedarikci TEXT,
    gelen_tutar NUMERIC(18,2),
    fark_tl NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (outgoing_invoice_id, irsaliye_kodu)
);

CREATE INDEX IF NOT EXISTS idx_factory_F_kar_tarih ON factory_F_kar(tarih);
CREATE INDEX IF NOT EXISTS idx_factory_F_kar_outgoing ON factory_F_kar(outgoing_invoice_id);

COMMENT ON TABLE factory_F_kar IS 'FULLBOARD fabrikası - fatura kar (Fark TL) kayıtları';

-- Fabrika T (TERMATECH) - irsaliye prefix T
CREATE TABLE IF NOT EXISTS factory_T_kar (
    id BIGSERIAL PRIMARY KEY,
    outgoing_invoice_id TEXT NOT NULL,
    irsaliye_kodu TEXT NOT NULL,
    tarih DATE NOT NULL,
    giden_fatura_no TEXT,
    giden_firma TEXT,
    giden_tutar NUMERIC(18,2),
    gelen_fatura_id TEXT,
    gelen_tedarikci TEXT,
    gelen_tutar NUMERIC(18,2),
    fark_tl NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (outgoing_invoice_id, irsaliye_kodu)
);

CREATE INDEX IF NOT EXISTS idx_factory_T_kar_tarih ON factory_T_kar(tarih);
CREATE INDEX IF NOT EXISTS idx_factory_T_kar_outgoing ON factory_T_kar(outgoing_invoice_id);

COMMENT ON TABLE factory_T_kar IS 'TERMATECH fabrikası - fatura kar (Fark TL) kayıtları';
