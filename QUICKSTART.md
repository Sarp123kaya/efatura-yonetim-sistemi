# 🚀 Stateful Postgres Ingestion - Quick Start

## ✅ Installation Verification

Sistemi doğrulamak için:

```bash
python3 scripts/verify_installation.py
```

**Beklenen çıktı:** Tüm testler ✅ PASS (Database uyarısı normal)

---

## 📦 1. Prerequisites

### PostgreSQL Kurulumu

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Docker:**
```bash
docker run -d \
  --name invoices-postgres \
  -e POSTGRES_DB=invoices \
  -e POSTGRES_USER=invoices_user \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  postgres:15
```

**Database Oluşturma:**
```bash
# Local PostgreSQL
createdb invoices

# Docker
docker exec invoices-postgres createdb -U invoices_user invoices
```

---

## ⚙️ 2. Configuration

### .env Dosyasını Yapılandır

```bash
# .env dosyası yoksa oluştur
cp env.example .env

# .env dosyasını düzenle
nano .env
```

**Gerekli ayarlar:**

```bash
# API Credentials
ISBASI_API_KEY=your_api_key_here
ISBASI_USERNAME=your.email@example.com

# Database URL
DB_URL=postgresql://invoices_user:your_password@localhost:5432/invoices

# Opsiyonel
ISBASI_BASE_URL=https://mw-jplatform.isbasi.com
ISBASI_VERIFY_SSL=true
```

**Not:** `DB_URL` formatı:
```
postgresql://username:password@host:port/database
```

---

## 🗄️ 3. Database Setup

### Otomatik Setup (Önerilen)

```bash
./scripts/setup_postgres.sh
```

**Script ne yapar:**
- ✅ .env kontrolü
- ✅ Database bağlantı testi
- ✅ Schema migration
- ✅ Tablo doğrulaması
- ✅ Agent state initialization

### Manuel Setup

```bash
# Schema'yı uygula
psql "postgresql://user:password@localhost:5432/invoices" < sql/stateful_ingestion_schema.sql

# Doğrulama
psql "postgresql://user:password@localhost:5432/invoices" -c "\dt"
```

**Beklenen tablolar:**
- `agent_state`
- `incoming_invoices`
- `outgoing_invoices`

---

## 🎯 4. İlk Çalıştırma

### Gelen Faturalar (Incoming Invoices)

```bash
python backend/agents/incoming_agent.py
```

**Ne yapar:**
1. Agent state'den son tarih alır (ilk: 2026-01-01)
2. API'ye login olur
3. 2026-01-01'den bugüne kadar gelen faturaları çeker
4. İrsaliye bilgilerini normalize eder
5. Postgres'e upsert yapar
6. Agent state'i günceller

**Beklenen çıktı:**
```
🚀 INCOMING INVOICE AGENT STARTING
============================================================
🔐 Şifre: [güvenli giriş]
✅ API girişi başarılı!
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

### Giden Faturalar (Outgoing Invoices)

```bash
python backend/agents/outgoing_agent.py
```

**Ne yapar:**
1. Agent state'den son tarih alır
2. API'ye login olur
3. Giden faturaları çeker (PURCHASE_INVOICE hariç)
4. Description'dan irsaliye kodlarını extract eder
5. Postgres'e upsert yapar
6. Agent state'i günceller

**Beklenen çıktı:**
```
🚀 OUTGOING INVOICE AGENT STARTING
============================================================
✅ Fetched 2095 invoices from API
============================================================
📊 OUTGOING INVOICE AGENT RESULTS
============================================================
✅ Inserted: 2080
🔄 Updated: 15
⚪ Unchanged: 0
📅 Max issue_date: 2026-02-10
============================================================
```

---

## 🔄 5. İkinci Çalıştırma (Incremental)

Agent'ları tekrar çalıştırdığınızda:

```bash
python backend/agents/incoming_agent.py
python backend/agents/outgoing_agent.py
```

**Fark:**
- ✅ Sadece son `last_issue_date`'den sonraki faturaları çeker
- ✅ Çok daha hızlı (yeni kayıtlar yoksa saniyeler içinde biter)
- ✅ Hash değişenleri günceller (changed=TRUE)

**Örnek çıktı (değişiklik yoksa):**
```
📅 Fetching invoices from 2026-02-10 to 2026-02-10
✅ Fetched 0 invoices from API
============================================================
📊 RESULTS
============================================================
✅ Inserted: 0
🔄 Updated: 0
⚪ Unchanged: 0
============================================================
```

---

## 📊 6. Veritabanı Kontrolü

### Agent State'i Görüntüle

```sql
SELECT agent_name, last_issue_date, last_run_at 
FROM agent_state 
ORDER BY agent_name;
```

**Beklenen:**
```
    agent_name    | last_issue_date |      last_run_at        
------------------+-----------------+-------------------------
 incoming_agent   | 2026-02-10      | 2026-02-10 00:30:00
 outgoing_agent   | 2026-02-10      | 2026-02-10 00:35:00
```

### Fatura Sayıları

```sql
-- Gelen faturalar
SELECT COUNT(*), MIN(issue_date), MAX(issue_date) 
FROM incoming_invoices;

-- Giden faturalar
SELECT COUNT(*), MIN(issue_date), MAX(issue_date) 
FROM outgoing_invoices;
```

### Son Eklenen Faturalar

```sql
-- Gelen faturalar (son 10)
SELECT invoice_id, issue_date, supplier, amount 
FROM incoming_invoices 
ORDER BY created_at DESC 
LIMIT 10;

-- Giden faturalar (son 10)
SELECT invoice_no, issue_date, firm_name, total_tl 
FROM outgoing_invoices 
ORDER BY created_at DESC 
LIMIT 10;
```

### Değişen Faturalar

```sql
-- Gelen faturalarda değişenler
SELECT invoice_id, supplier, updated_at 
FROM incoming_invoices 
WHERE changed = TRUE;

-- Giden faturalarda değişenler
SELECT invoice_no, firm_name, updated_at 
FROM outgoing_invoices 
WHERE changed = TRUE;
```

### İrsaliye İstatistikleri

```sql
-- Gelen faturalarda irsaliyeli kayıt sayısı
SELECT COUNT(*) 
FROM incoming_invoices 
WHERE jsonb_array_length(despatch_ids) > 0;

-- Giden faturalarda irsaliyeli kayıt sayısı
SELECT COUNT(*) 
FROM outgoing_invoices 
WHERE jsonb_array_length(irsaliye_codes) > 0;
```

---

## 🔧 7. Troubleshooting

### "Database connection failed"

**Çözüm:**
```bash
# PostgreSQL çalışıyor mu?
pg_isready

# Database var mı?
psql postgres -c "\l" | grep invoices

# Bağlantı test et
psql "postgresql://user:password@localhost:5432/invoices" -c "SELECT 1"
```

### "API login failed"

**Çözüm:**
1. `.env`'de credentials doğru mu?
2. API erişimi var mı?
3. Şifre doğru girildi mi?

### "No invoices returned"

**Çözüm:**
1. Tarih aralığında fatura var mı kontrol et
2. API filtreleri çalışıyor mu?
3. İlk çalıştırmada 2026-01-01'den başlar

### Agent State Reset (Yeniden başlatma)

```python
from backend.core.agent_state import set_state
from datetime import datetime

# 2026-01-01'den yeniden başlat
set_state('incoming_agent', datetime(2026, 1, 1))
set_state('outgoing_agent', datetime(2026, 1, 1))
```

Veya SQL ile:
```sql
UPDATE agent_state 
SET last_issue_date = '2026-01-01 00:00:00' 
WHERE agent_name IN ('incoming_agent', 'outgoing_agent');
```

---

## ⏰ 8. Cron Job Kurulumu (Otomatik Çalıştırma)

```bash
# crontab düzenle
crontab -e
```

**Örnek cron jobs:**

```cron
# Her gün saat 02:00'de gelen faturalar
0 2 * * * cd /path/to/project && /path/to/venv/bin/python backend/agents/incoming_agent.py >> /tmp/incoming_agent.log 2>&1

# Her gün saat 03:00'de giden faturalar
0 3 * * * cd /path/to/project && /path/to/venv/bin/python backend/agents/outgoing_agent.py >> /tmp/outgoing_agent.log 2>&1

# Her 6 saatte bir
0 */6 * * * cd /path/to/project && /path/to/venv/bin/python backend/agents/incoming_agent.py >> /tmp/incoming_agent.log 2>&1
```

---

## 📈 9. Monitoring

### Log Kontrolü

```bash
# Cron job logları
tail -f /tmp/incoming_agent.log
tail -f /outgoing_agent.log
```

### Agent Durumu

```sql
-- Agent'ların son çalışma zamanı
SELECT 
    agent_name,
    last_issue_date,
    last_run_at,
    NOW() - last_run_at AS time_since_last_run
FROM agent_state;
```

### Performans

```sql
-- Gelen faturalar - aylık dağılım
SELECT 
    DATE_TRUNC('month', issue_date) AS month,
    COUNT(*) AS invoice_count,
    SUM(amount) AS total_amount
FROM incoming_invoices
GROUP BY month
ORDER BY month DESC;

-- Giden faturalar - aylık dağılım
SELECT 
    DATE_TRUNC('month', issue_date) AS month,
    COUNT(*) AS invoice_count,
    SUM(total_tl) AS total_amount
FROM outgoing_invoices
GROUP BY month
ORDER BY month DESC;
```

---

## 📚 10. Daha Fazla Bilgi

- **Detaylı dokümantasyon:** `backend/README.md`
- **Implementation summary:** `STATEFUL_INGESTION_SUMMARY.md`
- **Main README:** `README.md`

---

## ✅ Checklist

İlk setup için:
- [ ] PostgreSQL kuruldu
- [ ] Database oluşturuldu (`createdb invoices`)
- [ ] `.env` dosyası yapılandırıldı
- [ ] Schema migrate edildi (`./scripts/setup_postgres.sh`)
- [ ] Verification testi geçti (`python3 scripts/verify_installation.py`)
- [ ] Incoming agent çalıştırıldı
- [ ] Outgoing agent çalıştırıldı
- [ ] Database'de faturalar görüldü
- [ ] Cron job kuruldu (opsiyonel)

---

**İyi çalışmalar! 🚀**
