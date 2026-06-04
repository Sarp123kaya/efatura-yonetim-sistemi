#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrika Ekstre Parser
=====================
AK GİPS ve FULLBOARD gibi fabrikalardan gelen cari hesap ekstresi
PDF'lerini satır bazında parse eder.

pdfplumber formatları:
  AK GİPS  : DD.MM.YYYY fis_no fis_turu [aciklama] TUTAR BAKIYE_(A|B)
  FULLBOARD: DD.MM.YYYY fis_no fis_turu [belge]    TUTAR BAKIYE_(A|B) TL TUTAR_(A|B) 0 0

Bakiye değişim yönüne bakarak borç / alacak ayrımı yapılır:
  - Bakiye azaldı  (daha az Alacaklı / daha çok Borçlu) → BORÇ
  - Bakiye arttı   (daha çok Alacaklı / daha az Borçlu) → ALACAK
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional


# ── Sabitler ─────────────────────────────────────────────────────────────────

KNOWN_FIS_TURLERI: list[str] = sorted(
    [
        "Toptan Satış Faturası",
        "Alınan Hizmet Faturası",
        "Verilen Hizmet Faturası",
        "Açılış Fişi",
        "Virman Fişi",
        "Kredi Kartı Fişi",
        "Borç Dekontu",
        "Gelen Havale",
        "Çek Giriş",
    ],
    key=len,
    reverse=True,
)

TR_AMOUNT_RE = re.compile(r"\b(\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,3},\d{2})\b")
BALANCE_RE   = re.compile(r"([\d.]+,\d{2})\s*\((A|B)\)")
DATE_RE      = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})\s+")
# Cari hesap satırı: "120.20.807 / D KAYA..." veya "120.342.03.00001 / D.KAYA..."
ACCOUNT_RE   = re.compile(r"^(\d{3}[\d.]+\d)\s*/\s*(.+?)(?:\s+Risk Limiti.*)?$")


# ── Veri Modeli ───────────────────────────────────────────────────────────────

@dataclass
class StatementRow:
    fabrika: str
    cari_hesap_kodu: str
    musteri_adi: str
    tarih: date
    fis_no: str
    fis_turu: str
    aciklama: str
    borc: Optional[Decimal]
    alacak: Optional[Decimal]
    bakiye: Optional[Decimal]
    bakiye_yon: Optional[str]   # "A" = Alacaklı, "B" = Borçlu
    source_file: str


@dataclass
class ParsedStatement:
    fabrika: str
    source_file: str
    rows: list[StatementRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _parse_tr_amount(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _parse_tr_date(s: str) -> Optional[date]:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _detect_factory(lines: list[str]) -> str:
    head = "\n".join(lines[:30])
    if "AK GİPS" in head:
        return "AK GİPS A.Ş."
    if "FULLBOARD" in head:
        return "FULLBOARD YAPI ELEMANLARI A.Ş."
    return "BİLİNMEYEN"


def _is_skip_line(line: str) -> bool:
    s = line.strip()
    return (
        not s
        or s.startswith("--")
        or s.startswith("Tarih Fiş")
        or s.startswith("Toplam")
        or s.startswith("Tarih Aralığı")
        or s.startswith("( ")
        or "Sayfa" in s
        or "Cari Hesap Ekstresi" in s
        or "Tarih Aralığı" in s
        or s == ":"
        or re.match(r"^\d{2}\.\d{2}\.\d{4}\s*\d*\s*$", s)   # sadece tarih[+sayfa no]
    )


def _is_account_line(line: str) -> bool:
    return bool(ACCOUNT_RE.match(line.strip()))


def _parse_account_line(line: str) -> tuple[str, str]:
    m = ACCOUNT_RE.match(line.strip())
    if not m:
        return "", ""
    code = m.group(1).strip()
    name = re.sub(r"\s+Risk Limiti.*$", "", m.group(2)).strip()
    return code, name


def _signed_bakiye(val: Decimal, yon: str) -> Decimal:
    """
    A = Alacaklı (factory holds credit for customer): pozitif
    B = Borçlu   (customer owes factory):             negatif
    """
    return val if yon == "A" else -val


def _determine_borc_alacak(
    tutar: Optional[Decimal],
    prev_signed: Optional[Decimal],
    curr_bakiye: Optional[Decimal],
    curr_yon: Optional[str],
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Bakiye değişimine göre (borç, alacak) döndürür."""
    if tutar is None:
        return None, None
    if prev_signed is None or curr_bakiye is None or curr_yon is None:
        return tutar, None  # bilinemiyor → varsayılan borç

    curr_signed = _signed_bakiye(curr_bakiye, curr_yon)
    diff = curr_signed - prev_signed
    if diff > Decimal("0.005"):
        return None, tutar   # ALACAK (bakiye arttı = müşteri lehine)
    elif diff < Decimal("-0.005"):
        return tutar, None   # BORÇ (bakiye azaldı = müşterinin borcu arttı)
    else:
        return tutar, None   # değişmedi → virman/nötr → borç kabul


def _parse_transaction_line(
    line: str,
    fabrika: str,
    cari_hesap_kodu: str,
    musteri_adi: str,
    source_file: str,
    prev_signed_bakiye: Optional[Decimal],
) -> Optional[StatementRow]:
    """Tek bir işlem satırını parse eder."""
    date_m = DATE_RE.match(line)
    if not date_m:
        return None
    tarih = _parse_tr_date(date_m.group(0).strip())
    if not tarih:
        return None
    rest = line[date_m.end():]

    # Fiş No (ilk boşluklu token)
    fis_no_m = re.match(r"(\S+)\s+", rest)
    if not fis_no_m:
        return None
    fis_no = fis_no_m.group(1)
    rest = rest[fis_no_m.end():]

    # Fiş Türü (bilinen listeden en uzun eşleşme)
    fis_turu = ""
    for turu in KNOWN_FIS_TURLERI:
        if rest.startswith(turu):
            fis_turu = turu
            rest = rest[len(turu):].strip()
            break
    if not fis_turu:
        # İlk sayıya kadar olan metni fiş türü yap
        am = TR_AMOUNT_RE.search(rest)
        fis_turu = rest[: am.start()].strip() if am else rest.strip() or "Diğer"
        rest = rest[am.start():] if am else ""

    # Bakiye = satırdaki ilk "miktar (A|B)" eşleşmesi
    balance_m = BALANCE_RE.search(rest)
    bakiye: Optional[Decimal] = None
    bakiye_yon: Optional[str] = None
    if balance_m:
        bakiye    = _parse_tr_amount(balance_m.group(1))
        bakiye_yon = balance_m.group(2)

    # Açıklama = fis_turu'ndan sonra, ilk rakama kadar olan metin
    first_amount_m = TR_AMOUNT_RE.search(rest)
    aciklama = rest[: first_amount_m.start()].strip() if first_amount_m else ""

    # Ana tutar = ilk Turkish amount (bakiyeden önce)
    tutar: Optional[Decimal] = None
    if first_amount_m:
        first_amount_str = first_amount_m.group(1)
        first_pos = first_amount_m.start()
        # Bakiye'nin pozisyonu
        if balance_m and first_pos < balance_m.start():
            tutar = _parse_tr_amount(first_amount_str)
        elif balance_m is None:
            tutar = _parse_tr_amount(first_amount_str)

    # Borç / Alacak tespiti
    borc, alacak = _determine_borc_alacak(tutar, prev_signed_bakiye, bakiye, bakiye_yon)

    return StatementRow(
        fabrika=fabrika,
        cari_hesap_kodu=cari_hesap_kodu,
        musteri_adi=musteri_adi,
        tarih=tarih,
        fis_no=fis_no,
        fis_turu=fis_turu,
        aciklama=aciklama,
        borc=borc,
        alacak=alacak,
        bakiye=bakiye,
        bakiye_yon=bakiye_yon,
        source_file=source_file,
    )


# ── Ana parse fonksiyonu ──────────────────────────────────────────────────────

def parse_factory_statement_pdf(pdf_path: str | Path) -> ParsedStatement:
    """
    PDF'i okuyup tüm işlem satırlarını parse eder.
    Birden fazla cari hesap içeren PDF'leri destekler.
    """
    path = Path(pdf_path)

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber kurulu değil: pip install pdfplumber") from exc

    with pdfplumber.open(str(path)) as pdf:
        raw_lines: list[str] = []
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            raw_lines.extend(text.splitlines())

    fabrika = _detect_factory(raw_lines)
    result  = ParsedStatement(fabrika=fabrika, source_file=path.name)

    current_account_code = ""
    current_customer     = ""
    # Her cari hesap için ayrı bakiye takibi (hesap kodu → signed bakiye)
    prev_signed: dict[str, Optional[Decimal]] = {}

    for line in raw_lines:
        stripped = line.strip()
        if _is_skip_line(stripped):
            continue

        if _is_account_line(stripped):
            current_account_code, current_customer = _parse_account_line(stripped)
            # Yeni hesap → önceki bakiyeyi sıfırla
            if current_account_code not in prev_signed:
                prev_signed[current_account_code] = None
            continue

        if not DATE_RE.match(stripped):
            continue

        row = _parse_transaction_line(
            stripped,
            fabrika=fabrika,
            cari_hesap_kodu=current_account_code,
            musteri_adi=current_customer,
            source_file=path.name,
            prev_signed_bakiye=prev_signed.get(current_account_code),
        )
        if row:
            # Bakiyeyi güncelle
            if row.bakiye is not None and row.bakiye_yon is not None:
                prev_signed[current_account_code] = _signed_bakiye(row.bakiye, row.bakiye_yon)
            result.rows.append(row)
        else:
            result.warnings.append(f"Parse edilemedi: {stripped[:80]}")

    return result
