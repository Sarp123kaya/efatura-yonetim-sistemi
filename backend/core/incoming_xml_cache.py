#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incoming invoice XML cache helpers.

The cache stores the official UBL/XML payload by UUID and the parsed despatch
data derived from that XML. Manual corrections live outside the cache.
"""

import hashlib
import json
from typing import Dict, List, Optional

from .db import db


def compute_xml_hash(xml_content: str) -> str:
    """Return a stable hash for XML change tracking."""
    return hashlib.sha256(xml_content.encode("utf-8")).hexdigest()


def ensure_xml_cache_schema() -> None:
    """Create XML cache structures if the migration has not been applied yet."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS incoming_invoice_xml_cache (
            uuid TEXT PRIMARY KEY,
            invoice_id TEXT,
            supplier TEXT,
            xml_content TEXT NOT NULL,
            xml_hash TEXT NOT NULL,
            despatch_documents JSONB DEFAULT '[]'::jsonb,
            despatch_ids JSONB DEFAULT '[]'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incoming_xml_cache_invoice_id
        ON incoming_invoice_xml_cache(invoice_id)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incoming_xml_cache_updated_at
        ON incoming_invoice_xml_cache(updated_at)
        """
    )
    db.execute(
        """
        ALTER TABLE incoming_invoices
        ADD COLUMN IF NOT EXISTS despatch_ids_override JSONB
        """
    )


def get_cached_xml(uuid: str) -> Optional[Dict]:
    """Return cached XML/despatch data for a UUID, if present."""
    if not uuid:
        return None

    row = db.query_one(
        """
        SELECT uuid, invoice_id, supplier, xml_content, xml_hash,
               despatch_documents, despatch_ids, fetched_at, parsed_at, updated_at
        FROM incoming_invoice_xml_cache
        WHERE uuid = %s
        """,
        (uuid,),
    )
    if not row:
        return None

    for key in ("despatch_documents", "despatch_ids"):
        value = row.get(key)
        if isinstance(value, str):
            row[key] = json.loads(value) if value else []

    return row


def upsert_xml_cache(
    uuid: str,
    invoice_id: str,
    supplier: str,
    xml_content: str,
    despatch_documents: List[Dict],
    despatch_ids: List[str],
) -> str:
    """Insert or update cached XML after a successful fetch and parse."""
    xml_hash = compute_xml_hash(xml_content)
    db.execute(
        """
        INSERT INTO incoming_invoice_xml_cache (
            uuid, invoice_id, supplier, xml_content, xml_hash,
            despatch_documents, despatch_ids, fetched_at, parsed_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
        ON CONFLICT (uuid) DO UPDATE SET
            invoice_id = EXCLUDED.invoice_id,
            supplier = EXCLUDED.supplier,
            xml_content = EXCLUDED.xml_content,
            xml_hash = EXCLUDED.xml_hash,
            despatch_documents = EXCLUDED.despatch_documents,
            despatch_ids = EXCLUDED.despatch_ids,
            fetched_at = NOW(),
            parsed_at = NOW(),
            updated_at = NOW()
        """,
        (
            uuid,
            invoice_id,
            supplier,
            xml_content,
            xml_hash,
            json.dumps(despatch_documents, ensure_ascii=False),
            json.dumps(despatch_ids, ensure_ascii=False),
        ),
    )
    return xml_hash
