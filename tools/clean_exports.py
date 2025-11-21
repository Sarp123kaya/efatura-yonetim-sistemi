#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kayıtlar Klasörünü Temizleme Script
"""

import os
import glob
from datetime import datetime

def temizle_kayitlar():
    """kayıtlar klasöründeki tüm Excel dosyalarını siler"""
    
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    kayitlar_path = 'data/excel'
    
    # Klasör var mı kontrol et
    if not os.path.exists(kayitlar_path):
        print(f"❌ '{kayitlar_path}' klasörü bulunamadı!")
        return
    
    # Excel dosyalarını bul
    excel_files = glob.glob(f'{kayitlar_path}/*.xlsx')
    
    # Geçici dosyaları da bul (Excel açıkken oluşan ~$ ile başlayanlar)
    temp_files = glob.glob(f'{kayitlar_path}/~$*.xlsx')
    
    all_files = excel_files + temp_files
    
    if not all_files:
        print(f"✓ '{kayitlar_path}' klasörü zaten temiz (dosya bulunamadı)")
        return
    
    print("=" * 70)
    print("KAYITLAR KLASÖRÜ TEMİZLEME")
    print("=" * 70)
    print()
    print(f"📁 Silinecek dosya sayısı: {len(all_files)}")
    print()
    
    # Onay iste
    for f in all_files:
        file_size = os.path.getsize(f) / 1024  # KB cinsinden
        mod_time = datetime.fromtimestamp(os.path.getmtime(f))
        print(f"  • {os.path.basename(f)} ({file_size:.1f} KB) - {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print()
    response = input("⚠️  Tüm dosyaları silmek istediğinizden emin misiniz? (evet/hayır): ")
    
    if response.lower() in ['evet', 'e', 'yes', 'y']:
        deleted_count = 0
        for f in all_files:
            try:
                os.remove(f)
                print(f"  ✓ Silindi: {os.path.basename(f)}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ Hata: {os.path.basename(f)} - {str(e)}")
        
        print()
        print("=" * 70)
        print(f"✓ Temizleme tamamlandı! {deleted_count}/{len(all_files)} dosya silindi.")
        print("=" * 70)
    else:
        print()
        print("❌ İşlem iptal edildi. Hiçbir dosya silinmedi.")

def en_yenisini_tut():
    """En yeni Excel dosyasını tutar, diğerlerini siler"""
    
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    kayitlar_path = 'data/excel'
    
    if not os.path.exists(kayitlar_path):
        print(f"❌ '{kayitlar_path}' klasörü bulunamadı!")
        return
    
    excel_files = glob.glob(f'{kayitlar_path}/efatura_veritabani_*.xlsx')
    
    if len(excel_files) <= 1:
        print(f"✓ Silinecek eski dosya yok ({len(excel_files)} dosya)")
        return
    
    # Dosyaları değişiklik tarihine göre sırala
    excel_files.sort(key=os.path.getmtime, reverse=True)
    
    newest_file = excel_files[0]
    old_files = excel_files[1:]
    
    print("=" * 70)
    print("EN YENİSİNİ TUT - ESKİLERİ SİL")
    print("=" * 70)
    print()
    print(f"✓ Tutulacak: {os.path.basename(newest_file)}")
    print(f"  Tarih: {datetime.fromtimestamp(os.path.getmtime(newest_file)).strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"📁 Silinecek eski dosya sayısı: {len(old_files)}")
    print()
    
    for f in old_files:
        mod_time = datetime.fromtimestamp(os.path.getmtime(f))
        print(f"  • {os.path.basename(f)} - {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print()
    response = input("⚠️  Eski dosyaları silmek istediğinizden emin misiniz? (evet/hayır): ")
    
    if response.lower() in ['evet', 'e', 'yes', 'y']:
        deleted_count = 0
        for f in old_files:
            try:
                os.remove(f)
                print(f"  ✓ Silindi: {os.path.basename(f)}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ Hata: {os.path.basename(f)} - {str(e)}")
        
        print()
        print("=" * 70)
        print(f"✓ Temizleme tamamlandı! {deleted_count} eski dosya silindi.")
        print("=" * 70)
    else:
        print()
        print("❌ İşlem iptal edildi. Hiçbir dosya silinmedi.")

def main():
    """Ana menü"""
    print()
    print("=" * 70)
    print(" " * 20 + "KAYITLAR KLASÖRÜ YÖNETİMİ")
    print("=" * 70)
    print()
    print("1. Tüm Excel dosyalarını sil")
    print("2. En yenisini tut, eskileri sil")
    print("3. İptal")
    print()
    
    choice = input("Seçiminiz (1-3): ")
    print()
    
    if choice == '1':
        temizle_kayitlar()
    elif choice == '2':
        en_yenisini_tut()
    elif choice == '3':
        print("İşlem iptal edildi.")
    else:
        print("❌ Geçersiz seçim!")

if __name__ == '__main__':
    main()

