#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AK GIPS / FULLBOARD gelen fatura ürün detay Excel raporu.

Gelen fatura başlıklarını PostgreSQL'den, ürün satırlarını ise cache'lenmiş
UBL/XML içindeki InvoiceLine öğelerinden okur.
"""
import argparse
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from xlsxwriter.utility import xl_rowcol_to_cell

from backend.core.db import db
from report_cleanup import cleanup_old_reports


NAMESPACES = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


SUPPLIER_CONFIG = [
    {
        "code": "ak_gips",
        "display": "AK GIPS",
        "filename": "AK_GIPS_Fabrikasi",
        "keywords": ("ak gips", "akgips"),
        "prefix": "A",
    },
    {
        "code": "fullboard",
        "display": "FULLBOARD",
        "filename": "FULLBOARD_Fabrikasi",
        "keywords": ("fullboard", "fulboard"),
        "prefix": "F",
    },
]


DETAIL_COLUMNS = [
    "Düzenleme Tarihi",
    "Tedarikçi",
    "Fatura ID",
    "UUID",
    "TCKN/VKN",
    "Fatura Tutarı",
    "KDV Matrahı",
    "Para Birimi",
    "İrsaliye Kodları",
    "Giden Müşteri",
    "Giden Müşteri Fiyatı",
    "İrsaliye Açıklaması",
    "Satır No",
    "Ürün Kodu",
    "Ürün Adı",
    "Açıklama",
    "Miktar",
    "Birim",
    "Birim Fiyat",
    "KDV Dahil Birim Fiyat",
    "Torba KG",
    "Alış Fiyatı (Torba)",
    "Satır Tutarı",
    "KDV Oranı",
]


SUMMARY_COLUMNS = [
    "Düzenleme Tarihi",
    "Tedarikçi",
    "Fatura ID",
    "UUID",
    "Fatura Tutarı",
    "KDV Matrahı",
    "Para Birimi",
    "İrsaliye Kodları",
    "Giden Müşteri",
    "Giden Müşteri Fiyatı",
    "İrsaliye Açıklaması",
    "Ürün Satır Sayısı",
    "Ürün Satır Tutarı Toplamı",
    "Matrah - Satır Toplamı",
]


FULLBOARD_PIVOT_COLUMNS = [
    "Giden Müşteri",
    "Ürün Adı",
    "Açıklama",
    "İrsaliye Açıklaması",
    "Toplam KDV Dahil Birim Fiyat",
    "Toplam Birim Fiyat",
]

DETAIL_DROP_COLUMNS = {
    "ak_gips": [
        "UUID",
        "TCKN/VKN",
        "Para Birimi",
        "Satır No",
        "Satır Tutarı",
        "KDV Oranı",
        "Torba KG",
    ],
    "fullboard": [
        "UUID",
        "TCKN/VKN",
        "Para Birimi",
        "Satır No",
        "Satır Tutarı",
        "KDV Oranı",
        "Torba KG",
        "Alış Fiyatı (Torba)",
        "Ürün Kodu",
    ],
}

SUMMARY_DROP_COLUMNS = {
    "ak_gips": [
        "UUID",
        "Para Birimi",
        "Ürün Satır Sayısı",
        "Matrah - Satır Toplamı",
    ],
    "fullboard": [
        "UUID",
        "Para Birimi",
        "Ürün Satır Sayısı",
        "Matrah - Satır Toplamı",
    ],
}


def normalize_text(value: Any) -> str:
    """Return a lowercase, accent-insensitive string for supplier matching."""
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = text.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def matches_supplier(supplier: Any, keywords: Iterable[str]) -> bool:
    normalized_supplier = normalize_text(supplier)
    compact_supplier = normalized_supplier.replace(" ", "")

    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword in normalized_supplier:
            return True
        if normalized_keyword.replace(" ", "") in compact_supplier:
            return True

    return False


def format_jsonb_for_excel(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def parse_jsonb_list(value: Any) -> List[Any]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value if isinstance(value, list) else [value]


def normalize_code_number(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-5:].zfill(5) if digits else ""


def normalize_despatch_key(value: Any) -> str:
    """Normalize A/F prefixed despatch codes without losing factory identity."""
    text = str(value or "").upper()
    match = re.search(r"\b([AF])\s*[-:]?\s*0*(\d+)\b", text)
    if not match:
        return ""
    prefix, number = match.groups()
    return f"{prefix}-{number[-5:].zfill(5)}"


def collect_despatch_keys(row: Dict[str, Any], prefix: str = "") -> List[str]:
    """Collect unique A/F-prefixed despatch keys from ids and XML documents."""
    expected = f"{prefix.upper()}-" if prefix else ""
    keys = []

    def add_key(value: Any) -> None:
        key = normalize_despatch_key(value)
        if not key:
            return
        if expected and not key.startswith(expected):
            return
        if key not in keys:
            keys.append(key)

    for despatch_id in parse_jsonb_list(row.get("despatch_ids")):
        add_key(despatch_id)

    for doc in parse_jsonb_list(row.get("despatch_documents")):
        if not isinstance(doc, dict):
            continue
        for field in ("despatch_id_short", "despatch_id_full", "description"):
            add_key(doc.get(field))

    return keys


def row_has_factory_prefix(row: Dict[str, Any], prefix: str) -> bool:
    """True when incoming invoice has at least one despatch code for this factory."""
    return bool(collect_despatch_keys(row, prefix))


def format_factory_despatch_ids(row: Dict[str, Any], prefix: str) -> str:
    """Prefer factory-prefixed despatch codes in Excel output."""
    keys = collect_despatch_keys(row, prefix)
    if keys:
        return ", ".join(keys)
    return format_jsonb_for_excel(row.get("despatch_ids"))


def text_or_empty(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def find_text(parent: ET.Element, path: str) -> str:
    return text_or_empty(parent.find(path, NAMESPACES))


def decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def add_vat_to_unit_price(line: Dict[str, Any]) -> Optional[Decimal]:
    unit_price = line.get("Birim Fiyat")
    vat_rate = line.get("KDV Oranı")
    if unit_price is None:
        return None
    if vat_rate is None:
        return unit_price
    return unit_price * (Decimal("1") + (vat_rate / Decimal("100")))


def infer_vat_rate(line_amount: Optional[Decimal], tax_amount: Optional[Decimal]) -> Optional[Decimal]:
    if not line_amount or line_amount == 0 or tax_amount is None:
        return None
    return (tax_amount / line_amount) * Decimal("100")


def infer_bag_kg(line: Dict[str, Any]) -> Optional[int]:
    """Infer bag weight for gypsum products that are priced by ton."""
    product_text = normalize_text(
        " ".join(
            str(line.get(key) or "")
            for key in ("Ürün Kodu", "Ürün Adı", "Açıklama")
        )
    )
    compact = product_text.replace(" ", "").replace("-", "")

    if "saten" in product_text:
        return 25

    if "25kg" in compact:
        return 25

    if "35kg" in compact:
        return 35

    if (
        ("makine" in product_text or "makina" in product_text or "turbo" in product_text)
        and "siva" in product_text
        and "alci" in product_text
    ):
        return 35

    if "perlitli" in product_text and "siva" in product_text:
        return 35

    return None


def parse_invoice_lines(xml_content: Optional[str]) -> List[Dict[str, Any]]:
    if not xml_content:
        return []

    root = ET.fromstring(xml_content)
    lines = []

    for line in root.findall(".//cac:InvoiceLine", NAMESPACES):
        quantity = line.find("cbc:InvoicedQuantity", NAMESPACES)
        price_amount = line.find("cac:Price/cbc:PriceAmount", NAMESPACES)
        line_amount = line.find("cbc:LineExtensionAmount", NAMESPACES)
        tax_amount = line.find(".//cac:TaxSubtotal/cbc:TaxAmount", NAMESPACES)

        product_code = (
            find_text(line, "cac:Item/cac:SellersItemIdentification/cbc:ID")
            or find_text(line, "cac:Item/cac:BuyersItemIdentification/cbc:ID")
            or find_text(line, "cac:Item/cac:ManufacturersItemIdentification/cbc:ID")
        )

        parsed_line_amount = decimal_or_none(text_or_empty(line_amount))
        parsed_tax_amount = decimal_or_none(text_or_empty(tax_amount))
        parsed_vat_rate = decimal_or_none(find_text(line, ".//cac:TaxSubtotal/cac:TaxCategory/cbc:Percent"))
        if parsed_vat_rate is None:
            parsed_vat_rate = infer_vat_rate(parsed_line_amount, parsed_tax_amount)

        line_data = {
            "Satır No": find_text(line, "cbc:ID"),
            "Ürün Kodu": product_code,
            "Ürün Adı": find_text(line, "cac:Item/cbc:Name"),
            "Açıklama": find_text(line, "cac:Item/cbc:Description") or find_text(line, "cbc:Note"),
            "Miktar": decimal_or_none(text_or_empty(quantity)),
            "Birim": quantity.attrib.get("unitCode", "") if quantity is not None else "",
            "Birim Fiyat": decimal_or_none(text_or_empty(price_amount)),
            "Satır Tutarı": parsed_line_amount,
            "KDV Oranı": parsed_vat_rate,
            "KDV Tutarı": parsed_tax_amount,
            "Satır Para Birimi": (
                line_amount.attrib.get("currencyID", "")
                if line_amount is not None
                else price_amount.attrib.get("currencyID", "") if price_amount is not None else ""
            ),
        }
        line_data["KDV Dahil Birim Fiyat"] = add_vat_to_unit_price(line_data)
        line_data["Torba KG"] = infer_bag_kg(line_data)
        line_data["Alış Fiyatı (Torba)"] = None
        lines.append(line_data)

    return lines


def fetch_incoming_invoice_rows() -> List[Dict[str, Any]]:
    query = """
        SELECT
            i.invoice_id,
            i.uuid,
            i.issue_date,
            i.supplier,
            i.supplier_tckn_vkn,
            i.amount,
            i.total_vat_base,
            i.currency,
            COALESCE(i.despatch_ids_override, i.despatch_ids) AS despatch_ids,
            c.despatch_documents,
            c.xml_content
        FROM incoming_invoices i
        LEFT JOIN incoming_invoice_xml_cache c ON c.uuid = i.uuid
        ORDER BY i.issue_date ASC, i.invoice_id ASC
    """
    return db.query(query)


def fetch_outgoing_index() -> Dict[str, Dict[str, Any]]:
    rows = db.query(
        """
        SELECT invoice_no, firm_name, total_tl, taxable_amount, description,
               COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes
        FROM outgoing_invoices
        """
    )

    index = {}
    for row in rows:
        codes = parse_jsonb_list(row.get("irsaliye_codes"))
        code_count = len(codes) or 1
        total_tl = decimal_or_none(row.get("total_tl")) or Decimal("0")
        per_despatch_total = total_tl / Decimal(code_count)

        for code in codes:
            key = normalize_despatch_key(code)
            if not key:
                continue
            index[key] = {
                "customer": row.get("firm_name") or "",
                "price": per_despatch_total,
                "description": row.get("description") or "",
                "invoice_no": row.get("invoice_no") or "",
            }

    return index


def summarize_despatch_context(row: Dict[str, Any], outgoing_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    despatch_docs = parse_jsonb_list(row.get("despatch_documents"))
    despatch_keys = collect_despatch_keys(row)
    incoming_descriptions = {}
    customers = []
    descriptions = []
    total_customer_price = Decimal("0")

    for doc in despatch_docs:
        if not isinstance(doc, dict):
            continue
        key = (
            normalize_despatch_key(doc.get("despatch_id_short"))
            or normalize_despatch_key(doc.get("despatch_id_full"))
            or normalize_despatch_key(doc.get("description"))
        )
        description = doc.get("description")
        if key and description:
            incoming_descriptions[key] = str(description)

    for key in despatch_keys:
        outgoing = outgoing_index.get(key)
        if outgoing:
            if outgoing["customer"] and outgoing["customer"] not in customers:
                customers.append(outgoing["customer"])
            total_customer_price += outgoing["price"]
            if outgoing["description"] and outgoing["description"] not in descriptions:
                descriptions.append(outgoing["description"])

        incoming_description = incoming_descriptions.get(key)
        if incoming_description and incoming_description not in descriptions:
            descriptions.append(incoming_description)

    return {
        "Giden Müşteri": ", ".join(customers),
        "Giden Müşteri Fiyatı": total_customer_price if total_customer_price else None,
        "İrsaliye Açıklaması": " | ".join(descriptions),
    }


def invoice_base(row: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    return {
        "Düzenleme Tarihi": row.get("issue_date"),
        "Tedarikçi": row.get("supplier"),
        "Fatura ID": row.get("invoice_id"),
        "UUID": row.get("uuid"),
        "TCKN/VKN": row.get("supplier_tckn_vkn"),
        "Fatura Tutarı": row.get("amount"),
        "KDV Matrahı": row.get("total_vat_base"),
        "Para Birimi": row.get("currency"),
        "İrsaliye Kodları": format_factory_despatch_ids(row, prefix),
    }


def build_report_frames(
    rows: List[Dict[str, Any]],
    keywords: Iterable[str],
    prefix: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows = []
    summary_rows = []
    outgoing_index = fetch_outgoing_index()

    for row in rows:
        if not matches_supplier(row.get("supplier"), keywords):
            continue
        if not row_has_factory_prefix(row, prefix):
            continue

        base = invoice_base(row, prefix)
        despatch_context = summarize_despatch_context(row, outgoing_index)
        base.update(despatch_context)
        xml_status = "OK"
        try:
            lines = parse_invoice_lines(row.get("xml_content"))
            if not row.get("xml_content"):
                xml_status = "XML yok"
            elif not lines:
                xml_status = "Ürün satırı yok"
        except ET.ParseError as exc:
            lines = []
            xml_status = f"XML parse hatası: {exc}"

        if lines:
            for line in lines:
                detail_rows.append({**base, **line, "XML Durumu": xml_status})
        else:
            detail_rows.append({**base, "XML Durumu": xml_status})

        line_total = sum((line.get("Satır Tutarı") or Decimal("0")) for line in lines)
        vat_base = decimal_or_none(row.get("total_vat_base")) or Decimal("0")
        summary_rows.append(
            {
                "Düzenleme Tarihi": row.get("issue_date"),
                "Tedarikçi": row.get("supplier"),
                "Fatura ID": row.get("invoice_id"),
                "UUID": row.get("uuid"),
                "Fatura Tutarı": row.get("amount"),
                "KDV Matrahı": row.get("total_vat_base"),
                "Para Birimi": row.get("currency"),
                "İrsaliye Kodları": format_factory_despatch_ids(row, prefix),
                "Giden Müşteri": despatch_context["Giden Müşteri"],
                "Giden Müşteri Fiyatı": despatch_context["Giden Müşteri Fiyatı"],
                "İrsaliye Açıklaması": despatch_context["İrsaliye Açıklaması"],
                "Ürün Satır Sayısı": len(lines),
                "Ürün Satır Tutarı Toplamı": line_total if lines else None,
                "Matrah - Satır Toplamı": vat_base - line_total if lines else None,
                "XML Durumu": xml_status,
            }
        )

    detail_df = pd.DataFrame(detail_rows, columns=DETAIL_COLUMNS)
    summary_df = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)

    for df in (detail_df, summary_df):
        for col in df.columns:
            df[col] = df[col].map(decimal_to_float)
        if "Düzenleme Tarihi" in df.columns and not df.empty:
            df["Düzenleme Tarihi"] = pd.to_datetime(df["Düzenleme Tarihi"], errors="coerce").dt.tz_localize(None)

    return detail_df, summary_df


def build_fullboard_pivot_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df.empty:
        return pd.DataFrame(columns=FULLBOARD_PIVOT_COLUMNS)

    source = detail_df.copy()
    for column in FULLBOARD_PIVOT_COLUMNS[:4]:
        source[column] = source[column].fillna("").astype(str)

    grouped = (
        source.groupby(FULLBOARD_PIVOT_COLUMNS[:4], dropna=False, as_index=False)
        .agg(
            {
                "KDV Dahil Birim Fiyat": "sum",
                "Birim Fiyat": "sum",
            }
        )
        .rename(
            columns={
                "KDV Dahil Birim Fiyat": "Toplam KDV Dahil Birim Fiyat",
                "Birim Fiyat": "Toplam Birim Fiyat",
            }
        )
    )

    grouped = grouped.sort_values(
        ["İrsaliye Açıklaması", "Açıklama", "Ürün Adı", "Giden Müşteri"],
        kind="stable",
    )
    return grouped[FULLBOARD_PIVOT_COLUMNS]


def write_supplier_excel(
    detail_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    output_file: Path,
    supplier_code: str,
) -> None:
    detail_export = detail_df.copy()
    if {"Alış Fiyatı (Torba)", "Birim Fiyat", "Torba KG"}.issubset(detail_export.columns):
        detail_export["Alış Fiyatı (Torba)"] = detail_export.apply(
            lambda row: (
                (row["Birim Fiyat"] * row["Torba KG"]) / 1000
                if pd.notna(row.get("Birim Fiyat")) and pd.notna(row.get("Torba KG"))
                else None
            ),
            axis=1,
        )

    summary_export = summary_df.copy()
    detail_export = detail_export.drop(columns=DETAIL_DROP_COLUMNS.get(supplier_code, []), errors="ignore")
    summary_export = summary_export.drop(columns=SUMMARY_DROP_COLUMNS.get(supplier_code, []), errors="ignore")

    with pd.ExcelWriter(output_file, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        detail_export.to_excel(writer, index=False, sheet_name="Fatura Detayları")
        summary_export.to_excel(writer, index=False, sheet_name="Fatura Özeti")
        pivot_df = None
        if supplier_code == "fullboard":
            pivot_df = build_fullboard_pivot_summary(detail_df)
            pivot_df.to_excel(writer, index=False, sheet_name="Pivot Özet")

        workbook = writer.book
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "fg_color": "#2F5496",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        )
        currency_fmt = workbook.add_format({"num_format": '#,##0.00 "₺"', "border": 1})
        number_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd", "border": 1})

        sheets = [("Fatura Detayları", detail_export), ("Fatura Özeti", summary_export)]
        if pivot_df is not None:
            sheets.append(("Pivot Özet", pivot_df))

        for sheet_name, df in sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            price_col_idx = df.columns.get_loc("Birim Fiyat") if "Birim Fiyat" in df.columns else None

            for col_num, column in enumerate(df.columns):
                worksheet.write(0, col_num, column, header_fmt)
                width = min(max(len(str(column)) + 2, 12), 45)
                if not df.empty:
                    sample_width = df[column].astype(str).map(len).max()
                    width = min(max(width, int(sample_width) + 2), 45)
                worksheet.set_column(col_num, col_num, width)

            for row_num in range(1, len(df) + 1):
                for col_num, column in enumerate(df.columns):
                    value = df.iloc[row_num - 1][column]
                    if pd.isna(value):
                        value = ""
                    if column == "Alış Fiyatı (Torba)" and price_col_idx is not None and "Torba KG" in df.columns:
                        bag_kg = df.iloc[row_num - 1].get("Torba KG")
                        if pd.isna(bag_kg) or bag_kg == "":
                            worksheet.write(row_num, col_num, "", currency_fmt)
                        else:
                            price_cell = xl_rowcol_to_cell(row_num, price_col_idx)
                            worksheet.write_formula(row_num, col_num, f"=({price_cell}*{int(bag_kg)})/1000", currency_fmt)
                    elif column in {
                        "Fatura Tutarı",
                        "KDV Matrahı",
                        "Giden Müşteri Fiyatı",
                        "Alış Fiyatı (Torba)",
                        "Birim Fiyat",
                        "KDV Dahil Birim Fiyat",
                        "Satır Tutarı",
                        "KDV Tutarı",
                        "Ürün Satır Tutarı Toplamı",
                        "Matrah - Satır Toplamı",
                        "Toplam KDV Dahil Birim Fiyat",
                        "Toplam Birim Fiyat",
                    }:
                        worksheet.write(row_num, col_num, value, currency_fmt)
                    elif column in {"Miktar", "KDV Oranı", "Torba KG"}:
                        worksheet.write(row_num, col_num, value, number_fmt)
                    elif column == "Düzenleme Tarihi" and value != "":
                        worksheet.write_datetime(row_num, col_num, value.to_pydatetime(), date_fmt)
                    else:
                        worksheet.write(row_num, col_num, value)


def export_supplier_reports(output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = fetch_incoming_invoice_rows()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    created_files = []

    for supplier in SUPPLIER_CONFIG:
        cleanup_old_reports(output_dir, [f"{supplier['filename']}_*.xlsx"])
        detail_df, summary_df = build_report_frames(rows, supplier["keywords"], supplier["prefix"])
        output_file = output_dir / f"{supplier['filename']}_{timestamp}.xlsx"
        write_supplier_excel(detail_df, summary_df, output_file, supplier["code"])
        created_files.append(output_file)
        print(
            f"✅ {supplier['display']}: {len(summary_df)} fatura, "
            f"{len(detail_df)} detay satırı -> {output_file}"
        )

    return created_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AK GIPS ve FULLBOARD gelen faturaları için ürün/adet/birim fiyat detay Excel raporu üretir."
    )
    parser.add_argument(
        "--output-dir",
        default="kayıtlar",
        help="Excel raporlarının yazılacağı klasör (varsayılan: kayıtlar).",
    )
    args = parser.parse_args()

    print()
    print("=" * 80)
    print("  TEDARIKCI FATURA URUN DETAY EXCEL RAPORU")
    print("=" * 80)
    print()

    try:
        files = export_supplier_reports(Path(args.output_dir))
    finally:
        db.close_persistent_connection()

    print()
    print("Oluşturulan dosyalar:")
    for file_path in files:
        print(f"  - {file_path}")
    print()


if __name__ == "__main__":
    main()
