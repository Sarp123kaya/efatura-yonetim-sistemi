from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MovementType(str, Enum):
    RECEIVED_CHECK = "RECEIVED_CHECK"


class CheckSourceType(str, Enum):
    PDF = "PDF"
    EXCEL = "EXCEL"
    IMAGE_OCR = "IMAGE_OCR"
    MANUAL = "MANUAL"


class ReviewStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    IMPORTED = "IMPORTED"
    REJECTED = "REJECTED"


class ImportSessionStatus(str, Enum):
    CREATED = "CREATED"
    PARSED = "PARSED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


class StatementMetadata(BaseModel):
    company_name: Optional[str] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    page_count: int = 0
    source_filename: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class CheckRecord(BaseModel):
    transaction_date: Optional[date] = None
    document_date: Optional[date] = None
    voucher_no: Optional[str] = None
    document_no: Optional[str] = None
    movement_type: MovementType = MovementType.RECEIVED_CHECK
    check_no: str
    bank: str
    maturity_date: date
    maturity_month: str
    amount: Optional[Decimal] = None
    currency: str = "TRY"
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    sent_to: Optional[str] = None
    source_page: int
    raw_description: str
    raw_line: str
    parse_warning: Optional[str] = None


class StoredCheckRecord(CheckRecord):
    source_type: CheckSourceType = CheckSourceType.PDF
    source_file: Optional[str] = None
    import_session_id: Optional[str] = None
    review_status: ReviewStatus = ReviewStatus.APPROVED
    source_row_index: Optional[int] = None
    source_sheet: Optional[str] = None
    source_image_region: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ImportSession(BaseModel):
    import_session_id: str
    source_type: CheckSourceType
    source_file: str
    status: ImportSessionStatus = ImportSessionStatus.CREATED
    statement_metadata: StatementMetadata = Field(default_factory=StatementMetadata)
    total_rows: int = 0
    parsed_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    message: Optional[str] = None


class ImportResult(BaseModel):
    import_session: ImportSession
    records: List[StoredCheckRecord] = Field(default_factory=list)
    warnings: List["ParseWarning"] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class ParseWarning(BaseModel):
    source_page: Optional[int] = None
    raw_line: Optional[str] = None
    warning_type: str
    message: str


class Summary(BaseModel):
    total_count: int = 0
    total_amount: Decimal = Decimal("0")
    earliest_maturity_date: Optional[date] = None
    latest_maturity_date: Optional[date] = None
    bank_totals: Dict[str, Decimal] = Field(default_factory=dict)
    maturity_month_totals: Dict[str, Decimal] = Field(default_factory=dict)
    weekly_maturity_totals: Dict[str, Decimal] = Field(default_factory=dict)
    overdue_total: Decimal = Decimal("0")
    due_in_7_days_total: Decimal = Decimal("0")
    due_in_30_days_total: Decimal = Decimal("0")
    warning_count: int = 0


class ParseResult(BaseModel):
    statement_metadata: StatementMetadata
    checks: List[CheckRecord] = Field(default_factory=list)
    warnings: List[ParseWarning] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    debug_rows: List["DebugRow"] = Field(default_factory=list)


class PdfLine(BaseModel):
    page_number: int
    text: str


class DebugRow(BaseModel):
    source_page: int
    raw_line: str
    parsed: bool
    found_check_no: Optional[str] = None
    found_bank: Optional[str] = None
    found_maturity_date: Optional[date] = None
    found_amounts: List[Decimal] = Field(default_factory=list)
    used_amount: Optional[Decimal] = None
    warning: Optional[str] = None


if hasattr(ParseResult, "model_rebuild"):
    ParseResult.model_rebuild()
    ImportResult.model_rebuild()
else:
    ParseResult.update_forward_refs(DebugRow=DebugRow)
    ImportResult.update_forward_refs(ParseWarning=ParseWarning)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        if hasattr(value, "model_dump"):
            return to_jsonable(value.model_dump(mode="python"))
        return value.dict()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
