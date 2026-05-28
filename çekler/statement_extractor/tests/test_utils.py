from __future__ import annotations

from datetime import date
from decimal import Decimal

from statement_extractor.src.utils import (
    calculate_days_until_maturity,
    calculate_maturity_status,
    format_try_amount,
    get_week_period,
    normalize_bank_name,
    parse_turkish_amount,
    parse_turkish_date,
    safe_filename,
)


def test_parse_turkish_amount() -> None:
    assert parse_turkish_amount("2.550.000,00") == Decimal("2550000.00")


def test_parse_turkish_date_short_year_as_2000s() -> None:
    assert parse_turkish_date("25.05.26") == date(2026, 5, 25)


def test_normalize_bank_name_aliases() -> None:
    assert normalize_bank_name("HALK BANKASI") == "Halkbank"
    assert normalize_bank_name("QNB FİNANSBANK") == "QNB Finansbank"
    assert normalize_bank_name("TÜRKİYE İŞ BANKASI") == "İş Bankası"


def test_maturity_helpers() -> None:
    today = date(2026, 5, 3)
    assert calculate_days_until_maturity(date(2026, 5, 10), today) == 7
    assert calculate_maturity_status(date(2026, 5, 2), today) == "Vadesi Geçmiş"
    assert get_week_period(date(2026, 5, 10)) == "2026-W19"


def test_filename_and_amount_formatting() -> None:
    assert safe_filename("çek listesi.pdf") == "cek_listesi"
    assert format_try_amount(Decimal("2550000")) == "2.550.000,00 TL"
