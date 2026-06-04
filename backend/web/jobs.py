#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostgreSQL-backed job storage for the web panel."""

from __future__ import annotations

import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2.extras

from backend.core.db import db


VALID_STATUSES = {"pending", "running", "success", "failed", "cancelled"}


def ensure_web_job_schema() -> None:
    """Create web job tables/indexes if the migration has not been applied yet."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS web_jobs (
            id UUID PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled')),
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            locked_by TEXT,
            locked_at TIMESTAMPTZ,
            log_text TEXT NOT NULL DEFAULT '',
            log_path TEXT,
            created_files JSONB NOT NULL DEFAULT '[]'::jsonb,
            error_message TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_web_jobs_status_created ON web_jobs(status, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_web_jobs_type_created ON web_jobs(type, created_at DESC)")


def _row_to_job(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    for key in ("created_at", "started_at", "finished_at", "updated_at", "locked_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            row[key] = value.isoformat(timespec="seconds")
    return row


def create_job(job_type: str, params: dict[str, Any], created_by: str | None = None) -> str:
    ensure_web_job_schema()
    job_id = str(uuid.uuid4())
    params = {key: value for key, value in params.items() if value not in ("", None)}
    db.execute(
        """
        INSERT INTO web_jobs (id, type, params, created_by)
        VALUES (%s, %s, %s, %s)
        """,
        (job_id, job_type, psycopg2.extras.Json(params), created_by),
    )
    return job_id


def list_jobs(limit: int = 25) -> list[dict[str, Any]]:
    ensure_web_job_schema()
    rows = db.query(
        """
        SELECT id, type, status, params, created_by, created_at, started_at, finished_at,
               updated_at, locked_by, locked_at, created_files, error_message
        FROM web_jobs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [_row_to_job(row) for row in rows]


def get_job(job_id: str) -> dict[str, Any] | None:
    ensure_web_job_schema()
    row = db.query_one("SELECT * FROM web_jobs WHERE id = %s", (job_id,))
    return _row_to_job(row)


def claim_next_job(worker_name: str | None = None) -> dict[str, Any] | None:
    ensure_web_job_schema()
    worker = worker_name or socket.gethostname()
    with db.get_connection(auto_commit=False) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM web_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None

            claimed = dict(row)
            cur.execute(
                """
                UPDATE web_jobs
                SET status = 'running',
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW(),
                    locked_by = %s,
                    locked_at = NOW(),
                    params = params - 'api_password'
                WHERE id = %s
                RETURNING *
                """,
                (worker, row["id"]),
            )
            # Return the originally selected row to the worker so it can use the
            # transient password, while the persisted DB row is already scrubbed.
            persisted = dict(cur.fetchone())
            claimed["status"] = persisted["status"]
            claimed["started_at"] = persisted["started_at"]
            claimed["updated_at"] = persisted["updated_at"]
            claimed["locked_by"] = persisted["locked_by"]
            claimed["locked_at"] = persisted["locked_at"]
            conn.commit()
            return _row_to_job(claimed)


def _job_log_file(job_id: str) -> Path:
    from backend.core.config import PROJECT_ROOT

    return PROJECT_ROOT / "data" / "logs" / "web_jobs" / f"{job_id}.log"


def resolve_job_log_text(job: dict[str, Any] | None) -> str:
    """Return log text for the UI, including live output while a job is running."""
    if not job:
        return ""
    stored = (job.get("log_text") or "").strip()
    if stored:
        return job["log_text"]
    if job.get("status") != "running":
        return job.get("log_text") or ""

    log_path = job.get("log_path")
    path = Path(log_path) if log_path else _job_log_file(str(job["id"]))
    if not path.is_absolute():
        from backend.core.config import PROJECT_ROOT

        path = PROJECT_ROOT / path
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return ""


def set_job_log_path(job_id: str, log_path: Path) -> None:
    """Persist log file path so the UI can stream output while the job runs."""
    db.execute(
        """
        UPDATE web_jobs
        SET log_path = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (str(log_path), job_id),
    )


def mark_success(job_id: str, created_files: list[str], log_text: str, log_path: Path | None = None) -> None:
    db.execute(
        """
        UPDATE web_jobs
        SET status = 'success',
            finished_at = NOW(),
            updated_at = NOW(),
            created_files = %s,
            log_text = %s,
            log_path = %s,
            error_message = NULL
        WHERE id = %s
        """,
        (psycopg2.extras.Json(created_files), log_text, str(log_path) if log_path else None, job_id),
    )


def mark_failed(job_id: str, error_message: str, log_text: str, log_path: Path | None = None) -> None:
    db.execute(
        """
        UPDATE web_jobs
        SET status = 'failed',
            finished_at = NOW(),
            updated_at = NOW(),
            log_text = %s,
            log_path = %s,
            error_message = %s
        WHERE id = %s
        """,
        (log_text, str(log_path) if log_path else None, error_message, job_id),
    )


def dashboard_stats() -> dict[str, Any]:
    ensure_web_job_schema()

    def scalar(query: str, default: Any = 0) -> Any:
        try:
            row = db.query_one(query)
            return next(iter(row.values())) if row else default
        except Exception:
            return default

    return {
        "incoming_count": scalar("SELECT COUNT(*) FROM incoming_invoices"),
        "outgoing_count": scalar("SELECT COUNT(*) FROM outgoing_invoices"),
        "agent_run_count": scalar("SELECT COUNT(*) FROM agent_runs"),
        "pending_jobs": scalar("SELECT COUNT(*) FROM web_jobs WHERE status = 'pending'"),
        "running_jobs": scalar("SELECT COUNT(*) FROM web_jobs WHERE status = 'running'"),
        "failed_jobs": scalar("SELECT COUNT(*) FROM web_jobs WHERE status = 'failed'"),
        "last_success": scalar(
            "SELECT MAX(finished_at) FROM web_jobs WHERE status = 'success'",
            None,
        ),
        "last_error": scalar(
            "SELECT error_message FROM web_jobs WHERE status = 'failed' ORDER BY finished_at DESC NULLS LAST LIMIT 1",
            None,
        ),
    }
