#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Incoming e-despatch description cache helpers."""

from __future__ import annotations

from typing import Dict, Optional

from .db import db


def ensure_incoming_despatch_description_cache_schema() -> None:
    """Create incoming e-despatch description cache structures if missing."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS incoming_despatch_description_cache (
            uuid TEXT PRIMARY KEY,
            dispatch_id TEXT,
            supplier TEXT,
            description TEXT DEFAULT '',
            document_text TEXT DEFAULT '',
            fetch_source TEXT DEFAULT '',
            fetch_status TEXT NOT NULL DEFAULT 'success',
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incoming_despatch_desc_dispatch_id
        ON incoming_despatch_description_cache(dispatch_id)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incoming_despatch_desc_updated_at
        ON incoming_despatch_description_cache(updated_at)
        """
    )


def get_cached_despatch_description(uuid: str) -> Optional[Dict]:
    """Return cached description data for an incoming e-despatch UUID."""
    if not uuid:
        return None
    return db.query_one(
        """
        SELECT uuid, dispatch_id, supplier, description, document_text,
               fetch_source, fetch_status, fetched_at, updated_at
        FROM incoming_despatch_description_cache
        WHERE uuid = %s
        """,
        (uuid,),
    )


def upsert_despatch_description_cache(
    *,
    uuid: str,
    dispatch_id: str,
    supplier: str,
    description: str,
    document_text: str = "",
    fetch_source: str = "",
    fetch_status: str = "success",
) -> None:
    """Insert or update cached incoming e-despatch description data."""
    if not uuid:
        return
    db.execute(
        """
        INSERT INTO incoming_despatch_description_cache (
            uuid, dispatch_id, supplier, description, document_text,
            fetch_source, fetch_status, fetched_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (uuid) DO UPDATE SET
            dispatch_id = EXCLUDED.dispatch_id,
            supplier = EXCLUDED.supplier,
            description = EXCLUDED.description,
            document_text = EXCLUDED.document_text,
            fetch_source = EXCLUDED.fetch_source,
            fetch_status = EXCLUDED.fetch_status,
            updated_at = NOW()
        """,
        (
            uuid,
            dispatch_id,
            supplier,
            description or "",
            document_text or "",
            fetch_source or "",
            fetch_status or "success",
        ),
    )
