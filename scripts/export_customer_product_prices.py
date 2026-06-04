#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Customer product price Excel report from outgoing invoice XML cache."""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from backend.core.db import db
from backend.core.outgoing_xml_cache import ensure_outgoing_xml_cache_schema
from report_cleanup import cleanup_old_reports


DETAIL_COLUMNS = [
    "Düzenleme Tarihi",
    "Müşteri",
    "Fatura No",
    "Fatura ID",
    "Fatura Tutarı",
    "KDV Matrahı",
    "İrsaliye Kodları",
    "Satır No",
    "Ürün Kodu",
    "Ürün Adı",
    "Açıklama",
    "Miktar",
    "Birim",
    "Birim Fiyat",
    "KDV Dahil Birim Fiyat",
    "KDV Oranı",
    "Satır Tutarı",
    "XML Durumu",
]


SUMMARY_COLUMNS = [
    "Müşteri",
    "Ürün Adı",
    "Açıklama",
    "Fatura Sayısı",
    "Satır Sayısı",
    "Toplam Miktar",
    "Min Birim Fiyat",
    "Ortalama Birim Fiyat",
    "Max Birim Fiyat",
    "Son Birim Fiyat",
    "Son KDV Dahil Birim Fiyat",
    "Son Fatura Tarihi",
    "Son Fatura No",
]


def parse_jsonb_list(value: Any) -> List[Any]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value if isinstance(value, list) else [value]


def format_jsonb_for_excel(value: Any) -> str:
    items = parse_jsonb_list(value)
    return ", ".join(str(item) for item in items)


def safe_sheet_name(name: str, used: set) -> str:
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", " ", str(name or "Musteri")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned) or "Musteri"
    base = cleaned[:31]
    candidate = base
    index = 2
    while candidate in used:
        suffix = f" {index}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def fetch_rows() -> List[Dict[str, Any]]:
    ensure_outgoing_xml_cache_schema()
    return db.query(
        """
        SELECT
            o.id,
            o.invoice_no,
            o.issue_date,
            o.firm_name,
            o.total_tl,
            o.taxable_amount,
            COALESCE(o.irsaliye_codes_override, o.irsaliye_codes) AS irsaliye_codes,
            c.line_items,
            c.xml_content
        FROM outgoing_invoices o
        LEFT JOIN outgoing_invoice_xml_cache c ON c.id = o.id
        ORDER BY o.firm_name ASC, o.issue_date ASC, o.invoice_no ASC
        """
    )


def build_detail_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    detail_rows = []

    for row in rows:
        base = {
            "Düzenleme Tarihi": row.get("issue_date"),
            "Müşteri": row.get("firm_name"),
            "Fatura No": row.get("invoice_no"),
            "Fatura ID": row.get("id"),
            "Fatura Tutarı": row.get("total_tl"),
            "KDV Matrahı": row.get("taxable_amount"),
            "İrsaliye Kodları": format_jsonb_for_excel(row.get("irsaliye_codes")),
        }

        line_items = parse_jsonb_list(row.get("line_items"))
        if line_items:
            for item in line_items:
                if not isinstance(item, dict):
                    continue
                detail_rows.append({**base, **item, "XML Durumu": "OK"})
        else:
            detail_rows.append({**base, "XML Durumu": "XML yok/ürün satırı yok"})

    df = pd.DataFrame(detail_rows, columns=DETAIL_COLUMNS)
    if not df.empty:
        df["Düzenleme Tarihi"] = pd.to_datetime(df["Düzenleme Tarihi"], errors="coerce").dt.tz_localize(None)
    return df


def build_summary_df(detail_df: pd.DataFrame) -> pd.DataFrame:
    valid = detail_df[detail_df["XML Durumu"] == "OK"].copy()
    if valid.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    valid = valid.sort_values(["Müşteri", "Ürün Adı", "Açıklama", "Düzenleme Tarihi", "Fatura No"])
    grouped = valid.groupby(["Müşteri", "Ürün Adı", "Açıklama"], dropna=False)
    summary = grouped.agg(
        **{
            "Fatura Sayısı": ("Fatura No", "nunique"),
            "Satır Sayısı": ("Fatura No", "size"),
            "Toplam Miktar": ("Miktar", "sum"),
            "Min Birim Fiyat": ("Birim Fiyat", "min"),
            "Ortalama Birim Fiyat": ("Birim Fiyat", "mean"),
            "Max Birim Fiyat": ("Birim Fiyat", "max"),
            "Son Birim Fiyat": ("Birim Fiyat", "last"),
            "Son KDV Dahil Birim Fiyat": ("KDV Dahil Birim Fiyat", "last"),
            "Son Fatura Tarihi": ("Düzenleme Tarihi", "last"),
            "Son Fatura No": ("Fatura No", "last"),
        }
    ).reset_index()
    return summary[SUMMARY_COLUMNS]


def write_excel(detail_df: pd.DataFrame, summary_df: pd.DataFrame, output_file: Path) -> None:
    with pd.ExcelWriter(output_file, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        detail_df.to_excel(writer, index=False, sheet_name="Tüm Detaylar")
        summary_df.to_excel(writer, index=False, sheet_name="Müşteri Özeti")

        used_sheet_names = {"Tüm Detaylar", "Müşteri Özeti"}
        sheet_frames = {
            "Tüm Detaylar": detail_df,
            "Müşteri Özeti": summary_df,
        }
        for customer, customer_df in detail_df.groupby("Müşteri", dropna=False):
            sheet_name = safe_sheet_name(str(customer), used_sheet_names)
            customer_df.to_excel(writer, index=False, sheet_name=sheet_name)
            sheet_frames[sheet_name] = customer_df

        workbook = writer.book
        header_fmt = workbook.add_format({
            "bold": True,
            "fg_color": "#2F5496",
            "font_color": "white",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        currency_fmt = workbook.add_format({"num_format": '#,##0.00 "₺"', "border": 1})
        number_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd", "border": 1})

        currency_cols = {
            "Fatura Tutarı",
            "KDV Matrahı",
            "Birim Fiyat",
            "KDV Dahil Birim Fiyat",
            "Satır Tutarı",
            "Min Birim Fiyat",
            "Ortalama Birim Fiyat",
            "Max Birim Fiyat",
            "Son Birim Fiyat",
            "Son KDV Dahil Birim Fiyat",
        }
        number_cols = {"Miktar", "KDV Oranı", "Fatura Sayısı", "Satır Sayısı", "Toplam Miktar"}
        date_cols = {"Düzenleme Tarihi", "Son Fatura Tarihi"}

        for sheet_name, worksheet in writer.sheets.items():
            sheet_df = sheet_frames[sheet_name]

            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(len(sheet_df), 1), max(len(sheet_df.columns) - 1, 0))

            for col_num, column in enumerate(sheet_df.columns):
                worksheet.write(0, col_num, column, header_fmt)
                width = min(max(len(str(column)) + 2, 12), 45)
                if not sheet_df.empty:
                    sample_width = sheet_df[column].astype(str).map(len).max()
                    width = min(max(width, int(sample_width) + 2), 45)
                worksheet.set_column(col_num, col_num, width)

            for row_num in range(1, len(sheet_df) + 1):
                for col_num, column in enumerate(sheet_df.columns):
                    value = sheet_df.iloc[row_num - 1][column]
                    if pd.isna(value):
                        value = ""
                    if column in currency_cols:
                        worksheet.write(row_num, col_num, value, currency_fmt)
                    elif column in number_cols:
                        worksheet.write(row_num, col_num, value, number_fmt)
                    elif column in date_cols and value != "":
                        worksheet.write_datetime(row_num, col_num, pd.to_datetime(value).to_pydatetime(), date_fmt)
                    else:
                        worksheet.write(row_num, col_num, value)


def export_customer_product_prices(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_reports(output_dir, ["Musteri_Urun_Fiyatlari_*.xlsx"])
    rows = fetch_rows()
    detail_df = build_detail_df(rows)
    summary_df = build_summary_df(detail_df)
    output_file = output_dir / f"Musteri_Urun_Fiyatlari_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    write_excel(detail_df, summary_df, output_file)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Müşteri bazlı giden fatura ürün/fiyat Excel raporu üretir.")
    parser.add_argument(
        "--output-dir",
        default="kayıtlar",
        help="Excel raporunun yazılacağı klasör (varsayılan: kayıtlar).",
    )
    args = parser.parse_args()

    try:
        output_file = export_customer_product_prices(Path(args.output_dir))
    finally:
        db.close_persistent_connection()

    print(f"✅ Müşteri ürün fiyat raporu oluşturuldu: {output_file}")


if __name__ == "__main__":
    main()
