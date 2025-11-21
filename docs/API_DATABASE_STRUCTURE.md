# API Veritabanı Yapısı

## 📋 Genel Bakış

API verileri artık **ayrı bir veritabanında** (`api.db`) saklanıyor ve diğer veritabanlarıyla (AK GİPS ve FULLBOARD) tutarlı bir yapıda birleştiriliyor.

## 🗄️ Veritabanı Yapısı

### 1. **api.db** - API Veritabanı

API'den çekilen fatura verileri için özel veritabanı.

#### Tablolar:

##### `invoices` - Ana Fatura Tablosu
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id TEXT NOT NULL UNIQUE,           -- API'den gelen orijinal ID
    source TEXT DEFAULT 'API',              -- Kaynak (API)
    parse_date TEXT NOT NULL,               -- Parse tarihi
    invoice_number TEXT,                    -- Fatura numarası
    invoice_type TEXT,                      -- SALES_INVOICE veya PURCHASE_INVOICE
    issue_date TEXT,                        -- Fatura tarihi
    total_amount REAL,                      -- Toplam tutar
    currency TEXT DEFAULT 'TRY',            -- Para birimi
    taxable_amount REAL,                    -- Vergi matrahı
    firm_name TEXT,                         -- Firma adı
    firm_vkn TEXT,                          -- Firma VKN
    description TEXT,                       -- Açıklama (banka bilgileri temizlenmiş)
    raw_json TEXT,                          -- Ham JSON verisi (yedek)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Index:**
```sql
CREATE UNIQUE INDEX idx_unique_api_invoice 
ON invoices(api_id, invoice_number)
```

##### `despatch_references` - İrsaliye Referansları
```sql
CREATE TABLE despatch_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    irsaliye_no TEXT NOT NULL,              -- Description'dan çıkarılan irsaliye no
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
)
```

## 🔄 Veri Akışı

```
┌─────────────────────┐
│   İşbaşı API        │
│  (Giden + Gelen)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  api_data_extractor │ ← API'den veri çeker
│       .py           │
└──────────┬──────────┘
           │
           ├──────────────────┐
           │                  │
           ▼                  ▼
    ┌───────────┐      ┌──────────┐
    │  api.db   │      │ Excel    │
    │           │      │ Çıktıları│
    └─────┬─────┘      └──────────┘
          │
          │
          ▼
    ┌────────────────┐
    │ merge_databases│ ← Tüm DB'leri birleştirir
    │      .py       │
    └────────┬───────┘
             │
             ▼
    ┌─────────────────┐
    │   birlesik.db   │ ← Merkezi veritabanı
    │                 │   (A, F, API)
    └─────────────────┘
```

## 📊 Veritabanı Karşılaştırması

| Özellik | akgips.db | fullboard.db | api.db | birlesik.db |
|---------|-----------|--------------|--------|-------------|
| **Kaynak** | XML | XML | API | Tümü |
| **Attachments** | ✅ | ✅ | ❌ | ✅ |
| **Invoice Lines** | ✅ | ✅ | ❌ | ✅ |
| **Despatch Docs** | ✅ | ✅ | ✅* | ✅ |
| **Raw JSON** | ❌ | ❌ | ✅ | ❌ |
| **Firma Kodu** | ❌ | ❌ | ❌ | ✅ (A/F/API) |

*API'de irsaliye description'dan regex ile çıkarılır

## 🛠️ Kullanım

### 1. API Verilerini Çekme
```bash
python3 src/api/api_data_extractor.py
```

**Yapılan İşlemler:**
- İşbaşı API'sine güvenli giriş
- Giden ve gelen faturaları sayfalama ile çekme
- Banka bilgilerini temizleme
- İrsaliye numaralarını otomatik çıkarma
- api.db'ye kaydetme
- Excel export (8 sütun)

### 2. Veritabanlarını Birleştirme
```bash
python3 src/database/merge_databases.py
```

**Yapılan İşlemler:**
- akgips.db → birlesik.db (Firma kodu: A)
- fullboard.db → birlesik.db (Firma kodu: F)
- api.db → birlesik.db (Firma kodu: API)
- İrsaliye prefix'lerini düzenleme

### 3. Excel Export (Opsiyonel)
```bash
python3 src/exporters/api_exporter.py
```

**Çıktı:** `kayıtlar/API_Faturalar_YYYYMMDD_HHMMSS.xlsx`

**Sütunlar (8 adet):**
1. `id` - API ID
2. `date` - Tarih (gün.ay.yıl)
3. `invoiceNumber` - Fatura numarası
4. `totalTL` - Toplam tutar
5. `taxableAmount` - Vergi matrahı
6. `firmName` - Firma adı
7. `description` - Açıklama (temizlenmiş)
8. `irsaliyeNo` - İrsaliye numaraları (otomatik çıkarılmış)

## 🔍 İrsaliye Çıkarma

API'de irsaliye numaraları description alanından **regex** ile otomatik çıkarılır:

**Desteklenen Formatlar:**
- `IRS12345` → `IRS12345`
- `İRS12345` → `IRS12345`
- `A-14740` → `A-14740`
- `F-07904` → `F-07904`

## 🧹 Banka Bilgisi Temizleme

Description alanından banka bilgileri otomatik olarak temizlenir:

**Örnek:**
```
Öncesi: "Fatura açıklaması Banka Bilgileri\nGARANTİBANK - TR35..."
Sonrası: "Fatura açıklaması"
```

## 📁 Dosya Yapısı

```
data/
  db/
    ├── akgips.db       # XML (AK GİPS)
    ├── fullboard.db    # XML (FULLBOARD)
    ├── api.db          # ✨ YENİ: API verileri
    └── birlesik.db     # Birleşik (A + F + API)

src/
  api/
    ├── api_data_extractor.py   # API veri çekme
    └── api_database.py         # ✨ YENİ: API DB modülü
  
  database/
    └── merge_databases.py      # ✨ GÜNCELLENDİ: API dahil
  
  exporters/
    ├── akgips_exporter.py
    ├── fullboard_exporter.py
    └── api_exporter.py         # ✨ YENİ: API export

kayıtlar/                       # Excel çıktıları
  ├── API_Faturalar_*.xlsx      # API export
  ├── efatura_birlesik.xlsx     # Birleşik export
  └── ...
```

## 🔐 Güvenlik

- API şifresi **asla** veritabanına kaydedilmez
- Güvenli giriş için `getpass` modülü kullanılır
- Ham JSON verisi `raw_json` alanında yedeklenir

## 📈 İstatistikler

API veritabanı istatistiklerini görüntülemek için:

```python
from src.api.api_database import APIDatabase

db = APIDatabase()
db.print_statistics()
```

**Çıktı:**
```
============================================================
API VERİTABANI İSTATİSTİKLERİ
============================================================
📊 Toplam Fatura: 125
   🟢 Giden: 89
   🔴 Gelen: 36

💰 Toplam Tutar: 1,234,567.89 TRY
   🟢 Giden: 987,654.32 TRY
   🔴 Gelen: 246,913.57 TRY

📄 İrsaliye Referansları: 67
💾 Veritabanı: data/db/api.db
============================================================
```

## 🚀 Avantajlar

### ✅ Önceki Yapı (api.db yoktu)
- ❌ API verileri doğrudan birlesik.db'ye gidiyordu
- ❌ Tutarsız yapı (XML'ler ayrı DB, API direkt merge)
- ❌ Yeniden çekme zorluğu

### ✅ Yeni Yapı (api.db var)
- ✅ Tüm kaynaklar önce kendi DB'sine kaydedilir
- ✅ Tutarlı mimari (akgips.db, fullboard.db, api.db)
- ✅ Bağımsız export ve yedekleme
- ✅ Kolay yeniden birleştirme

## 🧪 Test

```bash
python3 test_api_database.py
```

Test scripti:
- Veritabanı oluşturma
- Test faturası ekleme
- İrsaliye çıkarma
- İstatistik gösterme
- Temizlik

## 📞 Destek

Sorular için proje dokümantasyonuna bakın:
- `README.md` - Genel kullanım
- `HIZLI_BASLANGIC.md` - Hızlı başlangıç
- `KULLANIM_AKISI.md` - Detaylı akış

