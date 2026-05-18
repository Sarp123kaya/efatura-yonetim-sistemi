#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export documented customer account activity from İşbaşı.

Swagger does not expose a standalone customer check/collection list endpoint.
This script reads the customer card and the documented sales invoice list fields
that include payment status, payment date, remaining totals and safe/bank names.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_client import IsbasiApiClient

logger = logging.getLogger(__name__)


PAYMENT_COLUMNS = [
    "id",
    "date",
    "invoiceNumber",
    "documentNumber",
    "firmName",
    "firmCode",
    "firmVknNo",
    "totalTL",
    "total",
    "remainingTotal",
    "remainingTotalTL",
    "currency",
    "paymentDate",
    "paymentDateStatus",
    "paymentDateStatusDescription",
    "paymentStatus",
    "safeOrBankName",
    "caseOrBankName",
    "documentType",
    "invoiceTypeName",
    "description",
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="İşbaşı müşteri kartı ve ödeme alanlı satış hareketleri export")
    parser.add_argument("--firm-id", help="İşbaşı firma/cari ID")
    parser.add_argument("--tax-id", help="VKN/TCKN ile müşteri bul")
    parser.add_argument("--firm-name", help="Unvan/ad ile müşteri bul")
    parser.add_argument("--start-date", default="", help="Fatura başlangıç tarihi, örn 2026-01-01T00:00:00")
    parser.add_argument("--end-date", default="", help="Fatura bitiş tarihi, örn 2026-12-31T23:59:59")
    parser.add_argument("--allow-full-scan", action="store_true", help="Filtre tutmazsa satış fatura listesini çekip yerelde süz")
    parser.add_argument("--output-dir", default="kayıtlar")
    parser.add_argument("--json", action="store_true", help="Excel yerine JSON yaz")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def pick_firm(client: IsbasiApiClient, args: argparse.Namespace) -> Dict[str, Any]:
    if args.firm_id:
        return client.get_firm(args.firm_id)

    filters = [{"columnName": "isActive", "operator": "IsEqualTo", "value": True}]
    if args.tax_id:
        filters.append({"columnName": "vknTckn", "operator": "IsEqualTo", "value": args.tax_id})
    elif args.firm_name:
        filters.append({"columnName": "name", "operator": "Contains", "value": args.firm_name})
    else:
        raise ValueError("--firm-id, --tax-id veya --firm-name gerekli")

    rows = client.list_firms(filters=filters, page_size=20, max_pages=3)
    if not rows:
        raise ValueError("Müşteri bulunamadı")
    if len(rows) > 1 and not args.tax_id:
        names = ", ".join(str(row.get("name") or row.get("displayName") or row.get("id")) for row in rows[:5])
        raise ValueError(f"Birden fazla müşteri adayı var; --firm-id veya --tax-id kullanın: {names}")
    return rows[0]


def flatten_payment_row(row: Dict[str, Any]) -> Dict[str, Any]:
    firm = row.get("firm") if isinstance(row.get("firm"), dict) else {}
    flattened = {key: row.get(key, "") for key in PAYMENT_COLUMNS}
    flattened["firmId"] = firm.get("firmId") or row.get("firmId") or ""
    flattened["firmName"] = flattened["firmName"] or firm.get("name") or firm.get("displayName") or ""
    flattened["firmCode"] = flattened["firmCode"] or firm.get("firmCode") or ""
    return flattened


def export_snapshot(snapshot: Dict[str, Any], output_dir: Path, as_json: bool = False) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    firm = snapshot.get("firm") or {}
    safe_name = str(firm.get("code") or firm.get("taxOrPersonalId") or firm.get("id") or "customer").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if as_json:
        path = output_dir / f"Musteri_Hareketleri_{safe_name}_{timestamp}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    path = output_dir / f"Musteri_Hareketleri_{safe_name}_{timestamp}.xlsx"
    activity = [flatten_payment_row(row) for row in snapshot.get("sales_activity") or []]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([firm]).to_excel(writer, sheet_name="Musteri", index=False)
        pd.DataFrame(activity).to_excel(writer, sheet_name="Fatura_Odeme_Alanlari", index=False)
        pd.DataFrame(
            [
                {
                    "not": (
                        "Swagger ayrı müşteri çek/tahsilat listesi vermiyor. Bu sayfa satış faturası "
                        "listesindeki paymentDate/paymentStatus/remainingTotal/safeOrBankName alanlarından üretilmiştir."
                    )
                }
            ]
        ).to_excel(writer, sheet_name="Not", index=False)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    client = IsbasiApiClient()
    firm = pick_firm(client, args)
    firm_id = str(firm.get("id") or firm.get("firmId") or args.firm_id or "")
    if not firm_id:
        raise ValueError("Müşteri bulundu ama firm id dönmedi")

    snapshot = client.get_customer_account_snapshot(
        firm_id,
        start_date=args.start_date,
        end_date=args.end_date,
        allow_full_scan=args.allow_full_scan,
    )
    path = export_snapshot(snapshot, output_dir, as_json=args.json)
    print(f"Müşteri: {snapshot['firm'].get('name') or snapshot['firm'].get('displayName')}")
    print(f"Satış/fatura ödeme alanı satırı: {len(snapshot.get('sales_activity') or [])}")
    print(f"Çıktı: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.error("%s", exc)
        raise SystemExit(1)
