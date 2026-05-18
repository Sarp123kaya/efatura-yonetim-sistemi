#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a consolidated check pool report with İşbaşı matching/comparison."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.check_pool import (  # noqa: E402
    compare_check_pool_with_isbasi,
    export_check_pool_report,
    extract_checks_from_paths,
    flatten_import_results,
    stored_to_customer_check,
    transfer_candidate_records,
)
from backend.core.isbasi_client import IsbasiApiClient  # noqa: E402
from backend.core.payment_import import firm_cards_from_api, load_firms_from_json, match_check_to_firm  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cek havuzu ve Isbasi karsilastirma raporu")
    parser.add_argument("input_files", nargs="+", help="PDF/Excel/CSV/TXT/gorsel dosyalari veya klasor")
    parser.add_argument("--output-dir", default="kayıtlar", help="Rapor cikti dizini")
    parser.add_argument("--firms-json", help="API yerine yerel firma JSON dosyasindan eslestir")
    parser.add_argument("--skip-isbasi-activity", action="store_true", help="Sadece cari eslestir, Isbasi fatura/odeme alanlarini cekme")
    parser.add_argument("--allow-full-scan", action="store_true", help="Filtreler sonuc dondurmezse fatura listesini yerelde filtrele")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def load_firms(args: argparse.Namespace):
    if args.firms_json:
        return load_firms_from_json(Path(args.firms_json))
    client = IsbasiApiClient()
    rows = client.list_firms()
    return firm_cards_from_api(rows)


def load_isbasi_activity(records, firms, allow_full_scan: bool) -> Dict[str, List[dict]]:
    client = IsbasiApiClient()
    activity_by_firm_id: Dict[str, List[dict]] = {}
    for record in records:
        match = match_check_to_firm(stored_to_customer_check(record), firms)
        if match.status != "matched" or not match.firm or match.firm.id in activity_by_firm_id:
            continue
        rows = client.list_customer_sales_activity(
            firm_id=match.firm.id,
            firm_code=match.firm.code,
            tax_id=match.firm.tax_id,
            firm_name=match.firm.name or match.firm.display_name,
            allow_full_scan=allow_full_scan,
        )
        activity_by_firm_id[match.firm.id] = rows
    return activity_by_firm_id


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")

    results = extract_checks_from_paths(Path(raw) for raw in args.input_files)
    records = flatten_import_results(results)
    firms = load_firms(args)
    activity_by_firm_id = {} if args.skip_isbasi_activity else load_isbasi_activity(records, firms, args.allow_full_scan)
    comparisons = compare_check_pool_with_isbasi(records, firms, activity_by_firm_id)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"Cek_Havuzu_Isbasi_Karsilastirma_{timestamp}.xlsx"
    export_check_pool_report(records, report_path, comparisons=comparisons)

    summary = {
        "source_file_count": len(results),
        "check_count": len(records),
        "parser_warning_count": sum(len(result.warnings) for result in results),
        "parser_error_count": sum(len(result.errors) for result in results),
        "matched_customer_count": sum(1 for item in comparisons if item.match.status == "matched"),
        "missing_in_isbasi_count": sum(1 for item in comparisons if item.isbasi_status == "missing_in_isbasi"),
        "transfer_candidate_count": len(transfer_candidate_records(comparisons)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Karşılaştırma raporu: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.error("%s", exc)
        raise SystemExit(1)
