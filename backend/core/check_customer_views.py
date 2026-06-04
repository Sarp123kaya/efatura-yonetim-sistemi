#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Müşteri sayfaları için çek özetleri (gelecek / ödenen)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.core.db import db
from backend.core.customer_ekstre_comparison import match_musteri_adi_to_firm


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _distinct_check_account_names() -> list[str]:
    rows = db.query(
        """
        SELECT DISTINCT account_name
        FROM checks
        WHERE COALESCE(account_name, '') <> ''
        ORDER BY account_name
        """
    )
    return [str(row.get("account_name") or "").strip() for row in rows if row.get("account_name")]


def _matched_check_account_names(customer_name: str) -> list[str]:
    if not customer_name:
        return []
    names = _distinct_check_account_names()
    matched, _method = match_musteri_adi_to_firm(customer_name, names)
    return matched or [customer_name]


def load_checks_by_customer_name(account_name: str) -> dict[str, Any]:
    """
    Tek müşteri için çek görünümü:
    - upcoming_checks: vadesi gelecek (tabloda)
    - ödenen: vade tarihi bugünden önce (vadesi geçti = ödenmiş kabul)
    """
    today = date.today()
    empty = {
        "upcoming_checks": [],
        "gelecek_adedi": 0,
        "gelecek_toplam": Decimal("0"),
        "odenen_adedi": 0,
        "odenen_toplam": Decimal("0"),
    }
    try:
        account_names = _matched_check_account_names(account_name)
        if not account_names:
            return empty
        upcoming = db.query(
            """
            SELECT id, check_no, bank_name, amount, currency,
                   maturity_date, transaction_date, status, review_status,
                   raw_description
            FROM (
                SELECT DISTINCT ON (TRIM(check_no))
                    id, check_no, bank_name, amount, currency,
                    maturity_date, transaction_date, status, review_status,
                    raw_description
                FROM checks
                WHERE account_name = ANY(%s)
                  AND review_status = 'APPROVED'
                  AND TRIM(check_no) <> ''
                  AND (maturity_date IS NULL OR maturity_date >= %s)
                ORDER BY TRIM(check_no), id DESC
            ) u
            ORDER BY maturity_date ASC NULLS LAST, check_no
            """,
            (account_names, today),
        )
        agg = db.query_one(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE maturity_date IS NULL OR maturity_date >= %s
                ) AS gelecek_adedi,
                COALESCE(SUM(amount) FILTER (
                    WHERE maturity_date IS NULL OR maturity_date >= %s
                ), 0) AS gelecek_toplam,
                COUNT(*) FILTER (
                    WHERE maturity_date IS NOT NULL AND maturity_date < %s
                ) AS odenen_adedi,
                COALESCE(SUM(amount) FILTER (
                    WHERE maturity_date IS NOT NULL AND maturity_date < %s
                ), 0) AS odenen_toplam
            FROM (
                SELECT DISTINCT ON (TRIM(check_no))
                    amount, maturity_date
                FROM checks
                WHERE account_name = ANY(%s)
                  AND review_status = 'APPROVED'
                  AND TRIM(check_no) <> ''
                ORDER BY TRIM(check_no), id DESC
            ) u
            """,
            (today, today, today, today, account_names),
        )
    except Exception:
        return empty

    row = agg or {}
    return {
        "upcoming_checks": upcoming,
        "gelecek_adedi": int(row.get("gelecek_adedi") or 0),
        "gelecek_toplam": _to_decimal(row.get("gelecek_toplam")),
        "odenen_adedi": int(row.get("odenen_adedi") or 0),
        "odenen_toplam": _to_decimal(row.get("odenen_toplam")),
    }


def load_check_summaries_for_all_customers() -> dict[str, dict[str, Any]]:
    """Müşteriler listesi — account_name bazlı özet."""
    today = date.today()
    try:
        rows = db.query(
            """
            SELECT
                account_name,
                COUNT(*) FILTER (
                    WHERE maturity_date IS NULL OR maturity_date >= %s
                ) AS gelecek_adedi,
                COALESCE(SUM(amount) FILTER (
                    WHERE maturity_date IS NULL OR maturity_date >= %s
                ), 0) AS gelecek_toplam,
                COALESCE(SUM(amount) FILTER (
                    WHERE maturity_date IS NOT NULL AND maturity_date < %s
                ), 0) AS odenen_toplam,
                MIN(maturity_date) FILTER (
                    WHERE maturity_date >= %s
                ) AS son_vade
            FROM (
                SELECT DISTINCT ON (account_name, TRIM(check_no))
                    account_name, amount, maturity_date
                FROM checks
                WHERE review_status = 'APPROVED'
                  AND TRIM(check_no) <> ''
                  AND COALESCE(account_name, '') <> ''
                ORDER BY account_name, TRIM(check_no), id DESC
            ) u
            GROUP BY account_name
            """,
            (today, today, today, today),
        )
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("account_name") or ""
        out[name] = {
            "gelecek_adedi": int(row.get("gelecek_adedi") or 0),
            "gelecek_toplam": _to_decimal(row.get("gelecek_toplam")),
            "odenen_toplam": _to_decimal(row.get("odenen_toplam")),
            "son_vade": row.get("son_vade"),
        }
    try:
        firm_rows = db.query("SELECT name FROM firm_cards WHERE COALESCE(name, '') <> ''")
    except Exception:
        return out

    account_names = list(out.keys())
    for firm_row in firm_rows:
        firm_name = str(firm_row.get("name") or "").strip()
        if not firm_name or firm_name in out:
            continue
        matched, _method = match_musteri_adi_to_firm(firm_name, account_names)
        if not matched:
            continue
        combined = {
            "gelecek_adedi": 0,
            "gelecek_toplam": Decimal("0"),
            "odenen_toplam": Decimal("0"),
            "son_vade": None,
        }
        for matched_name in matched:
            item = out.get(matched_name) or {}
            combined["gelecek_adedi"] += int(item.get("gelecek_adedi") or 0)
            combined["gelecek_toplam"] += _to_decimal(item.get("gelecek_toplam"))
            combined["odenen_toplam"] += _to_decimal(item.get("odenen_toplam"))
            son_vade = item.get("son_vade")
            if son_vade and (combined["son_vade"] is None or son_vade < combined["son_vade"]):
                combined["son_vade"] = son_vade
        out[firm_name] = combined
    return out
