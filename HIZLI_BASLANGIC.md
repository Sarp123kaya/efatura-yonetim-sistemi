# 🚀 Hızlı Başlangıç Kılavuzu

## 📊 E-Fatura Sistemi - 3 Adımda Kullanım

### ✨ Yeni Kullanıcılar İçin

#### 1️⃣ XML Faturalarını İşle
```bash
# AK GİPS XML'lerini parse et
python3 src/parsers/akgips_parser.py

# FULLBOARD XML'lerini parse et  
python3 src/parsers/fullboard_parser.py

# İkisini birleştir
python3 src/database/merge_databases.py
```

#### 2️⃣ API Faturalarını Çek (Opsiyonel)
```bash
# API'den faturaları çek (otomatik birleşik DB'ye eklenir)
python3 src/api/api_data_extractor.py
```
Şifrenizi girin → Veriler otomatik olarak `birlesik.db`'ye eklenir!

#### 3️⃣ Dashboard'u Başlat
```bash
./start_dashboard.sh
```
Tarayıcıda **http://localhost:8080** adresini açın

---

## 🔄 Düzenli Kullanım

### Yeni XML Faturaları Eklemek
```bash
# 1. Yeni XML'leri ilgili klasöre kopyala
cp yeni_faturalar/*.xml data/xml/akgips/

# 2. Parser'ı çalıştır
python3 src/parsers/akgips_parser.py

# 3. Birleştir
python3 src/database/merge_databases.py

# 4. Dashboard'u başlat
./start_dashboard.sh
```

### Yeni API Faturaları Çekmek
```bash
# Direkt çalıştır (birleşik DB'ye otomatik eklenir)
python3 src/api/api_data_extractor.py

# Dashboard'u başlat
./start_dashboard.sh
```

**Önemli:** API scripti verileri otomatik olarak birleşik DB'ye ekler!

---

## 📊 Dashboard'da Ne Göreceksiniz?

### KPI Kartları:
- 📊 Toplam fatura sayısı ve tutar
- 🟠 **A** - AK GİPS faturaları
- 🟣 **F** - FULLBOARD faturaları  
- 🔵 **API** - API faturaları
- 📦 İrsaliye sayısı

### Fatura Tablosu:
Tüm faturalar firma kodlarıyla birlikte tek tabloda

---

## 💾 Veritabanı Yapısı

```
birlesik.db (Tek Veritabanı)
├── A - AK GİPS faturaları (XML)
├── F - FULLBOARD faturaları (XML)
└── API - API faturaları (otomatik)
```

**Tek veritabanı**, 3 farklı kaynak!

---

## 🎯 Sık Sorulan Sorular

### API verilerini ekledikten sonra merge gerekli mi?
**Hayır!** API scripti verileri otomatik olarak `birlesik.db`'ye ekler.

### Excel rapor nasıl çıkarırım?
```bash
# Tüm Excel dosyalarını oluştur + API'den veri çek (Önerilen)
./exceli_guncelle.sh

# API veri çekmeyi atlamak için
./exceli_guncelle.sh --skip-api

# Veya sadece birleşik Excel
python3 src/exporters/birlesik_exporter.py
```

**Ne yapar:**
1. İlk 3 Excel'i oluşturur (akgips, birlesik, fullboard)
2. API'den yeni fatura verileri çeker (şifre ister)
3. API Excel'ini oluşturur

Çıktılar:
- `data/excel/akgips/efatura_akgips_*.xlsx` (sadece 1 dosya)
- `data/excel/fullboard/efatura_fullboard_*.xlsx` (sadece 1 dosya)
- `data/excel/birlesik/efatura_birlesik.xlsx` (sabit isim)
- `kayıtlar/API_Faturalar_*.xlsx` (sadece 1 dosya)

**Not:** Her çalıştırmada eski Excel dosyaları otomatik silinir, sadece en güncel dosya kalır.

### Veritabanında kaç fatura var?
```bash
sqlite3 data/db/birlesik.db "SELECT firma_kodu, COUNT(*) FROM invoices GROUP BY firma_kodu"
```

### Dashboard çalışmıyor?
```bash
# 1. Port 8080'i kontrol et
lsof -i :8080

# 2. Veritabanını kontrol et
ls -lh data/db/birlesik.db

# 3. Dashboard'u yeniden başlat
./start_dashboard.sh
```

---

## 📝 İpuçları

1. ✅ **API scripti** her çalıştığında yeni verileri `birlesik.db`'ye ekler
2. ✅ **XML parsers** her çalıştığında ilgili DB'yi günceller
3. ✅ **merge_databases.py** XML DB'leri birleştirir (API için gerekli değil)
4. ✅ **Dashboard** her zaman `birlesik.db`'den okur

---

**Versiyon:** 2.1 (Otomatik Birleştirme)  
**Güncelleme:** 15 Ekim 2025

🎉 **Artık daha basit ve otomatik!**
