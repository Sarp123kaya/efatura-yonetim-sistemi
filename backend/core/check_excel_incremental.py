#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yeni çek Excel dosyasını önceki snapshot ile karşılaştırır;
yalnızca eklenen / değişen satırları içeri aktarmaya aday yapar.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.core.config import PROJECT_ROOT

_CEKKER_DIR = PROJECT_ROOT / "çekler"
if str(_CEKKER_DIR) not in sys.path:
    sys.path.insert(0, str(_CEKKER_DIR))

from statement_extractor.src.diff_models import DiffType  # noqa: E402
from statement_extractor.src.excel_compare import compare_excel_files  # noqa: E402
from statement_extractor.src.snapshot_manager import (  # noqa: E402
    create_snapshot,
    find_latest_snapshot,
    read_snapshot_metadata,
)

DEFAULT_SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "check_excel_snapshots"


def normalize_check_no(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


@dataclass
class IncrementalImportPlan:
    is_first_upload: bool
    compared_with_snapshot: bool
    old_snapshot_id: Optional[str] = None
    added_count: int = 0
    modified_count: int = 0
    unchanged_count: int = 0
    removed_count: int = 0
    check_nos_to_import: Optional[set[str]] = None
    modified_check_nos: set[str] = field(default_factory=set)


def find_baseline_snapshot(
    new_filename: str,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> Optional[object]:
    """Önce aynı dosya adı, yoksa en son snapshot."""
    by_name = find_latest_snapshot(new_filename, snapshots_dir)
    if by_name is not None:
        return by_name
    if not snapshots_dir.exists():
        return None
    candidates = []
    for meta_path in snapshots_dir.glob("*.json"):
        try:
            candidates.append(read_snapshot_metadata(meta_path))
        except (OSError, ValueError, KeyError):
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.created_at)


def build_incremental_plan(
    new_excel_path: Path,
    *,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> IncrementalImportPlan:
    baseline = find_baseline_snapshot(new_excel_path.name, snapshots_dir)
    if baseline is None:
        return IncrementalImportPlan(is_first_upload=True, compared_with_snapshot=False)

    report = compare_excel_files(
        baseline.snapshot_file,
        new_excel_path,
        old_snapshot_id=baseline.snapshot_id,
        new_snapshot_id=new_excel_path.stem,
        source_file=new_excel_path.name,
    )

    check_nos: set[str] = set()
    modified_nos: set[str] = set()
    for row_diff in report.row_diffs:
        if row_diff.diff_type not in (DiffType.ADDED, DiffType.MODIFIED):
            continue
        if row_diff.check_no:
            norm = normalize_check_no(row_diff.check_no)
            if norm:
                check_nos.add(norm)
                if row_diff.diff_type == DiffType.MODIFIED:
                    modified_nos.add(norm)

    return IncrementalImportPlan(
        is_first_upload=False,
        compared_with_snapshot=True,
        old_snapshot_id=baseline.snapshot_id,
        added_count=report.added_count,
        modified_count=report.modified_count,
        unchanged_count=report.unchanged_count,
        removed_count=report.removed_count,
        check_nos_to_import=check_nos,
        modified_check_nos=modified_nos,
    )


def record_should_import(
    check_no: str,
    plan: IncrementalImportPlan,
) -> bool:
    if plan.is_first_upload or plan.check_nos_to_import is None:
        return True
    return normalize_check_no(check_no) in plan.check_nos_to_import


def save_snapshot_after_upload(
    excel_path: Path,
    *,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> None:
    create_snapshot(excel_path, snapshots_dir)


def filter_import_records(records, plan: IncrementalImportPlan) -> list:
    filtered = [r for r in records if record_should_import(r.check_no, plan)]
    if (
        plan.compared_with_snapshot
        and not filtered
        and plan.check_nos_to_import is not None
        and (plan.added_count + plan.modified_count) > 0
        and records
    ):
        return list(records)
    return filtered
