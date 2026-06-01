#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrika ekstre satırları ile gelen e-faturaları karşılaştırır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from backend.core.purchase_invoice_importer import FACTORY_SUPPLIERS, FACTORY_VKN_SET

FATURA_FIS_TURLERI = frozenset(
    {
        "Toptan Satış Faturası",
        "Alınan Hizmet Faturası",
        "Verilen Hizmet Faturası",
    }
)

AMOUNT_TOLERANCE = Decimal("0.02")
INVOICE_REF_RE = re.compile(r"[A-Za-z]{2,5}[\d]{4,}|[A-Z]{3,}[\d]{6,}")


def _fabrika_vknleri(fabrika: str) -> set[str]:
    f = fabrika.upper()
    if "AK G" in f or "AKG" in f:
        return {FACTORY_SUPPLIERS["AKG"]["vkn"]}
    if "FULLBOARD" in f or "FLL" in f:
        return {FACTORY_SUPPLIERS["FLL"]["vkn"]}
    return set(FACTORY_VKN_SET)


def _normalize_ref(value: str) -> str:
    return re.sub(r"[\s\-_/\.]", "", (value or "")).upper()


def _row_amount(row: dict[str, Any]) -> Optional[Decimal]:
    borc = row.get("borc")
    alacak = row.get("alacak")
    if borc is not None and borc != 0:
        return Decimal(str(borc))
    if alacak is not None and alacak != 0:
        return Decimal(str(alacak))
    return None


def _invoice_amount(inv: dict[str, Any]) -> Optional[Decimal]:
    val = inv.get("amount")
    if val is None:
        return None
    return Decimal(str(val))


def _issue_date_only(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None


def _extract_refs(fis_no: str, aciklama: str) -> list[str]:
    refs: list[str] = []
    for raw in (fis_no, aciklama):
        if not raw:
            continue
        norm = _normalize_ref(raw)
        if norm and norm not in refs:
            refs.append(norm)
        for m in INVOICE_REF_RE.findall(raw):
            n = _normalize_ref(m)
            if n and n not in refs:
                refs.append(n)
    return refs


@dataclass
class MatchedPair:
    ekstre: dict[str, Any]
    fatura: dict[str, Any]
    match_kind: str  # ref | amount_date
    amount_ok: bool
    date_ok: bool


@dataclass
class EkstreFaturaComparison:
    fabrika: str
    cari_hesap_kodu: str = ""
    source_file: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    ekstre_fatura_satirlari: int = 0
    gelen_fatura_adedi: int = 0
    matched: list[MatchedPair] = field(default_factory=list)
    ekstre_only: list[dict[str, Any]] = field(default_factory=list)
    fatura_only: list[dict[str, Any]] = field(default_factory=list)
    amount_mismatch: list[MatchedPair] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def tam_eslesme(self) -> bool:
        return (
            not self.ekstre_only
            and not self.fatura_only
            and not self.amount_mismatch
            and self.ekstre_fatura_satirlari > 0
        )


def compare_ekstre_with_incoming(
    ekstre_rows: list[dict[str, Any]],
    incoming_rows: list[dict[str, Any]],
    *,
    fabrika: str,
    cari_hesap_kodu: str = "",
    source_file: Optional[str] = None,
    only_latest_upload: bool = True,
) -> EkstreFaturaComparison:
    """Ekstre fatura satırlarını gelen faturalarla eşleştirir."""
    result = EkstreFaturaComparison(
        fabrika=fabrika,
        cari_hesap_kodu=cari_hesap_kodu,
        source_file=source_file,
    )

    rows = list(ekstre_rows)
    if only_latest_upload and rows:
        latest = max(
            (r.get("source_file") or "" for r in rows),
            key=lambda s: str(s),
        )
        if latest:
            rows = [r for r in rows if (r.get("source_file") or "") == latest]
            result.source_file = latest

    fatura_rows = [
        r
        for r in rows
        if (r.get("fis_turu") or "") in FATURA_FIS_TURLERI
        or "fatura" in (r.get("fis_turu") or "").lower()
    ]
    result.ekstre_fatura_satirlari = len(fatura_rows)

    if not fatura_rows:
        result.warnings.append("Ekstrede fatura türü işlem satırı bulunamadı.")
        return result

    dates = [d for d in (_issue_date_only(r.get("tarih")) for r in fatura_rows) if d]
    if dates:
        result.date_from = min(dates)
        result.date_to = max(dates)

    inv_by_ref: dict[str, dict[str, Any]] = {}
    for inv in incoming_rows:
        iid = _normalize_ref(str(inv.get("invoice_id") or ""))
        if iid:
            inv_by_ref[iid] = inv

    used_invoices: set[str] = set()
    unmatched_ekstre: list[dict[str, Any]] = []

    for row in fatura_rows:
        refs = _extract_refs(str(row.get("fis_no") or ""), str(row.get("aciklama") or ""))
        ekstre_amt = _row_amount(row)
        ekstre_date = _issue_date_only(row.get("tarih"))

        matched_inv: Optional[dict[str, Any]] = None
        match_kind = ""

        for ref in refs:
            if ref in inv_by_ref:
                matched_inv = inv_by_ref[ref]
                match_kind = "ref"
                break

        if matched_inv is None and ekstre_amt is not None and ekstre_date is not None:
            for inv in incoming_rows:
                iid = str(inv.get("invoice_id") or "")
                if iid in used_invoices:
                    continue
                inv_amt = _invoice_amount(inv)
                inv_date = _issue_date_only(inv.get("issue_date"))
                if (
                    inv_amt is not None
                    and inv_date == ekstre_date
                    and abs(inv_amt - ekstre_amt) <= AMOUNT_TOLERANCE
                ):
                    matched_inv = inv
                    match_kind = "amount_date"
                    break

        if matched_inv is None:
            unmatched_ekstre.append(row)
            continue

        iid = str(matched_inv.get("invoice_id") or "")
        used_invoices.add(iid)

        inv_amt = _invoice_amount(matched_inv)
        inv_date = _issue_date_only(matched_inv.get("issue_date"))
        amount_ok = (
            ekstre_amt is None
            or inv_amt is None
            or abs(ekstre_amt - inv_amt) <= AMOUNT_TOLERANCE
        )
        date_ok = ekstre_date is None or inv_date is None or ekstre_date == inv_date

        pair = MatchedPair(
            ekstre=row,
            fatura=matched_inv,
            match_kind=match_kind,
            amount_ok=amount_ok,
            date_ok=date_ok,
        )
        if amount_ok and date_ok:
            result.matched.append(pair)
        else:
            result.amount_mismatch.append(pair)

    result.ekstre_only = unmatched_ekstre
    result.fatura_only = [
        inv
        for inv in incoming_rows
        if str(inv.get("invoice_id") or "") not in used_invoices
    ]
    result.gelen_fatura_adedi = len(incoming_rows)
    return result


def load_incoming_for_fabrika(
    fabrika: str,
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[dict[str, Any]]:
    from backend.core.db import db

    vkns = list(_fabrika_vknleri(fabrika))
    if not vkns:
        return []

    filters = ["supplier_tckn_vkn IN (" + ",".join(["%s"] * len(vkns)) + ")"]
    params: list[Any] = list(vkns)
    if date_from:
        filters.append("issue_date::date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("issue_date::date <= %s")
        params.append(date_to)

    where = " AND ".join(filters)
    try:
        return db.query(
            f"""
            SELECT invoice_id, uuid, issue_date, supplier, supplier_tckn_vkn,
                   amount, currency
            FROM incoming_invoices
            WHERE {where}
            ORDER BY issue_date DESC, invoice_id
            """,
            tuple(params),
        )
    except Exception:
        return []
