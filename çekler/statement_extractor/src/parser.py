from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .models import CheckRecord, DebugRow, ParseResult, ParseWarning, StatementMetadata, Summary
from .utils import (
    calculate_days_until_maturity,
    find_turkish_amounts,
    get_week_period,
    normalize_bank_name,
    normalize_for_match,
    parse_turkish_amount,
    parse_turkish_date,
)


DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
RECEIVED_CHECK_RE = re.compile(r"AL[Iİ]NAN\s+Ç?C?E?K|ALINAN\s+CEK", re.IGNORECASE)
CHECK_DETAIL_RE = re.compile(
    r"\(?\s*(?P<check_no>\d+)\s+NL\s+(?P<bank>.*?)\s+V\.?\s*D\.?\s*:\s*(?P<maturity>\d{1,2}[.:]\d{1,2}[.:]\d{2,4})",
    re.IGNORECASE,
)


def parse_statement_lines(
    lines: list[tuple[int, str]] | list[object],
    metadata: StatementMetadata | None = None,
    today: date | None = None,
) -> ParseResult:
    statement_metadata = metadata or StatementMetadata()
    checks: list[CheckRecord] = []
    warnings: list[ParseWarning] = []
    debug_rows: list[DebugRow] = []

    for item in lines:
        source_page = getattr(item, "page_number", item[0] if isinstance(item, tuple) else 0)
        raw_line = getattr(item, "text", item[1] if isinstance(item, tuple) else str(item))
        if not is_received_check_line(raw_line):
            if is_unsupported_check_summary_line(raw_line):
                warning_message = (
                    "Satır çek hareketi içeriyor ancak çek no, banka ve vade detayı bulunmuyor; "
                    "CheckRecord oluşturulmadı."
                )
                warnings.append(
                    ParseWarning(
                        source_page=int(source_page),
                        raw_line=raw_line,
                        warning_type="unsupported_check_summary",
                        message=warning_message,
                    )
                )
                debug_rows.append(
                    DebugRow(
                        source_page=int(source_page),
                        raw_line=raw_line,
                        parsed=False,
                        found_amounts=find_turkish_amounts(raw_line),
                        used_amount=None,
                        warning=warning_message,
                    )
                )
            continue

        record, line_warnings, debug_row = parse_received_check_line(raw_line, int(source_page), statement_metadata)
        warnings.extend(line_warnings)
        debug_rows.append(debug_row)
        if record is not None:
            checks.append(record)

    checks.sort(key=lambda item: (item.maturity_date, item.amount or Decimal("0"), item.transaction_date or date.min))
    summary = build_summary(checks, warnings, today=today)
    return ParseResult(
        statement_metadata=statement_metadata,
        checks=checks,
        warnings=warnings,
        summary=summary,
        debug_rows=debug_rows,
    )


def is_received_check_line(line: str) -> bool:
    normalized = normalize_for_match(line)
    return "ALINAN CEK" in normalized or "ALINAN ÇEK" in line.upper()


def is_unsupported_check_summary_line(line: str) -> bool:
    normalized = normalize_for_match(line)
    if "KREDI KARTI" in normalized or "TEK CEKIM" in normalized:
        return False
    return "CEK GIRIS" in normalized or ("BORC DEKONTU" in normalized and "CEKIN" in normalized)


def parse_received_check_line(
    raw_line: str,
    source_page: int,
    metadata: StatementMetadata,
) -> tuple[CheckRecord | None, list[ParseWarning], DebugRow]:
    warnings: list[ParseWarning] = []
    description_start = find_description_start(raw_line)
    prefix = raw_line[:description_start].strip() if description_start >= 0 else ""
    suffix = raw_line[description_start:].strip() if description_start >= 0 else raw_line.strip()
    raw_description = extract_raw_description(suffix)
    amounts = find_turkish_amounts(suffix)
    used_amount = amounts[0] if amounts else None

    prefix_values = parse_prefix(prefix)
    detail_match = CHECK_DETAIL_RE.search(suffix)
    check_no = detail_match.group("check_no") if detail_match else None
    raw_bank = detail_match.group("bank") if detail_match else None
    bank = normalize_bank_name(raw_bank) if raw_bank else None
    maturity_date = parse_maturity_date(detail_match.group("maturity")) if detail_match else None

    debug_row = DebugRow(
        source_page=source_page,
        raw_line=raw_line,
        parsed=False,
        found_check_no=check_no,
        found_bank=bank,
        found_maturity_date=maturity_date,
        found_amounts=amounts,
        used_amount=used_amount,
    )

    blocking_messages: list[str] = []
    if not check_no:
        blocking_messages.append("Çek no bulunamadı.")
    if not maturity_date:
        blocking_messages.append("Vade tarihi bulunamadı.")

    if blocking_messages:
        message = " ".join(blocking_messages)
        warnings.append(
            ParseWarning(
                source_page=source_page,
                raw_line=raw_line,
                warning_type="missing_required_field",
                message=message,
            )
        )
        debug_row.warning = message
        return None, warnings, debug_row

    parse_warning = None
    if used_amount is None:
        parse_warning = "Tutar net bulunamadı."
        warnings.append(
            ParseWarning(
                source_page=source_page,
                raw_line=raw_line,
                warning_type="missing_amount",
                message=parse_warning,
            )
        )

    record = CheckRecord(
        transaction_date=prefix_values.get("transaction_date"),
        document_date=prefix_values.get("document_date"),
        voucher_no=prefix_values.get("voucher_no"),
        document_no=prefix_values.get("document_no"),
        check_no=check_no or "",
        bank=bank or (raw_bank or "").strip(),
        maturity_date=maturity_date,
        maturity_month=maturity_date.strftime("%Y-%m"),
        amount=used_amount,
        customer_name=metadata.account_name,
        company_name=metadata.company_name,
        source_page=source_page,
        raw_description=raw_description,
        raw_line=raw_line,
        parse_warning=parse_warning,
    )
    debug_row.parsed = True
    debug_row.warning = parse_warning
    return record, warnings, debug_row


def parse_maturity_date(value: str | None) -> date | None:
    if not value:
        return None
    return parse_turkish_date(value.replace(":", "."))


def find_description_start(line: str) -> int:
    normalized = normalize_for_match(line)
    index = normalized.find("ALINAN CEK")
    return index


def extract_raw_description(suffix: str) -> str:
    first_amount = re.search(r"\s+" + DATE_RE.pattern, suffix)
    amount_match = re.search(r"\s+\d{1,3}(?:\.\d{3})*,\d{2}|\s+\d+,\d{2}", suffix)
    if amount_match:
        return suffix[: amount_match.start()].strip()
    if first_amount:
        return suffix[: first_amount.start()].strip()
    return suffix.strip()


def parse_prefix(prefix: str) -> dict[str, object]:
    tokens = prefix.split()
    values: dict[str, object] = {
        "transaction_date": None,
        "voucher_no": None,
        "document_date": None,
        "document_no": None,
    }
    if not tokens:
        return values

    values["transaction_date"] = parse_turkish_date(tokens[0])
    if len(tokens) > 1:
        values["voucher_no"] = tokens[1]

    date_token_indexes = [index for index, token in enumerate(tokens[2:], start=2) if parse_turkish_date(token)]
    if date_token_indexes:
        document_date_index = date_token_indexes[-1]
        values["document_date"] = parse_turkish_date(tokens[document_date_index])
        remaining = tokens[document_date_index + 1 :]
        if remaining:
            values["document_no"] = remaining[-1]
    elif len(tokens) > 2:
        values["document_no"] = tokens[-1]
    return values


def build_summary(checks: list[CheckRecord], warnings: list[ParseWarning], today: date | None = None) -> Summary:
    total_amount = sum((check.amount or Decimal("0") for check in checks), Decimal("0"))
    maturity_dates = [check.maturity_date for check in checks]
    bank_totals: dict[str, Decimal] = {}
    maturity_month_totals: dict[str, Decimal] = {}
    weekly_maturity_totals: dict[str, Decimal] = {}
    overdue_total = Decimal("0")
    due_in_7_days_total = Decimal("0")
    due_in_30_days_total = Decimal("0")

    for check in checks:
        amount = check.amount or Decimal("0")
        bank_totals[check.bank] = bank_totals.get(check.bank, Decimal("0")) + amount
        maturity_month_totals[check.maturity_month] = maturity_month_totals.get(check.maturity_month, Decimal("0")) + amount
        week = get_week_period(check.maturity_date)
        weekly_maturity_totals[week] = weekly_maturity_totals.get(week, Decimal("0")) + amount

        days = calculate_days_until_maturity(check.maturity_date, today)
        if days < 0:
            overdue_total += amount
        if 0 <= days <= 7:
            due_in_7_days_total += amount
        if 0 <= days <= 30:
            due_in_30_days_total += amount

    return Summary(
        total_count=len(checks),
        total_amount=total_amount,
        earliest_maturity_date=min(maturity_dates) if maturity_dates else None,
        latest_maturity_date=max(maturity_dates) if maturity_dates else None,
        bank_totals=bank_totals,
        maturity_month_totals=maturity_month_totals,
        weekly_maturity_totals=weekly_maturity_totals,
        overdue_total=overdue_total,
        due_in_7_days_total=due_in_7_days_total,
        due_in_30_days_total=due_in_30_days_total,
        warning_count=len(warnings),
    )
