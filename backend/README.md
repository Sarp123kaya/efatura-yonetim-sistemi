# Backend Agents - Stateful Postgres Ingestion

Bu dizin, İşbaşı API'sinden gelen ve giden faturaları Postgres veritabanına stateful (durum takipli) olarak aktaran agent'ları içerir.

## 📋 Özellikler

- **Stateful Ingestion**: Her agent son işlediği `issue_date`'i takip eder
- **Incremental Updates**: Sadece yeni/değişen faturalar işlenir
- **Change Detection**: Row hash kullanılarak değişiklikler tespit edilir
- **Normalizasyon**: İrsaliye kodları otomatik normalize edilir (IRS-XXXXX formatı)
- **Upsert**: Yoksa insert, varsa (hash değiştiyse) update
- **Duplicate Prevention**: Primary key constraints ile duplicate önlenir

## 🏗️ Mimari

```
backend/
├── core/
│   ├── config.py          # .env'den konfigürasyon okur
│   ├── db.py              # psycopg2 database helper'ları
│   ├── agent_state.py     # Agent state yönetimi
│   └── normalize.py       # İrsaliye kodu normalizasyonu
└── agents/
    ├── incoming_agent.py  # Gelen fatura agent'ı
    └── outgoing_agent.py  # Giden fatura agent'ı
```

## 📊 Veritabanı Şeması

### `agent_state` Tablosu
Agent'ların son işleme durumunu takip eder:
- `agent_name` (PK): Agent adı
- `last_issue_date`: Son işlenen fatura tarihi
- `last_run_at`: Son çalışma zamanı

### `incoming_invoices` Tablosu
Gelen faturalar (myInvoicesList endpoint):
- `invoice_id` (PK): Fatura ID
- `uuid`: Fatura UUID (ETTN)
- `issue_date`: Fatura tarihi
- `supplier`: Tedarikçi
- `amount`: Tutar
- `despatch_ids`: İrsaliye ID'leri (JSONB, normalize edilmiş)
- `raw_json`: Ham API yanıtı (JSONB)
- `row_hash`: Değişiklik tespiti için hash
- `changed`: Güncelleme durumu

### `outgoing_invoices` Tablosu
Giden faturalar (invoices endpoint, PURCHASE_INVOICE hariç):
- `invoice_no` (PK): Fatura numarası
- `issue_date`: Fatura tarihi
- `firm_name`: Firma adı
- `total_tl`: Toplam tutar
- `description`: Açıklama
- `irsaliye_codes`: Description'dan çıkarılan irsaliye kodları (JSONB)
- `raw_json`: Ham API yanıtı (JSONB)
- `row_hash`: Değişiklik tespiti için hash
- `changed`: Güncelleme durumu

## 🚀 Kurulum

### 1. PostgreSQL Kurulumu

```bash
# PostgreSQL kur (macOS)
brew install postgresql@15
brew services start postgresql@15

# Database oluştur
createdb invoices

# Veya docker ile:
docker run -d \
  --name invoices-postgres \
  -e POSTGRES_DB=invoices \
  -e POSTGRES_USER=invoices_user \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  postgres:15
```

### 2. Schema Migrate Et

```bash
# Schema ve migration'ları uygula
psql invoices < sql/stateful_ingestion_schema_v2.sql
psql invoices < sql/migration_v2.2_despatch_improvements.sql
psql invoices < sql/migration_irsaliye_override.sql
psql invoices < sql/migration_incoming_xml_cache.sql

# Veya docker ile:
docker exec -i invoices-postgres psql -U invoices_user -d invoices < sql/stateful_ingestion_schema_v2.sql
docker exec -i invoices-postgres psql -U invoices_user -d invoices < sql/migration_v2.2_despatch_improvements.sql
docker exec -i invoices-postgres psql -U invoices_user -d invoices < sql/migration_irsaliye_override.sql
docker exec -i invoices-postgres psql -U invoices_user -d invoices < sql/migration_incoming_xml_cache.sql
```

### 3. Python Paketlerini Kur

```bash
pip install -r requirements.txt
```

### 4. .env Dosyasını Yapılandır

```bash
cp env.example .env
nano .env
```

`.env` içeriği:
```bash
# İşbaşı API Credentials
ISBASI_API_KEY=your_api_key_here
ISBASI_USERNAME=your.email@example.com

# PostgreSQL Connection
DB_URL=postgresql://invoices_user:your_password@localhost:5432/invoices
```

## 🎯 Kullanım

### Gelen Fatura Agent'ı

```bash
# Agent'ı çalıştır
python backend/agents/incoming_agent.py
```

**Ne Yapar:**
1. `agent_state`'den son `last_issue_date`'i okur (ilk çalışmada 2026-01-01)
2. API'den son tarihten sonraki gelen faturaları çeker
3. Her fatura için:
   - İrsaliye ID'lerini normalize eder (IRS-XXXXX)
   - Row hash hesaplar
   - Upsert yapar (insert veya update)
4. Max `issue_date`'i `agent_state`'e yazar

**Çıktı Örneği:**
```
🚀 INCOMING INVOICE AGENT STARTING
============================================================
🔌 Testing database connection...
✅ Database connection successful
📅 Fetching invoices from 2026-01-01 to 2026-02-10
🔐 Logging in to Isbasi API...
✅ API girişi başarılı!
📥 Fetching incoming invoices from API...
✅ Fetched 156 invoices from API
📊 Processing 156 new/updated invoices (after 2026-01-01)
💾 Updating agent_state with max issue_date: 2026-02-10 14:30:00
============================================================
📊 INCOMING INVOICE AGENT RESULTS
============================================================
✅ Inserted: 150
🔄 Updated: 6
⚪ Unchanged: 0
📅 Max issue_date: 2026-02-10
============================================================
```

### Giden Fatura Agent'ı

```bash
# Agent'ı çalıştır
python backend/agents/outgoing_agent.py
```

**Ne Yapar:**
1. `agent_state`'den son `last_issue_date`'i okur
2. API'den son tarihten sonraki giden faturaları çeker (PURCHASE_INVOICE hariç)
3. Her fatura için:
   - Description'dan irsaliye kodlarını extract eder (A-09170, F/14740 vb.)
   - Kodları normalize eder (IRS-09170, IRS-14740)
   - Row hash hesaplar
   - Upsert yapar
4. Max `issue_date`'i `agent_state`'e yazar

## 🔄 İrsaliye Kodu Normalizasyonu

### Gelen Faturalar (Incoming)
XML'den gelen format: `IRS2025000014740`
Normalized: `IRS-14740` (son 5 hane)

### Giden Faturalar (Outgoing)
Description'daki format: `A-09170`, `F / 14740`, `A-1234 / F-5678`
Regex: `([AF])\s*[-/]\s*(\d{4,5})`
Normalized: `IRS-09170`, `IRS-14740`, `IRS-01234`, `IRS-05678`

## 📅 Cron Job Kurulumu

Agent'ları günlük otomatik çalıştırmak için:

```bash
# crontab aç
crontab -e

# Her gün saat 02:00'de çalıştır
0 2 * * * cd /path/to/project && /path/to/venv/bin/python backend/agents/incoming_agent.py >> /tmp/incoming_agent.log 2>&1
0 3 * * * cd /path/to/project && /path/to/venv/bin/python backend/agents/outgoing_agent.py >> /tmp/outgoing_agent.log 2>&1
```

## 🐛 Debugging

### Database Connection Test

```python
from backend.core.db import db

# Test connection
if db.test_connection():
    print("✅ Connected!")
else:
    print("❌ Connection failed")
```

### Agent State Kontrolü

```python
from backend.core.agent_state import get_state

# Son işleme tarihini görüntüle
last_date = get_state('incoming_agent')
print(f"Last processed: {last_date}")
```

### Manuel Tarih Değiştirme

```python
from backend.core.agent_state import set_state
from datetime import datetime

# State'i sıfırla
set_state('incoming_agent', datetime(2026, 1, 1))
```

## 🔧 Mevcut Extractor'larla İlişki

**Agent'lar mevcut extractor'ları BOZMAZ:**

- `src/api/api_incoming_invoices_extractor.py` - Hala çalışır, Excel yazar
- `src/api/api_data_extractor.py` - Hala çalışır, Excel ve SQLite yazar

**Agent'lar sadece:**
- Aynı extractor sınıflarını **import** eder
- Onların `fetch_*` metodlarını çağırır
- Excel/SQLite yazma kısımlarını ÇAĞIRMAZ
- Sadece Postgres'e yazar

## ⚠️ Önemli Notlar

1. **İlk Çalışma**: Agent'lar ilk çalışmada `2026-01-01`'den başlar (varsayılan)
2. **API Rate Limiting**: Her XML fetch arasında 300ms delay var
3. **Hash Değişiklikleri**: Raw JSON değişirse `changed=TRUE` olur
4. **Duplicate Handling**: Primary key ile duplicate engellenir
5. **Timezone**: Tüm tarihler UTC'de saklanır

## 📈 Performans

- **Incoming Agent**: ~150 fatura/dakika (XML fetch ile)
- **Outgoing Agent**: ~500 fatura/dakika (XML yok)
- **Memory**: ~100-200 MB
- **Database**: Batch insert kullanır (hızlı)
- **Batch Size**: 100 rows (configurable via BATCH_SIZE)
- **Transaction**: Per-batch (ACID compliance - v2.0.1)

### Transaction Per Batch (v2.0.1)

Her batch için ayrı transaction kullanılır:
```
Batch 1: BEGIN -> UPSERT 100 rows -> COMMIT ✅
Batch 2: BEGIN -> UPSERT 100 rows -> COMMIT ✅
Batch 3: BEGIN -> UPSERT 100 rows -> ROLLBACK ❌ (error)

Sonuç: 200 rows başarıyla kaydedildi, 100 rows failed
```

**Avantajlar:**
- ✅ Yarım veri kalmaz (ACID compliance)
- ✅ Partial success mümkün (Batch 1-2 başarılı, 3 fail)
- ✅ Production-safe data integrity

**Detaylar:** `../TRANSACTION_PER_BATCH.md`

## 🧪 Test

```bash
# Test modunda çalıştır (dry run)
python backend/agents/incoming_agent.py --dry-run

# Belirli tarih aralığı
python backend/agents/incoming_agent.py --start-date 2026-01-15 --end-date 2026-01-20
```

## 🆘 Sorun Giderme

### "Database connection failed"
- `.env`'de `DB_URL` doğru mu?
- PostgreSQL çalışıyor mu? (`pg_isready`)
- Kullanıcı/şifre doğru mu?

### "API login failed"
- `.env`'de `ISBASI_API_KEY` ve `ISBASI_USERNAME` doğru mu?
- API erişiminiz var mı?

### "No invoices returned"
- Tarih aralığında fatura var mı?
- API filtreleri doğru çalışıyor mu?

### "Duplicate key violation"
- Normal! Aynı faturayı iki kez çekmeye çalışıyorsunuz
- Agent state güncel mi kontrol edin

## 📝 Changelog

- **v1.0.0** (2026-02-10): İlk versiyon
  - Stateful ingestion
  - Change detection
  - İrsaliye normalizasyonu
  - Upsert logic
