# 🔍 Fatura Eşleştirme Sistemi

Bu proje, API'den gönderilen faturaların description alanından irsaliye kodlarını çıkarıp, XML kaynaklı gelen faturalarla eşleştiren bir sistemdir.

## 📋 İçindekiler

- [Hızlı Başlangıç](#-hızlı-başlangıç)
- [Sistem Mimarisi](#-sistem-mimarisi)
- [Veri Akışı](#-veri-akışı)
- [Backend Agents (Stateful Postgres Ingestion)](#-backend-agents-stateful-postgres-ingestion)
- [Proje Yapısı](#-proje-yapısı)
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
python3 scripts/tools/invoice_matcher.py
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
python3 archive/legacy_src/parsers/akgips_parser.py
```
- `data/xml/akgips/*.xml` → `data/db/akgips.db`
- İrsaliye kodu formatı: `A-18356`

**Fullboard XML'leri:**
```bash
python3 archive/legacy_src/parsers/fullboard_parser.py
```
- `data/xml/fullboard/*.xml` → `data/db/fullboard.db`
- İrsaliye kodu formatı: `F-9171`

### 2️⃣ API'den Giden Faturaları Çek

```bash
python3 ingestion/api_data_extractor.py
```

**Ne yapar:**
- İşbaşı API'sinden **giden faturaları** çeker (API tarafı filtre sorunları nedeniyle filtreleme kod içinde yapılır: `type != PURCHASE_INVOICE`)
- Şifre ile güvenli giriş
- Excel çıktısı: `data/excel/api/API_Giden_Faturalar.xlsx`
- Excel çıktısında ayrıca `type` gibi ek alanlar da bulunabilir
- Ek olarak API verilerini ayrı bir veritabanına da yazar: `data/db/api.db`
- Description alanında irsaliye kodları bulunur

**Not (GitHub):** `ingestion/api_data_extractor.py` çalışması için `ISBASI_API_KEY` ve `ISBASI_USERNAME` ortam değişkenleri gerekir.
Örnek:
```bash
cp env.example .env
# sonra .env içini doldurun
python3 ingestion/api_data_extractor.py
```

### 3️⃣ Fatura Eşleştirme Raporunu Oluştur

```bash
python3 scripts/tools/invoice_matcher.py
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

**Detaylı dokümantasyon:** `scripts/tools/README_invoice_matcher.md`

---

## 🤖 Backend Agents (Stateful Postgres Ingestion)

**Yeni!** API verilerini Postgres'e stateful (durum takipli) olarak aktaran agent'lar:

### Özellikler
- ✅ **Stateful Ingestion**: Her agent son işlediği `issue_date`'i takip eder
- ✅ **Incremental Updates**: Sadece yeni/değişen faturalar işlenir
- ✅ **Change Detection**: Row hash ile değişiklikler tespit edilir
- ✅ **İrsaliye Normalizasyonu**: Otomatik IRS-XXXXX formatına çevirir
- ✅ **Upsert Logic**: Yoksa insert, varsa (değiştiyse) update

### Kurulum

```bash
# 1. PostgreSQL kur ve database oluştur
createdb invoices

# 2. Schema'yı migrate et
psql invoices < sql/stateful_ingestion_schema_v2.sql

# 3. .env dosyasını yapılandır
cp env.example .env
# DB_URL=postgresql://user:password@localhost:5432/invoices ekle

# 4. Python paketlerini kur
pip install -r requirements.txt
```

### Kullanım

```bash
# Gelen fatura agent'ı (incoming invoices)
python backend/agents/incoming_agent.py

# Giden fatura agent'ı (outgoing invoices)
python backend/agents/outgoing_agent.py
```

### Çıktı Örneği

```
🚀 INCOMING INVOICE AGENT STARTING
============================================================
📅 Fetching invoices from 2026-01-01 to 2026-02-10
✅ Fetched 156 invoices from API
============================================================
📊 INCOMING INVOICE AGENT RESULTS
============================================================
✅ Inserted: 150
🔄 Updated: 6
⚪ Unchanged: 0
📅 Max issue_date: 2026-02-10
============================================================
```

**Detaylı dokümantasyon:**
- `backend/README.md` - Agent kullanım kılavuzu
- `docs/V2_PRODUCTION_READY.md` - v2.0 sistem özeti
- `PROJECT_STRUCTURE.md` - Proje yapısı detayları

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

**Yeni yapı:** v2.1.1 (Temiz ve organize edilmiş)

```
gelen efaturalar deneme/
├── backend/                       🤖 Production ingestion system
│   ├── core/                      Core utilities
│   │   ├── config.py             ⚙️ Configuration management
│   │   ├── db.py                 💾 Database helpers (psycopg2)
│   │   ├── agent_state.py        📅 Agent state tracking
│   │   ├── normalize.py          🔧 İrsaliye normalization
│   │   └── agent_run_logger.py   📊 Run history logging
│   ├── agents/                    Agent implementations
│   │   ├── incoming_agent.py     📥 Gelen fatura ingestion
│   │   └── outgoing_agent.py     📤 Giden fatura ingestion
│   └── README.md                 📖 Agent documentation
│
├── ingestion/                     🌐 API extractors (v2.0+)
│   ├── api_data_extractor.py     Outgoing invoice extractor
│   └── api_incoming_invoices_extractor.py  Incoming invoice extractor
│
├── sql/                           💾 Database schemas
│   ├── stateful_ingestion_schema_v2.sql  Current schema (v2.1.1)
│   ├── stateful_ingestion_schema.sql     Legacy v1.0
│   └── postgres_schema.sql               Original schema
│
├── scripts/                       🛠️ Utilities and tools
│   ├── agent_monitor.py          CLI monitoring tool
│   ├── setup_postgres.sh         Database setup
│   ├── verify_installation.py    Installation check
│   └── tools/                    Additional tools
│       ├── invoice_matcher.py    ⭐ Invoice matcher
│       └── README_invoice_matcher.md
│
├── docs/                          📚 All documentation
│   ├── V2_PRODUCTION_READY.md    Main v2.0 docs
│   ├── ADVANCED_MONITORING.md    v2.1.1 monitoring
│   ├── AGENT_RUN_LOGGING.md      v2.1.0 logging
│   ├── TRANSACTION_PER_BATCH.md  v2.0.1 transactions
│   └── ... (changelogs, etc.)
│
├── archive/                       📦 Legacy code (preserved)
│   └── legacy_src/               Old src/ folder
│       ├── api_database.py       Old DB wrapper
│       ├── db/                   Old DB utilities
│       └── parsers/              Old XML parsers
│           ├── akgips_parser.py
│           └── fullboard_parser.py
│
├── data/                          📊 Data files (not in repo)
│   ├── db/                       SQLite databases
│   ├── excel/                    Excel exports
│   ├── xml/                      XML invoices
│   └── logs/                     Log files
│
├── kayıtlar/                      📈 Matching reports
├── .env                           ⚙️ Environment config (not in repo)
├── env.example                    ⚙️ Example config
├── requirements.txt               📦 Dependencies
├── README.md                      📖 This file
├── QUICKSTART.md                  🚀 Quick start guide
└── PROJECT_STRUCTURE.md           📁 Detailed structure docs
```

**Detaylı bilgi:** `PROJECT_STRUCTURE.md`

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

# 2. Yeniden parse et (legacy)
python3 archive/legacy_src/parsers/akgips_parser.py
python3 archive/legacy_src/parsers/fullboard_parser.py
```

### API Verileri Güncelleme

Giden faturaları güncellemek için:
```bash
# Legacy extractor (eski yöntem)
python3 ingestion/api_data_extractor.py

# Modern agent (önerilen - v2.0+)
python3 backend/agents/outgoing_agent.py
```

---

## 📞 Sorun Giderme

### "API Excel dosyası bulunamadı"
```bash
# Excel'in varlığını kontrol edin
ls -l data/excel/api/API_Giden_Faturalar.xlsx

# Yoksa API'den çekin
python3 ingestion/api_data_extractor.py
```

### "Veritabanı bulunamadı"
```bash
# Veritabanlarını kontrol edin
ls -l data/db/akgips.db data/db/fullboard.db

# Yoksa XML'leri parse edin (legacy)
python3 archive/legacy_src/parsers/akgips_parser.py
python3 archive/legacy_src/parsers/fullboard_parser.py
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

**Son Güncelleme:** 10 Şubat 2026

### Yeni Özellikler (v2.1.1)
- 🤖 Backend agents: Stateful Postgres ingestion
- 📅 Agent state tracking (incremental updates)
- 🔄 Change detection with row hashing
- 🔧 İrsaliye code normalization (IRS-XXXXX)
- ⚡ Upsert logic (insert/update)
- 📊 Agent run logging (v2.1.0)
- 🖥️ Advanced monitoring: host/version/batch tracking (v2.1.1)
- 🔒 Transaction-per-batch safety (v2.0.1)

**Proje yapısı temizlendi (v2.1.1):**
- ✅ `backend/` - Production code
- ✅ `ingestion/` - API extractors
- ✅ `docs/` - All documentation
- ✅ `archive/` - Legacy code preserved
- ✅ `scripts/` - Utilities organized

Detaylı değişiklik listesi: `docs/CHANGELOG_v2.1.1.md`
