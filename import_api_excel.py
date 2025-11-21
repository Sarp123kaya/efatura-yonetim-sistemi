#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Excel dosyasından verileri birleşik veritabanına import eder
"""

import pandas as pd
import sqlite3
import os
from pathlib import Path

def import_api_excel_to_db():
    """API Excel dosyasından verileri birleşik DB'ye import eder"""
    
    # Proje kök dizini
    project_root = Path(__file__).resolve().parent
    
    # Excel dosyası yolu
    excel_path = project_root / "data" / "excel" / "api" / "API_Giden_Faturalar.xlsx"
    
    if not excel_path.exists():
        print(f"❌ Excel dosyası bulunamadı: {excel_path}")
        return False
    
    # Birleşik veritabanı yolu
    db_path = project_root / "data" / "db" / "birlesik.db"
    
    if not db_path.exists():
        print(f"❌ Birleşik veritabanı bulunamadı: {db_path}")
        return False
    
    print("=" * 80)
    print("API EXCEL'İNDEN VERİTABANINA IMPORT")
    print("=" * 80)
    print()
    
    # Excel'i oku
    print(f"📖 Excel dosyası okunuyor: {excel_path.name}")
    df = pd.read_excel(excel_path, sheet_name='Tum_Faturalar')
    print(f"✓ {len(df)} kayıt okundu")
    print()
    
    # Veritabanına bağlan
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Mevcut API kayıtlarını sil (yeniden import için)
    cursor.execute("DELETE FROM invoices WHERE firma_kodu = 'API'")
    deleted_count = cursor.rowcount
    print(f"🗑️  Eski {deleted_count} API kaydı silindi")
    print()
    
    # Excel'deki verileri ekle
    added_count = 0
    giden_count = 0
    gelen_count = 0
    
    print("💾 Veriler veritabanına ekleniyor...")
    
    for idx, row in df.iterrows():
        # Type'a göre supplier/customer ayır
        inv_type = row.get('type', '')
        firm_name = row.get('firmName', '')
        
        if inv_type == 'PURCHASE_INVOICE':
            supplier_name = firm_name
            customer_name = None
            gelen_count += 1
        else:
            supplier_name = None
            customer_name = firm_name
            giden_count += 1
        
        # Description'ı al (banka bilgileri zaten temizlenmiş)
        description = row.get('description', '')
        if pd.isna(description):
            description = None
        
        # Date formatını kontrol et
        date_val = row.get('date', '')
        if pd.isna(date_val):
            date_val = None
        else:
            date_val = str(date_val)
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO invoices (
                    firma_kodu, source_file, parse_date, invoice_id, uuid, invoice_number,
                    issue_date, total_amount, currency, taxable_amount, tax_amount,
                    supplier_name, supplier_vkn, customer_name, customer_vkn, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'API',
                'API',
                date_val,
                str(row.get('id', '')),
                None,  # uuid
                row.get('invoiceNumber', ''),
                date_val,
                float(row.get('totalTL', 0)) if not pd.isna(row.get('totalTL')) else 0,
                'TRY',
                float(row.get('taxableAmount', 0)) if not pd.isna(row.get('taxableAmount')) else 0,
                None,  # tax_amount
                supplier_name,
                None,  # supplier_vkn
                customer_name,
                None,  # customer_vkn
                description
            ))
            
            if cursor.rowcount > 0:
                added_count += 1
        except Exception as e:
            print(f"⚠️  Satır {idx+1} eklenirken hata: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"✓ {added_count} API faturası birleşik DB'ye eklendi")
    print(f"   🟢 Giden: {giden_count}")
    print(f"   🔴 Gelen: {gelen_count}")
    print()
    
    # Kontrol
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'API'")
    final_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE firma_kodu = 'API'")
    total_amount = cursor.fetchone()[0] or 0
    
    conn.close()
    
    print("=" * 80)
    print("✅ IMPORT TAMAMLANDI")
    print("=" * 80)
    print(f"📊 Birleşik DB'deki API Fatura Sayısı: {final_count}")
    print(f"💰 Toplam Tutar: {total_amount:,.2f} TRY")
    print()
    
    return True

if __name__ == '__main__':
    import_api_excel_to_db()

