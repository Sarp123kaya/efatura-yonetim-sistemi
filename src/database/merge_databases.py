#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Üç Veritabanını Birleştirme Script
- AK GİPS verileri: A- prefix (XML)
- FULLBOARD verileri: F- prefix (XML)
- API verileri: API prefix (İşbaşı API)
"""

import sqlite3
import os

def create_merged_database():
    """Birleşik veritabanı şemasını oluşturur"""
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    
    conn = sqlite3.connect('data/db/birlesik.db')
    cursor = conn.cursor()
    
    # Ana fatura tablosu (firma_kodu eklendi)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_kodu TEXT NOT NULL,
            source_file TEXT NOT NULL,
            parse_date TEXT NOT NULL,
            invoice_id TEXT,
            uuid TEXT,
            invoice_number TEXT,
            issue_date TEXT,
            total_amount REAL,
            currency TEXT,
            taxable_amount REAL,
            tax_amount REAL,
            supplier_name TEXT,
            supplier_vkn TEXT,
            customer_name TEXT,
            customer_vkn TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Attachment tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            filename TEXT,
            mime_type TEXT,
            encoding TEXT,
            charset TEXT,
            data_base64 TEXT,
            decoded_size INTEGER,
            decoded_preview TEXT,
            decode_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    # Fatura satırları tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            line_id TEXT,
            item_name TEXT,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            line_total REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    # UNIQUE INDEX ekle - aynı faturanın aynı satırı tekrar edilemez
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_invoice_line 
        ON invoice_lines(invoice_id, line_id)
    ''')
    
    # İrsaliye tablosu (firma_kodu prefix'li)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS despatch_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            despatch_id_full TEXT NOT NULL,
            despatch_id_short TEXT NOT NULL,
            issue_date TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    # UNIQUE INDEX ekle - aynı firma_kodu + invoice_number kombinasyonu tekrar edilemez
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_invoice 
        ON invoices(firma_kodu, invoice_number)
    ''')
    
    conn.commit()
    return conn

def merge_databases():
    """İki veritabanını birleştirir"""
    
    print("=" * 80)
    print("VERİTABANLARI BİRLEŞTİRME")
    print("=" * 80)
    print()
    
    # Birleşik veritabanını oluştur
    if os.path.exists('efatura_birlesik.db'):
        os.remove('efatura_birlesik.db')
        print("✓ Eski birleşik veritabanı silindi")
    
    merged_conn = create_merged_database()
    merged_cursor = merged_conn.cursor()
    print("✓ Birleşik veritabanı şeması oluşturuldu")
    print()
    
    # ========== AK GİPS VERİLERİ ==========
    print("📊 AK GİPS verileri aktarılıyor...")
    
    if os.path.exists('data/db/akgips.db'):
        ak_conn = sqlite3.connect('data/db/akgips.db')
        ak_cursor = ak_conn.cursor()
        
        # Faturaları kopyala
        ak_cursor.execute('SELECT * FROM invoices')
        invoices = ak_cursor.fetchall()
        
        invoice_id_map = {}  # Eski ID -> Yeni ID mapping
        
        for old_invoice in invoices:
            # Description alanını çek (15. sütun, index 15)
            description = old_invoice[15] if len(old_invoice) > 15 else None
            
            merged_cursor.execute('''
                INSERT OR IGNORE INTO invoices (
                    firma_kodu, source_file, parse_date, invoice_id, uuid, invoice_number,
                    issue_date, total_amount, currency, taxable_amount, tax_amount,
                    supplier_name, supplier_vkn, customer_name, customer_vkn, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('A', old_invoice[1], old_invoice[2], old_invoice[3], old_invoice[4],
                  old_invoice[5], old_invoice[6], old_invoice[7], old_invoice[8],
                  old_invoice[9], old_invoice[10], old_invoice[11], old_invoice[12],
                  old_invoice[13], old_invoice[14], description))
            
            new_id = merged_cursor.lastrowid
            
            # Eğer INSERT IGNORE ile atlandıysa (lastrowid = 0), mevcut kaydın ID'sini bul
            if new_id == 0:
                merged_cursor.execute('''
                    SELECT id FROM invoices WHERE firma_kodu = ? AND invoice_number = ?
                ''', ('A', old_invoice[5]))
                result = merged_cursor.fetchone()
                if result:
                    new_id = result[0]
            
            invoice_id_map[old_invoice[0]] = new_id
        
        # Attachments kopyala
        ak_cursor.execute('SELECT * FROM attachments')
        for att in ak_cursor.fetchall():
            merged_cursor.execute('''
                INSERT INTO attachments (
                    invoice_id, filename, mime_type, encoding, charset,
                    data_base64, decoded_size, decoded_preview, decode_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id_map[att[1]], att[2], att[3], att[4], att[5],
                  att[6], att[7], att[8], att[9]))
        
        # Fatura satırlarını kopyala
        ak_cursor.execute('SELECT * FROM invoice_lines')
        for line in ak_cursor.fetchall():
            merged_cursor.execute('''
                INSERT OR IGNORE INTO invoice_lines (
                    invoice_id, line_id, item_name, quantity, unit,
                    unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id_map[line[1]], line[2], line[3], line[4],
                  line[5], line[6], line[7]))
        
        # İrsaliyeleri kopyala (parser zaten A- prefix ekliyor)
        ak_cursor.execute('SELECT * FROM despatch_documents')
        for desp in ak_cursor.fetchall():
            # Parser zaten A- prefix ekliyor, olduğu gibi kopyala
            short_id = desp[3]  # Zaten A-14740 formatında
            full_id = desp[2]   # IRS2025000014740
            
            merged_cursor.execute('''
                INSERT INTO despatch_documents (
                    invoice_id, despatch_id_full, despatch_id_short,
                    issue_date, description
                ) VALUES (?, ?, ?, ?, ?)
            ''', (invoice_id_map[desp[1]], full_id, short_id, desp[4], desp[5]))
        
        ak_conn.close()
        print(f"  ✓ {len(invoices)} AK GİPS faturası eklendi (A- prefix)")
    else:
        print("  ⚠️  efatura.db bulunamadı!")
    
    print()
    
    # ========== FULLBOARD VERİLERİ ==========
    print("📊 FULLBOARD verileri aktarılıyor...")
    
    fullboard_db_path = 'data/db/fullboard.db'
    if os.path.exists(fullboard_db_path):
        fb_conn = sqlite3.connect(fullboard_db_path)
        fb_cursor = fb_conn.cursor()
        
        # Faturaları kopyala
        fb_cursor.execute('SELECT * FROM invoices')
        invoices = fb_cursor.fetchall()
        
        invoice_id_map = {}
        
        for old_invoice in invoices:
            # Description alanını çek (15. sütun, index 15)
            description = old_invoice[15] if len(old_invoice) > 15 else None
            
            merged_cursor.execute('''
                INSERT OR IGNORE INTO invoices (
                    firma_kodu, source_file, parse_date, invoice_id, uuid, invoice_number,
                    issue_date, total_amount, currency, taxable_amount, tax_amount,
                    supplier_name, supplier_vkn, customer_name, customer_vkn, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('F', old_invoice[1], old_invoice[2], old_invoice[3], old_invoice[4],
                  old_invoice[5], old_invoice[6], old_invoice[7], old_invoice[8],
                  old_invoice[9], old_invoice[10], old_invoice[11], old_invoice[12],
                  old_invoice[13], old_invoice[14], description))
            
            new_id = merged_cursor.lastrowid
            
            # Eğer INSERT IGNORE ile atlandıysa (lastrowid = 0), mevcut kaydın ID'sini bul
            if new_id == 0:
                merged_cursor.execute('''
                    SELECT id FROM invoices WHERE firma_kodu = ? AND invoice_number = ?
                ''', ('F', old_invoice[5]))
                result = merged_cursor.fetchone()
                if result:
                    new_id = result[0]
            
            invoice_id_map[old_invoice[0]] = new_id
        
        # Attachments kopyala
        fb_cursor.execute('SELECT * FROM attachments')
        for att in fb_cursor.fetchall():
            merged_cursor.execute('''
                INSERT INTO attachments (
                    invoice_id, filename, mime_type, encoding, charset,
                    data_base64, decoded_size, decoded_preview, decode_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id_map[att[1]], att[2], att[3], att[4], att[5],
                  att[6], att[7], att[8], att[9]))
        
        # Fatura satırlarını kopyala
        fb_cursor.execute('SELECT * FROM invoice_lines')
        for line in fb_cursor.fetchall():
            merged_cursor.execute('''
                INSERT OR IGNORE INTO invoice_lines (
                    invoice_id, line_id, item_name, quantity, unit,
                    unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id_map[line[1]], line[2], line[3], line[4],
                  line[5], line[6], line[7]))
        
        # İrsaliyeleri kopyala (parser zaten F- prefix ekliyor)
        fb_cursor.execute('SELECT * FROM despatch_documents')
        for desp in fb_cursor.fetchall():
            # Parser zaten F- prefix ekliyor, olduğu gibi kopyala
            short_id = desp[3]  # Zaten F-07904 formatında
            full_id = desp[2]   # IRS2025000007904
            
            merged_cursor.execute('''
                INSERT INTO despatch_documents (
                    invoice_id, despatch_id_full, despatch_id_short,
                    issue_date, description
                ) VALUES (?, ?, ?, ?, ?)
            ''', (invoice_id_map[desp[1]], full_id, short_id, desp[4], desp[5]))
        
        fb_conn.close()
        print(f"  ✓ {len(invoices)} FULLBOARD faturası eklendi (F- prefix)")
    else:
        print(f"  ⚠️  {fullboard_db_path} bulunamadı!")
    
    # ========== API VERİLERİ ==========
    print("📊 API verileri aktarılıyor...")
    
    api_db_path = 'data/db/api.db'
    if os.path.exists(api_db_path):
        api_conn = sqlite3.connect(api_db_path)
        api_cursor = api_conn.cursor()
        
        # API invoices tablosunu kontrol et
        api_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'")
        if api_cursor.fetchone():
            # API faturalarını al
            api_cursor.execute('SELECT * FROM invoices')
            api_invoices = api_cursor.fetchall()
            
            invoice_id_map = {}
            
            for inv in api_invoices:
                # API veritabanı sütun sırası:
                # id, api_id, source, parse_date, invoice_number, invoice_type, issue_date, 
                # total_amount, currency, taxable_amount, firm_name, firm_vkn, description, raw_json, created_at
                
                api_id = inv[1]
                invoice_number = inv[4]
                invoice_type = inv[5]
                issue_date = inv[6]
                total_amount = inv[7]
                taxable_amount = inv[9]
                firm_name = inv[10]
                firm_vkn = inv[11]
                description = inv[12]
                
                # Gelen fatura ise supplier, giden fatura ise customer
                if invoice_type == 'PURCHASE_INVOICE':
                    supplier_name = firm_name
                    customer_name = None
                else:
                    supplier_name = None
                    customer_name = firm_name
                
                merged_cursor.execute('''
                    INSERT OR IGNORE INTO invoices (
                        firma_kodu, source_file, parse_date, invoice_id, uuid, invoice_number,
                        issue_date, total_amount, currency, taxable_amount, tax_amount,
                        supplier_name, supplier_vkn, customer_name, customer_vkn, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'API',
                    'API',
                    issue_date,
                    api_id,
                    None,  # uuid
                    invoice_number,
                    issue_date,
                    total_amount,
                    'TRY',
                    taxable_amount,
                    None,  # tax_amount
                    supplier_name,
                    firm_vkn,
                    customer_name,
                    None,  # customer_vkn
                    description
                ))
                
                new_id = merged_cursor.lastrowid
                
                # Eğer INSERT IGNORE ile atlandıysa (lastrowid = 0), mevcut kaydın ID'sini bul
                if new_id == 0:
                    merged_cursor.execute('''
                        SELECT id FROM invoices WHERE firma_kodu = ? AND invoice_number = ?
                    ''', ('API', invoice_number))
                    result = merged_cursor.fetchone()
                    if result:
                        new_id = result[0]
                
                invoice_id_map[inv[0]] = new_id
            
            # İrsaliye referanslarını kopyala
            api_cursor.execute('SELECT * FROM despatch_references')
            for desp_ref in api_cursor.fetchall():
                # desp_ref: id, invoice_id, irsaliye_no, created_at
                old_invoice_id = desp_ref[1]
                irsaliye_no = desp_ref[2]
                
                if old_invoice_id in invoice_id_map:
                    new_invoice_id = invoice_id_map[old_invoice_id]
                    
                    # İrsaliye numarasını despatch_documents tablosuna ekle
                    # API prefix ile ekle
                    merged_cursor.execute('''
                        INSERT INTO despatch_documents (
                            invoice_id, despatch_id_full, despatch_id_short,
                            issue_date, description
                        ) VALUES (?, ?, ?, ?, ?)
                    ''', (new_invoice_id, irsaliye_no, f'API-{irsaliye_no}', None, None))
            
            api_conn.close()
            print(f"  ✓ {len(api_invoices)} API faturası eklendi (API prefix)")
        else:
            print("  ⚠️  API veritabanında 'invoices' tablosu bulunamadı")
    else:
        print(f"  ⚠️  {api_db_path} bulunamadı (API verileri henüz çekilmemiş)")
    
    merged_conn.commit()
    merged_conn.close()
    
    print()
    print("=" * 80)
    print("BİRLEŞTİRME TAMAMLANDI")
    print("=" * 80)
    print()
    
    # Özet
    conn = sqlite3.connect('data/db/birlesik.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'A'")
    ak_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'F'")
    fb_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'API'")
    api_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM despatch_documents")
    desp_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM invoice_lines")
    line_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE firma_kodu = 'A'")
    ak_total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE firma_kodu = 'F'")
    fb_total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE firma_kodu = 'API'")
    api_total = cursor.fetchone()[0] or 0
    
    print("📊 Birleşik Veritabanı İstatistikleri:")
    print(f"  • AK GİPS Faturaları (A-): {ak_count} adet - {ak_total:,.2f} TRY")
    print(f"  • FULLBOARD Faturaları (F-): {fb_count} adet - {fb_total:,.2f} TRY")
    print(f"  • API Faturaları (API): {api_count} adet - {api_total:,.2f} TRY")
    print(f"  • Toplam Fatura: {ak_count + fb_count + api_count} adet")
    print(f"  • Toplam İrsaliye: {desp_count} adet")
    print(f"  • Toplam Satır: {line_count} adet")
    print(f"  • Genel Toplam: {ak_total + fb_total + api_total:,.2f} TRY")
    print()
    print("✓ Birleşik veritabanı: data/db/birlesik.db")
    
    conn.close()

if __name__ == '__main__':
    merge_databases()

