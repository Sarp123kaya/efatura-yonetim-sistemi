#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İrsaliye Kodu Manuel Düzeltme
Fatura açıklamasında yanlış girilen irsaliye kodlarını kalıcı olarak düzeltir.
"""
import sys
import json
import re
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.db import db


def normalize_code(code: str) -> str:
    """A-64 -> A-00064, F-956 -> F-00956"""
    m = re.match(r'^([AFT])-?(\d+)$', code.strip(), re.IGNORECASE)
    if not m:
        return code
    prefix = m.group(1).upper()
    digits = m.group(2).zfill(5)
    return f"{prefix}-{digits}"


def find_invoice(invoice_ref: str):
    """Find invoice by id or invoice_no"""
    invoice_ref = invoice_ref.strip()
    row = db.query_one(
        "SELECT id, invoice_no, firm_name, irsaliye_codes, irsaliye_codes_override, description "
        "FROM outgoing_invoices WHERE id = %s OR invoice_no = %s",
        (invoice_ref, invoice_ref)
    )
    return row


def cmd_show(invoice_ref: str):
    row = find_invoice(invoice_ref)
    if not row:
        print(f"Fatura bulunamadı: {invoice_ref}")
        return 1

    override = row.get('irsaliye_codes_override')
    extracted = row.get('irsaliye_codes')
    if isinstance(extracted, str):
        extracted = json.loads(extracted) if extracted else []
    if isinstance(override, str):
        override = json.loads(override) if override else None

    effective = override if override else extracted

    print(f"\nFatura: {row['invoice_no']} ({row['firm_name'][:40]}...)")
    print(f"  Açıklama:   {str(row.get('description') or '')[:60]}...")
    print(f"  Extracted:  {extracted}")
    print(f"  Override:   {override if override else '(yok)'}")
    print(f"  Kullanılan: {effective}")
    print()
    return 0


def cmd_clear(invoice_ref: str):
    row = find_invoice(invoice_ref)
    if not row:
        print(f"Fatura bulunamadı: {invoice_ref}")
        return 1

    db.execute(
        "UPDATE outgoing_invoices SET irsaliye_codes_override = NULL WHERE id = %s",
        (row['id'],)
    )
    print(f"Override kaldırıldı: {row['invoice_no']} -> extracted kullanılacak")
    return 0


def cmd_correct(invoice_ref: str, from_code: str, to_code: str):
    row = find_invoice(invoice_ref)
    if not row:
        print(f"Fatura bulunamadı: {invoice_ref}")
        return 1

    from_norm = normalize_code(from_code)
    to_norm = normalize_code(to_code)

    extracted = row.get('irsaliye_codes')
    if isinstance(extracted, str):
        extracted = json.loads(extracted) if extracted else []
    override = row.get('irsaliye_codes_override')
    if isinstance(override, str):
        override = json.loads(override) if override else []

    base_codes = override if override else extracted
    if from_norm not in base_codes:
        print(f"Uyarı: '{from_norm}' mevcut kodlarda yok: {base_codes}")
        print("Yine de düzeltme uygulanıyor (tüm kodları değiştiriyorsanız --from'u atlayabilirsiniz)")

    new_codes = [to_norm if c == from_norm else c for c in base_codes]
    if from_norm not in base_codes and not base_codes:
        new_codes = [to_norm]

    db.execute(
        "UPDATE outgoing_invoices SET irsaliye_codes_override = %s WHERE id = %s",
        (json.dumps(new_codes), row['id'])
    )
    print(f"Düzeltme uygulandı: {row['invoice_no']}")
    print(f"  {from_norm} -> {to_norm}")
    print(f"  Override: {new_codes}")
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
