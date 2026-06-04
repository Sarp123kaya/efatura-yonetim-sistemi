from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class DiffType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"


@dataclass
class ExcelSnapshot:
    snapshot_id: str
    source_file: str
    snapshot_file: str
    created_at: datetime
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    company_name: Optional[str] = None
    row_count: int = 0
    total_amount: Decimal = Decimal("0")


@dataclass
class FieldChange:
    row_identity: str
    field_name: str
    old_value: Any
    new_value: Any


@dataclass
class RowDiff:
    diff_type: DiffType
    row_identity: str
    check_no: Optional[str] = None
    bank: Optional[str] = None
    maturity_date: Optional[date] = None
    amount: Optional[Decimal] = None
    changes: list[FieldChange] = field(default_factory=list)
    identity_method: str = "row_index"
    old_row: dict[str, Any] = field(default_factory=dict)
    new_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExcelDiffReport:
    old_snapshot_id: str
    new_snapshot_id: str
    source_file: str
    generated_at: datetime
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    company_name: Optional[str] = None
    added_count: int = 0
    removed_count: int = 0
    modified_count: int = 0
    unchanged_count: int = 0
    old_total_amount: Decimal = Decimal("0")
    new_total_amount: Decimal = Decimal("0")
    amount_difference: Decimal = Decimal("0")
    row_diffs: list[RowDiff] = field(default_factory=list)


def dataclass_to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [dataclass_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_jsonable(item) for key, item in value.items()}
    return value
