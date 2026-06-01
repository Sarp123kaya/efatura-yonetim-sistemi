#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Müşteri sayfaları için çek özetleri (gelecek / ödenen)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.core.db import db


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


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
                WHERE account_name = %s
                  AND review_status = 'APPROVED'
                  AND TRIM(check_no) <> ''
                  AND (maturity_date IS NULL OR maturity_date >= %s)
                ORDER BY TRIM(check_no), id DESC
            ) u
            ORDER BY maturity_date ASC NULLS LAST, check_no
            """,
            (account_name, today),
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
                WHERE account_name = %s
                  AND review_status = 'APPROVED'
                  AND TRIM(check_no) <> ''
                ORDER BY TRIM(check_no), id DESC
            ) u
            """,
            (today, today, today, today, account_name),
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
    return out
