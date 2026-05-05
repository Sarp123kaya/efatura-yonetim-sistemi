#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tek komut fatura akışı:
1. Gelen faturaları API'den çekip PostgreSQL'e yazar.
2. Giden faturaları API'den çekip PostgreSQL'e yazar.
3. PostgreSQL verisi üzerinden eşleştirme Excel raporu üretir.
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
            outgoing_agent = OutgoingInvoiceAgent(run_id=f"{pipeline_id}_outgoing")
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
        "--refresh-xml",
        action="store_true",
        help="Cache olsa bile gelen fatura XML içeriklerini yeniden çek.",
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
