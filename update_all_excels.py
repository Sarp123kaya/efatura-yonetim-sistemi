#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tüm Excel Dosyalarını Güncelleme Script'i
==========================================

Bu script tüm veritabanlarından (akgips, api, birlesik, fullboard) 
Excel dosyalarını tek seferde oluşturur/günceller.

İlk 3 Excel oluşturulduktan sonra API'den veri çeker ve API Excel'i oluşturur.

Kullanım:
    python3 update_all_excels.py
    python3 update_all_excels.py --skip-api  # API veri çekmeyi atla
"""

import sys
from pathlib import Path
from datetime import datetime

# Proje kök dizinini ayarla
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

def print_header(text):
    """Başlık yazdır"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def print_step(number, total, name):
    """Adım başlığı yazdır"""
    print(f"\n[{number}/{total}] {name}...")
    print("-" * 80)

def fetch_api_data():
    """API'den fatura verilerini çek"""
    print("\n" + "🌐" * 40)
    print("  API'DEN VERİ ÇEKME")
    print("🌐" * 40)
    
    try:
        from api.api_data_extractor import IsbasiAPIDataExtractor
        
        print("\n📱 İşbaşı API'sinden fatura verileri çekiliyor...")
        
        # API extractor'ı başlat
        extractor = IsbasiAPIDataExtractor()
        
        # secure_login() metodunu kullan (şifre içeride sorulur)
        login_success = extractor.secure_login()
        
        if not login_success:
            print("⚠️  API girişi başarısız, veri çekme atlanıyor")
            return False
        
        print("✅ API girişi başarılı!")
        
        # Faturaları çek (giden + gelen birlikte)
        print("\n📦 Faturalar çekiliyor (giden + gelen)...")
        success = extractor.fetch_invoices()
        
        if success:
            print(f"✅ API'den faturalar başarıyla çekildi ve veritabanına kaydedildi!")
            return True
        else:
            print("⚠️  API'den fatura çekilemedi veya yeni fatura bulunamadı")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Şifre girişi iptal edildi")
        return False
    except Exception as e:
        print(f"\n❌ API veri çekme hatası: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def update_all_excels(skip_api_fetch=False):
    """Tüm Excel dosyalarını güncelle"""
    start_time = datetime.now()
    
    print_header("TÜM EXCEL DOSYALARINI GÜNCELLEME")
    print(f"Başlangıç Zamanı: {start_time.strftime('%H:%M:%S')}")
    
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    # İlk 3 exporter (API hariç)
    first_exporters = [
        ('akgips', 'data/db/akgips.db'),
        ('birlesik', 'data/db/birlesik.db'),
        ('fullboard', 'data/db/fullboard.db')
    ]
    
    # Toplam adım sayısı (3 export + API çekme + API export)
    total_steps = 5 if not skip_api_fetch else 4
    current_step = 0
    
    # İlk 3 Excel'i oluştur
    for name, db_path in first_exporters:
        current_step += 1
        db_file = project_root / db_path
        
        # Veritabanı kontrolü
        if not db_file.exists():
            print_step(current_step, total_steps, f"{name.upper()} - ATLANDI")
            print(f"⚠️  Veritabanı bulunamadı: {db_path}")
            results['skipped'].append(name)
            continue
        
        print_step(current_step, total_steps, f"{name.upper()} Excel Export")
        
        try:
            if name == 'akgips':
                from exporters.akgips_exporter import create_excel_export
            elif name == 'birlesik':
                from exporters.birlesik_exporter import create_excel_export
            elif name == 'fullboard':
                from exporters.fullboard_exporter import create_excel_export
            
            filename = create_excel_export()
            results['success'].append(name)
            print(f"✅ {name} Excel dosyası başarıyla oluşturuldu!")
            
        except Exception as e:
            results['failed'].append(name)
            print(f"❌ HATA ({name}): {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    # API'den veri çek (opsiyonel)
    api_data_fetched = False
    if not skip_api_fetch:
        current_step += 1
        print_step(current_step, total_steps, "API'DEN VERİ ÇEKME")
        api_data_fetched = fetch_api_data()
        if api_data_fetched:
            results['success'].append('api_fetch')
    
    # API Excel export
    current_step += 1
    print_step(current_step, total_steps, "API Excel Export")
    
    db_file = project_root / 'data/db/api.db'
    
    if not db_file.exists():
        print(f"⚠️  API veritabanı bulunamadı: data/db/api.db")
        results['skipped'].append('api')
    else:
        try:
            from exporters.api_exporter import export_api_to_excel
            success = export_api_to_excel()
            if success:
                results['success'].append('api')
                print(f"✅ API Excel dosyası başarıyla oluşturuldu!")
            else:
                results['failed'].append('api')
                print(f"❌ API Excel dosyası oluşturulamadı!")
        except Exception as e:
            results['failed'].append('api')
            print(f"❌ HATA (api): {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    # Özet Rapor
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print_header("ÖZET RAPOR")
    print(f"\n⏱️  Toplam Süre: {duration:.2f} saniye")
    print(f"\n📊 Sonuçlar:")
    print(f"  ✅ Başarılı: {len(results['success'])} işlem")
    if results['success']:
        for name in results['success']:
            label = {
                'akgips': '📄 AK GİPS Excel',
                'birlesik': '📄 Birleşik Excel',
                'fullboard': '📄 FULLBOARD Excel',
                'api': '📄 API Excel',
                'api_fetch': '🌐 API Veri Çekme'
            }.get(name, name)
            print(f"     - {label}")
    
    if results['failed']:
        print(f"\n  ❌ Başarısız: {len(results['failed'])}")
        for name in results['failed']:
            print(f"     - {name}")
    
    if results['skipped']:
        print(f"\n  ⚠️  Atlanan: {len(results['skipped'])}")
        for name in results['skipped']:
            print(f"     - {name}")
    
    print("\n" + "=" * 80)
    
    # Çıkış kodu
    if results['failed']:
        return 1
    return 0

def main():
    """Ana fonksiyon"""
    try:
        # Komut satırı argümanlarını kontrol et
        skip_api_fetch = '--skip-api' in sys.argv
        
        if skip_api_fetch:
            print("ℹ️  API veri çekme atlanacak (--skip-api bayrağı aktif)")
        
        # Gerekli kütüphaneleri kontrol et
        try:
            import openpyxl
        except ImportError:
            print("📦 openpyxl kütüphanesi yükleniyor...")
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'openpyxl'])
            import openpyxl
        
        try:
            import pandas
        except ImportError:
            print("📦 pandas kütüphanesi yükleniyor...")
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pandas', 'xlsxwriter'])
            import pandas
        
        # Excel'leri güncelle
        return update_all_excels(skip_api_fetch=skip_api_fetch)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  İşlem kullanıcı tarafından iptal edildi!")
        return 130
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        import traceback
        print(traceback.format_exc())
        return 1

if __name__ == '__main__':
    sys.exit(main())

