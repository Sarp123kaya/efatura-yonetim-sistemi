# 🧹 Banka Bilgisi Temizleme Sistemi

## 📋 Özet

API'den çekilen fatura description'larından **SADECE banka bilgilerini otomatik olarak temizleyen** gelişmiş bir sistem.

**⚠️ ÖNEMLİ**: İrsaliye numaraları ve diğer önemli bilgiler **KORUNUR**.

## 🎯 Özellikler

### ✅ Desteklenen Formatlar
- **Excel format**: `_x000D_` satır sonları
- **Normal newline**: `\n`
- **Windows newline**: `\r\n`
- **HTML break**: `<br>` veya `<br/>`
- **Tek satır**: Boşluklarla ayrılmış
- **Spesifik IBAN**: Sadece GARANTİBANK IBAN'ı ve TR IBAN formatları

### ✅ Korunan Bilgiler
- **İrsaliye numaraları**: `F-9 99`, `A-18146`, vb.
- **Lokasyon bilgileri**: `(K.MARAŞ/ALTINOVA)`, `(İSTANBUL)`, vb.
- **Diğer açıklamalar**: Banka bilgisi olmayan tüm metinler

### ✅ Temizleme Noktaları
1. **Excel Export**: API Excel'e kaydedilmeden önce
2. **Database Insert**: Veritabanına kaydedilmeden önce
3. **Excel Report**: Birleşik Excel export'ta

## 🔧 Teknik Detaylar

### Ana Fonksiyon
```python
IsbasiAPIDataExtractor.clean_bank_info_from_description(description: str) -> str
```

**Konum**: `src/api/api_data_extractor.py` (satır 114-160)

### Kullanım Yerleri

1. **API Excel Export** (satır 363-369)
2. **Database Insert** (satır 541-568)
3. **Birlesik Export** (satır 64-66)

## 📊 Veritabanı Değişiklikleri

### Yeni Sütun
- **Tablo**: `invoices`
- **Sütun**: `description TEXT`
- **Güncellenen dosyalar**:
  - `merge_databases.py`
  - `api_data_extractor.py`
  - `birlesik_exporter.py`

## 🧪 Test Sonuçları

### Test 1: İrsaliye Numaraları Korunuyor ✅
```python
input = "IRSALIYE NO: F-9 99/F-9 98/F-9 97\nBanka Bilgileri\nGARANTİBANK - TR35 0006 2001 1670 0006 2939 21"
output = clean_bank_info_from_description(input)
# Sonuç: "IRSALIYE NO: F-9 99/F-9 98/F-9 97"
```

### Test 2: Lokasyon Bilgileri Korunuyor ✅
```python
input = "IRSALIYE NO: A-18146 (K.MARAŞ/ALTINOVA)\nBanka Bilgileri\nGARANTİBANK - TR35..."
output = clean_bank_info_from_description(input)
# Sonuç: "IRSALIYE NO: A-18146 (K.MARAŞ/ALTINOVA)"
```

### Test 3: Sadece Banka Bilgisi Temizleniyor ✅
```python
input = "Banka Bilgileri\nGARANTİBANK - TR35 0006 2001 1670 0006 2939 21"
output = clean_bank_info_from_description(input)
# Sonuç: "" (boş)
```

## 💡 Kullanım

### Yeni API Verisi Çekme
```bash
python3 src/api/api_data_extractor.py
```
→ Description otomatik temizlenir ve kaydedilir

### Excel Export
```bash
python3 src/exporters/birlesik_exporter.py
```
→ "Açıklama" sütunu temiz description'ları gösterir

## 📈 Sonuç

✅ **Banka bilgileri** artık hiçbir yerde görünmüyor
✅ **İrsaliye numaraları** korunuyor ve görünür kalıyor
✅ **Lokasyon bilgileri** (K.MARAŞ, İSTANBUL, vb.) korunuyor
✅ Temiz description'lar hem Excel'de hem DB'de
✅ Otomatik ve şeffaf çalışma
✅ 5 farklı format desteği

## 🔧 Versiyon Geçmişi

### v2.0 - 7 Kasım 2024
- 🐛 **Kritik Düzeltme**: İrsaliye numaralarının silinmesi sorunu çözüldü
- ✅ Agresif regex pattern'leri daha spesifik hale getirildi
- ✅ Satır sonları artık korunuyor
- ✅ Sadece kesin banka bilgileri temizleniyor
- ✅ Tüm testler başarılı (5/5)

### v1.0 - 15 Ekim 2024
- İlk versiyon
- Banka bilgileri temizleme özelliği eklendi

---
*Son güncelleme: 7 Kasım 2024*
