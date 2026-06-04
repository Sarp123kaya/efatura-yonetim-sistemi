#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aynı çek numarasına sahip mükerrer kayıtları birleştirir."""
from __future__ import annotations

from typing import Any

from backend.core.check_excel_incremental import normalize_check_no
from backend.core.db import db


def count_duplicate_check_groups() -> int:
    try:
        row = db.query_one(
            """
            SELECT COUNT(*) AS n
            FROM (
                SELECT TRIM(check_no) AS cno
                FROM checks
                WHERE TRIM(check_no) <> ''
                GROUP BY TRIM(check_no)
                HAVING COUNT(*) > 1
            ) d
            """
        )
        return int(row["n"]) if row else 0
    except Exception:
        return 0


def _pick_best_name(*names: str | None) -> str | None:
    candidates = [n.strip() for n in names if n and str(n).strip()]
    if not candidates:
        return None
    return max(candidates, key=len)


def dedupe_checks_by_check_no() -> dict[str, int]:
    """
    Her çek numarası için tek kayıt bırakır.
    En dolu müşteri/keşideci adına sahip satır kalır; diğerleri silinir.
    """
    try:
        rows = db.query(
            """
            SELECT id, check_no, account_name, company_name, bank_name,
                   amount, maturity_date, review_status
            FROM checks
            WHERE TRIM(check_no) <> ''
            ORDER BY TRIM(check_no) ASC, id ASC
            """
        )
    except Exception:
        return {"groups": 0, "removed": 0, "merged": 0}

    by_no: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = normalize_check_no(row.get("check_no"))
        if key:
            by_no.setdefault(key, []).append(row)

    removed = 0
    merged = 0
    groups = 0

    with db.get_connection(auto_commit=False) as conn:
        cur = conn.cursor()
        for _cno, group in by_no.items():
            if len(group) < 2:
                continue
            groups += 1
            group.sort(
                key=lambda r: (
                    len((r.get("account_name") or "") + (r.get("company_name") or "")),
                    int(r["id"]),
                ),
                reverse=True,
            )
            keep = group[0]
            keep_id = int(keep["id"])
            best_account = _pick_best_name(*(g.get("account_name") for g in group))
            best_company = _pick_best_name(*(g.get("company_name") for g in group))
            if best_account or best_company:
                cur.execute(
                    """
                    UPDATE checks
                    SET account_name = COALESCE(%s, account_name),
                        company_name = COALESCE(%s, company_name),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (best_account, best_company, keep_id),
                )
                merged += 1

            delete_ids = [int(g["id"]) for g in group[1:]]
            for dup_id in delete_ids:
                cur.execute(
                    """
                    UPDATE check_import_rows
                    SET canonical_check_id = %s
                    WHERE canonical_check_id = %s
                    """,
                    (keep_id, dup_id),
                )
                cur.execute(
                    """
                    UPDATE check_import_rows
                    SET duplicate_of_check_id = %s
                    WHERE duplicate_of_check_id = %s
                    """,
                    (keep_id, dup_id),
                )
                cur.execute("DELETE FROM checks WHERE id = %s", (dup_id,))
                removed += 1
        conn.commit()

    return {"groups": groups, "removed": removed, "merged": merged}


def ensure_unique_check_no_index() -> None:
    """Mükerrer temizlendikten sonra çek no benzersizliği (opsiyonel)."""
    try:
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_checks_check_no_trim
            ON checks (TRIM(check_no))
            WHERE TRIM(check_no) <> ''
            """
        )
    except Exception:
        pass
