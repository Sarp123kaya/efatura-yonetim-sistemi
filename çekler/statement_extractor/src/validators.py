from __future__ import annotations

from decimal import Decimal

from .models import CheckRecord


def validate_check_record(record: CheckRecord) -> list[str]:
    errors: list[str] = []
    if not record.check_no:
        errors.append("Çek no bulunamadı.")
    if not record.maturity_date:
        errors.append("Vade tarihi bulunamadı.")
    if record.amount is None:
        errors.append("Tutar bulunamadı.")
    elif record.amount <= Decimal("0"):
        errors.append("Tutar pozitif olmalı.")
    return errors


def duplicate_key(record: CheckRecord) -> tuple[str | None, str, str, str, Decimal | None]:
    return (
        record.customer_name,
        record.check_no,
        record.bank,
        record.maturity_date.isoformat(),
        record.amount,
    )


def find_duplicate_checks(records: list[CheckRecord]) -> list[CheckRecord]:
    seen: set[tuple[str | None, str, str, str, Decimal | None]] = set()
    duplicates: list[CheckRecord] = []
    for record in records:
        key = duplicate_key(record)
        if key in seen:
            duplicates.append(record)
        else:
            seen.add(key)
    return duplicates
