from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .models import (
    CheckSourceType,
    ImportResult,
    ImportSession,
    ImportSessionStatus,
    ParseWarning,
    ReviewStatus,
    StatementMetadata,
    StoredCheckRecord,
)
from .utils import normalize_bank_name, parse_turkish_amount, parse_turkish_date


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DATE_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
AMOUNT_RE = re.compile(r"(?:#|\b)(\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2})(?:#|\b)")
CHECK_NO_RE = re.compile(r"(?:Çek\s*No|Cek\s*No|Seri\s*No|Çek\s*Numarası|Cek\s*Numarasi)\s*[:#]?\s*(\d{4,})", re.IGNORECASE)


class OcrUnavailableError(RuntimeError):
    pass


def extract_text_from_image(image_path: str | Path, lang: str = "tur+eng") -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise OcrUnavailableError("OCR için Pillow ve pytesseract kurulmalı.") from exc

    try:
        with Image.open(image_path) as image:
            return pytesseract.image_to_string(image, lang=lang)
    except Exception as exc:
        raise OcrUnavailableError(
            "OCR çalıştırılamadı. Tesseract sistem binary kurulu olmayabilir veya görüntü okunamadı."
        ) from exc


def extract_checks_from_image(
    image_path: str | Path,
    import_session_id: Optional[str] = None,
    ocr_text: Optional[str] = None,
) -> ImportResult:
    path = Path(image_path)
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError("Sadece JPG, JPEG veya PNG görüntü dosyaları işlenebilir.")

    session_id = import_session_id or str(uuid4())
    metadata = StatementMetadata(source_filename=path.name)
    session = ImportSession(
        import_session_id=session_id,
        source_type=CheckSourceType.IMAGE_OCR,
        source_file=path.name,
        status=ImportSessionStatus.PARSED,
        statement_metadata=metadata,
        total_rows=1,
    )
    text = ocr_text if ocr_text is not None else extract_text_from_image(path)
    record, warning = parse_check_from_ocr_text(text, path.name, session_id)
    records = [record] if record else []
    warnings = [warning] if warning else []
    session.parsed_count = len(records)
    session.warning_count = len(warnings)
    session.completed_at = datetime.utcnow()
    return ImportResult(import_session=session, records=records, warnings=warnings, errors=[])


def extract_checks_from_image_dir(input_dir: str | Path) -> list[ImportResult]:
    results: list[ImportResult] = []
    for path in sorted(Path(input_dir).iterdir()):
        if path.name.startswith(".") or path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        results.append(extract_checks_from_image(path))
    return results


def parse_check_from_ocr_text(text: str, source_file: str, import_session_id: str) -> tuple[Optional[StoredCheckRecord], Optional[ParseWarning]]:
    normalized_text = normalize_ocr_text(text)
    check_no = extract_check_no(normalized_text)
    bank = extract_bank(normalized_text)
    maturity_date = extract_maturity_date(normalized_text)
    amount = extract_amount(normalized_text)
    customer_name = extract_named_line(normalized_text, ("Lehtar", "Bu çek karşılığında", "Bu cek karsiliginda"))
    company_name = extract_named_line(normalized_text, ("Keşideci", "Kesideci"))
    warning_messages: list[str] = []

    if not check_no:
        warning_messages.append("OCR çek no alanını güvenilir okuyamadı.")
    if not bank:
        warning_messages.append("OCR banka alanını güvenilir okuyamadı.")
    if maturity_date is None:
        warning_messages.append("OCR vade/keşide tarihini güvenilir okuyamadı.")
    if amount is None:
        warning_messages.append("OCR tutar alanını güvenilir okuyamadı.")

    if not (check_no and bank and maturity_date and amount is not None):
        return None, ParseWarning(
            source_page=1,
            raw_line=normalized_text[:1000],
            warning_type="ocr_low_confidence",
            message=" ".join(warning_messages),
        )

    parse_warning = "OCR ile çıkarıldı; kullanıcı onayı gerektirir."
    if warning_messages:
        parse_warning += " " + " ".join(warning_messages)

    record = StoredCheckRecord(
        check_no=check_no,
        bank=bank,
        maturity_date=maturity_date,
        maturity_month=maturity_date.strftime("%Y-%m"),
        amount=amount,
        currency="TRY",
        customer_name=customer_name or None,
        company_name=company_name or None,
        source_page=1,
        raw_description="OCR image check draft",
        raw_line=normalized_text[:4000],
        parse_warning=parse_warning,
        source_type=CheckSourceType.IMAGE_OCR,
        source_file=source_file,
        import_session_id=import_session_id,
        review_status=ReviewStatus.NEEDS_REVIEW,
        source_row_index=1,
    )
    return record, None


def normalize_ocr_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    return "\n".join(lines)


def extract_check_no(text: str) -> str:
    match = CHECK_NO_RE.search(text)
    if match:
        return match.group(1)
    numeric_lines = re.findall(r"\b\d{6,}\b", text)
    return numeric_lines[0] if numeric_lines else ""


def extract_bank(text: str) -> str:
    candidates = [
        "Garanti BBVA",
        "HALKBANK",
        "DENİZBANK",
        "DENIZBANK",
        "ZİRAAT",
        "ZIRAAT",
        "YAPI KREDİ",
        "YAPI KREDI",
        "AKBANK",
        "QNB FİNANSBANK",
        "QNB FINANSBANK",
        "İŞ BANKASI",
        "IS BANKASI",
    ]
    upper_text = text.upper()
    for candidate in candidates:
        if candidate.upper() in upper_text:
            return normalize_bank_name(candidate) or candidate
    return ""


def extract_maturity_date(text: str):
    for match in DATE_RE.findall(text):
        parsed = parse_turkish_date(match.replace("/", "."))
        if parsed:
            return parsed
    return None


def extract_amount(text: str) -> Optional[Decimal]:
    for match in AMOUNT_RE.findall(text):
        amount_text = match if "," in match else f"{match},00"
        amount = parse_turkish_amount(amount_text)
        if amount is not None and amount > Decimal("0"):
            return amount
    return None


def extract_named_line(text: str, markers: tuple[str, ...]) -> str:
    for line in text.splitlines():
        for marker in markers:
            if marker.lower() in line.lower():
                value = line.split(marker, 1)[-1].strip(" :#")
                if value and len(value) > 3:
                    return value
    return ""
