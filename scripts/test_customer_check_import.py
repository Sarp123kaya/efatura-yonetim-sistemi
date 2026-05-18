#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit checks for customer check import helpers."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_endpoints import payment_endpoint_verification
from backend.core.isbasi_client import IsbasiApiClient
from backend.core.check_pool import (
    CheckIsbasiComparison,
    CheckSourceType,
    ReviewStatus,
    StatementMetadata,
    parse_statement_lines,
    transfer_candidate_records,
)
from backend.core.payment_import import (
    CustomerCheckRow,
    FirmCard,
    build_dry_run,
    match_check_to_firm,
    normalize_tax_id,
    normalize_text,
)


def test_normalization() -> None:
    assert normalize_tax_id("123 456 7890") == "1234567890"
    assert normalize_text("İSTANBUL Çelik A.Ş.") == "istanbul celik as"


def test_tax_id_match() -> None:
    check = CustomerCheckRow(
        source_row=2,
        firm_name="ACME LTD",
        tax_id="1234567890",
        check_number="C-1",
        due_date=date(2026, 1, 31),
        amount=Decimal("100.00"),
    )
    firm = FirmCard(
        id="f1",
        code="ACME",
        name="ACME LIMITED",
        display_name="ACME LTD",
        firm_type="Customer",
        tax_id="1234567890",
    )
    result = match_check_to_firm(check, [firm])
    assert result.status == "matched"
    assert result.firm is firm
    assert result.score >= 90


def test_duplicate_dry_run() -> None:
    check = CustomerCheckRow(
        source_row=2,
        firm_name="ACME LTD",
        tax_id="1234567890",
        check_number="C-1",
        due_date=date(2026, 1, 31),
        amount=Decimal("100.00"),
    )
    firm = FirmCard(
        id="f1",
        code="ACME",
        name="ACME LTD",
        display_name="",
        firm_type="Customer",
        tax_id="1234567890",
    )
    report = build_dry_run([check, check], [firm])
    assert report.summary["total"] == 2
    assert report.summary["matched"] == 1
    assert report.summary["duplicate"] == 1


def test_parse_errors_mark_invalid() -> None:
    check = CustomerCheckRow(
        source_row=2,
        firm_name="ACME LTD",
        tax_id="1234567890",
        check_number="C-1",
        due_date=date(1900, 1, 1),
        amount=Decimal("0.00"),
        parse_errors=["gecersiz tarih"],
    )
    report = build_dry_run([check], [])
    assert report.summary["invalid"] == 1
    assert report.rows[0].errors == ["gecersiz tarih", "tutar sifirdan buyuk olmali"]


def test_payment_endpoint_is_not_verified() -> None:
    verification = payment_endpoint_verification()
    assert verification["verified"] is False
    assert verification["endpoint"] is None


def test_customer_activity_local_filter() -> None:
    client = IsbasiApiClient(api_key="x", username="u", password="p")
    rows = [
        {
            "id": "inv1",
            "firm": {"firmId": "f1", "name": "ACME LTD", "firmCode": "ACME"},
            "firmVknNo": "1234567890",
            "paymentStatus": True,
        },
        {
            "id": "inv2",
            "firm": {"firmId": "f2", "name": "OTHER LTD", "firmCode": "OTHER"},
            "firmVknNo": "9999999999",
            "paymentStatus": False,
        },
    ]
    matched = client._filter_customer_rows(rows, firm_id="f1", tax_id="1234567890", firm_name="ACME LTD")
    assert [row["id"] for row in matched] == ["inv1"]


def test_statement_line_parser() -> None:
    metadata = StatementMetadata(account_name="ACME LTD", source_filename="muavin.pdf")
    records, warnings = parse_statement_lines(
        [(1, "ALINAN ÇEK (123456 NL HALKBANK VD: 31.01.2026) 1.250,50")],
        metadata,
        "00000000-0000-0000-0000-000000000000",
        CheckSourceType.PDF,
    )
    assert len(records) == 1
    assert warnings == []
    assert records[0].check_no == "123456"
    assert records[0].bank == "Halkbank"
    assert records[0].customer_name == "ACME LTD"


def test_transfer_candidates_only_approved_missing_matched() -> None:
    firm = FirmCard(
        id="f1",
        code="ACME",
        name="ACME LTD",
        display_name="",
        firm_type="Customer",
        tax_id="1234567890",
    )
    records, _warnings = parse_statement_lines(
        [(1, "ALINAN ÇEK (123456 NL HALKBANK VD: 31.01.2026) 1.250,50")],
        StatementMetadata(account_name="ACME LTD"),
        "00000000-0000-0000-0000-000000000000",
        CheckSourceType.PDF,
    )
    comparison = CheckIsbasiComparison(
        record=records[0],
        match=match_check_to_firm(
            CustomerCheckRow(
                source_row=1,
                firm_name="ACME LTD",
                tax_id="1234567890",
                check_number="123456",
                due_date=date(2026, 1, 31),
                amount=Decimal("1250.50"),
            ),
            [firm],
        ),
        isbasi_status="missing_in_isbasi",
    )
    assert records[0].review_status == ReviewStatus.APPROVED
    assert len(transfer_candidate_records([comparison])) == 1


def main() -> int:
    test_normalization()
    test_tax_id_match()
    test_duplicate_dry_run()
    test_parse_errors_mark_invalid()
    test_payment_endpoint_is_not_verified()
    test_customer_activity_local_filter()
    test_statement_line_parser()
    test_transfer_candidates_only_approved_missing_matched()
    print("customer check import tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
