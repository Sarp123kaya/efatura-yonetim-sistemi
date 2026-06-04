#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yazma Probe 3: SalesInvoiceDetails satır yapısını çöz
======================================================
Kalan sorun: "Fatura satırında ürün girilmesi zorunludur."
Her satırda bir product/stok referansı gerekiyor.

Bu probe farklı satır yapılarını dener:
  - product: {id, name, code}
  - stockId / stockRef
  - description tabanlı (stok yerine serbest metin)
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError
from backend.core.db import db
from backend.core.ubl_line_parser import parse_invoice_lines


def login(password: str) -> IsbasiApiClient:
    c = IsbasiApiClient(base_url="https://mw-jplatform.isbasi.com")
    c.login(password=password)
    return c


def get_data():
    row = db.query_one(
        """SELECT invoice_id, uuid, supplier, supplier_tckn_vkn,
                  amount, total_vat_base, currency, issue_date
           FROM incoming_invoices
           WHERE supplier_tckn_vkn IN ('0111275461','6100452262')
           ORDER BY issue_date DESC LIMIT 1"""
    )
    if not row:
        raise SystemExit("DB'de AKG/FLL fatura yok")

    xml_row = db.query_one(
        "SELECT xml_content FROM incoming_invoice_xml_cache WHERE uuid = %s LIMIT 1",
        (str(row["uuid"]),)
    )
    lines = []
    if xml_row and xml_row.get("xml_content"):
        for l in parse_invoice_lines(xml_row["xml_content"]):
            lines.append({
                "name":     str(l.get("Ürün Adı") or l.get("Açıklama") or ""),
                "code":     str(l.get("Ürün Kodu") or ""),
                "qty":      float(l.get("Miktar") or 1),
                "price":    float(l.get("Birim Fiyat") or 0),
                "vat":      float(l.get("KDV Oranı") or 0),
                "total":    float(l.get("Satır Tutarı") or 0),
                "unit":     str(l.get("Birim") or ""),
            })
    return row, lines


def post(client: IsbasiApiClient, label: str, payload: Dict) -> str:
    try:
        resp = client.post("/api/v1.0/invoices/integrationInvoices", payload)
        print(f"\n  ✅ 200 — BAŞARILI! [{label}]")
        print(f"     {str(resp)[:500]}")
        return "200"
    except IsbasiAPIError as exc:
        raw = str(exc)
        try:
            body = json.loads(raw[raw.find("{"):])
            msg  = body.get("message") or raw[:400]
        except Exception:
            msg = raw[:300]
        code = raw.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in raw else "err"
        icon = "🟡" if code in ("400","422") else "🔴"
        errors = [l.strip() for l in msg.split("\n") if l.strip()]
        print(f"\n  {icon} [{code}] {label}")
        for e in errors:
            print(f"         → {e}")
        return code


def base_payload(row, lines_field: str, lines_data: List, date_val: str) -> Dict:
    """Bilinen doğru alanlarla temel payload."""
    return {
        "type":          "PURCHASE_INVOICE",
        "invoiceDate":   date_val,
        "invoiceNumber": str(row["invoice_id"]),
        "eInvoiceUUID":  str(row["uuid"]),
        "totalAmount":   float(row["amount"] or 0),
        "taxableAmount": float(row["total_vat_base"] or 0),
        "currency":      str(row["currency"] or "TRY"),
        "customer": {
            "tcknvkn": str(row["supplier_tckn_vkn"]),
            "name":    str(row["supplier"]),
            "address": "Türkiye",
        },
        lines_field: lines_data,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    print("="*65)
    print("✍️  YAZMA PROBE 3: satır (product) yapısı arayışı")
    print("="*65)

    client = login(args.password)
    print("✅ Login")

    row, ubl_lines = get_data()
    date_val = str(row["issue_date"])[:10]
    print(f"✅ Fatura: {row['invoice_id']} | {len(ubl_lines)} UBL satırı")

    # ── Referans satır: tek satır ile test ──────────────────────────────────
    L = ubl_lines[0] if ubl_lines else {"name":"Test Ürün","code":"TST","qty":1,"price":100,"vat":20,"total":100,"unit":"KG"}

    print("\n── 1) product objesi varyasyonları ────────────────────────────")

    # 1a: product.id=0 ile
    line_1a = {"product": {"id": 0, "name": L["name"], "code": L["code"]},
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_1a], date_val)
    s = post(client, "1a) product:{id:0, name, code}", p); time.sleep(0.3)
    if s == "200": return

    # 1b: product.id=null
    line_1b = {"product": {"id": None, "name": L["name"], "code": L["code"]},
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_1b], date_val)
    s = post(client, "1b) product:{id:null, name, code}", p); time.sleep(0.3)
    if s == "200": return

    # 1c: product sadece name
    line_1c = {"product": {"name": L["name"]},
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_1c], date_val)
    s = post(client, "1c) product:{name only}", p); time.sleep(0.3)
    if s == "200": return

    # 1d: stock objesi
    line_1d = {"stock": {"id": 0, "name": L["name"], "code": L["code"]},
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_1d], date_val)
    s = post(client, "1d) stock:{id:0, name, code}", p); time.sleep(0.3)
    if s == "200": return

    print("\n── 2) stockId / stockRef flat field ───────────────────────────")

    # 2a: stockId=0 ile
    line_2a = {"stockId": 0, "stockName": L["name"], "stockCode": L["code"],
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_2a], date_val)
    s = post(client, "2a) stockId:0, stockName, stockCode", p); time.sleep(0.3)
    if s == "200": return

    # 2b: stockRef=0
    line_2b = {"stockRef": 0, "stockName": L["name"],
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_2b], date_val)
    s = post(client, "2b) stockRef:0, stockName", p); time.sleep(0.3)
    if s == "200": return

    # 2c: stockId=null
    line_2c = {"stockId": None, "stockName": L["name"],
                "amount": L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"]}
    p = base_payload(row, "SalesInvoiceDetails", [line_2c], date_val)
    s = post(client, "2c) stockId:null, stockName", p); time.sleep(0.3)
    if s == "200": return

    print("\n── 3) unit objesi varyasyonu ────────────────────────────────────")

    # 3a: unit objesi + product id=0
    line_3a = {
        "product":   {"id": 0, "name": L["name"], "code": L["code"]},
        "unit":      {"id": 0, "name": L["unit"], "code": L["unit"]},
        "amount":    L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"],
    }
    p = base_payload(row, "SalesInvoiceDetails", [line_3a], date_val)
    s = post(client, "3a) product+unit obje", p); time.sleep(0.3)
    if s == "200": return

    # 3b: stockId=0, unit obje
    line_3b = {
        "stockId": 0, "stockName": L["name"],
        "unit":    {"id": 0, "name": L["unit"], "code": L["unit"]},
        "amount":  L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"],
    }
    p = base_payload(row, "SalesInvoiceDetails", [line_3b], date_val)
    s = post(client, "3b) stockId:0 + unit obje", p); time.sleep(0.3)
    if s == "200": return

    print("\n── 4) description / serbest metin ──────────────────────────────")

    # 4a: sadece description (stoksuz)
    line_4a = {
        "description": L["name"],
        "amount":      L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"],
    }
    p = base_payload(row, "SalesInvoiceDetails", [line_4a], date_val)
    s = post(client, "4a) description only (no product)", p); time.sleep(0.3)
    if s == "200": return

    # 4b: product id=0 + description
    line_4b = {
        "product":     {"id": 0, "name": L["name"]},
        "description": L["name"],
        "amount":      L["qty"], "unitPrice": L["price"], "vatRate": L["vat"], "total": L["total"],
    }
    p = base_payload(row, "SalesInvoiceDetails", [line_4b], date_val)
    s = post(client, "4b) product id=0 + description", p); time.sleep(0.3)
    if s == "200": return

    print("\n── 5) Tam UBL satırları (tüm hataları bir arada görelim) ───────")

    full_lines = []
    for l in ubl_lines:
        full_lines.append({
            "product":   {"id": 0, "name": l["name"], "code": l["code"]},
            "unit":      {"id": 0, "name": l["unit"], "code": l["unit"]},
            "amount":    l["qty"],
            "unitPrice": l["price"],
            "vatRate":   l["vat"],
            "total":     l["total"],
            "description": l["name"],
        })
    p = base_payload(row, "SalesInvoiceDetails", full_lines, date_val)
    post(client, "5) TÜM UBL satırları — product+unit+description", p)


if __name__ == "__main__":
    main()
