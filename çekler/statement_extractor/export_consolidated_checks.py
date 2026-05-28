from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.consolidated_report import build_default_consolidated_output_path, write_consolidated_check_report
from statement_extractor.src.postgres_repository import PostgresCheckRepository


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PostgreSQL'deki çek kayıtlarından tek konsolide Excel raporu üretir.")
    parser.add_argument("--output", help="Oluşturulacak Excel dosyası")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL bağlantı adresi")
    parser.add_argument("--today", help="Vade hesapları için referans tarih. Örnek: 2026-05-03")
    parser.add_argument("--include-drafts", action="store_true", help="NEEDS_REVIEW/DRAFT kayıtları da rapora dahil et")
    parser.add_argument("--include-overdue-in-value-calc", action="store_true", help="Vadesi geçmiş çekleri değer hesabına dahil et")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else None
    repository = PostgresCheckRepository(args.database_url)
    records = repository.list_stored_checks(approved_only=not args.include_drafts)
    output_path = Path(args.output) if args.output else build_default_consolidated_output_path(DEFAULT_OUTPUT_DIR)
    write_consolidated_check_report(
        records,
        output_path,
        today=today,
        include_overdue_in_value_calc=args.include_overdue_in_value_calc,
    )
    print(f"{len(records)} çek konsolide rapora yazıldı.")
    print(f"Excel oluşturuldu: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
