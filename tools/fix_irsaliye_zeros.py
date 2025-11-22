#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İrsaliye Numaralarındaki Başındaki 0'ları Kaldırma Scripti
===========================================================

Veritabanlarındaki irsaliye numaralarının başındaki 0'ları kaldırır.
Örnek: F-07128 -> F-7128, A-01234 -> A-1234

Kullanım:
    python3 tools/fix_irsaliye_zeros.py
"""

import sqlite3
from pathlib import Path
import re


def fix_irsaliye_numbers(db_path: Path, firma_prefix: str):
    """
    Veritabanındaki irsaliye numaralarının başındaki 0'ları kaldırır
    
    Args:
        db_path: Veritabanı dosya yolu
        firma_prefix: Firma prefix'i (A veya F)
    """
    if not db_path.exists():
        print(f"⚠️  Veritabanı bulunamadı: {db_path}")
        return
    
    print(f"\n📊 İşleniyor: {db_path.name}")
    print("=" * 80)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Mevcut irsaliye numaralarını al
    cursor.execute("SELECT id, despatch_id_short FROM despatch_documents")
    rows = cursor.fetchall()
    
    updated_count = 0
    
    for row_id, despatch_id_short in rows:
        # Pattern: F-07128 veya A-01234
        match = re.match(r'([AF])-(\d+)', despatch_id_short)
        
        if match:
            prefix = match.group(1)
            number = match.group(2)
            
            # Başındaki 0'ları kaldır
            new_number = number.lstrip('0') or '0'
            new_despatch_id = f"{prefix}-{new_number}"
            
            # Eğer değişiklik varsa güncelle
            if new_despatch_id != despatch_id_short:
                cursor.execute(
                    "UPDATE despatch_documents SET despatch_id_short = ? WHERE id = ?",
                    (new_despatch_id, row_id)
                )
                print(f"  {despatch_id_short} → {new_despatch_id}")
                updated_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ {updated_count} irsaliye numarası güncellendi")
    
    return updated_count


def main():
    """Ana fonksiyon"""
    print("=" * 80)
    print("🔧 İRSALİYE NUMARASI DÜZELTİCİ")
    print("=" * 80)
    print("Başındaki 0'ları kaldırır: F-07128 → F-7128")
    print()
    
    # Proje kök dizini
    project_root = Path(__file__).resolve().parent.parent
    
    # Veritabanı yolları
    akgips_db = project_root / "data" / "db" / "akgips.db"
    fullboard_db = project_root / "data" / "db" / "fullboard.db"
    
    total_updated = 0
    
    # AK GİPS veritabanını düzelt
    if akgips_db.exists():
        count = fix_irsaliye_numbers(akgips_db, 'A')
        total_updated += count
    
    # FULLBOARD veritabanını düzelt
    if fullboard_db.exists():
        count = fix_irsaliye_numbers(fullboard_db, 'F')
        total_updated += count
    
    print()
    print("=" * 80)
    print(f"✅ İŞLEM TAMAMLANDI - Toplam {total_updated} güncelleme")
    print("=" * 80)
    print()
    print("📝 Sonraki adımlar:")
    print("  1. Excel dosyalarını yeniden oluştur:")
    print("     python3 src/exporters/akgips_exporter.py")
    print("     python3 src/exporters/fullboard_exporter.py")
    print()
    print("  2. Eşleştirme raporunu yeniden çalıştır:")
    print("     python3 tools/invoice_matcher.py")
    print()


if __name__ == '__main__':
    main()

