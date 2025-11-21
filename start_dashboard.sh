#!/bin/bash
# E-Fatura Web Dashboard Başlatıcı

echo "======================================================================"
echo "🚀 E-FATURA WEB DASHBOARD BAŞLATILIYOR"
echo "======================================================================"
echo ""

# Proje dizinine git
cd "$(dirname "$0")"

# Virtual environment'ı aktif et
if [ -d ".venv" ]; then
    echo "✓ Virtual environment aktif ediliyor..."
    source .venv/bin/activate
    
    # Flask kontrolü (venv içinde)
    if ! python3 -c "import flask" 2>/dev/null; then
        echo ""
        echo "❌ Flask virtual environment'ta kurulu değil!"
        echo ""
        echo "Kurulum için:"
        echo "  source .venv/bin/activate"
        echo "  pip3 install flask"
        echo ""
        exit 1
    fi
else
    echo "⚠️  Virtual environment bulunamadı (.venv)"
    echo ""
    echo "❌ Virtual environment gerekli!"
    echo ""
    echo "Oluşturmak için:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip3 install flask openpyxl"
    echo ""
    exit 1
fi

# Port kontrolü
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo ""
    echo "⚠️  Port 8080 kullanımda!"
    echo "   Mevcut process sonlandırılıyor..."
    pkill -f "simple_web_dashboard" 2>/dev/null
    sleep 1
fi

echo ""
echo "======================================================================"
echo "📊 Dashboard başlatılıyor..."
echo ""
echo "   🌐 Adres: http://localhost:8080"
echo ""
echo "   💡 Tarayıcınızda yukarıdaki adresi açın"
echo "   ⏹️  Durdurmak için: Ctrl+C"
echo "======================================================================"
echo ""

# Dashboard'u başlat
python3 src/web/app.py

