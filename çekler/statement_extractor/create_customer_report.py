from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.customer_report import format_customer_report_summary, write_customer_payment_check_report


DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "uploads" / "excel"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "outputs" / "musteri_bazli_odeme_cek_raporu.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ekstre Excel'lerini parse edip müşteri bazlı ödeme ve çek raporu üretir.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Ekstre Excel upload klasörü")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Oluşturulacak müşteri bazlı Excel raporu")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = write_customer_payment_check_report(args.input_dir, args.output)
    print(format_customer_report_summary(result))
    print(f"Excel oluşturuldu: {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
