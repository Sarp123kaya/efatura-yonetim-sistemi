-- Müşteri kartları (İşbaşı firms API / giden fatura firm nesnesi)

CREATE TABLE IF NOT EXISTS firm_cards (
    firm_id TEXT PRIMARY KEY,
    name TEXT,
    tax_id TEXT,
    city TEXT,
    district TEXT,
    balance NUMERIC(18, 2),
    beginning_balance NUMERIC(18, 2),
    beginning_balance_date TIMESTAMPTZ,
    currency TEXT DEFAULT 'TL',
    ar_ap_type INTEGER,
    balance_updated_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    raw_json JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_firm_cards_tax_id ON firm_cards(tax_id);
CREATE INDEX IF NOT EXISTS idx_firm_cards_name ON firm_cards(name);

COMMENT ON TABLE firm_cards IS
'Müşteri/cari kartları; İşbaşı firms listesi veya giden fatura raw_json.firm ile doldurulur.';
