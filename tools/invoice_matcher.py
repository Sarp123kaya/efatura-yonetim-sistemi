#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fatura Eşleştirme Aracı
========================

API'den gönderilen faturaların description alanından irsaliye kodlarını çıkarıp,
ilgili veritabanlarında (akgips.db veya fullboard.db) eşleşen fatura bilgilerini
bulan ve Excel raporuna yazan araç.

Kullanım:
    python3 tools/invoice_matcher.py
"""

import pandas as pd
import sqlite3
import re
from pathlib import Path
from datetime import datetime
import logging

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InvoiceMatcher:
    """
    Giden faturalardan irsaliye kodlarını çıkarıp,
    gelen faturalarla eşleştiren sınıf
    """
    
    def __init__(self):
        """Matcher sınıfını başlatır"""
        # Proje kök dizini
        self.project_root = Path(__file__).resolve().parent.parent
        
        # Dosya yolları
        self.api_excel = self.project_root / "data" / "excel" / "api" / "API_Giden_Faturalar.xlsx"
        self.akgips_db = self.project_root / "data" / "db" / "akgips.db"
        self.fullboard_db = self.project_root / "data" / "db" / "fullboard.db"
        
        # Çıktı klasörü
        self.output_dir = self.project_root / "kayıtlar"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # İrsaliye kodu regex pattern'i
        # A- veya F- ile başlayan 4-5 haneli kodları yakalar
        # Desteklenen formatlar:
        #   - F-9171, A-18356 (standart)
        #   - F-9170 / F-9189 (çoklu, / ile ayrılmış)
        #   - F/9099 (/ ile birleşik)
        #   - F- 9026 (boşluklu)
        # Prefix olmayan kodlar atlanır (örn: İRSALİYE NO: 18277)
        self.irsaliye_pattern = r'([AF])\s*[-/]\s*(\d{4,5})'
        
        logger.info("Invoice Matcher başlatıldı")
        logger.info(f"API Excel: {self.api_excel}")
        logger.info(f"AkGips DB: {self.akgips_db}")
        logger.info(f"Fullboard DB: {self.fullboard_db}")
    
    def extract_irsaliye_codes(self, description: str) -> list:
        """
        Description alanından irsaliye kodlarını çıkarır
        
        Desteklenen formatlar:
        - İRSALİYE NO: F-9171 ( İSTANBUL )
        - İRSALİYE NO: A-18356 ( ALTINOVA )
        - İRSALİYE NO: F-9170 / F-9189 (çoklu, / ile ayrılmış)
        - İRSALİYE NO:F/9099/F-9098 (/ ile birleşik)
        - İRSALİYE NO: F- 9026 (boşluklu)
        
        Prefix olmayan kodlar atlanır:
        - İRSALİYE NO: 18277 → ATLANIR
        
        Args:
            description: Açıklama metni
            
        Returns:
            List[tuple]: [(prefix, number), ...] formatında irsaliye kodları
            Örnek: [('A', '18356'), ('F', '9197')]
        """
        if not description or pd.isna(description):
            return []
        
        # Description'ı string'e çevir ve büyük harfe çevir (case-insensitive)
        desc = str(description).upper()
        
        # Tüm eşleşmeleri bul (A-XXXX veya F-XXXX formatında)
        # Pattern: ([AF])\s*[-/]\s*(\d{4,5})
        # A veya F, sonra - veya / (boşluklarla), sonra 4-5 haneli numara
        matches = re.findall(self.irsaliye_pattern, desc)
        
        # Unique yapıp döndür
        return list(set(matches))
    
    def search_in_database(self, irsaliye_code: str, db_path: Path) -> dict:
        """
        Veritabanında irsaliye koduna göre fatura arar
        Gelen faturada birden fazla irsaliye varsa tutarı bölüştürür
        
        Args:
            irsaliye_code: İrsaliye kodu (örn: 'A-18356')
            db_path: Veritabanı dosya yolu
            
        Returns:
            dict: {'invoice_number': '...', 'total_amount': ..., 'found': True/False, 'irsaliye_count': N}
        """
        result = {
            'invoice_number': None,
            'total_amount': None,
            'found': False,
            'irsaliye_count': 0
        }
        
        if not db_path.exists():
            logger.warning(f"Veritabanı bulunamadı: {db_path}")
            return result
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # İrsaliye koduna göre fatura bilgilerini çek
            query = """
                SELECT i.invoice_number, i.total_amount, i.id
                FROM despatch_documents d 
                JOIN invoices i ON d.invoice_id = i.id 
                WHERE d.despatch_id_short = ?
                LIMIT 1
            """
            
            cursor.execute(query, (irsaliye_code,))
            row = cursor.fetchone()
            
            if row:
                invoice_number = row[0]
                total_amount = row[1]
                invoice_id = row[2]
                
                # Bu faturada kaç irsaliye var?
                count_query = """
                    SELECT COUNT(*) 
                    FROM despatch_documents 
                    WHERE invoice_id = ?
                """
                cursor.execute(count_query, (invoice_id,))
                irsaliye_count = cursor.fetchone()[0]
                
                # Tutarı irsaliye sayısına böl
                ortalama_tutar = total_amount / irsaliye_count if irsaliye_count > 0 else total_amount
                
                result['invoice_number'] = invoice_number
                result['total_amount'] = ortalama_tutar
                result['irsaliye_count'] = irsaliye_count
                result['found'] = True
                
                logger.debug(f"Eşleşme bulundu: {irsaliye_code} -> {invoice_number} ({irsaliye_count} irsaliye, ortalama: {ortalama_tutar:.2f})")
            else:
                logger.debug(f"Eşleşme bulunamadı: {irsaliye_code}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Veritabanı hatası ({db_path}): {e}")
        
        return result
    
    def process_api_invoices(self) -> pd.DataFrame:
        """
        API Excel dosyasını okur ve her fatura için eşleşme arar
        
        Returns:
            pd.DataFrame: Eşleştirme sonuçları
        """
        logger.info("API fatura dosyası okunuyor...")
        
        # Excel dosyasını oku
        df = pd.read_excel(self.api_excel)
        
        logger.info(f"Toplam {len(df)} fatura bulundu")
        
        # Sonuç listesi
        results = []
        
        for idx, row in df.iterrows():
            giden_fatura_no = row.get('invoiceNumber', '')
            giden_tutar = row.get('totalTL', 0)
            giden_tarih = row.get('date', '')
            description = row.get('description', '')
            
            # Tarihi gün.ay.yıl formatına çevir
            try:
                if giden_tarih:
                    from datetime import datetime
                    if isinstance(giden_tarih, str):
                        tarih_obj = datetime.fromisoformat(giden_tarih.replace('T', ' ').split('.')[0])
                    else:
                        tarih_obj = giden_tarih
                    giden_tarih_formatted = tarih_obj.strftime('%d.%m.%Y')
                else:
                    giden_tarih_formatted = ''
            except:
                giden_tarih_formatted = str(giden_tarih)
            
            # Description'dan irsaliye kodlarını çıkar
            irsaliye_codes = self.extract_irsaliye_codes(description)
            
            if not irsaliye_codes:
                # İrsaliye kodu bulunamadı
                results.append({
                    'Tarih': giden_tarih_formatted,
                    'Giden_Fatura_No': giden_fatura_no,
                    'Giden_Tutar_TL': giden_tutar,
                    'Irsaliye_Kodu': 'Bulunamadı',
                    'Firma': '-',
                    'Gelen_Fatura_No': '-',
                    'Gelen_Tutar_TL': 0,
                    'Fark_TL': 0,
                    'KDV_20_TL': 0,
                    'Fark_KDV_Dusulmus_TL': 0,
                    'Durum': 'İrsaliye kodu yok ⚠'
                })
                continue
            
            # Çoklu irsaliye durumunda ortalama tutar hesapla
            irsaliye_sayisi = len(irsaliye_codes)
            ortalama_tutar = giden_tutar / irsaliye_sayisi if irsaliye_sayisi > 0 else giden_tutar
            
            # Çoklu irsaliye işareti
            coklu_irsaliye_isareti = f" (÷{irsaliye_sayisi})" if irsaliye_sayisi > 1 else ""
            
            # Her irsaliye kodu için arama yap
            for prefix, number in irsaliye_codes:
                irsaliye_code = f"{prefix}-{number}"
                
                # Firma ve veritabanını belirle
                if prefix == 'A':
                    firma = 'AK GİPS'
                    db_path = self.akgips_db
                elif prefix == 'F':
                    firma = 'FULLBOARD'
                    db_path = self.fullboard_db
                else:
                    continue
                
                # Veritabanında ara
                search_result = self.search_in_database(irsaliye_code, db_path)
                
                if search_result['found']:
                    durum = 'Eşleşti ✓'
                    gelen_fatura_no = search_result['invoice_number']
                    gelen_tutar = search_result['total_amount']
                    gelen_irsaliye_count = search_result['irsaliye_count']
                    
                    # Gelen faturada çoklu irsaliye varsa işaretle
                    if gelen_irsaliye_count > 1:
                        gelen_fatura_no = f"{gelen_fatura_no} (÷{gelen_irsaliye_count})"
                else:
                    durum = 'Bulunamadı ✗'
                    gelen_fatura_no = '-'
                    gelen_tutar = 0
                
                # Fark hesaplaması
                fark = ortalama_tutar - gelen_tutar if search_result['found'] else 0
                kdv_20 = fark * 0.20  # %20 KDV
                fark_kdv_dusulmus = fark - kdv_20  # KDV düşülmüş fark
                
                results.append({
                    'Tarih': giden_tarih_formatted,
                    'Giden_Fatura_No': giden_fatura_no + coklu_irsaliye_isareti,  # İşaret ekle
                    'Giden_Tutar_TL': ortalama_tutar,  # Ortalama tutar kullan
                    'Irsaliye_Kodu': irsaliye_code,
                    'Firma': firma,
                    'Gelen_Fatura_No': gelen_fatura_no,
                    'Gelen_Tutar_TL': gelen_tutar,
                    'Fark_TL': fark,
                    'KDV_20_TL': kdv_20,
                    'Fark_KDV_Dusulmus_TL': fark_kdv_dusulmus,
                    'Durum': durum
                })
        
        # DataFrame'e çevir
        results_df = pd.DataFrame(results)
        
        logger.info(f"İşlem tamamlandı: {len(results)} kayıt")
        
        return results_df
    
    def generate_excel_report(self, df: pd.DataFrame) -> Path:
        """
        Eşleştirme sonuçlarını Excel raporuna yazar
        
        Args:
            df: Sonuç DataFrame'i
            
        Returns:
            Path: Oluşturulan Excel dosyasının yolu
        """
        # NaN değerlerini temizle
        df = df.fillna({
            'Tarih': '',
            'Giden_Fatura_No': '',
            'Giden_Tutar_TL': 0,
            'Irsaliye_Kodu': '',
            'Firma': '-',
            'Gelen_Fatura_No': '-',
            'Gelen_Tutar_TL': 0,
            'Fark_TL': 0,
            'KDV_20_TL': 0,
            'Fark_KDV_Dusulmus_TL': 0,
            'Durum': ''
        })
        
        # Eski rapor dosyalarını sil
        for old_file in self.output_dir.glob("Fatura_Eslesme_Raporu_*.xlsx"):
            try:
                old_file.unlink()
                logger.info(f"🗑️  Eski rapor silindi: {old_file.name}")
            except Exception as e:
                logger.warning(f"⚠️  Eski rapor silinemedi: {old_file.name} - {e}")
        
        # Dosya adı (timestamp ile)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"Fatura_Eslesme_Raporu_{timestamp}.xlsx"
        
        logger.info(f"Excel raporu oluşturuluyor: {output_file}")
        
        # Excel'e yaz
        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Eşleştirme Sonuçları')
            
            # Workbook ve worksheet al
            workbook = writer.book
            worksheet = writer.sheets['Eşleştirme Sonuçları']
            
            # Formatlar
            header_format = workbook.add_format({
                'bold': True,
                'fg_color': '#4472C4',
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            
            currency_format = workbook.add_format({
                'num_format': '#,##0.00 ₺',
                'border': 1
            })
            
            center_format = workbook.add_format({
                'align': 'center',
                'border': 1
            })
            
            success_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'border': 1
            })
            
            warning_format = workbook.add_format({
                'bg_color': '#FFEB9C',
                'border': 1
            })
            
            error_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'border': 1
            })
            
            # Header formatını uygula
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Sütun genişliklerini ayarla
            worksheet.set_column('A:A', 12)  # Tarih
            worksheet.set_column('B:B', 25)  # Giden_Fatura_No
            worksheet.set_column('C:C', 18)  # Giden_Tutar_TL
            worksheet.set_column('D:D', 18)  # Irsaliye_Kodu
            worksheet.set_column('E:E', 15)  # Firma
            worksheet.set_column('F:F', 20)  # Gelen_Fatura_No
            worksheet.set_column('G:G', 18)  # Gelen_Tutar_TL
            worksheet.set_column('H:H', 18)  # Fark_TL
            worksheet.set_column('I:I', 18)  # KDV_20_TL
            worksheet.set_column('J:J', 20)  # Fark_KDV_Dusulmus_TL
            worksheet.set_column('K:K', 20)  # Durum
            
            # Para birimi formatını uygula
            for row_num in range(1, len(df) + 1):
                worksheet.write(row_num, 2, df.iloc[row_num - 1]['Giden_Tutar_TL'], currency_format)
                worksheet.write(row_num, 6, df.iloc[row_num - 1]['Gelen_Tutar_TL'], currency_format)
                worksheet.write(row_num, 7, df.iloc[row_num - 1]['Fark_TL'], currency_format)
                worksheet.write(row_num, 8, df.iloc[row_num - 1]['KDV_20_TL'], currency_format)
                worksheet.write(row_num, 9, df.iloc[row_num - 1]['Fark_KDV_Dusulmus_TL'], currency_format)
            
            # Durum sütununa göre satır renklendirme
            for row_num in range(1, len(df) + 1):
                durum = df.iloc[row_num - 1]['Durum']
                
                if 'Eşleşti' in durum:
                    row_format = success_format
                elif 'İrsaliye kodu yok' in durum:
                    row_format = warning_format
                else:
                    row_format = error_format
                
                # Sadece durum sütununu renklendir (K sütunu - 10. index)
                worksheet.write(row_num, 10, durum, row_format)
            
            # İstatistikler ekle
            last_row = len(df) + 3
            
            eslesme_sayisi = len(df[df['Durum'].str.contains('Eşleşti', na=False)])
            bulunamayan_sayisi = len(df[df['Durum'].str.contains('Bulunamadı', na=False)])
            irsaliye_yok_sayisi = len(df[df['Durum'].str.contains('İrsaliye kodu yok', na=False)])
            
            worksheet.write(last_row, 0, '📊 İSTATİSTİKLER', header_format)
            worksheet.write(last_row + 1, 0, f'✓ Eşleşen: {eslesme_sayisi}', success_format)
            worksheet.write(last_row + 2, 0, f'✗ Bulunamayan: {bulunamayan_sayisi}', error_format)
            worksheet.write(last_row + 3, 0, f'⚠ İrsaliye kodu yok: {irsaliye_yok_sayisi}', warning_format)
            worksheet.write(last_row + 4, 0, f'📝 Toplam: {len(df)}', header_format)
        
        logger.info(f"✅ Excel raporu oluşturuldu: {output_file}")
        
        return output_file
    
    def run(self) -> Path:
        """
        Tam eşleştirme işlemini çalıştırır
        
        Returns:
            Path: Oluşturulan Excel dosyasının yolu
        """
        print("=" * 70)
        print("🔍 FATURA EŞLEŞTIRME ARACI")
        print("=" * 70)
        print()
        
        # Dosya kontrolü
        if not self.api_excel.exists():
            logger.error(f"❌ API Excel dosyası bulunamadı: {self.api_excel}")
            return None
        
        if not self.akgips_db.exists():
            logger.warning(f"⚠️ AkGips veritabanı bulunamadı: {self.akgips_db}")
        
        if not self.fullboard_db.exists():
            logger.warning(f"⚠️ Fullboard veritabanı bulunamadı: {self.fullboard_db}")
        
        print("📊 Giden faturalar işleniyor...")
        results_df = self.process_api_invoices()
        
        print()
        print("📈 İstatistikler:")
        print(f"   ✓ Eşleşen: {len(results_df[results_df['Durum'].str.contains('Eşleşti', na=False)])}")
        print(f"   ✗ Bulunamayan: {len(results_df[results_df['Durum'].str.contains('Bulunamadı', na=False)])}")
        print(f"   ⚠ İrsaliye kodu yok: {len(results_df[results_df['Durum'].str.contains('İrsaliye kodu yok', na=False)])}")
        print(f"   📝 Toplam: {len(results_df)}")
        print()
        
        print("📝 Excel raporu oluşturuluyor...")
        output_file = self.generate_excel_report(results_df)
        
        print()
        print("=" * 70)
        print("✅ İŞLEM TAMAMLANDI")
        print("=" * 70)
        print(f"📄 Rapor: {output_file}")
        print()
        
        return output_file


def main():
    """Ana fonksiyon"""
    matcher = InvoiceMatcher()
    matcher.run()


if __name__ == '__main__':
    main()

