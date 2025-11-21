# 🚀 Finansal Sistem - Hızlı Referans

## ⚡ En Çok Kullanılan Komutlar

### İlk Kurulum (Bir kez)
```bash
python3 setup_financial_backend.py
```

### Günlük İşlemler

#### Yeni Faturalar Eklendiğinde
```bash
# 1. XML parse
python3 src/parsers/akgips_parser.py
python3 src/parsers/fullboard_parser.py

# 2. Birleştir
python3 src/database/merge_databases.py

# 3. Eşleştir
python3 src/financial/irs_matcher.py
```

#### Raporlar
```bash
# Kar/Zarar
python3 src/financial/irs_matcher.py

# Borç/Alacak
python3 src/financial/debt_tracker.py

# Bilanço
python3 src/financial/balance_calculator.py
```

---

## 💳 Ödeme İşlemleri (Python)

```python
from src.financial.payment_manager import PaymentManager
pm = PaymentManager()

# Ödeme ekle
pm.add_payment(
    invoice_id=123,
    amount=5000.00,
    payment_method='BANK_TRANSFER'
)

# Fatura ödemelerini gör
payments = pm.get_invoice_payments(invoice_id=123)

# Özet
pm.print_payment_summary()
```

---

## 📊 Veritabanı Sorguları

```bash
# SQLite'a bağlan
sqlite3 data/db/birlesik.db

# Faturalar
SELECT * FROM invoices LIMIT 10;

# Eşleşmeler
SELECT * FROM irs_matching;

# Ödemeler
SELECT * FROM payment_records;

# Snapshot'lar
SELECT * FROM balance_snapshots;

# Çıkış
.exit
```

---

## 🔍 Hızlı Kontroller

### Toplam Kar/Zarar
```bash
python3 -c "from src.financial.irs_matcher import IRSMatcher; m=IRSMatcher(); r=m.generate_report(); print(f'Net Kar: {r[\"net_profit\"]:,.2f} TRY')"
```

### Toplam Borç
```bash
python3 -c "from src.financial.debt_tracker import DebtTracker; d=DebtTracker(); s=d.get_payables_summary(); print(f'Borç: {s[\"total_remaining\"]:,.2f} TRY')"
```

### Toplam Alacak
```bash
python3 -c "from src.financial.debt_tracker import DebtTracker; d=DebtTracker(); s=d.get_receivables_summary(); print(f'Alacak: {s[\"total_remaining\"]:,.2f} TRY')"
```

---

## 📁 Önemli Dosya Yolları

```
data/db/birlesik.db              # Ana veritabanı
data/db/backups/                 # Backup'lar
data/logs/api_extraction.log     # API logları
data/excel/                      # Excel çıktıları
```

---

## 🆘 Sorun Giderme

### Migration Hatası
```bash
# Backup'tan geri yükle
cp data/db/backups/birlesik_backup_*.db data/db/birlesik.db

# Tekrar çalıştır
python3 src/database/schema_migration.py
```

### Veritabanı Kilidi
```bash
# Tüm Python process'leri kapat
pkill -9 python3

# Tekrar dene
```

### IRS Eşleşmesi Yok
```sql
-- Description'ları kontrol et
sqlite3 data/db/birlesik.db
SELECT description FROM invoices WHERE invoice_type='SALES' LIMIT 10;
```

---

## 📞 Yardım

- Detaylı Dok: `FINANCIAL_BACKEND.md`
- Kurulum: `BACKEND_COMPLETE.md`
- Bu Dosya: `QUICK_REFERENCE.md`

