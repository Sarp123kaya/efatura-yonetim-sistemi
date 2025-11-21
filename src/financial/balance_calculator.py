#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bilanço Hesaplama Modülü
========================

Amaç:
- Genel finansal durumu hesaplama
- Snapshot (anlık durum) kaydetme
- Kar/zarar, borç/alacak, net pozisyon analizi
- Zaman içinde trend analizi

Kullanım:
    from src.financial.balance_calculator import BalanceCalculator
    
    bc = BalanceCalculator()
    balance = bc.calculate_current_balance()
    bc.save_snapshot()
    bc.print_balance_sheet()
"""

import sqlite3
from typing import Dict, List
from datetime import datetime
from pathlib import Path


class BalanceCalculator:
    """Bilanço hesaplama sınıfı"""
    
    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Veritabanı dosya yolu (None ise birlesik.db kullanılır)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / "data" / "db" / "birlesik.db"
        
        self.db_path = str(db_path)
    
    def get_purchase_totals(self) -> Dict:
        """Alış faturası toplamları (Fabrikalardan alışlar)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                COALESCE(SUM(total_amount), 0) as total,
                COALESCE(SUM(paid_amount), 0) as paid,
                COALESCE(SUM(remaining_amount), 0) as remaining
            FROM invoices
            WHERE invoice_type = 'PURCHASE'
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'count': row[0],
            'total': row[1],
            'paid': row[2],
            'remaining': row[3]
        }
    
    def get_sales_totals(self) -> Dict:
        """Satış faturası toplamları (Müşterilere satışlar)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                COALESCE(SUM(total_amount), 0) as total,
                COALESCE(SUM(paid_amount), 0) as paid,
                COALESCE(SUM(remaining_amount), 0) as remaining
            FROM invoices
            WHERE invoice_type = 'SALES'
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'count': row[0],
            'total': row[1],
            'paid': row[2],
            'remaining': row[3]
        }
    
    def get_profit_loss_totals(self) -> Dict:
        """Kar/zarar toplamları (İrsaliye eşleştirmelerinden)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as matched_count,
                COALESCE(SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END), 0) as profit,
                COALESCE(SUM(CASE WHEN profit_loss < 0 THEN ABS(profit_loss) ELSE 0 END), 0) as loss,
                COALESCE(SUM(profit_loss), 0) as net_profit,
                COALESCE(AVG(profit_margin), 0) as avg_margin
            FROM irs_matching
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'matched_count': row[0],
            'total_profit': row[1],
            'total_loss': row[2],
            'net_profit': row[3],
            'avg_profit_margin': row[4]
        }
    
    def calculate_current_balance(self) -> Dict:
        """Mevcut finansal durumu hesapla"""
        purchases = self.get_purchase_totals()
        sales = self.get_sales_totals()
        profit_loss = self.get_profit_loss_totals()
        
        # Net pozisyon = Alacaklar - Borçlar
        net_balance = sales['remaining'] - purchases['remaining']
        
        # Toplam nakit akışı = Tahsil edilen - Ödenen
        cash_flow = sales['paid'] - purchases['paid']
        
        # İşletme sermayesi (working capital) = Net pozisyon + Nakit akışı
        working_capital = net_balance + cash_flow
        
        balance = {
            'snapshot_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            
            # Alışlar (Borçlar)
            'total_purchases': purchases['total'],
            'paid_to_suppliers': purchases['paid'],
            'outstanding_payables': purchases['remaining'],
            
            # Satışlar (Alacaklar)
            'total_sales': sales['total'],
            'received_from_customers': sales['paid'],
            'outstanding_receivables': sales['remaining'],
            
            # Net durum
            'net_balance': net_balance,
            'cash_flow': cash_flow,
            'working_capital': working_capital,
            
            # Kar/Zarar
            'total_profit': profit_loss['total_profit'],
            'total_loss': profit_loss['total_loss'],
            'net_profit': profit_loss['net_profit'],
            'avg_profit_margin': profit_loss['avg_profit_margin'],
            'matched_invoices': profit_loss['matched_count'],
            
            # Sayılar
            'purchase_invoice_count': purchases['count'],
            'sales_invoice_count': sales['count']
        }
        
        return balance
    
    def save_snapshot(self) -> int:
        """Mevcut durumu snapshot olarak kaydet"""
        balance = self.calculate_current_balance()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO balance_snapshots (
                snapshot_date,
                total_purchases,
                total_sales,
                total_paid_to_suppliers,
                total_received_from_customers,
                outstanding_payables,
                outstanding_receivables,
                net_balance,
                total_profit,
                total_matched_invoices
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            balance['snapshot_date'],
            balance['total_purchases'],
            balance['total_sales'],
            balance['paid_to_suppliers'],
            balance['received_from_customers'],
            balance['outstanding_payables'],
            balance['outstanding_receivables'],
            balance['net_balance'],
            balance['net_profit'],
            balance['matched_invoices']
        ))
        
        snapshot_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"💾 Snapshot kaydedildi (ID: {snapshot_id})")
        return snapshot_id
    
    def get_historical_snapshots(self, limit: int = 10) -> List[Dict]:
        """Geçmiş snapshot'ları getir"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM balance_snapshots
            ORDER BY snapshot_date DESC
            LIMIT ?
        """, (limit,))
        
        snapshots = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return snapshots
    
    def print_balance_sheet(self, balance: Dict = None):
        """Bilanço raporunu yazdır"""
        if balance is None:
            balance = self.calculate_current_balance()
        
        print("\n" + "=" * 80)
        print("📊 FİNANSAL DURUM RAPORU (BALANCE SHEET)")
        print("=" * 80)
        print(f"\n📅 Tarih: {balance['snapshot_date']}")
        
        # AKTİF (Varlıklar - Assets)
        print("\n" + "-" * 80)
        print("💰 AKTİF (VARLIKLAR)")
        print("-" * 80)
        print(f"\n1. ALACAKLAR (Müşterilerden)")
        print(f"   Toplam Satışlar: {balance['total_sales']:,.2f} TRY")
        print(f"   Tahsil Edilen: {balance['received_from_customers']:,.2f} TRY")
        print(f"   Kalan Alacaklar: {balance['outstanding_receivables']:,.2f} TRY")
        
        print(f"\n2. NAKİT AKIŞI")
        print(f"   Net Nakit: {balance['cash_flow']:,.2f} TRY")
        
        total_aktif = balance['outstanding_receivables'] + balance['cash_flow']
        print(f"\n   📌 TOPLAM AKTİF: {total_aktif:,.2f} TRY")
        
        # PASİF (Borçlar - Liabilities)
        print("\n" + "-" * 80)
        print("📤 PASİF (BORÇLAR)")
        print("-" * 80)
        print(f"\n1. KISA VADELİ BORÇLAR (Fabrikalara)")
        print(f"   Toplam Alışlar: {balance['total_purchases']:,.2f} TRY")
        print(f"   Ödenen: {balance['paid_to_suppliers']:,.2f} TRY")
        print(f"   Kalan Borçlar: {balance['outstanding_payables']:,.2f} TRY")
        
        total_pasif = balance['outstanding_payables']
        print(f"\n   📌 TOPLAM PASİF: {total_pasif:,.2f} TRY")
        
        # ÖZKAYNAK (Equity)
        print("\n" + "-" * 80)
        print("💼 ÖZKAYNAK")
        print("-" * 80)
        print(f"\nNet Kar: {balance['net_profit']:,.2f} TRY")
        print(f"   • Toplam Kar: {balance['total_profit']:,.2f} TRY")
        print(f"   • Toplam Zarar: {balance['total_loss']:,.2f} TRY")
        print(f"   • Ortalama Kar Marjı: {balance['avg_profit_margin']:.2f}%")
        print(f"   • Eşleşen Fatura: {balance['matched_invoices']}")
        
        ozkaynak = balance['net_profit'] + balance['working_capital']
        print(f"\n   📌 TOPLAM ÖZKAYNAK: {ozkaynak:,.2f} TRY")
        
        # NET DURUM
        print("\n" + "=" * 80)
        print("💵 NET FİNANSAL DURUM")
        print("=" * 80)
        print(f"\nAlacaklar - Borçlar = {balance['net_balance']:,.2f} TRY")
        print(f"İşletme Sermayesi = {balance['working_capital']:,.2f} TRY")
        
        if balance['net_balance'] > 0:
            print(f"\n✅ POZİTİF - Alacaklarınız borçlarınızdan {balance['net_balance']:,.2f} TRY fazla")
        elif balance['net_balance'] < 0:
            print(f"\n⚠️  NEGATİF - Borçlarınız alacaklarınızdan {abs(balance['net_balance']):,.2f} TRY fazla")
        else:
            print(f"\n⚪ DENGE - Alacak ve borçlar eşit")
        
        # Likidite durumu
        liquidity_ratio = balance['outstanding_receivables'] / balance['outstanding_payables'] if balance['outstanding_payables'] > 0 else float('inf')
        print(f"\n📊 LİKİDİTE ORANI: {liquidity_ratio:.2f}")
        if liquidity_ratio >= 2.0:
            print("   ✅ Çok İyi - Alacaklarınız borçlarınızın 2 katından fazla")
        elif liquidity_ratio >= 1.0:
            print("   ✅ İyi - Alacaklarınız borçlarınızı karşılıyor")
        else:
            print("   ⚠️  Dikkat - Borçlarınız alacaklarınızdan fazla")
        
        print("\n" + "=" * 80)
    
    def print_historical_trend(self):
        """Geçmiş trend analizi"""
        snapshots = self.get_historical_snapshots(limit=5)
        
        if not snapshots:
            print("\n⚠️  Henüz snapshot kaydı yok")
            return
        
        print("\n" + "=" * 80)
        print("📈 GEÇMİŞ TREND ANALİZİ (Son 5 Snapshot)")
        print("=" * 80)
        
        for i, snap in enumerate(snapshots, 1):
            print(f"\n{i}. {snap['snapshot_date']}")
            print(f"   Net Pozisyon: {snap['net_balance']:,.2f} TRY")
            print(f"   Net Kar: {snap['total_profit']:,.2f} TRY")
            print(f"   Alacaklar: {snap['outstanding_receivables']:,.2f} TRY")
            print(f"   Borçlar: {snap['outstanding_payables']:,.2f} TRY")
        
        print("\n" + "=" * 80)


def main():
    """Test ve örnek kullanım"""
    bc = BalanceCalculator()
    
    print("=" * 80)
    print("BİLANÇO HESAPLAMA SİSTEMİ")
    print("=" * 80)
    
    # Mevcut durumu hesapla ve yazdır
    balance = bc.calculate_current_balance()
    bc.print_balance_sheet(balance)
    
    # Snapshot kaydet mi?
    print("\n" + "=" * 80)
    response = input("\nBu durumu snapshot olarak kaydetmek ister misiniz? (y/N): ")
    if response.lower() == 'y':
        bc.save_snapshot()
        print("✅ Snapshot kaydedildi")
    
    # Geçmiş trend
    bc.print_historical_trend()


if __name__ == '__main__':
    main()

