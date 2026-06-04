#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Probe İşbaşı outgoing invoice detail endpoints.

The outgoing invoice list endpoint only returns invoice headers. This diagnostic
script logs in, selects one outgoing invoice from PostgreSQL, and tries likely
detail/UBL endpoint shapes to discover where product line items are available.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import config
from backend.core.db import db
from ingestion.api_data_extractor import IsbasiAPIDataExtractor


LINE_HINTS = (
    "lines",
    "lineItems",
    "invoiceLines",
    "invoiceLine",
    "items",
    "products",
    "details",
    "stockTransactions",
    "materialTransactions",
    "serviceTransactions",
)


def get_nested(value: Any, dotted_key: str) -> Any:
    current = value
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def flatten_keys(value: Any, prefix: str = "") -> List[str]:
    keys = []
    if isinstance(value, dict):
        for key, nested in value.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            keys.append(full)
            keys.extend(flatten_keys(nested, full))
    elif isinstance(value, list):
        for item in value[:3]:
            keys.extend(flatten_keys(item, prefix))
    return keys


def looks_like_line_payload(value: Any) -> bool:
    keys = {key.lower() for key in flatten_keys(value)}
    if any(hint.lower() in keys for hint in LINE_HINTS):
        return True
    joined = " ".join(keys)
    product_terms = ("product", "item", "stock", "material", "service", "quantity", "amount", "price")
    return sum(1 for term in product_terms if term in joined) >= 3


def response_summary(response) -> Dict[str, Any]:
    text = response.text or ""
    summary = {
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "text_head": text[:500],
    }
    try:
        parsed = response.json()
        summary["json_keys"] = list(parsed.keys()) if isinstance(parsed, dict) else []
        summary["looks_like_line_payload"] = looks_like_line_payload(parsed)
        summary["json"] = parsed
    except Exception:
        summary["looks_like_line_payload"] = any(token in text for token in ("InvoiceLine", "InvoicedQuantity", "PriceAmount"))
    return summary


def login(extractor: IsbasiAPIDataExtractor) -> bool:
    if config.ISBASI_PASSWORD:
        login_data = {
            "username": config.ISBASI_USERNAME,
            "password": config.ISBASI_PASSWORD,
        }
        response = extractor.session.post(
            f"{extractor.base_url}{extractor.endpoints['login']}",
            json=login_data,
            timeout=extractor.timeout,
            verify=extractor.verify_ssl,
        )
        if response.status_code != 200:
            print(f"❌ .env ile login başarısız: HTTP {response.status_code}")
            return False
        data = response.json().get("data", {})
        extractor.access_token = data.get("accessToken")
        extractor.user_id = data.get("id") or data.get("userId")
        extractor.user_email = data.get("email") or config.ISBASI_USERNAME
        extractor.tenant_id = data.get("tenantId")
        extractor.user_name = data.get("userName") or data.get("name")
        if extractor.access_token:
            extractor.session.headers.update({"Authorization": f"Bearer {extractor.access_token}"})
        if extractor.user_id:
            extractor.session.headers.update({"UserId": str(extractor.user_id)})
        if extractor.user_email:
            extractor.session.headers.update({"UserEmail": extractor.user_email})
        if extractor.tenant_id:
            extractor.session.headers.update({"tenantId": str(extractor.tenant_id)})
        if extractor.user_name:
            extractor.session.headers.update({"UserName": extractor.user_name})
        return True

    return extractor.secure_login()


def fetch_invoice(invoice_id: str = "") -> Dict[str, Any]:
    if invoice_id:
        row = db.query_one(
            """
            SELECT id, invoice_no, issue_date, firm_name, raw_json
            FROM outgoing_invoices
            WHERE id = %s OR invoice_no = %s
            LIMIT 1
            """,
            (invoice_id, invoice_id),
        )
    else:
        row = db.query_one(
            """
            SELECT id, invoice_no, issue_date, firm_name, raw_json
            FROM outgoing_invoices
            ORDER BY issue_date DESC
            LIMIT 1
            """
        )
    if not row:
        raise SystemExit("Giden fatura kaydı bulunamadı.")
    return row


def candidate_identifiers(row: Dict[str, Any]) -> List[Tuple[str, Any]]:
    raw = row.get("raw_json") or {}
    candidates = [
        ("db_id", row.get("id")),
        ("db_invoice_no", row.get("invoice_no")),
        ("raw.id", raw.get("id")),
        ("raw.invoiceNumber", raw.get("invoiceNumber")),
        ("raw.dispatchNumber", raw.get("dispatchNumber")),
        ("raw.documentNumber", raw.get("documentNumber")),
        ("raw.firm.id", get_nested(raw, "firm.id")),
        ("raw.firmCode", raw.get("firmCode")),
    ]
    seen = set()
    unique = []
    for label, value in candidates:
        if value in (None, "", "Numarasız"):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, value))
    return unique


def build_requests(row: Dict[str, Any]) -> Iterable[Tuple[str, str, Dict[str, Any], Any]]:
    identifiers = candidate_identifiers(row)
    get_path_templates = [
        "/api/v1.0/invoices/{value}",
        "/api/v1.0/invoices/invoice/{value}",
        "/api/v1.0/invoices/detail/{value}",
        "/api/v1.0/invoices/details/{value}",
        "/api/v1.0/invoices/get/{value}",
        "/api/v1.0/invoices/getInvoice/{value}",
        "/api/v1.0/invoices/GetInvoice/{value}",
        "/api/v1.0/invoices/GetInvoiceById/{value}",
        "/api/v1.0/invoices/invoiceDetails/{value}",
        "/api/v1.0/invoices/items/{value}",
        "/api/v1.0/invoices/lines/{value}",
        "/api/v1.0/einvoices/{value}",
        "/api/v1.0/einvoices/detail/{value}",
        "/api/v1.0/einvoices/details/{value}",
        "/api/v1.0/einvoices/GetInvoice/{value}",
    ]
    query_endpoints = [
        "/api/v1.0/invoices/invoice",
        "/api/v1.0/invoices/detail",
        "/api/v1.0/invoices/details",
        "/api/v1.0/invoices/getInvoice",
        "/api/v1.0/invoices/GetInvoice",
        "/api/v1.0/invoices/GetInvoiceById",
        "/api/v1.0/invoices/invoiceDetails",
        "/api/v1.0/invoices/items",
        "/api/v1.0/invoices/lines",
        "/api/v1.0/einvoices/detail",
        "/api/v1.0/einvoices/details",
        "/api/v1.0/einvoices/GetInvoice",
        "/api/v1.0/einvoices/DocumentUblDatawithuuid",
        "/api/v1.0/invoices/DocumentUblDatawithuuid",
        "/api/v1.0/invoices/DocumentUblData",
    ]
    param_names = ["id", "invoiceId", "invoiceID", "invoiceNo", "invoiceNumber", "number", "uuid", "dispatchNumber"]

    for label, value in identifiers:
        for template in get_path_templates:
            yield "GET", template.format(value=value), {}, f"path:{label}"
        for endpoint in query_endpoints:
            for param_name in param_names:
                yield "GET", endpoint, {param_name: value, "type": 1}, f"query:{param_name}={label}"
                yield "GET", endpoint, {param_name: value}, f"query:{param_name}={label}"

    # Common POST detail shapes.
    raw = row.get("raw_json") or {}
    for payload in [
        {"id": row.get("id")},
        {"invoiceId": row.get("id")},
        {"invoiceNumber": row.get("invoice_no")},
        {"dispatchNumber": raw.get("dispatchNumber")},
        {"filters": [{"columnName": "id", "operator": 0, "value": row.get("id")}], "paging": {"currentPage": 1, "pageSize": 20}},
    ]:
        for endpoint in [
            "/api/v1.0/invoices/invoice",
            "/api/v1.0/invoices/detail",
            "/api/v1.0/invoices/details",
            "/api/v1.0/invoices/getInvoice",
            "/api/v1.0/invoices/GetInvoice",
            "/api/v1.0/invoices/invoiceDetails",
            "/api/v1.0/invoices/items",
            "/api/v1.0/invoices/lines",
        ]:
            yield "POST", endpoint, {}, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Giden fatura ürün/adet detay endpointini keşfet.")
    parser.add_argument("--invoice", default="", help="Denenecek giden fatura id veya fatura no.")
    parser.add_argument("--limit", type=int, default=160, help="Denenecek maksimum istek sayısı.")
    args = parser.parse_args()

    row = fetch_invoice(args.invoice)
    print("Seçilen fatura:")
    print(f"  ID: {row['id']}")
    print(f"  No: {row['invoice_no']}")
    print(f"  Tarih: {row['issue_date']}")
    print(f"  Müşteri: {row['firm_name']}")

    extractor = IsbasiAPIDataExtractor()
    if not login(extractor):
        raise SystemExit("Login başarısız.")

    results = []
    successful = []
    for index, (method, endpoint, params, payload) in enumerate(build_requests(row), 1):
        if index > args.limit:
            break
        url = f"{extractor.base_url}{endpoint}"
        try:
            if method == "GET":
                response = extractor.session.get(url, params=params, timeout=extractor.timeout, verify=extractor.verify_ssl)
            else:
                response = extractor.session.post(url, json=payload, timeout=extractor.timeout, verify=extractor.verify_ssl)
        except Exception as exc:
            results.append({"method": method, "endpoint": endpoint, "params": params, "payload": payload, "error": str(exc)})
            continue

        summary = response_summary(response)
        record = {
            "method": method,
            "endpoint": endpoint,
            "params": params,
            "payload": payload,
            **summary,
        }
        results.append(record)

        if response.status_code == 200:
            print(f"HTTP 200: {method} {endpoint} params={params} payload={payload}")
            if summary.get("looks_like_line_payload"):
                print("  ✅ Ürün satırı olabilecek payload bulundu.")
                successful.append(record)
                break

    out_dir = PROJECT_ROOT / "data" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"outgoing_invoice_detail_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print()
    print(f"Deneme logu: {out_file}")
    if successful:
        found = successful[0]
        print("Bulunan aday:")
        print(f"  {found['method']} {found['endpoint']}")
        print(f"  params={found.get('params')}")
        print(f"  payload={found.get('payload')}")
    else:
        print("Ürün satırı içeren endpoint bulunamadı. Log dosyasındaki HTTP 200 cevaplarını incelemek gerekiyor.")

    db.close_persistent_connection()


if __name__ == "__main__":
    main()
