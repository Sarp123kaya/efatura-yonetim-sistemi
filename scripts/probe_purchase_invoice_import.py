#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Probe: AKG/FLL e-fatura → İşbaşı alış faturası oluşturma endpoint keşfi
==========================================================================

Bu script READ-ONLY bir keşif aracıdır. Hiçbir fatura oluşturmaz.

Yapılanlar:
1. myInvoicesList'ten AKG/FLL e-faturalarını çeker
2. Her fatura için GET endpoint adaylarını dener
3. POST endpoint adaylarının varlığını kontrol eder (oluşturma yapmadan)
4. Sonuçları data/logs/ altına JSON olarak yazar

Kullanım:
    python scripts/probe_purchase_invoice_import.py
    python scripts/probe_purchase_invoice_import.py --invoice-id AKG2026000003719
    python scripts/probe_purchase_invoice_import.py --limit 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import config
from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError

# ── Base URL'ler — ikisi de denenir ─────────────────────────────────────────
# mw-jplatform: integrationInvoices, myInvoicesList vs.
# isbasimw:     dispatch/mydispatchlist, bazı e-invoice action'ları
ALT_BASE_URL = "https://isbasimw.isbasi.com"

# ── Fabrika tanımları ────────────────────────────────────────────────────────
FACTORY_VKN: Dict[str, str] = {
    "AKG": "0111275461",   # AK GİPS YAPI KİMYASALLARI
    "FLL": "6100452262",   # FULLBOARD YAPI ELEMANLARI
}
FACTORY_VKN_SET = set(FACTORY_VKN.values())
FACTORY_SUPPLIER_KEYWORDS = ("ak g\u0130ps", "fullboard", "akgips")

# ── Endpoint adayları (GET - okuma) ──────────────────────────────────────────
# Parametre: {id} = İşbaşı numeric ID, {uuid} = e-fatura UUID
GET_CANDIDATES: List[Tuple[str, str]] = [
    ("einvoices_by_id",          "/api/v1.0/einvoices/{id}"),
    ("einvoices_detail_by_id",   "/api/v1.0/einvoices/{id}/detail"),
    ("einvoices_by_uuid",        "/api/v1.0/einvoices/{uuid}"),
    ("invoices_by_id",           "/api/v1.0/invoices/{id}"),
    ("invoices_purchase_by_id",  "/api/v1.0/invoices/{id}/purchase"),
    ("invoices_gider_by_id",     "/api/v1.0/invoices/{id}/gider"),
    ("purchase_by_id",           "/api/v1.0/purchases/{id}"),
    ("purchase_detail_by_id",    "/api/v1.0/purchases/{id}/detail"),
]

# ── POST endpoint adayları — mw-jplatform üzerinde ──────────────────────────
POST_CHECK_CANDIDATES: List[Tuple[str, str]] = [
    # integrationInvoices 500 döndürdü → type=2 (PURCHASE) ile dene
    ("integration_invoices_type2",        "/api/v1.0/invoices/integrationInvoices"),
    ("integration_purchase",              "/api/v1.0/invoices/integrationPurchaseInvoice"),
    ("integration_purchases",             "/api/v1.0/invoices/integrationPurchaseInvoices"),
    ("einvoices_create_purchase",         "/api/v1.0/einvoices/createPurchaseInvoice"),
    ("einvoices_import_purchase",         "/api/v1.0/einvoices/integrationPurchaseInvoice"),
    ("purchases_integration",             "/api/v1.0/purchases/integrationPurchases"),
    ("purchases_from_einvoice",           "/api/v1.0/purchases/fromEInvoice"),
    ("purchases_create",                  "/api/v1.0/purchases"),
    ("einvoices_accept_import",           "/api/v1.0/einvoices/acceptAndImport"),
    ("einvoices_accept",                  "/api/v1.0/einvoices/accept"),
    ("einvoices_id_purchase",             "/api/v1.0/einvoices/{id}/createPurchase"),
    ("einvoices_id_import",               "/api/v1.0/einvoices/{id}/import"),
    ("einvoices_id_accept",               "/api/v1.0/einvoices/{id}/accept"),
    # Ekranda görülen "InvoiceTypeForEnvo..." → muhtemel endpoint adları
    ("invoice_type_for_einvoice_get",     "/api/v1.0/invoices/InvoiceTypeForEInvoice"),
    ("einvoice_to_purchase",              "/api/v1.0/einvoices/toPurchaseInvoice"),
    ("einvoice_convert",                  "/api/v1.0/einvoices/convertToPurchase"),
]

# ── POST adayları — isbasimw.isbasi.com base URL üzerinde ───────────────────
ALT_POST_CANDIDATES: List[Tuple[str, str]] = [
    ("alt_integration_invoices",          "/api/v1.0/invoices/integrationInvoices"),
    ("alt_einvoices_create_purchase",     "/api/v1.0/einvoices/createPurchaseInvoice"),
    ("alt_einvoices_import",              "/api/v1.0/einvoices/integrationPurchaseInvoice"),
    ("alt_purchases_integration",         "/api/v1.0/purchases/integrationPurchases"),
    ("alt_einvoices_accept",              "/api/v1.0/einvoices/accept"),
    ("alt_einvoice_to_purchase",          "/api/v1.0/einvoices/toPurchaseInvoice"),
    ("alt_invoices_purchase",             "/api/v1.0/invoices/purchase"),
    ("alt_invoice_type_for_einvoice",     "/api/v1.0/invoices/InvoiceTypeForEInvoice"),
    ("alt_gider_integration",             "/api/v1.0/gider/integrationGider"),
    ("alt_gider_from_einvoice",           "/api/v1.0/gider/fromEInvoice"),
    ("alt_einvoice_id_purchase",          "/api/v1.0/einvoices/{id}/purchase"),
    ("alt_einvoice_id_create_purchase",   "/api/v1.0/einvoices/{id}/createPurchaseInvoice"),
    ("alt_einvoice_uuid_purchase",        "/api/v1.0/einvoices/{uuid}/createPurchase"),
]

# ── GET adayları — isbasimw.isbasi.com üzerinde ──────────────────────────────
ALT_GET_CANDIDATES: List[Tuple[str, str]] = [
    ("alt_einvoices_by_uuid",        "/api/v1.0/einvoices/{uuid}"),
    ("alt_einvoices_detail_uuid",    "/api/v1.0/einvoices/{uuid}/detail"),
    ("alt_invoices_by_id",           "/api/v1.0/invoices/{id}"),
    ("alt_invoice_type_einvoice",    "/api/v1.0/invoices/InvoiceTypeForEInvoice"),
    # Parametre varyantları — 429 geldi (endpoint var!), doğru param bulmak için:
    ("alt_invoice_type_?uuid",       "/api/v1.0/invoices/InvoiceTypeForEInvoice?uuid={uuid}"),
    ("alt_invoice_type_?invoiceId",  "/api/v1.0/invoices/InvoiceTypeForEInvoice?invoiceId={invoice_id}"),
    ("alt_invoice_type_/{uuid}",     "/api/v1.0/invoices/InvoiceTypeForEInvoice/{uuid}"),
]


def _build_client(password: str = "") -> IsbasiApiClient:
    client = IsbasiApiClient()
    client.login(password=password or None)
    return client


def _fetch_factory_invoices_from_db(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Rate limit sorununu önlemek için API yerine veritabanından AKG/FLL faturalarını çeker.
    incoming_invoices tablosundaki raw_json + uuid kullanılır.
    """
    print("\n📥 AKG/FLL gelen faturalar veritabanından çekiliyor (rate limit yok)...")
    try:
        from backend.core.db import db
        vkn_list = list(FACTORY_VKN_SET)
        placeholders = ",".join(["%s"] * len(vkn_list))
        rows = db.query(
            f"""
            SELECT i.invoice_id, i.uuid, i.supplier, i.supplier_tckn_vkn,
                   i.amount, i.total_vat_base, i.currency, i.issue_date,
                   i.raw_json
            FROM incoming_invoices i
            WHERE i.supplier_tckn_vkn IN ({placeholders})
            ORDER BY i.issue_date DESC
            LIMIT %s
            """,
            tuple(vkn_list) + (limit,),
        )
        result = []
        for row in rows:
            raw = row.get("raw_json") or {}
            if isinstance(raw, str):
                import json as _json
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            # Probe için gereken alanları normalize et
            invoice = dict(raw)
            invoice["invoiceId"] = invoice.get("invoiceId") or str(row.get("invoice_id") or "")
            invoice["uuId"] = invoice.get("uuId") or str(row.get("uuid") or "")
            invoice["supplier"] = invoice.get("supplier") or str(row.get("supplier") or "")
            invoice["supplierTcknVkn"] = invoice.get("supplierTcknVkn") or str(row.get("supplier_tckn_vkn") or "")
            invoice["amount"] = invoice.get("amount") or float(row.get("amount") or 0)
            # id alanı: İşbaşı numeric ID (raw_json'da varsa)
            if not invoice.get("id"):
                invoice["id"] = raw.get("id") or ""
            result.append(invoice)
        print(f"   ✅ {len(result)} AKG/FLL fatura bulundu (veritabanından)")
        return result
    except Exception as exc:
        print(f"   ❌ Veritabanı hatası: {exc}")
        print("   ⚠️  DB erişimi yoksa API'den deneniyor...")
        return []


def _fetch_factory_invoices_from_api(client: IsbasiApiClient, limit: int = 5) -> List[Dict[str, Any]]:
    """myInvoicesList'ten AKG/FLL faturalarını çeker (rate limit varsa hata verir)."""
    print("\n📥 AKG/FLL gelen faturalar API'den çekiliyor...")
    payload = {
        "filters": [
            {"columnName": "issueDate", "operator": 5, "value": "2026-01-01T00:00:00"},
            {"columnName": "issueDate", "operator": 2, "value": "2026-12-31T23:59:59"},
        ],
        "sorting": {"issueDate": -1},
        "paging": {"currentPage": 1, "pageSize": 200},
        "count": True,
        "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
    }
    try:
        resp = client.post("/api/v1.0/einvoices/myInvoicesList", payload)
    except IsbasiAPIError as exc:
        print(f"   ❌ myInvoicesList hatası: {exc}")
        return []

    data = resp.get("data") or {}
    rows = data.get("data") if isinstance(data, dict) else []
    rows = rows or []

    factory_rows = []
    for row in rows:
        vkn = str(row.get("supplierTcknVkn") or "").strip()
        if vkn in FACTORY_VKN_SET:
            factory_rows.append(row)
            if len(factory_rows) >= limit:
                break

    print(f"   ✅ {len(factory_rows)} AKG/FLL fatura bulundu (toplam {len(rows)} gelen fatura)")
    return factory_rows


def _fetch_factory_invoices(client: IsbasiApiClient, limit: int = 5) -> List[Dict[str, Any]]:
    """DB'den çeker, olmadığında API'ye döner."""
    rows = _fetch_factory_invoices_from_db(limit)
    if not rows:
        rows = _fetch_factory_invoices_from_api(client, limit)
    return rows


def _probe_get(client: IsbasiApiClient, label: str, path: str) -> Dict[str, Any]:
    """Tek bir GET endpoint'ini dener, özet döner."""
    try:
        resp = client.get(path)
        data = resp.get("data")
        keys = list(resp.keys()) if isinstance(resp, dict) else []
        has_purchase_id = "purchaseInvoiceId" in json.dumps(resp)
        has_invoice_lines = any(k in json.dumps(resp) for k in ("invoiceLines", "lineItems", "lines"))
        return {
            "label": label,
            "path": path,
            "status": "200",
            "top_keys": keys,
            "has_purchase_id": has_purchase_id,
            "has_invoice_lines": has_invoice_lines,
            "data_type": type(data).__name__,
            "data_summary": str(resp)[:300],
        }
    except IsbasiAPIError as exc:
        msg = str(exc)
        code = msg.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in msg else "err"
        return {
            "label": label,
            "path": path,
            "status": code,
            "error": msg[:200],
        }
    except Exception as exc:
        return {
            "label": label,
            "path": path,
            "status": "exception",
            "error": str(exc)[:200],
        }


def _probe_post_check(client: IsbasiApiClient, label: str, path: str,
                      invoice_id: str = "", uuid: str = "") -> Dict[str, Any]:
    """
    POST endpoint varlığını MINIMAL payload ile kontrol eder.
    400/422 → endpoint var ama payload eksik (iyi işaret!)
    404/405 → endpoint yok
    200     → beklenmedik, tam yanıt kaydedilir
    """
    minimal_payloads = [
        {},
        {"id": invoice_id} if invoice_id else {},
        {"uuid": uuid} if uuid else {},
        {"invoiceId": invoice_id, "uuid": uuid},
    ]
    for payload in minimal_payloads:
        if not payload:
            continue
        try:
            resp = client.post(path, payload)
            return {
                "label": label,
                "path": path,
                "status": "200",
                "note": "200 döndü — endpoint mevcut ve çalışıyor olabilir!",
                "response_summary": str(resp)[:400],
            }
        except IsbasiAPIError as exc:
            msg = str(exc)
            code = msg.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in msg else "err"
            if code in ("400", "422"):
                return {
                    "label": label,
                    "path": path,
                    "status": code,
                    "note": "400/422 → endpoint VAR, payload şeması farklı",
                    "error_detail": msg[:300],
                }
            if code in ("404", "405"):
                return {
                    "label": label,
                    "path": path,
                    "status": code,
                    "note": "404/405 → endpoint YOK veya bu method desteklenmiyor",
                    "error_detail": msg[:200],
                }
            return {
                "label": label,
                "path": path,
                "status": code,
                "note": f"HTTP {code}",
                "error_detail": msg[:200],
            }
        except Exception as exc:
            pass

    return {"label": label, "path": path, "status": "skipped", "note": "Tüm payloadlar atlandı"}


def _fetch_numeric_id(client: IsbasiApiClient, invoice_id: str, uuid: str) -> str:
    """
    myInvoicesList'ten tek fatura için İşbaşı numeric ID'sini çeker.
    Rate limit riskini azaltmak için sadece 1 kayıt istenir.
    """
    try:
        resp = client.post("/api/v1.0/einvoices/myInvoicesList", {
            "filters": [{"columnName": "invoiceId", "operator": "IsEqualTo", "value": invoice_id}],
            "sorting": {"issueDate": -1},
            "paging": {"currentPage": 1, "pageSize": 5},
            "count": False,
            "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
        })
        data = resp.get("data") or {}
        rows = data.get("data") if isinstance(data, dict) else []
        rows = rows or []
        for row in rows:
            if str(row.get("uuId") or "").upper() == uuid.upper() or \
               str(row.get("invoiceId") or "") == invoice_id:
                return str(row.get("id") or "")
    except IsbasiAPIError as exc:
        if "429" in str(exc):
            print(f"   ⚠️  Rate limit — numeric ID alınamadı, UUID ile devam ediliyor")
        else:
            print(f"   ⚠️  Numeric ID alınamadı: {exc}")
    return ""


def probe_invoice(client: IsbasiApiClient, invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Tek bir fatura için tüm endpoint adaylarını probelar."""
    inv_id = str(invoice.get("invoiceId") or invoice.get("id") or "")
    numeric_id = str(invoice.get("id") or "")
    uuid = str(invoice.get("uuId") or invoice.get("uuid") or "")
    supplier = str(invoice.get("supplier") or "")
    vkn = str(invoice.get("supplierTcknVkn") or "")
    status_code = invoice.get("statusCode")
    status = str(invoice.get("status") or "")
    purchase_invoice_id = invoice.get("purchaseInvoiceId")

    # Numeric ID eksikse API'den almayı dene
    if not numeric_id:
        print("   🔍 Numeric ID DB'de yok, API'den çekiliyor...")
        numeric_id = _fetch_numeric_id(client, inv_id, uuid)
        if numeric_id:
            print(f"   ✅ Numeric ID bulundu: {numeric_id}")
        else:
            print(f"   ⚠️  Numeric ID bulunamadı — ID parametresi boş kalacak")

    print(f"\n{'='*60}")
    print(f"📄 Fatura: {inv_id}")
    print(f"   Tedarikçi: {supplier} (VKN: {vkn})")
    print(f"   Numeric ID: {numeric_id}  |  UUID: {uuid[:16]}...")
    print(f"   Status: {status} (code={status_code})")
    print(f"   purchaseInvoiceId: {purchase_invoice_id}")
    print(f"{'='*60}")

    results: Dict[str, Any] = {
        "invoice_id": inv_id,
        "numeric_id": numeric_id,
        "uuid": uuid,
        "supplier": supplier,
        "supplier_vkn": vkn,
        "status": status,
        "status_code": status_code,
        "purchase_invoice_id": purchase_invoice_id,
        "get_probes": [],
        "post_check_probes": [],
        "alt_get_probes": [],
        "alt_post_check_probes": [],
    }

    # ── GET probes (mw-jplatform) ────────────────────────────────────────────
    print("\n🔍 GET endpoint adayları (mw-jplatform)...")
    for label, template in GET_CANDIDATES:
        path = template.replace("{id}", numeric_id).replace("{uuid}", uuid).replace("{invoice_id}", inv_id)
        result = _probe_get(client, label, path)
        results["get_probes"].append(result)
        icon = "✅" if result["status"] == "200" else "  "
        print(f"   {icon} [{result['status']:>4}] {label:<40} {path}")
        if result.get("has_purchase_id"):
            print(f"         ↳ purchaseInvoiceId alanı içeriyor!")
        time.sleep(0.15)

    # ── POST check probes (mw-jplatform) ────────────────────────────────────
    print("\n🔍 POST adayları (mw-jplatform) — minimal payload...")
    # integrationInvoices için type=PURCHASE_INVOICE payload'ı ayrıca dene
    _probe_integration_invoices_typed(client, inv_id, uuid, numeric_id, results["post_check_probes"])

    for label, template in POST_CHECK_CANDIDATES[1:]:  # ilki ayrıca işlendi
        path = template.replace("{id}", numeric_id).replace("{uuid}", uuid)
        result = _probe_post_check(client, label, path, inv_id, uuid)
        results["post_check_probes"].append(result)
        icon = "🟢" if result["status"] in ("200", "400", "422", "500") else "  "
        note = result.get("note", "")
        print(f"   {icon} [{result['status']:>4}] {label:<45} {note}")
        time.sleep(0.15)

    # ── isbasimw.isbasi.com üzerinde de dene ─────────────────────────────────
    print(f"\n🔍 isbasimw.isbasi.com üzerinde GET adayları...")
    alt_client = IsbasiApiClient(base_url=ALT_BASE_URL)
    # Aynı token'ı kopyala
    if client.login_state:
        alt_client.session.headers.update({"Authorization": f"Bearer {client.login_state.access_token}"})
        if client.login_state.user_id:
            alt_client.session.headers.update({"UserId": str(client.login_state.user_id)})
        if client.login_state.user_email:
            alt_client.session.headers.update({"UserEmail": str(client.login_state.user_email)})
        if client.login_state.tenant_id:
            alt_client.session.headers.update({"tenantId": str(client.login_state.tenant_id)})
        if client.login_state.user_name:
            alt_client.session.headers.update({"UserName": str(client.login_state.user_name)})
        alt_client.login_state = client.login_state  # token işaretlenmesi için

    for label, template in ALT_GET_CANDIDATES:
        path = template.replace("{id}", numeric_id).replace("{uuid}", uuid).replace("{invoice_id}", inv_id)
        result = _probe_get(alt_client, label, path)
        results["alt_get_probes"].append(result)
        icon = "✅" if result["status"] == "200" else "  "
        print(f"   {icon} [{result['status']:>4}] {label:<45} {path}")
        time.sleep(0.15)

    print(f"\n🔍 isbasimw.isbasi.com üzerinde POST adayları...")
    for label, template in ALT_POST_CANDIDATES:
        path = template.replace("{id}", numeric_id).replace("{uuid}", uuid).replace("{invoice_id}", inv_id)
        result = _probe_post_check(alt_client, label, path, inv_id, uuid)
        results["alt_post_check_probes"].append(result)
        icon = "🟢" if result["status"] in ("200", "400", "422", "500") else "  "
        note = result.get("note", "")
        print(f"   {icon} [{result['status']:>4}] {label:<47} {note}")
        time.sleep(0.15)

    return results


def _probe_integration_invoices_typed(
    client: IsbasiApiClient,
    inv_id: str,
    uuid: str,
    numeric_id: str,
    results_list: List[Dict[str, Any]],
) -> None:
    """
    integrationInvoices endpoint'ini type=PURCHASE_INVOICE payload'ıyla dener.
    500 döndürmüştü — şimdi daha detaylı payload ile ne döneceğini görelim.
    """
    # Probe bulgusu: "IntegrationCustomerModelIsRequired"
    # customer modeli ekliyoruz — daha anlamlı hata mesajı bekliyoruz
    minimal_customer = {
        "taxOrPersonalId": "0111275461",   # AK GİPS VKN
        "name": "AK GİPS YAPI KİMYASALLARI İNŞ. ENERJİ ÜR A.Ş.",
    }
    payloads = [
        {"type": "PURCHASE_INVOICE", "invoiceId": inv_id, "uuid": uuid, "eInvoiceUUID": uuid, "customer": minimal_customer},
        {"type": 2, "invoiceId": inv_id, "uuid": uuid, "eInvoiceUUID": uuid, "customer": minimal_customer},
        {"invoiceType": "PURCHASE_INVOICE", "invoiceNumber": inv_id, "eInvoiceUUID": uuid, "customer": minimal_customer},
        # Sade — sadece customer ve UUID
        {"eInvoiceUUID": uuid, "customer": minimal_customer, "type": "PURCHASE_INVOICE"},
    ]
    path = "/api/v1.0/invoices/integrationInvoices"
    best: Dict[str, Any] = {}
    for payload in payloads:
        try:
            resp = client.post(path, payload)
            best = {
                "label": "integration_invoices_type2",
                "path": path,
                "status": "200",
                "note": f"200 döndü! payload={payload}",
                "response_summary": str(resp)[:400],
            }
            break
        except IsbasiAPIError as exc:
            msg = str(exc)
            code = msg.split("HTTP ")[-1].split(":")[0].strip() if "HTTP" in msg else "err"
            if not best or code in ("400", "422"):
                best = {
                    "label": "integration_invoices_type2",
                    "path": path,
                    "status": code,
                    "note": f"payload={list(payload.keys())} → {code}",
                    "error_detail": msg[:300],
                }
        time.sleep(0.1)

    icon = "🟢" if best.get("status") in ("200", "400", "422") else "  "
    print(f"   {icon} [{best.get('status','?'):>4}] integration_invoices_type2              {best.get('note','')}")
    results_list.append(best)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AKG/FLL e-fatura → alış faturası endpoint keşfi (READ-ONLY)"
    )
    parser.add_argument("--invoice-id", default="", help="Belirli bir fatura ID'si (opsiyonel)")
    parser.add_argument("--limit", type=int, default=2, help="Kaç fatura probe edilsin (default: 2)")
    parser.add_argument("--password", default="", help="İşbaşı şifresi (opsiyonel, yoksa prompt çıkar)")
    args = parser.parse_args()

    print("=" * 70)
    print("🔬 PROBE: AKG/FLL E-Fatura → Alış Faturası Endpoint Keşfi")
    print("   (READ-ONLY — hiçbir fatura oluşturulmaz)")
    print("=" * 70)

    # Login
    print("\n🔑 İşbaşı'ya bağlanılıyor...")
    try:
        client = _build_client(password=args.password)
        print("   ✅ Login başarılı")
    except Exception as exc:
        print(f"   ❌ Login başarısız: {exc}")
        sys.exit(1)

    # Fatura(lar) al
    invoices: List[Dict[str, Any]] = []
    if args.invoice_id:
        # Belirli bir fatura arama
        try:
            resp = client.post("/api/v1.0/einvoices/myInvoicesList", {
                "filters": [{"columnName": "invoiceId", "operator": "IsEqualTo", "value": args.invoice_id}],
                "sorting": {"issueDate": -1},
                "paging": {"currentPage": 1, "pageSize": 10},
                "count": True,
                "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
            })
            data = resp.get("data") or {}
            rows = data.get("data") if isinstance(data, dict) else []
            invoices = rows or []
            if not invoices:
                print(f"   ⚠️  Fatura bulunamadı: {args.invoice_id}, tüm AKG/FLL faturalarına geçiliyor")
                invoices = _fetch_factory_invoices(client, limit=args.limit)
        except Exception:
            invoices = _fetch_factory_invoices(client, limit=args.limit)
    else:
        invoices = _fetch_factory_invoices(client, limit=args.limit)

    if not invoices:
        print("❌ Probe edilecek fatura bulunamadı.")
        sys.exit(1)

    # Her fatura için probe
    all_results = []
    for invoice in invoices:
        result = probe_invoice(client, invoice)
        all_results.append(result)

    # Sonuçları kaydet
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"purchase_invoice_import_probe_{ts}.json"
    log_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Özet
    print(f"\n{'='*70}")
    print("📊 ÖZET")
    print(f"{'='*70}")
    for r in all_results:
        print(f"\n  Fatura: {r['invoice_id']} ({r['supplier'][:30]})")
        print(f"  Status: {r['status']} (code={r['status_code']}), purchaseInvoiceId={r['purchase_invoice_id']}")

        good_get = [p for p in r["get_probes"] if p["status"] == "200"]
        if good_get:
            print(f"  ✅ GET 200 döndüren endpoint'ler:")
            for p in good_get:
                has_pi = " [purchaseInvoiceId✓]" if p.get("has_purchase_id") else ""
                has_lines = " [lines✓]" if p.get("has_invoice_lines") else ""
                print(f"     GET {p['path']}{has_pi}{has_lines}")

        likely_post = [p for p in r["post_check_probes"] if p["status"] in ("200", "400", "422")]
        if likely_post:
            print(f"  🟢 POST endpoint adayları (var gibi görünüyor):")
            for p in likely_post:
                print(f"     POST {p['path']}  [{p['status']}] {p.get('note', '')}")

    print(f"\n📁 Tam sonuçlar: {log_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
