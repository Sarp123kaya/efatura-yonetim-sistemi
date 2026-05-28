from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.app.schemas.statement_checks import (
    StatementCheckImportError,
    StatementCheckImportRequest,
    StatementCheckImportResponse,
)
from statement_extractor.src.models import CheckRecord
from statement_extractor.src.validators import duplicate_key, validate_check_record


class StatementCheckRepository(Protocol):
    def exists(self, record: CheckRecord) -> bool:
        ...

    def insert(self, record: CheckRecord, source_file: str | None = None) -> None:
        ...


class StatementCheckImportService:
    def __init__(self, repository: StatementCheckRepository | None = None) -> None:
        self.repository = repository

    def import_checks(self, request: StatementCheckImportRequest, source_file: str | None = None) -> StatementCheckImportResponse:
        response = StatementCheckImportResponse()
        seen_payload_keys: set[tuple[str | None, str, str, str, Decimal | None]] = set()

        if self.repository is None:
            response.errors.append(
                StatementCheckImportError(
                    message=(
                        "PostgreSQL repository henüz bağlanmadı. Preview/export çalışır; "
                        "kalıcı import için backend DB katmanına StatementCheckRepository uygulanmalı."
                    )
                )
            )
            response.error_count = len(response.errors)
            return response

        for record in request.checks:
            validation_errors = validate_check_record(record)
            if validation_errors:
                response.errors.append(
                    StatementCheckImportError(check_no=record.check_no, message=" ".join(validation_errors))
                )
                continue

            key = duplicate_key(record)
            if key in seen_payload_keys or self.repository.exists(record):
                response.skipped_duplicate_count += 1
                continue

            seen_payload_keys.add(key)
            try:
                self.repository.insert(record, source_file=source_file)
                response.inserted_count += 1
            except Exception as exc:  # pragma: no cover - concrete repository behavior
                response.errors.append(StatementCheckImportError(check_no=record.check_no, message=str(exc)))

        response.error_count = len(response.errors)
        return response
