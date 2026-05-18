#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Match incoming e-despatches from Isbasi API output to outgoing invoices."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from backend.core.db import db
from backend.core.normalize import normalize_incoming_despatch
from report_cleanup import cleanup_old_reports


def parse_json_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def normalize_outgoing_code(value: Any) -> str:
    match = re.search(r"\b([AFT])\s*[-:/]?\s*0*(\d+)\b", str(value or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    prefix, digits = match.groups()
    return f"{prefix.upper()}-{digits[-5:].zfill(5)}"


def latest_source_json() -> Path:
    candidates = sorted(
        (PROJECT_ROOT / "data" / "logs").glob("incoming_despatch_probe_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    candidates = [path for path in candidates if "_fail_" not in path.name]
    if not candidates:
        raise SystemExit("Gelen e-irsaliye JSON bulunamadı. Önce scripts/probe_incoming_despatches.py çalıştırın.")
    return candidates[0]


def load_despatch_rows(source_json: Path) -> List[Dict[str, Any]]:
    payload = json.loads(source_json.read_text(encoding="utf-8"))
    rows = payload.get("raw_rows", [])
    if not isinstance(rows, list):
        raise SystemExit(f"Geçersiz kaynak JSON: {source_json}")
    return [row for row in rows if isinstance(row, dict)]


def fetch_outgoing_rows() -> List[Dict[str, Any]]:
    return db.query(
        """
        SELECT id, invoice_no, issue_date, firm_name,
               total_tl, taxable_amount, description,
               COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes
        FROM outgoing_invoices
        ORDER BY issue_date DESC, invoice_no DESC
        """
    )


def build_outgoing_index(outgoing_rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}
    for row in outgoing_rows:
        codes = [normalize_outgoing_code(code) for code in parse_json_list(row.get("irsaliye_codes"))]
        codes = [code for code in dict.fromkeys(codes) if code]
        row["_normalized_codes"] = codes
        row["_code_count"] = len(codes)
        for code in codes:
            index.setdefault(code, []).append(row)
    return index


def format_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def despatch_description(row: Dict[str, Any]) -> str:
    for key in ("description", "extraDescription", "etradeDescription", "message"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def clean_extracted_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.strip(" -:;,.")


def normalize_plate(value: Any) -> str:
    text = clean_extracted_text(value).upper()
    return re.sub(r"\s+", " ", text)


def extract_vehicle_and_destination(description: str, supplier: str = "") -> Dict[str, str]:
    text = str(description or "")
    supplier_upper = str(supplier or "").upper()
    result = {"Plaka": "", "Sevk Yeri": ""}

    if not text:
        return result

    plate_patterns = []
    destination_patterns = []

    if "FULL" in supplier_upper:
        plate_patterns.extend(
            [
                r"Not:\s*(\d{2}\s+[A-ZÇĞİÖŞÜ]{1,3}\s+\d{2,5})\s*-\s*KEND[İI]\s+ARACI",
                r"\b(\d{2}\s+[A-ZÇĞİÖŞÜ]{1,3}\s+\d{2,5})\s*-\s*KEND[İI]\s+ARACI",
            ]
        )
        destination_patterns.extend(
            [
                r"Sevk\s+Adresi\s*:\s*\[[^\]]*?:\s*\]\s*([^\n\r]+?)(?:\s+-\s+|$)",
                r"Sevk\s+Adresi\s*:\s*\[[^\]]*-\s*([^:\]]+?)\s*:",
            ]
        )
    else:
        plate_patterns.append(r"\b(\d{2}\s+[A-ZÇĞİÖŞÜ]{1,3}\s+\d{2,5})\s+PLAKAL[İIıi]\s+ARA[ÇC]")
        destination_patterns.append(r"\b[İI]LE\s+(.+?)\s+ADRES[İI]NE\s+SEVK\s+ED[İI]LM[İIŞ]T[İI]R")

    # Fallbacks cover occasional supplier text differences.
    plate_patterns.append(r"\b(\d{2}\s+[A-ZÇĞİÖŞÜ]{1,3}\s+\d{2,5})\b")
    destination_patterns.append(r"\b[İI]LE\s+(.+?)\s+ADRES[İI]NE\s+SEVK")

    for pattern in plate_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            result["Plaka"] = normalize_plate(match.group(1))
            break

    for pattern in destination_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            result["Sevk Yeri"] = clean_extracted_text(match.group(1)).upper()
            break

    return result


def build_despatch_export_rows(despatch_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    export_rows = []
    for row in despatch_rows:
        dispatch_id = str(row.get("dispatchId") or "")
        supplier = str(row.get("supplier") or "")
        prefixed_code = normalize_incoming_despatch(dispatch_id, supplier) or ""
        route_info = extract_vehicle_and_destination(despatch_description(row), supplier)
        export_rows.append(
            {
                "İrsaliye No": dispatch_id,
                "Prefixli Kod": prefixed_code,
                "Tedarikçi": supplier,
                "Tip": row.get("type", ""),
                "Tip Açıklaması": row.get("typeDesc", ""),
                "İrsaliye Tipi": row.get("dispatchType", ""),
                "İrsaliye Tarihi": format_date(row.get("issueDate")),
                "Para Birimi": row.get("currency", ""),
                "Plaka": route_info["Plaka"],
                "Sevk Yeri": route_info["Sevk Yeri"],
                "İşlenebilir": row.get("isProcessable", ""),
                "Seçilemez": row.get("notSelectable", ""),
                "Mesaj": row.get("message", ""),
                "Uygulama Yanıtı": row.get("appRespstatus", ""),
                "Uygulama Yanıt Kodu": row.get("appRespstatusCode", ""),
                "Bağlantı Durumu": row.get("connectStatusDescription", ""),
                "Bağlantı Durum Kodu": row.get("connectStatusCode", ""),
                "İade Edilebilir": row.get("returnable", ""),
                "İşbaşı ID": row.get("id", ""),
                "Görüntülendi": row.get("isViewed", ""),
            }
        )
    return export_rows


def build_match_rows(despatch_rows: List[Dict[str, Any]], outgoing_index: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    results = []
    for row in despatch_rows:
        dispatch_id = str(row.get("dispatchId") or "")
        supplier = str(row.get("supplier") or "")
        prefixed_code = normalize_incoming_despatch(dispatch_id, supplier) or ""
        matches = outgoing_index.get(prefixed_code, []) if prefixed_code else []
        route_info = extract_vehicle_and_destination(despatch_description(row), supplier)

        base = {
            "İrsaliye Tarihi": format_date(row.get("issueDate")),
            "Gelen İrsaliye No": dispatch_id,
            "Prefixli Kod": prefixed_code,
            "Tedarikçi": supplier,
            "Plaka": route_info["Plaka"],
            "Sevk Yeri": route_info["Sevk Yeri"],
        }

        if not prefixed_code:
            results.append(
                {
                    **base,
                    "Giden Fatura Tarihi": "",
                    "Giden Fatura No": "",
                    "Giden Firma": "",
                    "Giden Fatura Tutarı": 0,
                    "Durum": "Kod üretilemedi",
                }
            )
            continue

        if not matches:
            results.append(
                {
                    **base,
                    "Giden Fatura Tarihi": "",
                    "Giden Fatura No": "",
                    "Giden Firma": "",
                    "Giden Fatura Tutarı": 0,
                    "Durum": "Karşılıksız",
                }
            )
            continue

        match_status = "Eşleşti" if len(matches) == 1 else "Çoklu eşleşme"
        for out_row in matches:
            out_total = float(out_row.get("total_tl") or 0)
            code_count = int(out_row.get("_code_count") or 1)
            results.append(
                {
                    **base,
                    "Giden Fatura Tarihi": format_date(out_row.get("issue_date")),
                    "Giden Fatura No": out_row.get("invoice_no", ""),
                    "Giden Firma": out_row.get("firm_name", ""),
                    "Giden Fatura Tutarı": round(out_total, 2),
                    "Durum": match_status,
                }
            )

    return results


def write_excel(match_df: pd.DataFrame, despatch_df: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_reports(output_dir, ["Irsaliye_Giden_Fatura_Eslestirme_*.xlsx"])
    output_file = output_dir / f"Irsaliye_Giden_Fatura_Eslestirme_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        match_df.to_excel(writer, index=False, sheet_name="Eşleştirme")
        despatch_df.to_excel(writer, index=False, sheet_name="Gelen İrsaliyeler")

        workbook = writer.book
        header_fmt = workbook.add_format(
            {"bold": True, "fg_color": "#2F5496", "font_color": "white", "border": 1, "align": "center"}
        )
        currency_fmt = workbook.add_format({"num_format": "#,##0.00 ₺", "border": 1})
        matched_fmt = workbook.add_format({"bg_color": "#C6EFCE", "border": 1, "bold": True})
        missing_fmt = workbook.add_format({"bg_color": "#FFC7CE", "border": 1, "bold": True})
        warning_fmt = workbook.add_format({"bg_color": "#FFEB9C", "border": 1, "bold": True})

        for sheet_name, df in [("Eşleştirme", match_df), ("Gelen İrsaliyeler", despatch_df)]:
            worksheet = writer.sheets[sheet_name]
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                max_len = max([len(str(value))] + [len(str(item)) for item in df[value].head(200).tolist()])
                worksheet.set_column(col_num, col_num, min(max_len + 2, 45))

        match_ws = writer.sheets["Eşleştirme"]
        for row_num in range(1, len(match_df) + 1):
            row = match_df.iloc[row_num - 1]
            for column in ["Giden Fatura Tutarı"]:
                if column in match_df.columns:
                    match_ws.write(row_num, match_df.columns.get_loc(column), row[column], currency_fmt)
            status = row["Durum"]
            if status == "Eşleşti":
                fmt = matched_fmt
            elif status == "Karşılıksız":
                fmt = missing_fmt
            else:
                fmt = warning_fmt
            match_ws.write(row_num, match_df.columns.get_loc("Durum"), status, fmt)

        last = len(match_df) + 3
        stat_fmt = workbook.add_format({"bold": True, "fg_color": "#2F5496", "font_color": "white", "border": 1})
        match_ws.write(last, 0, "İSTATİSTİKLER", stat_fmt)
        for offset, status in enumerate(["Eşleşti", "Çoklu eşleşme", "Karşılıksız", "Kod üretilemedi"], start=1):
            count = len(match_df[match_df["Durum"] == status])
            fmt = matched_fmt if status == "Eşleşti" else missing_fmt if status == "Karşılıksız" else warning_fmt
            match_ws.write(last + offset, 0, f"{status}: {count}", fmt)
        match_ws.write(last + 5, 0, f"Toplam eşleştirme satırı: {len(match_df)}", stat_fmt)
        match_ws.write(last + 6, 0, f"Toplam gelen irsaliye: {len(despatch_df)}", stat_fmt)

    return output_file


def generate_match_report(source_json: Path, output_dir: Path, *, print_summary: bool = True) -> Path:
    source_json = Path(source_json)
    despatch_rows = load_despatch_rows(source_json)
    outgoing_rows = fetch_outgoing_rows()
    outgoing_index = build_outgoing_index(outgoing_rows)

    despatch_df = pd.DataFrame(build_despatch_export_rows(despatch_rows))
    match_df = pd.DataFrame(build_match_rows(despatch_rows, outgoing_index))
    output_file = write_excel(match_df, despatch_df, output_dir)

    if print_summary:
        print()
        print("=" * 70)
        print("  GELEN E-IRSALIYE -> GIDEN FATURA ESLESTIRME")
        print("=" * 70)
        print(f"  Kaynak JSON: {source_json}")
        print(f"  Gelen irsaliye: {len(despatch_df)}")
        print(f"  Eslesen: {len(match_df[match_df['Durum'] == 'Eşleşti'])}")
        print(f"  Coklu eslesme: {len(match_df[match_df['Durum'] == 'Çoklu eşleşme'])}")
        print(f"  Karsiliksiz: {len(match_df[match_df['Durum'] == 'Karşılıksız'])}")
        print(f"  Kod uretilemedi: {len(match_df[match_df['Durum'] == 'Kod üretilemedi'])}")
        print(f"  Rapor: {output_file}")
        print("=" * 70)
        print()

    return output_file


def main() -> Path:
    parser = argparse.ArgumentParser(description="Gelen e-irsaliyeleri giden faturalarla A/F/T kodlarına göre eşleştirir.")
    parser.add_argument("--source-json", default="", help="incoming_despatch_probe_*.json dosyası. Boşsa en güncel dosya kullanılır.")
    parser.add_argument("--output-dir", default="kayıtlar")
    args = parser.parse_args()

    source_json = Path(args.source_json) if args.source_json else latest_source_json()
    return generate_match_report(source_json, Path(args.output_dir), print_summary=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        db.close_persistent_connection()
