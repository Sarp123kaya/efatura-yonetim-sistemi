#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Son ekstre yüklemesinden sonra gelen fabrika alış faturalarına göre
tahmini cari bakiye (canlı bakiye) hesaplar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from backend.core.db import db
from backend.core.ekstre_fatura_compare import _fabrika_vknleri
from backend.core.factory_statement_parser import _signed_bakiye

ZERO = Decimal("0")


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _unsigned_from_signed(signed: Decimal) -> tuple[Decimal, str]:
    if signed >= ZERO:
        return signed, "A"
    return abs(signed), "B"


def _statement_filters(
    fabrika: str,
    cari_hesap_kodu: Optional[str],
    alias: str = "",
) -> tuple[list[str], list[Any]]:
    prefix = f"{alias}." if alias else ""
    filters = [f"{prefix}fabrika = %s"]
    params: list[Any] = [fabrika]
    if cari_hesap_kodu is not None:
        filters.append(f"COALESCE({prefix}cari_hesap_kodu, '') = %s")
        params.append(cari_hesap_kodu)
    return filters, params


@dataclass
class BalanceAdjustment:
    invoice_id: str
    issue_date: Optional[date]
    amount: Decimal
    running_balance: Decimal
    running_balance_yon: str


@dataclass
class LiveBalanceResult:
    fabrika: str
    cari_hesap_kodu: str = ""
    has_baseline: bool = False
    message: str = ""
    baseline_balance: Optional[Decimal] = None
    baseline_balance_yon: Optional[str] = None
    baseline_signed: Optional[Decimal] = None
    baseline_date: Optional[date] = None
    baseline_source_file: Optional[str] = None
    adjustment_count: int = 0
    adjustments: list[BalanceAdjustment] = field(default_factory=list)
    projected_balance: Optional[Decimal] = None
    projected_balance_yon: Optional[str] = None
    projected_signed: Optional[Decimal] = None


def _find_latest_baseline_row(
    fabrika: str,
    cari_hesap_kodu: Optional[str],
) -> Optional[dict[str, Any]]:
    filters, params = _statement_filters(fabrika, cari_hesap_kodu)
    where = " AND ".join(filters)
    sub_filters = [
        f.replace("fabrika", "fs2.fabrika").replace("cari_hesap_kodu", "fs2.cari_hesap_kodu")
        for f in filters
    ]
    latest = db.query_one(
        f"""
        SELECT source_file
        FROM factory_statements fs2
        WHERE {" AND ".join(sub_filters)}
        ORDER BY fs2.created_at DESC NULLS LAST, fs2.id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    if not latest or not latest.get("source_file"):
        return None

    source_file = latest["source_file"]
    batch_filters = filters + ["source_file = %s"]
    batch_params = params + [source_file]
    batch_where = " AND ".join(batch_filters)
    rows = db.query(
        f"""
        SELECT tarih, bakiye, bakiye_yon, source_file, id
        FROM factory_statements
        WHERE {batch_where}
        ORDER BY tarih ASC, id ASC
        """,
        tuple(batch_params),
    )
    if not rows:
        return None

    baseline_row: Optional[dict[str, Any]] = None
    for row in rows:
        if row.get("bakiye") is not None and row.get("bakiye_yon"):
            baseline_row = row
    if baseline_row is None:
        baseline_row = rows[-1]
    baseline_row = dict(baseline_row)
    baseline_row["source_file"] = source_file
    return baseline_row


def _load_incoming_after_baseline(
    fabrika: str,
    baseline_date: date,
) -> list[dict[str, Any]]:
    vkns = list(_fabrika_vknleri(fabrika))
    if not vkns:
        return []

    placeholders = ",".join(["%s"] * len(vkns))
    params: list[Any] = list(vkns) + [baseline_date]
    try:
        return db.query(
            f"""
            SELECT invoice_id, issue_date, amount, supplier, supplier_tckn_vkn
            FROM incoming_invoices
            WHERE supplier_tckn_vkn IN ({placeholders})
              AND COALESCE(issue_date::date, created_at::date) > %s
            ORDER BY issue_date ASC NULLS LAST, invoice_id ASC
            """,
            tuple(params),
        )
    except Exception:
        return []


def compute_live_balance(
    fabrika: str,
    cari_hesap_kodu: Optional[str] = None,
) -> LiveBalanceResult:
    """
    Son ekstre yüklemesinin kapanış bakiyesinden itibaren gelen fabrika
    alış faturalarını düşerek tahmini güncel bakiyeyi hesaplar.

    İşaretli bakiye (_signed_bakiye):
      A (Alacaklı) → pozitif, B (Borçlu) → negatif.
    Her yeni alış faturası borç artışıdır → signed -= tutar.
    """
    hesap = cari_hesap_kodu or ""
    result = LiveBalanceResult(fabrika=fabrika, cari_hesap_kodu=hesap)

    try:
        baseline_row = _find_latest_baseline_row(fabrika, cari_hesap_kodu or None)
    except Exception as exc:
        result.message = f"Bakiye hesaplanamadı: {exc}"
        return result

    if not baseline_row:
        result.message = "Önce güncel ekstre PDF yükleyin."
        return result

    bakiye = _to_decimal(baseline_row.get("bakiye"))
    yon = (baseline_row.get("bakiye_yon") or "").strip().upper()
    baseline_date = _to_date(baseline_row.get("tarih"))

    if bakiye is None or yon not in ("A", "B"):
        result.message = "Son ekstre satırında bakiye bilgisi bulunamadı."
        return result

    signed = _signed_bakiye(bakiye, yon)
    unsigned, unsigned_yon = _unsigned_from_signed(signed)

    result.has_baseline = True
    result.baseline_balance = unsigned
    result.baseline_balance_yon = unsigned_yon
    result.baseline_signed = signed
    result.baseline_date = baseline_date
    result.baseline_source_file = baseline_row.get("source_file")

    if baseline_date is None:
        result.message = "Ekstre baz tarihi okunamadı."
        return result

    incoming = _load_incoming_after_baseline(fabrika, baseline_date)
    running = signed
    adjustments: list[BalanceAdjustment] = []

    for inv in incoming:
        amount = _to_decimal(inv.get("amount"))
        if amount is None or amount <= ZERO:
            continue
        running -= amount
        bal, bal_yon = _unsigned_from_signed(running)
        adjustments.append(
            BalanceAdjustment(
                invoice_id=str(inv.get("invoice_id") or ""),
                issue_date=_to_date(inv.get("issue_date")),
                amount=amount,
                running_balance=bal,
                running_balance_yon=bal_yon,
            )
        )

    result.adjustments = adjustments
    result.adjustment_count = len(adjustments)
    result.projected_signed = running
    proj_bal, proj_yon = _unsigned_from_signed(running)
    result.projected_balance = proj_bal
    result.projected_balance_yon = proj_yon

    if adjustments:
        result.message = (
            f"Son ekstre yüklemesinden ({baseline_date.strftime('%d.%m.%Y')}) "
            f"sonra {len(adjustments)} fatura düşüldü."
        )
    else:
        result.message = "Son ekstre tarihinden sonra yeni fatura yok; tahmini bakiye ekstre ile aynı."

    return result
