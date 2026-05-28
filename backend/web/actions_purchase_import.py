#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web panel actions — AKG/FLL Alış Faturası Aktarımı
====================================================

Bu dosya mevcut actions.py'ye dokunmadan yeni action'lar tanımlar.
app.py'deki ACTIONS sözlüğüne eklenmek yerine kendi PURCHASE_ACTIONS
sözlüğünü sağlar; route kaydı purchase_import_routes.py üzerinden yapılır.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.core.purchase_invoice_importer import ImportReport, PurchaseInvoiceImporter

logger = logging.getLogger(__name__)


def run_factory_purchase_import_dryrun(params: dict[str, Any]) -> ImportReport:
    """Dry-run: hangi faturaların aktarılacağını listeler, kayıt yapmaz."""
    importer = PurchaseInvoiceImporter(
        password=params.get("api_password") or None,
        start_date=str(params.get("start_date") or "2026-01-01"),
        end_date=str(params.get("end_date") or ""),
    )
    return importer.run(dry_run=True)


def run_factory_purchase_import_execute(params: dict[str, Any]) -> ImportReport:
    """Gerçek aktarım: kabul edilmiş AKG/FLL faturalarını İşbaşı'ya yazar."""
    importer = PurchaseInvoiceImporter(
        password=params.get("api_password") or None,
        start_date=str(params.get("start_date") or "2026-01-01"),
        end_date=str(params.get("end_date") or ""),
        import_endpoint=str(params.get("import_endpoint") or ""),
    )
    return importer.run(dry_run=False)


def list_factory_invoice_candidates(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Web paneli için aday listeyi döner (API çağrısı yapar)."""
    importer = PurchaseInvoiceImporter(
        password=params.get("api_password") or None,
        start_date=str(params.get("start_date") or "2026-01-01"),
        end_date=str(params.get("end_date") or ""),
    )
    return importer.list_candidates()
