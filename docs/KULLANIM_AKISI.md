# 📊 E-Fatura Birleşik Sistem - Kullanım Akışı

## 🔄 Tam İş Akışı

### 1️⃣ XML Faturaları İşle
```bash
# AK GİPS XML'lerini parse et
python3 src/parsers/akgips_parser.py
# → data/db/akgips.db

# FULLBOARD XML'lerini parse et
python3 src/parsers/fullboard_parser.py
# → data/db/fullboard.db
```

### 2️⃣ API Faturalarını Çek
```bash
# İşbaşı API'sinden faturaları çek
python3 src/api/api_data_extractor.py
# Şifre girin → data/db/accounting_master.db
```

### 3️⃣ Tüm Veritabanlarını Birleştir
```bash
# 3 veritabanını birleştir
python3 src/database/merge_databases.py

# Çıktı:
# ✓ AK GİPS (A-) → birlesik.db
# ✓ FULLBOARD (F-) → birlesik.db
# ✓ API (API) → birlesik.db
```

### 4️⃣ Web Dashboard'u Başlat
```bash
./start_dashboard.sh
# → http://localhost:8080

# Dashboard'da göreceksiniz:
# - Toplam fatura sayısı (A + F + API)
# - Firma bazlı istatistikler
# - Tüm faturaları tek tabloda (firma badgeleri ile)
```

### 5️⃣ Excel Rapor Çıkar (Opsiyonel)
```bash
# Birleşik Excel raporu
python3 src/exporters/birlesik_exporter.py
# → data/excel/birlesik/efatura_birlesik_*.xlsx
```

## 📊 Veri Akışı Şeması

```
XML Dosyaları (akgips/*.xml)
    ↓
  Parser
    ↓
  akgips.db (firma_kodu: -)
    ↓
    ├──────────┐
    │          │
XML Dosyaları  │
(fullboard/*)  │
    ↓          │
  Parser       │
    ↓          │
fullboard.db   │
    ↓          │
    ├──────────┤
    │          │
İşbaşı API     │
    ↓          │
api_data_      │
extractor.py   │
    ↓          │
accounting_    │
master.db      │
    ↓          │
    └──────────┴──────────────┐
                              │
                    merge_databases.py
                              │
                              ↓
                        birlesik.db
                    (A, F, API firmalar)
                              │
                    ┌─────────┴─────────┐
                    │                   │
              Web Dashboard      Excel Exporter
              (app.py)           (birlesik_exporter.py)
                    │                   │
                    ↓                   ↓
            http://localhost:8080    *.xlsx
```

## 🎯 Önemli Notlar

1. **API → Birleştirme Sırası**
   - Önce `api_data_extractor.py` çalıştırın
   - Sonra `merge_databases.py` çalıştırın
   - Aksi halde API verileri birleşik DB'de olmaz

2. **Firma Kodları**
   - **A** = AK GİPS (XML)
   - **F** = FULLBOARD (XML)
   - **API** = İşbaşı API

3. **Dashboard Veri Kaynağı**
   - Dashboard **sadece** `birlesik.db`'den okur
   - API verilerini görmek için birleştirme şart!

4. **Yeniden Birleştirme**
   - Yeni API verileri çektikten sonra
   - `merge_databases.py`'yi tekrar çalıştırın
   - Eski `birlesik.db` silinir, yenisi oluşturulur

## ✅ Hızlı Kontrol

```bash
# Birleşik DB'de kaç fatura var?
sqlite3 data/db/birlesik.db "SELECT firma_kodu, COUNT(*) FROM invoices GROUP BY firma_kodu"

# Çıktı örneği:
# A|150
# F|75
# API|230
```

---

**Versiyon:** 2.1 (Birleşik Sistem)  
**Güncelleme:** 15 Ekim 2025
