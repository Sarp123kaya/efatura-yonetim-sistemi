#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yazma Probe 2: 4 bilinen alanı düzelterek integrationInvoices'ı çöz
====================================================================
Öğrenilenler (probe_1):
  - Fatura tarihi zorunludur         → "date" yanlış, farklı field adı dene
  - SalesInvoiceDetails boş olamaz   → invoiceLines değil, SalesInvoiceDetails
  - customer.address boş olamaz      → adres gerekli
  - customer.tcknvkn boş olamaz      → tcknvkn field adı farklı

Kullanım:
    python3 scripts/probe_purchase_invoice_write2.py --password 125368
"""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError
from backend.core.db import db
from backend.core.ubl_line_parser import parse_invoice_lines

BASE_MW = "https://mw-jplatform.isbasi.com"


def login(password: str) -> IsbasiApiClient:
    c = IsbasiApiClient(base_url=BASE_MW)
    c.login(password=password)
    return c


def get_invoice() -> Dict[str, Any]:
    row = db.query_one(
        """SELECT invoice_id, uuid, supplier, supplier_tckn_vkn,
                  amount, total_vat_base, currency, issue_date, raw_json
           FROM incoming_invoices
           WHERE supplier_tckn_vkn IN ('0111275461','6100452262')
           ORDER BY issue_date DESC LIMIT 1"""
    )
    if not row:
        raise SystemExit("DB'de AKG/FLL fatura yok")
    raw = row.get("raw_json") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    inv = dict(raw)
    inv.setdefault("invoiceId",        str(row["invoice_id"] or ""))
    inv.setdefault("uuId",             str(row["uuid"] or ""))
    inv.setdefault("supplier",         str(row["supplier"] or ""))
    inv.setdefault("supplierTcknVkn",  str(row["supplier_tckn_vkn"] or ""))
    inv.setdefault("amount",           float(row["amount"] or 0))
    inv.setdefault("totalVatBase",     float(row["total_vat_base"] or 0))
    inv.setdefault("currency",         str(row["currency"] or "TRY"))
    inv.setdefault("issueDate",        str(row["issue_date"] or ""))
    return inv


def get_lines(uuid: str) -> List[Dict]:
    row = db.query_one(
        "SELECT xml_content FROM incoming_invoice_xml_cache WHERE uuid = %s LIMIT 1",
        (uuid,)
    )
    if not row or not row.get("xml_content"):
        return []
    parsed = parse_invoice_lines(row["xml_content"])
    lines = []
    for i, l in enumerate(parsed, 1):
        qty   = float(l.get("Miktar") or 1)
        price = float(l.get("Birim Fiyat") or 0)
        vat   = float(l.get("KDV Oranı") or 0)
        total = float(l.get("Satır Tutarı") or 0)
        lines.append({
            "lineNumber":  i,
            "stockName":   str(l.get("Ürün Adı") or l.get("Açıklama") or ""),
            "stockCode":   str(l.get("Ürün Kodu") or ""),
            "amount":      qty,
            "unitPrice":   price,
            "vatRate":     vat,
            "total":       total,
            "unit":        {"name": str(l.get("Birim") or ""), "code": str(l.get("Birim") or "")},
        })
    return lines


def try_post(client: IsbasiApiClient, label: str, payload: Dict) -> str:
    path = "/api/v1.0/invoices/integrationInvoices"
    try:
        resp = client.post(path, payload)
        print(f"\n  ✅ 200 — BAŞARILI! [{label}]")
        print(f"     resp: {str(resp)[:400]}")
        return "200"
    except IsbasiAPIError as exc:
        raw = str(exc)
        try:
            body = json.loads(raw[raw.find("{"):])
            msg = body.get("message") or raw[:400]
        except Exception:
            msg = raw[:400]
        code = raw.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in raw else "err"
        icon = "🟡" if code in ("400","422") else "🔴"
        print(f"\n  {icon} [{code}] {label}")
        # Her satırı ayrı bas
        for line in msg.split("\n"):
            line = line.strip()
            if line:
                print(f"         → {line}")
        return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    print("="*65)
    print("✍️  YAZMA PROBE 2: field adı varyasyonları")
    print("="*65)

    client = login(args.password)
    print("✅ Login")

    inv   = get_invoice()
    uuid  = inv["uuId"]
    inv_id = inv["invoiceId"]
    vkn   = inv["supplierTcknVkn"]
    name  = inv["supplier"]
    amt   = inv["amount"]
    vat   = inv["totalVatBase"]
    cur   = inv["currency"]
    # tarih: sadece YYYY-MM-DD
    date_raw = str(inv["issueDate"])[:10]
    # ISO8601 tam format
    date_iso = date_raw + "T00:00:00"

    lines = get_lines(uuid)
    print(f"✅ {len(lines)} UBL satırı")
    print(f"   Fatura: {inv_id}  Tarih: {date_raw}  Tutar: {amt}")

    # ── Base customer varyasyonları ──────────────────────────────────────────
    cust_v1 = {                        # öğrenilmiş field adları
        "tcknvkn":   vkn,
        "name":      name,
        "address":   "Türkiye",        # minimal — field var mı kontrol
    }
    cust_v2 = {
        "tcknvkn":   vkn,
        "name":      name,
        "address":   " ",              # boşluk kabul edilir mi?
    }
    cust_v3 = {                        # her iki field adını birlikte gönder
        "tcknvkn":           vkn,
        "taxOrPersonalId":   vkn,
        "name":              name,
        "address":           "Türkiye",
        "firmName":          name,
    }

    # ── SalesInvoiceDetails varyasyonları ────────────────────────────────────
    # Adı değişik olabilir; her adımda farklı isim deneriz
    details_field_names = [
        "SalesInvoiceDetails",
        "salesInvoiceDetails",
        "invoiceDetails",
        "invoiceLines",
        "PurchaseInvoiceDetails",
        "purchaseInvoiceDetails",
    ]

    # ── Tarih field adı varyasyonları ────────────────────────────────────────
    date_fields = {
        "invoiceDate":    date_raw,
        "billingDate":    date_raw,
        "documentDate":   date_raw,
        "date":           date_raw,    # zaten denediniz — tekrar
        "invoiceDate_iso":date_iso,    # ISO format
        "date_iso":       date_iso,
    }

    print("\n── Tarih field adı arayışı ──────────────────────────────────────")
    base = {
        "type":    "PURCHASE_INVOICE",
        "customer": cust_v1,
        "SalesInvoiceDetails": lines if lines else [{"stockName": "test", "amount": 1, "unitPrice": 1, "vatRate": 0, "total": 1}],
    }
    for fname, fval in date_fields.items():
        p = dict(base)
        p[fname] = fval
        code = try_post(client, f"date field = '{fname}'", p)
        if code == "200":
            break
        time.sleep(0.3)

    print("\n── SalesInvoiceDetails alan adı arayışı ─────────────────────────")
    base2 = {
        "type":         "PURCHASE_INVOICE",
        "invoiceDate":  date_raw,
        "customer":     cust_v1,
    }
    dummy_lines = lines if lines else [{"stockName": "test", "amount": 1, "unitPrice": 1, "vatRate": 0, "total": 1}]
    for fname in details_field_names:
        p = dict(base2)
        p[fname] = dummy_lines
        code = try_post(client, f"lines field = '{fname}'", p)
        if code == "200":
            break
        time.sleep(0.3)

    print("\n── customer.address farklı formatlar ───────────────────────────")
    for clabel, cust in [("v1: address=str", cust_v1),
                          ("v2: address=' '", cust_v2),
                          ("v3: tüm alanlar", cust_v3)]:
        p = {
            "type":                "PURCHASE_INVOICE",
            "invoiceDate":         date_raw,
            "SalesInvoiceDetails": dummy_lines,
            "customer":            cust,
        }
        code = try_post(client, f"customer {clabel}", p)
        if code == "200":
            break
        time.sleep(0.3)

    print("\n── Tam payload — tüm bilinen alanlar ───────────────────────────")
    full = {
        "type":                "PURCHASE_INVOICE",
        "invoiceDate":         date_raw,
        "invoiceNumber":       inv_id,
        "eInvoiceUUID":        uuid,
        "totalAmount":         amt,
        "taxableAmount":       vat,
        "currency":            cur,
        "customer":            cust_v3,
        "SalesInvoiceDetails": lines if lines else dummy_lines,
    }
    try_post(client, "TAM PAYLOAD", full)

    print("\n── Tam payload — salesInvoiceDetails (küçük harf) ─────────────")
    full2 = dict(full)
    del full2["SalesInvoiceDetails"]
    full2["salesInvoiceDetails"] = lines if lines else dummy_lines
    try_post(client, "TAM PAYLOAD salesInvoiceDetails küçük", full2)

    print("\n── Tam payload — invoiceDate ISO ───────────────────────────────")
    full3 = dict(full)
    full3["invoiceDate"] = date_iso
    try_post(client, "TAM PAYLOAD invoiceDate ISO", full3)

    # Log kaydet
    print("\n✅ Tamamlandı")


if __name__ == "__main__":
    main()
