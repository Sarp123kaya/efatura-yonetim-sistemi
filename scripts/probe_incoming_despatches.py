#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export incoming Isbasi e-despatch list fields."""

from __future__ import annotations

import argparse
import base64
import glob
import gzip
import io
import json
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.outgoing_agent import OutgoingInvoiceAgent
from backend.core.config import config
from backend.core.db import db
from backend.core.incoming_despatch_cache import (
    ensure_incoming_despatch_description_cache_schema,
    get_cached_despatch_description,
    upsert_despatch_description_cache,
)
from backend.core.isbasi_client import IsbasiAPIError, IsbasiApiClient
from backend.core.normalize import normalize_incoming_despatch
from scripts.match_incoming_despatches_to_outgoing import generate_match_report


SWAGGER_BASE_URL = "https://isbasimw.isbasi.com"
DESPATCH_DEFAULT_START_DATE = "2026-01-01"

ENDPOINT_CANDIDATES = [
    "/api/v1.0/dispatch/mydispatchlist",
    "/api/v1.0/dispatch/dispatches?type=2",
    "/api/v1.0/dispatch/dispatches?type=1",
    "/api/v1.0/edespatches/despatches",
    "/api/v1.0/edespatches/incomingdespatches",
    "/api/v1.0/edespatches/incomingDespatches",
    "/api/v1.0/edespatches/incoming",
    "/api/v1.0/edespatches/inbox",
    "/api/v1.0/edespatches/received",
    "/api/v1.0/edespatches/receiveddespatches",
    "/api/v1.0/eDespatches/eDespatches",
    "/api/v1.0/eDespatches/incomingDespatches",
    "/api/v1.0/eDespatches/incoming",
    "/api/v1.0/eDespatches/inbox",
    "/api/v1.0/despatches/despatches",
    "/api/v1.0/despatches/incomingdespatches",
    "/api/v1.0/despatches/incoming",
    "/api/v1.0/despatches/inbox",
    "/api/v1.0/dispatches/dispatches",
    "/api/v1.0/dispatches/incoming",
    "/api/v1.0/ewaybills/ewaybills",
    "/api/v1.0/ewaybills/incoming",
    "/api/v1.0/eirsaliyeler",
    "/api/v1.0/eirsaliyeler/gelen",
]

DATE_COLUMNS = ["issueDate", "date", "despatchDate", "dispatchDate"]

FIELD_ALIASES = {
    "irsaliye_no": [
        "dispatchId",
        "despatchNumber",
        "dispatchNumber",
        "despatchNo",
        "dispatchNo",
        "number",
        "documentNumber",
        "id",
    ],
    "irsaliye_tarihi": [
        "issueDate",
        "despatchDate",
        "dispatchDate",
        "date",
        "issueDate",
        "documentDate",
    ],
    "tedarikci": [
        "supplier",
        "supplierName",
        "firmName",
        "senderName",
        "customerName",
        "title",
    ],
    "irsaliye_aciklamasi": [
        "description",
        "extraDescription",
        "etradeDescription",
        "message",
    ],
}


def default_start_date() -> str:
    return DESPATCH_DEFAULT_START_DATE


def parse_date_arg(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def list_payload(page: int, page_size: int, start_date: str, end_date: str, date_column: str) -> Dict[str, Any]:
    return {
        "filters": [
            {"columnName": date_column, "operator": 5, "value": f"{start_date}T00:00:00"},
            {"columnName": date_column, "operator": 2, "value": f"{end_date}T23:59:59"},
        ],
        "sorting": {date_column: -1},
        "paging": {"currentPage": page, "pageSize": page_size},
        "columnNames": None,
        "count": True,
        "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
    }


def rows_from_payload(payload: Any) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            rows = data.get("data") or data.get("items") or data.get("result") or []
            count = data.get("count") or data.get("totalCount")
            return [row for row in rows if isinstance(row, dict)], count
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)], len(data)
        rows = payload.get("items") or payload.get("result") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)], payload.get("count")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], len(payload)
    return [], None


def pick(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return ""


def decode_document_content(content: str) -> bytes:
    raw = base64.b64decode(content)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            first = zf.namelist()[0]
            return zf.read(first)
    except zipfile.BadZipFile:
        pass
    try:
        return gzip.decompress(raw)
    except gzip.BadGzipFile:
        return raw


def bytes_to_text(payload: bytes, document_type: str = "") -> str:
    kind = str(document_type or "").lower()
    if "pdf" in kind or payload.startswith(b"%PDF"):
        try:
            import PyPDF2  # type: ignore

            reader = PyPDF2.PdfReader(io.BytesIO(payload))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            pass
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(io.BytesIO(payload)) as pdf:
                return "\n\n-- PAGE BREAK --\n\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return ""

    for encoding in ("utf-8", "iso-8859-9", "windows-1254"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def extract_description_from_text(text: str) -> str:
    if not text:
        return ""

    notes = re.findall(r"<(?:cbc:)?Note[^>]*>(.*?)</(?:cbc:)?Note>", text, flags=re.IGNORECASE | re.DOTALL)
    if notes:
        cleaned_notes = []
        for note in notes:
            cleaned = re.sub(r"<[^>]+>", " ", note)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                cleaned_notes.append(cleaned)
        if cleaned_notes:
            return " | ".join(dict.fromkeys(cleaned_notes))

    match = re.search(
        r"Açıklamalar\s*(.*?)(?:Taşıyıcı Bilgileri|Sıra\s*No|Toplam Tutar|İlgili Dokümanlar)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        cleaned = re.sub(r"\s+", " ", match.group(1)).strip()
        if cleaned:
            return cleaned

    heading = re.search(r"Açıklamalar(?:\s+Taşıyıcı Bilgileri)?\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if heading:
        body = heading.group(1)
        stop_positions = [
            pos
            for marker in ("\nAK GİPS", "\nFULLBOARD", "\nSAYIN", "\ne-İRSALİYE", "\n-- PAGE BREAK --")
            for pos in [body.upper().find(marker.upper())]
            if pos > 0
        ]
        if stop_positions:
            body = body[: min(stop_positions)]

        lines = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.split(
                r"\s+(?:Taşıyıcı Firma:|Araç plaka numarası:|Dorse plaka numarası:|Şoför:)",
                line,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            if line:
                lines.append(line)
        cleaned = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if cleaned:
            return cleaned

    return ""


def parse_pdf_despatch_descriptions(pdf_paths: Iterable[Path]) -> Dict[str, Dict[str, str]]:
    """Read İşbaşı web-panel PDF exports and index descriptions by UUID and dispatch number."""

    index: Dict[str, Dict[str, str]] = {}
    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            print(f"   PDF bulunamadı, atlanıyor: {pdf_path}")
            continue

        text = bytes_to_text(pdf_path.read_bytes(), "pdf")
        if not text:
            print(f"   PDF okunamadı, atlanıyor: {pdf_path}")
            continue

        blocks = re.split(r"\n\s*(?:--\s+\d+\s+of\s+\d+\s+--|-- PAGE BREAK --)\s*\n", text)
        found = 0
        for block in blocks:
            dispatch_match = re.search(r"İrsaliye\s+No:\s*(IRS\d+)", block, flags=re.IGNORECASE)
            uuid_match = re.search(r"ETTN:\s*([0-9A-Fa-f-]{36})", block)
            description = extract_description_from_text(block)
            if not description or not (dispatch_match or uuid_match):
                continue

            record = {
                "description": description,
                "document_text": block.strip(),
                "fetch_source": str(pdf_path),
                "fetch_status": "success",
            }
            if dispatch_match:
                index[dispatch_match.group(1).upper()] = record
            if uuid_match:
                index[uuid_match.group(1).upper()] = record
            found += 1
        print(f"   PDF açıklama okundu: {pdf_path} ({found} irsaliye)")
    return index


def expand_pdf_paths(values: Iterable[str]) -> List[Path]:
    paths: List[Path] = []
    for value in values:
        raw_path = Path(value).expanduser()
        if raw_path.is_dir():
            paths.extend(sorted(raw_path.glob("*.pdf")))
            continue

        matches = [Path(match) for match in sorted(glob.glob(str(raw_path)))] if any(char in str(raw_path) for char in "*?[]") else []
        paths.extend(matches or [raw_path])

    seen = set()
    unique_paths = []
    for path in paths:
        resolved_key = str(path.resolve()) if path.exists() else str(path)
        if resolved_key in seen:
            continue
        seen.add(resolved_key)
        unique_paths.append(path)
    return unique_paths


def extract_description_from_payload(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    data = value.get("data") if isinstance(value.get("data"), dict) else value
    if not isinstance(data, dict):
        return ""

    candidates = []
    for key in ("description", "extraDescription", "etradeDescription", "message", "note", "notes"):
        raw = data.get(key)
        if raw not in (None, "", []):
            if isinstance(raw, list):
                candidates.extend(str(item) for item in raw if item not in (None, ""))
            else:
                candidates.append(str(raw))

    for nested_key in ("dispatchLines", "eDispatchDetails", "lines"):
        lines = data.get(nested_key)
        if isinstance(lines, list):
            for item in lines:
                if not isinstance(item, dict):
                    continue
                for key in ("description", "lineDescription", "note"):
                    raw = item.get(key)
                    if raw not in (None, ""):
                        candidates.append(str(raw))

    cleaned = []
    for candidate in candidates:
        text = re.sub(r"\s+", " ", candidate).strip()
        if text:
            cleaned.append(text)
    return " | ".join(dict.fromkeys(cleaned))


def fetch_description_for_row(client: IsbasiApiClient, row: Dict[str, Any]) -> Dict[str, str]:
    uuid = str(row.get("uuId") or row.get("uuid") or "").strip()
    dispatch_pk = str(row.get("id") or "").strip()
    if not uuid and not dispatch_pk:
        return {"description": "", "document_text": "", "fetch_source": "", "fetch_status": "missing_uuid"}

    if dispatch_pk:
        for path in (f"/api/v1.0/dispatch/{dispatch_pk}",):
            for params in ({}, {"type": 1}, {"type": 2}):
                try:
                    payload = client.get(path, params=params)
                except Exception:
                    continue
                description = extract_description_from_payload(payload)
                if description:
                    return {
                        "description": description,
                        "document_text": json.dumps(payload, ensure_ascii=False),
                        "fetch_source": f"{path}?{params}",
                        "fetch_status": "success",
                    }

    attempts = [
        ("/api/v1.0/einvoices/DocumentUblDatawithuuid", {"uuid": uuid, "type": 1}),
        ("/api/v1.0/einvoices/DocumentUblDatawithuuid", {"uuid": uuid, "type": 2}),
        ("/api/v1.0/einvoices/DocumentDatawithuuid", {"uuid": uuid, "fileFormat": "PDF"}),
    ]
    for path, params in attempts:
        try:
            payload = client.get(path, params=params)
        except Exception:
            continue
        data = payload.get("data") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            continue
        content = data.get("content")
        if not content:
            continue
        try:
            decoded = decode_document_content(str(content))
        except Exception:
            continue
        document_text = bytes_to_text(decoded, str(data.get("type") or ""))
        description = extract_description_from_text(document_text)
        if description:
            return {
                "description": description,
                "document_text": document_text,
                "fetch_source": f"{path}?{params}",
                "fetch_status": "success",
            }
    return {"description": "", "document_text": "", "fetch_source": "all_attempts", "fetch_status": "not_found"}


def enrich_descriptions(
    client: IsbasiApiClient,
    rows: List[Dict[str, Any]],
    *,
    limit: int = 0,
    refresh: bool = False,
    pdf_descriptions: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    ensure_incoming_despatch_description_cache_schema()
    total = len(rows) if limit <= 0 else min(len(rows), limit)
    cache_hits = 0
    fetched = 0
    pdf_hits = 0
    for idx, row in enumerate(rows[:total], 1):
        if row.get("description") or row.get("extraDescription"):
            continue
        uuid = str(row.get("uuId") or row.get("uuid") or "").strip()
        dispatch_id = str(row.get("dispatchId") or "").strip()
        pdf_result = None
        if pdf_descriptions:
            pdf_result = pdf_descriptions.get(uuid.upper()) or pdf_descriptions.get(dispatch_id.upper())
        if pdf_result and pdf_result.get("description"):
            row["description"] = pdf_result["description"]
            pdf_hits += 1
            if uuid:
                upsert_despatch_description_cache(
                    uuid=uuid,
                    dispatch_id=dispatch_id,
                    supplier=str(row.get("supplier") or ""),
                    description=pdf_result.get("description", ""),
                    document_text=pdf_result.get("document_text", ""),
                    fetch_source=pdf_result.get("fetch_source", ""),
                    fetch_status=pdf_result.get("fetch_status", "success"),
                )
            if idx % 10 == 0 or idx == total:
                print(f"   Açıklama PDF: {pdf_hits}, cache: {cache_hits}, API: {fetched}, ilerleme: {idx}/{total}")
            continue
        if uuid and not refresh:
            cached = get_cached_despatch_description(uuid)
            if cached:
                cached_description = cached.get("description") or ""
                cached_source = cached.get("fetch_source") or ""
                if cached_description or cached_source == "all_attempts":
                    row["description"] = cached_description
                    cache_hits += 1
                    if idx % 10 == 0 or idx == total:
                        print(f"   Açıklama PDF: {pdf_hits}, cache: {cache_hits}, API: {fetched}, ilerleme: {idx}/{total}")
                    continue

        fetched_result = fetch_description_for_row(client, row)
        fetched += 1
        description = fetched_result.get("description", "")
        if description:
            row["description"] = description
        if uuid:
            upsert_despatch_description_cache(
                uuid=uuid,
                dispatch_id=str(row.get("dispatchId") or ""),
                supplier=str(row.get("supplier") or ""),
                description=description,
                document_text=fetched_result.get("document_text", ""),
                fetch_source=fetched_result.get("fetch_source", ""),
                fetch_status=fetched_result.get("fetch_status", "not_found"),
            )
        if idx % 10 == 0 or idx == total:
            print(f"   Açıklama PDF: {pdf_hits}, cache: {cache_hits}, API: {fetched}, ilerleme: {idx}/{total}")


def to_despatch_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        record = {name: pick(row, aliases) for name, aliases in FIELD_ALIASES.items()}
        record["prefixli_kod"] = normalize_incoming_despatch(
            str(record.get("irsaliye_no") or ""),
            str(record.get("tedarikci") or ""),
        ) or ""
        cleaned.append(record)
    return cleaned


def write_json_output(
    raw_rows: List[Dict[str, Any]],
    endpoint: str,
    date_column: str,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = PROJECT_ROOT / "data" / "logs" / f"incoming_despatch_probe_{stamp}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(
            {
                "endpoint": endpoint,
                "date_column": date_column,
                "row_count": len(raw_rows),
                "raw_rows": raw_rows,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return json_path


def try_endpoint(
    client: IsbasiApiClient,
    endpoint: str,
    *,
    start_date: str,
    end_date: str,
    page_size: int,
    max_pages: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    attempts = []
    for date_column in DATE_COLUMNS:
        all_rows: List[Dict[str, Any]] = []
        count: Optional[int] = None
        for page in range(1, max_pages + 1):
            payload = list_payload(page, page_size, start_date, end_date, date_column)
            try:
                result = client.post(endpoint, payload)
            except IsbasiAPIError as exc:
                attempts.append({"date_column": date_column, "error": str(exc)})
                break

            rows, count = rows_from_payload(result)
            if not rows:
                attempts.append({"date_column": date_column, "status": "empty", "count": count})
                break
            all_rows.extend(rows)
            if len(rows) < page_size or (count is not None and len(all_rows) >= int(count)):
                break

        if all_rows:
            return all_rows, {"endpoint": endpoint, "date_column": date_column, "count": count}

    return [], {"endpoint": endpoint, "attempts": attempts}


def refresh_outgoing_invoices(start_date: str, end_date: str) -> None:
    print("Giden faturalar güncelleniyor...")
    agent = OutgoingInvoiceAgent(run_id=f"despatch_match_outgoing_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    agent.run(start_date=parse_date_arg(start_date), end_date=parse_date_arg(end_date))
    db.close_persistent_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description="Isbasi gelen e-irsaliye listesini export eder.")
    parser.add_argument("--start-date", default=default_start_date(), help="Baslangic tarihi (YYYY-MM-DD).")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Bitis tarihi (YYYY-MM-DD).")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--output-dir", default="kayıtlar")
    parser.add_argument(
        "--fetch-descriptions",
        action="store_true",
        help="Her irsaliye UUID'si icin UBL/PDF belge iceriginden Aciklamalar alanini cek.",
    )
    parser.add_argument(
        "--description-limit",
        type=int,
        default=0,
        help="Açıklama çekilecek maksimum kayıt sayısı (0 = tüm kayıtlar).",
    )
    parser.add_argument(
        "--refresh-descriptions",
        action="store_true",
        help="Açıklama cache'ini yok sayıp UBL/PDF belgelerini yeniden çek.",
    )
    parser.add_argument(
        "--description-pdf",
        action="append",
        default=[],
        help="İşbaşı web panelinden indirilen e-irsaliye PDF export'u. Birden fazla kez verilebilir.",
    )
    parser.add_argument(
        "--skip-outgoing-refresh",
        action="store_true",
        help="Eşleştirme Excel'i üretilmeden önce giden faturaları API'den güncelleme.",
    )
    parser.add_argument(
        "--base-url",
        default=SWAGGER_BASE_URL,
        help="Isbasi API base URL. Swagger host: https://isbasimw.isbasi.com",
    )
    args = parser.parse_args()

    if not config.ISBASI_PASSWORD and not sys.stdin.isatty():
        raise SystemExit("ISBASI_PASSWORD .env icinde yok. Interaktif terminalde calistirin veya .env'e ISBASI_PASSWORD ekleyin.")

    client = IsbasiApiClient(base_url=args.base_url or config.ISBASI_BASE_URL)
    login_state = client.login()
    diagnostics = []
    auth_variants = [
        ("raw-token", login_state.access_token),
        ("bearer-token", f"Bearer {login_state.access_token}"),
    ]
    for auth_name, authorization in auth_variants:
        client.session.headers.update({"Authorization": authorization})
        for endpoint in ENDPOINT_CANDIDATES:
            print(f"Deniyorum: {endpoint} ({auth_name})")
            rows, info = try_endpoint(
                client,
                endpoint,
                start_date=args.start_date,
                end_date=args.end_date,
                page_size=args.page_size,
                max_pages=args.max_pages,
            )
            info["auth"] = auth_name
            diagnostics.append(info)
            if rows:
                pdf_descriptions = None
                if args.fetch_descriptions:
                    pdf_paths = expand_pdf_paths(args.description_pdf)
                    pdf_descriptions = parse_pdf_despatch_descriptions(pdf_paths) if pdf_paths else None
                    print("İrsaliye açıklamaları UBL/PDF belgelerinden çekiliyor...")
                    enrich_descriptions(
                        client,
                        rows,
                        limit=args.description_limit,
                        refresh=args.refresh_descriptions,
                        pdf_descriptions=pdf_descriptions,
                    )
                json_path = write_json_output(rows, endpoint, info["date_column"])
                print(f"Bulundu: {endpoint} ({len(rows)} kayit, {auth_name})")
                print(f"Ham JSON: {json_path}")
                if args.fetch_descriptions:
                    if not args.skip_outgoing_refresh:
                        refresh_outgoing_invoices(args.start_date, args.end_date)
                    print("Eşleştirme Excel raporu oluşturuluyor...")
                    report_path = generate_match_report(json_path, Path(args.output_dir), print_summary=True)
                    print(f"Eşleştirme Excel: {report_path}")
                return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = PROJECT_ROOT / "data" / "logs" / f"incoming_despatch_probe_fail_{stamp}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    raise SystemExit(f"E-irsaliye endpointi bulunamadi. Deneme logu: {log_path}")


if __name__ == "__main__":
    try:
        main()
    finally:
        db.close_persistent_connection()
