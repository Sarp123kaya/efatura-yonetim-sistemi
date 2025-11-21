#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Veritabanı Modülü
=====================

İşbaşı API'sinden çekilen fatura verilerini SQLite veritabanına kaydeder.
AK GİPS ve FULLBOARD yapılarıyla tutarlılık için ayrı bir API DB oluşturur.
"""

import sqlite3
import os
import re
from pathlib import Path
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class APIDatabase:
    """API veritabanı yönetimi sınıfı"""
    
    def __init__(self, db_path: str = None):
        """
        API Database'i başlatır
        
        Args:
            db_path: Veritabanı dosya yolu (varsayılan: data/db/api.db)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.db_path = project_root / "data" / "db" / "api.db"
        else:
            self.db_path = Path(db_path)
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"API Database path: {self.db_path}")
    
    def create_database(self) -> sqlite3.Connection:
        """
        API veritabanı şemasını oluşturur
        
        Returns:
            sqlite3.Connection: Veritabanı bağlantısı
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Ana fatura tablosu (API verilerine özel)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_id TEXT NOT NULL UNIQUE,
                source TEXT DEFAULT 'API',
                parse_date TEXT NOT NULL,
                invoice_number TEXT,
                invoice_type TEXT,
                issue_date TEXT,
                total_amount REAL,
                currency TEXT DEFAULT 'TRY',
                taxable_amount REAL,
                firm_name TEXT,
                firm_vkn TEXT,
                description TEXT,
                raw_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # İrsaliye numaraları (description'dan çıkarılan)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS despatch_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                irsaliye_no TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            )
        ''')
        
        # Unique index - aynı fatura tekrar edilemez
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_api_invoice 
            ON invoices(api_id, invoice_number)
        ''')
        
        conn.commit()
        logger.info("✅ API veritabanı şeması oluşturuldu")
        return conn
    
    @staticmethod
    def extract_irsaliye_from_description(description: str) -> List[str]:
        """
        Description alanından irsaliye numaralarını çıkarır
        
        Desteklenen formatlar:
        - IRS12345
        - İRS12345
        - A-12345
        - F-12345
        
        Args:
            description: Açıklama metni
            
        Returns:
            List[str]: Bulunan irsaliye numaraları listesi
        """
        if not description:
            return []
        
        irsaliye_numbers = []
        
        # Pattern 1: IRS veya İRS ile başlayanlar
        pattern1 = r'[İI]RS[-\s]?(\d{5,})'
        matches1 = re.findall(pattern1, description, re.IGNORECASE)
        for match in matches1:
            irsaliye_numbers.append(f"IRS{match}")
        
        # Pattern 2: A- veya F- prefix'li numaralar
        pattern2 = r'([AF])-(\d{5,})'
        matches2 = re.findall(pattern2, description, re.IGNORECASE)
        for match in matches2:
            irsaliye_numbers.append(f"{match[0]}-{match[1]}")
        
        return list(set(irsaliye_numbers))  # Duplicate'leri temizle
    
    @staticmethod
    def clean_bank_info_from_description(description: str) -> str:
        """
        Description alanından SADECE banka bilgilerini temizler
        İrsaliye numaraları ve diğer bilgileri KORUR
        
        Args:
            description: Temizlenecek açıklama metni
            
        Returns:
            Temizlenmiş açıklama metni (irsaliye bilgileri korunur)
        """
        if not description:
            return ""
        
        desc = str(description)
        
        # SADECE banka bilgisi içeren spesifik pattern'leri temizle
        # ÇOK SPESİFİK - sadece kesin banka bilgilerini temizler
        patterns_to_remove = [
            # Spesifik GARANTİBANK IBAN'ı (Excel format)
            r'Banka\s+Bilgileri\s*[:\s]*_x000D_\s*GARANTİBANK\s*-?\s*TR\s*35\s*0006\s*2001\s*1670\s*0006\s*2939\s*21\s*_x000D_',
            # Spesifik GARANTİBANK IBAN'ı (normal format)
            r'Banka\s+Bilgileri\s*[:\s]*[\r\n]+\s*GARANTİBANK\s*-?\s*TR\s*35\s*0006\s*2001\s*1670\s*0006\s*2939\s*21\s*[\r\n]+',
            # Spesifik GARANTİBANK IBAN'ı (HTML format)
            r'Banka\s+Bilgileri\s*[:\s]*<br\s*/?>\s*GARANTİBANK\s*-?\s*TR\s*35\s*0006\s*2001\s*1670\s*0006\s*2939\s*21\s*<br\s*/?>',
            # Spesifik GARANTİBANK IBAN'ı (tek satır)
            r'Banka\s+Bilgileri\s*[:\s]*GARANTİBANK\s*-?\s*TR\s*35\s*0006\s*2001\s*1670\s*0006\s*2939\s*21',
            # Herhangi bir IBAN (TR ile başlayan 26 haneli)
            r'TR\s*\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}',
        ]
        
        for pattern in patterns_to_remove:
            desc = re.sub(pattern, '', desc, flags=re.IGNORECASE | re.MULTILINE)
        
        # "Banka Bilgileri:" başlığını da temizle (yalnız kaldıysa)
        desc = re.sub(r'Banka\s+Bilgileri\s*[:\s]*$', '', desc, flags=re.IGNORECASE | re.MULTILINE)
        desc = re.sub(r'^Banka\s+Bilgileri\s*[:\s]*', '', desc, flags=re.IGNORECASE | re.MULTILINE)
        
        # Sadece fazla boşlukları temizle - satır sonlarını KORUR
        desc = re.sub(r' +', ' ', desc)  # Sadece boşlukları tek boşluğa indir
        desc = desc.strip()  # Başındaki ve sonundaki boşlukları temizle
        
        return desc
    
    def insert_invoice(self, conn: sqlite3.Connection, invoice_data: Dict) -> int:
        """
        Tek bir faturayı veritabanına ekler
        
        Args:
            conn: Veritabanı bağlantısı
            invoice_data: Fatura verisi (API'den gelen dict)
            
        Returns:
            int: Eklenen kaydın ID'si (0 ise duplicate)
        """
        cursor = conn.cursor()
        
        # Description'ı temizle
        raw_description = invoice_data.get('description', '')
        cleaned_description = self.clean_bank_info_from_description(raw_description)
        
        # İrsaliye numaralarını çıkar
        irsaliye_numbers = self.extract_irsaliye_from_description(raw_description)
        
        # Invoice type'a göre firm_name'i belirle
        invoice_type = invoice_data.get('type', '')
        firm_name = invoice_data.get('firmName', '')
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO invoices (
                    api_id, source, parse_date, invoice_number, invoice_type,
                    issue_date, total_amount, currency, taxable_amount,
                    firm_name, firm_vkn, description, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(invoice_data.get('id', '')),
                'API',
                invoice_data.get('date', ''),
                invoice_data.get('invoiceNumber', ''),
                invoice_type,
                invoice_data.get('date', ''),
                float(invoice_data.get('totalTL', 0)),
                'TRY',
                float(invoice_data.get('taxableAmount', 0)),
                firm_name,
                invoice_data.get('vkn', None),
                cleaned_description,
                str(invoice_data)  # Raw JSON'u sakla
            ))
            
            invoice_db_id = cursor.lastrowid
            
            # Eğer INSERT IGNORE ile atlandıysa (lastrowid = 0), mevcut kaydın ID'sini bul
            if invoice_db_id == 0:
                cursor.execute('''
                    SELECT id FROM invoices WHERE api_id = ? AND invoice_number = ?
                ''', (str(invoice_data.get('id', '')), invoice_data.get('invoiceNumber', '')))
                result = cursor.fetchone()
                if result:
                    invoice_db_id = result[0]
                    return 0  # Duplicate, yeni kayıt eklenmedi
            
            # İrsaliye numaralarını ekle
            for irsaliye_no in irsaliye_numbers:
                cursor.execute('''
                    INSERT OR IGNORE INTO despatch_references (
                        invoice_id, irsaliye_no
                    ) VALUES (?, ?)
                ''', (invoice_db_id, irsaliye_no))
            
            conn.commit()
            return invoice_db_id
            
        except Exception as e:
            logger.error(f"❌ Fatura ekleme hatası: {e}")
            return 0
    
    def insert_invoices_batch(self, invoices_data: List[Dict]) -> tuple:
        """
        Toplu fatura ekleme
        
        Args:
            invoices_data: Fatura verileri listesi
            
        Returns:
            tuple: (toplam, eklenen, duplicate)
        """
        conn = self.create_database()
        
        total = len(invoices_data)
        added = 0
        duplicate = 0
        giden = 0
        gelen = 0
        
        logger.info(f"📊 {total} fatura işleniyor...")
        
        for invoice in invoices_data:
            result = self.insert_invoice(conn, invoice)
            if result > 0:
                added += 1
                # Type'a göre say
                if invoice.get('type') == 'PURCHASE_INVOICE':
                    gelen += 1
                else:
                    giden += 1
            else:
                duplicate += 1
        
        conn.close()
        
        logger.info(f"✅ API veritabanına kaydedildi:")
        logger.info(f"   📊 Toplam: {total}")
        logger.info(f"   ✅ Eklenen: {added}")
        logger.info(f"      🟢 Giden: {giden}")
        logger.info(f"      🔴 Gelen: {gelen}")
        logger.info(f"   ⚠️  Duplicate: {duplicate}")
        
        return (total, added, duplicate)
    
    def get_statistics(self) -> Dict:
        """
        Veritabanı istatistiklerini getirir
        
        Returns:
            Dict: İstatistik bilgileri
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stats = {}
        
        # Toplam fatura sayısı
        cursor.execute("SELECT COUNT(*) FROM invoices")
        stats['total_invoices'] = cursor.fetchone()[0]
        
        # Giden fatura sayısı
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE invoice_type != 'PURCHASE_INVOICE'")
        stats['outgoing_invoices'] = cursor.fetchone()[0]
        
        # Gelen fatura sayısı
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE invoice_type = 'PURCHASE_INVOICE'")
        stats['incoming_invoices'] = cursor.fetchone()[0]
        
        # Toplam tutar
        cursor.execute("SELECT SUM(total_amount) FROM invoices")
        result = cursor.fetchone()
        stats['total_amount'] = result[0] if result[0] else 0
        
        # Giden fatura tutarı
        cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE invoice_type != 'PURCHASE_INVOICE'")
        result = cursor.fetchone()
        stats['outgoing_amount'] = result[0] if result[0] else 0
        
        # Gelen fatura tutarı
        cursor.execute("SELECT SUM(total_amount) FROM invoices WHERE invoice_type = 'PURCHASE_INVOICE'")
        result = cursor.fetchone()
        stats['incoming_amount'] = result[0] if result[0] else 0
        
        # İrsaliye sayısı
        cursor.execute("SELECT COUNT(*) FROM despatch_references")
        stats['despatch_count'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def print_statistics(self):
        """İstatistikleri ekrana yazdırır"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("API VERİTABANI İSTATİSTİKLERİ")
        print("=" * 60)
        print(f"📊 Toplam Fatura: {stats['total_invoices']}")
        print(f"   🟢 Giden: {stats['outgoing_invoices']}")
        print(f"   🔴 Gelen: {stats['incoming_invoices']}")
        print()
        print(f"💰 Toplam Tutar: {stats['total_amount']:,.2f} TRY")
        print(f"   🟢 Giden: {stats['outgoing_amount']:,.2f} TRY")
        print(f"   🔴 Gelen: {stats['incoming_amount']:,.2f} TRY")
        print()
        print(f"📄 İrsaliye Referansları: {stats['despatch_count']}")
        print(f"💾 Veritabanı: {self.db_path}")
        print("=" * 60)


if __name__ == '__main__':
    # Test
    db = APIDatabase()
    conn = db.create_database()
    conn.close()
    db.print_statistics()

