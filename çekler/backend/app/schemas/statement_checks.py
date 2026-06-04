from __future__ import annotations

from pydantic import BaseModel, Field

from statement_extractor.src.models import CheckRecord, ParseWarning, StatementMetadata, Summary


class StatementCheckPreviewResponse(BaseModel):
    statement_metadata: StatementMetadata
    summary: Summary
    checks: list[CheckRecord] = Field(default_factory=list)
    warnings: list[ParseWarning] = Field(default_factory=list)


class StatementCheckImportRequest(BaseModel):
    statement_metadata: StatementMetadata
    checks: list[CheckRecord]


class StatementCheckImportError(BaseModel):
    check_no: str | None = None
    message: str


class StatementCheckImportResponse(BaseModel):
    inserted_count: int = 0
    skipped_duplicate_count: int = 0
    error_count: int = 0
    errors: list[StatementCheckImportError] = Field(default_factory=list)


class StatementCheckExportRequest(BaseModel):
    statement_metadata: StatementMetadata
    checks: list[CheckRecord]
    warnings: list[ParseWarning] = Field(default_factory=list)
