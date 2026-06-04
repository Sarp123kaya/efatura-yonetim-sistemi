#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Müşteri bazında 2026 ekstre çekleri ↔ giden fatura karşılaştırması."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from backend.core.db import db
from backend.core.payment_import import normalize_text

YEAR_2026_START = date(2026, 1, 1)
YEAR_2026_END = date(2026, 12, 31)

CHECK_FIS_TURLERI: tuple[str, ...] = (
    "Çek Giriş",
)

_LATEST_BATCH_CTE = """
WITH latest_batch AS (
    SELECT DISTINCT ON (fabrika, COALESCE(cari_hesap_kodu, ''))
        fabrika,
        COALESCE(cari_hesap_kodu, '') AS hesap_key,
        source_file
    FROM factory_statements
    ORDER BY fabrika, COALESCE(cari_hesap_kodu, ''),
             created_at DESC NULLS LAST, id DESC
)
"""


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _check_amount(row: dict[str, Any]) -> Decimal:
    alacak = row.get("alacak")
    if alacak is not None and _to_decimal(alacak) > 0:
        return _to_decimal(alacak)
    return _to_decimal(row.get("borc"))


def _is_check_row(row: dict[str, Any]) -> bool:
    fis_turu = (row.get("fis_turu") or "").strip()
    if fis_turu in CHECK_FIS_TURLERI:
        return True
    lowered = fis_turu.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return "cek" in lowered and "giris" in lowered


def _month_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    return str(value)[:7]


def match_musteri_adi_to_firm(firm_name: str, musteri_adis: list[str]) -> tuple[list[str], str]:
    """Ekstre musteri_adi değerlerini firm_cards.name ile eşleştirir."""
    if not firm_name or not musteri_adis:
        return [], "none"

    norm_firm = normalize_text(firm_name)
    exact: list[str] = []
    partial: list[str] = []

    firm_tokens = _match_tokens(norm_firm)

    for raw in musteri_adis:
        name = (raw or "").strip()
        if not name:
            continue
        norm_name = normalize_text(name)
        name_tokens = _match_tokens(norm_name)
        if norm_name == norm_firm or name.strip().upper() == firm_name.strip().upper():
            exact.append(name)
        elif norm_name and norm_firm and (norm_name in norm_firm or norm_firm in norm_name):
            partial.append(name)
        elif _token_match(norm_firm, firm_tokens, norm_name, name_tokens):
            partial.append(name)

    if exact:
        return sorted(set(exact)), "exact_name"
    if partial:
        return sorted(set(partial)), "normalized_name"
    return [], "none"


def _match_tokens(normalized_name: str) -> set[str]:
    replacements = {
        "ins": "insaat",
        "insaat": "insaat",
        "tic": "ticaret",
        "san": "sanayi",
        "sti": "sirketi",
        "ltd": "limited",
        "as": "",
        "a": "",
    }
    ignored = {
        "",
        "ve",
        "limited",
        "sirketi",
        "anonim",
        "ticaret",
        "sanayi",
        "ltd",
        "sti",
    }
    tokens = set()
    for token in normalized_name.split():
        token = replacements.get(token, token)
        if token not in ignored and len(token) > 1:
            tokens.add(token)
    return tokens


def _first_match_token(normalized_name: str) -> str:
    for token in normalized_name.split():
        tokens = _match_tokens(token)
        if tokens:
            return next(iter(tokens))
    return ""


def _token_match(left_name: str, left: set[str], right_name: str, right: set[str]) -> bool:
    if not left or not right:
        return False
    smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
    common = smaller & larger
    left_first = _first_match_token(left_name)
    right_first = _first_match_token(right_name)
    if left_first and right_first and left_first not in common and right_first not in common:
        return False
    if len(smaller) == 1:
        return bool(common) and len(next(iter(common))) >= 5
    return len(common) >= 2


def _load_distinct_musteri_adis() -> list[str]:
    try:
        rows = db.query(
            f"""
            {_LATEST_BATCH_CTE}
            SELECT DISTINCT fs.musteri_adi
            FROM factory_statements fs
            INNER JOIN latest_batch lb
                ON fs.fabrika = lb.fabrika
               AND COALESCE(fs.cari_hesap_kodu, '') = lb.hesap_key
               AND fs.source_file = lb.source_file
            WHERE fs.tarih >= %s
              AND fs.tarih <= %s
              AND COALESCE(fs.musteri_adi, '') <> ''
            """,
            (YEAR_2026_START, YEAR_2026_END),
        )
    except Exception:
        return []
    return [str(r.get("musteri_adi") or "").strip() for r in rows if r.get("musteri_adi")]


def _load_ekstre_check_rows(musteri_adis: list[str]) -> list[dict[str, Any]]:
    if not musteri_adis:
        return []
    placeholders = ",".join(["%s"] * len(musteri_adis))
    try:
        rows = db.query(
            f"""
            {_LATEST_BATCH_CTE}
            SELECT fs.tarih, fs.fis_no, fs.fis_turu, fs.aciklama,
                   fs.alacak, fs.borc, fs.fabrika, fs.cari_hesap_kodu,
                   fs.musteri_adi, fs.source_file
            FROM factory_statements fs
            INNER JOIN latest_batch lb
                ON fs.fabrika = lb.fabrika
               AND COALESCE(fs.cari_hesap_kodu, '') = lb.hesap_key
               AND fs.source_file = lb.source_file
            WHERE fs.tarih >= %s
              AND fs.tarih <= %s
              AND fs.musteri_adi IN ({placeholders})
            ORDER BY fs.tarih DESC, fs.fis_no DESC
            """,
            (YEAR_2026_START, YEAR_2026_END, *musteri_adis),
        )
    except Exception:
        return []

    return [dict(r) for r in rows if _is_check_row(r) and _check_amount(r) > 0]


def _load_outgoing_invoices_2026(tax_id: str) -> list[dict[str, Any]]:
    if not tax_id:
        return []
    try:
        return db.query(
            """
            SELECT id, invoice_no, issue_date, total_tl, taxable_amount, description
            FROM outgoing_invoices
            WHERE raw_json->>'firmVknNo' = %s
              AND issue_date >= %s
              AND issue_date <= %s
            ORDER BY issue_date DESC, invoice_no DESC
            """,
            (tax_id, YEAR_2026_START, YEAR_2026_END),
        )
    except Exception:
        return []


@dataclass
class Customer2026Comparison:
    year: int = 2026
    invoice_count: int = 0
    invoice_total: Decimal = field(default_factory=lambda: Decimal("0"))
    ekstre_check_count: int = 0
    ekstre_check_total: Decimal = field(default_factory=lambda: Decimal("0"))
    difference: Decimal = field(default_factory=lambda: Decimal("0"))
    monthly: list[dict[str, Any]] = field(default_factory=list)
    ekstre_checks: list[dict[str, Any]] = field(default_factory=list)
    invoices: list[dict[str, Any]] = field(default_factory=list)
    match_method: str = "none"
    matched_musteri_adis: list[str] = field(default_factory=list)
    tables_available: bool = True

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "invoice_count": self.invoice_count,
            "invoice_total": self.invoice_total,
            "ekstre_check_count": self.ekstre_check_count,
            "ekstre_check_total": self.ekstre_check_total,
            "difference": self.difference,
            "monthly": self.monthly,
            "ekstre_checks": self.ekstre_checks,
            "invoices": self.invoices,
            "match_method": self.match_method,
            "matched_musteri_adis": self.matched_musteri_adis,
            "tables_available": self.tables_available,
        }


def _build_monthly_rows(
    invoices: list[dict[str, Any]],
    ekstre_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    inv_by_month: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"invoice_count": 0, "invoice_total": Decimal("0")}
    )
    chk_by_month: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"check_count": 0, "check_total": Decimal("0")}
    )

    for inv in invoices:
        month = _month_key(inv.get("issue_date"))
        if not month:
            continue
        inv_by_month[month]["invoice_count"] += 1
        inv_by_month[month]["invoice_total"] += _to_decimal(inv.get("total_tl"))

    for row in ekstre_checks:
        month = _month_key(row.get("tarih"))
        if not month:
            continue
        chk_by_month[month]["check_count"] += 1
        chk_by_month[month]["check_total"] += _check_amount(row)

    months = sorted(set(inv_by_month) | set(chk_by_month), reverse=True)
    out: list[dict[str, Any]] = []
    for month in months:
        inv_part = inv_by_month[month]
        chk_part = chk_by_month[month]
        inv_total = inv_part["invoice_total"]
        chk_total = chk_part["check_total"]
        out.append(
            {
                "month": month,
                "invoice_count": inv_part["invoice_count"],
                "invoice_total": inv_total,
                "check_count": chk_part["check_count"],
                "check_total": chk_total,
                "difference": inv_total - chk_total,
            }
        )
    return out


def build_customer_2026_comparison(
    firm_name: str,
    tax_id: str,
    *,
    musteri_adis: Optional[list[str]] = None,
) -> Customer2026Comparison:
    """Tek müşteri için 2026 ekstre çek ↔ giden fatura karşılaştırması."""
    result = Customer2026Comparison()
    invoices = _load_outgoing_invoices_2026(tax_id or "")
    result.invoices = invoices
    result.invoice_count = len(invoices)
    result.invoice_total = sum(
        (_to_decimal(inv.get("total_tl")) for inv in invoices),
        Decimal("0"),
    )

    all_musteri_adis = musteri_adis if musteri_adis is not None else _load_distinct_musteri_adis()
    matched, method = match_musteri_adi_to_firm(firm_name or "", all_musteri_adis)
    result.match_method = method
    result.matched_musteri_adis = matched

    if not matched:
        result.difference = result.invoice_total
        result.monthly = _build_monthly_rows(invoices, [])
        return result

    ekstre_checks = _load_ekstre_check_rows(matched)
    for row in ekstre_checks:
        row["tutar"] = _check_amount(row)
    result.ekstre_checks = ekstre_checks
    result.ekstre_check_count = len(ekstre_checks)
    result.ekstre_check_total = sum(
        (_check_amount(row) for row in ekstre_checks),
        Decimal("0"),
    )
    result.difference = result.invoice_total - result.ekstre_check_total
    result.monthly = _build_monthly_rows(invoices, ekstre_checks)
    return result


def load_ekstre_check_summaries_for_all_customers(
    customer_names: list[str],
) -> dict[str, dict[str, Any]]:
    """Müşteriler listesi — firma adına göre 2026 ekstre çek özeti."""
    empty = {
        "ekstre_cek_adedi": 0,
        "ekstre_cek_toplam": Decimal("0"),
        "fatura_toplam": Decimal("0"),
        "fark": Decimal("0"),
    }
    musteri_adis = _load_distinct_musteri_adis()
    if not musteri_adis:
        return {name: dict(empty) for name in customer_names}

    try:
        rows = db.query(
            f"""
            {_LATEST_BATCH_CTE}
            SELECT fs.musteri_adi, fs.tarih, fs.fis_turu, fs.alacak, fs.borc
            FROM factory_statements fs
            INNER JOIN latest_batch lb
                ON fs.fabrika = lb.fabrika
               AND COALESCE(fs.cari_hesap_kodu, '') = lb.hesap_key
               AND fs.source_file = lb.source_file
            WHERE fs.tarih >= %s
              AND fs.tarih <= %s
              AND COALESCE(fs.musteri_adi, '') <> ''
            """,
            (YEAR_2026_START, YEAR_2026_END),
        )
    except Exception:
        return {name: dict(empty) for name in customer_names}

    by_musteri: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not _is_check_row(row):
            continue
        amount = _check_amount(row)
        if amount <= 0:
            continue
        name = str(row.get("musteri_adi") or "").strip()
        if name:
            by_musteri[name].append(dict(row))

    out: dict[str, dict[str, Any]] = {}
    for customer_name in customer_names:
        matched, _ = match_musteri_adi_to_firm(customer_name, list(by_musteri.keys()))
        check_rows: list[dict[str, Any]] = []
        for matched_name in matched:
            check_rows.extend(by_musteri.get(matched_name, []))
        total = sum((_check_amount(r) for r in check_rows), Decimal("0"))
        out[customer_name] = {
            "ekstre_cek_adedi": len(check_rows),
            "ekstre_cek_toplam": total,
            "fatura_toplam": Decimal("0"),
            "fark": Decimal("0"),
        }
    return out
