#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İrsaliye Eşleştirme ve Kar/Zarar Hesaplama Modülü
==================================================

Amaç:
- Aynı irsaliye numarasına sahip alış ve satış faturalarını eşleştirme
- Alış fiyatı - Satış fiyatı karşılaştırması
- Kar/Zarar hesaplama
- Kar marjı analizi

Mantık:
1. Alış faturaları (AK GİPS, FULLBOARD) → despatch_documents tablosundan IRS numaraları
2. Satış faturaları (API) → description alanından IRS numaraları (regex ile)
3. Normalize edilmiş IRS numarası ile eşleştirme
4. Kar/Zarar = Satış Tutarı - Alış Tutarı
5. Kar Marjı = (Kar/Zarar ÷ Alış Tutarı) × 100
"""

import sqlite3
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from pathlib import Path


class IRSMatcher:
    """İrsaliye eşleştirme ve kar/zarar hesaplama sınıfı"""
    
    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Veritabanı dosya yolu (None ise birlesik.db kullanılır)
        """
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / "data" / "db" / "birlesik.db"
        
        self.db_path = str(db_path)
        self.matches = []
    
    @staticmethod
    def normalize_irs_number(irs_full: str) -> str:
        """
        İrsaliye numarasını normalize et (firma prefix'siz, sadece rakamlar)
        
        Örnekler:
        - "A-14740" -> "14740"
        - "F-07904" -> "7904"
        - "IRS2025000014740" -> "14740"
        - "IRS14740" -> "14740"
        - "14740" -> "14740"
        
        Args:
            irs_full: Tam irsaliye numarası
            
        Returns:
            Normalize edilmiş numara (sadece rakamlar, baştaki sıfırlar yok)
        """
        if not irs_full:
            return ""
        
        # String'e çevir
        irs = str(irs_full).strip().upper()
        
        # Firma prefix'ini kaldır (A-, F-, API-, vb.)
        irs = re.sub(r'^[A-Z]+-', '', irs)
        
        # IRS önekini ve ardındaki sıfırları kaldır
        # IRS2025000014740 -> 14740
        # IRS000014740 -> 14740
        irs = re.sub(r'^IRS\d*?0*', 'IRS', irs)
        irs = irs.replace('IRS', '')
        
        # Baştaki sıfırları kaldır
        irs = irs.lstrip('0') or '0'
        
        return irs
    
    def extract_irs_from_description(self, description: str) -> List[str]:
        """
        Description alanından irsaliye numaralarını çıkar
        
        Desteklenen formatlar:
        - "IRS NO: 14740"
        - "İrsaliye: A-14740"
        - "IRSALIYE: 14740"
        - "IRS:14740"
        - "Irsaliye No: 14740, 14741, 14742"
        
        Args:
            description: Açıklama metni
            
        Returns:
            Bulunan irsaliye numaraları listesi (normalize edilmiş)
        """
        if not description or description.strip() == '':
            return []
        
        irs_numbers = []
        
        # Pattern'ler (öncelik sırasına göre)
        patterns = [
            r'IRS\s*NO[:\s]*([A-Z]-)?(\d+)',  # IRS NO: 14740 veya IRS NO: A-14740
            r'İRSALİYE\s*(?:NO)?[:\s]*([A-Z]-)?(\d+)',  # İrsaliye: 14740
            r'IRSALIYE\s*(?:NO)?[:\s]*([A-Z]-)?(\d+)',  # Irsaliye: 14740
            r'IRS[:\s]*([A-Z]-)?(\d+)',  # IRS:14740
            r'(?:^|\s)([A-Z]-)?(\d{5,})',  # Tek başına 5+ haneli numara
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, description.upper())
            for match in matches:
                # Son grubu al (rakamlar)
                groups = match.groups()
                number = groups[-1]  # Son grup her zaman rakamlar
                
                # 5 haneden kısa numaraları atla (false positive)
                if len(number) >= 5:
                    normalized = self.normalize_irs_number(number)
                    if normalized and normalized not in irs_numbers:
                        irs_numbers.append(normalized)
        
        return irs_numbers
    
    def get_purchase_invoices_with_irs(self) -> List[Dict]:
        """
        Alış faturalarını (AK GİPS, FULLBOARD) ve irsaliye numaralarını getir
        
        Returns:
            List of dicts with invoice and IRS info
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Alış faturaları ve irsaliye numaraları
        cursor.execute("""
            SELECT 
                i.id as invoice_id,
                i.invoice_number,
                i.total_amount,
                i.firma_kodu,
                i.issue_date,
                i.supplier_name,
                d.despatch_id_short,
                d.despatch_id_full
            FROM invoices i
            JOIN despatch_documents d ON i.id = d.invoice_id
            WHERE i.invoice_type = 'PURCHASE'
            ORDER BY i.issue_date DESC
        """)
        
        invoices = []
        for row in cursor.fetchall():
            invoices.append({
                'invoice_id': row['invoice_id'],
                'invoice_number': row['invoice_number'],
                'total_amount': float(row['total_amount']) if row['total_amount'] else 0,
                'firma_kodu': row['firma_kodu'],
                'issue_date': row['issue_date'],
                'supplier_name': row['supplier_name'],
                'irs_short': row['despatch_id_short'],
                'irs_full': row['despatch_id_full'],
                'irs_normalized': self.normalize_irs_number(row['despatch_id_short'])
            })
        
        conn.close()
        return invoices
    
    def get_sales_invoices_with_irs(self) -> List[Dict]:
        """
        Satış faturalarını (API) ve description'dan çıkarılan irsaliye numaralarını getir
        
        Returns:
            List of dicts with invoice and IRS info
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Satış faturaları
        cursor.execute("""
            SELECT 
                id as invoice_id,
                invoice_number,
                total_amount,
                issue_date,
                customer_name,
                description
            FROM invoices
            WHERE invoice_type = 'SALES'
            AND description IS NOT NULL
            AND description != ''
            ORDER BY issue_date DESC
        """)
        
        invoices = []
        for row in cursor.fetchall():
            # Description'dan IRS numaralarını çıkar
            irs_numbers = self.extract_irs_from_description(row['description'])
            
            if irs_numbers:  # Sadece IRS numarası bulunanlara ekle
                invoices.append({
                    'invoice_id': row['invoice_id'],
                    'invoice_number': row['invoice_number'],
                    'total_amount': float(row['total_amount']) if row['total_amount'] else 0,
                    'issue_date': row['issue_date'],
                    'customer_name': row['customer_name'],
                    'description': row['description'],
                    'irs_numbers': irs_numbers  # Liste (birden fazla olabilir)
                })
        
        conn.close()
        return invoices
    
    def find_matches(self) -> List[Dict]:
        """
        Alış ve satış faturalarında IRS numarası eşleşmesi ara
        
        Returns:
            Eşleşmelerin listesi
        """
        print("\n🔍 İrsaliye eşleştirmeleri aranıyor...")
        
        # Verileri çek
        purchase_invoices = self.get_purchase_invoices_with_irs()
        sales_invoices = self.get_sales_invoices_with_irs()
        
        print(f"   📦 {len(purchase_invoices)} alış faturasında irsaliye bulundu")
        print(f"   📤 {len(sales_invoices)} satış faturasında irsaliye bulundu")
        
        matches = []
        matched_sales = set()  # Tekrar eşleşmeyi önle
        
        # Her alış faturası için satış faturalarında eşleşme ara
        for purchase in purchase_invoices:
            purchase_irs = purchase['irs_normalized']
            
            for sales in sales_invoices:
                # Bu satış faturası zaten eşleştirilmiş mi?
                if sales['invoice_id'] in matched_sales:
                    continue
                
                # Satış faturasının IRS numaralarından herhangi biri eşleşiyor mu?
                for sales_irs in sales['irs_numbers']:
                    if sales_irs == purchase_irs:
                        # Eşleşme bulundu!
                        purchase_amt = purchase['total_amount']
                        sales_amt = sales['total_amount']
                        
                        # Kar/Zarar hesapla
                        profit_loss = sales_amt - purchase_amt
                        profit_margin = (profit_loss / purchase_amt * 100) if purchase_amt > 0 else 0
                        
                        match = {
                            'irs_number': purchase['irs_short'],
                            'irs_normalized': purchase_irs,
                            'purchase_invoice_id': purchase['invoice_id'],
                            'purchase_invoice_no': purchase['invoice_number'],
                            'purchase_amount': purchase_amt,
                            'purchase_date': purchase['issue_date'],
                            'supplier': purchase['firma_kodu'],
                            'supplier_name': purchase['supplier_name'],
                            'sales_invoice_id': sales['invoice_id'],
                            'sales_invoice_no': sales['invoice_number'],
                            'sales_amount': sales_amt,
                            'sales_date': sales['issue_date'],
                            'customer_name': sales['customer_name'],
                            'profit_loss': profit_loss,
                            'profit_margin': profit_margin,
                            'status': 'PROFITABLE' if profit_loss > 0 else 'LOSS' if profit_loss < 0 else 'BREAK_EVEN'
                        }
                        
                        matches.append(match)
                        matched_sales.add(sales['invoice_id'])
                        break  # Bu alış faturası için eşleşme bulundu, diğer IRS'lere bakmaya gerek yok
        
        self.matches = matches
        print(f"\n✅ {len(matches)} eşleşme bulundu")
        
        return matches
    
    def save_matches_to_db(self, matches: List[Dict] = None) -> int:
        """
        Eşleşmeleri veritabanına kaydet
        
        Args:
            matches: Eşleşmeler listesi (None ise self.matches kullanılır)
            
        Returns:
            Kaydedilen eşleşme sayısı
        """
        if matches is None:
            matches = self.matches
        
        if not matches:
            print("⚠️  Kaydedilecek eşleşme yok")
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Önce mevcut eşleşmeleri temizle
        cursor.execute("DELETE FROM irs_matching")
        
        saved_count = 0
        for match in matches:
            try:
                cursor.execute("""
                    INSERT INTO irs_matching (
                        irs_number, purchase_invoice_id, sales_invoice_id,
                        purchase_amount, sales_amount, profit_loss, profit_margin, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    match['irs_number'],
                    match['purchase_invoice_id'],
                    match['sales_invoice_id'],
                    match['purchase_amount'],
                    match['sales_amount'],
                    match['profit_loss'],
                    match['profit_margin'],
                    match['status']
                ))
                saved_count += 1
            except Exception as e:
                print(f"⚠️  Eşleşme kaydedilemedi: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"💾 {saved_count} eşleşme veritabanına kaydedildi")
        return saved_count
    
    def generate_report(self, matches: List[Dict] = None) -> Dict:
        """
        Eşleşmelerden detaylı rapor üret
        
        Args:
            matches: Eşleşmeler listesi (None ise self.matches kullanılır)
            
        Returns:
            Rapor dictionary'si
        """
        if matches is None:
            matches = self.matches
        
        if not matches:
            return {
                'total_matches': 0,
                'profitable_count': 0,
                'loss_count': 0,
                'break_even_count': 0,
                'total_profit': 0,
                'total_loss': 0,
                'net_profit': 0,
                'avg_profit_margin': 0,
                'matches': []
            }
        
        # İstatistikler
        profitable = [m for m in matches if m['profit_loss'] > 0]
        loss_making = [m for m in matches if m['profit_loss'] < 0]
        break_even = [m for m in matches if m['profit_loss'] == 0]
        
        total_profit = sum(m['profit_loss'] for m in profitable)
        total_loss = sum(abs(m['profit_loss']) for m in loss_making)
        net_profit = total_profit - total_loss
        avg_margin = sum(m['profit_margin'] for m in matches) / len(matches)
        
        report = {
            'total_matches': len(matches),
            'profitable_count': len(profitable),
            'loss_count': len(loss_making),
            'break_even_count': len(break_even),
            'total_profit': total_profit,
            'total_loss': total_loss,
            'net_profit': net_profit,
            'avg_profit_margin': avg_margin,
            'matches': matches
        }
        
        return report
    
    def print_report(self, report: Dict = None):
        """Raporu console'a yazdır"""
        if report is None:
            report = self.generate_report()
        
        print("\n" + "=" * 80)
        print("📊 İRSALİYE EŞLEŞTİRME VE KAR/ZARAR RAPORU")
        print("=" * 80)
        
        print(f"\n📈 GENEL DURUM:")
        print(f"   Toplam Eşleşme: {report['total_matches']}")
        print(f"   🟢 Karlı İşlemler: {report['profitable_count']}")
        print(f"   🔴 Zararlı İşlemler: {report['loss_count']}")
        print(f"   ⚪ Başabaş: {report['break_even_count']}")
        
        print(f"\n💰 FİNANSAL ÖZET:")
        print(f"   Toplam Kar: {report['total_profit']:,.2f} TRY")
        print(f"   Toplam Zarar: {report['total_loss']:,.2f} TRY")
        print(f"   Net Kar: {report['net_profit']:,.2f} TRY")
        print(f"   Ortalama Kar Marjı: {report['avg_profit_margin']:.2f}%")
        
        # Detaylı liste (ilk 20)
        if report['matches']:
            print("\n" + "=" * 80)
            print("📋 DETAYLI LİSTE (İlk 20 Eşleşme)")
            print("=" * 80)
            
            for i, m in enumerate(report['matches'][:20], 1):
                profit_emoji = "🟢" if m['profit_loss'] > 0 else "🔴" if m['profit_loss'] < 0 else "⚪"
                
                print(f"\n{i}. İrsaliye: {m['irs_number']} (Normalize: {m['irs_normalized']})")
                print(f"   Alış: {m['purchase_invoice_no']} - {m['purchase_amount']:,.2f} TRY")
                print(f"         Tedarikçi: {m['supplier_name']} ({m['supplier']}) - Tarih: {m['purchase_date']}")
                print(f"   Satış: {m['sales_invoice_no']} - {m['sales_amount']:,.2f} TRY")
                print(f"         Müşteri: {m['customer_name']} - Tarih: {m['sales_date']}")
                print(f"   {profit_emoji} Kar/Zarar: {m['profit_loss']:,.2f} TRY ({m['profit_margin']:.2f}%)")
        
        print("\n" + "=" * 80)
    
    def run_full_analysis(self) -> Dict:
        """Tam analiz: eşleştir, kaydet, raporla"""
        print("\n" + "=" * 80)
        print("İRSALİYE EŞLEŞTİRME VE KAR/ZARAR ANALİZİ - BAŞLATILIYOR")
        print("=" * 80)
        print(f"\n📁 Veritabanı: {self.db_path}")
        
        # 1. Eşleşmeleri bul
        matches = self.find_matches()
        
        # 2. Veritabanına kaydet
        if matches:
            self.save_matches_to_db(matches)
        
        # 3. Rapor üret
        report = self.generate_report(matches)
        
        # 4. Raporu yazdır
        self.print_report(report)
        
        print("\n✅ Analiz tamamlandı!")
        print(f"💾 Veriler 'irs_matching' tablosuna kaydedildi")
        
        return report


def main():
    """Ana fonksiyon"""
    matcher = IRSMatcher()
    report = matcher.run_full_analysis()
    
    # Sonuç kodu döndür
    if report['total_matches'] > 0:
        print(f"\n🎉 {report['total_matches']} eşleşme başarıyla işlendi!")
        return 0
    else:
        print("\n⚠️  Hiç eşleşme bulunamadı. Description alanlarını kontrol edin.")
        return 1


if __name__ == '__main__':
    exit(main())

