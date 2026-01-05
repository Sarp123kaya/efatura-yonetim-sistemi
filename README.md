# 🔍 Fatura Eşleştirme Sistemi

Bu proje, API'den gönderilen faturaların description alanından irsaliye kodlarını çıkarıp, XML kaynaklı gelen faturalarla eşleştiren bir sistemdir.

## 📋 İçindekiler

- [Hızlı Başlangıç](#-hızlı-başlangıç)
- [Sistem Mimarisi](#-sistem-mimarisi)
- [Veri Akışı](#-veri-akışı)
- [Kullanım Kılavuzu](#-kullanım-kılavuzu)
- [Veritabanı Yapıları](#-veritabanı-yapıları)

---

## 🚀 Hızlı Başlangıç

### Gereksinimler

```bash
pip install -r requirements.txt
```

### Temel Kullanım

```bash
# Fatura eşleştirme raporunu oluştur
python3 tools/invoice_matcher.py
```

**Çıktı:** `kayıtlar/Fatura_Eslesme_Raporu_YYYYMMDD_HHMMSS.xlsx`

---

## 🏗️ Sistem Mimarisi

```
┌─────────────────────┐
│   XML Dosyaları     │
│  (AkGips/Fullboard) │
└──────────┬──────────┘
           │
           ▼
    ┌──────────────┐
    │   Parsers    │
    │ akgips.py    │
    │ fullboard.py │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐       ┌─────────────────┐
    │ akgips.db    │       │   API Extractor │
    │ fullboard.db │       │ (Giden Faturalar)│
    └──────┬───────┘       └────────┬────────┘
           │                        │
           │                        ▼
           │              ┌─────────────────────┐
           │              │ API_Giden_Faturalar │
           │              │      .xlsx          │
           │              └──────┬──────────────┘
           │                     │
           └─────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Invoice Matcher     │
          │  (Eşleştirme Motoru) │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Fatura_Eslesme_     │
          │  Raporu_*.xlsx       │
          └──────────────────────┘
```

---

## 🔄 Veri Akışı

### 1️⃣ XML'leri Parse Et

**AkGips XML'leri:**
```bash
python3 src/parsers/akgips_parser.py
```
- `data/xml/akgips/*.xml` → `data/db/akgips.db`
- İrsaliye kodu formatı: `A-18356`

**Fullboard XML'leri:**
```bash
python3 src/parsers/fullboard_parser.py
```
- `data/xml/fullboard/*.xml` → `data/db/fullboard.db`
- İrsaliye kodu formatı: `F-9171`

### 2️⃣ API'den Giden Faturaları Çek

```bash
python3 src/api/api_data_extractor.py
```

**Ne yapar:**
- İşbaşı API'sinden **giden faturaları** çeker (API tarafı filtre sorunları nedeniyle filtreleme kod içinde yapılır: `type != PURCHASE_INVOICE`)
- Şifre ile güvenli giriş
- Excel çıktısı: `data/excel/api/API_Giden_Faturalar.xlsx`
- Excel çıktısında ayrıca `type` gibi ek alanlar da bulunabilir
- Ek olarak API verilerini ayrı bir veritabanına da yazar: `data/db/api.db`
- Description alanında irsaliye kodları bulunur

**Not (GitHub):** `src/api/api_data_extractor.py` çalışması için `ISBASI_API_KEY` ve `ISBASI_USERNAME` ortam değişkenleri gerekir.
Örnek:
```bash
cp env.example .env
# sonra .env içini doldurun
python3 src/api/api_data_extractor.py
```

### 3️⃣ Fatura Eşleştirme Raporunu Oluştur

```bash
python3 tools/invoice_matcher.py
```

**İşlem Adımları:**
1. API Excel'den giden faturaları okur
2. Description'dan irsaliye kodlarını çıkarır (regex ile)
3. Prefix'e göre veritabanını belirler (A→akgips.db, F→fullboard.db)
4. Her irsaliye için gelen faturayı arar
5. Eşleşenleri ve bulunmayanları raporlar
6. Formatlanmış Excel raporu oluşturur

**Rapor İçeriği:**
- ✅ Eşleşen faturalar (**Durum hücresi** yeşil)
- ❌ Bulunamayan faturalar (**Durum hücresi** kırmızı)
- ⚠️ İrsaliye kodu olmayan faturalar (**Durum hücresi** sarı)
- Tutar farkları ve KDV hesaplamaları
- İstatistik özeti

**Detaylı dokümantasyon:** `tools/README_invoice_matcher.md`

---

## 🗄️ Veritabanı Yapıları

### akgips.db / fullboard.db

**invoices tablosu:**
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,           -- XML dosya adı
    invoice_number TEXT,        -- Fatura numarası
    issue_date TEXT,            -- Düzenleme tarihi
    total_amount REAL,          -- Toplam tutar
    supplier_name TEXT,         -- Satıcı adı
    customer_name TEXT,         -- Müşteri adı
    description TEXT,           -- Açıklama
    -- ... diğer alanlar
)
```

**despatch_documents tablosu:**
```sql
CREATE TABLE despatch_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,         -- invoices.id foreign key
    despatch_id TEXT,           -- Tam irsaliye ID
    despatch_id_short TEXT,     -- Kısa format (A-18356, F-9171)
    issue_date TEXT,            -- İrsaliye tarihi
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
)
```

---

## 📁 Proje Yapısı

```
gelen efaturalar deneme/
├── tools/
│   ├── invoice_matcher.py          ⭐ Ana eşleştirme aracı
│   └── README_invoice_matcher.md   📖 Detaylı dokümantasyon
├── src/
│   ├── api/
│   │   ├── api_data_extractor.py   🌐 API'den veri çekme
│   │   └── api_database.py         💾 API DB yönetimi
│   └── parsers/
│       ├── akgips_parser.py        🔧 AkGips XML parser
│       └── fullboard_parser.py     🔧 Fullboard XML parser
├── data/
│   ├── db/
│   │   ├── akgips.db              💾 AkGips veritabanı
│   │   └── fullboard.db           💾 Fullboard veritabanı
│   ├── excel/
│   │   └── api/
│   │       └── API_Giden_Faturalar.xlsx  📊 Giden faturalar
│   ├── logs/
│   │   └── api_extraction.log     📝 API işlem logları
│   └── xml/
│       ├── akgips/                📄 AkGips XML dosyaları (79 adet)
│       └── fullboard/             📄 Fullboard XML dosyaları (282 adet)
├── kayıtlar/
│   └── Fatura_Eslesme_Raporu_*.xlsx  📈 Eşleştirme raporları
├── requirements.txt               📦 Python bağımlılıkları
└── README.md                      📖 Bu dosya
```

---

## 🔍 İrsaliye Kodu Formatları

**Desteklenen Formatlar:**
- `İRSALİYE NO: A-18356` ✅ Standart
- `İRSALİYE NO: F-9171 ( İSTANBUL )` ✅ Lokasyon ile
- `İRSALİYE NO: F-9170 / F-9189` ✅ Çoklu (/ ile)
- `İRSALİYE NO:F/9099/F-9098` ✅ Birleşik
- `İRSALİYE NO: F- 9026` ✅ Boşluklu
- `İRSALİYE NO: 18277` ❌ ATLANIR (prefix yok)

**Regex Pattern:** `([AF])\s*[-/]\s*(\d{4,5})`

---

## 📊 Örnek Çıktı

```
======================================================================
🔍 FATURA EŞLEŞTIRME ARACI
======================================================================

📊 Giden faturalar işleniyor...

📈 İstatistikler:
   ✓ Eşleşen: 367
   ✗ Bulunamayan: 240
   ⚠ İrsaliye kodu yok: 1488
   📝 Toplam: 2095

📝 Excel raporu oluşturuluyor...

======================================================================
✅ İŞLEM TAMAMLANDI
======================================================================
📄 Rapor: kayıtlar/Fatura_Eslesme_Raporu_20260102_170307.xlsx
```

---

## 🛠️ Geliştirici Notları

### Önemli Fonksiyonlar

**invoice_matcher.py:**
- `extract_irsaliye_codes()` - Regex ile irsaliye çıkarma
- `search_in_database()` - Veritabanında eşleşme arama
- `process_api_invoices()` - Ana işlem döngüsü
- `generate_excel_report()` - Excel rapor oluşturma

### Veritabanı Güncelleme

XML dosyaları güncellendiğinde:
```bash
# 1. Eski DB'leri sil
rm -f data/db/akgips.db data/db/fullboard.db

# 2. Yeniden parse et
python3 src/parsers/akgips_parser.py
python3 src/parsers/fullboard_parser.py
```

### API Verileri Güncelleme

Giden faturaları güncellemek için:
```bash
python3 src/api/api_data_extractor.py
```

---

## 📞 Sorun Giderme

### "API Excel dosyası bulunamadı"
```bash
# Excel'in varlığını kontrol edin
ls -l data/excel/api/API_Giden_Faturalar.xlsx

# Yoksa API'den çekin
python3 src/api/api_data_extractor.py
```

### "Veritabanı bulunamadı"
```bash
# Veritabanlarını kontrol edin
ls -l data/db/akgips.db data/db/fullboard.db

# Yoksa XML'leri parse edin
python3 src/parsers/akgips_parser.py
python3 src/parsers/fullboard_parser.py
```

### Boş Eşleşme Sonuçları
```bash
# despatch_documents tablosunu kontrol edin
sqlite3 data/db/akgips.db "SELECT COUNT(*) FROM despatch_documents"
sqlite3 data/db/fullboard.db "SELECT COUNT(*) FROM despatch_documents"
```

---

## 📦 Bağımlılıklar

- `pandas` - Excel okuma/yazma
- `xlsxwriter` - Excel formatlaması
- `requests` - API istekleri
- `sqlite3` - Veritabanı (built-in)

---

## 📄 Lisans

Bu proje dahili kullanım için geliştirilmiştir.

---

**Son Güncelleme:** 2 Ocak 2026
