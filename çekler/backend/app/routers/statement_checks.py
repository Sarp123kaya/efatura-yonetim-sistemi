from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.app.schemas.statement_checks import (
    StatementCheckExportRequest,
    StatementCheckImportRequest,
    StatementCheckImportResponse,
    StatementCheckPreviewResponse,
)
from backend.app.services.statement_check_import_service import StatementCheckImportService
from statement_extractor.src.models import ParseResult
from statement_extractor.src.parser import build_summary
from statement_extractor.src.pdf_reader import PdfReadError
from statement_extractor.src.service import create_excel_from_parse_result, extract_checks_from_pdf
from statement_extractor.src.utils import safe_filename


router = APIRouter(prefix="/api/statements/checks", tags=["Statement Checks"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/preview", response_model=StatementCheckPreviewResponse)
async def preview_statement_checks(file: UploadFile = File(...)) -> StatementCheckPreviewResponse:
    validate_pdf_upload(file)
    temp_path: Path | None = None
    try:
        temp_path = await persist_upload_temporarily(file)
        parse_result = extract_checks_from_pdf(temp_path)
        parse_result.statement_metadata.source_filename = file.filename
        return StatementCheckPreviewResponse(
            statement_metadata=parse_result.statement_metadata,
            summary=parse_result.summary,
            checks=parse_result.checks,
            warnings=parse_result.warnings,
        )
    except PdfReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


@router.post("/import", response_model=StatementCheckImportResponse)
async def import_statement_checks(payload: StatementCheckImportRequest) -> StatementCheckImportResponse:
    service = StatementCheckImportService()
    return service.import_checks(payload, source_file=payload.statement_metadata.source_filename)


@router.post("/export-excel")
async def export_statement_checks_excel(payload: StatementCheckExportRequest) -> FileResponse:
    parse_result = ParseResult(
        statement_metadata=payload.statement_metadata,
        checks=sorted(
            payload.checks,
            key=lambda item: (item.maturity_date, item.amount or 0, item.transaction_date or date.min),
        ),
        warnings=payload.warnings,
        summary=build_summary(payload.checks, payload.warnings),
    )

    output_dir = Path(tempfile.mkdtemp(prefix="statement_checks_export_"))
    filename_base = safe_filename(payload.statement_metadata.account_name or "cekler")
    output_path = output_dir / f"{filename_base}_cekler.xlsx"
    create_excel_from_parse_result(parse_result, output_path)

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_path.name,
        background=BackgroundTask(cleanup_path, output_path),
    )


def validate_pdf_upload(file: UploadFile) -> None:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece PDF dosyası yüklenebilir.")
    if file.content_type not in (None, "", "application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Dosya tipi PDF olmalı.")


async def persist_upload_temporarily(file: UploadFile) -> Path:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF dosyası çok büyük. En fazla 25 MB yüklenebilir.")
    suffix = Path(file.filename or "statement.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return Path(temp_file.name)


def cleanup_path(path: Path) -> None:
    if path.exists():
        parent = path.parent
        path.unlink()
        try:
            parent.rmdir()
        except OSError:
            pass
