#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tek komut fatura akışı:
1. Gelen faturaları API'den çekip PostgreSQL'e yazar.
2. Giden faturaları API'den çekip PostgreSQL'e yazar.
3. PostgreSQL verisi üzerinden eşleştirme (+ isteğe bağlı ters eşleştirme) Excel raporu üretir.
4. Gelen e-irsaliyeleri API'den çekip giden faturalarla eşleştirme raporu üretir.
5. --all-excel ile: Gelen/Giden listeleri, ters eşleştirme dahil yukarıdakilere ek olarak
   fabrika (AK GIPS / FULLBOARD) ve müşteri ürün fiyat Excel'lerini de aynı çalıştırmada üretir.
"""

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from backend.agents.incoming_agent import IncomingInvoiceAgent
from backend.agents.outgoing_agent import OutgoingInvoiceAgent
from backend.core.db import db
from pg_invoice_matcher import generate_excel, get_matching_data
from pg_reverse_matcher import generate_excel as generate_reverse_excel
from pg_reverse_matcher import get_reverse_matching_data

from backend.core.isbasi_client import IsbasiApiClient
from export_customer_product_prices import export_customer_product_prices
from export_supplier_invoice_details import export_supplier_reports
from export_to_excel import (
    export_agent_runs,
    export_incoming_invoices,
    export_outgoing_invoices,
)
from probe_incoming_despatches import (
    ENDPOINT_CANDIDATES,
    SWAGGER_BASE_URL,
    default_start_date,
    enrich_descriptions,
    expand_pdf_paths,
    parse_pdf_despatch_descriptions,
    try_endpoint,
    write_json_output,
)
from match_incoming_despatches_to_outgoing import generate_match_report, latest_source_json


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Geçersiz tarih: {value}. Format YYYY-MM-DD olmalı."
        ) from exc


def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print()


def summarize_forward_match(df) -> dict:
    return {
        "toplam": len(df),
        "eslesen": len(df[df["Durum"] == "Eşleşti"]),
        "bulunamayan": len(df[df["Durum"] == "Bulunamadı"]),
        "irsaliye_yok": len(df[df["Durum"] == "İrsaliye kodu yok"]),
    }


def summarize_reverse_match(df) -> dict:
    return {
        "toplam": len(df),
        "eslesen": len(df[df["Durum"] == "Eşleşti"]),
        "karsiliksiz": len(df[df["Durum"] == "Karşılıksız"]),
        "irsaliye_yok": len(df[df["Durum"] == "İrsaliye yok"]),
    }


def run_all_excel_exports(output_dir: Path, created_files: list[Path]) -> None:
    """DB'den Gelen/Giden/Agent listeleri, fabrika detayları ve müşteri fiyat raporunu üret."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("  • Gelen_Faturalar_*.xlsx")
    path_in = output_dir / f"Gelen_Faturalar_{timestamp}.xlsx"
    export_incoming_invoices(path_in)
    created_files.append(path_in)
    db.close_persistent_connection()

    print("  • Giden_Faturalar_*.xlsx")
    path_out = output_dir / f"Giden_Faturalar_{timestamp}.xlsx"
    export_outgoing_invoices(path_out)
    created_files.append(path_out)
    db.close_persistent_connection()

    print("  • Agent_Calismalari_*.xlsx")
    path_runs = output_dir / f"Agent_Calismalari_{timestamp}.xlsx"
    export_agent_runs(path_runs)
    created_files.append(path_runs)
    db.close_persistent_connection()

    print("  • AK_GIPS_Fabrikasi_*.xlsx ve FULLBOARD_Fabrikasi_*.xlsx")
    supplier_files = export_supplier_reports(output_dir)
    created_files.extend(supplier_files)
    db.close_persistent_connection()

    print("  • Musteri_Urun_Fiyatlari_*.xlsx")
    cust_file = export_customer_product_prices(output_dir)
    created_files.append(cust_file)
    db.close_persistent_connection()

    if not any(path.name.startswith("Irsaliye_Giden_Fatura_Eslestirme_") for path in created_files):
        print("  • Irsaliye_Giden_Fatura_Eslestirme_*.xlsx")
        despatch_report = generate_match_report(latest_source_json(), output_dir, print_summary=True)
        created_files.append(despatch_report)
        db.close_persistent_connection()


def run_incoming_despatch_step(args: argparse.Namespace, output_dir: Path, created_files: list[Path]) -> None:
    """Fetch incoming e-despatches and create the incoming despatch -> outgoing invoice report."""

    start_date = args.start_date.date().isoformat() if args.start_date else default_start_date()
    end_date = args.end_date.date().isoformat() if args.end_date else datetime.now().date().isoformat()
    pdf_paths = expand_pdf_paths(args.despatch_description_pdf)
    pdf_descriptions = parse_pdf_despatch_descriptions(pdf_paths) if pdf_paths else None

    client = IsbasiApiClient(base_url=args.despatch_base_url or SWAGGER_BASE_URL)
    login_state = client.login()
    diagnostics = []
    auth_variants = [
        ("raw-token", login_state.access_token),
        ("bearer-token", f"Bearer {login_state.access_token}"),
    ]

    for auth_name, authorization in auth_variants:
        client.session.headers.update({"Authorization": authorization})
        for endpoint in ENDPOINT_CANDIDATES:
            print(f"  Deniyorum: {endpoint} ({auth_name})")
            rows, info = try_endpoint(
                client,
                endpoint,
                start_date=start_date,
                end_date=end_date,
                page_size=args.despatch_page_size,
                max_pages=args.despatch_max_pages,
            )
            info["auth"] = auth_name
            diagnostics.append(info)
            if not rows:
                continue

            print("  İrsaliye açıklamaları cache/API/PDF kaynaklarından tamamlanıyor...")
            enrich_descriptions(
                client,
                rows,
                limit=0,
                refresh=args.refresh_despatch_descriptions,
                pdf_descriptions=pdf_descriptions,
            )

            json_path = write_json_output(rows, endpoint, info["date_column"])
            report_path = generate_match_report(json_path, output_dir, print_summary=True)
            created_files.append(Path(report_path))
            print(f"  Gelen e-irsaliye: {len(rows)} kayıt ({endpoint}, {auth_name})")
            print(f"  Ham JSON: {json_path}")
            print(f"  Rapor:    {report_path}")
            return

    raise RuntimeError(f"Gelen e-irsaliye endpoint'i bulunamadı. Deneme özeti: {diagnostics[-5:]}")


def run_pipeline(args: argparse.Namespace) -> list[Path]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    created_files = []

    print_header("TEK KOMUT FATURA ESLESTIRME AKISI")
    print(f"Pipeline ID: {pipeline_id}")
    print(f"Çıktı klasörü: {output_dir.resolve()}")
    if args.start_date or args.end_date:
        print(
            "Tarih aralığı: "
            f"{args.start_date.date() if args.start_date else 'agent state'}"
            f" -> {args.end_date.date() if args.end_date else 'bugün'}"
        )
    print()

    try:
        if not args.skip_ingest:
            print_header("1/3 GELEN FATURALAR CEKILIYOR")
            incoming_agent = IncomingInvoiceAgent(
                run_id=f"{pipeline_id}_incoming",
                refresh_xml_cache=args.refresh_xml,
            )
            incoming_agent.run(start_date=args.start_date, end_date=args.end_date)
            db.close_persistent_connection()

            print_header("2/3 GIDEN FATURALAR CEKILIYOR")
            outgoing_agent = OutgoingInvoiceAgent(
                run_id=f"{pipeline_id}_outgoing",
                refresh_xml_cache=args.refresh_xml,
            )
            outgoing_agent.run(start_date=args.start_date, end_date=args.end_date)
            db.close_persistent_connection()
        else:
            print_header("1-2/3 VERI CEKME ATLANDI")
            print("--skip-ingest kullanıldığı için mevcut DB verisiyle devam ediliyor.")

        print_header("3/3 ESLESTIRME EXCEL RAPORU OLUSTURULUYOR")
        match_df = get_matching_data()
        match_summary = summarize_forward_match(match_df)
        match_file = generate_excel(match_df, output_dir=output_dir)
        created_files.append(Path(match_file))

        print("Giden -> Gelen eşleştirme özeti:")
        print(f"  Toplam satır:       {match_summary['toplam']}")
        print(f"  Eşleşen:            {match_summary['eslesen']}")
        print(f"  Bulunamayan:        {match_summary['bulunamayan']}")
        print(f"  İrsaliye kodu yok:  {match_summary['irsaliye_yok']}")
        print(f"  Rapor:              {match_file}")

        if not args.skip_reverse:
            print()
            print("Ters eşleştirme raporu oluşturuluyor...")
            reverse_df = get_reverse_matching_data()
            reverse_summary = summarize_reverse_match(reverse_df)
            reverse_file = generate_reverse_excel(reverse_df, output_dir=output_dir)
            created_files.append(Path(reverse_file))

            print("Gelen -> Giden kontrol özeti:")
            print(f"  Toplam satır:  {reverse_summary['toplam']}")
            print(f"  Eşleşen:       {reverse_summary['eslesen']}")
            print(f"  Karşılıksız:   {reverse_summary['karsiliksiz']}")
            print(f"  İrsaliye yok:  {reverse_summary['irsaliye_yok']}")
            print(f"  Rapor:         {reverse_file}")

        if not args.skip_despatches and not args.skip_ingest:
            print()
            print_header("GELEN E-IRSALIYELER CEKILIYOR")
            run_incoming_despatch_step(args, output_dir, created_files)
        elif args.skip_ingest and not args.skip_despatches:
            print()
            print("Gelen e-irsaliye API çekimi --skip-ingest nedeniyle atlandı.")

        if args.all_excel:
            print_header("4/4 TUM EXCEL CIKTILARI (LISTE + FABRIKA + MUSTERI FIYAT)")
            print(
                "Gelen/Giden listeleri, Agent çalışmaları, AK GIPS & FULLBOARD, "
                "müşteri ürün fiyat raporu üretiliyor..."
            )
            print()
            run_all_excel_exports(output_dir, created_files)

        print_header("AKIS TAMAMLANDI")
        for file_path in created_files:
            print(f"✅ {file_path}")

        return created_files
    finally:
        db.close_persistent_connection()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gelen/giden faturaları çek, DB'ye aktar, eşleştir ve Excel raporu üret."
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Başlangıç tarihi (YYYY-MM-DD). Verilmezse agent state/lookback kullanılır.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Bitiş tarihi (YYYY-MM-DD). Verilmezse bugün kullanılır.",
    )
    parser.add_argument(
        "--output-dir",
        default="kayıtlar",
        help="Excel raporlarının yazılacağı klasör (varsayılan: kayıtlar).",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="API'den veri çekmeden mevcut DB verisiyle sadece eşleştirme raporu üret.",
    )
    parser.add_argument(
        "--skip-reverse",
        action="store_true",
        help="Varsayılan ters eşleştirme raporunu üretme.",
    )
    parser.add_argument(
        "--skip-despatches",
        action="store_true",
        help="Gelen e-irsaliye listesini çekip giden faturalarla eşleştirme raporunu üretme.",
    )
    parser.add_argument(
        "--despatch-description-pdf",
        action="append",
        default=["data/incoming_despatch_pdfs"],
        help=(
            "İrsaliye açıklama/plaka/sevk yeri için İşbaşı PDF export dosyası, klasörü veya glob'u. "
            "Varsayılan: data/incoming_despatch_pdfs"
        ),
    )
    parser.add_argument(
        "--refresh-despatch-descriptions",
        action="store_true",
        help="Gelen e-irsaliye açıklama cache'ini yok sayıp kaynaklardan yeniden çek.",
    )
    parser.add_argument(
        "--despatch-page-size",
        type=int,
        default=100,
        help="Gelen e-irsaliye API sayfa boyutu.",
    )
    parser.add_argument(
        "--despatch-max-pages",
        type=int,
        default=3,
        help="Gelen e-irsaliye API maksimum sayfa sayısı.",
    )
    parser.add_argument(
        "--despatch-base-url",
        default=SWAGGER_BASE_URL,
        help="Gelen e-irsaliye API base URL.",
    )
    parser.add_argument(
        "--refresh-xml",
        action="store_true",
        help="Cache olsa bile gelen ve giden fatura XML cache'ini yeniden çek.",
    )
    parser.add_argument(
        "--all-excel",
        action="store_true",
        help=(
            "Eşleştirme raporlarına ek olarak Gelen/Giden/Agent Excel'leri, "
            "AK GIPS & FULLBOARD fabrika raporları ve müşteri ürün fiyat Excel'ini üret."
        ),
    )

    args = parser.parse_args()

    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("--start-date, --end-date değerinden büyük olamaz.")

    try:
        run_pipeline(args)
    except KeyboardInterrupt:
        print("\nAkış kullanıcı tarafından durduruldu.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nAkış başarısız: {exc}")
        raise


if __name__ == "__main__":
    main()
