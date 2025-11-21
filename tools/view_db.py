#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Veritabanı İçeriğini Görüntüleme Script
"""

import sqlite3
import os

def view_database():
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    # Veritabanı yolunu belirle
    db_path = 'data/db/birlesik.db'
    if not os.path.exists(db_path):
        db_path = 'data/db/akgips.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 100)
    print("VERİTABANI İÇERİĞİ - FATURALAR")
    print("=" * 100)
    
    cursor.execute('SELECT * FROM invoices')
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"\n📄 Fatura ID: {row[0]}")
        print(f"   Kaynak Dosya: {row[1]}")
        print(f"   Fatura No: {row[5]}")
        print(f"   UUID: {row[4]}")
        print(f"   Tarih: {row[6]}")
        print(f"   Toplam: {row[7]:.2f} {row[8]}")
        print(f"   Vergi Matrahı: {row[9]:.2f}" if row[9] else "")
        print(f"   Vergi Tutarı: {row[10]:.2f}" if row[10] else "")
        print(f"   Satıcı: {row[11]} (VKN: {row[12]})")
        print(f"   Müşteri: {row[13]} (VKN: {row[14]})")
    
    print("\n")
    print("=" * 100)
    print("ATTACHMENTS")
    print("=" * 100)
    
    cursor.execute('SELECT * FROM attachments')
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"\n📎 Attachment ID: {row[0]}")
        print(f"   Bağlı Fatura ID: {row[1]}")
        print(f"   Dosya Adı: {row[2]}")
        print(f"   MIME Tipi: {row[3]}")
        print(f"   Encoding: {row[4]}")
        print(f"   Charset: {row[5]}")
        print(f"   Decode Edilen Boyut: {row[7]} bytes" if row[7] else "")
        if row[8]:
            print(f"   Önizleme: {row[8][:150]}...")
        if row[9]:
            print(f"   ⚠️  Decode Hatası: {row[9]}")
    
    print("\n")
    print("=" * 100)
    print("FATURA SATIRLARI (Özet)")
    print("=" * 100)
    
    cursor.execute('''
        SELECT 
            i.invoice_number,
            COUNT(il.id) as line_count,
            SUM(il.line_total) as total
        FROM invoices i
        LEFT JOIN invoice_lines il ON i.id = il.invoice_id
        GROUP BY i.id
    ''')
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"\n📋 Fatura: {row[0]}")
        print(f"   Satır Sayısı: {row[1]}")
        print(f"   Toplam Tutar: {row[2]:.2f} TRY" if row[2] else "   Toplam Tutar: 0.00 TRY")
    
    # İrsaliye bilgileri
    print("\n")
    print("=" * 100)
    print("İRSALİYELER")
    print("=" * 100)
    
    cursor.execute('''
        SELECT 
            i.invoice_number,
            d.despatch_id_short,
            d.despatch_id_full,
            d.issue_date,
            d.description
        FROM despatch_documents d
        JOIN invoices i ON d.invoice_id = i.id
        ORDER BY i.invoice_number, d.despatch_id_short
    ''')
    rows = cursor.fetchall()
    
    current_invoice = None
    for row in rows:
        if current_invoice != row[0]:
            current_invoice = row[0]
            print(f"\n📄 Fatura: {current_invoice}")
        
        print(f"   📦 {row[1]} (Tam: {row[2]})")
        print(f"      Tarih: {row[3]}")
        if row[4]:
            desc_preview = row[4][:100] + "..." if len(row[4]) > 100 else row[4]
            print(f"      Açıklama: {desc_preview}")
    
    # Detaylı satır bilgileri
    print("\n")
    print("=" * 100)
    print("FATURA SATIRLARI (Detay)")
    print("=" * 100)
    
    cursor.execute('''
        SELECT 
            il.*,
            i.invoice_number
        FROM invoice_lines il
        JOIN invoices i ON il.invoice_id = i.id
        ORDER BY il.invoice_id, il.line_id
    ''')
    rows = cursor.fetchall()
    
    current_invoice = None
    for row in rows:
        if current_invoice != row[9]:
            current_invoice = row[9]
            print(f"\n📄 Fatura: {current_invoice}")
        
        print(f"   Satır {row[2]}: {row[3]}")
        print(f"      Miktar: {row[4]} {row[5]}")
        print(f"      Birim Fiyat: {row[6]:.2f} TRY" if row[6] else "")
        print(f"      Toplam: {row[7]:.2f} TRY" if row[7] else "")
    
    conn.close()
    
    print("\n" + "=" * 100)
    print("VERİTABANI GÖRÜNTÜLEME TAMAMLANDI")
    print("=" * 100)

if __name__ == '__main__':
    view_database()

