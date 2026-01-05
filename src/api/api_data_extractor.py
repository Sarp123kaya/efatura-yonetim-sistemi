#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Fatura Çekme Modülü
=======================

İşbaşı API'sinden sadece fatura verilerini (giden ve gelen) çeker
ve Excel dosyalarına kaydeder.

Özellikler:
- Güvenli şifre girişi
- Sayfalama ile veri çekme
- Giden ve gelen fatura desteği
- Excel formatlaması
"""

import requests
import pandas as pd
import os
import sys
import time
import sqlite3
import re
from datetime import datetime
from pathlib import Path
import getpass
import logging
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Proje kök dizinini sys.path'e ekle
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# API Database modülünü import et
from src.api.api_database import APIDatabase

# Logging konfigürasyonu
# Log dosyasını proje kök dizinine yerleştir
log_file = project_root / "data" / "logs" / "api_extraction.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class IsbasiAPIDataExtractor:
    """
    İşbaşı API'sinden veri çekme sınıfı
    
    API bağlantısı, veri çekme, sayfalama ve Excel kaydetme işlemlerini yönetir.
    """
    
    def __init__(self):
        """API extractor sınıfını başlatır"""
        self.session = requests.Session()
        # Güvenlik: API bilgileri repoya hardcode edilmez, ortam değişkenlerinden alınır.
        # Gerekli değişkenler: ISBASI_API_KEY, ISBASI_USERNAME
        self.base_url = os.getenv("ISBASI_BASE_URL", "https://mw-jplatform.isbasi.com").rstrip("/")
        self.api_key = os.getenv("ISBASI_API_KEY")
        self.username = os.getenv("ISBASI_USERNAME")
        self.password = None
        self.verify_ssl = os.getenv("ISBASI_VERIFY_SSL", "true").strip().lower() in ("1", "true", "yes", "y", "on")
        self.timeout = 30

        if not self.api_key or not self.username:
            print("❌ Eksik konfigürasyon: ISBASI_API_KEY ve ISBASI_USERNAME ortam değişkenleri tanımlı olmalı.")
            print("   Örnek: cp .env.example .env  (sonra .env içini doldurun)")
            raise SystemExit(2)
        
        # Session ayarları
        self.session.verify = self.verify_ssl
        self.access_token = None
        
        # Kullanıcı bilgileri
        self.user_id = None
        self.user_email = None
        self.tenant_id = None
        self.user_name = None
        
        # Header'ları ayarla
        self.session.headers.update({
            'ApiKey': self.api_key,
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'XML-Processing-System/1.0',
            'Accept': 'application/json',
            'DeviceName': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Lang': 'tr-TR',
            'DeviceType': 'WEB'
        })
        
        # API endpoint'leri (sadece faturalar)
        self.endpoints = {
            'login': '/api/v1.0/user/integrationLogin',
            'invoices': '/api/v1.0/invoices/invoices'
        }
        
        # Excel dosya yolları (sadece faturalar)
        # Proje kök dizinini bul
        project_root = Path(__file__).resolve().parent.parent.parent
        self.output_dir = project_root / "data" / "excel" / "api"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.excel_files = {
            'invoices': self.output_dir / "API_Giden_Faturalar.xlsx",
            'incoming_invoices': self.output_dir / "API_Gelen_Faturalar.xlsx"
        }
        
        # API veritabanı (kendi ayrı DB'si)
        self.api_db = APIDatabase()
        self.db_path = self.api_db.db_path
        
        # Sayfalama parametreleri
        self.pagination_config = {
            'page_size': 100,
            'max_pages': 50,
            'delay_between_requests': 0.5
        }
        
        # Fatura numarası filtresi kaldırıldı (HTTP 500 hatası veriyordu)
        # Bunun yerine sadece giden faturaları çek (PURCHASE_INVOICE hariç)
        self.only_outgoing = True  # Sadece giden faturalar
        
        logger.info("API Data Extractor başlatıldı")
        logger.info(f"Hedef veritabanı: {self.db_path}")
        logger.info(f"Fatura tipi: Sadece GİDEN faturalar (PURCHASE_INVOICE hariç)")
    
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
        if not description or pd.isna(description):
            return ""
        
        # String'e çevir
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
    
    def secure_login(self) -> bool:
        """
        Güvenli API girişi yapar
        
        Returns:
            bool: Giriş başarılı ise True, değilse False
        """
        try:
            print("🔐 İşbaşı API - Güvenli Giriş")
            print("-" * 40)
            print(f"👤 Kullanıcı: {self.username}")
            
            # Şifreyi güvenli bir şekilde al
            self.password = getpass.getpass("🔑 Şifre: ")
            if not self.password.strip():
                print("❌ Şifre boş olamaz!")
                return False
            
            # Login payload'ı hazırla
            login_data = {
                "username": self.username,
                "password": self.password
            }
            
            # API'ye login isteği gönder
            response = self.session.post(
                f"{self.base_url}{self.endpoints['login']}",
                json=login_data,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            
            if response.status_code == 200:
                # Türkçe karakter desteği için encoding'i zorla UTF-8 yap
                response.encoding = 'utf-8'
                response_data = response.json()
                data = response_data.get('data', {})
                self.access_token = data.get('accessToken')
                
                # Kullanıcı bilgilerini çek
                self.user_id = data.get('id') or data.get('userId')
                self.user_email = data.get('email') or self.username
                self.tenant_id = data.get('tenantId')
                self.user_name = data.get('userName') or data.get('name')
                
                if self.access_token:
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.access_token}'
                    })
                    
                    # İrsaliye için gereken ek header'ları ekle
                    if self.user_id:
                        self.session.headers.update({'UserId': str(self.user_id)})
                    if self.user_email:
                        self.session.headers.update({'UserEmail': self.user_email})
                    if self.tenant_id:
                        self.session.headers.update({'tenantId': str(self.tenant_id)})
                    if self.user_name:
                        self.session.headers.update({'UserName': self.user_name})
                        
                    logger.info("✅ API girişi başarılı!")
                    logger.info(f"👤 Kullanıcı ID: {self.user_id}")
                    return True
            
            logger.error(f"❌ Login başarısız: {response.status_code}")
            return False
                
        except KeyboardInterrupt:
            print("\n❌ İşlem iptal edildi.")
            return False
        except Exception as e:
            logger.error(f"❌ Login hatası: {e}")
            return False
        finally:
            # Güvenlik: Şifreyi bellekten temizle
            self.password = None
    
    def fetch_data_with_pagination(self, endpoint: str, data_type: str, only_outgoing: bool = False) -> Tuple[bool, List[Dict]]:
        """
        Sayfalama ile veri çeker
        
        Args:
            endpoint: API endpoint'i
            data_type: Veri türü (customers, invoices, products)
            only_outgoing: Sadece giden faturaları çek (PURCHASE_INVOICE hariç)
            
        Returns:
            Tuple[bool, List[Dict]]: (başarı durumu, veri listesi)
        """
        all_data = []
        page = 1
        total_pages = 0
        
        if only_outgoing:
            print(f"📊 {data_type.upper()} verileri çekiliyor (sadece GİDEN faturalar)...")
        else:
            print(f"📊 {data_type.upper()} verileri çekiliyor...")
        
        try:
            while page <= self.pagination_config['max_pages']:
                # API filtreleri HTTP 500 hatası veriyor
                # Bunun yerine tüm verileri çek, sonra Python'da filtrele
                
                # GİB API yapısına uygun format - FİLTRESİZ
                payload = {
                        "filters": [],
                        "sorting": {},
                        "paging": {
                            "currentPage": page,
                            "pageSize": self.pagination_config['page_size']
                        },
                        "count": True,
                        "excel": {
                            "export": False,
                            "allowedColumns": None,
                            "lucaExport": False
                        }
                }
                
                response = self.session.post(
                    f"{self.base_url}{endpoint}",
                    json=payload,
                    timeout=self.timeout,
                    verify=self.verify_ssl
                )
                
                if response.status_code != 200:
                    if response.status_code == 401:
                        logger.error("❌ Yetkilendirme hatası")
                        return False, []
                    logger.error(f"❌ HTTP {response.status_code}")
                    break
                
                # Türkçe karakter desteği için encoding'i zorla UTF-8 yap
                response.encoding = 'utf-8'
                response_data = response.json()
                
                # Veri yapısını analiz et
                page_data = []
                if isinstance(response_data, dict):
                    if 'data' in response_data and isinstance(response_data['data'], dict):
                        page_data = response_data['data'].get('data', [])
                        page_count = response_data['data'].get('count', 0)
                        if page == 1:
                            total_pages = page_count
                    elif 'data' in response_data:
                        page_data = response_data['data']
                        
                    # Sayfa bilgilerini al
                    if 'totalPages' in response_data:
                        total_pages = response_data['totalPages']
                    elif 'pageCount' in response_data:
                        total_pages = response_data['pageCount']
                        
                elif isinstance(response_data, list):
                    page_data = response_data
                
                if not page_data:
                    logger.info(f"📄 Sayfa {page} boş - veri çekme tamamlandı")
                    break
                
                # Metin alanlarını string olarak zorla (sıfırları korumak için)
                for item in page_data:
                    if isinstance(item, dict):
                        # Description, invoiceNumber, firmName vb. metin alanlarını string'e çevir
                        text_fields = ['description', 'invoiceNumber', 'firmName', 'id']
                        for field in text_fields:
                            if field in item and item[field] is not None:
                                item[field] = str(item[field])
                
                # Python tarafında filtrele (API filtresi HTTP 500 veriyor)
                if only_outgoing and data_type in ['all_invoices', 'invoices']:
                    # Sadece giden faturaları al (PURCHASE_INVOICE hariç)
                    original_count = len(page_data)
                    page_data = [item for item in page_data if item.get('type') != 'PURCHASE_INVOICE']
                    filtered_count = len(page_data)
                    if original_count != filtered_count:
                        logger.info(f"   🔍 Filtreleme: {original_count} kayıt → {filtered_count} giden fatura")
                
                all_data.extend(page_data)
                print(f"   📄 Sayfa {page}: {len(page_data)} kayıt (giden faturalar)")
                
                # Toplam sayfa sayısını kontrol et
                if total_pages > 0 and page >= total_pages:
                    logger.info(f"📄 Son sayfa ({total_pages}) ulaşıldı")
                    break
                
                page += 1
                time.sleep(self.pagination_config['delay_between_requests'])
            
            print(f"✅ {data_type.upper()} verileri tamamlandı: {len(all_data)} kayıt")
            return True, all_data
            
        except Exception as e:
            logger.error(f"❌ {data_type} veri çekme hatası: {e}")
            return False, []
    
    def fetch_invoices(self) -> bool:
        """Sadece giden faturaları çeker (PURCHASE_INVOICE hariç)"""
        success, invoices_data = self.fetch_data_with_pagination(
            self.endpoints['invoices'], 
            'all_invoices',
            only_outgoing=self.only_outgoing
        )
        
        if success and invoices_data:
            # Hem Excel hem de veritabanına kaydet
            excel_ok = self.save_all_invoices_to_excel(invoices_data)
            db_ok = self.save_invoices_to_api_database(invoices_data)
            return excel_ok and db_ok
        return False
    
    
    def save_all_invoices_to_excel(self, invoices_data: List[Dict]) -> bool:
        """
        Tüm faturaları Excel'e kaydeder (giden + gelen birlikte)
        Sadece 8 sütun: id, date, invoiceNumber, totalTL, taxableAmount, firmName, description, type
        """
        try:
            # DataFrame oluştururken metin sütunlarını string olarak zorla
            df = pd.DataFrame(invoices_data)
            
            # Metin sütunlarını string'e çevir (sıfırları korumak için)
            text_columns = ['invoiceNumber', 'description', 'firmName']
            for col in text_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
            
            # Sadece istenen 8 sütunu al (type eklendi)
            required_columns = ['id', 'date', 'invoiceNumber', 'totalTL', 'taxableAmount', 'firmName', 'description', 'type']
            available_columns = [col for col in required_columns if col in df.columns]
            
            if not available_columns:
                logger.warning("⚠️ Gerekli sütunlar bulunamadı")
                available_columns = df.columns.tolist()
            
            df_filtered = df[available_columns].copy()
            
            # Description alanından banka bilgilerini temizle
            if 'description' in df_filtered.columns:
                logger.info("🧹 Description alanındaki banka bilgileri temizleniyor...")
                df_filtered['description'] = df_filtered['description'].apply(
                    self.clean_bank_info_from_description
                )
                logger.info("✅ Banka bilgileri temizlendi")
            
            # Excel'e kaydet
            with pd.ExcelWriter(self.excel_files['invoices'], engine='xlsxwriter') as writer:
                workbook = writer.book
                
                header_format = workbook.add_format({
                    'bold': True,
                    'fg_color': '#D7E4BC',
                    'border': 1
                })
                
                currency_format = workbook.add_format({
                    'num_format': '#,##0.00 ₺',
                    'border': 1
                })
                
                date_format = workbook.add_format({
                    'num_format': 'dd.mm.yyyy',
                    'border': 1
                })
                
                text_format = workbook.add_format({
                    'border': 1,
                    'text_wrap': False
                })
                
                # Metin sütunları için @ formatı (string olarak tutulması için)
                text_only_format = workbook.add_format({
                    'num_format': '@',
                    'border': 1
                })
                
                df_filtered.to_excel(writer, index=False, sheet_name='Tum_Faturalar')
                worksheet = writer.sheets['Tum_Faturalar']
                
                # Header formatını uygula
                for col_num, value in enumerate(df_filtered.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Sütun genişliklerini ve formatlarını ayarla
                for i, col in enumerate(df_filtered.columns):
                    if col in ['totalTL', 'taxableAmount']:
                        worksheet.set_column(i, i, 18, currency_format)
                    elif col == 'date':
                        worksheet.set_column(i, i, 15, date_format)
                    elif col == 'description':
                        worksheet.set_column(i, i, 50, text_only_format)
                    elif col in ['invoiceNumber', 'firmName', 'id', 'type']:
                        # Bu sütunları metin olarak formatla (sıfırları korumak için)
                        column_len = max(df_filtered[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(column_len + 2, 40), text_only_format)
                    else:
                        column_len = max(df_filtered[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(column_len + 2, 40), text_format)
                
                # İstatistikler ekle
                last_row = len(df_filtered) + 1
                
                # Type bazlı sayılar
                if 'type' in df_filtered.columns:
                    giden = len(df_filtered[df_filtered['type'] != 'PURCHASE_INVOICE'])
                    gelen = len(df_filtered[df_filtered['type'] == 'PURCHASE_INVOICE'])
                    worksheet.write(last_row + 2, 0, f'Toplam Fatura: {len(df_filtered)}', header_format)
                    worksheet.write(last_row + 3, 0, f'  🟢 Giden: {giden}', header_format)
                    worksheet.write(last_row + 4, 0, f'  🔴 Gelen: {gelen}', header_format)
                else:
                    worksheet.write(last_row + 2, 0, f'Toplam Fatura: {len(df_filtered)}', header_format)
                    
                if 'totalTL' in df_filtered.columns:
                    total_amount = df_filtered['totalTL'].sum()
                    worksheet.write(last_row + 5, 0, f'Toplam Tutar: {total_amount:,.2f} ₺', header_format)
            
            logger.info(f"✅ Tüm fatura verileri kaydedildi: {self.excel_files['invoices']}")
            print(f"📊 {len(df_filtered)} fatura kaydı işlendi")
            return True
            
        except Exception as e:
            logger.error(f"❌ Fatura verileri kaydetme hatası: {e}")
            return False
    
    def save_incoming_invoices_to_excel_DEPRECATED(self, invoices_data: List[Dict]) -> bool:
        """
        Gelen fatura verilerini Excel'e kaydeder (PURCHASE_INVOICE)
        Sadece 7 sütun: id, date, invoiceNumber, totalTL, taxableAmount, firmName, description
        """
        try:
            df = pd.DataFrame(invoices_data)
            
            # Sadece istenen 7 sütunu al
            required_columns = ['id', 'date', 'invoiceNumber', 'totalTL', 'taxableAmount', 'firmName', 'description']
            available_columns = [col for col in required_columns if col in df.columns]
            
            if not available_columns:
                logger.warning("⚠️ Gerekli sütunlar bulunamadı")
                available_columns = df.columns.tolist()
            
            df_filtered = df[available_columns].copy()
            
            # Excel'e kaydet
            with pd.ExcelWriter(self.excel_files['incoming_invoices'], engine='xlsxwriter') as writer:
                workbook = writer.book
                
                header_format = workbook.add_format({
                    'bold': True,
                    'fg_color': '#FFC7CE',  # Kırmızımsı renk - gelen faturalar
                    'border': 1
                })
                
                currency_format = workbook.add_format({
                    'num_format': '#,##0.00 ₺',
                    'border': 1
                })
                
                date_format = workbook.add_format({
                    'num_format': 'dd.mm.yyyy',
                    'border': 1
                })
                
                df_filtered.to_excel(writer, index=False, sheet_name='Gelen_Faturalar')
                worksheet = writer.sheets['Gelen_Faturalar']
                
                # Header formatını uygula
                for col_num, value in enumerate(df_filtered.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Sütun genişliklerini ayarla
                for i, col in enumerate(df_filtered.columns):
                    if col in ['totalTL', 'taxableAmount']:
                        worksheet.set_column(i, i, 18, currency_format)
                    elif col == 'date':
                        worksheet.set_column(i, i, 15, date_format)
                    elif col == 'description':
                        worksheet.set_column(i, i, 50)
                    else:
                        column_len = max(df_filtered[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(column_len + 2, 40))
                
                # İstatistikler ekle
                last_row = len(df_filtered) + 1
                worksheet.write(last_row + 2, 0, f'Toplam Gelen Fatura: {len(df_filtered)}', header_format)
                if 'totalTL' in df_filtered.columns:
                    total_amount = df_filtered['totalTL'].sum()
                    worksheet.write(last_row + 3, 0, f'Toplam Tutar: {total_amount:,.2f} ₺', header_format)
            
            logger.info(f"✅ Gelen fatura verileri kaydedildi: {self.excel_files['incoming_invoices']}")
            print(f"📊 {len(df_filtered)} gelen fatura kaydı işlendi")
            return True
            
        except Exception as e:
            logger.error(f"❌ Gelen fatura verileri kaydetme hatası: {e}")
            return False
    
    def save_invoices_to_api_database(self, invoices_data: List[Dict]) -> bool:
        """
        API faturalarını API veritabanına kaydeder (api.db)
        
        Args:
            invoices_data: Fatura verileri listesi
            
        Returns:
            bool: Başarı durumu
        """
        try:
            total, added, duplicate = self.api_db.insert_invoices_batch(invoices_data)
            
            print(f"💾 API veritabanına kaydedildi:")
            print(f"   📊 Toplam: {total}")
            print(f"   ✅ Eklenen: {added}")
            print(f"   ⚠️  Duplicate: {duplicate}")
            
            return added > 0
            
        except Exception as e:
            logger.error(f"❌ API veritabanına kaydetme hatası: {e}")
            print(f"⚠️ Veritabanı hatası: {e}")
            return False
    
    def run_full_extraction(self) -> bool:
        """
        Tüm API veri çekme işlemini çalıştırır
        
        Returns:
            bool: Genel başarı durumu
        """
        print("🚀 API FATURA ÇEKME İŞLEMİ BAŞLATIYOR")
        print("=" * 60)
        
        # API girişi yap
        if not self.secure_login():
            return False
        
        # Eski verileri temizle (her seferinde fresh data)
        print("\n" + "=" * 60)
        print("ESKİ VERİLER TEMİZLENİYOR")
        print("=" * 60)
        
        if not self.api_db.clear_all_data():
            logger.warning("⚠️  Veritabanı temizlenemedi, yine de devam ediliyor...")
        
        print("\n" + "=" * 60)
        print("FATURA VERİLERİ ÇEKİLİYOR")
        print("=" * 60)
        
        # Tüm faturaları çek (giden + gelen birlikte)
        invoices_success = self.fetch_invoices()
        
        # Sonuçları raporla
        print("\n" + "=" * 60)
        print("FATURA ÇEKME SONUÇLARI")
        print("=" * 60)
        
        results = {
            'Giden Faturalar': invoices_success
        }
        
        for data_type, success in results.items():
            if success:
                print(f"✅ {data_type} verileri başarıyla çekildi")
            else:
                print(f"❌ {data_type} verileri çekilemedi")
        
        # Dosya yollarını göster
        print(f"\n📁 Excel çıktıları: {self.output_dir}")
        for file_type, file_path in self.excel_files.items():
            if file_path.exists():
                print(f"   📄 {file_type.upper()}: {file_path}")
        
        print(f"\n💾 Veritabanı: {self.db_path}")
        if self.db_path.exists():
            # API DB istatistiklerini göster
            self.api_db.print_statistics()
        
        # Genel başarı durumu
        overall_success = any(results.values())
        
        if overall_success:
            print("\n🎉 Fatura çekme işlemi tamamlandı!")
        else:
            print("\n⚠️ Hiçbir fatura çekilemedi!")
        
        return overall_success


def main():
    """Ana fonksiyon - Sadece giden fatura verilerini çeker"""
    print("\n" + "="*60)
    print("İŞBAŞI API - GİDEN FATURA ÇEKME MODÜLÜ")
    print("="*60)
    print("Bu modül sadece GİDEN faturaları çeker.")
    print("(PURCHASE_INVOICE türündeki gelen faturalar hariç)")
    print("="*60 + "\n")
    
    extractor = IsbasiAPIDataExtractor()
    extractor.run_full_extraction()


if __name__ == "__main__":
    main() 
