#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dry-run/import workflow for customer check collections.

Default mode is safe: it reads the Excel/CSV file, matches firms and writes a
report. It will not post payments to İşbaşı until a real customer collection
endpoint is added to the endpoint matrix.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError
from backend.core.check_pool import (
    CheckPoolRepository,
    export_check_pool_report,
    extract_checks_from_path,
    stored_to_customer_check,
)
from backend.core.payment_import import (
    PaymentAuditStore,
    build_dry_run,
    export_dry_run_report,
    firm_cards_from_api,
    load_firms_from_json,
    read_customer_checks,
)

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel/CSV/PDF/gorsel musteri cek aktarimi dry-run araci")
    parser.add_argument("input_files", nargs="+", help="Cek dosyasi veya dosyalari; klasor de verilebilir")
    parser.add_argument("--sheet", help="Excel sheet adi veya index'i", default=None)
    parser.add_argument("--output-dir", default="kayıtlar", help="Rapor cikti dizini")
    parser.add_argument("--firms-json", help="API yerine yerel firma JSON dosyasindan eslestir")
    parser.add_argument("--skip-audit-db", action="store_true", help="DB idempotency kontrolunu atla")
    parser.add_argument("--store-check-pool", action="store_true", help="Okunan cekleri checks/check_import_* tablolarina yaz")
    parser.add_argument("--execute", action="store_true", help="Gercek yazim denemesi yap")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def expand_input_paths(paths: Iterable[str]) -> List[Path]:
    supported = {".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}
    expanded: List[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            expanded.extend(
                sorted(
                    child
                    for child in path.iterdir()
                    if child.is_file() and child.suffix.lower() in supported and not child.name.startswith("~$")
                )
            )
        else:
            expanded.append(path)

    missing = [str(path) for path in expanded if not path.exists()]
    if missing:
        raise FileNotFoundError("Bulunamayan dosya(lar): " + ", ".join(missing))
    if not expanded:
        raise FileNotFoundError("Okunacak Excel/CSV dosyasi bulunamadi")
    return expanded


def read_checks_from_inputs(input_paths: Iterable[Path], sheet_name: Optional[str] = None):
    checks = []
    import_results = []
    for input_path in input_paths:
        suffix = input_path.suffix.lower()
        if suffix in {".xlsx", ".xls", ".csv"}:
            file_checks = read_customer_checks(input_path, sheet_name=sheet_name)
            for check in file_checks:
                check.raw["_source_file"] = str(input_path)
            checks.extend(file_checks)

        pool_result = extract_checks_from_path(input_path)
        import_results.append(pool_result)
        if suffix not in {".xlsx", ".xls", ".csv"}:
            for record in pool_result.records:
                check = stored_to_customer_check(record)
                check.raw["_source_file"] = str(input_path)
                checks.append(check)
    return checks, import_results


def load_firms(args: argparse.Namespace):
    if args.firms_json:
        return load_firms_from_json(Path(args.firms_json))

    client = IsbasiApiClient()
    rows = client.list_firms()
    return firm_cards_from_api(rows)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")

    input_paths = expand_input_paths(args.input_files)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    checks, import_results = read_checks_from_inputs(input_paths, sheet_name=args.sheet)
    firms = load_firms(args)

    existing_keys = set()
    audit = None
    if not args.skip_audit_db:
        audit = PaymentAuditStore()
        audit.ensure_schema()
        existing_keys = audit.existing_keys(check.idempotency_key for check in checks)

    report = build_dry_run(checks, firms, existing_keys=existing_keys)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"Musteri_Cek_Dry_Run_{timestamp}.xlsx"
    export_dry_run_report(report, report_path)
    pool_records = [record for result in import_results for record in result.records]
    pool_report_path = output_dir / f"Cek_Havuzu_Raporu_{timestamp}.xlsx"
    export_check_pool_report(pool_records, pool_report_path)

    if args.store_check_pool:
        repository = CheckPoolRepository()
        store_counts = {"inserted_count": 0, "skipped_duplicate_count": 0, "error_count": 0}
        for result in import_results:
            counts = repository.import_result(result)
            for key, value in counts.items():
                store_counts[key] += value
    else:
        store_counts = {}

    print(f"Okunan dosya sayısı: {len(input_paths)}")
    print(f"Çek havuzu kayıt sayısı: {len(pool_records)}")
    print(f"Çek havuzu parser uyarı sayısı: {sum(len(result.warnings) for result in import_results)}")
    print(f"Çek havuzu parser hata sayısı: {sum(len(result.errors) for result in import_results)}")
    if store_counts:
        print("Çek havuzu DB yazım özeti:", json.dumps(store_counts, ensure_ascii=False))
    print(json.dumps(report.summary, ensure_ascii=False, indent=2))
    print(f"Dry-run raporu: {report_path}")
    print(f"Çek havuzu raporu: {pool_report_path}")
    print("Odeme endpoint durumu:", json.dumps(report.payment_endpoint, ensure_ascii=False))

    if args.execute:
        if not report.payment_endpoint.get("verified"):
            raise IsbasiAPIError(str(report.payment_endpoint.get("reason")))
        raise IsbasiAPIError("Execute modu henuz kapali: odeme endpoint payload mapping'i eklenmeli.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.error("%s", exc)
        raise SystemExit(1)
