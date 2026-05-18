#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL-Based Invoice Matcher (Prefix-Aware)

Matching logic:
  1. Extract irsaliye code from outgoing description: "A-604" -> prefix=A, number=00604
  2. Map prefix to supplier: A=AK GİPS, F=FULLBOARD, T=TERMATECH
  3. Find incoming invoice from THAT supplier with matching despatch number
"""
import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime
from backend.core.db import db
from report_cleanup import cleanup_old_reports
from backend.core.incoming_xml_cache import ensure_xml_cache_schema

PREFIX_TO_SUPPLIER = {
    'A': 'AK',
    'F': 'FULL',
    'T': 'TERMA',
}


def normalize_despatch_code(value):
    text = str(value or '').upper()
    match = re.search(r'\b([AFT])\s*[-:]?\s*0*(\d+)\b', text)
    if not match:
        return ''
    prefix, number = match.groups()
    return f"{prefix}-{number[-5:].zfill(5)}"


def extract_plaka_text(description):
    text = str(description or '')
    match = re.search(r'\bPLAKA\s*[:：]\s*([^\n\r|;]+)', text, re.IGNORECASE)
    if match:
        plate = re.sub(r'\s+', ' ', match.group(1)).strip(' -,:')
        return f"PLAKA: {plate}" if plate else ''

    match = re.search(
        r'\b(\d{2}\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,5})\s+PLAKAL[İIıi]\b',
        text,
        re.IGNORECASE,
    )
    if not match:
        return ''
    plate = re.sub(r'\s+', '', match.group(1)).upper()
    return f"PLAKA: {plate}" if plate else ''


def extract_plaka_for_code(incoming_row, code):
    documents = incoming_row.get('despatch_documents') or []
    if isinstance(documents, str):
        try:
            documents = json.loads(documents)
        except json.JSONDecodeError:
            documents = []

    target = normalize_despatch_code(code)
    fallback = ''
    for doc in documents:
        if not isinstance(doc, dict):
            continue

        description = doc.get('description') or ''
        plaka = extract_plaka_text(description)
        if plaka and not fallback:
            fallback = plaka

        doc_codes = [
            normalize_despatch_code(doc.get('despatch_id_short')),
            normalize_despatch_code(doc.get('despatch_id_full')),
            normalize_despatch_code(description),
        ]
        if plaka and target and target in doc_codes:
            return plaka

    if fallback:
        return fallback

    xml_content = incoming_row.get('xml_content') or ''
    note_values = re.findall(r'<cbc:Note[^>]*>(.*?)</cbc:Note>', str(xml_content), flags=re.IGNORECASE | re.DOTALL)
    for note in note_values:
        plaka = extract_plaka_text(re.sub(r'<[^>]+>', ' ', note))
        if plaka:
            return plaka

    return ''


def build_incoming_index(incoming_rows):
    """
    Build lookup: (supplier_key, number) -> incoming_row

    supplier_key is derived from the supplier name (AK, FULL, TERMA).
    number is the last 5 digits zero-padded from despatch_id.
    """
    index = {}
    for row in incoming_rows:
        supplier = (row.get('supplier') or '').upper()

        if 'AK' in supplier:
            sup_key = 'AK'
        elif 'FULL' in supplier:
            sup_key = 'FULL'
        elif 'TERMA' in supplier:
            sup_key = 'TERMA'
        else:
            sup_key = 'OTHER'

        ids = row.get('despatch_ids', [])
        if isinstance(ids, str):
            ids = json.loads(ids)

        for did in ids:
            digits = re.sub(r'\D', '', str(did))
            if digits:
                num = digits[-5:].zfill(5)
                index[(sup_key, num)] = row

    return index


def get_matching_data():
    ensure_xml_cache_schema()

    outgoing_rows = db.query("""
        SELECT id, invoice_no, issue_date, firm_name,
               total_tl, taxable_amount, description,
               COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes
        FROM outgoing_invoices
        ORDER BY issue_date DESC
    """)

    incoming_rows = db.query("""
        SELECT i.invoice_id, i.issue_date, i.supplier, i.amount, i.currency,
               COALESCE(i.despatch_ids_override, i.despatch_ids) AS despatch_ids,
               c.despatch_documents,
               c.xml_content
        FROM incoming_invoices i
        LEFT JOIN incoming_invoice_xml_cache c ON c.uuid = i.uuid
        WHERE jsonb_array_length(COALESCE(i.despatch_ids_override, i.despatch_ids)) > 0
    """)

    incoming_index = build_incoming_index(incoming_rows)

    results = []

    for out_row in outgoing_rows:
        invoice_no = out_row.get('invoice_no', '')
        issue_date = out_row.get('issue_date', '')
        if isinstance(issue_date, datetime):
            issue_date = issue_date.strftime('%Y-%m-%d')
        firm_name = out_row.get('firm_name', '')
        total_tl = out_row.get('total_tl', 0) or 0

        codes = out_row.get('irsaliye_codes', [])
        if isinstance(codes, str):
            codes = json.loads(codes)

        if not codes:
            results.append({
                'outgoing_invoice_id': out_row.get('id', ''),
                'Tarih': issue_date,
                'Giden Fatura No': invoice_no,
                'Giden Firma': firm_name,
                'Giden Tutar (TL)': total_tl,
                'İrsaliye Kodu': '',
                'Gelen Fatura ID': '',
                'Gelen Tedarikçi': '',
                'Gelen Tutar (TL)': 0,
                'Fark (TL)': 0,
                'İrsaliye Açıklaması': '',
                'Durum': 'İrsaliye kodu yok'
            })
            continue

        code_count = len(codes)
        avg_outgoing = total_tl / code_count if code_count > 0 else total_tl

        for code in codes:
            # Parse prefix and number: "A-00604" -> prefix=A, number=00604
            m = re.match(r'^([AFT])-(\d+)$', code, re.IGNORECASE)
            if m:
                prefix = m.group(1).upper()
                number = m.group(2).zfill(5)
                sup_key = PREFIX_TO_SUPPLIER.get(prefix, 'OTHER')
                in_row = incoming_index.get((sup_key, number))
            else:
                in_row = None

            if in_row:
                in_despatch_count = len(in_row.get('despatch_ids', []))
                in_amount = in_row.get('amount', 0) or 0
                avg_incoming = in_amount / in_despatch_count if in_despatch_count > 1 else in_amount

                fark = avg_outgoing - avg_incoming
                durum = 'Eşleşti'
                gelen_fatura_id = in_row.get('invoice_id', '')
                gelen_supplier = in_row.get('supplier', '')
                gelen_tutar = avg_incoming
                irsaliye_aciklamasi = extract_plaka_for_code(in_row, code)
            else:
                fark = 0
                durum = 'Bulunamadı'
                gelen_fatura_id = ''
                gelen_supplier = ''
                gelen_tutar = 0
                irsaliye_aciklamasi = ''

            results.append({
                'outgoing_invoice_id': out_row.get('id', ''),
                'Tarih': issue_date,
                'Giden Fatura No': invoice_no + (f' (÷{code_count})' if code_count > 1 else ''),
                'Giden Firma': firm_name,
                'Giden Tutar (TL)': round(avg_outgoing, 2),
                'İrsaliye Kodu': code,
                'Gelen Fatura ID': gelen_fatura_id,
                'Gelen Tedarikçi': gelen_supplier,
                'Gelen Tutar (TL)': round(gelen_tutar, 2),
                'Fark (TL)': round(fark, 2),
                'İrsaliye Açıklaması': irsaliye_aciklamasi,
                'Durum': durum
            })

    return pd.DataFrame(results)


def generate_excel(df, output_dir='kayıtlar'):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cleanup_old_reports(output_path, ["Fatura_Eslestirme_*.xlsx"])

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = output_path / f'Fatura_Eslestirme_{timestamp}.xlsx'

    df_export = df.drop(columns=['outgoing_invoice_id'], errors='ignore')

    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Eşleştirme')

        workbook = writer.book
        worksheet = writer.sheets['Eşleştirme']

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

        widths = [12, 22, 35, 16, 16, 22, 35, 16, 14, 24, 16]
        for i, w in enumerate(widths):
            worksheet.set_column(i, i, w)

        for row_num in range(1, len(df_export) + 1):
            r = df_export.iloc[row_num - 1]
            for column in ['Giden Tutar (TL)', 'Gelen Tutar (TL)', 'Fark (TL)']:
                if column in df_export.columns:
                    worksheet.write(row_num, df_export.columns.get_loc(column), r[column], currency_fmt)

            durum = r['Durum']
            if durum == 'Eşleşti':
                fmt = matched_fmt
            elif durum == 'Bulunamadı':
                fmt = missing_fmt
            else:
                fmt = nocode_fmt
            worksheet.write(row_num, df_export.columns.get_loc('Durum'), durum, fmt)

        last = len(df_export) + 3
        matched = len(df_export[df_export['Durum'] == 'Eşleşti'])
        not_found = len(df_export[df_export['Durum'] == 'Bulunamadı'])
        no_code = len(df_export[df_export['Durum'] == 'İrsaliye kodu yok'])

        stat_header = workbook.add_format({
            'bold': True, 'fg_color': '#2F5496', 'font_color': 'white',
            'border': 1, 'font_size': 12
        })
        worksheet.write(last, 0, 'İSTATİSTİKLER', stat_header)
        worksheet.write(last + 1, 0, f'Eşleşen: {matched}', matched_fmt)
        worksheet.write(last + 2, 0, f'Bulunamayan: {not_found}', missing_fmt)
        worksheet.write(last + 3, 0, f'İrsaliye kodu yok: {no_code}', nocode_fmt)
        worksheet.write(last + 4, 0, f'Toplam satır: {len(df_export)}', stat_header)

        if matched > 0:
            matched_df = df_export[df_export['Durum'] == 'Eşleşti']
            total_fark = matched_df['Fark (TL)'].sum()
            avg_fark = matched_df['Fark (TL)'].mean()
            worksheet.write(last + 6, 0, 'Toplam Fark (TL):', stat_header)
            worksheet.write(last + 6, 1, round(total_fark, 2), currency_fmt)
            worksheet.write(last + 7, 0, 'Ortalama Fark (TL):', stat_header)
            worksheet.write(last + 7, 1, round(avg_fark, 2), currency_fmt)

    return filename


def main():
    print()
    print("=" * 70)
    print("  FATURA ESLESTIRME RAPORU (PostgreSQL - Prefix-Aware)")
    print("=" * 70)
    print()

    print("Veriler cekiliyor...")
    df = get_matching_data()

    matched = len(df[df['Durum'] == 'Eşleşti'])
    not_found = len(df[df['Durum'] == 'Bulunamadı'])
    no_code = len(df[df['Durum'] == 'İrsaliye kodu yok'])

    print()
    print(f"  Toplam giden fatura satiri: {len(df)}")
    print(f"  Eslesen:          {matched}")
    print(f"  Bulunamayan:      {not_found}")
    print(f"  Irsaliye kodu yok: {no_code}")
    print()

    if matched > 0:
        matched_df = df[df['Durum'] == 'Eşleşti']
        print(f"  Toplam fark:    {matched_df['Fark (TL)'].sum():,.2f} TL")
        print(f"  Ortalama fark:  {matched_df['Fark (TL)'].mean():,.2f} TL")
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
