#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yazma Probe: integrationInvoices şemasını 500 hata mesajlarıyla çöz
====================================================================

Read rate limit aşıldığında kullanılır. POST istekleri ayrı limitte.

Her adımda payload'a yeni alan eklenir → 500 mesajı hangi alanın
eksik/hatalı olduğunu söyler → şema adım adım çözülür.

Kullanım:
    python3 scripts/probe_purchase_invoice_write.py --password 125368
    python3 scripts/probe_purchase_invoice_write.py --password 125368 --invoice-id AKG2026000003561
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError

# ── Bilinen fatura verileri (DB'den çekilecek) ───────────────────────────────
FACTORY_VKN = {
    "AKG": "0111275461",
    "FLL": "6100452262",
}

BASE_URL_MW   = "https://mw-jplatform.isbasi.com"
BASE_URL_ISMW = "https://isbasimw.isbasi.com"


def _build_client(base_url: str, password: str = "") -> IsbasiApiClient:
    c = IsbasiApiClient(base_url=base_url)
    c.login(password=password or None)
    return c


def _clone_client(src: IsbasiApiClient, base_url: str) -> IsbasiApiClient:
    """Aynı session token'ını farklı base URL ile kullan."""
    c = IsbasiApiClient(base_url=base_url)
    c.session.headers.update(dict(src.session.headers))
    c.login_state = src.login_state
    return c


def _get_invoice_from_db(invoice_id: str = "") -> Optional[Dict[str, Any]]:
    """DB'den AKG/FLL fatura verisi çek."""
    try:
        from backend.core.db import db
        vkns = list(FACTORY_VKN.values())
        ph = ",".join(["%s"] * len(vkns))
        if invoice_id:
            row = db.query_one(
                f"SELECT invoice_id, uuid, supplier, supplier_tckn_vkn, amount, "
                f"total_vat_base, currency, issue_date, raw_json "
                f"FROM incoming_invoices WHERE invoice_id = %s LIMIT 1",
                (invoice_id,),
            )
        else:
            row = db.query_one(
                f"SELECT invoice_id, uuid, supplier, supplier_tckn_vkn, amount, "
                f"total_vat_base, currency, issue_date, raw_json "
                f"FROM incoming_invoices WHERE supplier_tckn_vkn IN ({ph}) "
                f"ORDER BY issue_date DESC LIMIT 1",
                tuple(vkns),
            )
        if not row:
            return None
        raw = row.get("raw_json") or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        inv = dict(raw)
        inv.setdefault("invoiceId", str(row.get("invoice_id") or ""))
        inv.setdefault("uuId", str(row.get("uuid") or ""))
        inv.setdefault("supplier", str(row.get("supplier") or ""))
        inv.setdefault("supplierTcknVkn", str(row.get("supplier_tckn_vkn") or ""))
        inv.setdefault("amount", float(row.get("amount") or 0))
        inv.setdefault("totalVatBase", float(row.get("total_vat_base") or 0))
        inv.setdefault("currency", str(row.get("currency") or "TRY"))
        inv.setdefault("issueDate", str(row.get("issue_date") or ""))
        return inv
    except Exception as exc:
        print(f"   ⚠️  DB hatası: {exc}")
        return None


def _post_and_report(client: IsbasiApiClient, path: str, payload: Dict[str, Any],
                     label: str, results: List[Dict]) -> str:
    """POST yapar, hata mesajını döner."""
    try:
        resp = client.post(path, payload)
        msg = f"✅ 200 — BAŞARILI! resp={str(resp)[:300]}"
        status = "200"
    except IsbasiAPIError as exc:
        raw = str(exc)
        # İçindeki JSON mesajını çıkar
        try:
            start = raw.find("{")
            if start >= 0:
                body = json.loads(raw[start:])
                msg = body.get("message") or raw[:300]
            else:
                msg = raw[:300]
        except Exception:
            msg = raw[:300]
        status = raw.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in raw else "err"

    icon = "✅" if status == "200" else ("🟡" if status in ("400", "422") else "🔴")
    print(f"\n  {icon} [{status}] {label}")
    print(f"      Mesaj: {msg}")
    results.append({"label": label, "status": status, "message": msg,
                    "payload_keys": list(payload.keys())})
    return status


def run_schema_discovery(client_mw: IsbasiApiClient, client_ismw: IsbasiApiClient,
                          inv: Dict[str, Any]) -> List[Dict]:
    """
    integrationInvoices endpoint'ini artan payload'larla test eder.
    Her adım bir öncekinin üzerine yeni alan ekler.
    """
    results = []
    path = "/api/v1.0/invoices/integrationInvoices"

    inv_id   = str(inv.get("invoiceId") or "")
    uuid     = str(inv.get("uuId") or "")
    vkn      = str(inv.get("supplierTcknVkn") or "")
    supplier = str(inv.get("supplier") or "")
    amount   = inv.get("amount") or 0
    vat_base = inv.get("totalVatBase") or 0
    currency = str(inv.get("currency") or "TRY")
    date_str = str(inv.get("issueDate") or "")[:10]  # YYYY-MM-DD

    print(f"\n{'='*65}")
    print(f"  Fatura: {inv_id}  |  UUID: {uuid[:16]}...")
    print(f"  Tedarikçi: {supplier[:50]}")
    print(f"  Tutar: {amount} {currency}")
    print(f"{'='*65}")

    # ── Adım 1: Minimal — sadece customer ──────────────────────────────────
    p1 = {
        "type": "PURCHASE_INVOICE",
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
    }
    _post_and_report(client_mw, path, p1, "1) type + customer(vkn,name)", results)
    time.sleep(0.4)

    # ── Adım 2: customer'a code denemesi ────────────────────────────────────
    p2 = {
        "type": "PURCHASE_INVOICE",
        "customer": {
            "taxOrPersonalId": vkn,
            "name": supplier,
            "firmVknTckn": vkn,       # alternatif field adı
        },
    }
    _post_and_report(client_mw, path, p2, "2) customer + firmVknTckn", results)
    time.sleep(0.4)

    # ── Adım 3: + invoiceNumber + date ──────────────────────────────────────
    p3 = {
        "type": "PURCHASE_INVOICE",
        "invoiceNumber": inv_id,
        "date": date_str,
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
    }
    _post_and_report(client_mw, path, p3, "3) + invoiceNumber + date", results)
    time.sleep(0.4)

    # ── Adım 4: + eInvoiceUUID ───────────────────────────────────────────────
    p4 = {
        "type": "PURCHASE_INVOICE",
        "invoiceNumber": inv_id,
        "date": date_str,
        "eInvoiceUUID": uuid,
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
    }
    _post_and_report(client_mw, path, p4, "4) + eInvoiceUUID", results)
    time.sleep(0.4)

    # ── Adım 5: + totalAmount + vatBase ─────────────────────────────────────
    p5 = {
        "type": "PURCHASE_INVOICE",
        "invoiceNumber": inv_id,
        "date": date_str,
        "eInvoiceUUID": uuid,
        "totalAmount": amount,
        "taxableAmount": vat_base,
        "currency": currency,
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
    }
    _post_and_report(client_mw, path, p5, "5) + totalAmount + vatBase + currency", results)
    time.sleep(0.4)

    # ── Adım 6: invoiceType=2 yerine numerik tip ─────────────────────────────
    p6 = {
        "type": 2,
        "invoiceNumber": inv_id,
        "date": date_str,
        "eInvoiceUUID": uuid,
        "totalAmount": amount,
        "taxableAmount": vat_base,
        "currency": currency,
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
    }
    _post_and_report(client_mw, path, p6, "6) type=2 (numerik)", results)
    time.sleep(0.4)

    # ── Adım 7: boş invoiceLines array ─────────────────────────────────────
    p7 = {
        "type": "PURCHASE_INVOICE",
        "invoiceNumber": inv_id,
        "date": date_str,
        "eInvoiceUUID": uuid,
        "totalAmount": amount,
        "taxableAmount": vat_base,
        "currency": currency,
        "customer": {"taxOrPersonalId": vkn, "name": supplier},
        "invoiceLines": [],
    }
    _post_and_report(client_mw, path, p7, "7) + boş invoiceLines", results)
    time.sleep(0.4)

    # ── Adım 8: aynı payload isbasimw.isbasi.com'da ─────────────────────────
    _post_and_report(client_ismw, path, p5, "8) isbasimw: adım-5 payload", results)
    time.sleep(0.4)

    # ── Adım 9: isbasimw'da type=2 ─────────────────────────────────────────
    _post_and_report(client_ismw, path, p6, "9) isbasimw: type=2", results)
    time.sleep(0.4)

    # ── Adım 10: tam satır içeren payload ───────────────────────────────────
    # UBL satırlarını DB cache'ten almayı dene
    lines = _get_invoice_lines_from_cache(str(inv.get("uuId") or ""))
    if lines:
        p10 = {
            "type": "PURCHASE_INVOICE",
            "invoiceNumber": inv_id,
            "date": date_str,
            "eInvoiceUUID": uuid,
            "totalAmount": amount,
            "taxableAmount": vat_base,
            "currency": currency,
            "customer": {"taxOrPersonalId": vkn, "name": supplier},
            "invoiceLines": lines,
        }
        _post_and_report(client_mw, path, p10, "10) + UBL satırları (DB'den)", results)
        time.sleep(0.4)
    else:
        print("\n  ⚠️  Adım 10 atlandı: UBL satırları DB'de yok")

    return results


def _get_invoice_lines_from_cache(uuid: str) -> List[Dict[str, Any]]:
    """XML cache'ten UBL satırlarını parse eder."""
    if not uuid:
        return []
    try:
        from backend.core.db import db
        from backend.core.ubl_line_parser import parse_invoice_lines
        row = db.query_one(
            "SELECT xml_content FROM incoming_invoice_xml_cache WHERE uuid = %s LIMIT 1",
            (uuid,),
        )
        if not row or not row.get("xml_content"):
            return []
        parsed = parse_invoice_lines(row["xml_content"])
        # integrationInvoices formatına çevir
        lines = []
        for i, line in enumerate(parsed, 1):
            qty = line.get("Miktar")
            price = line.get("Birim Fiyat")
            vat_rate = line.get("KDV Oranı")
            total = line.get("Satır Tutarı")
            lines.append({
                "lineNumber": i,
                "description": str(line.get("Ürün Adı") or line.get("Açıklama") or ""),
                "quantity": float(qty) if qty else 1,
                "unitPrice": float(price) if price else 0,
                "vatRate": float(vat_rate) if vat_rate else 0,
                "lineTotal": float(total) if total else 0,
                "unit": str(line.get("Birim") or ""),
                "productCode": str(line.get("Ürün Kodu") or ""),
            })
        print(f"   ✅ {len(lines)} UBL satırı parse edildi")
        return lines
    except Exception as exc:
        print(f"   ⚠️  UBL parse hatası: {exc}")
        return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Yazma probe: integrationInvoices şemasını POST'larla çöz"
    )
    parser.add_argument("--password", default="", required=True, help="İşbaşı şifresi")
    parser.add_argument("--invoice-id", default="", help="Belirli fatura ID (opsiyonel)")
    args = parser.parse_args()

    print("=" * 65)
    print("✍️  YAZMA PROBE: integrationInvoices şema keşfi")
    print("   (Read limit aşıldı — sadece POST kullanılır)")
    print("=" * 65)

    # Login
    print("\n🔑 Login...")
    try:
        client_mw = _build_client(BASE_URL_MW, args.password)
        client_ismw = _clone_client(client_mw, BASE_URL_ISMW)
        print(f"   ✅ Login başarılı")
    except Exception as exc:
        print(f"   ❌ Login başarısız: {exc}")
        sys.exit(1)

    # Fatura verisi
    print("\n📋 DB'den fatura çekiliyor...")
    inv = _get_invoice_from_db(args.invoice_id)
    if not inv:
        print("   ❌ DB'de AKG/FLL fatura bulunamadı")
        sys.exit(1)
    print(f"   ✅ Fatura: {inv.get('invoiceId')} ({inv.get('supplier', '')[:40]})")

    # Şema keşfi
    results = run_schema_discovery(client_mw, client_ismw, inv)

    # Özet
    print(f"\n{'='*65}")
    print("📊 ÖZET")
    print(f"{'='*65}")
    for r in results:
        icon = "✅" if r["status"] == "200" else ("🟡" if r["status"] in ("400", "422") else "🔴")
        print(f"  {icon} [{r['status']:>4}] {r['label']}")
        if r.get("message") and r["status"] != "200":
            print(f"          → {r['message'][:100]}")

    # Kaydet
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"purchase_invoice_write_probe_{ts}.json"
    log_path.write_text(
        json.dumps({"invoice": inv.get("invoiceId"), "steps": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n📁 Log: {log_path}")

    # Başarılı adım var mı?
    success = [r for r in results if r["status"] == "200"]
    if success:
        print(f"\n🎉 BAŞARILI endpoint bulundu: {success[0]['label']}")
        print(f"   Payload fields: {success[0]['payload_keys']}")
    else:
        best = [r for r in results if r["status"] in ("400", "422")]
        if best:
            print(f"\n💡 En umut verici: [{best[-1]['status']}] {best[-1]['label']}")
            print(f"   → {best[-1]['message'][:200]}")


if __name__ == "__main__":
    main()
