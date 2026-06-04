from __future__ import annotations

from datetime import date
from pathlib import Path

from .excel_writer import write_parse_result_to_excel
from .models import ParseResult
from .parser import parse_statement_lines
from .pdf_reader import read_pdf_lines


def extract_checks_from_pdf(pdf_path: str | Path, today: date | None = None) -> ParseResult:
    lines, metadata = read_pdf_lines(pdf_path)
    return parse_statement_lines(lines, metadata=metadata, today=today)


def create_excel_from_parse_result(
    parse_result: ParseResult,
    output_path: str | Path,
    today: date | None = None,
    include_debug: bool = True,
    include_overdue_in_value_calc: bool = False,
) -> Path:
    return write_parse_result_to_excel(
        parse_result,
        output_path,
        today=today,
        include_debug=include_debug,
        include_overdue_in_value_calc=include_overdue_in_value_calc,
    )
