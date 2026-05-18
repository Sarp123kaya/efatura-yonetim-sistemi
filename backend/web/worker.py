#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Background worker for web panel jobs."""

from __future__ import annotations

import argparse
import io
import os
import socket
import sys
import time
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Iterable

from backend.core.config import PROJECT_ROOT, config
from backend.core.db import db
from backend.web.actions import ACTIONS
from backend.web.jobs import claim_next_job, mark_failed, mark_success

LOCK_NAME = "web_invoice_pipeline_exclusive_lock"


class Tee(io.TextIOBase):
    """Write captured process output to memory and to a log file."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _logs_dir() -> Path:
    path = PROJECT_ROOT / "data" / "logs" / "web_jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _relative_paths(paths: Iterable[Path]) -> list[str]:
    result = []
    for path in paths:
        try:
            result.append(str(path.resolve().relative_to(PROJECT_ROOT)))
        except ValueError:
            result.append(str(path.resolve()))
    return result


def _run_with_optional_lock(action_key: str, params: dict) -> list[Path]:
    action = ACTIONS[action_key]
    if not action.exclusive:
        return action.runner(params)

    with db.get_connection(auto_commit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK_NAME,))
            locked = cur.fetchone()[0]
            if not locked:
                raise RuntimeError("Başka bir pipeline/export işi çalışıyor. Lütfen mevcut işin bitmesini bekleyin.")
            try:
                return action.runner(params)
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_NAME,))


@contextmanager
def transient_isbasi_password(params: dict):
    """Expose a form-provided API password only for the current job run."""
    password = str(params.pop("api_password", "") or "").strip()
    if not password:
        yield
        return

    old_env_password = os.environ.get("ISBASI_PASSWORD")
    old_config_password = config.ISBASI_PASSWORD
    os.environ["ISBASI_PASSWORD"] = password
    config.ISBASI_PASSWORD = password
    try:
        yield
    finally:
        if old_env_password is None:
            os.environ.pop("ISBASI_PASSWORD", None)
        else:
            os.environ["ISBASI_PASSWORD"] = old_env_password
        config.ISBASI_PASSWORD = old_config_password


def process_one(worker_name: str) -> bool:
    job = claim_next_job(worker_name)
    if not job:
        return False

    job_id = str(job["id"])
    action_key = job["type"]
    params = job.get("params") or {}
    log_path = _logs_dir() / f"{job_id}.log"
    buffer = io.StringIO()

    try:
        if action_key not in ACTIONS:
            raise ValueError(f"Bilinmeyen web job tipi: {action_key}")

        with log_path.open("w", encoding="utf-8") as log_file:
            tee = Tee(buffer, log_file, sys.__stdout__)
            with redirect_stdout(tee), redirect_stderr(tee):
                print(f"Job ID: {job_id}")
                print(f"Action: {ACTIONS[action_key].label}")
                print(f"Worker: {worker_name}")
                print()
                with transient_isbasi_password(params):
                    created_files = _run_with_optional_lock(action_key, params)
                print()
                print("Oluşturulan dosyalar:")
                for path in created_files:
                    print(f"  - {path}")

        mark_success(job_id, _relative_paths(created_files), buffer.getvalue(), log_path)
        return True
    except Exception as exc:
        trace = traceback.format_exc()
        message = f"{exc}"
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write("\nHATA:\n")
            log_file.write(trace)
        buffer.write("\nHATA:\n")
        buffer.write(trace)
        mark_failed(job_id, message, buffer.getvalue(), log_path)
        return True
    finally:
        db.close_persistent_connection()


def run_worker(poll_seconds: float = 3.0, once: bool = False, worker_name: str | None = None) -> None:
    name = worker_name or f"{socket.gethostname()}:{os_getpid()}"
    while True:
        worked = process_one(name)
        if once:
            return
        if not worked:
            time.sleep(poll_seconds)


def os_getpid() -> int:
    import os

    return os.getpid()


def main() -> None:
    parser = argparse.ArgumentParser(description="Web panel job worker")
    parser.add_argument("--once", action="store_true", help="Tek job işle ve çık")
    parser.add_argument("--poll-seconds", type=float, default=3.0, help="Boş kuyrukta bekleme süresi")
    parser.add_argument("--worker-name", help="Log ve job kilidi için worker adı")
    args = parser.parse_args()
    run_worker(poll_seconds=args.poll_seconds, once=args.once, worker_name=args.worker_name)


if __name__ == "__main__":
    main()
