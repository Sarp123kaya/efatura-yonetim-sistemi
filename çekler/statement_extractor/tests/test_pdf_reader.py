from __future__ import annotations

from statement_extractor.src.models import PdfLine
from statement_extractor.src.pdf_reader import extract_statement_metadata


def test_extracts_metadata_from_muavin_defter_combined_line() -> None:
    metadata = extract_statement_metadata(
        [
            PdfLine(
                page_number=1,
                text="Firma : D KAYA İNŞAAT TAAHHÜT TİC.VE İHR.İTH. LTD.ŞTİ. Sayfa No : 1 / 1",
            ),
            PdfLine(
                page_number=1,
                text="Alt Hesap Kodu : 120.01.095 Alt Hesap Adı : DİVAN RESTORASYON YAPI İNŞ.LTD.ŞTİ.",
            ),
        ]
    )

    assert metadata.company_name == "D KAYA İNŞAAT TAAHHÜT TİC.VE İHR.İTH. LTD.ŞTİ."
    assert metadata.account_code == "120.01.095"
    assert metadata.account_name == "DİVAN RESTORASYON YAPI İNŞ.LTD.ŞTİ."


def test_extracts_metadata_from_cari_hesap_ekstresi_format() -> None:
    metadata = extract_statement_metadata(
        [
            PdfLine(page_number=1, text="( 3) AK GİPS A.Ş. Tarih Aralığı : 01.01.2026 - 31.12.2026"),
            PdfLine(
                page_number=1,
                text="120.20.807 / D KAYA İNŞAAT TAAHHÜT TİCARET VE İHRACAT İTHALAT LİMİTED ŞİRKETİ",
            ),
        ]
    )

    assert metadata.company_name == "AK GİPS A.Ş."
    assert metadata.account_code == "120.20.807"
    assert metadata.account_name == "D KAYA İNŞAAT TAAHHÜT TİCARET VE İHRACAT İTHALAT LİMİTED ŞİRKETİ"
