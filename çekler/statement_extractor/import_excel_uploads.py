from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.excel_importer import extract_checks_from_excel_dir
from statement_extractor.src.models import to_jsonable
from statement_extractor.src.postgres_repository import PostgresCheckRepository


DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "uploads" / "excel"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel upload klasöründen çek kayıtlarını PostgreSQL'e aktarır.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Excel upload klasörü")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL bağlantı adresi")
    parser.add_argument("--json-output", help="Import sonuçlarını JSON olarak yaz")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = extract_checks_from_excel_dir(args.input_dir)
    repository = PostgresCheckRepository(args.database_url)
    summaries = []
    for result in results:
        summary = repository.import_result(result)
        summaries.append({"session": result.import_session, "summary": summary})
        print(
            f"{result.import_session.source_file}: "
            f"{summary['import_row_count']} session satırı saklandı, "
            f"{summary['inserted_count']} kayıt eklendi, "
            f"{summary['skipped_duplicate_count']} duplicate atlandı, "
            f"{summary['error_count']} hata."
        )

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(to_jsonable(summaries), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
