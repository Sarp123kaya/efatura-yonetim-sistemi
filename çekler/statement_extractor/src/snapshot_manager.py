from __future__ import annotations

import json
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from .diff_models import ExcelSnapshot, dataclass_to_jsonable
from .excel_compare import load_excel_rows
from .utils import safe_filename


def create_snapshot(
    excel_path: str | Path,
    snapshots_dir: str | Path,
    metadata: Optional[dict[str, Any]] = None,
) -> ExcelSnapshot:
    source_path = Path(excel_path)
    snapshots_path = Path(snapshots_dir)
    snapshots_path.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now()
    source_name = safe_filename(source_path.stem, default="excel")
    snapshot_id = f"{source_name}_{created_at.strftime('%Y%m%d_%H%M%S_%f')}"
    snapshot_file = snapshots_path / f"{snapshot_id}.xlsx"
    shutil.copy2(source_path, snapshot_file)

    workbook_data = load_excel_rows(snapshot_file)
    rows = workbook_data["rows"]
    total_amount = sum((row.get("amount_decimal") or Decimal("0") for row in rows), Decimal("0"))
    merged_metadata = {**workbook_data, **(metadata or {})}

    snapshot = ExcelSnapshot(
        snapshot_id=snapshot_id,
        source_file=source_path.name,
        snapshot_file=str(snapshot_file),
        created_at=created_at,
        account_code=merged_metadata.get("account_code"),
        account_name=merged_metadata.get("account_name"),
        company_name=merged_metadata.get("company_name"),
        row_count=len(rows),
        total_amount=total_amount,
    )
    write_snapshot_metadata(snapshot, snapshots_path)
    return snapshot


def find_latest_snapshot(source_file: str | Path, snapshots_dir: str | Path) -> Optional[ExcelSnapshot]:
    source_name = Path(source_file).name
    snapshots_path = Path(snapshots_dir)
    if not snapshots_path.exists():
        return None

    candidates: list[ExcelSnapshot] = []
    for metadata_path in snapshots_path.glob("*.json"):
        try:
            snapshot = read_snapshot_metadata(metadata_path)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if snapshot.source_file == source_name:
            candidates.append(snapshot)

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.created_at)[-1]


def write_snapshot_metadata(snapshot: ExcelSnapshot, snapshots_dir: str | Path) -> Path:
    path = Path(snapshots_dir) / f"{snapshot.snapshot_id}.json"
    path.write_text(json.dumps(dataclass_to_jsonable(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_snapshot_metadata(metadata_path: str | Path) -> ExcelSnapshot:
    data = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    return ExcelSnapshot(
        snapshot_id=data["snapshot_id"],
        source_file=data["source_file"],
        snapshot_file=data["snapshot_file"],
        created_at=datetime.fromisoformat(data["created_at"]),
        account_code=data.get("account_code"),
        account_name=data.get("account_name"),
        company_name=data.get("company_name"),
        row_count=int(data.get("row_count") or 0),
        total_amount=Decimal(str(data.get("total_amount") or "0")),
    )
