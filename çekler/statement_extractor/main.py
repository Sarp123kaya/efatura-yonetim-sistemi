from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.models import to_jsonable
from statement_extractor.src.service import create_excel_from_parse_result, extract_checks_from_pdf
from statement_extractor.src.utils import format_try_amount, safe_filename


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cari/muavin PDF dosyasından ALINAN ÇEK kayıtlarını çıkarır.")
    parser.add_argument("input_pdf", help="İşlenecek PDF dosyası")
    parser.add_argument("output_xlsx", nargs="?", help="Oluşturulacak Excel dosyası")
    parser.add_argument("--today", help="Vade hesapları için referans tarih. Örnek: 2026-05-03")
    parser.add_argument("--include-debug", action="store_true", help="Parse Debug sayfasını Excel'e ekle")
    parser.add_argument("--no-excel", action="store_true", help="Excel üretmeden sadece parse et")
    parser.add_argument("--json-output", help="Parse sonucunu JSON dosyasına yaz")
    parser.add_argument(
        "--include-overdue-in-value-calc",
        action="store_true",
        help="Vadesi geçmiş çekleri Değer Hesabı ağırlıklı ortalama vade hesabına dahil et",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else None
    parse_result = extract_checks_from_pdf(args.input_pdf, today=today)

    if parse_result.summary.total_count == 0:
        print("PDF içinde ALINAN ÇEK kaydı bulunamadı.")
    else:
        print(f"{parse_result.summary.total_count} çek bulundu.")
        print(f"Toplam çek tutarı: {format_try_amount(parse_result.summary.total_amount)}")
        if parse_result.summary.earliest_maturity_date:
            print(f"En erken vade: {parse_result.summary.earliest_maturity_date.strftime('%d.%m.%Y')}")
        if parse_result.summary.latest_maturity_date:
            print(f"En geç vade: {parse_result.summary.latest_maturity_date.strftime('%d.%m.%Y')}")

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(to_jsonable(parse_result), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON oluşturuldu: {json_path}")

    if not args.no_excel:
        output_path = Path(args.output_xlsx) if args.output_xlsx else build_default_output_path(args.input_pdf)
        create_excel_from_parse_result(
            parse_result,
            output_path,
            today=today,
            include_debug=True if args.include_debug else True,
            include_overdue_in_value_calc=args.include_overdue_in_value_calc,
        )
        print(f"Excel oluşturuldu: {output_path}")

    return 0


def build_default_output_path(input_pdf: str) -> Path:
    source_name = safe_filename(Path(input_pdf).stem, default="ekstre")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return DEFAULT_OUTPUT_DIR / f"cekler_vadeye_gore_detayli_{source_name}_{timestamp}.xlsx"


if __name__ == "__main__":
    raise SystemExit(main())
