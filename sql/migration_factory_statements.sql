-- Fabrika ekstre satırları (AK GİPS, FULLBOARD vb.)

CREATE TABLE IF NOT EXISTS factory_statements (
    id                  BIGSERIAL PRIMARY KEY,
    fabrika             VARCHAR(255) NOT NULL,
    cari_hesap_kodu     VARCHAR(64),
    musteri_adi         VARCHAR(255),
    tarih               DATE NOT NULL,
    fis_no              VARCHAR(128),
    fis_turu            VARCHAR(128),
    aciklama            TEXT,
    borc                NUMERIC(18, 2),
    alacak              NUMERIC(18, 2),
    bakiye              NUMERIC(18, 2),
    bakiye_yon          CHAR(1),           -- A = Alacaklı, B = Borçlu
    source_file         VARCHAR(255),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_factory_statements_key
    ON factory_statements (fabrika, COALESCE(cari_hesap_kodu,''), tarih, COALESCE(fis_no,''));

CREATE INDEX IF NOT EXISTS idx_factory_statements_tarih   ON factory_statements(tarih);
CREATE INDEX IF NOT EXISTS idx_factory_statements_fabrika ON factory_statements(fabrika);
CREATE INDEX IF NOT EXISTS idx_factory_statements_fis_no  ON factory_statements(fis_no);

COMMENT ON TABLE factory_statements IS
    'Fabrika cari hesap ekstrelerinden çıkarılan muharebe satırları';
