#!/bin/bash
# Tüm Excel dosyalarını güncelleme scripti

# Script'in bulunduğu dizine git
cd "$(dirname "$0")"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          TÜM EXCEL DOSYALARINI GÜNCELLEME                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Python3 kontrolü
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 bulunamadı!"
    exit 1
fi

# Kullanım bilgisi
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Kullanım:"
    echo "  ./exceli_guncelle.sh              # API veri çekme dahil"
    echo "  ./exceli_guncelle.sh --skip-api   # API veri çekmeyi atla"
    echo ""
    exit 0
fi

# Script'i çalıştır
python3 update_all_excels.py "$@"

# Çıkış kodu
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ Tüm Excel dosyaları başarıyla güncellendi!"
    echo ""
elif [ $exit_code -eq 130 ]; then
    echo ""
    echo "⚠️  İşlem iptal edildi"
    echo ""
else
    echo ""
    echo "⚠️  Bazı dosyalar güncellenirken hata oluştu (Çıkış Kodu: $exit_code)"
    echo ""
fi

exit $exit_code

