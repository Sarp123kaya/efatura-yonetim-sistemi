#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Customer check import, matching, dry-run and audit helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .db import DatabaseHelper, db as default_db
from .isbasi_client import IsbasiApiClient, IsbasiAPIError
from .isbasi_endpoints import payment_endpoint_verification

logger = logging.getLogger(__name__)


REQUIRED_CHECK_FIELDS = ("firm_name", "tax_id", "check_number", "due_date", "amount")


COLUMN_ALIASES: Dict[str, Sequence[str]] = {
    "firm_name": (
        "firma",
        "firma adi",
        "firma adı",
        "musteri",
        "müşteri",
        "musteri adi",
        "müşteri adı",
        "unvan",
        "cari",
        "cari adi",
        "cari adı",
    ),
    "tax_id": (
        "vkn",
        "tckn",
        "vkn/tckn",
        "tckn/vkn",
        "vergi no",
        "vergi numarasi",
        "vergi numarası",
        "tc kimlik no",
        "tc kimlik numarasi",
        "tc kimlik numarası",
    ),
    "check_number": (
        "cek no",
        "çek no",
        "cek numarasi",
        "çek numarası",
        "belge no",
        "evrak no",
        "portfoy no",
        "portföy no",
    ),
    "due_date": (
        "vade",
        "vade tarihi",
        "cek vadesi",
        "çek vadesi",
        "odeme tarihi",
        "ödeme tarihi",
    ),
    "amount": (
        "tutar",
        "cek tutari",
        "çek tutarı",
        "odeme tutari",
        "ödeme tutarı",
        "borc",
        "borç",
        "alacak",
    ),
    "currency": ("doviz", "döviz", "para birimi", "currency"),
    "bank_name": ("banka", "banka adi", "banka adı"),
    "description": ("aciklama", "açıklama", "not", "description"),
    "firm_code": ("firma kodu", "cari kodu", "code"),
    "firm_id": ("firma id", "cari id", "id"),
}


@dataclass
class CustomerCheckRow:
    source_row: int
    firm_name: str
    tax_id: str
    check_number: str
    due_date: date
    amount: Decimal
    currency: str = "TL"
    bank_name: str = ""
    description: str = ""
    firm_code: str = ""
    firm_id: str = ""
    parse_errors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def idempotency_key(self) -> str:
        material = "|".join(
            [
                normalize_tax_id(self.tax_id),
                normalize_text(self.check_number),
                self.due_date.isoformat(),
                format_decimal(self.amount),
                normalize_text(self.currency or "TL"),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class FirmCard:
    id: str
    code: str
    name: str
    display_name: str
    firm_type: str
    tax_id: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, row: Dict[str, Any]) -> "FirmCard":
        tax_id = row.get("vknTckn") or row.get("taxOrPersonalId") or row.get("taxNo") or ""
        return cls(
            id=str(row.get("id") or row.get("firmId") or ""),
            code=str(row.get("code") or row.get("firmCode") or ""),
            name=str(row.get("name") or row.get("fullName") or ""),
            display_name=str(row.get("displayName") or row.get("listName") or ""),
            firm_type=str(row.get("firmType") or row.get("type") or ""),
            tax_id=normalize_tax_id(tax_id),
            raw=row,
        )


@dataclass
class MatchResult:
    status: str
    score: int
    firm: Optional[FirmCard] = None
    candidates: List[FirmCard] = field(default_factory=list)
    reason: str = ""


@dataclass
class DryRunRow:
    check: CustomerCheckRow
    match: MatchResult
    duplicate: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "invalid"
        if self.duplicate:
            return "duplicate"
        return self.match.status

    def to_record(self) -> Dict[str, Any]:
        firm = self.match.firm
        return {
            "status": self.status,
            "source_row": self.check.source_row,
            "firm_name": self.check.firm_name,
            "tax_id": self.check.tax_id,
            "check_number": self.check.check_number,
            "due_date": self.check.due_date.isoformat(),
            "amount": float(self.check.amount),
            "currency": self.check.currency,
            "bank_name": self.check.bank_name,
            "description": self.check.description,
            "matched_firm_id": firm.id if firm else "",
            "matched_firm_code": firm.code if firm else "",
            "matched_firm_name": firm.name if firm else "",
            "match_score": self.match.score,
            "match_reason": self.match.reason,
            "idempotency_key": self.check.idempotency_key,
            "errors": "; ".join(self.errors),
        }


@dataclass
class DryRunReport:
    rows: List[DryRunRow]
    payment_endpoint: Dict[str, object]

    @property
    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {
            "total": len(self.rows),
            "matched": 0,
            "ambiguous": 0,
            "unmatched": 0,
            "invalid": 0,
            "duplicate": 0,
        }
        for row in self.rows:
            status = row.status
            if status in counts:
                counts[status] += 1
        return counts

    def records(self) -> List[Dict[str, Any]]:
        return [row.to_record() for row in self.rows]


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = text.translate(replacements)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return text.strip()


def normalize_tax_id(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_column_name(value: Any) -> str:
    return normalize_text(value).replace("_", " ")


def format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def parse_decimal(value: Any) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("tutar bos")
    text = str(value).strip()
    if not text:
        raise ValueError("tutar bos")
    text = text.replace("TL", "").replace("TRY", "").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"gecersiz tutar: {value}") from exc


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("vade tarihi bos")
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"gecersiz tarih: {value}")
    return parsed.date()


def canonical_column_map(columns: Iterable[Any]) -> Dict[str, str]:
    normalized_to_original = {normalize_column_name(col): str(col) for col in columns}
    result: Dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            original = normalized_to_original.get(normalize_column_name(alias))
            if original is not None:
                result[canonical] = original
                break
    return result


def read_customer_checks(path: Path, sheet_name: Optional[str] = None) -> List[CustomerCheckRow]:
    """Read Excel/CSV customer check rows into the standard transfer model."""

    path = Path(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path, sheet_name=sheet_name or 0)

    mapping = canonical_column_map(df.columns)
    missing = [field for field_name, field in [(f, f) for f in REQUIRED_CHECK_FIELDS] if field_name not in mapping]
    if missing:
        raise ValueError("Eksik zorunlu kolonlar: " + ", ".join(missing))

    checks: List[CustomerCheckRow] = []
    for idx, row in df.iterrows():
        raw = {str(col): row[col] for col in df.columns}
        source_row = int(idx) + 2  # Header is row 1 in Excel.

        def get(name: str, default: Any = "") -> Any:
            column = mapping.get(name)
            if not column:
                return default
            value = row[column]
            if isinstance(value, float) and pd.isna(value):
                return default
            return value

        parse_errors: List[str] = []
        try:
            due_date = parse_date(get("due_date"))
        except ValueError as exc:
            due_date = date(1900, 1, 1)
            parse_errors.append(str(exc))

        try:
            amount = parse_decimal(get("amount"))
        except ValueError as exc:
            amount = Decimal("0.00")
            parse_errors.append(str(exc))

        checks.append(
            CustomerCheckRow(
                source_row=source_row,
                firm_name=str(get("firm_name")).strip(),
                tax_id=normalize_tax_id(get("tax_id")),
                check_number=str(get("check_number")).strip(),
                due_date=due_date,
                amount=amount,
                currency=str(get("currency", "TL") or "TL").strip() or "TL",
                bank_name=str(get("bank_name", "") or "").strip(),
                description=str(get("description", "") or "").strip(),
                firm_code=str(get("firm_code", "") or "").strip(),
                firm_id=str(get("firm_id", "") or "").strip(),
                parse_errors=parse_errors,
                raw=raw,
            )
        )

    return checks


def validate_check(check: CustomerCheckRow) -> List[str]:
    errors: List[str] = list(check.parse_errors)
    if not check.firm_name:
        errors.append("firma adi bos")
    if not check.tax_id:
        errors.append("vergi/tc no bos")
    if check.tax_id and len(check.tax_id) not in (10, 11):
        errors.append("vergi/tc no 10 veya 11 hane olmali")
    if not check.check_number:
        errors.append("cek no bos")
    if check.amount <= Decimal("0"):
        errors.append("tutar sifirdan buyuk olmali")
    return errors


def match_check_to_firm(check: CustomerCheckRow, firms: Sequence[FirmCard]) -> MatchResult:
    scored: List[tuple[int, FirmCard, List[str]]] = []
    check_tax_id = normalize_tax_id(check.tax_id)
    check_name = normalize_text(check.firm_name)
    check_code = normalize_text(check.firm_code)

    for firm in firms:
        score = 0
        reasons: List[str] = []

        if check.firm_id and check.firm_id == firm.id:
            score += 120
            reasons.append("firm_id")
        if check_code and check_code == normalize_text(firm.code):
            score += 100
            reasons.append("firm_code")
        if check_tax_id and check_tax_id == firm.tax_id:
            score += 90
            reasons.append("tax_id")

        firm_names = [normalize_text(firm.name), normalize_text(firm.display_name)]
        if check_name and check_name in firm_names:
            score += 50
            reasons.append("name_exact")
        elif check_name and any(check_name in name or name in check_name for name in firm_names if name):
            score += 25
            reasons.append("name_partial")

        if score:
            scored.append((score, firm, reasons))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return MatchResult(status="unmatched", score=0, reason="no candidate")

    best_score = scored[0][0]
    best = [item for item in scored if item[0] == best_score]
    if len(best) > 1:
        return MatchResult(
            status="ambiguous",
            score=best_score,
            candidates=[item[1] for item in best],
            reason="multiple candidates with same score",
        )

    score, firm, reasons = scored[0]
    if score < 75:
        return MatchResult(
            status="ambiguous",
            score=score,
            candidates=[item[1] for item in scored[:5]],
            reason="low confidence: " + ",".join(reasons),
        )

    return MatchResult(status="matched", score=score, firm=firm, reason=",".join(reasons))


class PaymentAuditStore:
    """Persistence for import idempotency and result auditing."""

    def __init__(self, database: DatabaseHelper = default_db) -> None:
        self.db = database

    def ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_check_transfer_audit (
                id BIGSERIAL PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                source_file TEXT,
                source_row INTEGER,
                firm_id TEXT,
                firm_name TEXT,
                tax_id TEXT,
                check_number TEXT,
                due_date DATE,
                amount NUMERIC(18,2),
                currency TEXT,
                status TEXT NOT NULL,
                isbasi_record_id TEXT,
                request_payload JSONB DEFAULT '{}'::jsonb,
                response_payload JSONB DEFAULT '{}'::jsonb,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    def existing_keys(self, keys: Iterable[str]) -> set[str]:
        key_list = list(keys)
        if not key_list:
            return set()
        rows = self.db.query(
            "SELECT idempotency_key FROM customer_check_transfer_audit WHERE idempotency_key = ANY(%s)",
            (key_list,),
        )
        return {str(row["idempotency_key"]) for row in rows}

    def record_result(
        self,
        check: CustomerCheckRow,
        status: str,
        source_file: str = "",
        firm: Optional[FirmCard] = None,
        isbasi_record_id: str = "",
        request_payload: Optional[Dict[str, Any]] = None,
        response_payload: Optional[Dict[str, Any]] = None,
        error_message: str = "",
    ) -> None:
        self.ensure_schema()
        self.db.execute(
            """
            INSERT INTO customer_check_transfer_audit (
                idempotency_key, source_file, source_row, firm_id, firm_name, tax_id,
                check_number, due_date, amount, currency, status, isbasi_record_id,
                request_payload, response_payload, error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                status = EXCLUDED.status,
                isbasi_record_id = EXCLUDED.isbasi_record_id,
                request_payload = EXCLUDED.request_payload,
                response_payload = EXCLUDED.response_payload,
                error_message = EXCLUDED.error_message,
                updated_at = NOW()
            """,
            (
                check.idempotency_key,
                source_file,
                check.source_row,
                firm.id if firm else "",
                firm.name if firm else check.firm_name,
                check.tax_id,
                check.check_number,
                check.due_date,
                check.amount,
                check.currency,
                status,
                isbasi_record_id,
                json.dumps(request_payload or {}, ensure_ascii=False),
                json.dumps(response_payload or {}, ensure_ascii=False),
                error_message,
            ),
        )


def build_dry_run(
    checks: Sequence[CustomerCheckRow],
    firms: Sequence[FirmCard],
    existing_keys: Optional[set[str]] = None,
) -> DryRunReport:
    existing_keys = existing_keys or set()
    rows: List[DryRunRow] = []
    seen: set[str] = set()
    for check in checks:
        errors = validate_check(check)
        duplicate = check.idempotency_key in existing_keys or check.idempotency_key in seen
        seen.add(check.idempotency_key)
        match = match_check_to_firm(check, firms) if not errors else MatchResult(status="invalid", score=0)
        rows.append(DryRunRow(check=check, match=match, duplicate=duplicate, errors=errors))
    return DryRunReport(rows=rows, payment_endpoint=payment_endpoint_verification())


def export_dry_run_report(report: DryRunReport, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(report.records())
    if output_path.suffix.lower() == ".csv":
        df.to_csv(output_path, index=False)
    else:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            pd.DataFrame([report.summary]).to_excel(writer, sheet_name="Summary", index=False)
            pd.DataFrame(report.records()).to_excel(writer, sheet_name="Rows", index=False)
            pd.DataFrame([report.payment_endpoint]).to_excel(writer, sheet_name="PaymentEndpoint", index=False)
    return output_path


class IsbasiPaymentWriter:
    """Customer payment writer guard.

    The implementation is intentionally blocked until a real customer
    collection/check endpoint is verified from İşbaşı documentation.
    """

    def __init__(self, client: IsbasiApiClient) -> None:
        self.client = client

    def create_customer_check_payment(self, check: CustomerCheckRow, firm: FirmCard) -> Dict[str, Any]:
        verification = self.client.verify_customer_payment_endpoint()
        if not verification.get("verified"):
            raise IsbasiAPIError(str(verification.get("reason")))
        raise IsbasiAPIError("Customer payment endpoint is marked verified but no writer mapping is implemented.")


def firm_cards_from_api(rows: Sequence[Dict[str, Any]]) -> List[FirmCard]:
    return [FirmCard.from_api(row) for row in rows]


def load_firms_from_json(path: Path) -> List[FirmCard]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(rows, dict) and "data" in rows:
        rows = rows["data"]
    return firm_cards_from_api(rows or [])
