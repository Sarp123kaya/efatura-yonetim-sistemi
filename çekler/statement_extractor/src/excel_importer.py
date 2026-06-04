from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from openpyxl import load_workbook

from .excel_compare import load_excel_rows, parse_amount, parse_date
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
from .utils import normalize_bank_name
from .zirve_muavin_excel import extract_checks_from_zirve_muavin_workbook


SUPPORTED_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


def extract_checks_from_excel(
    excel_path: str | Path,
    source_type: CheckSourceType = CheckSourceType.EXCEL,
    review_status: ReviewStatus = ReviewStatus.APPROVED,
    import_session_id: Optional[str] = None,
) -> ImportResult:
    path = Path(excel_path)
    if path.suffix.lower() not in SUPPORTED_EXCEL_SUFFIXES:
        raise ValueError("Sadece .xlsx veya .xlsm Excel dosyaları işlenebilir.")

    session_id = import_session_id or str(uuid4())
    workbook = load_workbook(path, data_only=True)
    try:
        muavin_result = extract_checks_from_zirve_muavin_workbook(
            workbook,
            path.name,
            session_id,
            source_type,
            review_status,
        )
    finally:
        workbook.close()
    if muavin_result is not None:
        return muavin_result

    workbook_data = load_excel_rows(path)
    metadata = StatementMetadata(
        account_code=workbook_data.get("account_code"),
        account_name=workbook_data.get("account_name"),
        company_name=workbook_data.get("company_name"),
        source_filename=path.name,
    )
    session = ImportSession(
        import_session_id=session_id,
        source_type=source_type,
        source_file=path.name,
        status=ImportSessionStatus.PARSED,
        statement_metadata=metadata,
        total_rows=len(workbook_data["rows"]),
    )

    records: list[StoredCheckRecord] = []
    warnings: list[ParseWarning] = []
    errors: list[str] = []
    for row in workbook_data["rows"]:
        record, warning = row_to_stored_check(row, path.name, workbook_data.get("sheet_name"), metadata, source_type, review_status, session_id)
        if record:
            records.append(record)
        if warning:
            warnings.append(warning)

    session.parsed_count = len(records)
    session.warning_count = len(warnings)
    session.error_count = len(errors)
    session.completed_at = datetime.utcnow()
    return ImportResult(import_session=session, records=records, warnings=warnings, errors=errors)


def extract_checks_from_excel_dir(
    input_dir: str | Path,
    source_type: CheckSourceType = CheckSourceType.EXCEL,
) -> list[ImportResult]:
    results: list[ImportResult] = []
    for path in sorted(Path(input_dir).iterdir()):
        if path.name.startswith(".") or path.suffix.lower() not in SUPPORTED_EXCEL_SUFFIXES:
            continue
        results.append(extract_checks_from_excel(path, source_type=source_type))
    return results


def row_to_stored_check(
    row: dict[str, Any],
    source_file: str,
    source_sheet: Optional[str],
    metadata: StatementMetadata,
    source_type: CheckSourceType,
    review_status: ReviewStatus,
    import_session_id: str,
) -> tuple[Optional[StoredCheckRecord], Optional[ParseWarning]]:
    check_no = clean_text(row.get("Çek No"))
    bank = normalize_bank_name(clean_text(row.get("Banka"))) or clean_text(row.get("Banka"))
    maturity_date = parse_date(row.get("Vade Tarihi"))
    amount = parse_amount(row.get("Tutar"))
    warning_messages: list[str] = []

    if not check_no:
        warning_messages.append("Çek no boş.")
    if not bank:
        warning_messages.append("Banka boş.")
    if maturity_date is None:
        warning_messages.append("Vade tarihi okunamadı.")
    if amount is None:
        warning_messages.append("Tutar okunamadı.")
    elif amount <= Decimal("0"):
        warning_messages.append("Tutar pozitif olmalı.")

    row_index = int(row.get("row_index") or 0)
    raw_line = build_raw_line(row)
    if warning_messages:
        return None, ParseWarning(
            source_page=row_index,
            raw_line=raw_line,
            warning_type="invalid_excel_row",
            message=" ".join(warning_messages),
        )

    parse_warning = clean_text(row.get("Doğrulama Notu")) or None
    record = StoredCheckRecord(
        transaction_date=None,
        document_date=None,
        voucher_no=None,
        document_no=None,
        check_no=check_no,
        bank=bank,
        maturity_date=maturity_date,
        maturity_month=maturity_date.strftime("%Y-%m"),
        amount=amount,
        currency="TRY",
        customer_name=clean_text(row.get("Lehtar")) or metadata.account_name,
        company_name=clean_text(row.get("Keşideci")) or metadata.company_name,
        sent_to=clean_text(row.get("Gönderildiği Yer")) or None,
        source_page=row_index,
        raw_description=clean_text(row.get("Açıklama")) or "Excel upload",
        raw_line=raw_line,
        parse_warning=parse_warning,
        source_type=source_type,
        source_file=source_file,
        import_session_id=import_session_id,
        review_status=review_status,
        source_row_index=row_index,
        source_sheet=source_sheet,
    )
    return record, None


def build_raw_line(row: dict[str, Any]) -> str:
    parts = []
    for key in ("Çek No", "Banka", "Vade Tarihi", "Tutar", "Lehtar", "Keşideci", "Gönderildiği Yer", "Açıklama"):
        value = row.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    return " | ".join(parts)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
