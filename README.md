# E-Fatura Yönetim ve Analiz Sistemi

e-fatura XML parse, veritabanı yönetimi ve web dashboard sistemi.

## 📌 Hızlı Erişim

- 📊 **[Proje Özeti](PROJE_OZETI.md)** - Tüm fonksiyonlar ve detaylı açıklamalar
- 🚀 **[Hızlı Başlangıç](HIZLI_BASLANGIC.md)** - 3 adımda kullanım
- 📋 **[Excel Güncelleme](EXCEL_GUNCELLEME.md)** - Tek komutla tüm Excel'ler
- 📚 **[Dokümantasyon](docs/)** - Detaylı teknik belgeler

## 📁 Proje Yapısı

```
.
├── src/                          # Kaynak kodlar
│   ├── parsers/                  # XML Parser'lar
│   │   ├── akgips_parser.py      # AK GİPS için XML parser
│   │   └── fullboard_parser.py   # FULLBOARD için XML parser
│   ├── exporters/                # Excel Export modülleri
│   │   ├── akgips_exporter.py    # AK GİPS Excel export
│   │   ├── fullboard_exporter.py # FULLBOARD Excel export
│   │   └── birlesik_exporter.py  # Birleşik Excel export
│   ├── database/                 # Veritabanı işlemleri
│   │   └── merge_databases.py    # DB birleştirme
│   ├── api/                      # API Veri Çekme
│   │   └── api_data_extractor.py # İşbaşı API fatura çekme
│   └── web/                      # Web Dashboard
│       └── app.py                # Flask web uygulaması
├── data/                         # Tüm veriler
│   ├── xml/                      # XML dosyaları
│   │   ├── akgips/              # AK GİPS XML'leri
│   │   └── fullboard/           # FULLBOARD XML'leri
│   ├── db/                       # Veritabanları
│   │   ├── akgips.db            # AK GİPS veritabanı (XML)
│   │   ├── fullboard.db         # FULLBOARD veritabanı (XML)
│   │   └── birlesik.db          # ★ BİRLEŞİK DB (A + F + API)
│   ├── excel/                    # Excel çıktıları
│   │   ├── akgips/              # AK GİPS Excel'leri
│   │   ├── fullboard/           # FULLBOARD Excel'leri
│   │   ├── birlesik/            # Birleşik Excel'ler
│   │   └── api/                 # API fatura Excel'leri
│   └── logs/                     # Log dosyaları
│       └── api_extraction.log   # API çekme logları
├── tools/                        # Yardımcı araçlar
│   ├── view_db.py               # Veritabanı görüntüleme
│   ├── irsaliye_rapor.py        # İrsaliye raporu
│   └── clean_exports.py         # Excel temizleme
├── docs/                         # Dokümantasyon
│   ├── API_DATABASE_STRUCTURE.md
│   ├── BACKEND_COMPLETE.md
│   ├── BIRLESIK_SISTEM.md
│   └── KULLANIM_AKISI.md
├── start_dashboard.sh            # Dashboard başlatıcı
├── exceli_guncelle.sh            # ⚡ Tüm Excel'leri güncelle
├── update_all_excels.py          # ⚡ Excel güncelleme scripti
├── README.md                     # Bu dosya
└── HIZLI_BASLANGIC.md           # Hızlı başlangıç kılavuzu
```

## 🚀 Hızlı Başlangıç

### 1. 🌐 Web Dashboard (Önerilen - En Kolay)

```bash
./start_dashboard.sh
```

Ardından tarayıcınızda: **http://localhost:8080**

**Dashboard Özellikleri:**
- 📊 Modern gradient tasarım
- 📈 KPI kartları:
  - Toplam fatura sayısı ve tutar
  - Firma bazlı ayrıştırma (A, F, API)
  - İrsaliye ve KDV istatistikleri
- 📋 Birleşik fatura listesi (XML + API)
- 🎨 Otomatik firma renklendirme:
  - 🟠 **A** = AK GİPS (XML)
  - 🟣 **F** = FULLBOARD (XML)
  - 🔵 **API** = İşbaşı API
- ⚡ Tek birleşik veritabanından veri çeker (`birlesik.db`)

---

## 📋 İşlevler

### 🔄 XML Parse İşlemleri

#### AK GİPS XML Parse
```bash
python3 src/parsers/akgips_parser.py
```
- `data/xml/akgips/*.xml` dosyalarını okur
- `data/db/akgips.db` veritabanına aktarır

#### FULLBOARD XML Parse
```bash
python3 src/parsers/fullboard_parser.py
```
- `data/xml/fullboard/*.xml` dosyalarını okur
- `data/db/fullboard.db` veritabanına aktarır

---

### 🌐 API Fatura Çekme

```bash
python3 src/api/api_data_extractor.py
```

**Ne yapar:**
- İşbaşı API'sinden **giden** ve **gelen** faturaları çeker
- Sayfalama ile tüm verileri alır
- **Direkt `data/db/birlesik.db`'ye kaydeder** (firma_kodu: 'API')
- Excel çıktıları: `data/excel/api/API_Giden_Faturalar.xlsx` ve `API_Gelen_Faturalar.xlsx`
- Log dosyası: `data/logs/api_extraction.log`

**Özellikler:**
- 🔐 Güvenli şifre girişi
- 📊 Sayfalama ile veri çekme
- 🔴 Gelen faturalar (PURCHASE_INVOICE)
- 🟢 Giden faturalar (SALES_INVOICE)
- 💾 **Otomatik birleşik DB entegrasyonu**
- 📈 Excel formatlaması ve istatistikler

**Önemli:** API verileri otomatik olarak birleşik veritabanına eklenir, ayrı bir merge işlemi gerekmez!

---

### 🔗 Veritabanı Birleştirme (Sadece XML)

```bash
python3 src/database/merge_databases.py
```

**Ne yapar:**
- **XML veritabanlarını** birleştirir:
  - AK GİPS (XML) → firma_kodu: **A**
  - FULLBOARD (XML) → firma_kodu: **F**
- İrsaliyeleri sadeleştirir (A-14740, F-07904)
- `data/db/birlesik.db` oluşturur veya günceller

**Not:** API verileri zaten otomatik olarak `birlesik.db`'ye eklenir, bu script sadece XML verileri için gereklidir.

---

### 📊 Excel Export

#### ⚡ Tüm Excel Dosyalarını Güncelle (Önerilen)
```bash
./exceli_guncelle.sh
# veya
python3 update_all_excels.py
```

**Tek komutla tüm Excel dosyalarını günceller ve API'den veri çeker:**
- ✅ AK GİPS Excel → oluşturulur (eski dosyalar silinir)
- ✅ Birleşik Excel → oluşturulur (eski dosyalar silinir)
- ✅ FULLBOARD Excel → oluşturulur (eski dosyalar silinir)
- 🌐 **API'den veri çekme** → Şifreniz istenecek
- ✅ API Excel → oluşturulur (eski dosyalar silinir)
- 🗑️ **Otomatik temizlik** → Her klasörde sadece en güncel dosya kalır
- 📊 İlerleme takibi ve özet rapor
- ⚠️ Hata yönetimi ve atlama

**API veri çekmeyi atlamak için:**
```bash
./exceli_guncelle.sh --skip-api
# veya
python3 update_all_excels.py --skip-api
```

---

#### AK GİPS Excel (Tekil)
```bash
python3 src/exporters/akgips_exporter.py
```
Çıktı: `data/excel/akgips/efatura_akgips_YYYYMMDD_HHMMSS.xlsx`

#### FULLBOARD Excel (Tekil)
```bash
python3 src/exporters/fullboard_exporter.py
```
Çıktı: `data/excel/fullboard/efatura_fullboard_YYYYMMDD_HHMMSS.xlsx`

#### Birleşik Excel (Tekil)
```bash
python3 src/exporters/birlesik_exporter.py
```
Çıktı: `data/excel/birlesik/efatura_birlesik.xlsx`

#### API Excel (Tekil)
```bash
python3 src/exporters/api_exporter.py
```
Çıktı: `kayıtlar/API_Faturalar_YYYYMMDD_HHMMSS.xlsx`

**Excel İçeriği:**
- **Özet**: Genel istatistikler
- **Faturalar**: Tüm fatura bilgileri
- **Fatura Satırları**: Detaylı kalem bilgileri (ADET hesaplamalı)
- **İrsaliyeler**: İrsaliye listesi (kısa ve tam numara)

---

### 🛠️ Yardımcı Araçlar

#### Veritabanı Görüntüleme
```bash
python3 tools/view_db.py
```
Veritabanı içeriğini terminalde gösterir.

#### İrsaliye Raporu
```bash
python3 tools/irsaliye_rapor.py
```
İrsaliye bazlı detaylı rapor üretir.

#### Excel Temizleme
```bash
python3 tools/clean_exports.py
```
- Tüm Excel dosyalarını sil
- Sadece en yenisini tut, eskileri sil

---

## 🗂️ Veritabanı Yapısı

### 1. **invoices** (Faturalar)
- Fatura temel bilgileri
- Firma kodu (birleşik DB'de)
- Satıcı ve müşteri bilgileri
- Toplam tutar, KDV matrahı

### 2. **invoice_lines** (Fatura Satırları)
- Ürün/hizmet detayları
- Miktar, birim, fiyat
- ADET hesaplaması (TNE → miktar × 1000 ÷ 35)

### 3. **despatch_documents** (İrsaliyeler)
- İrsaliye numaraları (kısa ve tam)
- İrsaliye tarihi
- Fatura ilişkilendirme

### 4. **attachments** (Ekler)
- XSLT ve diğer dosyalar
- Base64 encoded veri

---

## 🔧 Kurulum

### Gereksinimler
```bash
pip3 install flask openpyxl
```

**Bağımlılıklar:**
- Python 3.x
- `flask` - Web dashboard
- `openpyxl` - Excel export

---

## 💾 Veritabanı Sorguları

```bash
sqlite3 data/db/birlesik.db
```

### Örnek Sorgular:

```sql
-- Tüm faturaları listele
SELECT firma_kodu, invoice_number, issue_date, total_amount 
FROM invoices 
ORDER BY issue_date DESC;

-- Firma bazlı toplam
SELECT firma_kodu, 
       COUNT(*) as fatura_sayisi,
       SUM(total_amount) as toplam_tutar
FROM invoices
GROUP BY firma_kodu;

-- Fatura satırları
SELECT i.invoice_number, il.item_name, il.quantity, il.line_total
FROM invoice_lines il
JOIN invoices i ON il.invoice_id = i.id;

-- İrsaliye raporu
SELECT i.firma_kodu, i.invoice_number, 
       d.despatch_id_short, d.issue_date
FROM despatch_documents d
JOIN invoices i ON d.invoice_id = i.id
ORDER BY i.invoice_number;
```

---

## 🎯 Kullanım Senaryoları

### Senaryo 1: Yeni XML Faturalar Ekleme
```bash
# 1. XML dosyalarını ilgili klasöre kopyala
cp yeni_faturalar/*.xml data/xml/akgips/

# 2. Parser'ı çalıştır
python3 src/parsers/akgips_parser.py

# 3. Veritabanlarını birleştir
python3 src/database/merge_databases.py

# 4. Dashboard'u başlat
./start_dashboard.sh
```

### Senaryo 1b: API'den Fatura Çekme
```bash
# 1. API veri çekme scriptini çalıştır
python3 src/api/api_data_extractor.py
# Şifrenizi girin
# → Veriler otomatik olarak birlesik.db'ye eklenir (firma_kodu: API)

# 2. Dashboard'u başlat
./start_dashboard.sh
# → XML + API verileri birlikte görünür
```

**Not:** API scripti verileri otomatik olarak `birlesik.db`'ye ekler, ayrı merge gerekmez!

### Senaryo 2: Excel Rapor Çıkarma
```bash
# Tüm Excel dosyalarını oluştur (Önerilen)
./exceli_guncelle.sh

# Veya sadece birleşik rapor
python3 src/exporters/birlesik_exporter.py

# Excel dosyaları:
# - data/excel/akgips/efatura_akgips_*.xlsx
# - data/excel/fullboard/efatura_fullboard_*.xlsx
# - data/excel/birlesik/efatura_birlesik.xlsx
# - kayıtlar/API_Faturalar_*.xlsx
```

### Senaryo 3: Veritabanı Analizi
```bash
# Konsol görüntüleme
python3 tools/view_db.py

# İrsaliye raporu
python3 tools/irsaliye_rapor.py

# Veya direkt SQL
sqlite3 data/db/birlesik.db "SELECT * FROM invoices LIMIT 10"
```

---

## 🔍 Sorun Giderme

### Port 5000 Kullanımda Hatası
MacOS'ta AirPlay Receiver genellikle 5000 portunu kullanır. Dashboard otomatik olarak 8080 portunu kullanır.

### Veritabanı Bulunamadı
```bash
# Veritabanını yeniden oluştur
python3 src/parsers/akgips_parser.py
python3 src/database/merge_databases.py
```

### Excel Boş Çıkıyor
Önce veritabanında veri olduğundan emin olun:
```bash
python3 tools/view_db.py
```

---

## 📝 Notlar

- ✅ XML dosyaları UBL-TR 2.1 formatında olmalıdır
- ✅ Tüm path'ler proje kök dizinine göre relatif çalışır
- ✅ Web dashboard otomatik olarak birleşik DB'yi tercih eder
- ✅ Excel dosyaları timestamp ile oluşturulur
- ✅ Tüm araçlar proje kök dizininden çalıştırılabilir

---

**Versiyon:** 2.1 (API Entegrasyonu)  
**Son Güncelleme:** 15 Ekim 2025  

🎉 **Modern, Temiz, Profesyonel - XML + API Entegrasyonu!**
