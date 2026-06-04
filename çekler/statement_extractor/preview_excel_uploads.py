from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.consolidated_report import write_consolidated_check_report
from statement_extractor.src.excel_importer import extract_checks_from_excel_dir
from statement_extractor.src.models import to_jsonable


DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "uploads" / "excel"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel upload dosyalarını DB'ye yazmadan preview olarak okur.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Excel upload klasörü")
    parser.add_argument("--json-output", default=str(DEFAULT_OUTPUT_DIR / "excel_upload_preview.json"), help="Preview JSON çıktısı")
    parser.add_argument("--excel-output", help="Preview kayıtlarından konsolide Excel üret")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = extract_checks_from_excel_dir(args.input_dir)
    records = [record for result in results for record in result.records]
    warnings = [warning for result in results for warning in result.warnings]

    output = {
        "file_count": len(results),
        "record_count": len(records),
        "warning_count": len(warnings),
        "sessions": [result.import_session for result in results],
        "records": records,
        "warnings": warnings,
    }
    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(to_jsonable(output), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(results)} Excel dosyası okundu.")
    print(f"{len(records)} çek kaydı bulundu.")
    print(f"{len(warnings)} uyarı üretildi.")
    print(f"JSON oluşturuldu: {json_path}")

    if args.excel_output:
        excel_path = Path(args.excel_output)
        write_consolidated_check_report(records, excel_path)
        print(f"Preview Excel oluşturuldu: {excel_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
