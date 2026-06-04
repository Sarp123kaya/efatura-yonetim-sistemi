#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKG/FLL E-Fatura → İşbaşı Alış Faturası İçeri Aktarma Modülü
==============================================================

Bu modül yalnızca AK GİPS ve FULLBOARD fabrikalarından gelen,
kabul edilmiş (statusCode ≥ 1) ve henüz içeri alınmamış
(purchaseInvoiceId == 0 veya null) e-faturaları İşbaşı'ya alış
faturası olarak aktarır.

Tasarım ilkeleri:
- Mevcut hiçbir dosyaya dokunmaz / değiştirmez
- dry_run=True varsayılanı: gerçek oluşturma için açıkça False geçilmeli
- Her adım loglanır; hata alınan fatura atlanır, diğerlerine devam edilir
- Mükerrer koruma: purchaseInvoiceId zaten doluysa atlar
- DB'ye dokunmaz: İşbaşı API'sine yazar, sadece sonuç raporunu döner

Kullanım (kod):
    from backend.core.purchase_invoice_importer import PurchaseInvoiceImporter
    imp = PurchaseInvoiceImporter()
    report = imp.run(dry_run=True)   # önce dry-run ile kontrol edin
    report = imp.run(dry_run=False)  # gerçek aktarım

CLI için: scripts/import_factory_purchase_invoices.py
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.isbasi_client import IsbasiApiClient, IsbasiAPIError

logger = logging.getLogger(__name__)

# ── Fabrika sabitleri ────────────────────────────────────────────────────────

FACTORY_SUPPLIERS: Dict[str, Dict[str, str]] = {
    "AKG": {
        "vkn": "0111275461",
        "name": "AK GİPS YAPI KİMYASALLARI İNŞ. ENERJİ ÜR A.Ş.",
        "short": "AK GİPS",
    },
    "FLL": {
        "vkn": "6100452262",
        "name": "FULLBOARD YAPI ELEMANLARI A.Ş.",
        "short": "FULLBOARD",
    },
}
FACTORY_VKN_SET = {v["vkn"] for v in FACTORY_SUPPLIERS.values()}

# statusCode değerleri (myInvoicesList'ten gözlemlenen)
# 0 = İşlem Bekleniyor / henüz yanıt verilmemiş
# 1 = Kabul Edildi  (genellikle)
# 2 = Red Edildi
# Probe sonucuna göre güncellenebilir.
ACCEPTED_STATUS_CODES = {1, 3, 5, 6, 7, 8, 9}  # Geniş tutuldu; probe netleştirir

# İçeri alma endpoint adayları — sırasıyla denenir, ilk başarılı kullanılır
# Probe scripti çalıştırıldıktan sonra başarılı olan buraya taşınabilir.
IMPORT_ENDPOINT_CANDIDATES: List[str] = [
    "/api/v1.0/einvoices/integrationPurchaseInvoice",
    "/api/v1.0/einvoices/createPurchaseInvoice",
    "/api/v1.0/invoices/integrationPurchaseInvoices",
    "/api/v1.0/invoices/integrationPurchaseInvoice",
    "/api/v1.0/purchases/integrationPurchases",
    "/api/v1.0/purchases/fromEInvoice",
]

# Eğer probe sonucu kesin endpoint bulunduysa buraya yaz (boş = otomatik keşif):
CONFIRMED_IMPORT_ENDPOINT: str = ""


# ── Veri sınıfları ────────────────────────────────────────────────────────────

@dataclass
class InvoiceImportResult:
    invoice_id: str
    uuid: str
    supplier: str
    status_code: Optional[int]
    success: bool
    purchase_invoice_id: Optional[int] = None
    endpoint_used: str = ""
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class ImportReport:
    run_at: str = field(default_factory=lambda: datetime.now().isoformat())
    dry_run: bool = True
    total_candidates: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    endpoint_discovered: str = ""
    results: List[InvoiceImportResult] = field(default_factory=list)

    def summary(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "GERÇEK"
        return (
            f"[{mode}] {self.total_candidates} aday | "
            f"✅ {self.imported} aktarıldı | "
            f"⏭ {self.skipped} atlandı | "
            f"❌ {self.failed} hata"
        )


# ── Ana sınıf ─────────────────────────────────────────────────────────────────

class PurchaseInvoiceImporter:
    """
    AKG/FLL e-fatura → İşbaşı alış faturası aktarıcı.

    Parametreler:
        password:           İşbaşı API şifresi (None → .env veya getpass)
        start_date:         Fatura tarih filtresi başlangıcı (YYYY-MM-DD)
        end_date:           Fatura tarih filtresi bitişi  (YYYY-MM-DD)
        request_delay:      İstekler arası bekleme (saniye)
        page_size:          myInvoicesList sayfa boyutu
        import_endpoint:    Zorunlu endpoint (boş = otomatik keşif)
    """

    def __init__(
        self,
        password: Optional[str] = None,
        start_date: str = "2026-01-01",
        end_date: str = "",
        request_delay: float = 0.5,
        page_size: int = 100,
        import_endpoint: str = "",
    ) -> None:
        self.password = password
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.request_delay = request_delay
        self.page_size = page_size
        self._import_endpoint: str = import_endpoint or CONFIRMED_IMPORT_ENDPOINT
        self._client: Optional[IsbasiApiClient] = None

    # ── İstemci ──────────────────────────────────────────────────────────────

    def _get_client(self) -> IsbasiApiClient:
        if self._client is None:
            self._client = IsbasiApiClient()
            self._client.login(password=self.password)
        return self._client

    # ── E-fatura listesi ─────────────────────────────────────────────────────

    def fetch_factory_invoices(self) -> List[Dict[str, Any]]:
        """
        AKG/FLL faturalarını çeker.
        Önce veritabanından dener (rate limit yok), başarısız olursa API'ye geçer.
        """
        # Önce DB'den dene
        db_rows = self._fetch_from_db()
        if db_rows:
            return db_rows
        # DB boşsa veya erişilemezse API'ye geç
        return self._fetch_from_api()

    def _fetch_from_db(self) -> List[Dict[str, Any]]:
        """incoming_invoices tablosundan AKG/FLL faturalarını çeker."""
        try:
            from backend.core.db import db as _db
            vkn_list = list(FACTORY_VKN_SET)
            placeholders = ",".join(["%s"] * len(vkn_list))
            rows = _db.query(
                f"""
                SELECT i.invoice_id, i.uuid, i.supplier, i.supplier_tckn_vkn,
                       i.amount, i.total_vat_base, i.currency, i.issue_date,
                       i.raw_json
                FROM incoming_invoices i
                WHERE i.supplier_tckn_vkn IN ({placeholders})
                  AND i.issue_date >= %s
                  AND i.issue_date <= %s
                ORDER BY i.issue_date DESC
                """,
                tuple(vkn_list) + (self.start_date, self.end_date),
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
                invoice = dict(raw)
                invoice["invoiceId"] = invoice.get("invoiceId") or str(row.get("invoice_id") or "")
                invoice["uuId"] = invoice.get("uuId") or str(row.get("uuid") or "")
                invoice["supplier"] = invoice.get("supplier") or str(row.get("supplier") or "")
                invoice["supplierTcknVkn"] = (
                    invoice.get("supplierTcknVkn") or str(row.get("supplier_tckn_vkn") or "")
                )
                invoice["amount"] = invoice.get("amount") or float(row.get("amount") or 0)
                result.append(invoice)
            logger.info("   DB'den %d AKG/FLL fatura yüklendi", len(result))
            return result
        except Exception as exc:
            logger.warning("DB'den fatura yüklenemedi: %s — API'ye geçiliyor", exc)
            return []

    def _fetch_from_api(self) -> List[Dict[str, Any]]:
        """myInvoicesList API'sinden AKG/FLL faturalarını çeker."""
        client = self._get_client()
        logger.info("📥 AKG/FLL e-faturaları API'den çekiliyor (%s — %s)...", self.start_date, self.end_date)

        payload = {
            "filters": [
                {"columnName": "issueDate", "operator": 5, "value": f"{self.start_date}T00:00:00"},
                {"columnName": "issueDate", "operator": 2, "value": f"{self.end_date}T23:59:59"},
            ],
            "sorting": {"issueDate": -1},
            "paging": {"currentPage": 1, "pageSize": self.page_size},
            "count": True,
            "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
        }

        all_rows: List[Dict[str, Any]] = []
        page = 1
        while True:
            payload["paging"]["currentPage"] = page
            try:
                resp = client.post("/api/v1.0/einvoices/myInvoicesList", payload)
            except IsbasiAPIError as exc:
                logger.error("myInvoicesList hatası (sayfa %d): %s", page, exc)
                break

            data = resp.get("data") or {}
            rows: List[Dict[str, Any]] = data.get("data") if isinstance(data, dict) else []
            rows = rows or []
            if not rows:
                break

            all_rows.extend(rows)
            total = data.get("count") if isinstance(data, dict) else None
            if len(rows) < self.page_size:
                break
            if total is not None and len(all_rows) >= int(total):
                break
            page += 1
            time.sleep(self.request_delay)

        factory_rows = [
            r for r in all_rows
            if str(r.get("supplierTcknVkn") or "").strip() in FACTORY_VKN_SET
        ]
        logger.info("   API: toplam %d | AKG/FLL: %d", len(all_rows), len(factory_rows))
        return factory_rows

    # ── Aday seçimi ──────────────────────────────────────────────────────────

    def filter_pending_invoices(
        self, invoices: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        İçeri alınmaya uygun faturaları filtreler:
        - statusCode kabul edilmiş olmalı (ACCEPTED_STATUS_CODES)
        - purchaseInvoiceId == 0 veya None (daha önce aktarılmamış)
        """
        pending = []
        for inv in invoices:
            sc = inv.get("statusCode")
            pi_id = inv.get("purchaseInvoiceId")
            inv_id = str(inv.get("invoiceId") or "")

            # Daha önce aktarılmış mı?
            if pi_id and int(pi_id) > 0:
                logger.debug("  ATLA (zaten aktarılmış) → %s  purchaseInvoiceId=%s", inv_id, pi_id)
                continue

            # Status kodu kabul edilmiş mi?
            # statusCode 0 = bekliyor, pozitif değerler genellikle kabul
            # statusCode None = bilgi yok; güvenli tarafta kalmak için dahil et
            if sc is not None and int(sc) not in ACCEPTED_STATUS_CODES and int(sc) != 0:
                logger.debug("  ATLA (reddedilmiş/beklenmedik status) → %s  statusCode=%s", inv_id, sc)
                continue

            pending.append(inv)

        logger.info("   Aktarım adayı: %d fatura", len(pending))
        return pending

    # ── Firma kartı çekme ─────────────────────────────────────────────────────

    def _lookup_firm_by_vkn(self, vkn: str) -> Optional[Dict[str, Any]]:
        """
        İşbaşı'dan VKN ile cari kartını çeker.
        list_firms endpoint'i kullanılır — rate limit düşük, verimli.
        """
        client = self._get_client()
        try:
            firms = client.list_firms(
                filters=[
                    {"columnName": "isActive", "operator": "IsEqualTo", "value": True},
                    {"columnName": "vknTckn", "operator": "IsEqualTo", "value": vkn},
                ],
                page_size=5,
                max_pages=1,
            )
            if firms:
                logger.info("   Cari bulundu: %s (VKN: %s)", firms[0].get("name"), vkn)
                return firms[0]
            # VKN filtresi çalışmadıysa geniş listeyle tara
            all_firms = client.list_firms(page_size=200, max_pages=5)
            for firm in all_firms:
                firm_vkn = str(firm.get("vknTckn") or firm.get("taxOrPersonalId") or "")
                import re as _re
                if _re.sub(r"\D", "", firm_vkn) == _re.sub(r"\D", "", vkn):
                    logger.info("   Cari (tarama) bulundu: %s (VKN: %s)", firm.get("name"), vkn)
                    return firm
        except IsbasiAPIError as exc:
            logger.warning("   Cari çekilemedi (VKN: %s): %s", vkn, exc)
        return None

    def _get_invoice_template(self, uuid: str, inv_id: str) -> Optional[Dict[str, Any]]:
        """
        InvoiceTypeForEInvoice endpoint'inden e-fatura şablonunu çeker.
        Bu endpoint fatura satırlarını ve tam form verilerini döner.
        isbasimw.isbasi.com üzerinde çalışır.
        """
        alt_base = "https://isbasimw.isbasi.com"
        client = self._get_client()

        # Alt base URL'li geçici istemci — aynı token
        import requests as _requests
        alt_session = _requests.Session()
        alt_session.verify = client.verify_ssl
        alt_session.headers.update(dict(client.session.headers))

        param_variants = [
            {"uuid": uuid},
            {"id": uuid},
            {"invoiceId": inv_id},
            {"uuid": uuid, "invoiceId": inv_id},
        ]
        for params in param_variants:
            try:
                url = f"{alt_base}/api/v1.0/invoices/InvoiceTypeForEInvoice"
                resp = alt_session.get(url, params=params, timeout=30, verify=client.verify_ssl)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("   ✅ InvoiceTypeForEInvoice başarılı (params=%s)", params)
                    return data
                elif resp.status_code == 429:
                    logger.warning("   ⚠️  InvoiceTypeForEInvoice rate limit — template olmadan devam")
                    return None
            except Exception as exc:
                logger.debug("   InvoiceTypeForEInvoice hata (params=%s): %s", params, exc)
        return None

    # ── Endpoint keşfi ───────────────────────────────────────────────────────

    def discover_import_endpoint(self, sample_invoice: Dict[str, Any]) -> str:
        """
        Probe sonucundan bilinen endpoint'i döner.
        integrationInvoices 500 döndürdü → endpoint VAR, customer modeli gerekiyor.
        Bu yüzden doğrudan bu endpoint'i kullan.
        """
        if self._import_endpoint:
            logger.info("   Endpoint yapılandırılmış: %s", self._import_endpoint)
            return self._import_endpoint

        # Probe'dan öğrendik: integrationInvoices hem mw-jplatform'da hem isbasimw'da çalışıyor
        # 500 → customer modeli eksikti. Biz bunu ekleyeceğiz.
        endpoint = "/api/v1.0/invoices/integrationInvoices"
        logger.info("   Endpoint belirlendi (probe sonucu): %s", endpoint)
        self._import_endpoint = endpoint
        return endpoint

    # ── İçeri alma payload'ı ─────────────────────────────────────────────────

    def _build_import_payload(
        self,
        invoice: Dict[str, Any],
        firm: Optional[Dict[str, Any]] = None,
        template: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        E-faturadan alış faturası payload'ı inşa eder.

        Probe sonucu:
        - integrationInvoices → customer modeli zorunlu (IntegrationCustomerModelIsRequired)
        - template: InvoiceTypeForEInvoice'den gelen tam veri (satırlar dahil)
        - firm: list_firms'ten gelen cari kartı

        Eğer template varsa onu temel al, yoksa raw_json'dan inşa et.
        """
        uuid = str(invoice.get("uuId") or "")
        inv_id = str(invoice.get("invoiceId") or "")
        issue_date = str(invoice.get("issueDate") or "")
        amount = invoice.get("amount") or 0
        vat_base = invoice.get("totalVatBase") or 0
        currency = str(invoice.get("currency") or "TRY")

        # customer modeli — cari kartından veya invoice'dan
        customer: Dict[str, Any] = {}
        if firm:
            customer = {
                "id": firm.get("id") or firm.get("firmId") or "",
                "code": firm.get("code") or firm.get("firmCode") or "",
                "name": firm.get("name") or firm.get("displayName") or "",
                "taxOrPersonalId": firm.get("vknTckn") or firm.get("taxOrPersonalId") or "",
            }
        else:
            # Firma bulunamadıysa VKN ile minimal model
            customer = {
                "taxOrPersonalId": str(invoice.get("supplierTcknVkn") or ""),
                "name": str(invoice.get("supplier") or ""),
            }

        # Template varsa onun üzerine customer ve type ekle
        if template:
            tdata = template.get("data") if isinstance(template, dict) else template
            if isinstance(tdata, dict):
                payload = dict(tdata)
                payload["customer"] = customer
                payload["type"] = "PURCHASE_INVOICE"
                payload["invoiceType"] = "PURCHASE_INVOICE"
                payload["eInvoiceUUID"] = uuid
                return payload

        # Template yoksa raw_json'dan inşa et
        return {
            "type": "PURCHASE_INVOICE",
            "invoiceType": "PURCHASE_INVOICE",
            "invoiceNumber": inv_id,
            "date": issue_date,
            "eInvoiceUUID": uuid,
            "eInvoiceId": inv_id,
            "customer": customer,
            "totalAmount": amount,
            "vatBase": vat_base,
            "currency": currency,
            "fromEInvoice": True,
            "sourceInvoiceType": 2,
        }

    # ── Firma cache ───────────────────────────────────────────────────────────

    _firm_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def _get_firm_cached(self, vkn: str) -> Optional[Dict[str, Any]]:
        if vkn not in self._firm_cache:
            self._firm_cache[vkn] = self._lookup_firm_by_vkn(vkn)
        return self._firm_cache[vkn]

    # ── Tek fatura aktarımı ──────────────────────────────────────────────────

    def _import_single(
        self,
        invoice: Dict[str, Any],
        endpoint: str,
        dry_run: bool,
    ) -> InvoiceImportResult:
        inv_id = str(invoice.get("invoiceId") or "")
        uuid = str(invoice.get("uuId") or "")
        supplier = str(invoice.get("supplier") or "")
        vkn = str(invoice.get("supplierTcknVkn") or "")
        status_code = invoice.get("statusCode")

        if dry_run:
            logger.info("  [DRY-RUN] Aktarılacak: %s (%s)", inv_id, supplier[:40])
            return InvoiceImportResult(
                invoice_id=inv_id,
                uuid=uuid,
                supplier=supplier,
                status_code=status_code,
                success=True,
                endpoint_used=endpoint,
                skipped=False,
            )

        client = self._get_client()

        # Adım 1: Cari kartını VKN ile çek
        logger.info("  Cari kartı çekiliyor (VKN: %s)...", vkn)
        firm = self._get_firm_cached(vkn) if vkn else None
        if not firm:
            logger.warning("  ⚠️  Cari bulunamadı (VKN: %s) — VKN ile devam", vkn)

        # Adım 2: InvoiceTypeForEInvoice'den fatura template'i çek
        logger.info("  Fatura şablonu çekiliyor (UUID: %s)...", uuid[:16])
        template = self._get_invoice_template(uuid, inv_id)
        if template:
            logger.info("  ✅ Fatura şablonu alındı")
        else:
            logger.info("  ⚠️  Şablon alınamadı — raw_json'dan inşa edilecek")

        # Adım 3: Payload inşa et
        payload = self._build_import_payload(invoice, firm=firm, template=template)

        # Adım 4: POST
        try:
            resp = client.post(endpoint, payload)
            data = resp.get("data") or {}
            pi_id = (
                data.get("id")
                or data.get("purchaseInvoiceId")
                or data.get("invoiceId")
            ) if isinstance(data, dict) else None

            logger.info("  ✅ Aktarıldı: %s → purchaseInvoiceId=%s", inv_id, pi_id)
            return InvoiceImportResult(
                invoice_id=inv_id,
                uuid=uuid,
                supplier=supplier,
                status_code=status_code,
                success=True,
                purchase_invoice_id=int(pi_id) if pi_id else None,
                endpoint_used=endpoint,
            )
        except IsbasiAPIError as exc:
            err_msg = str(exc)
            logger.error("  ❌ Hata: %s → %s", inv_id, err_msg[:200])
            # 500 → muhtemelen payload eksik alan var → logla
            if "HTTP 500" in err_msg:
                logger.error("  💡 500 alındı. Payload: %s", json.dumps(payload, ensure_ascii=False)[:400])
            return InvoiceImportResult(
                invoice_id=inv_id,
                uuid=uuid,
                supplier=supplier,
                status_code=status_code,
                success=False,
                endpoint_used=endpoint,
                error=err_msg[:300],
            )

    # ── Ana çalıştırıcı ──────────────────────────────────────────────────────

    def run(
        self,
        dry_run: bool = True,
        invoices: Optional[List[Dict[str, Any]]] = None,
    ) -> ImportReport:
        """
        Tam aktarım döngüsünü çalıştırır.

        Parametreler:
            dry_run:  True  → sadece hangi faturaların aktarılacağını gösterir
                      False → gerçekten İşbaşı'ya yazar
            invoices: Dışarıdan liste verilirse fetch atlanır (test için)
        """
        report = ImportReport(dry_run=dry_run)
        mode_label = "DRY-RUN" if dry_run else "GERÇEK AKTARIM"

        logger.info("=" * 60)
        logger.info("🏭 AKG/FLL Alış Faturası Aktarımı — %s", mode_label)
        logger.info("=" * 60)

        # 1. Fatura listesi
        if invoices is None:
            try:
                invoices = self.fetch_factory_invoices()
            except Exception as exc:
                logger.error("Fatura listesi çekilemedi: %s", exc)
                return report

        if not invoices:
            logger.info("Aktarılacak fatura bulunamadı.")
            return report

        # 2. Filtreleme
        pending = self.filter_pending_invoices(invoices)
        report.total_candidates = len(pending)

        if not pending:
            logger.info("İçeri alınmayı bekleyen AKG/FLL faturası yok.")
            return report

        # 3. Endpoint keşfi
        endpoint = self.discover_import_endpoint(pending[0])
        if not endpoint:
            logger.error(
                "Import endpoint bulunamadı. "
                "Önce probe_purchase_invoice_import.py çalıştırın, "
                "sonra CONFIRMED_IMPORT_ENDPOINT sabitini doldurun."
            )
            for inv in pending:
                report.results.append(InvoiceImportResult(
                    invoice_id=str(inv.get("invoiceId") or ""),
                    uuid=str(inv.get("uuId") or ""),
                    supplier=str(inv.get("supplier") or ""),
                    status_code=inv.get("statusCode"),
                    success=False,
                    skipped=True,
                    skip_reason="endpoint_not_found",
                    error="Import endpoint keşfedilemedi",
                ))
            report.skipped = len(pending)
            return report

        report.endpoint_discovered = endpoint
        logger.info("Kullanılacak endpoint: %s", endpoint)

        # 4. Aktarım döngüsü
        for inv in pending:
            result = self._import_single(inv, endpoint, dry_run=dry_run)
            report.results.append(result)
            if result.skipped:
                report.skipped += 1
            elif result.success:
                report.imported += 1
            else:
                report.failed += 1
            time.sleep(self.request_delay)

        logger.info("=" * 60)
        logger.info("📊 %s", report.summary())
        logger.info("=" * 60)
        return report

    # ── Aday listesi (UI için) ────────────────────────────────────────────────

    def list_candidates(self) -> List[Dict[str, Any]]:
        """
        Web paneli için: aktarıma uygun faturaları listeler (API çağrısı yapar).
        """
        invoices = self.fetch_factory_invoices()
        pending = self.filter_pending_invoices(invoices)
        return [
            {
                "invoice_id": str(inv.get("invoiceId") or ""),
                "uuid": str(inv.get("uuId") or ""),
                "supplier": str(inv.get("supplier") or ""),
                "supplier_vkn": str(inv.get("supplierTcknVkn") or ""),
                "issue_date": str(inv.get("issueDate") or ""),
                "amount": inv.get("amount"),
                "total_vat_base": inv.get("totalVatBase"),
                "currency": str(inv.get("currency") or "TRY"),
                "status": str(inv.get("status") or ""),
                "status_code": inv.get("statusCode"),
                "purchase_invoice_id": inv.get("purchaseInvoiceId"),
            }
            for inv in pending
        ]
