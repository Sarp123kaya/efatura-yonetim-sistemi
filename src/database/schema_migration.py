#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Schema Migration Script
=================================

Mevcut veritabanını yeni finansal takip sistemine uygun hale getirir.

Yapılan Değişiklikler:
1. invoices tablosuna yeni sütunlar ekler (invoice_type, payment_status, vb.)
2. Yeni tablolar oluşturur (payment_records, irs_matching, balance_snapshots, line_matching)
3. Performance için index'ler ekler
4. Mevcut verileri günceller (invoice_type ataması)
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime


class DatabaseMigration:
    """Veritabanı migration işlemlerini yöneten sınıf"""
    
    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Veritabanı dosya yolu (None ise birlesik.db kullanılır)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / "data" / "db" / "birlesik.db"
        
        self.db_path = str(db_path)
        self.backup_path = None
        
    def create_backup(self) -> bool:
        """Mevcut veritabanının yedeğini al"""
        try:
            if not os.path.exists(self.db_path):
                print(f"⚠️  Veritabanı bulunamadı: {self.db_path}")
                return False
            
            # Backup dosya adı: birlesik_backup_YYYYMMDD_HHMMSS.db
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = Path(self.db_path).parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            self.backup_path = backup_dir / f"birlesik_backup_{timestamp}.db"
            
            # SQLite veritabanını kopyala
            import shutil
            shutil.copy2(self.db_path, self.backup_path)
            
            print(f"✅ Backup oluşturuldu: {self.backup_path}")
            return True
            
        except Exception as e:
            print(f"❌ Backup hatası: {e}")
            return False
    
    def check_column_exists(self, cursor, table: str, column: str) -> bool:
        """Tabloda sütunun var olup olmadığını kontrol et"""
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        return column in columns
    
    def check_table_exists(self, cursor, table: str) -> bool:
        """Tablonun var olup olmadığını kontrol et"""
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (table,))
        return cursor.fetchone() is not None
    
    def add_columns_to_invoices(self, cursor) -> int:
        """invoices tablosuna yeni sütunlar ekle"""
        print("\n📊 invoices tablosuna yeni sütunlar ekleniyor...")
        
        new_columns = [
            ("invoice_type", "TEXT"),  # PURCHASE (alış) veya SALES (satış)
            ("payment_status", "TEXT DEFAULT 'UNPAID'"),  # PAID, PARTIAL, UNPAID
            ("payment_due_date", "TEXT"),  # Vade tarihi
            ("paid_amount", "REAL DEFAULT 0"),  # Ödenen miktar
            ("remaining_amount", "REAL"),  # Kalan borç/alacak
        ]
        
        added_count = 0
        for column_name, column_type in new_columns:
            if not self.check_column_exists(cursor, 'invoices', column_name):
                try:
                    cursor.execute(f"""
                        ALTER TABLE invoices ADD COLUMN {column_name} {column_type}
                    """)
                    print(f"  ✅ Eklendi: {column_name}")
                    added_count += 1
                except Exception as e:
                    print(f"  ⚠️  {column_name} eklenemedi: {e}")
            else:
                print(f"  ⏭️  Zaten var: {column_name}")
        
        return added_count
    
    def create_payment_records_table(self, cursor) -> bool:
        """Ödeme kayıtları tablosunu oluştur"""
        if self.check_table_exists(cursor, 'payment_records'):
            print("  ⏭️  payment_records tablosu zaten var")
            return False
        
        cursor.execute("""
            CREATE TABLE payment_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT,
                reference_number TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            )
        """)
        print("  ✅ payment_records tablosu oluşturuldu")
        return True
    
    def create_irs_matching_table(self, cursor) -> bool:
        """İrsaliye eşleştirme tablosunu oluştur"""
        if self.check_table_exists(cursor, 'irs_matching'):
            print("  ⏭️  irs_matching tablosu zaten var")
            return False
        
        cursor.execute("""
            CREATE TABLE irs_matching (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                irs_number TEXT NOT NULL,
                purchase_invoice_id INTEGER,
                sales_invoice_id INTEGER,
                purchase_amount REAL,
                sales_amount REAL,
                profit_loss REAL,
                profit_margin REAL,
                matched_date TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'MATCHED',
                notes TEXT,
                FOREIGN KEY (purchase_invoice_id) REFERENCES invoices (id),
                FOREIGN KEY (sales_invoice_id) REFERENCES invoices (id)
            )
        """)
        print("  ✅ irs_matching tablosu oluşturuldu")
        return True
    
    def create_balance_snapshots_table(self, cursor) -> bool:
        """Bilanço snapshot tablosunu oluştur"""
        if self.check_table_exists(cursor, 'balance_snapshots'):
            print("  ⏭️  balance_snapshots tablosu zaten var")
            return False
        
        cursor.execute("""
            CREATE TABLE balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                total_purchases REAL,
                total_sales REAL,
                total_paid_to_suppliers REAL,
                total_received_from_customers REAL,
                outstanding_payables REAL,
                outstanding_receivables REAL,
                net_balance REAL,
                total_profit REAL,
                total_matched_invoices INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ balance_snapshots tablosu oluşturuldu")
        return True
    
    def create_line_matching_table(self, cursor) -> bool:
        """Satır bazında eşleştirme tablosunu oluştur"""
        if self.check_table_exists(cursor, 'line_matching'):
            print("  ⏭️  line_matching tablosu zaten var")
            return False
        
        cursor.execute("""
            CREATE TABLE line_matching (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                irs_matching_id INTEGER NOT NULL,
                purchase_line_id INTEGER NOT NULL,
                sales_line_id INTEGER NOT NULL,
                item_name TEXT,
                purchase_quantity REAL,
                sales_quantity REAL,
                purchase_unit_price REAL,
                sales_unit_price REAL,
                unit_profit REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (irs_matching_id) REFERENCES irs_matching (id),
                FOREIGN KEY (purchase_line_id) REFERENCES invoice_lines (id),
                FOREIGN KEY (sales_line_id) REFERENCES invoice_lines (id)
            )
        """)
        print("  ✅ line_matching tablosu oluşturuldu")
        return True
    
    def create_indexes(self, cursor) -> int:
        """Performance için index'ler oluştur"""
        print("\n🔍 Index'ler oluşturuluyor...")
        
        indexes = [
            ("idx_invoice_type", "invoices", "invoice_type"),
            ("idx_payment_status", "invoices", "payment_status"),
            ("idx_firma_kodu", "invoices", "firma_kodu"),
            ("idx_irs_number", "irs_matching", "irs_number"),
            ("idx_payment_invoice", "payment_records", "invoice_id"),
            ("idx_snapshot_date", "balance_snapshots", "snapshot_date"),
        ]
        
        created_count = 0
        for index_name, table_name, column_name in indexes:
            try:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON {table_name}({column_name})
                """)
                print(f"  ✅ Index oluşturuldu: {index_name}")
                created_count += 1
            except Exception as e:
                print(f"  ⚠️  {index_name} oluşturulamadı: {e}")
        
        return created_count
    
    def populate_invoice_types(self, cursor) -> dict:
        """Mevcut faturaların invoice_type'larını güncelle"""
        print("\n📝 Fatura tipleri güncelleniyor...")
        
        # A ve F firma kodları = PURCHASE (alış)
        cursor.execute("""
            UPDATE invoices 
            SET invoice_type = 'PURCHASE'
            WHERE firma_kodu IN ('A', 'F') AND invoice_type IS NULL
        """)
        purchase_updated = cursor.rowcount
        
        # API firma kodu = SALES (satış)
        cursor.execute("""
            UPDATE invoices 
            SET invoice_type = 'SALES'
            WHERE firma_kodu = 'API' AND invoice_type IS NULL
        """)
        sales_updated = cursor.rowcount
        
        print(f"  ✅ {purchase_updated} alış faturası güncellendi (PURCHASE)")
        print(f"  ✅ {sales_updated} satış faturası güncellendi (SALES)")
        
        return {
            'purchase': purchase_updated,
            'sales': sales_updated
        }
    
    def calculate_remaining_amounts(self, cursor) -> int:
        """Kalan tutarları hesapla (remaining_amount)"""
        print("\n💰 Kalan tutarlar hesaplanıyor...")
        
        # remaining_amount = total_amount - paid_amount
        cursor.execute("""
            UPDATE invoices 
            SET remaining_amount = total_amount - COALESCE(paid_amount, 0)
            WHERE remaining_amount IS NULL
        """)
        updated = cursor.rowcount
        
        print(f"  ✅ {updated} fatura için kalan tutar hesaplandı")
        return updated
    
    def run_migration(self) -> bool:
        """Tüm migration işlemlerini çalıştır"""
        print("=" * 80)
        print("DATABASE SCHEMA MIGRATION - FİNANSAL TAKİP SİSTEMİ")
        print("=" * 80)
        print(f"\n📁 Hedef veritabanı: {self.db_path}")
        
        # Backup al
        if not self.create_backup():
            response = input("\n⚠️  Backup alınamadı. Devam edilsin mi? (y/N): ")
            if response.lower() != 'y':
                print("❌ Migration iptal edildi")
                return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. invoices tablosuna sütunlar ekle
            self.add_columns_to_invoices(cursor)
            
            # 2. Yeni tabloları oluştur
            print("\n📋 Yeni tablolar oluşturuluyor...")
            self.create_payment_records_table(cursor)
            self.create_irs_matching_table(cursor)
            self.create_balance_snapshots_table(cursor)
            self.create_line_matching_table(cursor)
            
            # 3. Index'leri oluştur
            self.create_indexes(cursor)
            
            # 4. Mevcut verileri güncelle
            self.populate_invoice_types(cursor)
            self.calculate_remaining_amounts(cursor)
            
            # Commit
            conn.commit()
            
            # İstatistikler
            print("\n" + "=" * 80)
            print("📊 MIGRATION İSTATİSTİKLERİ")
            print("=" * 80)
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()
            print(f"\n📋 Toplam Tablo Sayısı: {len(tables)}")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                count = cursor.fetchone()[0]
                print(f"   - {table[0]}: {count} kayıt")
            
            # Invoice type dağılımı
            print("\n📊 Fatura Tipi Dağılımı:")
            cursor.execute("""
                SELECT invoice_type, COUNT(*) 
                FROM invoices 
                WHERE invoice_type IS NOT NULL
                GROUP BY invoice_type
            """)
            for row in cursor.fetchall():
                print(f"   - {row[0]}: {row[1]} fatura")
            
            # Payment status dağılımı
            print("\n💳 Ödeme Durumu Dağılımı:")
            cursor.execute("""
                SELECT payment_status, COUNT(*) 
                FROM invoices 
                GROUP BY payment_status
            """)
            for row in cursor.fetchall():
                print(f"   - {row[0]}: {row[1]} fatura")
            
            conn.close()
            
            print("\n" + "=" * 80)
            print("✅ MIGRATION BAŞARIYLA TAMAMLANDI!")
            print("=" * 80)
            print(f"\n💾 Backup: {self.backup_path}")
            print(f"📁 Güncellenmiş DB: {self.db_path}")
            print("\n🎯 Sistem şimdi finansal takip için hazır!")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Migration hatası: {e}")
            print(f"💾 Backup'tan geri yükleme yapabilirsiniz: {self.backup_path}")
            return False


def main():
    """Ana fonksiyon"""
    migration = DatabaseMigration()
    
    print("\n⚠️  BU İŞLEM VERİTABANINI KALICI OLARAK DEĞİŞTİRECEK!")
    print("Devam etmeden önce backup alınacak.\n")
    
    response = input("Migration'ı başlatmak istiyor musunuz? (y/N): ")
    if response.lower() == 'y':
        success = migration.run_migration()
        if success:
            print("\n✨ Artık finansal takip modüllerini kullanabilirsiniz!")
            print("\nSonraki adımlar:")
            print("  1. python3 src/financial/irs_matcher.py  # İrsaliye eşleştirme")
            print("  2. python3 src/financial/balance_calculator.py  # Bilanço hesaplama")
        else:
            print("\n❌ Migration başarısız. Lütfen hataları kontrol edin.")
    else:
        print("\n❌ Migration iptal edildi")


if __name__ == '__main__':
    main()

