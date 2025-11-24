#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Fatura Veritabanını Excel'e Aktarma Modülü
===============================================

api.db veritabanındaki verileri Excel formatında export eder.
Kullanıcı hafızasına göre 8 sütun: id, date, invoiceNumber, totalTL, taxableAmount, firmName, description, irsaliyeNo
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


def extract_irsaliye_from_description(description: str) -> str:
    """
    Description alanından irsaliye numaralarını çıkarır ve birleştirir
    
    Args:
        description: Açıklama metni
        
    Returns:
        str: Virgülle ayrılmış irsaliye numaraları
    """
    if not description:
        return ""
    
    irsaliye_numbers = []
    
    # Pattern 1: IRS veya İRS ile başlayanlar
    pattern1 = r'[İI]RS[-\s]?(\d{5,})'
    matches1 = re.findall(pattern1, description, re.IGNORECASE)
    for match in matches1:
        irsaliye_numbers.append(f"IRS{match}")
    
    # Pattern 2: A- veya F- prefix'li numaralar (4-5 haneli)
    pattern2 = r'([AF])[-/\s]*(\d{4,5})'
    matches2 = re.findall(pattern2, description, re.IGNORECASE)
    for match in matches2:
        irsaliye_numbers.append(f"{match[0]}-{match[1]}")
    
    # Duplicate'leri temizle ve birleştir
    return ", ".join(list(set(irsaliye_numbers)))


def format_date_dmy(date_str: str) -> str:
    """
    Tarihi gün.ay.yıl formatına çevirir
    
    Args:
        date_str: Tarih string'i (çeşitli formatlar)
        
    Returns:
        str: gün.ay.yıl formatında tarih
    """
    if not date_str:
        return ""
    
    try:
        # ISO formatı (2024-10-08)
        if '-' in date_str:
            dt = datetime.fromisoformat(date_str.split('T')[0])
            return dt.strftime('%d.%m.%Y')
        # Zaten noktalı format (08.10.2024)
        elif '.' in date_str:
            return date_str
        else:
            return date_str
    except:
        return date_str


def export_api_to_excel(db_path: str = None, output_path: str = None) -> bool:
    """
    API veritabanını Excel'e export eder
    
    Args:
        db_path: API veritabanı yolu (varsayılan: data/db/api.db)
        output_path: Çıktı Excel dosyası (varsayılan: kayıtlar/API_Faturalar.xlsx)
        
    Returns:
        bool: Başarı durumu
    """
    try:
        # Proje kök dizinini bul
        project_root = Path(__file__).resolve().parent.parent.parent
        
        if db_path is None:
            db_path = project_root / "data" / "db" / "api.db"
        else:
            db_path = Path(db_path)
        
        if output_path is None:
            output_dir = project_root / "kayıtlar"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Eski API Excel dosyalarını sil
            for old_file in output_dir.glob("API_Faturalar_*.xlsx"):
                try:
                    old_file.unlink()
                    print(f"🗑️  Eski dosya silindi: {old_file.name}")
                except Exception as e:
                    print(f"⚠️  Eski dosya silinemedi: {old_file.name} - {e}")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"API_Faturalar_{timestamp}.xlsx"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not db_path.exists():
            logger.error(f"❌ Veritabanı bulunamadı: {db_path}")
            return False
        
        logger.info(f"📊 API veritabanı export ediliyor: {db_path}")
        
        # Veritabanından veri çek
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Fatura verilerini çek
        cursor.execute('''
            SELECT 
                api_id as id,
                issue_date as date,
                invoice_number as invoiceNumber,
                total_amount as totalTL,
                taxable_amount as taxableAmount,
                firm_name as firmName,
                description,
                invoice_type as type
            FROM invoices
            ORDER BY issue_date DESC, id DESC
        ''')
        
        rows = cursor.fetchall()
        columns = ['id', 'date', 'invoiceNumber', 'totalTL', 'taxableAmount', 'firmName', 'description', 'type']
        
        if not rows:
            logger.warning("⚠️  Veritabanında veri bulunamadı")
            conn.close()
            return False
        
        # DataFrame oluştur
        df = pd.DataFrame(rows, columns=columns)
        
        # Tarihi gün.ay.yıl formatına çevir
        df['date'] = df['date'].apply(format_date_dmy)
        
        # İrsaliye numaralarını çıkar
        df['irsaliyeNo'] = df['description'].apply(extract_irsaliye_from_description)
        
        # İstenen 8 sütunu seç (type dahil)
        final_columns = ['id', 'date', 'invoiceNumber', 'totalTL', 'taxableAmount', 'firmName', 'description', 'irsaliyeNo']
        df_export = df[final_columns].copy()
        
        conn.close()
        
        # Excel'e kaydet
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Formatlar
            header_format = workbook.add_format({
                'bold': True,
                'fg_color': '#D7E4BC',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            
            currency_format = workbook.add_format({
                'num_format': '#,##0.00 ₺',
                'border': 1
            })
            
            text_format = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'top',
                'text_wrap': True
            })
            
            # Excel'e yaz
            df_export.to_excel(writer, index=False, sheet_name='API_Faturalar', startrow=0)
            worksheet = writer.sheets['API_Faturalar']
            
            # Header formatını uygula
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Sütun genişlikleri ve formatları
            column_settings = {
                'id': (12, text_format),
                'date': (15, text_format),
                'invoiceNumber': (20, text_format),
                'totalTL': (18, currency_format),
                'taxableAmount': (18, currency_format),
                'firmName': (30, text_format),
                'description': (50, text_format),
                'irsaliyeNo': (20, text_format)
            }
            
            for i, col in enumerate(df_export.columns):
                width, fmt = column_settings.get(col, (15, text_format))
                worksheet.set_column(i, i, width, fmt)
            
            # Verileri formatla (header'ı atla)
            for row_num in range(1, len(df_export) + 1):
                for col_num, col in enumerate(df_export.columns):
                    value = df_export.iloc[row_num - 1, col_num]
                    if col in ['totalTL', 'taxableAmount']:
                        worksheet.write(row_num, col_num, value, currency_format)
                    else:
                        worksheet.write(row_num, col_num, value, text_format)
            
            # İstatistikler ekle
            last_row = len(df_export) + 2
            
            # Type bazlı istatistikler (type sütunu df'de var ama export edilmedi)
            giden_count = len(df[df['type'] != 'PURCHASE_INVOICE'])
            gelen_count = len(df[df['type'] == 'PURCHASE_INVOICE'])
            total_count = len(df)
            
            giden_total = df[df['type'] != 'PURCHASE_INVOICE']['totalTL'].sum()
            gelen_total = df[df['type'] == 'PURCHASE_INVOICE']['totalTL'].sum()
            total_amount = df['totalTL'].sum()
            
            stats_format = workbook.add_format({
                'bold': True,
                'fg_color': '#FFF2CC',
                'border': 1
            })
            
            worksheet.write(last_row, 0, 'İSTATİSTİKLER', stats_format)
            worksheet.write(last_row + 1, 0, f'Toplam Fatura: {total_count}', text_format)
            worksheet.write(last_row + 2, 0, f'  🟢 Giden: {giden_count}', text_format)
            worksheet.write(last_row + 3, 0, f'  🔴 Gelen: {gelen_count}', text_format)
            worksheet.write(last_row + 5, 0, f'Toplam Tutar: {total_amount:,.2f} ₺', text_format)
            worksheet.write(last_row + 6, 0, f'  🟢 Giden: {giden_total:,.2f} ₺', text_format)
            worksheet.write(last_row + 7, 0, f'  🔴 Gelen: {gelen_total:,.2f} ₺', text_format)
        
        logger.info(f"✅ Export tamamlandı: {output_path}")
        logger.info(f"📊 {len(df_export)} fatura export edildi")
        
        print("\n" + "=" * 60)
        print("API FATURALAR EXPORT TAMAMLANDI")
        print("=" * 60)
        print(f"📁 Dosya: {output_path}")
        print(f"📊 Toplam Fatura: {total_count}")
        print(f"   🟢 Giden: {giden_count}")
        print(f"   🔴 Gelen: {gelen_count}")
        print(f"💰 Toplam Tutar: {total_amount:,.2f} TRY")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Export hatası: {e}")
        print(f"❌ Hata: {e}")
        return False


def main():
    """Ana fonksiyon"""
    print("\n" + "=" * 60)
    print("API FATURALAR EXCEL EXPORT")
    print("=" * 60)
    
    # Logging ayarla
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    success = export_api_to_excel()
    
    if not success:
        print("❌ Export işlemi başarısız!")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

