#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web panel actions that wrap the existing invoice scripts."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for path in (PROJECT_ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.export_customer_product_prices import export_customer_product_prices
from scripts.export_fabrikalar import export_fabrikalar
from scripts.export_supplier_invoice_details import export_supplier_reports
from scripts.export_to_excel import (
    export_agent_runs,
    export_incoming_invoices,
    export_outgoing_invoices,
)
from scripts.pg_invoice_matcher import generate_excel, get_matching_data
from scripts.pg_reverse_matcher import generate_excel as generate_reverse_excel
from scripts.pg_reverse_matcher import get_reverse_matching_data
from scripts.run_invoice_pipeline import parse_date, run_pipeline
from scripts.sync_factory_kar import sync as sync_factory_kar


Runner = Callable[[dict[str, Any]], list[Path]]


@dataclass(frozen=True)
class ActionDefinition:
    key: str
    label: str
    description: str
    runner: Runner
    exclusive: bool = True
    requires_confirmation: bool = False


def _output_dir(params: dict[str, Any]) -> Path:
    output_dir = Path(str(params.get("output_dir") or "kayıtlar"))
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _optional_date(params: dict[str, Any], key: str) -> datetime | None:
    value = str(params.get(key) or "").strip()
    return parse_date(value) if value else None


def _bool(params: dict[str, Any], key: str) -> bool:
    value = params.get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _pipeline_args(params: dict[str, Any], *, skip_ingest: bool, all_excel: bool) -> argparse.Namespace:
    return argparse.Namespace(
        start_date=_optional_date(params, "start_date"),
        end_date=_optional_date(params, "end_date"),
        output_dir=str(_output_dir(params)),
        skip_ingest=skip_ingest,
        skip_reverse=_bool(params, "skip_reverse"),
        skip_despatches=_bool(params, "skip_despatches"),
        despatch_description_pdf=[str(params.get("despatch_description_pdf") or "data/incoming_despatch_pdfs")],
        refresh_despatch_descriptions=_bool(params, "refresh_despatch_descriptions"),
        despatch_page_size=int(params.get("despatch_page_size") or 100),
        despatch_max_pages=int(params.get("despatch_max_pages") or 3),
        despatch_base_url=str(params.get("despatch_base_url") or "https://isbasimw.isbasi.com"),
        refresh_xml=_bool(params, "refresh_xml"),
        all_excel=all_excel or _bool(params, "all_excel"),
    )


def run_full_pipeline(params: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in run_pipeline(_pipeline_args(params, skip_ingest=False, all_excel=False))]


def run_excel_only_pipeline(params: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in run_pipeline(_pipeline_args(params, skip_ingest=True, all_excel=False))]


def run_all_excel_pipeline(params: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in run_pipeline(_pipeline_args(params, skip_ingest=_bool(params, "skip_ingest"), all_excel=True))]


def run_forward_match(params: dict[str, Any]) -> list[Path]:
    output_dir = _output_dir(params)
    df = get_matching_data()
    return [Path(generate_excel(df, output_dir=output_dir))]


def run_reverse_match(params: dict[str, Any]) -> list[Path]:
    output_dir = _output_dir(params)
    df = get_reverse_matching_data()
    return [Path(generate_reverse_excel(df, output_dir=output_dir))]


def run_export_incoming(params: dict[str, Any]) -> list[Path]:
    path = _output_dir(params) / f"Gelen_Faturalar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return [path] if export_incoming_invoices(path) else []


def run_export_outgoing(params: dict[str, Any]) -> list[Path]:
    path = _output_dir(params) / f"Giden_Faturalar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return [path] if export_outgoing_invoices(path) else []


def run_export_agent_runs(params: dict[str, Any]) -> list[Path]:
    path = _output_dir(params) / f"Agent_Calismalari_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return [path] if export_agent_runs(path) else []


def run_export_supplier_reports(params: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in export_supplier_reports(_output_dir(params))]


def run_export_customer_prices(params: dict[str, Any]) -> list[Path]:
    return [Path(export_customer_product_prices(_output_dir(params)))]


def run_factory_report(params: dict[str, Any]) -> list[Path]:
    sync_factory_kar()
    return [Path(export_fabrikalar(_output_dir(params)))]


ACTIONS: dict[str, ActionDefinition] = {
    "full_pipeline": ActionDefinition(
        key="full_pipeline",
        label="Gelen/Giden Verileri Çek, Eşleştir, Excel Üret",
        description="İşbaşı API'den verileri çeker, PostgreSQL'e yazar ve eşleştirme raporlarını üretir.",
        runner=run_full_pipeline,
    ),
    "excel_only": ActionDefinition(
        key="excel_only",
        label="Mevcut Veriden Eşleştirme Excel'i Üret",
        description="API'ye bağlanmadan mevcut PostgreSQL verisiyle normal ve ters eşleştirme raporları üretir.",
        runner=run_excel_only_pipeline,
    ),
    "all_excel": ActionDefinition(
        key="all_excel",
        label="Tüm Excel Paketini Üret",
        description="Eşleştirme, ters eşleştirme, gelen/giden listeleri, agent çalışmaları ve ürün raporlarını üretir.",
        runner=run_all_excel_pipeline,
    ),
    "forward_match": ActionDefinition(
        key="forward_match",
        label="Sadece Giden -> Gelen Eşleştirme",
        description="PostgreSQL verisinden normal eşleştirme raporunu üretir.",
        runner=run_forward_match,
    ),
    "reverse_match": ActionDefinition(
        key="reverse_match",
        label="Sadece Gelen -> Giden Kontrol",
        description="PostgreSQL verisinden ters eşleştirme raporunu üretir.",
        runner=run_reverse_match,
    ),
    "export_incoming": ActionDefinition(
        key="export_incoming",
        label="Sadece Gelen Faturaları Excel'e Aktar",
        description="incoming_invoices tablosunu Excel'e aktarır.",
        runner=run_export_incoming,
        exclusive=False,
    ),
    "export_outgoing": ActionDefinition(
        key="export_outgoing",
        label="Sadece Giden Faturaları Excel'e Aktar",
        description="outgoing_invoices tablosunu Excel'e aktarır.",
        runner=run_export_outgoing,
        exclusive=False,
    ),
    "export_agent_runs": ActionDefinition(
        key="export_agent_runs",
        label="Agent Çalışma Geçmişini Excel'e Aktar",
        description="agent_runs tablosunu Excel'e aktarır.",
        runner=run_export_agent_runs,
        exclusive=False,
    ),
    "supplier_reports": ActionDefinition(
        key="supplier_reports",
        label="AK GIPS ve FULLBOARD Ürün Detaylarını Üret",
        description="Gelen fatura XML cache'inden fabrika ürün detay Excel'lerini üretir.",
        runner=run_export_supplier_reports,
    ),
    "customer_prices": ActionDefinition(
        key="customer_prices",
        label="Müşteri Ürün Fiyatlarını Üret",
        description="Giden fatura XML cache'inden müşteri ürün fiyat raporunu üretir.",
        runner=run_export_customer_prices,
    ),
    "factory_report": ActionDefinition(
        key="factory_report",
        label="Fabrika Kar Senkronizasyonu ve Raporu",
        description="Eşleşen satırları fabrika tablolarına işler ve Fabrikalar Excel raporunu üretir.",
        runner=run_factory_report,
        requires_confirmation=True,
    ),
}
