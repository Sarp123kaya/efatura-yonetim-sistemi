from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from statement_extractor.src.image_ocr_reader import OcrUnavailableError, extract_checks_from_image
from statement_extractor.src.models import to_jsonable
from statement_extractor.src.postgres_repository import PostgresCheckRepository


DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "uploads" / "images"
DEFAULT_DRAFT_DIR = Path(__file__).resolve().parent / "ocr_drafts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Görüntü upload klasöründen OCR taslak çek kayıtlarını PostgreSQL'e aktarır.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="JPG/PNG upload klasörü")
    parser.add_argument("--draft-dir", default=str(DEFAULT_DRAFT_DIR), help="OCR taslak JSON klasörü")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL bağlantı adresi")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    draft_dir = Path(args.draft_dir)
    draft_dir.mkdir(parents=True, exist_ok=True)
    repository = PostgresCheckRepository(args.database_url)

    for image_path in sorted(input_dir.iterdir()):
        if image_path.name.startswith(".") or image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            result = extract_checks_from_image(image_path)
        except OcrUnavailableError as exc:
            print(f"{image_path.name}: OCR çalışmadı - {exc}")
            continue
        draft_path = draft_dir / f"{image_path.stem}_ocr_draft.json"
        draft_path.write_text(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2), encoding="utf-8")
        summary = repository.import_result(result)
        print(
            f"{image_path.name}: OCR taslak kaydedildi, "
            f"{summary['import_row_count']} session satırı saklandı, "
            f"{summary['inserted_count']} kayıt eklendi, "
            f"{summary['skipped_duplicate_count']} duplicate atlandı, "
            f"{summary['error_count']} hata. Draft: {draft_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
