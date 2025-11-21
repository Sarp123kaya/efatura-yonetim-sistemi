#!/bin/bash

echo "======================================"
echo "VERİTABANLARINI YENİDEN OLUŞTURMA"
echo "======================================"
echo ""

# Proje dizinine git
cd "$(dirname "$0")"

# 1. Eski veritabanlarını sil
echo "📦 Eski veritabanları siliniyor..."
rm -f data/db/akgips.db
rm -f data/db/fullboard.db
rm -f data/db/birlesik.db
echo "✅ Eski veritabanları silindi"
echo ""

# 2. XML'leri parse et (Akgips)
echo "🔄 Akgips XML'leri parse ediliyor..."
python3 src/parsers/akgips_parser.py
echo ""

# 3. XML'leri parse et (Fullboard)
echo "🔄 Fullboard XML'leri parse ediliyor..."
python3 src/parsers/fullboard_parser.py
echo ""

# 4. Veritabanlarını birleştir
echo "🔄 Veritabanları birleştiriliyor..."
python3 src/database/merge_databases.py
echo ""

# 5. API verilerini import et (Excel'den)
echo "🔄 API verileri import ediliyor..."
python3 import_api_excel.py
echo ""

# 6. Excel export
echo "📊 Excel export ediliyor..."
python3 src/exporters/birlesik_exporter.py
echo ""

echo "======================================"
echo "✅ İŞLEM TAMAMLANDI!"
echo "======================================"
echo ""
echo "📄 Şimdi şunu kontrol edin:"
echo "   data/excel/birlesik/efatura_birlesik.xlsx"
echo ""
echo "Faturalar sayfasında 'Açıklama' sütununu kontrol edin."
echo ""

