#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrika Kar Tablolarını Senkronize Et

Fatura eşleştirmedeki "Eşleşti" satırlarını alır, irsaliye prefix'ine göre
factory_A_kar, factory_F_kar, factory_T_kar tablolarına upsert eder.
"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from pg_invoice_matcher import get_matching_data
from backend.core.db import db

FACTORY_TABLES = {
    'A': 'factory_A_kar',
    'F': 'factory_F_kar',
    'T': 'factory_T_kar',
}

UPSERT_SQL = """
INSERT INTO {table} (
    outgoing_invoice_id, irsaliye_kodu, tarih, giden_fatura_no,
    giden_firma, giden_tutar, gelen_fatura_id, gelen_tedarikci,
    gelen_tutar, fark_tl, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (outgoing_invoice_id, irsaliye_kodu)
DO UPDATE SET
    tarih = EXCLUDED.tarih,
    giden_fatura_no = EXCLUDED.giden_fatura_no,
    giden_firma = EXCLUDED.giden_firma,
    giden_tutar = EXCLUDED.giden_tutar,
    gelen_fatura_id = EXCLUDED.gelen_fatura_id,
    gelen_tedarikci = EXCLUDED.gelen_tedarikci,
    gelen_tutar = EXCLUDED.gelen_tutar,
    fark_tl = EXCLUDED.fark_tl,
    updated_at = NOW();
"""


def strip_invoice_suffix(giden_fatura_no):
    """Remove ' (÷N)' suffix from invoice number for DB storage."""
    if not giden_fatura_no:
        return giden_fatura_no
    return re.sub(r'\s*\(÷\d+\)\s*$', '', str(giden_fatura_no)).strip()


def sync():
    df = get_matching_data()
    matched = df[df['Durum'] == 'Eşleşti']

    if matched.empty:
        print("Eşleşen satır yok. Sync atlanıyor.")
        return 0

    counts = {'A': 0, 'F': 0, 'T': 0}

    for prefix, table in FACTORY_TABLES.items():
        rows = matched[matched['İrsaliye Kodu'].str.match(rf'^{re.escape(prefix)}-\d+', case=False, na=False)]
        if rows.empty:
            continue

        params_list = []
        for _, r in rows.iterrows():
            giden_no = strip_invoice_suffix(r.get('Giden Fatura No', ''))
            params_list.append((
                r.get('outgoing_invoice_id', ''),
                r.get('İrsaliye Kodu', ''),
                r.get('Tarih', ''),
                giden_no,
                r.get('Giden Firma', ''),
                r.get('Giden Tutar (TL)', 0),
                r.get('Gelen Fatura ID', ''),
                r.get('Gelen Tedarikçi', ''),
                r.get('Gelen Tutar (TL)', 0),
                r.get('Fark (TL)', 0),
            ))

        sql = UPSERT_SQL.format(table=table)
        n = db.execute_batch(sql, params_list)
        counts[prefix] = n

    return counts


def main():
    print()
    print("=" * 60)
    print("  FABRIKA KAR TABLOLARI SENKRONIZASYONU")
    print("=" * 60)
    print()

    print("Eşleştirme verileri alınıyor...")
    counts = sync()

    print()
    print("  Fabrika A (AK GİPS):    ", counts.get('A', 0), " satır")
    print("  Fabrika F (FULLBOARD):  ", counts.get('F', 0), " satır")
    print("  Fabrika T (TERMATECH):  ", counts.get('T', 0), " satır")
    print()
    print("=" * 60)
    print()


if __name__ == '__main__':
    main()
