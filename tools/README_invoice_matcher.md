# 🔍 Fatura Eşleştirme Aracı

## 📋 Genel Bakış

Bu araç, API'den gönderilen faturaların description alanından irsaliye kodlarını (A-18356, F-9197 gibi) otomatik olarak çıkarıp, ilgili veritabanlarında (akgips.db veya fullboard.db) eşleşen gelen fatura bilgilerini bulur ve detaylı bir Excel raporu oluşturur.

## 🚀 Kullanım

### Basit Kullanım

```bash
python3 tools/invoice_matcher.py
```

### Çıktı

- **Konum**: `kayıtlar/Fatura_Eslesme_Raporu_YYYYMMDD_HHMMSS.xlsx`
- **Format**: Excel (.xlsx) - Formatlanmış tablo + istatistikler

## 📊 Rapor İçeriği

### Sütunlar

1. **Giden_Fatura_No**: API'den gelen fatura numarası
2. **Giden_Tutar_TL**: Gönderilen fatura tutarı
3. **Irsaliye_Kodu**: Description'dan çıkarılan irsaliye kodu (A-18356, F-9197 vb.)
4. **Firma**: AK GİPS veya FULLBOARD
5. **Gelen_Fatura_No**: Veritabanında bulunan karşılık fatura numarası
6. **Gelen_Tutar_TL**: Gelen fatura tutarı
7. **Durum**: 
   - ✅ **Eşleşti ✓** (Yeşil arka plan)
   - ❌ **Bulunamadı ✗** (Kırmızı arka plan)
   - ⚠️ **İrsaliye kodu yok ⚠** (Sarı arka plan)

### İstatistikler

Rapor sonunda otomatik oluşturulan özet:
- ✓ Eşleşen fatura sayısı
- ✗ Bulunamayan fatura sayısı
- ⚠ İrsaliye kodu olmayan fatura sayısı
- 📝 Toplam kayıt sayısı

## 🔧 Nasıl Çalışır?

### 1. İrsaliye Kodlarını Çıkarma

Description alanından regex ile irsaliye kodları çıkarılır:

**Desteklenen Formatlar:**
- `İRSALİYE NO: A-18356` - Standart format
- `İRSALİYE NO: F-9171 ( İSTANBUL )` - Lokasyon ile
- `İRSALİYE NO: F-9170 / F-9189` - Çoklu irsaliye (/ ile ayrılmış)
- `İRSALİYE NO:F/9099/F-9098/F-9097` - Birleşik format
- `İRSALİYE NO: F- 9026` - Boşluklu format
- `İRSALİYE NO: 18277` - ❌ ATLANIR (prefix yok)

**Pattern**: `([AF])\s*[-/]\s*(\d{4,5})`
- A veya F prefix'i zorunlu
- 4-5 haneli numara
- Boşluk ve / karakterleri desteklenir

### 2. Veritabanında Arama

- **A-** prefix → `data/db/akgips.db`
- **F-** prefix → `data/db/fullboard.db`

SQL sorgusu:
```sql
SELECT i.invoice_number, i.total_amount 
FROM despatch_documents d 
JOIN invoices i ON d.invoice_id = i.id 
WHERE d.despatch_id_short = 'A-18356'
```

### 3. Excel Raporu Oluşturma

- Renkli header (mavi)
- Para birimi formatı (₺)
- Durum bazlı satır renklendirme
- Otomatik sütun genişlikleri
- İstatistik özeti

## 📁 Gerekli Dosyalar

### Girdi

- `data/excel/api/API_Giden_Faturalar.xlsx` - Giden faturalar
- `data/db/akgips.db` - AK GİPS veritabanı
- `data/db/fullboard.db` - FULLBOARD veritabanı

### Çıktı

- `kayıtlar/Fatura_Eslesme_Raporu_YYYYMMDD_HHMMSS.xlsx` - Eşleştirme raporu

## 📈 Örnek Sonuçlar

### Test Verisi (1837 fatura)

```
📊 İstatistikler:
   ✓ Eşleşen: 15
   ✗ Bulunamayan: 453
   ⚠ İrsaliye kodu yok: 1485
   📝 Toplam: 1960
```

### Firma Dağılımı

```
AK GİPS:   234 irsaliye kodu
FULLBOARD: 234 irsaliye kodu
```

### İyileştirme Sonuçları

**Önceki Versiyon:**
- 212 irsaliye kodu yakalandı
- Sadece basit A-XXXXX formatı destekleniyordu

**Güncel Versiyon:**
- 453 irsaliye kodu yakalandı (+241, %113.7 iyileştirme)
- Çoklu format desteği (/, boşluk, birleşik)
- Prefix kontrolü (18277 gibi kodlar atlanır)

## 🔍 Örnek Eşleşme

| Giden_Fatura_No | Giden_Tutar_TL | Irsaliye_Kodu | Firma | Gelen_Fatura_No | Gelen_Tutar_TL | Durum |
|----------------|----------------|---------------|-------|-----------------|----------------|--------|
| DKE2025000001135 | 84,100.80 ₺ | A-18286 | AK GİPS | AKG2025000008665 | 75,826.80 ₺ | Eşleşti ✓ |
| DKE2025000001141 | 114,136.80 ₺ | A-18356 | AK GİPS | - | 0.00 ₺ | Bulunamadı ✗ |
| DKE2025000000123 | 50,000.00 ₺ | Bulunamadı | - | - | 0.00 ₺ | İrsaliye kodu yok ⚠ |

## 🛠️ Teknik Detaylar

### Regex Pattern

```python
pattern = r'([AF])\s*[-/]\s*(\d{4,5})'
```

**Açıklama:**
- `([AF])` - A veya F prefix'i (zorunlu)
- `\s*` - Opsiyonel boşluk
- `[-/]` - Tire veya slash ayracı
- `\s*` - Opsiyonel boşluk
- `(\d{4,5})` - 4 veya 5 haneli numara

### Bağımlılıklar

```python
pandas
xlsxwriter
sqlite3 (built-in)
re (built-in)
```

### Sınıf Yapısı

```python
class InvoiceMatcher:
    def extract_irsaliye_codes(description) -> list
    def search_in_database(irsaliye_code, db_path) -> dict
    def process_api_invoices() -> pd.DataFrame
    def generate_excel_report(df) -> Path
    def run() -> Path
```

## 🐛 Sorun Giderme

### "API Excel dosyası bulunamadı"

```bash
# Dosyanın varlığını kontrol edin
ls -l data/excel/api/API_Giden_Faturalar.xlsx
```

### "Veritabanı bulunamadı"

```bash
# Veritabanlarını kontrol edin
ls -l data/db/akgips.db
ls -l data/db/fullboard.db
```

### Boş Sonuç

- XML dosyalarının parse edildiğinden emin olun
- `despatch_documents` tablosunun dolu olduğunu kontrol edin:

```bash
sqlite3 data/db/akgips.db "SELECT COUNT(*) FROM despatch_documents"
```

## 📞 Destek

Sorunlar için:
- `data/logs/api_extraction.log` - API çekme logları
- Script çıktısı - Eşleştirme işlem logları

## 🎯 İleriye Dönük Geliştirmeler

- [ ] Web arayüzü entegrasyonu
- [ ] Otomatik e-posta bildirimi
- [ ] Tutar farkı analizi
- [ ] Zamanlı çalıştırma (cron/scheduler)
- [ ] PDF rapor seçeneği

