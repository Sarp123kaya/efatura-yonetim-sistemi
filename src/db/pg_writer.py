#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional Postgres write-path (runs in parallel to existing SQLite + Excel outputs).

Enable by setting environment variable:
  - PG_DSN="postgresql://user:pass@host:5432/dbname"

This module is intentionally small and dependency-light. If psycopg/psycopg2 is not
installed or PG_DSN is missing, callers should gracefully skip Postgres writes.

Regression safety:
  - Existing SQLite writes are unchanged
  - Existing Excel report generation is unchanged
  - Postgres writes are strictly additive/parallel
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Sequence, Tuple


_DISPATCH_RE = re.compile(r"([AF])\s*[-/]\s*(\d{4,5})", flags=re.IGNORECASE)


def adapt_json(value: object) -> Optional[str]:
    """
    Make JSONB insertion compatible for both psycopg3 and psycopg2 without extra deps.

    Rules:
      - None -> None
      - str -> unchanged
      - dict/list -> json.dumps(..., ensure_ascii=False)
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    # Always return a JSON string for any other object (no extra deps; default=str for safety)
    return json.dumps(value, ensure_ascii=False, default=str)


def _to_decimal_2(value: object) -> Decimal:
    """
    Convert numbers to a 2-decimal Decimal safely.
    - If floats are passed, convert via str() to avoid binary float artifacts.
    """
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, (int, str)):
        d = Decimal(str(value))
    else:
        # floats and other numerics
        d = Decimal(str(value))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def allocate_equal_split(total_amount: object, dispatch_codes: Sequence[str]) -> List[Decimal]:
    """
    EQUAL_SPLIT with 2-decimal rounding and remainder assigned to the last dispatch.

    Requirement:
      - round to 2 places (TRY)
      - SUM(allocations) == total_amount exactly (as 2-decimal Decimal)
      - remainder is added to the last dispatch allocation
    """
    codes = list(dict.fromkeys([c for c in dispatch_codes if c]))  # stable-unique
    n = len(codes)
    if n == 0:
        return []

    total = _to_decimal_2(total_amount)
    if n == 1:
        return [total]

    # Rule: round to 2 decimals; remainder is assigned to the *last* dispatch so totals match exactly.
    base = (total / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    allocations = [base for _ in range(n - 1)]
    remainder = (total - (base * Decimal(n - 1))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    allocations.append(remainder)
    # Safety: ensure exact sum at 2dp
    if sum(allocations, Decimal("0.00")) != total:
        # As a last resort, force remainder to make totals match.
        allocations[-1] = (allocations[-1] + (total - sum(allocations, Decimal("0.00")))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return allocations


def extract_dispatch_codes_with_tokens(text: str) -> List[Tuple[str, str]]:
    """
    Extract canonical dispatch codes from text using current business regex:
      ([AF])\\s*[-/]\\s*(\\d{4,5})

    Returns list of tuples:
      [(code, raw_token), ...] where code is canonical 'A-7906' and raw_token is the matched substring.
    """
    if not text:
        return []
    results: List[Tuple[str, str]] = []
    for m in _DISPATCH_RE.finditer(str(text).upper()):
        prefix, num = m.group(1).upper(), m.group(2)
        code = f"{prefix}-{num}"
        raw_token = m.group(0)
        results.append((code, raw_token))
    # stable-unique by code (keep first token)
    seen: Dict[str, str] = {}
    for code, tok in results:
        if code not in seen:
            seen[code] = tok
    return list(seen.items())


# -----------------------------
# Postgres connection + upserts
# -----------------------------

try:
    import psycopg  # psycopg3
except Exception:  # pragma: no cover
    psycopg = None

try:
    import psycopg2  # psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None


def is_pg_enabled() -> bool:
    dsn = os.getenv("PG_DSN")
    if dsn is None:
        return False
    return bool(str(dsn).strip())


@contextmanager
def get_connection(dsn: Optional[str] = None):
    """
    Context manager that yields a Postgres connection.
    Uses psycopg (preferred) or psycopg2 as fallback.
    """
    dsn = (dsn or os.getenv("PG_DSN", "")).strip()
    if not dsn:
        raise RuntimeError("PG_DSN is not set")

    if psycopg is not None:
        conn = psycopg.connect(dsn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
        return

    if psycopg2 is not None:
        conn = psycopg2.connect(dsn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
        return

    raise RuntimeError("Neither psycopg nor psycopg2 is installed")


def _fetchone_id(cur) -> int:
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Expected RETURNING id row, got none")
    return int(row[0])


def upsert_invoice(
    conn,
    *,
    source: str,
    direction: str,
    invoice_no: str,
    total_amount: object,
    currency: str = "TRY",
    description_raw: Optional[str] = None,
    description_clean: Optional[str] = None,
    external_id: Optional[str] = None,
    source_file: Optional[str] = None,
    issue_date: Optional[object] = None,
    raw_payload: Optional[object] = None,
) -> int:
    """
    Upsert invoice.
    - If external_id is present: upsert by (source, external_id)
    - Else: upsert by (source, direction, invoice_no)
    """
    total = _to_decimal_2(total_amount)
    external_id = (str(external_id).strip() if external_id is not None and str(external_id).strip() else None)

    if external_id:
        sql = """
        INSERT INTO invoice (
          source, direction, invoice_no, total_amount, currency,
          description_raw, description_clean,
          external_id, source_file, issue_date, raw_payload,
          updated_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (source, external_id)
        DO UPDATE SET
          direction = EXCLUDED.direction,
          invoice_no = EXCLUDED.invoice_no,
          total_amount = EXCLUDED.total_amount,
          currency = EXCLUDED.currency,
          description_raw = EXCLUDED.description_raw,
          description_clean = EXCLUDED.description_clean,
          source_file = COALESCE(EXCLUDED.source_file, invoice.source_file),
          issue_date = COALESCE(EXCLUDED.issue_date, invoice.issue_date),
          raw_payload = COALESCE(EXCLUDED.raw_payload, invoice.raw_payload),
          updated_at = now()
        RETURNING id
        """
        params = (
            source,
            direction,
            invoice_no,
            str(total),
            currency,
            description_raw,
            description_clean,
            external_id,
            source_file,
            issue_date,
            adapt_json(raw_payload),
        )
    else:
        sql = """
        INSERT INTO invoice (
          source, direction, invoice_no, total_amount, currency,
          description_raw, description_clean,
          external_id, source_file, issue_date, raw_payload,
          updated_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (source, direction, invoice_no)
        DO UPDATE SET
          total_amount = EXCLUDED.total_amount,
          currency = EXCLUDED.currency,
          description_raw = EXCLUDED.description_raw,
          description_clean = EXCLUDED.description_clean,
          external_id = COALESCE(EXCLUDED.external_id, invoice.external_id),
          source_file = COALESCE(EXCLUDED.source_file, invoice.source_file),
          issue_date = COALESCE(EXCLUDED.issue_date, invoice.issue_date),
          raw_payload = COALESCE(EXCLUDED.raw_payload, invoice.raw_payload),
          updated_at = now()
        RETURNING id
        """
        params = (
            source,
            direction,
            invoice_no,
            str(total),
            currency,
            description_raw,
            description_clean,
            None,
            source_file,
            issue_date,
            adapt_json(raw_payload),
        )

    cur = conn.cursor()
    cur.execute(sql, params)
    return _fetchone_id(cur)


def upsert_dispatch(conn, *, code: str) -> int:
    # Uppercase enforcement is done in application code (schema validates with regex).
    code = (code or "").strip().upper()
    sql = """
    INSERT INTO dispatch (code)
    VALUES (%s)
    ON CONFLICT (code)
    DO UPDATE SET code = dispatch.code
    RETURNING id
    """
    cur = conn.cursor()
    cur.execute(sql, (code,))
    return _fetchone_id(cur)


def upsert_dispatch_invoice(
    conn,
    *,
    dispatch_id: int,
    invoice_id: int,
    direction: str,
    allocated_amount: object,
    allocation_method: str = "EQUAL_SPLIT",
    raw_token: Optional[str] = None,
) -> int:
    allocated = _to_decimal_2(allocated_amount)
    sql = """
    INSERT INTO dispatch_invoice (
      dispatch_id, invoice_id, direction,
      allocated_amount, allocation_method, raw_token
    )
    VALUES (%s,%s,%s,%s,%s,%s)
    ON CONFLICT (dispatch_id, invoice_id, direction)
    DO UPDATE SET
      allocated_amount = EXCLUDED.allocated_amount,
      allocation_method = EXCLUDED.allocation_method,
      raw_token = COALESCE(EXCLUDED.raw_token, dispatch_invoice.raw_token)
    RETURNING id
    """
    cur = conn.cursor()
    cur.execute(
        sql,
        (
            int(dispatch_id),
            int(invoice_id),
            direction,
            str(allocated),
            allocation_method,
            raw_token,
        ),
    )
    return _fetchone_id(cur)


def write_invoice_with_equal_split_allocations(
    conn,
    *,
    source: str,
    direction: str,
    invoice_no: str,
    total_amount: object,
    dispatch_codes_and_tokens: Sequence[Tuple[str, Optional[str]]],
    currency: str = "TRY",
    description_raw: Optional[str] = None,
    description_clean: Optional[str] = None,
    external_id: Optional[str] = None,
    source_file: Optional[str] = None,
    issue_date: Optional[object] = None,
    raw_payload: Optional[dict] = None,
) -> int:
    """
    Convenience helper:
      - upsert invoice
      - upsert dispatch rows
      - create/update dispatch_invoice allocation rows with remainder-safe EQUAL_SPLIT
    """
    invoice_id = upsert_invoice(
        conn,
        source=source,
        direction=direction,
        invoice_no=invoice_no,
        total_amount=total_amount,
        currency=currency,
        description_raw=description_raw,
        description_clean=description_clean,
        external_id=external_id,
        source_file=source_file,
        issue_date=issue_date,
        raw_payload=raw_payload,
    )

    items: List[Tuple[str, Optional[str]]] = []
    seen = set()
    for code, tok in dispatch_codes_and_tokens:
        if not code or code in seen:
            continue
        seen.add(code)
        items.append((code, tok))

    if not items:
        return invoice_id

    allocations = allocate_equal_split(total_amount, [c for c, _ in items])
    for (code, tok), amount in zip(items, allocations):
        dispatch_id = upsert_dispatch(conn, code=code)
        upsert_dispatch_invoice(
            conn,
            dispatch_id=dispatch_id,
            invoice_id=invoice_id,
            direction=direction,
            allocated_amount=amount,
            allocation_method="EQUAL_SPLIT",
            raw_token=tok,
        )
    return invoice_id


