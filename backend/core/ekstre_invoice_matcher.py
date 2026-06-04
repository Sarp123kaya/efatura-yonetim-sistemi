#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ekstre ↔ Gelen Fatura Karşılaştırması
======================================
Fabrika cari ekstresindeki fatura satırlarını incoming_invoices ile eşleştirir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from backend.core.db import db

INVOICE_FIS_TURLERI: tuple[str, ...] = (
    "Toptan Satış Faturası",
    "Alınan Hizmet Faturası",
    "Verilen Hizmet Faturası",
)

AMOUNT_TOLERANCE = Decimal("0.01")

FABRIKA_SUPPLIER_SQL: dict[str, str] = {
    "AK GİPS": "(supplier ILIKE 'AK G%%' OR supplier ILIKE '%%AK GİPS%%')",
    "FULLBOARD": "(supplier ILIKE 'FULLBOARD%%' OR supplier ILIKE '%%FULLBOARD%%')",
}


def _normalize_doc_id(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _supplier_filter_for_fabrika(fabrika: str) -> str:
    upper = (fabrika or "").upper()
    if "AK G" in upper or "AKG" in upper:
        return FABRIKA_SUPPLIER_SQL["AK GİPS"]
    if "FULLBOARD" in upper or "FLL" in upper:
        return FABRIKA_SUPPLIER_SQL["FULLBOARD"]
    return "FALSE"


@dataclass
class ComparisonRow:
    durum: str
    fis_no: str
    ekstre_tarih: Optional[date]
    ekstre_tutar: Optional[Decimal]
    ekstre_fis_turu: str
    invoice_id: str
    fatura_tarih: Optional[date]
    fatura_tutar: Optional[Decimal]
    fatura_supplier: str
    tutar_fark: Optional[Decimal]
    tarih_fark_gun: Optional[int]
    incoming_uuid: str = ""


@dataclass
class ComparisonResult:
    fabrika: str
    cari_hesap_kodu: str
    date_from: Optional[date]
    date_to: Optional[date]
    source_file: str
    rows: list[ComparisonRow] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


def _load_statement_invoice_rows(
    fabrika: str,
    cari_hesap_kodu: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[dict[str, Any]]:
    filters = ["fabrika = %s", "fis_turu = ANY(%s)", "COALESCE(borc, 0) > 0"]
    params: list[Any] = [fabrika, list(INVOICE_FIS_TURLERI)]
    if cari_hesap_kodu is not None:
        filters.append("COALESCE(cari_hesap_kodu, '') = %s")
        params.append(cari_hesap_kodu)
    if date_from:
        filters.append("tarih >= %s")
        params.append(date_from)
    if date_to:
        filters.append("tarih <= %s")
        params.append(date_to)
    where = " AND ".join(filters)
    return db.query(
        f"""
        SELECT fis_no, tarih, borc, fis_turu, aciklama, source_file
        FROM factory_statements
        WHERE {where}
        ORDER BY tarih DESC, fis_no DESC
        """,
        tuple(params),
    )


def _load_incoming_invoices(
    fabrika: str,
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[dict[str, Any]]:
    supplier_sql = _supplier_filter_for_fabrika(fabrika)
    filters = [supplier_sql]
    params: list[Any] = []
    if date_from:
        filters.append("issue_date::date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("issue_date::date <= %s")
        params.append(date_to)
    where = " AND ".join(filters)
    return db.query(
        f"""
        SELECT invoice_id, issue_date, supplier, amount, uuid
        FROM incoming_invoices
        WHERE {where}
        ORDER BY issue_date DESC, invoice_id DESC
        """,
        tuple(params),
    )


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


def _load_meta(fabrika: str, cari_hesap_kodu: Optional[str]) -> dict[str, Any]:
    filters, params = _statement_filters(fabrika, cari_hesap_kodu)
    where = " AND ".join(filters)
    sub_filters = [
        f.replace("fabrika", "fs2.fabrika").replace("cari_hesap_kodu", "fs2.cari_hesap_kodu")
        for f in filters
    ]
    row = db.query_one(
        f"""
        SELECT MIN(tarih) AS ilk_tarih,
               MAX(tarih) AS son_tarih,
               (
                   SELECT source_file
                   FROM factory_statements fs2
                   WHERE {" AND ".join(sub_filters)}
                   ORDER BY fs2.created_at DESC NULLS LAST, fs2.id DESC
                   LIMIT 1
               ) AS source_file
        FROM factory_statements
        WHERE {where}
        """,
        tuple(params + params),
    )
    return row or {}


def _classify_match(
    ekstre_tutar: Optional[Decimal],
    fatura_tutar: Optional[Decimal],
    ekstre_tarih: Optional[date],
    fatura_tarih: Optional[date],
) -> str:
    tutar_fark: Optional[Decimal] = None
    if ekstre_tutar is not None and fatura_tutar is not None:
        tutar_fark = abs(ekstre_tutar - fatura_tutar)
    tarih_fark: Optional[int] = None
    if ekstre_tarih and fatura_tarih:
        tarih_fark = abs((ekstre_tarih - fatura_tarih).days)

    amount_ok = tutar_fark is not None and tutar_fark <= AMOUNT_TOLERANCE
    date_ok = tarih_fark is not None and tarih_fark == 0

    if amount_ok and date_ok:
        return "Eşleşti"
    if amount_ok and not date_ok:
        return "Tarih Farkı"
    if not amount_ok and date_ok:
        return "Tutar Farkı"
    return "Tutar ve Tarih Farkı"


def compare_ekstre_with_incoming(
    fabrika: str,
    cari_hesap_kodu: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ComparisonResult:
    """Ekstre fatura satırları ile gelen e-faturaları karşılaştırır."""
    hesap = cari_hesap_kodu or ""
    result = ComparisonResult(
        fabrika=fabrika,
        cari_hesap_kodu=hesap,
        date_from=date_from,
        date_to=date_to,
        source_file="",
    )

    try:
        meta = _load_meta(fabrika, cari_hesap_kodu or None)
        if not date_from and meta.get("ilk_tarih"):
            date_from = _to_date(meta["ilk_tarih"])
        if not date_to and meta.get("son_tarih"):
            date_to = _to_date(meta["son_tarih"])
        result.date_from = date_from
        result.date_to = date_to
        result.source_file = meta.get("source_file") or ""

        stmt_rows = _load_statement_invoice_rows(
            fabrika, cari_hesap_kodu or None, date_from, date_to
        )
        inv_rows = _load_incoming_invoices(fabrika, date_from, date_to)

        stmt_by_id: dict[str, dict[str, Any]] = {}
        for row in stmt_rows:
            key = _normalize_doc_id(row.get("fis_no"))
            if key:
                stmt_by_id[key] = row

        inv_by_id: dict[str, dict[str, Any]] = {}
        for row in inv_rows:
            key = _normalize_doc_id(row.get("invoice_id"))
            if key:
                inv_by_id[key] = row

        all_ids = sorted(set(stmt_by_id) | set(inv_by_id), reverse=True)
        rows: list[ComparisonRow] = []

        for doc_id in all_ids:
            stmt = stmt_by_id.get(doc_id)
            inv = inv_by_id.get(doc_id)

            ekstre_tarih = _to_date(stmt.get("tarih")) if stmt else None
            ekstre_tutar = _decimal(stmt.get("borc")) if stmt else None
            fatura_tarih = _to_date(inv.get("issue_date")) if inv else None
            fatura_tutar = _decimal(inv.get("amount")) if inv else None

            tutar_fark: Optional[Decimal] = None
            if ekstre_tutar is not None and fatura_tutar is not None:
                tutar_fark = ekstre_tutar - fatura_tutar

            tarih_fark_gun: Optional[int] = None
            if ekstre_tarih and fatura_tarih:
                tarih_fark_gun = (ekstre_tarih - fatura_tarih).days

            if stmt and inv:
                durum = _classify_match(ekstre_tutar, fatura_tutar, ekstre_tarih, fatura_tarih)
            elif stmt:
                durum = "Faturada Yok"
            else:
                durum = "Ekstrede Yok"

            rows.append(
                ComparisonRow(
                    durum=durum,
                    fis_no=stmt.get("fis_no", "") if stmt else "",
                    ekstre_tarih=ekstre_tarih,
                    ekstre_tutar=ekstre_tutar,
                    ekstre_fis_turu=(stmt.get("fis_turu") or "") if stmt else "",
                    invoice_id=inv.get("invoice_id", "") if inv else doc_id,
                    fatura_tarih=fatura_tarih,
                    fatura_tutar=fatura_tutar,
                    fatura_supplier=(inv.get("supplier") or "") if inv else "",
                    tutar_fark=tutar_fark,
                    tarih_fark_gun=tarih_fark_gun,
                    incoming_uuid=(inv.get("uuid") or "") if inv else "",
                )
            )

        summary = {
            "toplam": len(rows),
            "eslesti": sum(1 for r in rows if r.durum == "Eşleşti"),
            "tutar_farki": sum(1 for r in rows if "Tutar" in r.durum and r.durum != "Eşleşti"),
            "tarih_farki": sum(1 for r in rows if r.durum == "Tarih Farkı"),
            "ekstrede_yok": sum(1 for r in rows if r.durum == "Ekstrede Yok"),
            "faturada_yok": sum(1 for r in rows if r.durum == "Faturada Yok"),
        }
        result.rows = rows
        result.summary = summary
        return result

    except Exception as exc:
        result.error = str(exc)
        return result
