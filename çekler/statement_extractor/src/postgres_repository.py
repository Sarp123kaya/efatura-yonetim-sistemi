from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Iterator, Optional

from .models import (
    CheckSourceType,
    ImportResult,
    ImportSession,
    ImportSessionStatus,
    ReviewStatus,
    StoredCheckRecord,
)
from .validators import duplicate_key


class PostgresUnavailableError(RuntimeError):
    pass


class PostgresCheckRepository:
    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise PostgresUnavailableError("DATABASE_URL tanımlı değil.")

    @contextmanager
    def connect(self) -> Iterator[object]:
        try:
            import psycopg
        except ImportError as exc:
            raise PostgresUnavailableError("PostgreSQL için psycopg kurulmalı.") from exc

        with psycopg.connect(self.database_url) as connection:
            yield connection

    def upsert_import_session(self, session: ImportSession) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO check_import_sessions (
                    id, source_type, source_file, status, account_code, account_name, company_name,
                    total_rows, parsed_count, warning_count, error_count, message, created_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    parsed_count = EXCLUDED.parsed_count,
                    warning_count = EXCLUDED.warning_count,
                    error_count = EXCLUDED.error_count,
                    message = EXCLUDED.message,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    session.import_session_id,
                    session.source_type.value,
                    session.source_file,
                    session.status.value,
                    session.statement_metadata.account_code,
                    session.statement_metadata.account_name,
                    session.statement_metadata.company_name,
                    session.total_rows,
                    session.parsed_count,
                    session.warning_count,
                    session.error_count,
                    session.message,
                    session.created_at,
                    session.completed_at,
                ),
            )

    def find_existing_check_id(self, record: StoredCheckRecord) -> Optional[int]:
        customer_name, check_no, bank, maturity_date, amount = duplicate_key(record)
        with self.connect() as connection:
            result = connection.execute(
                """
                SELECT id
                FROM checks
                WHERE COALESCE(account_name, '') = COALESCE(%s, '')
                  AND check_no = %s
                  AND bank_name = %s
                  AND maturity_date = %s
                  AND amount = %s
                LIMIT 1
                """,
                (customer_name, check_no, bank, maturity_date, amount),
            ).fetchone()
        return int(result[0]) if result else None

    def exists(self, record: StoredCheckRecord) -> bool:
        return self.find_existing_check_id(record) is not None

    def insert(self, record: StoredCheckRecord, source_file: Optional[str] = None) -> int:
        with self.connect() as connection:
            result = connection.execute(
                """
                INSERT INTO checks (
                    account_code, account_name, company_name, movement_type, check_no, bank_name,
                    sent_to, amount, currency, maturity_date, transaction_date, document_date, voucher_no,
                    document_no, status, source_file, source_page, raw_description, raw_line,
                    parse_warning, source_type, import_session_id, review_status, source_row_index,
                    source_sheet, source_image_region, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    None,
                    record.customer_name,
                    record.company_name,
                    record.movement_type.value,
                    record.check_no,
                    record.bank,
                    record.sent_to,
                    record.amount,
                    record.currency,
                    record.maturity_date,
                    record.transaction_date,
                    record.document_date,
                    record.voucher_no,
                    record.document_no,
                    "PORTFOLIO",
                    source_file or record.source_file,
                    record.source_page,
                    record.raw_description,
                    record.raw_line,
                    record.parse_warning,
                    record.source_type.value,
                    record.import_session_id,
                    record.review_status.value,
                    record.source_row_index,
                    record.source_sheet,
                    record.source_image_region,
                    record.created_at,
                    datetime.utcnow(),
                ),
            ).fetchone()
        return int(result[0])

    def insert_import_row(
        self,
        record: StoredCheckRecord,
        canonical_check_id: Optional[int] = None,
        duplicate_of_check_id: Optional[int] = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO check_import_rows (
                    import_session_id, canonical_check_id, source_type, source_file, source_sheet,
                    source_row_index, check_no, bank_name, amount, currency, maturity_date,
                    transaction_date, document_date, account_name, company_name, review_status,
                    sent_to, raw_description, raw_line, parse_warning, duplicate_of_check_id, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    record.import_session_id,
                    canonical_check_id,
                    record.source_type.value,
                    record.source_file,
                    record.source_sheet,
                    record.source_row_index,
                    record.check_no,
                    record.bank,
                    record.amount,
                    record.currency,
                    record.maturity_date,
                    record.transaction_date,
                    record.document_date,
                    record.customer_name,
                    record.company_name,
                    record.review_status.value,
                    record.sent_to,
                    record.raw_description,
                    record.raw_line,
                    record.parse_warning,
                    duplicate_of_check_id,
                    record.created_at,
                ),
            )

    def import_result(self, result: ImportResult) -> dict[str, int]:
        inserted = 0
        skipped = 0
        errors = 0
        self.upsert_import_session(result.import_session)
        for record in result.records:
            try:
                existing_check_id = self.find_existing_check_id(record)
                if existing_check_id is not None:
                    self.insert_import_row(record, duplicate_of_check_id=existing_check_id)
                    skipped += 1
                    continue
                inserted_check_id = self.insert(record, source_file=result.import_session.source_file)
                self.insert_import_row(record, canonical_check_id=inserted_check_id)
                inserted += 1
            except Exception:
                errors += 1
        return {
            "inserted_count": inserted,
            "skipped_duplicate_count": skipped,
            "import_row_count": len(result.records),
            "error_count": errors,
        }

    def list_stored_checks(self, approved_only: bool = True) -> list[StoredCheckRecord]:
        query = """
            SELECT
                movement_type, check_no, bank_name, amount, currency, maturity_date, transaction_date,
                document_date, voucher_no, document_no, account_name, company_name, source_file,
                sent_to, source_page, raw_description, raw_line, parse_warning, source_type, import_session_id,
                review_status, source_row_index, source_sheet, source_image_region, created_at
            FROM checks
        """
        params: tuple[object, ...] = ()
        if approved_only:
            query += " WHERE review_status IN ('APPROVED', 'IMPORTED')"
        query += " ORDER BY maturity_date, amount, check_no"

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [row_to_stored_check(row) for row in rows]


def row_to_stored_check(row: tuple[object, ...]) -> StoredCheckRecord:
    return StoredCheckRecord(
        check_no=str(row[1]),
        bank=str(row[2]),
        maturity_date=row[5],
        maturity_month=row[5].strftime("%Y-%m"),
        amount=Decimal(str(row[3])),
        currency=str(row[4] or "TRY"),
        transaction_date=row[6],
        document_date=row[7],
        voucher_no=row[8],
        document_no=row[9],
        customer_name=row[10],
        company_name=row[11],
        source_file=row[12],
        sent_to=row[13],
        source_page=int(row[14] or 0),
        raw_description=str(row[15] or ""),
        raw_line=str(row[16] or ""),
        parse_warning=row[17],
        source_type=CheckSourceType(str(row[18] or "PDF")),
        import_session_id=str(row[19]) if row[19] else None,
        review_status=ReviewStatus(str(row[20] or "APPROVED")),
        source_row_index=row[21],
        source_sheet=row[22],
        source_image_region=row[23],
        created_at=row[24] or datetime.utcnow(),
    )
