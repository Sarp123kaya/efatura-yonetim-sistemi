from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.diff_models import dataclass_to_jsonable
from statement_extractor.src.excel_compare import build_default_diff_report_path, compare_excel_files, write_diff_report
from statement_extractor.src.utils import format_try_amount


DEFAULT_DIFF_DIR = Path(__file__).resolve().parent / "diff_reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="İki çek Excel versiyonunu karşılaştırıp fark raporu üretir.")
    parser.add_argument("old_excel", help="Eski snapshot veya Excel dosyası")
    parser.add_argument("new_excel", help="Yeni/güncel Excel dosyası")
    parser.add_argument("--output", help="Oluşturulacak diff Excel raporu")
    parser.add_argument("--json-output", help="Diff sonucunu JSON olarak yaz")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = compare_excel_files(args.old_excel, args.new_excel)
    output_path = Path(args.output) if args.output else build_default_diff_report_path(args.new_excel, DEFAULT_DIFF_DIR)
    write_diff_report(report, output_path)

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Değişen satır: {report.modified_count}")
    print(f"Eklenen satır: {report.added_count}")
    print(f"Silinen satır: {report.removed_count}")
    print(f"Tutar farkı: {format_try_amount(report.amount_difference)}")
    print(f"Diff raporu oluşturuldu: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
