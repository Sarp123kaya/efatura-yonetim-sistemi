#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostgreSQL storage for İşbaşı customer/firm cards."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from backend.core.db import db


def ensure_firm_cards_schema() -> None:
    """Create firm_cards table if missing."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS firm_cards (
            firm_id TEXT PRIMARY KEY,
            name TEXT,
            tax_id TEXT,
            city TEXT,
            district TEXT,
            balance NUMERIC(18, 2),
            beginning_balance NUMERIC(18, 2),
            beginning_balance_date TIMESTAMPTZ,
            currency TEXT DEFAULT 'TL',
            ar_ap_type INTEGER,
            balance_updated_at TIMESTAMPTZ,
            is_active BOOLEAN DEFAULT TRUE,
            raw_json JSONB DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_firm_cards_tax_id
        ON firm_cards(tax_id)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_firm_cards_name
        ON firm_cards(name)
        """
    )


def _parse_api_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _firm_display_name(row: Dict[str, Any]) -> str:
    return str(
        row.get("name")
        or row.get("fullName")
        or row.get("displayName")
        or ""
    ).strip()


def _firm_tax_id(row: Dict[str, Any]) -> str:
    return str(
        row.get("taxOrPersonalId")
        or row.get("vknTckn")
        or row.get("taxNo")
        or ""
    ).strip()


def firm_card_params_from_api(row: Dict[str, Any]) -> Optional[tuple]:
    """Map İşbaşı firm object to INSERT/UPSERT parameters."""
    firm_id = str(row.get("id") or row.get("firmId") or "").strip()
    if not firm_id:
        return None

    now = datetime.now()
    return (
        firm_id,
        _firm_display_name(row),
        _firm_tax_id(row),
        str(row.get("city") or "").strip() or None,
        str(row.get("district") or "").strip() or None,
        row.get("balance"),
        row.get("beginningBalance"),
        _parse_api_datetime(row.get("beginningBalanceDate")),
        str(row.get("currency") or "TL").strip() or "TL",
        row.get("arApType"),
        now,
        bool(row.get("isActive", True)),
        json.dumps(row, ensure_ascii=False, default=str),
        now,
    )


def upsert_firm_cards_from_api_rows(rows: Iterable[Dict[str, Any]]) -> int:
    """Upsert firm cards from API firm dicts. Returns number of rows written."""
    ensure_firm_cards_schema()
    params: List[tuple] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = firm_card_params_from_api(row)
        if item:
            params.append(item)
    if not params:
        return 0

    db.execute_batch(
        """
        INSERT INTO firm_cards (
            firm_id, name, tax_id, city, district,
            balance, beginning_balance, beginning_balance_date,
            currency, ar_ap_type, balance_updated_at, is_active,
            raw_json, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (firm_id) DO UPDATE SET
            name = EXCLUDED.name,
            tax_id = EXCLUDED.tax_id,
            city = EXCLUDED.city,
            district = EXCLUDED.district,
            balance = EXCLUDED.balance,
            beginning_balance = EXCLUDED.beginning_balance,
            beginning_balance_date = EXCLUDED.beginning_balance_date,
            currency = EXCLUDED.currency,
            ar_ap_type = EXCLUDED.ar_ap_type,
            balance_updated_at = EXCLUDED.balance_updated_at,
            is_active = EXCLUDED.is_active,
            raw_json = EXCLUDED.raw_json,
            updated_at = EXCLUDED.updated_at
        """,
        params,
        batch_size=100,
        persistent=True,
    )
    return len(params)


def upsert_firm_cards_from_invoices(invoices: Iterable[Dict[str, Any]]) -> int:
    """Extract nested firm objects from outgoing invoice payloads."""
    firms: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for invoice in invoices:
        if not isinstance(invoice, dict):
            continue
        firm = invoice.get("firm")
        if not isinstance(firm, dict):
            continue
        firm_id = str(firm.get("id") or firm.get("firmId") or "").strip()
        if not firm_id or firm_id in seen:
            continue
        seen.add(firm_id)
        firms.append(firm)
    return upsert_firm_cards_from_api_rows(firms)


def backfill_firm_cards_from_outgoing_invoices() -> int:
    """Populate firm_cards from stored outgoing_invoices.raw_json when table is empty."""
    ensure_firm_cards_schema()
    count_row = db.query_one("SELECT COUNT(*)::int AS c FROM firm_cards")
    if count_row and int(count_row.get("c") or 0) > 0:
        return 0

    rows = db.query(
        """
        SELECT raw_json
        FROM outgoing_invoices
        WHERE raw_json IS NOT NULL
        """
    )
    invoices: List[Dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw_json")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if isinstance(raw, dict):
            invoices.append(raw)
    return upsert_firm_cards_from_invoices(invoices)
