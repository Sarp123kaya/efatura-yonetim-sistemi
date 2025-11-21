# 🗄️ Veritabanı Yapıları - Tam Özet

## 📊 Genel Bakış

Projede **4 ana veritabanı** bulunmaktadır:

| Veritabanı | Kaynak | Firma Kodu | Dosya Yolu |
|------------|--------|-----------|-----------|
| **akgips.db** | XML | A | `data/db/akgips.db` |
| **fullboard.db** | XML | F | `data/db/fullboard.db` |
| **api.db** | İşbaşı API | API | `data/db/api.db` |
| **birlesik.db** | Tümü | A/F/API | `data/db/birlesik.db` |

---

## 1️⃣ **akgips.db** (AK GİPS - XML Kaynaklı)

### Tablolar:

#### `invoices` - Ana Fatura Tablosu
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,              -- XML dosya adı
    parse_date TEXT NOT NULL,               -- Parse tarihi
    invoice_id TEXT,                        -- Fatura ID
    uuid TEXT,                              -- UUID
    invoice_number TEXT,                    -- Fatura numarası
    issue_date TEXT,                        -- Düzenleme tarihi
    total_amount REAL,                      -- Toplam tutar
    currency TEXT,                          -- Para birimi (TRY)
    taxable_amount REAL,                    -- Vergi matrahı
    tax_amount REAL,                        -- KDV tutarı
    supplier_name TEXT,                     -- Satıcı adı
    supplier_vkn TEXT,                      -- Satıcı VKN
    customer_name TEXT,                     -- Müşteri adı
    customer_vkn TEXT,                      -- Müşteri VKN
    description TEXT,                       -- Fatura açıklaması
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

#### `attachments` - Fatura Ekleri
```sql
CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    filename TEXT,                          -- Ek dosya adı
    mime_type TEXT,                         -- MIME tipi
    encoding TEXT,                          -- Encoding (base64)
    charset TEXT,                           -- Karakter seti
    data_base64 TEXT,                       -- Base64 veri
    decoded_size INTEGER,                   -- Decode sonrası boyut
    decoded_preview TEXT,                   -- İlk 200 karakter
    decode_error TEXT,                      -- Hata varsa
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
)
```

#### `invoice_lines` - Fatura Satırları
```sql
CREATE TABLE invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    line_id TEXT,                           -- Satır ID
    item_name TEXT,                         -- Ürün/hizmet adı
    quantity REAL,                          -- Miktar
    unit TEXT,                              -- Birim (C62, etc)
    unit_price REAL,                        -- Birim fiyat
    line_total REAL,                        -- Satır toplamı
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
)
```

#### `despatch_documents` - İrsaliye Belgeleri
```sql
CREATE TABLE despatch_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    despatch_id_full TEXT NOT NULL,        -- Tam irsaliye no (IRS2025000014740)
    despatch_id_short TEXT NOT NULL,       -- Kısa no (IRS14740)
    issue_date TEXT,                        -- İrsaliye tarihi
    description TEXT,                       -- Açıklama
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
)
```

---

## 2️⃣ **fullboard.db** (FULLBOARD - XML Kaynaklı)

**Yapı akgips.db ile tamamen aynıdır.**

Tek fark XML kaynak dizini: `data/xml/fullboard/`

---

## 3️⃣ **api.db** (İşbaşı API Kaynaklı) ✨ YENİ

### Tablolar:

#### `invoices` - Ana Fatura Tablosu
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id TEXT NOT NULL UNIQUE,           -- API'den gelen orijinal ID
    source TEXT DEFAULT 'API',              -- Kaynak
    parse_date TEXT NOT NULL,               -- Çekilme tarihi
    invoice_number TEXT,                    -- Fatura numarası
    invoice_type TEXT,                      -- SALES_INVOICE / PURCHASE_INVOICE
    issue_date TEXT,                        -- Fatura tarihi
    total_amount REAL,                      -- Toplam tutar (TL)
    currency TEXT DEFAULT 'TRY',            -- Para birimi
    taxable_amount REAL,                    -- Vergi matrahı
    firm_name TEXT,                         -- Firma adı
    firm_vkn TEXT,                          -- Firma VKN
    description TEXT,                       -- Açıklama (banka bilgileri temizlenmiş)
    raw_json TEXT,                          -- Ham JSON (yedek)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Index:**
```sql
CREATE UNIQUE INDEX idx_unique_api_invoice 
ON invoices(api_id, invoice_number)
```

#### `despatch_references` - İrsaliye Referansları
```sql
CREATE TABLE despatch_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    irsaliye_no TEXT NOT NULL,              -- Description'dan regex ile çıkarılan
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
)
```

**Özellikler:**
- ✅ Banka bilgileri otomatik temizlenir
- ✅ İrsaliye numaraları regex ile çıkarılır (IRS12345, A-14740, etc)
- ✅ Ham JSON verisi yedeklenir
- ✅ Giden/gelen fatura ayrımı (invoice_type)

---

## 4️⃣ **birlesik.db** (Merkezi Birleşik Veritabanı)

### Tablolar:

#### `invoices` - Birleşik Fatura Tablosu
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_kodu TEXT NOT NULL,              -- ✨ 'A', 'F', veya 'API'
    source_file TEXT NOT NULL,
    parse_date TEXT NOT NULL,
    invoice_id TEXT,
    uuid TEXT,
    invoice_number TEXT,
    issue_date TEXT,
    total_amount REAL,
    currency TEXT,
    taxable_amount REAL,
    tax_amount REAL,
    supplier_name TEXT,
    supplier_vkn TEXT,
    customer_name TEXT,
    customer_vkn TEXT,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Index:**
```sql
CREATE UNIQUE INDEX idx_unique_invoice 
ON invoices(firma_kodu, invoice_number)
```

#### `attachments`, `invoice_lines`, `despatch_documents`
**XML kaynaklı (A ve F) veriler için dolu, API için boş.**

**Index:**
```sql
CREATE UNIQUE INDEX idx_unique_invoice_line 
ON invoice_lines(invoice_id, line_id)
```

---

## 🔄 Veri Akışı

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  XML Files   │     │  XML Files   │     │  İşbaşı API  │
│  (AK GİPS)   │     │ (FULLBOARD)  │     │ (Giden+Gelen)│
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│akgips_parser │     │fullboard_    │     │api_data_     │
│    .py       │     │parser.py     │     │extractor.py  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ akgips.db    │     │ fullboard.db │     │   api.db     │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                     │
       └────────────────────┼─────────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ merge_databases  │
                  │       .py        │
                  └─────────┬────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   birlesik.db    │
                  │  (A + F + API)   │
                  └──────────────────┘
```

---

## 📊 Karşılaştırma Tablosu

| Özellik | akgips.db | fullboard.db | api.db | birlesik.db |
|---------|-----------|--------------|--------|-------------|
| **Kaynak** | XML | XML | API | Tümü |
| **Firma Kodu** | - | - | - | ✅ A/F/API |
| **Ana Fatura** | ✅ | ✅ | ✅ | ✅ |
| **Attachments** | ✅ | ✅ | ❌ | ✅ (A,F) |
| **Invoice Lines** | ✅ | ✅ | ❌ | ✅ (A,F) |
| **Despatch Docs** | ✅ | ✅ | ✅* | ✅ |
| **Raw JSON** | ❌ | ❌ | ✅ | ❌ |
| **Banka Temizleme** | ❌ | ❌ | ✅ | ✅ (API) |
| **İrsaliye Regex** | ❌ | ❌ | ✅ | ❌ |

*API'de irsaliye description'dan regex ile çıkarılır

---

## 🏷️ Firma Kodları ve Prefix'ler

| Kod | Firma | İrsaliye Prefix | Örnek |
|-----|-------|----------------|-------|
| **A** | AK GİPS | A-##### | A-14740 |
| **F** | FULLBOARD | F-##### | F-07904 |
| **API** | İşbaşı API | API-##### | API-IRS12345 |

---

## 🛠️ Kullanım Komutları

### 1. Veritabanı Oluşturma

```bash
# AK GİPS XML'lerini parse et
python3 src/parsers/akgips_parser.py

# FULLBOARD XML'lerini parse et
python3 src/parsers/fullboard_parser.py

# API verilerini çek
python3 src/api/api_data_extractor.py
```

### 2. Birleştirme

```bash
# Tüm veritabanlarını birleştir
python3 src/database/merge_databases.py
```

### 3. Excel Export

```bash
# AK GİPS export
python3 src/exporters/akgips_exporter.py

# FULLBOARD export
python3 src/exporters/fullboard_exporter.py

# API export
python3 src/exporters/api_exporter.py

# Birleşik export
python3 src/exporters/birlesik_exporter.py
```

---

## 📁 Veritabanı Dosya Konumları

```
data/
  db/
    ├── akgips.db       # 3 fatura, 9 satır
    ├── fullboard.db    # 3 fatura, 9 satır
    ├── api.db          # ✨ YENİ: API verileri
    └── birlesik.db     # Tümü (A + F + API)
```

---

## 🔍 Veritabanı İstatistikleri

Her veritabanının istatistiklerini görüntülemek için:

```bash
# SQLite ile
sqlite3 data/db/akgips.db "SELECT COUNT(*) FROM invoices;"

# Python ile (API örneği)
python3 -c "from src.api.api_database import APIDatabase; APIDatabase().print_statistics()"

# Veya view_db.py aracını kullan
python3 tools/view_db.py
```

---

## 🎯 Sonuç

✅ **4 veritabanı yapısı tamamlandı:**
1. akgips.db (XML kaynaklı)
2. fullboard.db (XML kaynaklı)
3. api.db (API kaynaklı) ✨ YENİ
4. birlesik.db (Merkezi)

✅ **Tutarlı mimari:**
- Her kaynak önce kendi DB'sine kaydedilir
- Sonra merge_databases.py ile birleştirilir
- Her firma kodu ile ayırt edilir (A/F/API)

✅ **Özel özellikler:**
- API: Banka bilgisi temizleme
- API: İrsaliye regex çıkarma
- API: Raw JSON yedekleme
- Birlesik: Firma kodu ile ayrım

📄 **Detaylı dokümantasyon:**
- `API_DATABASE_STRUCTURE.md` - API yapısı detayları
- `README.md` - Genel kullanım
- `HIZLI_BASLANGIC.md` - Hızlı başlangıç

