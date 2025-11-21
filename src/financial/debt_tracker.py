#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Borç/Alacak Takip Modülü
========================

Amaç:
- Fabrikalara olan borçları takip (AK GİPS, FULLBOARD)
- Müşterilerden olan alacakları takip (API satışları)
- Vade takibi
- Eski borç/alacak analizi (aging)

Kullanım:
    from src.financial.debt_tracker import DebtTracker
    
    dt = DebtTracker()
    payables = dt.get_payables()  # Borçlar
    receivables = dt.get_receivables()  # Alacaklar
    dt.print_aging_report()  # Yaşlandırma raporu
"""

import sqlite3
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from pathlib import Path


class DebtTracker:
    """Borç/Alacak takip sınıfı"""
    
    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Veritabanı dosya yolu (None ise birlesik.db kullanılır)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / "data" / "db" / "birlesik.db"
        
        self.db_path = str(db_path)
    
    def get_payables(self, firma_kodu: str = None) -> List[Dict]:
        """
        Borçları getir (Fabrikalara ödenecek - AK GİPS, FULLBOARD)
        
        Args:
            firma_kodu: Belirli bir firma (None ise tümü)
            
        Returns:
            Borç listesi
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        where_clause = "WHERE i.invoice_type = 'PURCHASE'"
        params = []
        
        if firma_kodu:
            where_clause += " AND i.firma_kodu = ?"
            params.append(firma_kodu)
        
        cursor.execute(f"""
            SELECT 
                i.id,
                i.invoice_number,
                i.firma_kodu,
                i.supplier_name,
                i.issue_date,
                i.total_amount,
                i.paid_amount,
                i.remaining_amount,
                i.payment_status,
                i.payment_due_date,
                julianday('now') - julianday(i.issue_date) as days_old
            FROM invoices i
            {where_clause}
            ORDER BY i.issue_date ASC
        """, params)
        
        payables = []
        for row in cursor.fetchall():
            payables.append({
                'id': row['id'],
                'invoice_number': row['invoice_number'],
                'firma_kodu': row['firma_kodu'],
                'supplier_name': row['supplier_name'],
                'issue_date': row['issue_date'],
                'total_amount': row['total_amount'] or 0,
                'paid_amount': row['paid_amount'] or 0,
                'remaining_amount': row['remaining_amount'] or row['total_amount'] or 0,
                'payment_status': row['payment_status'] or 'UNPAID',
                'payment_due_date': row['payment_due_date'],
                'days_old': int(row['days_old']) if row['days_old'] else 0
            })
        
        conn.close()
        return payables
    
    def get_receivables(self) -> List[Dict]:
        """
        Alacakları getir (Müşterilerden tahsil edilecek - API satışları)
        
        Returns:
            Alacak listesi
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                i.id,
                i.invoice_number,
                i.customer_name,
                i.issue_date,
                i.total_amount,
                i.paid_amount,
                i.remaining_amount,
                i.payment_status,
                i.payment_due_date,
                julianday('now') - julianday(i.issue_date) as days_old
            FROM invoices i
            WHERE i.invoice_type = 'SALES'
            ORDER BY i.issue_date ASC
        """)
        
        receivables = []
        for row in cursor.fetchall():
            receivables.append({
                'id': row['id'],
                'invoice_number': row['invoice_number'],
                'customer_name': row['customer_name'],
                'issue_date': row['issue_date'],
                'total_amount': row['total_amount'] or 0,
                'paid_amount': row['paid_amount'] or 0,
                'remaining_amount': row['remaining_amount'] or row['total_amount'] or 0,
                'payment_status': row['payment_status'] or 'UNPAID',
                'payment_due_date': row['payment_due_date'],
                'days_old': int(row['days_old']) if row['days_old'] else 0
            })
        
        conn.close()
        return receivables
    
    def get_payables_summary(self) -> Dict:
        """Borç özet bilgileri"""
        payables = self.get_payables()
        
        total_payables = sum(p['remaining_amount'] for p in payables)
        unpaid = [p for p in payables if p['payment_status'] == 'UNPAID']
        partial = [p for p in payables if p['payment_status'] == 'PARTIAL']
        
        # Firma bazında dağılım
        by_firma = {}
        for p in payables:
            firma = p['firma_kodu']
            if firma not in by_firma:
                by_firma[firma] = {
                    'count': 0,
                    'total': 0,
                    'remaining': 0
                }
            by_firma[firma]['count'] += 1
            by_firma[firma]['total'] += p['total_amount']
            by_firma[firma]['remaining'] += p['remaining_amount']
        
        return {
            'total_invoices': len(payables),
            'total_amount': sum(p['total_amount'] for p in payables),
            'total_paid': sum(p['paid_amount'] for p in payables),
            'total_remaining': total_payables,
            'unpaid_count': len(unpaid),
            'partial_count': len(partial),
            'by_firma': by_firma
        }
    
    def get_receivables_summary(self) -> Dict:
        """Alacak özet bilgileri"""
        receivables = self.get_receivables()
        
        total_receivables = sum(r['remaining_amount'] for r in receivables)
        unpaid = [r for r in receivables if r['payment_status'] == 'UNPAID']
        partial = [r for r in receivables if r['payment_status'] == 'PARTIAL']
        
        return {
            'total_invoices': len(receivables),
            'total_amount': sum(r['total_amount'] for r in receivables),
            'total_paid': sum(r['paid_amount'] for r in receivables),
            'total_remaining': total_receivables,
            'unpaid_count': len(unpaid),
            'partial_count': len(partial)
        }
    
    def get_aging_buckets(self, debts: List[Dict]) -> Dict:
        """
        Yaşlandırma analizi (Aging)
        
        Kategoriler:
        - 0-30 gün: Güncel
        - 31-60 gün: Vadesi yaklaşan
        - 61-90 gün: Vadesi geçen
        - 90+ gün: Çok eski
        
        Args:
            debts: Borç/alacak listesi
            
        Returns:
            Yaşlandırma bucket'ları
        """
        buckets = {
            '0-30': {'count': 0, 'amount': 0, 'items': []},
            '31-60': {'count': 0, 'amount': 0, 'items': []},
            '61-90': {'count': 0, 'amount': 0, 'items': []},
            '90+': {'count': 0, 'amount': 0, 'items': []}
        }
        
        for debt in debts:
            # Sadece ödenmemiş olanları say
            if debt['payment_status'] == 'PAID':
                continue
            
            days = debt['days_old']
            amount = debt['remaining_amount']
            
            if days <= 30:
                bucket = '0-30'
            elif days <= 60:
                bucket = '31-60'
            elif days <= 90:
                bucket = '61-90'
            else:
                bucket = '90+'
            
            buckets[bucket]['count'] += 1
            buckets[bucket]['amount'] += amount
            buckets[bucket]['items'].append(debt)
        
        return buckets
    
    def print_payables_report(self):
        """Borç raporunu yazdır"""
        summary = self.get_payables_summary()
        payables = self.get_payables()
        
        print("\n" + "=" * 80)
        print("📤 BORÇLARIMIZ (FABRİKALARA ÖDENECEK)")
        print("=" * 80)
        
        print(f"\n📊 GENEL DURUM:")
        print(f"   Toplam Fatura: {summary['total_invoices']}")
        print(f"   Toplam Tutar: {summary['total_amount']:,.2f} TRY")
        print(f"   Ödenen: {summary['total_paid']:,.2f} TRY")
        print(f"   Kalan Borç: {summary['total_remaining']:,.2f} TRY")
        print(f"   Ödenmemiş: {summary['unpaid_count']} fatura")
        print(f"   Kısmi Ödenen: {summary['partial_count']} fatura")
        
        print(f"\n🏢 FİRMA BAZINDA BORÇLAR:")
        for firma, data in summary['by_firma'].items():
            firma_name = "AK GİPS" if firma == 'A' else "FULLBOARD" if firma == 'F' else firma
            print(f"\n   {firma_name}:")
            print(f"      Fatura Sayısı: {data['count']}")
            print(f"      Toplam Tutar: {data['total']:,.2f} TRY")
            print(f"      Kalan Borç: {data['remaining']:,.2f} TRY")
        
        # Yaşlandırma
        aging = self.get_aging_buckets(payables)
        print(f"\n📅 YAŞLANDIRMA ANALİZİ:")
        for bucket, data in aging.items():
            if data['count'] > 0:
                print(f"   {bucket} gün: {data['count']} fatura - {data['amount']:,.2f} TRY")
        
        print("\n" + "=" * 80)
    
    def print_receivables_report(self):
        """Alacak raporunu yazdır"""
        summary = self.get_receivables_summary()
        receivables = self.get_receivables()
        
        print("\n" + "=" * 80)
        print("📥 ALACAKLARIMIZ (MÜŞTERİLERDEN TAHSİL EDİLECEK)")
        print("=" * 80)
        
        print(f"\n📊 GENEL DURUM:")
        print(f"   Toplam Fatura: {summary['total_invoices']}")
        print(f"   Toplam Tutar: {summary['total_amount']:,.2f} TRY")
        print(f"   Tahsil Edilen: {summary['total_paid']:,.2f} TRY")
        print(f"   Kalan Alacak: {summary['total_remaining']:,.2f} TRY")
        print(f"   Ödenmemiş: {summary['unpaid_count']} fatura")
        print(f"   Kısmi Ödenen: {summary['partial_count']} fatura")
        
        # Yaşlandırma
        aging = self.get_aging_buckets(receivables)
        print(f"\n📅 YAŞLANDIRMA ANALİZİ:")
        for bucket, data in aging.items():
            if data['count'] > 0:
                print(f"   {bucket} gün: {data['count']} fatura - {data['amount']:,.2f} TRY")
        
        print("\n" + "=" * 80)
    
    def print_full_report(self):
        """Tam borç/alacak raporu"""
        print("\n" + "=" * 80)
        print("💰 BORÇ/ALACAK TAKİP RAPORU")
        print("=" * 80)
        
        self.print_payables_report()
        self.print_receivables_report()
        
        # Net durum
        payables_summary = self.get_payables_summary()
        receivables_summary = self.get_receivables_summary()
        
        net_position = receivables_summary['total_remaining'] - payables_summary['total_remaining']
        
        print("\n" + "=" * 80)
        print("💵 NET DURUM")
        print("=" * 80)
        print(f"\nAlacaklarımız: {receivables_summary['total_remaining']:,.2f} TRY")
        print(f"Borçlarımız: {payables_summary['total_remaining']:,.2f} TRY")
        print(f"Net Pozisyon: {net_position:,.2f} TRY")
        
        if net_position > 0:
            print(f"\n✅ Pozitif durum - Alacaklarımız borçlarımızdan {net_position:,.2f} TRY fazla")
        elif net_position < 0:
            print(f"\n⚠️  Negatif durum - Borçlarımız alacaklarımızdan {abs(net_position):,.2f} TRY fazla")
        else:
            print(f"\n⚪ Dengede - Alacak ve borçlar eşit")
        
        print("\n" + "=" * 80)


def main():
    """Test ve örnek kullanım"""
    dt = DebtTracker()
    dt.print_full_report()


if __name__ == '__main__':
    main()

