#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ters Yönlü Fatura Eşleştirme (Gelen -> Giden)

Gelen faturaların irsaliye kodlarını alıp giden faturalarda karşılığı
olup olmadığını kontrol eder. Karşılıksız gelen faturaları tespit eder.
"""
import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime
from backend.core.db import db
from backend.core.incoming_xml_cache import ensure_xml_cache_schema
from report_cleanup import cleanup_old_reports

SUPPLIER_TO_PREFIX = {
    'AK': 'A',
    'FULL': 'F',
    'TERMA': 'T',
}


def classify_supplier(supplier_name):
    s = (supplier_name or '').upper()
    if 'AK' in s:
        return 'AK'
    if 'FULL' in s:
        return 'FULL'
    if 'TERMA' in s:
        return 'TERMA'
    return 'OTHER'


def build_outgoing_index(outgoing_rows):
    """
    Build lookup: (prefix, number) -> outgoing_row

    prefix: A/F/T from irsaliye code
    number: zero-padded 5-digit number
    """
    index = {}
    for row in outgoing_rows:
        codes = row.get('irsaliye_codes', [])
        if isinstance(codes, str):
            codes = json.loads(codes)
        for code in codes:
            m = re.match(r'^([AFT])-(\d+)$', code, re.IGNORECASE)
            if m:
                prefix = m.group(1).upper()
                number = m.group(2).zfill(5)
                index[(prefix, number)] = row
    return index


def get_reverse_matching_data():
    ensure_xml_cache_schema()

    incoming_rows = db.query("""
        SELECT invoice_id, issue_date, supplier, amount, currency,
               COALESCE(despatch_ids_override, despatch_ids) AS despatch_ids
        FROM incoming_invoices
        ORDER BY issue_date ASC
    """)

    outgoing_rows = db.query("""
        SELECT id, invoice_no, issue_date, firm_name,
               total_tl, taxable_amount,
               COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes
        FROM outgoing_invoices
    """)

    outgoing_index = build_outgoing_index(outgoing_rows)

    results = []

    for in_row in incoming_rows:
        invoice_id = in_row.get('invoice_id', '')
        issue_date = in_row.get('issue_date', '')
        if isinstance(issue_date, datetime):
            issue_date = issue_date.strftime('%Y-%m-%d')
        supplier = in_row.get('supplier', '')
        amount = in_row.get('amount', 0) or 0
        currency = in_row.get('currency', 'TRY')

        sup_key = classify_supplier(supplier)
        prefix = SUPPLIER_TO_PREFIX.get(sup_key, '')

        ids = in_row.get('despatch_ids', [])
        if isinstance(ids, str):
            ids = json.loads(ids)

        if not ids:
            results.append({
                'Tarih': issue_date,
                'Gelen Fatura ID': invoice_id,
                'Gelen Tedarikçi': supplier,
                'Gelen Tutar (TL)': amount,
                'Para Birimi': currency,
                'İrsaliye Kodu': '',
                'Giden Fatura No': '',
                'Giden Firma': '',
                'Giden Tutar (TL)': 0,
                'Fark (TL)': 0,
                'Durum': 'İrsaliye yok'
            })
            continue

        despatch_count = len(ids)
        avg_incoming = amount / despatch_count if despatch_count > 1 else amount

        for did in ids:
            digits = re.sub(r'\D', '', str(did))
            if not digits:
                results.append({
                    'Tarih': issue_date,
                    'Gelen Fatura ID': invoice_id,
                    'Gelen Tedarikçi': supplier,
                    'Gelen Tutar (TL)': round(avg_incoming, 2),
                    'Para Birimi': currency,
                    'İrsaliye Kodu': str(did),
                    'Giden Fatura No': '',
                    'Giden Firma': '',
                    'Giden Tutar (TL)': 0,
                    'Fark (TL)': 0,
                    'Durum': 'Geçersiz kod'
                })
                continue

            number = digits[-5:].zfill(5)
            code_display = f"{prefix}-{number}" if prefix else number

            out_row = outgoing_index.get((prefix, number)) if prefix else None

            if out_row:
                out_codes = out_row.get('irsaliye_codes', [])
                if isinstance(out_codes, str):
                    out_codes = json.loads(out_codes)
                out_code_count = len(out_codes) if out_codes else 1
                out_total = out_row.get('total_tl', 0) or 0
                avg_outgoing = out_total / out_code_count if out_code_count > 1 else out_total

                fark = avg_outgoing - avg_incoming
                results.append({
                    'Tarih': issue_date,
                    'Gelen Fatura ID': invoice_id,
                    'Gelen Tedarikçi': supplier,
                    'Gelen Tutar (TL)': round(avg_incoming, 2),
                    'Para Birimi': currency,
                    'İrsaliye Kodu': code_display,
                    'Giden Fatura No': out_row.get('invoice_no', ''),
                    'Giden Firma': out_row.get('firm_name', ''),
                    'Giden Tutar (TL)': round(avg_outgoing, 2),
                    'Fark (TL)': round(fark, 2),
                    'Durum': 'Eşleşti'
                })
            else:
                results.append({
                    'Tarih': issue_date,
                    'Gelen Fatura ID': invoice_id,
                    'Gelen Tedarikçi': supplier,
                    'Gelen Tutar (TL)': round(avg_incoming, 2),
                    'Para Birimi': currency,
                    'İrsaliye Kodu': code_display,
                    'Giden Fatura No': '',
                    'Giden Firma': '',
                    'Giden Tutar (TL)': 0,
                    'Fark (TL)': 0,
                    'Durum': 'Karşılıksız'
                })

    return pd.DataFrame(results)


def generate_excel(df, output_dir='kayıtlar'):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cleanup_old_reports(output_path, ["Ters_Eslestirme_*.xlsx"])

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_path / f'Ters_Eslestirme_{timestamp}.xlsx'
    df_export = df.drop(columns=['Para Birimi'], errors='ignore')

    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Gelen Kontrol')

        workbook = writer.book
        worksheet = writer.sheets['Gelen Kontrol']

        header_fmt = workbook.add_format({
            'bold': True, 'fg_color': '#2F5496', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 11
        })
        currency_fmt = workbook.add_format({'num_format': '#,##0.00 ₺', 'border': 1})
        matched_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'border': 1, 'bold': True})
        missing_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1, 'bold': True})
        nocode_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'border': 1, 'bold': True})

        for col_num, value in enumerate(df_export.columns.values):
            worksheet.write(0, col_num, value, header_fmt)

        widths = [12, 22, 35, 16, 16, 22, 35, 16, 14, 16]
        for i, w in enumerate(widths):
            worksheet.set_column(i, i, w)

        for row_num in range(1, len(df_export) + 1):
            r = df_export.iloc[row_num - 1]
            for column in ['Gelen Tutar (TL)', 'Giden Tutar (TL)', 'Fark (TL)']:
                if column in df_export.columns:
                    worksheet.write(row_num, df_export.columns.get_loc(column), r[column], currency_fmt)

            durum = r['Durum']
            if durum == 'Eşleşti':
                fmt = matched_fmt
            elif durum == 'Karşılıksız':
                fmt = missing_fmt
            else:
                fmt = nocode_fmt
            worksheet.write(row_num, df_export.columns.get_loc('Durum'), durum, fmt)

        last = len(df_export) + 3
        matched = len(df[df['Durum'] == 'Eşleşti'])
        karsilsiz = len(df[df['Durum'] == 'Karşılıksız'])
        no_code = len(df[df['Durum'] == 'İrsaliye yok'])
        invalid = len(df[df['Durum'] == 'Geçersiz kod'])

        stat_header = workbook.add_format({
            'bold': True, 'fg_color': '#2F5496', 'font_color': 'white',
            'border': 1, 'font_size': 12
        })
        worksheet.write(last, 0, 'GELEN FATURA KONTROL', stat_header)
        worksheet.write(last + 1, 0, f'Eşleşen: {matched}', matched_fmt)
        worksheet.write(last + 2, 0, f'Karşılıksız: {karsilsiz}', missing_fmt)
        worksheet.write(last + 3, 0, f'İrsaliye yok: {no_code}', nocode_fmt)
        if invalid > 0:
            worksheet.write(last + 4, 0, f'Geçersiz kod: {invalid}', nocode_fmt)
        worksheet.write(last + 5, 0, f'Toplam satır: {len(df_export)}', stat_header)

        if karsilsiz > 0:
            karsilsiz_df = df[df['Durum'] == 'Karşılıksız']
            total_karsilsiz = karsilsiz_df['Gelen Tutar (TL)'].sum()
            worksheet.write(last + 7, 0, 'Karşılıksız Toplam (TL):', stat_header)
            worksheet.write(last + 7, 1, round(total_karsilsiz, 2), currency_fmt)

    return filename


def main():
    print()
    print("=" * 70)
    print("  TERS ESLESTIRME: GELEN -> GIDEN KONTROL")
    print("=" * 70)
    print()

    print("Veriler cekiliyor...")
    df = get_reverse_matching_data()

    matched = len(df[df['Durum'] == 'Eşleşti'])
    karsilsiz = len(df[df['Durum'] == 'Karşılıksız'])
    no_code = len(df[df['Durum'] == 'İrsaliye yok'])

    print()
    print(f"  Toplam gelen fatura satiri: {len(df)}")
    print(f"  Eslesen:       {matched}")
    print(f"  Karsilsiz:     {karsilsiz}")
    print(f"  Irsaliye yok:  {no_code}")
    print()

    if karsilsiz > 0:
        karsilsiz_df = df[df['Durum'] == 'Karşılıksız']
        print(f"  Karsilsiz toplam: {karsilsiz_df['Gelen Tutar (TL)'].sum():,.2f} TL")
        print()

    print("Excel raporu olusturuluyor...")
    filename = generate_excel(df)

    print()
    print("=" * 70)
    print(f"  Rapor: {filename}")
    print("=" * 70)
    print()

    return filename


if __name__ == '__main__':
    main()
