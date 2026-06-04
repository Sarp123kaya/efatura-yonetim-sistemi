#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for customer ekstre comparison helpers."""

from __future__ import annotations

import unittest
from decimal import Decimal

from backend.core.customer_ekstre_comparison import (
    _build_monthly_rows,
    _check_amount,
    _is_check_row,
    match_musteri_adi_to_firm,
)


class CustomerEkstreComparisonTests(unittest.TestCase):
    def test_is_check_row(self) -> None:
        self.assertTrue(_is_check_row({"fis_turu": "Çek Giriş"}))
        self.assertTrue(_is_check_row({"fis_turu": "CEK GIRIS"}))
        self.assertFalse(_is_check_row({"fis_turu": "Toptan Satış Faturası"}))

    def test_check_amount_prefers_alacak(self) -> None:
        row = {"alacak": "1500.00", "borc": "999.00"}
        self.assertEqual(_check_amount(row), Decimal("1500.00"))

    def test_match_musteri_adi_exact(self) -> None:
        matched, method = match_musteri_adi_to_firm(
            "D KAYA İNŞAAT LTD. ŞTİ.",
            ["D KAYA İNŞAAT LTD. ŞTİ.", "BAŞKA FİRMA"],
        )
        self.assertEqual(matched, ["D KAYA İNŞAAT LTD. ŞTİ."])
        self.assertEqual(method, "exact_name")

    def test_match_musteri_adi_normalized(self) -> None:
        matched, method = match_musteri_adi_to_firm(
            "D KAYA İNŞAAT",
            ["D KAYA İNŞAAT TAAHHÜT TİCARET VE İHRACAT İTHALAT LİMİTED ŞİRKETİ"],
        )
        self.assertTrue(matched)
        self.assertEqual(method, "normalized_name")

    def test_build_monthly_rows(self) -> None:
        invoices = [
            {"issue_date": "2026-01-15", "total_tl": 1000},
            {"issue_date": "2026-02-10", "total_tl": 500},
        ]
        checks = [
            {"tarih": "2026-01-20", "alacak": 800, "fis_turu": "Çek Giriş"},
        ]
        rows = _build_monthly_rows(invoices, checks)
        by_month = {r["month"]: r for r in rows}
        self.assertEqual(by_month["2026-01"]["invoice_total"], Decimal("1000"))
        self.assertEqual(by_month["2026-01"]["check_total"], Decimal("800"))
        self.assertEqual(by_month["2026-01"]["difference"], Decimal("200"))
        self.assertEqual(by_month["2026-02"]["check_count"], 0)


if __name__ == "__main__":
    unittest.main()
