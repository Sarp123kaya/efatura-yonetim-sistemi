"""Fabrika kar tablolarının güncelliğini kontrol eder ve gerekirse senkronize eder."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def _kar_global_bounds() -> tuple[Optional[date], Optional[datetime]]:
    from backend.core.db import db

    row = db.query_one(
        """
        SELECT
            (SELECT MAX(tarih) FROM (
                SELECT tarih FROM factory_a_kar
                UNION ALL SELECT tarih FROM factory_f_kar
                UNION ALL SELECT tarih FROM factory_t_kar
            ) t) AS kar_max_tarih,
            (SELECT MAX(updated_at) FROM (
                SELECT updated_at FROM factory_a_kar
                UNION ALL SELECT updated_at FROM factory_f_kar
                UNION ALL SELECT updated_at FROM factory_t_kar
            ) u) AS kar_max_updated,
            (SELECT MAX(issue_date)::date FROM outgoing_invoices) AS inv_max_tarih
        """
    )
    if not row:
        return None, None
    return row.get("kar_max_tarih"), row.get("kar_max_updated")


def factory_kar_stale() -> bool:
    """True when outgoing invoices are newer than the latest factory kar snapshot."""
    from backend.core.db import db

    row = db.query_one(
        """
        SELECT
            (SELECT MAX(tarih) FROM (
                SELECT tarih FROM factory_a_kar
                UNION ALL SELECT tarih FROM factory_f_kar
                UNION ALL SELECT tarih FROM factory_t_kar
            ) t) AS kar_max_tarih,
            (SELECT MAX(issue_date)::date FROM outgoing_invoices) AS inv_max_tarih
        """
    )
    if not row:
        return True
    inv_max = row.get("inv_max_tarih")
    kar_max = row.get("kar_max_tarih")
    if inv_max is None:
        return False
    if kar_max is None:
        return True
    return kar_max < inv_max


def factory_kar_last_updated() -> Optional[datetime]:
    _, updated = _kar_global_bounds()
    return updated


def ensure_factory_kar_synced() -> bool:
    """
    Run sync_factory_kar when snapshot is behind outgoing invoices.
    Returns True if sync ran.
    """
    if not factory_kar_stale():
        return False
    from scripts.sync_factory_kar import sync

    sync()
    return True
