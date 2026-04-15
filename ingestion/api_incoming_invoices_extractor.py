#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Gelen Fatura Çekme Modülü
==============================

İşbaşı API'sinden sadece GELEN fatura verilerini çeker
ve Excel dosyalarına kaydeder.

Özellikler:
- Güvenli şifre girişi
- Sayfalama ile veri çekme
- Gelen fatura desteği (myInvoicesList endpoint)
- Excel formatlaması
"""

import requests
import pandas as pd
import os
import sys
import time
import re
import base64
import gzip
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import getpass
import logging
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Proje kök dizinini sys.path'e ekle
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Optional: load local .env without extra dependencies
def _load_dotenv_if_present(dotenv_path: Path) -> None:
    """
    Minimal .env loader (no python-dotenv dependency).
    - Only sets keys that are NOT already present in os.environ
    - Ignores blank lines and comments
    """
    try:
        if not dotenv_path.exists():
            return
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            key, val = s.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"⚠️ .env okunamadı ({dotenv_path}): {e}")


_load_dotenv_if_present(project_root / ".env")

# API Database modülünü import et
from archive.legacy_src.api_database import APIDatabase

# Logging konfigürasyonu
log_file = project_root / "data" / "logs" / "api_incoming_extraction.log"
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


class IsbasiAPIIncomingInvoicesExtractor:
    """
    İşbaşı API'sinden GELEN fatura veri çekme sınıfı
    
    API bağlantısı, veri çekme, sayfalama ve Excel kaydetme işlemlerini yönetir.
    """
    
    def __init__(self):
        """API extractor sınıfını başlatır"""
        self.session = requests.Session()
        self.base_url = os.getenv("ISBASI_BASE_URL", "https://mw-jplatform.isbasi.com").rstrip("/")
        self.api_key = os.getenv("ISBASI_API_KEY")
        self.username = os.getenv("ISBASI_USERNAME")
        self.password = None
        self.verify_ssl = os.getenv("ISBASI_VERIFY_SSL", "true").strip().lower() in ("1", "true", "yes", "y", "on")
        self.timeout = 30

        def _is_missing_or_placeholder(val: Optional[str]) -> bool:
            if val is None:
                return True
            v = str(val).strip()
            if not v:
                return True
            placeholders = {
                "YOUR_API_KEY_HERE",
                "your.email@example.com",
                "YOUR_USERNAME_HERE",
            }
            return v in placeholders

        if _is_missing_or_placeholder(self.api_key) or _is_missing_or_placeholder(self.username):
            if not sys.stdin.isatty():
                print("❌ Eksik konfigürasyon: ISBASI_API_KEY ve ISBASI_USERNAME ortam değişkenleri tanımlı olmalı.")
                print("   Örnek: cp env.example .env  (sonra .env içini doldurun)")
                raise SystemExit(2)

            print("⚠️ ISBASI_API_KEY / ISBASI_USERNAME eksik veya placeholder görünüyor.")
            print("   Devam etmek için değerleri şimdi girin (dosyaya yazılmaz).")
            entered_key = getpass.getpass("🔑 ISBASI_API_KEY: ").strip()
            entered_user = input("👤 ISBASI_USERNAME: ").strip()
            if not entered_key or not entered_user:
                print("❌ ISBASI_API_KEY ve ISBASI_USERNAME boş olamaz.")
                raise SystemExit(2)
            self.api_key = entered_key
            self.username = entered_user
        
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
        
        # API endpoint'leri
        self.endpoints = {
            'login': '/api/v1.0/user/integrationLogin',
            'incoming_invoices': '/api/v1.0/einvoices/myInvoicesList',  # Gelen faturalar listesi
            'invoice_ubl': '/api/v1.0/einvoices/DocumentUblDatawithuuid'  # Fatura UBL/XML içeriği
        }
        
        # Excel dosya yolları
        self.output_dir = project_root / "data" / "excel" / "api"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.excel_files = {
            'incoming_invoices': self.output_dir / "API_Gelen_Faturalar_NEW.xlsx"
        }
        
        # API veritabanı
        self.api_db = APIDatabase()
        self.db_path = self.api_db.db_path
        
        # Sayfalama parametreleri
        self.pagination_config = {
            'page_size': 100,
            'max_pages': 50,
            'delay_between_requests': 0.5
        }
        
        # XML namespace tanımları (UBL formatı için)
        self.namespaces = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        }
        
        logger.info("API Gelen Fatura Extractor başlatıldı")
        logger.info(f"Hedef veritabanı: {self.db_path}")
        logger.info(f"Fatura tipi: Sadece GELEN faturalar (irsaliye bilgileriyle)")
    
    def secure_login(self) -> bool:
        """
        Güvenli API girişi yapar
        
        Returns:
            bool: Giriş başarılı ise True, değilse False
        """
        try:
            print("🔐 İşbaşı API - Güvenli Giriş (Gelen Faturalar)")
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
                    
                    # Gelen fatura endpoint'i için gereken özel header'ları ekle
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
    
    def fetch_invoice_xml_by_uuid(self, uuid: str) -> Optional[str]:
        """
        UUID ile fatura XML içeriğini çeker
        
        Args:
            uuid: Fatura UUID'si (ETTN)
            
        Returns:
            Optional[str]: XML içeriği veya None
        """
        try:
            # UBL endpoint'ini çağır
            params = {
                'uuid': uuid,
                'type': 1  # UBL formatı
            }
            
            response = self.session.get(
                f"{self.base_url}{self.endpoints['invoice_ubl']}",
                params=params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            
            if response.status_code == 200:
                response.encoding = 'utf-8'
                response_data = response.json()
                
                # Response içinden content'i al
                if isinstance(response_data, dict):
                    data = response_data.get('data', {})
                    content = data.get('content', '')
                    
                    if content:
                        # Base64 decode et
                        try:
                            decoded_bytes = base64.b64decode(content)
                            
                            # Önce ZIP formatını dene
                            try:
                                with zipfile.ZipFile(io.BytesIO(decoded_bytes)) as zf:
                                    # İlk dosyayı al
                                    filename = zf.namelist()[0]
                                    xml_content = zf.read(filename).decode('utf-8')
                                    return xml_content
                            except zipfile.BadZipFile:
                                pass
                            
                            # GZIP formatını dene
                            try:
                                xml_content = gzip.decompress(decoded_bytes).decode('utf-8')
                                return xml_content
                            except gzip.BadGzipFile:
                                pass
                            
                            # Direkt UTF-8 olarak dene
                            try:
                                xml_content = decoded_bytes.decode('utf-8')
                                return xml_content
                            except UnicodeDecodeError:
                                # ISO-8859-9 (Turkish) encoding dene
                                try:
                                    xml_content = decoded_bytes.decode('iso-8859-9')
                                    return xml_content
                                except:
                                    logger.error(f"XML decode başarısız (UUID: {uuid}): Tüm encoding yöntemleri denendi")
                                    return None
                                
                        except Exception as e:
                            logger.error(f"Base64 decode hatası (UUID: {uuid}): {e}")
                            return None
            else:
                logger.warning(f"XML çekme başarısız (UUID: {uuid}): HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"XML çekme hatası (UUID: {uuid}): {e}")
            return None
    
    def parse_despatch_documents_from_xml(self, xml_content: str, supplier: str = None) -> List[Dict]:
        """
        XML içeriğinden irsaliye bilgilerini parse eder
        
        Args:
            xml_content: Fatura XML içeriği
            supplier: Tedarikçi adı (supplier-based normalization için)
            
        Returns:
            List[Dict]: İrsaliye bilgileri listesi
        """
        despatch_documents = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Import normalize function (lazy import to avoid circular dependency)
            try:
                from backend.core.normalize import normalize_incoming_despatch
            except ImportError:
                # Fallback if backend is not in path
                normalize_incoming_despatch = None
            
            # DespatchDocumentReference taglerini bul
            for despatch in root.findall('.//cac:DespatchDocumentReference', self.namespaces):
                despatch_data = {}
                
                # İrsaliye ID
                despatch_id = despatch.find('.//cbc:ID', self.namespaces)
                if despatch_id is not None and despatch_id.text:
                    full_id = despatch_id.text.strip()
                    despatch_data['despatch_id_full'] = full_id
                    
                    # NEW: Supplier-based normalization (v2.2)
                    if normalize_incoming_despatch and supplier:
                        normalized_id = normalize_incoming_despatch(full_id, supplier)
                        despatch_data['despatch_id_short'] = normalized_id or full_id[-5:] if len(full_id) >= 5 else full_id
                    else:
                        # Fallback: Son 5 haneyi al (IRS2025000014740 -> 14740)
                        if len(full_id) >= 5:
                            despatch_data['despatch_id_short'] = full_id[-5:]
                        else:
                            despatch_data['despatch_id_short'] = full_id
                
                # İrsaliye tarihi
                despatch_date = despatch.find('.//cbc:IssueDate', self.namespaces)
                if despatch_date is not None and despatch_date.text:
                    despatch_data['issue_date'] = despatch_date.text
                
                # Açıklama
                description = despatch.find('.//cbc:DocumentDescription', self.namespaces)
                if description is not None and description.text:
                    despatch_data['description'] = description.text.strip()
                
                if despatch_data.get('despatch_id_full'):
                    despatch_documents.append(despatch_data)
                    
        except Exception as e:
            logger.error(f"XML parse hatası: {e}")
        
        return despatch_documents
    
    def fetch_incoming_invoices_with_pagination(self) -> Tuple[bool, List[Dict]]:
        """
        Sayfalama ile gelen fatura verilerini çeker (Sadece 2026 yılı)
        
        Returns:
            Tuple[bool, List[Dict]]: (başarı durumu, veri listesi)
        """
        all_data = []
        page = 1
        total_count = 0
        
        print(f"📊 GELEN FATURA verileri çekiliyor (Sadece 2026 yılı)...")
        
        try:
            while page <= self.pagination_config['max_pages']:
                # Gelen faturalar için özel payload - 2026 yılı filtresi
                payload = {
                    "filters": [
                        {
                            "columnName": "issueDate",
                            "operator": 5,  # Büyük veya eşit (>=)
                            "value": "2026-01-01T00:00:00"
                        },
                        {
                            "columnName": "issueDate",
                            "operator": 2,  # Küçük veya eşit (<=)
                            "value": "2026-12-31T23:59:59"
                        }
                    ],
                    "sorting": {
                        "issueDate": 1  # Tarihe göre artan sırada
                    },
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
                    f"{self.base_url}{self.endpoints['incoming_invoices']}",
                    json=payload,
                    timeout=self.timeout,
                    verify=self.verify_ssl
                )
                
                if response.status_code != 200:
                    if response.status_code == 401:
                        logger.error("❌ Yetkilendirme hatası")
                        return False, []
                    logger.error(f"❌ HTTP {response.status_code}")
                    logger.error(f"Response: {response.text[:500]}")
                    break
                
                response.encoding = 'utf-8'
                response_data = response.json()
                
                # Veri yapısını analiz et
                page_data = []
                if isinstance(response_data, dict):
                    if 'data' in response_data and isinstance(response_data['data'], dict):
                        page_data = response_data['data'].get('data', [])
                        if page == 1:
                            total_count = response_data['data'].get('count', 0)
                    elif 'data' in response_data:
                        page_data = response_data['data']
                elif isinstance(response_data, list):
                    page_data = response_data
                
                if not page_data:
                    logger.info(f"📄 Sayfa {page} boş - veri çekme tamamlandı")
                    break
                
                # Metin alanlarını string olarak zorla
                for item in page_data:
                    if isinstance(item, dict):
                        text_fields = ['invoiceId', 'uuId', 'supplier', 'supplierTcknVkn']
                        for field in text_fields:
                            if field in item and item[field] is not None:
                                item[field] = str(item[field])
                
                all_data.extend(page_data)
                print(f"   📄 Sayfa {page}: {len(page_data)} kayıt (gelen fatura)")
                
                # Son sayfaya ulaşıldı mı kontrol et
                if len(page_data) < self.pagination_config['page_size']:
                    logger.info(f"📄 Son sayfa ulaşıldı (sayfa {page})")
                    break
                
                page += 1
                time.sleep(self.pagination_config['delay_between_requests'])
            
            print(f"✅ GELEN FATURA verileri tamamlandı: {len(all_data)} kayıt")
            if total_count > 0:
                print(f"   ℹ️  API toplam kayıt sayısı: {total_count}")
            
            # Her fatura için XML içeriğinden irsaliye bilgilerini çek
            print(f"\n📦 İrsaliye bilgileri çekiliyor...")
            despatch_count = 0
            for idx, invoice in enumerate(all_data, 1):
                uuid = invoice.get('uuId')
                if uuid:
                    if idx % 10 == 0:  # Her 10 faturada bir progress göster
                        print(f"   ⏳ {idx}/{len(all_data)} fatura işlendi...")
                    
                    # XML içeriğini çek
                    xml_content = self.fetch_invoice_xml_by_uuid(uuid)
                    if xml_content:
                        # İrsaliye bilgilerini parse et (supplier bilgisi ile)
                        supplier = invoice.get('supplier', '')
                        despatch_docs = self.parse_despatch_documents_from_xml(xml_content, supplier)
                        if despatch_docs:
                            # İrsaliye bilgilerini faturaya ekle
                            invoice['despatch_documents'] = despatch_docs
                            despatch_count += len(despatch_docs)
                            
                            # İrsaliye numaralarını virgülle ayrılmış string olarak da ekle
                            despatch_ids = ', '.join([d.get('despatch_id_short', '') for d in despatch_docs if d.get('despatch_id_short')])
                            invoice['despatch_ids_summary'] = despatch_ids
                    
                    # Rate limiting
                    time.sleep(0.3)  # Her XML çekme arasında 300ms bekle
            
            print(f"✅ İrsaliye bilgileri tamamlandı: {despatch_count} irsaliye bulundu")
            return True, all_data
            
        except Exception as e:
            logger.error(f"❌ Gelen fatura veri çekme hatası: {e}")
            return False, []
    
    def save_incoming_invoices_to_excel(self, invoices_data: List[Dict]) -> bool:
        """
        Gelen fatura verilerini Excel'e kaydeder
        
        Swagger'dan gelen temel alanlar + İrsaliye bilgileri:
        - invoiceId, uuId, type, typeDesc, issueDate
        - amount, totalVatBase, currency
        - supplier, supplierTcknVkn, isPersonal
        - invoiceType, status, statusCode
        - purchaseInvoiceId, salesInvoiceId
        - despatch_ids_summary (irsaliye numaraları)
        """
        try:
            df = pd.DataFrame(invoices_data)
            
            if df.empty:
                logger.warning("⚠️ Gelen fatura verisi boş")
                return False
            
            # Metin sütunlarını string'e çevir
            text_columns = ['invoiceId', 'uuId', 'supplier', 'supplierTcknVkn', 'purchaseInvoiceId', 'despatch_ids_summary']
            for col in text_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
            
            # Seçilecek sütunlar (swagger'a göre + irsaliye)
            preferred_columns = [
                'invoiceId', 'issueDate', 'supplier', 'supplierTcknVkn',
                'amount', 'totalVatBase', 'currency', 
                'despatch_ids_summary',  # İrsaliye numaraları
                'type', 'typeDesc', 'invoiceType',
                'status', 'statusCode', 'purchaseInvoiceId'
            ]
            available_columns = [col for col in preferred_columns if col in df.columns]
            
            if not available_columns:
                logger.warning("⚠️ Tercih edilen sütunlar bulunamadı, tüm sütunlar kullanılacak")
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
                
                text_format = workbook.add_format({
                    'border': 1,
                    'text_wrap': False
                })
                
                text_only_format = workbook.add_format({
                    'num_format': '@',
                    'border': 1
                })
                
                df_filtered.to_excel(writer, index=False, sheet_name='Gelen_Faturalar')
                worksheet = writer.sheets['Gelen_Faturalar']
                
                # Header formatını uygula
                for col_num, value in enumerate(df_filtered.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Sütun genişliklerini ve formatlarını ayarla
                for i, col in enumerate(df_filtered.columns):
                    if col in ['amount', 'totalVatBase']:
                        worksheet.set_column(i, i, 18, currency_format)
                    elif col == 'issueDate':
                        worksheet.set_column(i, i, 15, date_format)
                    elif col == 'despatch_ids_summary':
                        # İrsaliye numaraları için özel genişlik
                        worksheet.set_column(i, i, 30, text_only_format)
                    elif col in ['invoiceId', 'uuId', 'supplier', 'supplierTcknVkn', 'purchaseInvoiceId']:
                        column_len = max(df_filtered[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(column_len + 2, 40), text_only_format)
                    else:
                        column_len = max(df_filtered[col].astype(str).map(len).max(), len(col))
                        worksheet.set_column(i, i, min(column_len + 2, 40), text_format)
                
                # İstatistikler ekle
                last_row = len(df_filtered) + 1
                worksheet.write(last_row + 2, 0, f'Toplam Gelen Fatura: {len(df_filtered)}', header_format)
                
                if 'amount' in df_filtered.columns:
                    total_amount = df_filtered['amount'].sum()
                    worksheet.write(last_row + 3, 0, f'Toplam Tutar: {total_amount:,.2f} ₺', header_format)
                
                # İrsaliye istatistiği
                if 'despatch_ids_summary' in df_filtered.columns:
                    invoices_with_despatch = df_filtered[df_filtered['despatch_ids_summary'].notna() & 
                                                         (df_filtered['despatch_ids_summary'] != '') & 
                                                         (df_filtered['despatch_ids_summary'] != 'nan')].shape[0]
                    worksheet.write(last_row + 4, 0, f'İrsaliyeli Fatura Sayısı: {invoices_with_despatch}', header_format)
            
            logger.info(f"✅ Gelen fatura verileri kaydedildi: {self.excel_files['incoming_invoices']}")
            print(f"📊 {len(df_filtered)} gelen fatura kaydı işlendi")
            return True
            
        except Exception as e:
            logger.error(f"❌ Gelen fatura verileri kaydetme hatası: {e}")
            return False
    
    def run_extraction(self) -> bool:
        """
        Gelen fatura çekme işlemini çalıştırır
        
        Returns:
            bool: Genel başarı durumu
        """
        print("🚀 API GELEN FATURA ÇEKME İŞLEMİ BAŞLATIYOR")
        print("=" * 60)
        
        # API girişi yap
        if not self.secure_login():
            return False
        
        print("\n" + "=" * 60)
        print("GELEN FATURA VERİLERİ ÇEKİLİYOR")
        print("=" * 60)
        
        # Gelen faturaları çek
        success, invoices_data = self.fetch_incoming_invoices_with_pagination()
        
        if success and invoices_data:
            # Excel'e kaydet
            excel_ok = self.save_incoming_invoices_to_excel(invoices_data)
            
            # Sonuçları raporla
            print("\n" + "=" * 60)
            print("GELEN FATURA ÇEKME SONUÇLARI")
            print("=" * 60)
            
            if excel_ok:
                print(f"✅ Gelen fatura verileri başarıyla çekildi")
                print(f"\n📁 Excel çıktısı: {self.excel_files['incoming_invoices']}")
                print("\n🎉 Gelen fatura çekme işlemi tamamlandı!")
                return True
            else:
                print(f"❌ Gelen fatura verileri kaydedilemedi")
                return False
        else:
            print("\n⚠️ Gelen fatura verisi çekilemedi!")
            return False


def main():
    """Ana fonksiyon - Sadece gelen fatura verilerini çeker (2026 yılı)"""
    print("\n" + "="*60)
    print("İŞBAŞI API - GELEN FATURA ÇEKME MODÜLÜ")
    print("="*60)
    print("Bu modül sadece GELEN faturaları çeker.")
    print("(myInvoicesList endpoint kullanılır)")
    print("📅 SADECE 2026 YILI VERİLERİ")
    print("="*60 + "\n")
    
    extractor = IsbasiAPIIncomingInvoicesExtractor()
    extractor.run_extraction()


if __name__ == "__main__":
    main()
