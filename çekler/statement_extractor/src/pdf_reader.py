from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import PdfLine, StatementMetadata


class PdfReadError(RuntimeError):
    pass


def read_pdf_lines(pdf_path: str | Path) -> tuple[list[PdfLine], StatementMetadata]:
    path = Path(pdf_path)
    if not path.exists():
        raise PdfReadError(f"PDF dosyası bulunamadı: {path}")
    if path.suffix.lower() != ".pdf":
        raise PdfReadError("Sadece PDF dosyaları işlenebilir.")

    lines: list[PdfLine] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if line:
                        lines.append(PdfLine(page_number=index, text=line))
    except Exception as exc:  # pragma: no cover - library-specific failures
        raise PdfReadError(f"PDF okunamadı: {exc}") from exc

    if not lines:
        raise PdfReadError("PDF metni okunamadı veya taranmış görsel PDF olabilir.")

    metadata = extract_statement_metadata(lines)
    metadata.page_count = page_count
    metadata.source_filename = path.name
    return lines, metadata


def extract_statement_metadata(lines: list[PdfLine]) -> StatementMetadata:
    metadata = StatementMetadata()
    for item in lines[:80]:
        text = item.text
        if "Firma" in text and ":" in text and not metadata.company_name:
            metadata.company_name = clean_metadata_value(text.split(":", 1)[1], stop_markers=("Sayfa No",))
        if "Alt Hesap Kodu" in text and not metadata.account_code:
            match = re.search(r"Alt Hesap Kodu\s*:\s*(.*?)(?:\s+Alt Hesap Adı\s*:|$)", text)
            if match:
                metadata.account_code = match.group(1).strip()
        if "Alt Hesap Adı" in text and not metadata.account_name:
            match = re.search(r"Alt Hesap Adı\s*:\s*(.*)$", text)
            if match:
                metadata.account_name = clean_metadata_value(match.group(1))
        if not metadata.account_code or not metadata.account_name:
            match = re.search(r"\b(?P<code>\d{3}(?:\.\d+)+)\s*/\s*(?P<name>.+)$", text)
            if match:
                metadata.account_code = metadata.account_code or match.group("code").strip()
                metadata.account_name = metadata.account_name or match.group("name").strip()
        if not metadata.company_name:
            match = re.search(r"\)\s*(?P<company>.+?)\s+Tarih Aralığı\s*:", text)
            if match:
                metadata.company_name = match.group("company").strip()
    return metadata


def clean_metadata_value(value: str, stop_markers: tuple[str, ...] = ()) -> str:
    cleaned = value.strip()
    for marker in stop_markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip()
    return cleaned
