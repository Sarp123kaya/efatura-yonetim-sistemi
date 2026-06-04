#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outgoing invoice XML cache helpers.

The cache stores outgoing invoice UBL/XML payloads and parsed product line
items used by customer price reports.
"""
import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Optional

from .db import db


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def compute_xml_hash(xml_content: str) -> str:
    """Return a stable hash for XML change tracking."""
    return hashlib.sha256(xml_content.encode("utf-8")).hexdigest()


def ensure_outgoing_xml_cache_schema() -> None:
    """Create outgoing XML cache structures if the migration has not been applied."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS outgoing_invoice_xml_cache (
            id TEXT PRIMARY KEY,
            invoice_no TEXT,
            firm_name TEXT,
            xml_content TEXT NOT NULL,
            xml_hash TEXT NOT NULL,
            line_items JSONB DEFAULT '[]'::jsonb,
            fetch_key TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_invoice_no
        ON outgoing_invoice_xml_cache(invoice_no)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_firm_name
        ON outgoing_invoice_xml_cache(firm_name)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outgoing_xml_cache_updated_at
        ON outgoing_invoice_xml_cache(updated_at)
        """
    )


def get_cached_outgoing_xml(invoice_id: str) -> Optional[Dict]:
    """Return cached outgoing XML/line data for an invoice id, if present."""
    if not invoice_id:
        return None

    row = db.query_one(
        """
        SELECT id, invoice_no, firm_name, xml_content, xml_hash, line_items,
               fetch_key, fetched_at, parsed_at, updated_at
        FROM outgoing_invoice_xml_cache
        WHERE id = %s
        """,
        (invoice_id,),
    )
    if not row:
        return None

    value = row.get("line_items")
    if isinstance(value, str):
        row["line_items"] = json.loads(value) if value else []

    return row


def upsert_outgoing_xml_cache(
    invoice_id: str,
    invoice_no: str,
    firm_name: str,
    xml_content: str,
    line_items: List[Dict],
    fetch_key: str = "",
) -> str:
    """Insert or update cached outgoing XML after a successful fetch and parse."""
    xml_hash = compute_xml_hash(xml_content)
    db.execute(
        """
        INSERT INTO outgoing_invoice_xml_cache (
            id, invoice_no, firm_name, xml_content, xml_hash, line_items,
            fetch_key, fetched_at, parsed_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET
            invoice_no = EXCLUDED.invoice_no,
            firm_name = EXCLUDED.firm_name,
            xml_content = EXCLUDED.xml_content,
            xml_hash = EXCLUDED.xml_hash,
            line_items = EXCLUDED.line_items,
            fetch_key = EXCLUDED.fetch_key,
            fetched_at = NOW(),
            parsed_at = NOW(),
            updated_at = NOW()
        """,
        (
            invoice_id,
            invoice_no,
            firm_name,
            xml_content,
            xml_hash,
            json.dumps(line_items, ensure_ascii=False, default=_json_default),
            fetch_key,
        ),
    )
    return xml_hash
