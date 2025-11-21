# 💰 Finansal Takip Sistemi - Backend Dokümantasyonu

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Kurulum](#kurulum)
3. [Veritabanı Yapısı](#veritabanı-yapısı)
4. [Modüller](#modüller)
5. [Kullanım Örnekleri](#kullanım-örnekleri)
6. [API Referansı](#api-referansı)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Genel Bakış

Bu sistem, e-fatura verilerinden finansal analiz ve takip yapmak için geliştirilmiştir:

### Ana Özellikler

✅ **İrsaliye Eşleştirme**: Alış ve satış faturalarını IRS numarasıyla eşleştirme  
✅ **Kar/Zarar Hesaplama**: Her eşleşme için kar marjı analizi  
✅ **Borç Takibi**: Fabrikalara olan borçları takip  
✅ **Alacak Takibi**: Müşterilerden olan alacakları takip  
✅ **Ödeme Yönetimi**: Ödeme kayıtları ve kısmi ödeme desteği  
✅ **Bilanço Hesaplama**: Anlık finansal durum raporu  
✅ **Snapshot Sistemi**: Zaman içinde trend analizi  
✅ **Yaşlandırma Raporu**: Vade geçmiş borç/alacak analizi  

### İş Akışı

```
1. XML/API Faturalar → Parse → Veritabanı
2. Migration → Yeni tablolar ve sütunlar ekle
3. IRS Matcher → Alış/Satış eşleştirme → Kar/Zarar hesapla
4. Payment Manager → Ödeme kayıtları
5. Debt Tracker → Borç/Alacak analizi
6. Balance Calculator → Finansal durum raporu
```

---

## 🚀 Kurulum

### Hızlı Kurulum (Otomatik)

```bash
python3 setup_financial_backend.py
```

Bu script otomatik olarak:
- ✅ Database migration yapar
- ✅ IRS eşleştirme çalıştırır
- ✅ Borç/Alacak analizi yapar
- ✅ İlk bilanço snapshot'ını oluşturur

### Manuel Kurulum

#### 1. Database Migration

```bash
python3 src/database/schema_migration.py
```

**Ne yapar:**
- Yeni tablolar oluşturur (irs_matching, payment_records, balance_snapshots, line_matching)
- invoices tablosuna yeni sütunlar ekler (invoice_type, payment_status, vb.)
- Performance için index'ler ekler
- Mevcut verilere invoice_type atar (A/F=PURCHASE, API=SALES)

**⚠️ Önemli:** Backup otomatik olarak alınır (`data/db/backups/`)

#### 2. IRS Eşleştirme

```bash
python3 src/financial/irs_matcher.py
```

**Ne yapar:**
- Alış faturalarındaki (AK GİPS, FULLBOARD) irsaliye numaralarını okur
- Satış faturalarındaki (API) description'lardan irsaliye numaralarını çıkarır
- Eşleşenleri bulur ve kar/zarar hesaplar
- Sonuçları `irs_matching` tablosuna kaydeder

---

## 🗂️ Veritabanı Yapısı

### Yeni Tablolar

#### 1. `irs_matching` (İrsaliye Eşleştirme)

```sql
CREATE TABLE irs_matching (
    id INTEGER PRIMARY KEY,
    irs_number TEXT,                 -- A-14740, F-07904
    purchase_invoice_id INTEGER,     -- Alış faturası ID
    sales_invoice_id INTEGER,        -- Satış faturası ID
    purchase_amount REAL,            -- Alış tutarı
    sales_amount REAL,               -- Satış tutarı
    profit_loss REAL,                -- Kar/Zarar
    profit_margin REAL,              -- Kar marjı %
    status TEXT,                     -- PROFITABLE, LOSS, BREAK_EVEN
    matched_date TEXT
);
```

#### 2. `payment_records` (Ödeme Kayıtları)

```sql
CREATE TABLE payment_records (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER,
    payment_date TEXT,
    amount REAL,
    payment_method TEXT,             -- BANK_TRANSFER, CASH, CHECK, vb.
    reference_number TEXT,           -- Dekont/referans no
    notes TEXT,
    created_at TEXT
);
```

#### 3. `balance_snapshots` (Bilanço Snapshot'ları)

```sql
CREATE TABLE balance_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date TEXT,
    total_purchases REAL,
    total_sales REAL,
    total_paid_to_suppliers REAL,
    total_received_from_customers REAL,
    outstanding_payables REAL,       -- Kalan borç
    outstanding_receivables REAL,    -- Kalan alacak
    net_balance REAL,                -- Net pozisyon
    total_profit REAL,
    created_at TEXT
);
```

#### 4. `line_matching` (Satır Bazında Eşleştirme)

```sql
CREATE TABLE line_matching (
    id INTEGER PRIMARY KEY,
    irs_matching_id INTEGER,
    purchase_line_id INTEGER,
    sales_line_id INTEGER,
    item_name TEXT,
    purchase_quantity REAL,
    sales_quantity REAL,
    unit_profit REAL
);
```

### Güncellenmiş Tablolar

#### `invoices` (Yeni Sütunlar)

```sql
ALTER TABLE invoices ADD COLUMN invoice_type TEXT;      -- PURCHASE veya SALES
ALTER TABLE invoices ADD COLUMN payment_status TEXT;    -- PAID, PARTIAL, UNPAID
ALTER TABLE invoices ADD COLUMN payment_due_date TEXT;  -- Vade tarihi
ALTER TABLE invoices ADD COLUMN paid_amount REAL;       -- Ödenen miktar
ALTER TABLE invoices ADD COLUMN remaining_amount REAL;  -- Kalan borç/alacak
```

---

## 📦 Modüller

### 1. IRS Matcher (`src/financial/irs_matcher.py`)

**Amaç:** İrsaliye numarası ile alış/satış eşleştirme ve kar/zarar hesaplama

```python
from src.financial.irs_matcher import IRSMatcher

matcher = IRSMatcher()
report = matcher.run_full_analysis()

print(f"Toplam Eşleşme: {report['total_matches']}")
print(f"Net Kar: {report['net_profit']:,.2f} TRY")
print(f"Ortalama Kar Marjı: {report['avg_profit_margin']:.2f}%")
```

**Önemli Fonksiyonlar:**

- `find_matches()`: Eşleşmeleri bul
- `save_matches_to_db()`: Veritabanına kaydet
- `generate_report()`: Rapor üret
- `normalize_irs_number()`: IRS numarasını normalize et
- `extract_irs_from_description()`: Description'dan IRS çıkar

**Desteklenen IRS Formatları:**

```python
"IRS NO: 14740"
"İrsaliye: A-14740"
"IRSALIYE: 14740"
"IRS:14740"
"14740, 14741, 14742"  # Çoklu
```

### 2. Payment Manager (`src/financial/payment_manager.py`)

**Amaç:** Ödeme kayıtları yönetimi

```python
from src.financial.payment_manager import PaymentManager

pm = PaymentManager()

# Ödeme ekle
pm.add_payment(
    invoice_id=123,
    amount=5000.00,
    payment_method='BANK_TRANSFER',
    reference_number='DEKONT-001',
    notes='İlk taksit'
)

# Fatura ödemelerini görüntüle
payments = pm.get_invoice_payments(invoice_id=123)

# Özet rapor
pm.print_payment_summary()
```

**Ödeme Yöntemleri:**

- `BANK_TRANSFER`: Banka havalesi
- `CASH`: Nakit
- `CHECK`: Çek
- `CREDIT_CARD`: Kredi kartı
- `PROMISSORY_NOTE`: Senet
- `OTHER`: Diğer

### 3. Debt Tracker (`src/financial/debt_tracker.py`)

**Amaç:** Borç ve alacak takibi

```python
from src.financial.debt_tracker import DebtTracker

dt = DebtTracker()

# Borçları getir (fabrikalara)
payables = dt.get_payables()  # veya dt.get_payables(firma_kodu='A')

# Alacakları getir (müşterilerden)
receivables = dt.get_receivables()

# Tam rapor
dt.print_full_report()
```

**Yaşlandırma (Aging) Kategorileri:**

- **0-30 gün**: Güncel
- **31-60 gün**: Vadesi yaklaşan
- **61-90 gün**: Vadesi geçen
- **90+ gün**: Çok eski

### 4. Balance Calculator (`src/financial/balance_calculator.py`)

**Amaç:** Finansal durum hesaplama ve snapshot

```python
from src.financial.balance_calculator import BalanceCalculator

bc = BalanceCalculator()

# Mevcut durumu hesapla
balance = bc.calculate_current_balance()

# Bilanço raporu
bc.print_balance_sheet(balance)

# Snapshot kaydet (zaman içinde trend için)
snapshot_id = bc.save_snapshot()

# Geçmiş trend
bc.print_historical_trend()
```

**Balance Sheet İçeriği:**

- **Aktif**: Alacaklar + Nakit
- **Pasif**: Borçlar
- **Özkaynak**: Kar + İşletme sermayesi
- **Net Pozisyon**: Alacaklar - Borçlar
- **Likidite Oranı**: Alacaklar ÷ Borçlar

---

## 💡 Kullanım Örnekleri

### Senaryo 1: Yeni Fatura Geldiğinde

```bash
# 1. XML'leri parse et (zaten mevcut)
python3 src/parsers/akgips_parser.py

# 2. Veritabanlarını birleştir
python3 src/database/merge_databases.py

# 3. IRS eşleştirme çalıştır
python3 src/financial/irs_matcher.py

# 4. Bilanço güncelle
python3 src/financial/balance_calculator.py
```

### Senaryo 2: Ödeme Aldığınızda

```python
from src.financial.payment_manager import PaymentManager

pm = PaymentManager()

# Ödeme ekle (müşteriden alınan)
pm.add_payment(
    invoice_id=456,  # Satış faturası ID'si
    amount=15000.00,
    payment_method='BANK_TRANSFER',
    reference_number='HAVALE-20250115'
)

# Otomatik olarak:
# - payment_records tablosuna kaydedilir
# - invoices.paid_amount güncellenir
# - invoices.remaining_amount güncellenir
# - invoices.payment_status güncellenir (UNPAID → PARTIAL → PAID)
```

### Senaryo 3: Aylık Finansal Rapor

```python
from src.financial.irs_matcher import IRSMatcher
from src.financial.debt_tracker import DebtTracker
from src.financial.balance_calculator import BalanceCalculator

# 1. Kar/Zarar Raporu
matcher = IRSMatcher()
profit_report = matcher.generate_report()
print(f"Bu Ay Net Kar: {profit_report['net_profit']:,.2f} TRY")

# 2. Borç/Alacak Durumu
dt = DebtTracker()
payables = dt.get_payables_summary()
receivables = dt.get_receivables_summary()
print(f"Borçlarımız: {payables['total_remaining']:,.2f} TRY")
print(f"Alacaklarımız: {receivables['total_remaining']:,.2f} TRY")

# 3. Bilanço Snapshot
bc = BalanceCalculator()
bc.save_snapshot()  # Aylık kayıt
```

### Senaryo 4: Vade Kontrolü

```python
from src.financial.debt_tracker import DebtTracker

dt = DebtTracker()
payables = dt.get_payables()

# 90 günden eski borçlar
old_debts = [p for p in payables if p['days_old'] > 90]

for debt in old_debts:
    print(f"⚠️  Fatura {debt['invoice_number']}")
    print(f"   Tutar: {debt['remaining_amount']:,.2f} TRY")
    print(f"   Gün: {debt['days_old']}")
    print(f"   Tedarikçi: {debt['supplier_name']}")
```

---

## 📚 API Referansı

### IRSMatcher

#### `find_matches() -> List[Dict]`
Alış ve satış faturalarında IRS eşleşmesi ara.

**Returns:**
```python
[
    {
        'irs_number': 'A-14740',
        'purchase_invoice_no': 'AKG2025000001',
        'purchase_amount': 10000.00,
        'sales_invoice_no': 'API2025000001',
        'sales_amount': 12000.00,
        'profit_loss': 2000.00,
        'profit_margin': 20.00,
        'status': 'PROFITABLE'
    },
    ...
]
```

#### `normalize_irs_number(irs_full: str) -> str`
İrsaliye numarasını normalize et.

**Examples:**
```python
normalize_irs_number("A-14740")           # → "14740"
normalize_irs_number("IRS2025000014740")  # → "14740"
normalize_irs_number("F-07904")           # → "7904"
```

### PaymentManager

#### `add_payment(...) -> int`
Yeni ödeme kaydı ekle.

**Parameters:**
- `invoice_id` (int): Fatura ID
- `amount` (float): Ödeme tutarı
- `payment_date` (str, optional): Tarih (YYYY-MM-DD)
- `payment_method` (str): Ödeme yöntemi
- `reference_number` (str, optional): Referans no
- `notes` (str, optional): Notlar

**Returns:** Oluşturulan ödeme ID'si

#### `get_invoice_payments(invoice_id: int) -> List[Dict]`
Faturaya ait tüm ödemeleri getir.

### DebtTracker

#### `get_payables(firma_kodu: str = None) -> List[Dict]`
Borçları getir.

**Parameters:**
- `firma_kodu` (str, optional): 'A', 'F' veya None (tümü)

**Returns:**
```python
[
    {
        'id': 123,
        'invoice_number': 'AKG2025000001',
        'firma_kodu': 'A',
        'supplier_name': 'AK GİPS',
        'total_amount': 10000.00,
        'paid_amount': 3000.00,
        'remaining_amount': 7000.00,
        'payment_status': 'PARTIAL',
        'days_old': 45
    },
    ...
]
```

#### `get_aging_buckets(debts: List[Dict]) -> Dict`
Yaşlandırma analizi.

**Returns:**
```python
{
    '0-30': {'count': 5, 'amount': 50000.00, 'items': [...]},
    '31-60': {'count': 2, 'amount': 20000.00, 'items': [...]},
    '61-90': {'count': 1, 'amount': 10000.00, 'items': [...]},
    '90+': {'count': 0, 'amount': 0.00, 'items': []}
}
```

### BalanceCalculator

#### `calculate_current_balance() -> Dict`
Mevcut finansal durumu hesapla.

**Returns:**
```python
{
    'total_purchases': 100000.00,
    'paid_to_suppliers': 60000.00,
    'outstanding_payables': 40000.00,
    'total_sales': 120000.00,
    'received_from_customers': 80000.00,
    'outstanding_receivables': 40000.00,
    'net_balance': 0.00,  # receivables - payables
    'cash_flow': 20000.00,  # received - paid
    'net_profit': 15000.00,
    'avg_profit_margin': 15.5
}
```

#### `save_snapshot() -> int`
Mevcut durumu snapshot olarak kaydet.

---

## 🔧 Troubleshooting

### Hata: "Migration başarısız"

**Neden:** Veritabanı kilitli veya bozuk

**Çözüm:**
```bash
# Backup'tan geri yükle
cp data/db/backups/birlesik_backup_*.db data/db/birlesik.db

# Migration'ı tekrar çalıştır
python3 src/database/schema_migration.py
```

### Hata: "IRS eşleşmesi bulunamadı"

**Neden:** Description alanında IRS numarası yok veya format desteklenmiyor

**Çözüm:**
1. Satış faturalarının description alanını kontrol et:
```python
import sqlite3
conn = sqlite3.connect('data/db/birlesik.db')
cursor = conn.cursor()
cursor.execute("SELECT description FROM invoices WHERE invoice_type='SALES' LIMIT 10")
for row in cursor.fetchall():
    print(row[0])
```

2. Format eklemek için `irs_matcher.py` içindeki `extract_irs_from_description()` fonksiyonuna pattern ekle

### Hata: "Duplicate payment"

**Neden:** Aynı ödeme iki kez eklendi

**Çözüm:**
```python
from src.financial.payment_manager import PaymentManager
pm = PaymentManager()
pm.delete_payment(payment_id=123)  # Yanlış kaydı sil
```

---

## 📊 Raporlama Best Practices

### Günlük İşlemler

```bash
# Her gün sonunda
python3 src/financial/irs_matcher.py
```

### Haftalık Raporlar

```bash
# Haftanın sonunda
python3 src/financial/debt_tracker.py > reports/weekly_debt_$(date +%Y%m%d).txt
```

### Aylık Kapanış

```bash
# Ay sonunda
python3 src/financial/balance_calculator.py  # Snapshot kaydet
python3 src/financial/irs_matcher.py          # Kar/Zarar
```

---

## 🚀 Sonraki Adımlar (Frontend)

Backend hazır olduğuna göre, frontend için şunlar yapılacak:

1. ✅ **Dashboard Güncelleme**
   - Kar/Zarar grafikleri
   - Borç/Alacak KPI'ları
   - İrsaliye eşleştirme tablosu

2. ✅ **Raporlama Sayfası**
   - Excel export (finansal sütunlarla)
   - PDF raporlar
   - Grafik ve chartlar

3. ✅ **Ödeme Yönetimi UI**
   - Ödeme ekle/sil formu
   - Fatura ödeme geçmişi
   - Toplu ödeme kayıt

4. ✅ **Uyarı Sistemi**
   - Vade uyarıları
   - Düşük likidite uyarısı
   - Email/SMS entegrasyonu

---

**Versiyon:** 1.0.0  
**Son Güncelleme:** {{ datetime.now().strftime('%Y-%m-%d') }}  
**Geliştirici:** E-Fatura Yönetim Sistemi

