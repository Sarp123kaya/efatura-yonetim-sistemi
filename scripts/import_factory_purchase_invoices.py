#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKG/FLL E-Fatura → İşbaşı Alış Faturası Aktarımı — CLI
=========================================================

Yalnızca AK GİPS ve FULLBOARD fabrikalarından gelen, kabul edilmiş
ve henüz aktarılmamış e-faturaları İşbaşı'ya alış faturası olarak yazar.

Kullanım:
    # Önce dry-run ile nelerin aktarılacağını gör:
    python scripts/import_factory_purchase_invoices.py

    # Belirli tarih aralığı:
    python scripts/import_factory_purchase_invoices.py --start 2026-01-01 --end 2026-05-31

    # Gerçek aktarım (onay gerektirir):
    python scripts/import_factory_purchase_invoices.py --execute

    # Şifre CLI'dan:
    python scripts/import_factory_purchase_invoices.py --password SIFRENIM

    # Belirli endpoint zorla (probe sonrası):
    python scripts/import_factory_purchase_invoices.py --endpoint /api/v1.0/einvoices/integrationPurchaseInvoice --execute
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.purchase_invoice_importer import (
    FACTORY_SUPPLIERS,
    ImportReport,
    PurchaseInvoiceImporter,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def print_report(report: ImportReport) -> None:
    """Aktarım raporunu konsola yazar."""
    print()
    print("=" * 70)
    print(f"📊 AKTARIM RAPORU — {'DRY-RUN' if report.dry_run else 'GERÇEK'}")
    print(f"   {report.run_at}")
    print("=" * 70)
    print(f"   Toplam aday   : {report.total_candidates}")
    print(f"   Aktarıldı     : {report.imported}")
    print(f"   Atlandı       : {report.skipped}")
    print(f"   Hata          : {report.failed}")
    if report.endpoint_discovered:
        print(f"   Endpoint      : {report.endpoint_discovered}")
    print()

    if report.results:
        print("  Detaylar:")
        for r in report.results:
            if r.skipped:
                icon = "⏭ "
                detail = r.skip_reason
            elif r.success and not report.dry_run:
                icon = "✅ "
                detail = f"purchaseInvoiceId={r.purchase_invoice_id}"
            elif r.success and report.dry_run:
                icon = "🔍 "
                detail = "aktarılacak (dry-run)"
            else:
                icon = "❌ "
                detail = r.error[:80]

            sc_label = f"statusCode={r.status_code}" if r.status_code is not None else ""
            print(f"    {icon} {r.invoice_id:<25} {r.supplier[:30]:<32} {sc_label:<18} {detail}")

    print("=" * 70)

    if report.dry_run and report.total_candidates > 0:
        print()
        print("💡 Gerçek aktarım için: --execute parametresiyle tekrar çalıştırın")
    elif not report.dry_run and report.imported > 0:
        print()
        print(f"✅ {report.imported} fatura başarıyla İşbaşı'ya alış faturası olarak aktarıldı.")


def save_report(report: ImportReport, output_dir: Path) -> Path:
    """Raporu JSON olarak kaydeder."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "dryrun" if report.dry_run else "execute"
    path = output_dir / f"factory_purchase_import_{mode}_{ts}.json"
    data = {
        "run_at": report.run_at,
        "dry_run": report.dry_run,
        "total_candidates": report.total_candidates,
        "imported": report.imported,
        "skipped": report.skipped,
        "failed": report.failed,
        "endpoint_discovered": report.endpoint_discovered,
        "results": [
            {
                "invoice_id": r.invoice_id,
                "uuid": r.uuid,
                "supplier": r.supplier,
                "status_code": r.status_code,
                "success": r.success,
                "purchase_invoice_id": r.purchase_invoice_id,
                "endpoint_used": r.endpoint_used,
                "error": r.error,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
            }
            for r in report.results
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AKG/FLL e-fatura → İşbaşı alış faturası aktarımı"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Gerçek aktarım yap (varsayılan: dry-run)",
    )
    parser.add_argument("--start", default="2026-01-01", help="Başlangıç tarihi YYYY-MM-DD")
    parser.add_argument("--end", default="", help="Bitiş tarihi YYYY-MM-DD (varsayılan: bugün)")
    parser.add_argument("--password", default="", help="İşbaşı şifresi (yoksa getpass)")
    parser.add_argument(
        "--endpoint",
        default="",
        help="İçeri alma endpoint'i (boş = otomatik keşif)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/logs",
        help="Rapor çıktı dizini (varsayılan: data/logs)",
    )
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 70)
    print("🏭  AKG / FLL  E-Fatura → İşbaşı Alış Faturası Aktarımı")
    factory_str = ", ".join(f"{k} ({v['short']})" for k, v in FACTORY_SUPPLIERS.items())
    print(f"   Fabrikalar: {factory_str}")
    print(f"   Tarih      : {args.start} — {args.end or 'bugün'}")
    print(f"   Mod        : {'DRY-RUN (sadece önizleme)' if dry_run else '⚠️  GERÇEK AKTARIM'}")
    print("=" * 70)

    if not dry_run:
        print()
        confirm = input("Gerçek aktarım yapılacak. Devam etmek için 'evet' yazın: ").strip().lower()
        if confirm not in ("evet", "e", "yes", "y"):
            print("İptal edildi.")
            sys.exit(0)

    importer = PurchaseInvoiceImporter(
        password=args.password or None,
        start_date=args.start,
        end_date=args.end,
        import_endpoint=args.endpoint,
    )

    try:
        report = importer.run(dry_run=dry_run)
    except KeyboardInterrupt:
        print("\n❌ Kullanıcı tarafından iptal edildi.")
        sys.exit(1)
    except Exception as exc:
        logger.error("Kritik hata: %s", exc, exc_info=True)
        sys.exit(1)

    print_report(report)

    output_dir = PROJECT_ROOT / args.output_dir
    log_path = save_report(report, output_dir)
    print(f"\n📁 Rapor kaydedildi: {log_path}")


if __name__ == "__main__":
    main()
