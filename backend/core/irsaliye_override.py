#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""İrsaliye kodu manuel düzeltme (override) iş mantığı."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.core.db import db


def normalize_code(code: str) -> str:
    """A-64 -> A-00064, F-956 -> F-00956"""
    m = re.match(r"^([AFT])-?(\d+)$", code.strip(), re.IGNORECASE)
    if not m:
        return code.strip()
    prefix = m.group(1).upper()
    digits = m.group(2).zfill(5)
    return f"{prefix}-{digits}"


def _parse_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value else []
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def find_invoice(invoice_ref: str) -> dict[str, Any] | None:
    """Find invoice by id or invoice_no (exact match)."""
    invoice_ref = invoice_ref.strip()
    if not invoice_ref:
        return None
    return db.query_one(
        """
        SELECT id, invoice_no, firm_name, issue_date, total_tl, description,
               irsaliye_codes, irsaliye_codes_override
        FROM outgoing_invoices
        WHERE id::text = %s OR invoice_no = %s
        """,
        (invoice_ref, invoice_ref),
    )


def search_invoices(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search invoices by exact ref or partial invoice_no."""
    query = query.strip()
    if not query:
        return []

    exact = find_invoice(query)
    if exact:
        return [exact]

    pattern = f"%{query}%"
    return db.query(
        """
        SELECT id, invoice_no, firm_name, issue_date, total_tl, description,
               irsaliye_codes, irsaliye_codes_override
        FROM outgoing_invoices
        WHERE invoice_no ILIKE %s
        ORDER BY issue_date DESC NULLS LAST, invoice_no DESC
        LIMIT %s
        """,
        (pattern, limit),
    )


def invoice_code_state(row: dict[str, Any]) -> dict[str, Any]:
    extracted = _parse_codes(row.get("irsaliye_codes"))
    raw_override = row.get("irsaliye_codes_override")
    override = _parse_codes(raw_override) if raw_override is not None else None
    effective = override if override is not None else extracted
    return {
        "extracted": extracted,
        "override": override,
        "effective": effective,
        "has_override": raw_override is not None,
    }


def list_overridden_invoices(*, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT id, invoice_no, firm_name, issue_date, total_tl, description,
               irsaliye_codes, irsaliye_codes_override
        FROM outgoing_invoices
        WHERE irsaliye_codes_override IS NOT NULL
        ORDER BY updated_at DESC NULLS LAST, issue_date DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    out = []
    for row in rows:
        state = invoice_code_state(row)
        out.append({**row, **state})
    return out


def apply_correction(invoice_ref: str, from_code: str, to_code: str) -> dict[str, Any]:
    row = find_invoice(invoice_ref)
    if not row:
        return {"ok": False, "error": f"Fatura bulunamadı: {invoice_ref}"}

    from_norm = normalize_code(from_code)
    to_norm = normalize_code(to_code)
    if from_norm == to_norm:
        return {"ok": False, "error": "Kaynak ve hedef kod aynı olamaz."}

    state = invoice_code_state(row)
    base_codes = state["override"] if state["override"] is not None else state["extracted"]

    warning = None
    if from_norm not in base_codes:
        warning = f"'{from_norm}' mevcut kodlarda yok: {base_codes}"

    new_codes = [to_norm if c == from_norm else c for c in base_codes]
    if from_norm not in base_codes and not base_codes:
        new_codes = [to_norm]

    db.execute(
        "UPDATE outgoing_invoices SET irsaliye_codes_override = %s WHERE id = %s",
        (json.dumps(new_codes), row["id"]),
    )

    return {
        "ok": True,
        "invoice_no": row["invoice_no"],
        "from_code": from_norm,
        "to_code": to_norm,
        "override": new_codes,
        "warning": warning,
    }


def clear_override(invoice_ref: str) -> dict[str, Any]:
    row = find_invoice(invoice_ref)
    if not row:
        return {"ok": False, "error": f"Fatura bulunamadı: {invoice_ref}"}

    db.execute(
        "UPDATE outgoing_invoices SET irsaliye_codes_override = NULL WHERE id = %s",
        (row["id"],),
    )
    return {"ok": True, "invoice_no": row["invoice_no"]}
