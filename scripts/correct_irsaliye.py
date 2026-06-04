#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İrsaliye Kodu Manuel Düzeltme
Fatura açıklamasında yanlış girilen irsaliye kodlarını kalıcı olarak düzeltir.
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.irsaliye_override import (
    apply_correction,
    clear_override,
    find_invoice,
    invoice_code_state,
)


def cmd_show(invoice_ref: str):
    row = find_invoice(invoice_ref)
    if not row:
        print(f"Fatura bulunamadı: {invoice_ref}")
        return 1

    state = invoice_code_state(row)

    print(f"\nFatura: {row['invoice_no']} ({row['firm_name'][:40]}...)")
    print(f"  Açıklama:   {str(row.get('description') or '')[:60]}...")
    print(f"  Extracted:  {state['extracted']}")
    print(f"  Override:   {state['override'] if state['override'] else '(yok)'}")
    print(f"  Kullanılan: {state['effective']}")
    print()
    return 0


def cmd_clear(invoice_ref: str):
    result = clear_override(invoice_ref)
    if not result.get("ok"):
        print(result.get("error", "Override kaldırılamadı."))
        return 1
    print(f"Override kaldırıldı: {result['invoice_no']} -> extracted kullanılacak")
    return 0


def cmd_correct(invoice_ref: str, from_code: str, to_code: str):
    result = apply_correction(invoice_ref, from_code, to_code)
    if not result.get("ok"):
        print(result.get("error", "Düzeltme uygulanamadı."))
        return 1
    if result.get("warning"):
        print(f"Uyarı: {result['warning']}")
    print(f"Düzeltme uygulandı: {result['invoice_no']}")
    print(f"  {result['from_code']} -> {result['to_code']}")
    print(f"  Override: {result['override']}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='İrsaliye kodu manuel düzeltme (kalıcı override)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python scripts/correct_irsaliye.py --invoice DKE2026000000005 --from A-00064 --to F-00064
  python scripts/correct_irsaliye.py --invoice DKE2026000000005 --clear
  python scripts/correct_irsaliye.py --invoice DKE2026000000005 --show
        """
    )
    parser.add_argument('--invoice', '-i', required=True, help='Fatura no veya id')
    parser.add_argument('--from', '-f', dest='from_code', help='Yanlış kod (A-00064)')
    parser.add_argument('--to', '-t', dest='to_code', help='Doğru kod (F-00064)')
    parser.add_argument('--clear', '-c', action='store_true', help="Override'ı kaldır")
    parser.add_argument('--show', '-s', action='store_true', help='Mevcut durumu göster')

    args = parser.parse_args()

    if args.show:
        return cmd_show(args.invoice)
    if args.clear:
        return cmd_clear(args.invoice)
    if args.from_code and args.to_code:
        return cmd_correct(args.invoice, args.from_code, args.to_code)

    parser.print_help()
    print("\nHata: --show, --clear veya (--from + --to) belirtin.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
