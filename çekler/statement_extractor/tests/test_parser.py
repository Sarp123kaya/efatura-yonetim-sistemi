from __future__ import annotations

from datetime import date
from decimal import Decimal

from statement_extractor.src.models import StatementMetadata
from statement_extractor.src.parser import parse_statement_lines


METADATA = StatementMetadata(
    company_name="D KAYA İNŞAAT TAAHHÜT TİC.VE İHR.İTH. LTD.ŞTİ.",
    account_code="120.01.080",
    account_name="MUHAMMET EKREM ÖZKUL",
)


def parse_one(line: str):
    result = parse_statement_lines([(1, line)], metadata=METADATA, today=date(2026, 5, 3))
    assert len(result.checks) == 1
    return result.checks[0]


def test_parses_halkbank_received_check_with_two_amounts() -> None:
    record = parse_one(
        "20.01.2026 000000011 20.01.2026 2001 ALINAN ÇEK "
        "(5526515 NL HALKBANK VD:25.05.26) 2.550.000,00 468.904,39 A"
    )
    assert record.check_no == "5526515"
    assert record.bank == "Halkbank"
    assert record.maturity_date == date(2026, 5, 25)
    assert record.amount == Decimal("2550000.00")


def test_parses_denizbank_received_check() -> None:
    record = parse_one(
        "9.02.2026 000000029 09.02.2026 0902 ALINAN ÇEK "
        "(2885546 NL DENİZBANK VD:30.04.26) 850.000,00 548.576,75 A"
    )
    assert record.check_no == "2885546"
    assert record.bank == "Denizbank"
    assert record.maturity_date == date(2026, 4, 30)
    assert record.amount == Decimal("850000.00")


def test_parses_without_space_before_parenthesis() -> None:
    record = parse_one(
        "20.02.2026 000000050 20.02.2026 2002 ALINAN ÇEK"
        "(4403802 NL HALKBANK VD:30.06.26) 1.400.000,00 425.357,61 A"
    )
    assert record.check_no == "4403802"
    assert record.bank == "Halkbank"
    assert record.maturity_date == date(2026, 6, 30)
    assert record.amount == Decimal("1400000.00")


def test_parses_late_maturity_halkbank_check() -> None:
    record = parse_one(
        "13.04.2026 000000093 13.04.2026 1304 ALINAN ÇEK "
        "(4597493 NL HALKBANK VD:30.09.26) 1.200.000,00 1.293.731,22 A"
    )
    assert record.check_no == "4597493"
    assert record.bank == "Halkbank"
    assert record.maturity_date == date(2026, 9, 30)
    assert record.amount == Decimal("1200000.00")


def test_parses_unaccented_received_check_and_full_year_maturity() -> None:
    record = parse_one(
        "20.01.2026 000000011 20.01.2026 2001 ALINAN CEK "
        "(5526515 NL HALK BANK VD:25.05.2026) 2.550.000,00 468.904,39 A"
    )
    assert record.bank == "Halkbank"
    assert record.maturity_date == date(2026, 5, 25)


def test_parses_dotted_vd_label_and_full_year_maturity() -> None:
    record = parse_one(
        "05.05.2025 000000122 05.05.2025 0505 ALINAN ÇEK "
        "(1986659 NL DENİZBANK V.D:03.09.2025) 350.000,00"
    )
    assert record.check_no == "1986659"
    assert record.bank == "Denizbank"
    assert record.maturity_date == date(2025, 9, 3)


def test_parses_colon_separated_maturity_date() -> None:
    record = parse_one(
        "08.12.2025 000000454 08.12.2025 0812 ALINAN ÇEK "
        "(3873534 NL HALKBANK VD:15:04.26) 4.250.000,00"
    )
    assert record.check_no == "3873534"
    assert record.bank == "Halkbank"
    assert record.maturity_date == date(2026, 4, 15)


def test_parses_title_case_received_check_and_unaccented_bank() -> None:
    record = parse_one(
        "9.02.2026 000000029 09.02.2026 0902 Alınan Çek "
        "(2885546 NL DENIZBANK VD:30.04.26) 850.000,00 548.576,75 A"
    )
    assert record.bank == "Denizbank"
    assert record.amount == Decimal("850000.00")


def test_uses_first_amount_as_check_amount() -> None:
    record = parse_one(
        "20.02.2026 000000050 20.02.2026 2002 ALINAN ÇEK "
        "(4403802 NL HALKBANK VD:30.06.26) 1.400.000,00 999.999,99 A"
    )
    assert record.amount == Decimal("1400000.00")


def test_sorts_multiple_checks_by_maturity_date() -> None:
    result = parse_statement_lines(
        [
            (
                1,
                "13.04.2026 000000093 13.04.2026 1304 ALINAN ÇEK "
                "(4597493 NL HALKBANK VD:30.09.26) 1.200.000,00 1.293.731,22 A",
            ),
            (
                1,
                "9.02.2026 000000029 09.02.2026 0902 ALINAN ÇEK "
                "(2885546 NL DENİZBANK VD:30.04.26) 850.000,00 548.576,75 A",
            ),
        ],
        metadata=METADATA,
        today=date(2026, 5, 3),
    )
    assert [record.check_no for record in result.checks] == ["2885546", "4597493"]


def test_returns_empty_result_when_no_received_check_exists() -> None:
    result = parse_statement_lines([(1, "20.01.2026 000000011 EFT 2.550.000,00")], metadata=METADATA)
    assert result.checks == []
    assert result.summary.total_count == 0


def test_missing_check_no_or_maturity_is_warning_and_not_record() -> None:
    result = parse_statement_lines(
        [(1, "20.01.2026 000000011 20.01.2026 2001 ALINAN ÇEK (HALKBANK) 2.550.000,00")],
        metadata=METADATA,
    )
    assert result.checks == []
    assert result.warnings[0].warning_type == "missing_required_field"


def test_unsupported_check_summary_is_warning_and_not_record() -> None:
    result = parse_statement_lines(
        [(3, "17.03.2026 000051 Çek Giriş 3 ADET ÇEK 1.900.000,00 6.788.869,51 (A)")],
        metadata=METADATA,
    )
    assert result.checks == []
    assert result.warnings[0].warning_type == "unsupported_check_summary"
    assert result.debug_rows[0].source_page == 3
