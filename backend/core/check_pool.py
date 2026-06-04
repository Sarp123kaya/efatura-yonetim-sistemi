#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-source check pool adapted from the cek-takip project."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .db import DatabaseHelper, db as default_db
from .payment_import import (
    CustomerCheckRow,
    FirmCard,
    MatchResult,
    format_decimal,
    match_check_to_firm,
    normalize_text,
    parse_date,
    parse_decimal,
)

logger = logging.getLogger(__name__)


class MovementType(str, Enum):
    RECEIVED_CHECK = "RECEIVED_CHECK"


class CheckSourceType(str, Enum):
    PDF = "PDF"
    EXCEL = "EXCEL"
    IMAGE_OCR = "IMAGE_OCR"
    TEXT = "TEXT"
    MANUAL = "MANUAL"


class ReviewStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    IMPORTED = "IMPORTED"
    REJECTED = "REJECTED"


class ImportSessionStatus(str, Enum):
    CREATED = "CREATED"
    PARSED = "PARSED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


@dataclass
class StatementMetadata:
    company_name: Optional[str] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    page_count: int = 0
    source_filename: Optional[str] = None
    extracted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ParseWarning:
    source_page: Optional[int] = None
    raw_line: Optional[str] = None
    warning_type: str = ""
    message: str = ""


@dataclass
class StoredCheckRecord:
    check_no: str
    bank: str
    maturity_date: date
    amount: Optional[Decimal]
    source_page: int
    raw_description: str
    raw_line: str
    movement_type: MovementType = MovementType.RECEIVED_CHECK
    maturity_month: str = ""
    currency: str = "TRY"
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    sent_to: Optional[str] = None
    transaction_date: Optional[date] = None
    document_date: Optional[date] = None
    voucher_no: Optional[str] = None
    document_no: Optional[str] = None
    parse_warning: Optional[str] = None
    source_type: CheckSourceType = CheckSourceType.EXCEL
    source_file: Optional[str] = None
    import_session_id: Optional[str] = None
    review_status: ReviewStatus = ReviewStatus.APPROVED
    source_row_index: Optional[int] = None
    source_sheet: Optional[str] = None
    source_image_region: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.maturity_month and self.maturity_date:
            self.maturity_month = self.maturity_date.strftime("%Y-%m")

    @property
    def duplicate_key(self) -> tuple[str, str, str, str, str]:
        return (
            normalize_text(self.customer_name or ""),
            normalize_text(self.check_no),
            normalize_text(self.bank),
            self.maturity_date.isoformat(),
            format_decimal(self.amount or Decimal("0")),
        )

    @property
    def idempotency_key(self) -> str:
        material = "|".join(self.duplicate_key)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class ImportSession:
    import_session_id: str
    source_type: CheckSourceType
    source_file: str
    status: ImportSessionStatus = ImportSessionStatus.CREATED
    statement_metadata: StatementMetadata = field(default_factory=StatementMetadata)
    total_rows: int = 0
    parsed_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    message: Optional[str] = None


@dataclass
class CheckImportResult:
    import_session: ImportSession
    records: List[StoredCheckRecord] = field(default_factory=list)
    warnings: List[ParseWarning] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class CheckIsbasiComparison:
    record: StoredCheckRecord
    match: MatchResult
    isbasi_status: str
    isbasi_rows: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def to_record(self) -> Dict[str, Any]:
        firm = self.match.firm
        return {
            "status": self.isbasi_status,
            "check_no": self.record.check_no,
            "bank": self.record.bank,
            "maturity_date": self.record.maturity_date.isoformat(),
            "amount": float(self.record.amount or Decimal("0")),
            "currency": self.record.currency,
            "customer_name": self.record.customer_name or "",
            "company_name": self.record.company_name or "",
            "source_type": self.record.source_type.value,
            "source_file": self.record.source_file or "",
            "review_status": self.record.review_status.value,
            "matched_firm_id": firm.id if firm else "",
            "matched_firm_code": firm.code if firm else "",
            "matched_firm_name": firm.name if firm else "",
            "match_score": self.match.score,
            "match_reason": self.match.reason,
            "isbasi_candidate_count": len(self.isbasi_rows),
            "notes": self.notes,
        }


DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
CHECK_DETAIL_RE = re.compile(
    r"\(?\s*(?P<check_no>\d+)\s+NL\s+(?P<bank>.*?)\s+VD\s*:\s*(?P<maturity>\d{1,2}\.\d{1,2}\.\d{2,4})",
    re.IGNORECASE,
)


def extract_checks_from_paths(paths: Iterable[Path]) -> List[CheckImportResult]:
    results: List[CheckImportResult] = []
    for path in expand_check_input_paths(paths):
        results.append(extract_checks_from_path(path))
    return results


def expand_check_input_paths(paths: Iterable[Path]) -> List[Path]:
    supported = {".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}
    expanded: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
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
        raise FileNotFoundError("Okunacak çek dosyası bulunamadı")
    return expanded


def extract_checks_from_path(path: Path) -> CheckImportResult:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm", ".csv"}:
        return extract_checks_from_table_file(path)
    if suffix == ".txt":
        return extract_checks_from_text(path.read_text(encoding="utf-8", errors="ignore"), path.name, CheckSourceType.TEXT)
    if suffix == ".pdf":
        return extract_checks_from_pdf(path)
    if suffix in {".png", ".jpg", ".jpeg"}:
        return extract_checks_from_image(path)
    raise ValueError(f"Desteklenmeyen dosya tipi: {path}")


def extract_checks_from_table_file(path: Path) -> CheckImportResult:
    session_id = str(uuid.uuid4())
    source_type = CheckSourceType.EXCEL
    metadata = StatementMetadata(source_filename=path.name)
    session = ImportSession(session_id, source_type, path.name, statement_metadata=metadata)
    warnings: List[ParseWarning] = []
    errors: List[str] = []
    records: List[StoredCheckRecord] = []

    if path.suffix.lower() == ".csv":
        sheets = {"CSV": pd.read_csv(path)}
    else:
        sheets = pd.read_excel(path, sheet_name=None)

    total_rows = 0
    for sheet_name, df in sheets.items():
        mapping = _canonical_column_map(df.columns)
        for idx, row in df.iterrows():
            total_rows += 1
            record, warning = _row_to_stored_check(row, mapping, path.name, str(sheet_name), int(idx) + 2, session_id)
            if record:
                records.append(record)
            if warning:
                warnings.append(warning)

    session.total_rows = total_rows
    session.parsed_count = len(records)
    session.warning_count = len(warnings)
    session.error_count = len(errors)
    session.status = ImportSessionStatus.PARSED
    session.completed_at = datetime.utcnow()
    return CheckImportResult(session, records, warnings, errors)


def extract_checks_from_text(text: str, source_file: str, source_type: CheckSourceType = CheckSourceType.PDF) -> CheckImportResult:
    session_id = str(uuid.uuid4())
    metadata = StatementMetadata(source_filename=source_file)
    session = ImportSession(session_id, source_type, source_file, statement_metadata=metadata)
    lines = [(index + 1, line.strip()) for index, line in enumerate(text.splitlines()) if line.strip()]
    records, warnings = parse_statement_lines(lines, metadata, session_id, source_type)
    session.total_rows = len(lines)
    session.parsed_count = len(records)
    session.warning_count = len(warnings)
    session.status = ImportSessionStatus.PARSED
    session.completed_at = datetime.utcnow()
    return CheckImportResult(session, records, warnings, [])


def extract_checks_from_pdf(path: Path) -> CheckImportResult:
    text_parts: List[str] = []
    errors: List[str] = []
    try:
        import PyPDF2  # type: ignore

        with path.open("rb") as handle:
            reader = PyPDF2.PdfReader(handle)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
    except Exception as exc:
        errors.append(f"PDF metni okunamadı: {exc}")

    if errors:
        return _failed_import_result(path, CheckSourceType.PDF, errors)
    return extract_checks_from_text("\n".join(text_parts), path.name, CheckSourceType.PDF)


def extract_checks_from_image(path: Path) -> CheckImportResult:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        text = pytesseract.image_to_string(Image.open(path), lang="tur+eng")
    except Exception as exc:
        return _failed_import_result(
            path,
            CheckSourceType.IMAGE_OCR,
            [f"OCR için pillow/pytesseract/tesseract gerekli veya görüntü okunamadı: {exc}"],
        )
    result = extract_checks_from_text(text, path.name, CheckSourceType.IMAGE_OCR)
    for record in result.records:
        record.review_status = ReviewStatus.NEEDS_REVIEW
    return result


def _failed_import_result(path: Path, source_type: CheckSourceType, errors: List[str]) -> CheckImportResult:
    session = ImportSession(
        import_session_id=str(uuid.uuid4()),
        source_type=source_type,
        source_file=path.name,
        status=ImportSessionStatus.FAILED,
        error_count=len(errors),
        completed_at=datetime.utcnow(),
        message="; ".join(errors),
    )
    return CheckImportResult(session, [], [], errors)


def parse_statement_lines(
    lines: Sequence[tuple[int, str]],
    metadata: StatementMetadata,
    import_session_id: str,
    source_type: CheckSourceType,
) -> tuple[List[StoredCheckRecord], List[ParseWarning]]:
    records: List[StoredCheckRecord] = []
    warnings: List[ParseWarning] = []
    for source_page, raw_line in lines:
        if not _is_received_check_line(raw_line):
            if _is_unsupported_check_summary_line(raw_line):
                warnings.append(
                    ParseWarning(
                        source_page=source_page,
                        raw_line=raw_line,
                        warning_type="unsupported_check_summary",
                        message="Satır çek hareketi içeriyor ancak çek no, banka ve vade detayı bulunmuyor.",
                    )
                )
            continue
        record, warning = _parse_received_check_line(raw_line, source_page, metadata, import_session_id, source_type)
        if record:
            records.append(record)
        if warning:
            warnings.append(warning)
    return records, warnings


def _parse_received_check_line(
    raw_line: str,
    source_page: int,
    metadata: StatementMetadata,
    import_session_id: str,
    source_type: CheckSourceType,
) -> tuple[Optional[StoredCheckRecord], Optional[ParseWarning]]:
    detail_match = CHECK_DETAIL_RE.search(raw_line)
    amounts = _find_turkish_amounts(raw_line)
    amount = amounts[0] if amounts else None
    if not detail_match:
        return None, ParseWarning(
            source_page=source_page,
            raw_line=raw_line,
            warning_type="missing_required_field",
            message="Çek no/banka/vade detayı bulunamadı.",
        )

    maturity_date = _parse_turkish_date(detail_match.group("maturity"))
    if maturity_date is None:
        return None, ParseWarning(
            source_page=source_page,
            raw_line=raw_line,
            warning_type="missing_required_field",
            message="Vade tarihi bulunamadı.",
        )

    parse_warning = "Tutar net bulunamadı." if amount is None else None
    review_status = ReviewStatus.NEEDS_REVIEW if amount is None or source_type == CheckSourceType.IMAGE_OCR else ReviewStatus.APPROVED
    return StoredCheckRecord(
        check_no=detail_match.group("check_no"),
        bank=_normalize_bank_name(detail_match.group("bank")),
        maturity_date=maturity_date,
        maturity_month=maturity_date.strftime("%Y-%m"),
        amount=amount,
        currency="TRY",
        customer_name=metadata.account_name,
        company_name=metadata.company_name,
        source_page=source_page,
        raw_description=raw_line,
        raw_line=raw_line,
        parse_warning=parse_warning,
        source_type=source_type,
        source_file=metadata.source_filename,
        import_session_id=import_session_id,
        review_status=review_status,
    ), (
        ParseWarning(source_page=source_page, raw_line=raw_line, warning_type="missing_amount", message=parse_warning)
        if parse_warning
        else None
    )


def _is_received_check_line(line: str) -> bool:
    normalized = normalize_text(line)
    return "alinan cek" in normalized


def _is_unsupported_check_summary_line(line: str) -> bool:
    normalized = normalize_text(line)
    return "cek giris" in normalized or ("borc dekontu" in normalized and "cekin" in normalized)


def _row_to_stored_check(
    row: Any,
    mapping: Dict[str, str],
    source_file: str,
    source_sheet: str,
    row_index: int,
    import_session_id: str,
) -> tuple[Optional[StoredCheckRecord], Optional[ParseWarning]]:
    def get(name: str, default: Any = "") -> Any:
        column = mapping.get(name)
        if not column:
            return default
        value = row[column]
        if isinstance(value, float) and pd.isna(value):
            return default
        return value

    check_no = str(get("check_no")).strip()
    bank = _normalize_bank_name(str(get("bank")).strip())
    customer_name = str(get("customer_name")).strip() or None
    company_name = str(get("company_name")).strip() or None
    sent_to = str(get("sent_to")).strip() or None
    raw_description = str(get("description", "Excel upload")).strip() or "Excel upload"

    warning_messages: List[str] = []
    try:
        maturity_date = parse_date(get("maturity_date"))
    except ValueError:
        maturity_date = None
        warning_messages.append("Vade tarihi okunamadı.")
    try:
        amount = parse_decimal(get("amount"))
    except ValueError:
        amount = None
        warning_messages.append("Tutar okunamadı.")

    if not check_no:
        warning_messages.append("Çek no boş.")
    if not bank:
        warning_messages.append("Banka boş.")
    if amount is not None and amount <= Decimal("0"):
        warning_messages.append("Tutar pozitif olmalı.")

    raw_line = " | ".join(
        f"{key}={value}"
        for key, value in {
            "Çek No": check_no,
            "Banka": bank,
            "Vade Tarihi": maturity_date,
            "Tutar": amount,
            "Lehtar": customer_name,
            "Keşideci": company_name,
            "Gönderildiği Yer": sent_to,
            "Açıklama": raw_description,
        }.items()
        if value not in (None, "")
    )
    if warning_messages or maturity_date is None:
        return None, ParseWarning(row_index, raw_line, "invalid_excel_row", " ".join(warning_messages))

    return StoredCheckRecord(
        check_no=check_no,
        bank=bank,
        maturity_date=maturity_date,
        maturity_month=maturity_date.strftime("%Y-%m"),
        amount=amount,
        currency=str(get("currency", "TRY") or "TRY"),
        customer_name=customer_name,
        company_name=company_name,
        sent_to=sent_to,
        source_page=row_index,
        raw_description=raw_description,
        raw_line=raw_line,
        source_type=CheckSourceType.EXCEL,
        source_file=source_file,
        import_session_id=import_session_id,
        source_row_index=row_index,
        source_sheet=source_sheet,
        review_status=ReviewStatus.APPROVED,
    ), None


def _canonical_column_map(columns: Iterable[Any]) -> Dict[str, str]:
    aliases: Dict[str, Sequence[str]] = {
        "check_no": ("çek no", "cek no", "çek numarası", "cek numarasi", "portföy no", "portfoy no"),
        "bank": ("banka", "banka adı", "banka adi"),
        "maturity_date": ("vade tarihi", "vade", "çek vadesi", "cek vadesi"),
        "amount": ("tutar", "çek tutarı", "cek tutari", "ödeme tutarı", "odeme tutari"),
        "customer_name": ("lehtar", "müşteri", "musteri", "cari", "cari adı", "cari adi", "firma adı", "firma adi"),
        "company_name": ("keşideci", "kesideci", "firma", "şirket", "sirket"),
        "sent_to": ("gönderildiği yer", "gonderildigi yer", "ciro edilen", "sent_to"),
        "description": ("açıklama", "aciklama", "not"),
        "currency": ("para birimi", "döviz", "doviz", "currency"),
    }
    normalized_to_original = {normalize_text(col): str(col) for col in columns}
    result: Dict[str, str] = {}
    for canonical, candidates in aliases.items():
        for candidate in candidates:
            original = normalized_to_original.get(normalize_text(candidate))
            if original is not None:
                result[canonical] = original
                break
    return result


def _parse_turkish_date(value: Any) -> Optional[date]:
    try:
        return parse_date(value)
    except ValueError:
        return None


def _find_turkish_amounts(text: str) -> List[Decimal]:
    values: List[Decimal] = []
    for match in re.finditer(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b", text):
        try:
            values.append(parse_decimal(match.group(0)))
        except ValueError:
            continue
    return values


def _normalize_bank_name(value: Any) -> str:
    text = str(value or "").strip()
    normalized = normalize_text(text)
    bank_map = {
        "halkbank": "Halkbank",
        "denizbank": "Denizbank",
        "ziraat": "Ziraat Bankası",
        "garanti": "Garanti BBVA",
        "yapi kredi": "Yapı Kredi",
        "is bankasi": "İş Bankası",
        "akbank": "Akbank",
        "qnb": "QNB Finansbank",
        "finansbank": "QNB Finansbank",
    }
    for key, display in bank_map.items():
        if key in normalized:
            return display
    return text


def flatten_import_results(results: Sequence[CheckImportResult]) -> List[StoredCheckRecord]:
    return [record for result in results for record in result.records]


def stored_to_customer_check(record: StoredCheckRecord) -> CustomerCheckRow:
    return CustomerCheckRow(
        source_row=record.source_row_index or record.source_page or 0,
        firm_name=record.customer_name or record.company_name or "",
        tax_id="",
        check_number=record.check_no,
        due_date=record.maturity_date,
        amount=record.amount or Decimal("0"),
        currency=record.currency,
        bank_name=record.bank,
        description=record.raw_description,
        raw={
            "source_file": record.source_file,
            "source_type": record.source_type.value,
            "import_session_id": record.import_session_id,
            "review_status": record.review_status.value,
        },
    )


def compare_check_pool_with_isbasi(
    records: Sequence[StoredCheckRecord],
    firms: Sequence[FirmCard],
    isbasi_activity_by_firm_id: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[CheckIsbasiComparison]:
    isbasi_activity_by_firm_id = isbasi_activity_by_firm_id or {}
    comparisons: List[CheckIsbasiComparison] = []
    for record in records:
        check = stored_to_customer_check(record)
        match = match_check_to_firm(check, firms)
        isbasi_rows: List[Dict[str, Any]] = []
        status = "unmatched_customer"
        notes = ""
        if match.status == "matched" and match.firm:
            isbasi_rows = isbasi_activity_by_firm_id.get(match.firm.id, [])
            status = _compare_record_to_isbasi_activity(record, isbasi_rows)
        elif match.status == "ambiguous":
            status = "ambiguous_customer"
        comparisons.append(CheckIsbasiComparison(record, match, status, isbasi_rows, notes))
    return comparisons


def transfer_candidate_records(comparisons: Sequence[CheckIsbasiComparison]) -> List[Dict[str, Any]]:
    """Only approved checks missing in İşbaşı can become transfer candidates."""

    candidates: List[Dict[str, Any]] = []
    for comparison in comparisons:
        if (
            comparison.record.review_status == ReviewStatus.APPROVED
            and comparison.isbasi_status == "missing_in_isbasi"
            and comparison.match.status == "matched"
        ):
            candidates.append(comparison.to_record())
    return candidates


def _compare_record_to_isbasi_activity(record: StoredCheckRecord, rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "missing_in_isbasi"
    amount = record.amount or Decimal("0")
    for row in rows:
        row_amount = _row_decimal(row.get("totalTL") or row.get("total") or row.get("remainingTotal"))
        row_payment_date = str(row.get("paymentDate") or "")
        same_amount = row_amount is not None and abs(row_amount - amount) <= Decimal("0.01")
        same_date = record.maturity_date.isoformat() in row_payment_date if row_payment_date else False
        if same_amount and same_date:
            return "possible_match_in_isbasi"
        if same_amount:
            return "amount_match_date_differs"
    return "missing_in_isbasi"


def _row_decimal(value: Any) -> Optional[Decimal]:
    try:
        return parse_decimal(value)
    except ValueError:
        return None


class CheckPoolRepository:
    """PostgreSQL persistence for consolidated check pool records."""

    def __init__(self, database: DatabaseHelper = default_db) -> None:
        self.db = database

    def import_result(self, result: CheckImportResult) -> Dict[str, int]:
        self.upsert_import_session(result.import_session)
        inserted = skipped = errors = 0
        for record in result.records:
            try:
                existing_id = self.find_existing_check_id(record)
                if existing_id is not None:
                    self.insert_import_row(record, duplicate_of_check_id=existing_id)
                    skipped += 1
                    continue
                check_id = self.insert_check(record)
                self.insert_import_row(record, canonical_check_id=check_id)
                inserted += 1
            except Exception as exc:
                logger.error("Check import failed for %s: %s", record.check_no, exc)
                errors += 1
        return {"inserted_count": inserted, "skipped_duplicate_count": skipped, "error_count": errors}

    def upsert_import_session(self, session: ImportSession) -> None:
        self.db.execute(
            """
            INSERT INTO check_import_sessions (
                id, source_type, source_file, status, account_code, account_name, company_name,
                total_rows, parsed_count, warning_count, error_count, message, created_at, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                parsed_count = EXCLUDED.parsed_count,
                warning_count = EXCLUDED.warning_count,
                error_count = EXCLUDED.error_count,
                message = EXCLUDED.message,
                completed_at = EXCLUDED.completed_at
            """,
            (
                session.import_session_id,
                session.source_type.value,
                session.source_file,
                session.status.value,
                session.statement_metadata.account_code,
                session.statement_metadata.account_name,
                session.statement_metadata.company_name,
                session.total_rows,
                session.parsed_count,
                session.warning_count,
                session.error_count,
                session.message,
                session.created_at,
                session.completed_at,
            ),
        )

    def find_existing_check_id(self, record: StoredCheckRecord) -> Optional[int]:
        check_no = (record.check_no or "").strip()
        if check_no:
            row = self.db.query_one(
                """
                SELECT id FROM checks
                WHERE TRIM(check_no) = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (check_no,),
            )
            return int(row["id"]) if row else None
        row = self.db.query_one(
            """
            SELECT id FROM checks
            WHERE COALESCE(account_name, '') = COALESCE(%s, '')
              AND check_no = %s
              AND bank_name = %s
              AND maturity_date = %s
              AND amount IS NOT DISTINCT FROM %s
            LIMIT 1
            """,
            (record.customer_name, record.check_no, record.bank, record.maturity_date, record.amount),
        )
        return int(row["id"]) if row else None

    def insert_check(self, record: StoredCheckRecord) -> int:
        query = """
        INSERT INTO checks (
            account_name, company_name, movement_type, check_no, bank_name, sent_to,
            amount, currency, maturity_date, transaction_date, document_date, voucher_no,
            document_no, status, source_file, source_page, raw_description, raw_line,
            parse_warning, source_type, import_session_id, review_status, source_row_index,
            source_sheet, source_image_region, created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, NOW()
        )
        RETURNING id
        """
        params = (
            record.customer_name,
            record.company_name,
            record.movement_type.value,
            record.check_no,
            record.bank,
            record.sent_to,
            record.amount,
            record.currency,
            record.maturity_date,
            record.transaction_date,
            record.document_date,
            record.voucher_no,
            record.document_no,
            "PORTFOLIO",
            record.source_file,
            record.source_page,
            record.raw_description,
            record.raw_line,
            record.parse_warning,
            record.source_type.value,
            record.import_session_id,
            record.review_status.value,
            record.source_row_index,
            record.source_sheet,
            record.source_image_region,
            record.created_at,
        )
        with self.db.get_connection(auto_commit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return int(cur.fetchone()[0])

    def insert_import_row(
        self,
        record: StoredCheckRecord,
        canonical_check_id: Optional[int] = None,
        duplicate_of_check_id: Optional[int] = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO check_import_rows (
                import_session_id, canonical_check_id, source_type, source_file, source_sheet,
                source_row_index, check_no, bank_name, amount, currency, maturity_date,
                transaction_date, document_date, account_name, company_name, review_status,
                sent_to, raw_description, raw_line, parse_warning, duplicate_of_check_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.import_session_id,
                canonical_check_id,
                record.source_type.value,
                record.source_file,
                record.source_sheet,
                record.source_row_index,
                record.check_no,
                record.bank,
                record.amount,
                record.currency,
                record.maturity_date,
                record.transaction_date,
                record.document_date,
                record.customer_name,
                record.company_name,
                record.review_status.value,
                record.sent_to,
                record.raw_description,
                record.raw_line,
                record.parse_warning,
                duplicate_of_check_id,
                record.created_at,
            ),
        )


def export_check_pool_report(
    records: Sequence[StoredCheckRecord],
    output_path: Path,
    comparisons: Optional[Sequence[CheckIsbasiComparison]] = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame([_record_to_row(record) for record in records]).to_excel(writer, sheet_name="Tum_Cekler", index=False)
        pd.DataFrame(_account_summary(records)).to_excel(writer, sheet_name="Cari_Ozet", index=False)
        pd.DataFrame(_bank_summary(records)).to_excel(writer, sheet_name="Banka_Ozet", index=False)
        pd.DataFrame(_maturity_summary(records)).to_excel(writer, sheet_name="Vade_Takvimi", index=False)
        if comparisons is not None:
            pd.DataFrame([comparison.to_record() for comparison in comparisons]).to_excel(
                writer,
                sheet_name="Isbasi_Karsilastirma",
                index=False,
            )
            pd.DataFrame(transfer_candidate_records(comparisons)).to_excel(
                writer,
                sheet_name="Aktarim_Adaylari",
                index=False,
            )
    return output_path


def _record_to_row(record: StoredCheckRecord) -> Dict[str, Any]:
    return {
        "check_no": record.check_no,
        "bank": record.bank,
        "maturity_date": record.maturity_date.isoformat(),
        "maturity_month": record.maturity_month,
        "amount": float(record.amount or Decimal("0")),
        "currency": record.currency,
        "customer_name": record.customer_name or "",
        "company_name": record.company_name or "",
        "sent_to": record.sent_to or "",
        "source_type": record.source_type.value,
        "source_file": record.source_file or "",
        "review_status": record.review_status.value,
        "import_session_id": record.import_session_id or "",
        "parse_warning": record.parse_warning or "",
        "raw_description": record.raw_description,
    }


def _account_summary(records: Sequence[StoredCheckRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[StoredCheckRecord]] = defaultdict(list)
    for record in records:
        grouped[record.customer_name or "Belirsiz Cari"].append(record)
    rows = []
    for account, items in sorted(grouped.items()):
        total = sum((item.amount or Decimal("0") for item in items), Decimal("0"))
        rows.append({"account": account, "count": len(items), "total": float(total)})
    return rows


def _bank_summary(records: Sequence[StoredCheckRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[StoredCheckRecord]] = defaultdict(list)
    for record in records:
        grouped[record.bank or "Belirsiz Banka"].append(record)
    rows = []
    for bank, items in sorted(grouped.items()):
        total = sum((item.amount or Decimal("0") for item in items), Decimal("0"))
        rows.append({"bank": bank, "count": len(items), "total": float(total)})
    return rows


def _maturity_summary(records: Sequence[StoredCheckRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[StoredCheckRecord]] = defaultdict(list)
    for record in records:
        grouped[record.maturity_month].append(record)
    rows = []
    for month, items in sorted(grouped.items()):
        total = sum((item.amount or Decimal("0") for item in items), Decimal("0"))
        rows.append({"maturity_month": month, "count": len(items), "total": float(total)})
    return rows
