#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İrsaliye Raporu Oluşturma Script
"""

import sqlite3
import os

def generate_report():
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    # Veritabanı yolunu belirle
    db_path = 'data/db/birlesik.db'
    if not os.path.exists(db_path):
        db_path = 'data/db/akgips.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 80)
    print(" " * 25 + "İRSALİYE RAPORU")
    print("=" * 80)
    print()
    
    # Genel özet
    cursor.execute("SELECT COUNT(*) FROM invoices")
    invoice_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM despatch_documents")
    despatch_count = cursor.fetchone()[0]
    
    print(f"📊 GENEL ÖZET")
    print(f"   Toplam Fatura: {invoice_count}")
    print(f"   Toplam İrsaliye: {despatch_count}")
    print(f"   Ortalama İrsaliye/Fatura: {despatch_count/invoice_count:.1f}")
    print()
    
    # Fatura bazında irsaliye dağılımı
    print("=" * 80)
    print("📋 FATURA BAZINDA İRSALİYE DAĞILIMI")
    print("=" * 80)
    print()
    
    cursor.execute('''
        SELECT 
            i.invoice_number,
            i.issue_date,
            i.total_amount,
            COUNT(d.id) as despatch_count
        FROM invoices i
        LEFT JOIN despatch_documents d ON i.id = d.invoice_id
        GROUP BY i.id
        ORDER BY i.issue_date DESC
    ''')
    
    for row in cursor.fetchall():
        print(f"Fatura: {row[0]}")
        print(f"   Tarih: {row[1]}")
        print(f"   Tutar: {row[2]:,.2f} TRY")
        print(f"   İrsaliye Sayısı: {row[3]}")
        print()
    
    # İrsaliye detayları
    print("=" * 80)
    print("📦 İRSALİYE DETAYLARI")
    print("=" * 80)
    print()
    
    cursor.execute('''
        SELECT 
            i.invoice_number,
            d.despatch_id_short,
            d.despatch_id_full,
            d.issue_date
        FROM despatch_documents d
        JOIN invoices i ON d.invoice_id = i.id
        ORDER BY i.invoice_number, d.despatch_id_short
    ''')
    
    current_invoice = None
    for row in cursor.fetchall():
        if current_invoice != row[0]:
            if current_invoice is not None:
                print()
            current_invoice = row[0]
            print(f"📄 {current_invoice}:")
        
        print(f"   • {row[1]} (Tam: {row[2]}) - Tarih: {row[3]}")
    
    print()
    print("=" * 80)
    print(" " * 30 + "RAPOR SONU")
    print("=" * 80)
    
    conn.close()

if __name__ == '__main__':
    generate_report()

