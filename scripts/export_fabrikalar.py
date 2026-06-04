#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrikalar Excel Raporu

factory_A_kar, factory_F_kar, factory_T_kar tablolarından veriyi okur,
geçmişten bugüne sıralayıp Excel raporu oluşturur.
Her fabrika ayrı sayfada, özet sayfasında toplam alacaklar.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime

from backend.core.db import db

FACTORY_CONFIG = [
    ('factory_A_kar', 'Fabrika A (AK GİPS)'),
    ('factory_F_kar', 'Fabrika F (FULLBOARD)'),
    ('factory_T_kar', 'Fabrika T (TERMATECH)'),
]

COLUMNS_TR = {
    'tarih': 'Tarih',
    'giden_fatura_no': 'Giden Fatura No',
    'giden_firma': 'Giden Firma',
    'giden_tutar': 'Giden Tutar (TL)',
    'irsaliye_kodu': 'İrsaliye Kodu',
    'gelen_fatura_id': 'Gelen Fatura ID',
    'gelen_tedarikci': 'Gelen Tedarikçi',
    'gelen_tutar': 'Gelen Tutar (TL)',
    'fark_tl': 'Kar (TL)',
}


def fetch_factory_data(table_name):
    """Fetch factory data ordered by date ascending (past to present)."""
    query = f"""
        SELECT tarih, giden_fatura_no, giden_firma, giden_tutar,
               irsaliye_kodu, gelen_fatura_id, gelen_tedarikci,
               gelen_tutar, fark_tl
        FROM {table_name}
        ORDER BY tarih ASC
    """
    rows = db.query(query)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def export_fabrikalar(output_dir='kayıtlar'):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_path / f'Fabrikalar_{timestamp}.xlsx'

    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        workbook = writer.book
        currency_fmt = workbook.add_format({'num_format': '#,##0.00 ₺', 'border': 1})
        header_fmt = workbook.add_format({
            'bold': True, 'fg_color': '#2F5496', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 11
        })
        stat_header = workbook.add_format({
            'bold': True, 'fg_color': '#2F5496', 'font_color': 'white',
            'border': 1, 'font_size': 12
        })

        totals = {}

        for table_name, sheet_name in FACTORY_CONFIG:
            df = fetch_factory_data(table_name)

            if not df.empty:
                df = df.rename(columns=COLUMNS_TR)
                total_kar = df['Kar (TL)'].sum()
            else:
                df = pd.DataFrame(columns=list(COLUMNS_TR.values()))
                total_kar = 0

            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
            worksheet = writer.sheets[sheet_name[:31]]

            for col_num, col in enumerate(df.columns):
                worksheet.write(0, col_num, col, header_fmt)

            for row_num in range(1, len(df) + 1):
                for col_num, col in enumerate(df.columns):
                    val = df.iloc[row_num - 1][col]
                    if col in ('Giden Tutar (TL)', 'Gelen Tutar (TL)', 'Kar (TL)'):
                        worksheet.write(row_num, col_num, val, currency_fmt)
                    else:
                        worksheet.write(row_num, col_num, val)

            totals[sheet_name] = total_kar

        # Özet sayfası
        summary_data = [
            ['Fabrika A (AK GİPS)', totals.get('Fabrika A (AK GİPS)', 0)],
            ['Fabrika F (FULLBOARD)', totals.get('Fabrika F (FULLBOARD)', 0)],
            ['Fabrika T (TERMATECH)', totals.get('Fabrika T (TERMATECH)', 0)],
            ['Genel Toplam', sum(totals.values())],
        ]
        summary_df = pd.DataFrame(summary_data, columns=['Fabrika', 'Toplam Alacak (TL)'])
        summary_df.to_excel(writer, index=False, sheet_name='Özet')

        summary_ws = writer.sheets['Özet']
        summary_ws.write(0, 0, 'Fabrika', header_fmt)
        summary_ws.write(0, 1, 'Toplam Alacak (TL)', header_fmt)
        for row_num in range(1, 5):
            summary_ws.write(row_num, 0, summary_data[row_num - 1][0])
            summary_ws.write(row_num, 1, summary_data[row_num - 1][1], currency_fmt)
        summary_ws.set_column(0, 0, 25)
        summary_ws.set_column(1, 1, 20)

    return filename


def main():
    print()
    print("=" * 60)
    print("  FABRIKALAR EXCEL RAPORU")
    print("=" * 60)
    print()

    print("Veriler alınıyor...")
    filename = export_fabrikalar()

    print()
    print(f"  Rapor: {filename}")
    print()
    print("=" * 60)
    print()


if __name__ == '__main__':
    main()
