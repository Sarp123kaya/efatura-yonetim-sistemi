from __future__ import annotations

from decimal import Decimal

from openpyxl import Workbook

from statement_extractor.src.diff_models import DiffType
from statement_extractor.src.excel_compare import compare_excel_files


HEADERS = [
    "Sıra",
    "Çek No",
    "Banka",
    "Vade Tarihi",
    "Vadeye Kalan Gün",
    "Tutar",
    "Lehtar / Alacaklı",
    "Keşideci / Firma",
    "Açıklama",
    "Doğrulama Durumu",
    "Doğrulama Notu",
]


def write_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "JPEG Çek Taslak"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def base_row(check_no="1001", bank="Garanti BBVA", maturity="20.08.2026", amount=1500000):
    return [
        1,
        check_no,
        bank,
        maturity,
        100,
        amount,
        "MUHAMMET EKREM ÖZKUL",
        "AS MARMARA",
        "Açıklama",
        "UYGUN",
        "Satır doğrulandı.",
    ]


def only_diff_types(report):
    return [row.diff_type for row in report.row_diffs]


def test_same_excel_rows_are_unchanged(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    rows = [base_row()]
    write_workbook(old_path, rows)
    write_workbook(new_path, rows)

    report = compare_excel_files(old_path, new_path)

    assert only_diff_types(report) == [DiffType.UNCHANGED]
    assert report.unchanged_count == 1


def test_amount_change_is_modified(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(amount=1500000)])
    write_workbook(new_path, [base_row(amount=1600000)])

    report = compare_excel_files(old_path, new_path)

    assert report.modified_count == 1
    assert report.row_diffs[0].changes[0].field_name == "Tutar"


def test_bank_change_is_modified(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(bank="Garanti BBVA")])
    write_workbook(new_path, [base_row(bank="Halkbank")])

    report = compare_excel_files(old_path, new_path)

    assert report.modified_count == 1
    assert any(change.field_name == "Banka" for change in report.row_diffs[0].changes)


def test_added_row_is_detected(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(check_no="1001")])
    write_workbook(new_path, [base_row(check_no="1001"), base_row(check_no="1002")])

    report = compare_excel_files(old_path, new_path)

    assert report.added_count == 1
    assert DiffType.ADDED in only_diff_types(report)


def test_removed_row_is_detected(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(check_no="1001"), base_row(check_no="1002")])
    write_workbook(new_path, [base_row(check_no="1001")])

    report = compare_excel_files(old_path, new_path)

    assert report.removed_count == 1
    assert DiffType.REMOVED in only_diff_types(report)


def test_check_no_is_primary_identity(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(check_no="1001", bank="Garanti BBVA")])
    write_workbook(new_path, [base_row(check_no="1001", bank="Halkbank")])

    report = compare_excel_files(old_path, new_path)

    assert report.row_diffs[0].row_identity == "check_no:1001"
    assert report.row_diffs[0].identity_method == "check_no"


def test_bank_maturity_amount_is_fallback_identity_when_check_no_missing(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(check_no="", bank="Halkbank", maturity="30.10.2026", amount=1000000)])
    write_workbook(new_path, [base_row(check_no="", bank="Halkbank", maturity="30.10.2026", amount=1000000)])

    report = compare_excel_files(old_path, new_path)

    assert report.row_diffs[0].identity_method == "bank_maturity_amount"
    assert report.unchanged_count == 1


def test_total_amount_difference_is_calculated(tmp_path) -> None:
    old_path = tmp_path / "old.xlsx"
    new_path = tmp_path / "new.xlsx"
    write_workbook(old_path, [base_row(amount=1000000)])
    write_workbook(new_path, [base_row(amount=1250000)])

    report = compare_excel_files(old_path, new_path)

    assert report.amount_difference == Decimal("250000")
