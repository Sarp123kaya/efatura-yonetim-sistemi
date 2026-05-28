from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


TURKISH_AMOUNT_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b")


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_for_match(value: str) -> str:
    return strip_accents(value).upper().replace("İ", "I").replace("ı", "I")


def parse_turkish_amount(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = value.strip().replace(" ", "")
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def find_turkish_amounts(value: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    for match in TURKISH_AMOUNT_RE.findall(value):
        amount = parse_turkish_amount(match)
        if amount is not None:
            amounts.append(amount)
    return amounts


def parse_turkish_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt == "%d.%m.%y" and parsed.year < 2000:
                return parsed.replace(year=parsed.year + 100)
            return parsed
        except ValueError:
            continue
    return None


def normalize_bank_name(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"\s+", " ", value).strip()
    key = normalize_for_match(compact)
    key = re.sub(r"[^A-Z0-9 ]+", "", key)
    key = re.sub(r"\s+", " ", key).strip()

    bank_patterns: list[tuple[tuple[str, ...], str]] = [
        (("HALKBANK", "HALK BANK", "HALK BANKASI"), "Halkbank"),
        (("DENIZBANK",), "Denizbank"),
        (("ZIRAAT BANKASI", "ZIRAAT"), "Ziraat Bankası"),
        (("GARANTI BANKASI", "GARANTI"), "Garanti BBVA"),
        (("YAPI KREDI", "YAPIKREDI"), "Yapı Kredi"),
        (("TURKIYE IS BANKASI", "IS BANKASI", "ISBANK"), "İş Bankası"),
        (("AKBANK",), "Akbank"),
        (("QNB FINANSBANK", "FINANSBANK", "QNB"), "QNB Finansbank"),
    ]
    for aliases, normalized in bank_patterns:
        if any(alias in key for alias in aliases):
            return normalized
    return compact.title()


def calculate_days_until_maturity(maturity_date: date, today: date | None = None) -> int:
    reference = today or date.today()
    return (maturity_date - reference).days


def calculate_maturity_status(maturity_date: date, today: date | None = None) -> str:
    days = calculate_days_until_maturity(maturity_date, today)
    if days < 0:
        return "Vadesi Geçmiş"
    if days == 0:
        return "Bugün"
    if days <= 7:
        return "7 Gün İçinde"
    if days <= 30:
        return "30 Gün İçinde"
    return "İleri Vade"


def get_week_period(maturity_date: date) -> str:
    iso_year, iso_week, _ = maturity_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def safe_filename(value: str, default: str = "output") -> str:
    stem = Path(value).stem if value else default
    stem = strip_accents(stem)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or default


def format_try_amount(value: Decimal | int | float | None) -> str:
    if value is None:
        value = Decimal("0")
    amount = Decimal(str(value))
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".") + " TL"
