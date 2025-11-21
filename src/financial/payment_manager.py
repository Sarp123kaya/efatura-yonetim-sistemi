#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ödeme Yönetim Modülü
====================

Amaç:
- Ödeme kayıtlarını yönetme
- Fatura ödeme durumlarını güncelleme
- Ödeme geçmişi takibi
- Kısmi ödeme desteği

Kullanım:
    from src.financial.payment_manager import PaymentManager
    
    pm = PaymentManager()
    pm.add_payment(invoice_id=123, amount=5000, payment_method='BANK_TRANSFER')
    pm.get_invoice_payments(invoice_id=123)
"""

import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path


class PaymentManager:
    """Ödeme yönetim sınıfı"""
    
    PAYMENT_METHODS = [
        'BANK_TRANSFER',  # Banka havalesi
        'CASH',  # Nakit
        'CHECK',  # Çek
        'CREDIT_CARD',  # Kredi kartı
        'PROMISSORY_NOTE',  # Senet
        'OTHER'  # Diğer
    ]
    
    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Veritabanı dosya yolu (None ise birlesik.db kullanılır)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / "data" / "db" / "birlesik.db"
        
        self.db_path = str(db_path)
    
    def add_payment(
        self,
        invoice_id: int,
        amount: float,
        payment_date: str = None,
        payment_method: str = 'BANK_TRANSFER',
        reference_number: str = None,
        notes: str = None
    ) -> int:
        """
        Ödeme kaydı ekle
        
        Args:
            invoice_id: Fatura ID
            amount: Ödeme tutarı
            payment_date: Ödeme tarihi (None ise bugün)
            payment_method: Ödeme yöntemi
            reference_number: Referans/dekont numarası
            notes: Notlar
            
        Returns:
            Oluşturulan ödeme kaydının ID'si
        """
        if payment_date is None:
            payment_date = datetime.now().strftime('%Y-%m-%d')
        
        if payment_method not in self.PAYMENT_METHODS:
            print(f"⚠️  Geçersiz ödeme yöntemi: {payment_method}")
            print(f"   Geçerli yöntemler: {', '.join(self.PAYMENT_METHODS)}")
            payment_method = 'OTHER'
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Ödeme kaydını ekle
        cursor.execute("""
            INSERT INTO payment_records (
                invoice_id, payment_date, amount, payment_method,
                reference_number, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (invoice_id, payment_date, amount, payment_method, reference_number, notes))
        
        payment_id = cursor.lastrowid
        
        # Fatura ödeme durumunu güncelle
        self._update_invoice_payment_status(cursor, invoice_id)
        
        conn.commit()
        conn.close()
        
        print(f"✅ Ödeme kaydı eklendi (ID: {payment_id})")
        return payment_id
    
    def _update_invoice_payment_status(self, cursor, invoice_id: int):
        """Faturanın ödeme durumunu güncelle"""
        # Toplam ödenen miktarı hesapla
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total_paid
            FROM payment_records
            WHERE invoice_id = ?
        """, (invoice_id,))
        
        total_paid = cursor.fetchone()[0]
        
        # Fatura toplam tutarını al
        cursor.execute("""
            SELECT total_amount FROM invoices WHERE id = ?
        """, (invoice_id,))
        
        result = cursor.fetchone()
        if not result:
            return
        
        total_amount = result[0]
        remaining = total_amount - total_paid
        
        # Ödeme durumunu belirle
        if remaining <= 0:
            status = 'PAID'
        elif total_paid > 0:
            status = 'PARTIAL'
        else:
            status = 'UNPAID'
        
        # Güncelle
        cursor.execute("""
            UPDATE invoices
            SET paid_amount = ?,
                remaining_amount = ?,
                payment_status = ?
            WHERE id = ?
        """, (total_paid, max(0, remaining), status, invoice_id))
    
    def get_invoice_payments(self, invoice_id: int) -> List[Dict]:
        """Faturaya ait tüm ödemeleri getir"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM payment_records
            WHERE invoice_id = ?
            ORDER BY payment_date DESC
        """, (invoice_id,))
        
        payments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return payments
    
    def delete_payment(self, payment_id: int) -> bool:
        """Ödeme kaydını sil ve fatura durumunu güncelle"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Önce invoice_id'yi al
        cursor.execute("SELECT invoice_id FROM payment_records WHERE id = ?", (payment_id,))
        result = cursor.fetchone()
        
        if not result:
            print(f"❌ Ödeme kaydı bulunamadı (ID: {payment_id})")
            conn.close()
            return False
        
        invoice_id = result[0]
        
        # Ödemeyi sil
        cursor.execute("DELETE FROM payment_records WHERE id = ?", (payment_id,))
        
        # Fatura durumunu güncelle
        self._update_invoice_payment_status(cursor, invoice_id)
        
        conn.commit()
        conn.close()
        
        print(f"✅ Ödeme kaydı silindi (ID: {payment_id})")
        return True
    
    def get_payment_summary(self, firma_kodu: str = None) -> Dict:
        """
        Ödeme özet raporu
        
        Args:
            firma_kodu: Belirli bir firma için rapor (None ise tümü)
            
        Returns:
            Özet bilgiler
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # WHERE clause oluştur
        where_clause = ""
        params = []
        if firma_kodu:
            where_clause = "WHERE i.firma_kodu = ?"
            params.append(firma_kodu)
        
        # Ödeme durumu dağılımı
        cursor.execute(f"""
            SELECT 
                payment_status,
                COUNT(*) as count,
                SUM(total_amount) as total_amount,
                SUM(paid_amount) as total_paid,
                SUM(remaining_amount) as total_remaining
            FROM invoices i
            {where_clause}
            GROUP BY payment_status
        """, params)
        
        status_summary = {}
        for row in cursor.fetchall():
            status_summary[row['payment_status']] = {
                'count': row['count'],
                'total_amount': row['total_amount'] or 0,
                'total_paid': row['total_paid'] or 0,
                'total_remaining': row['total_remaining'] or 0
            }
        
        # Toplam ödeme sayısı
        cursor.execute("SELECT COUNT(*) as count FROM payment_records")
        total_payments_count = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'status_summary': status_summary,
            'total_payments_count': total_payments_count,
            'firma_kodu': firma_kodu
        }
    
    def print_payment_summary(self, firma_kodu: str = None):
        """Ödeme özetini console'a yazdır"""
        summary = self.get_payment_summary(firma_kodu)
        
        print("\n" + "=" * 80)
        if firma_kodu:
            print(f"ÖDEME ÖZETİ - {firma_kodu}")
        else:
            print("ÖDEME ÖZETİ - TÜM FİRMALAR")
        print("=" * 80)
        
        print(f"\nToplam Ödeme Kayıt Sayısı: {summary['total_payments_count']}")
        
        print("\n📊 FATURA DURUMU DAĞILIMI:")
        for status, data in summary['status_summary'].items():
            print(f"\n{status}:")
            print(f"   Fatura Sayısı: {data['count']}")
            print(f"   Toplam Tutar: {data['total_amount']:,.2f} TRY")
            print(f"   Ödenen: {data['total_paid']:,.2f} TRY")
            print(f"   Kalan: {data['total_remaining']:,.2f} TRY")
        
        print("\n" + "=" * 80)


def main():
    """Test ve örnek kullanım"""
    pm = PaymentManager()
    
    print("=" * 80)
    print("ÖDEME YÖNETİM SİSTEMİ")
    print("=" * 80)
    
    # Özet rapor
    pm.print_payment_summary()
    
    print("\n📋 Kullanım Örnekleri:")
    print("\n# Ödeme eklemek için:")
    print("pm.add_payment(invoice_id=123, amount=5000, payment_method='BANK_TRANSFER', reference_number='DEKONT001')")
    print("\n# Fatura ödemelerini görüntülemek için:")
    print("payments = pm.get_invoice_payments(invoice_id=123)")
    print("\n# Ödeme silmek için:")
    print("pm.delete_payment(payment_id=1)")


if __name__ == '__main__':
    main()

