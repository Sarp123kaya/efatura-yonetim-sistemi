#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finansal Takip Sistemi - Backend Kurulum ve Test Script
========================================================

Bu script tüm finansal backend sistemini kurur ve test eder:
1. Database migration
2. IRS matching
3. Payment tracking test
4. Debt/Receivables analysis
5. Balance calculation
6. Snapshot creation

Kullanım:
    python3 setup_financial_backend.py
"""

import sys
import os
from pathlib import Path

# Proje kök dizinini sys.path'e ekle
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    """Başlık yazdır"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def run_migration():
    """Database migration'ı çalıştır"""
    print_header("ADIM 1: DATABASE MIGRATION")
    
    try:
        from src.database.schema_migration import DatabaseMigration
        
        migration = DatabaseMigration()
        success = migration.run_migration()
        
        if success:
            print("\n✅ Migration başarılı!")
            return True
        else:
            print("\n❌ Migration başarısız!")
            return False
    
    except Exception as e:
        print(f"\n❌ Migration hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_irs_matching():
    """IRS eşleştirme analizi çalıştır"""
    print_header("ADIM 2: IRS EŞLEŞTİRME VE KAR/ZARAR ANALİZİ")
    
    try:
        from src.financial.irs_matcher import IRSMatcher
        
        matcher = IRSMatcher()
        report = matcher.run_full_analysis()
        
        if report['total_matches'] > 0:
            print(f"\n✅ {report['total_matches']} eşleşme bulundu ve kaydedildi!")
            return True
        else:
            print("\n⚠️  Hiç eşleşme bulunamadı (bu normal olabilir)")
            return True  # Eşleşme olmaması hata değil
    
    except Exception as e:
        print(f"\n❌ IRS matching hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_debt_analysis():
    """Borç/Alacak analizi çalıştır"""
    print_header("ADIM 3: BORÇ/ALACAK ANALİZİ")
    
    try:
        from src.financial.debt_tracker import DebtTracker
        
        dt = DebtTracker()
        dt.print_full_report()
        
        print("\n✅ Borç/Alacak analizi tamamlandı!")
        return True
    
    except Exception as e:
        print(f"\n❌ Debt tracking hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_balance_calculation():
    """Bilanço hesaplama ve snapshot"""
    print_header("ADIM 4: BİLANÇO HESAPLAMA VE SNAPSHOT")
    
    try:
        from src.financial.balance_calculator import BalanceCalculator
        
        bc = BalanceCalculator()
        
        # Mevcut durumu hesapla
        balance = bc.calculate_current_balance()
        bc.print_balance_sheet(balance)
        
        # Snapshot kaydet
        snapshot_id = bc.save_snapshot()
        
        print(f"\n✅ Bilanço hesaplandı ve snapshot kaydedildi (ID: {snapshot_id})!")
        return True
    
    except Exception as e:
        print(f"\n❌ Balance calculation hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_payment_test():
    """Ödeme sistemi testi"""
    print_header("ADIM 5: ÖDEME SİSTEMİ TEST")
    
    try:
        from src.financial.payment_manager import PaymentManager
        
        pm = PaymentManager()
        pm.print_payment_summary()
        
        print("\n💡 Ödeme eklemek için:")
        print("   from src.financial.payment_manager import PaymentManager")
        print("   pm = PaymentManager()")
        print("   pm.add_payment(invoice_id=123, amount=5000, payment_method='BANK_TRANSFER')")
        
        print("\n✅ Ödeme sistemi hazır!")
        return True
    
    except Exception as e:
        print(f"\n❌ Payment system hatası: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_final_summary(results: dict):
    """Son özet raporu"""
    print_header("FİNANSAL BACKEND KURULUM SONUCU")
    
    print("Adımlar:")
    for step, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {step}")
    
    all_success = all(results.values())
    
    if all_success:
        print("\n" + "=" * 80)
        print("🎉 TÜM SİSTEM BAŞARIYLA KURULDU VE TEST EDİLDİ!")
        print("=" * 80)
        print("\n📚 KULLANIM KILAVUZU:")
        print("\n1. İrsaliye Eşleştirme:")
        print("   python3 src/financial/irs_matcher.py")
        
        print("\n2. Borç/Alacak Takibi:")
        print("   python3 src/financial/debt_tracker.py")
        
        print("\n3. Bilanço Hesaplama:")
        print("   python3 src/financial/balance_calculator.py")
        
        print("\n4. Ödeme Ekleme (Python'da):")
        print("   from src.financial.payment_manager import PaymentManager")
        print("   pm = PaymentManager()")
        print("   pm.add_payment(invoice_id=X, amount=Y, payment_method='BANK_TRANSFER')")
        
        print("\n📊 Veritabanı Tabloları:")
        print("   - invoices (güncellenmiş: invoice_type, payment_status, vb.)")
        print("   - irs_matching (kar/zarar eşleştirmeleri)")
        print("   - payment_records (ödeme kayıtları)")
        print("   - balance_snapshots (bilanço snapshot'ları)")
        print("   - line_matching (satır bazında eşleştirme)")
        
        print("\n🔄 Sonraki Adımlar:")
        print("   1. Dashboard güncellemesi (frontend)")
        print("   2. Otomatik raporlama sistemi")
        print("   3. Vade uyarı sistemi")
        print("   4. Email/SMS bildirimleri")
        
    else:
        print("\n" + "=" * 80)
        print("⚠️  BAZI ADIMLAR BAŞARISIZ OLDU")
        print("=" * 80)
        print("\nLütfen yukarıdaki hata mesajlarını kontrol edin.")
        print("Hata giderildi mi kontrol etmek için tekrar çalıştırabilirsiniz.")
    
    print("\n" + "=" * 80)


def main():
    """Ana fonksiyon"""
    print("\n" + "=" * 80)
    print("  FİNANSAL TAKİP SİSTEMİ - BACKEND KURULUM")
    print("=" * 80)
    print("\nBu script şunları yapacak:")
    print("  1. ✅ Database migration (yeni tablolar ve sütunlar)")
    print("  2. ✅ IRS eşleştirme ve kar/zarar analizi")
    print("  3. ✅ Borç/Alacak analizi")
    print("  4. ✅ Bilanço hesaplama")
    print("  5. ✅ Ödeme sistemi kontrolü")
    print("\n" + "=" * 80)
    
    response = input("\nDevam etmek istiyor musunuz? (y/N): ")
    if response.lower() != 'y':
        print("\n❌ Kurulum iptal edildi")
        return
    
    # Adımları çalıştır
    results = {}
    
    # 1. Migration
    results['Database Migration'] = run_migration()
    if not results['Database Migration']:
        print("\n❌ Migration başarısız, diğer adımlar atlanıyor.")
        print_final_summary(results)
        return
    
    # 2. IRS Matching
    results['IRS Matching'] = run_irs_matching()
    
    # 3. Debt Analysis
    results['Debt Analysis'] = run_debt_analysis()
    
    # 4. Balance Calculation
    results['Balance Calculation'] = run_balance_calculation()
    
    # 5. Payment Test
    results['Payment System'] = run_payment_test()
    
    # Son özet
    print_final_summary(results)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Kullanıcı tarafından iptal edildi")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

