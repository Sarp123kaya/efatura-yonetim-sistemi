# 📊 Excel Toplu Güncelleme Sistemi

## 🚀 Hızlı Başlangıç

### Tek Komutla Tüm Excel'leri Güncelle + API Veri Çek

```bash
./exceli_guncelle.sh
```

## 📋 Ne Yapar?

Bu script **5 adımda** tüm işlemleri otomatikleştirir:

1. **[1/5]** AK GİPS Excel → `data/excel/akgips/efatura_akgips_*.xlsx`
2. **[2/5]** Birleşik Excel → `data/excel/birlesik/efatura_birlesik.xlsx`
3. **[3/5]** FULLBOARD Excel → `data/excel/fullboard/efatura_fullboard_*.xlsx`
4. **[4/5]** 🌐 **API'den Veri Çek** → Şifre ister, giden + gelen faturaları çeker
5. **[5/5]** API Excel → `kayıtlar/API_Faturalar_*.xlsx`

## 🎯 Kullanım Seçenekleri

### 1. API Veri Çekme ile (Varsayılan)
```bash
./exceli_guncelle.sh
```
**Ne yapar:**
- İlk 3 Excel'i oluşturur
- **Şifre ister** (İşbaşı API şifreniz)
- API'den giden + gelen faturaları çeker
- API Excel'ini oluşturur

### 2. API Veri Çekme Olmadan
```bash
./exceli_guncelle.sh --skip-api
```
**Ne yapar:**
- İlk 3 Excel'i oluşturur
- API veri çekmeyi **atlar**
- Mevcut API veritabanından Excel oluşturur

### 3. Python ile Çalıştırma
```bash
# API ile
python3 update_all_excels.py

# API olmadan
python3 update_all_excels.py --skip-api
```

### 4. Yardım
```bash
./exceli_guncelle.sh --help
```

## 📊 Örnek Çıktı

```
╔════════════════════════════════════════════════════════════╗
║          TÜM EXCEL DOSYALARINI GÜNCELLEME                  ║
╚════════════════════════════════════════════════════════════╝

================================================================================
  TÜM EXCEL DOSYALARINI GÜNCELLEME
================================================================================
Başlangıç Zamanı: 15:49:24

[1/5] AKGIPS Excel Export...
--------------------------------------------------------------------------------
✓ Excel dosyası oluşturuldu: data/excel/akgips/efatura_akgips_20251107_154924.xlsx
✅ akgips Excel dosyası başarıyla oluşturuldu!

[2/5] BIRLESIK Excel Export...
--------------------------------------------------------------------------------
✓ Excel dosyası oluşturuldu: data/excel/birlesik/efatura_birlesik.xlsx
✅ birlesik Excel dosyası başarıyla oluşturuldu!

[3/5] FULLBOARD Excel Export...
--------------------------------------------------------------------------------
✓ Excel dosyası oluşturuldu: data/excel/fullboard/efatura_fullboard_20251107_154924.xlsx
✅ fullboard Excel dosyası başarıyla oluşturuldu!

[4/5] API'DEN VERİ ÇEKME...
--------------------------------------------------------------------------------
🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐
  API'DEN VERİ ÇEKME
🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐🌐

📱 İşbaşı API'sinden fatura verileri çekiliyor...
⚠️  Şifrenizi girmeniz gerekecek

🔐 Şifrenizi girin (görünmez): ********

📤 Giden faturalar çekiliyor...
✅ Sayfa 1/2 işlendi (10 fatura)
✅ Sayfa 2/2 işlendi (5 fatura)

📥 Gelen faturalar çekiliyor...
✅ Sayfa 1/1 işlendi (8 fatura)

✅ API'den toplam 23 fatura çekildi
   📤 Giden: 15
   📥 Gelen: 8

[5/5] API Excel Export...
--------------------------------------------------------------------------------
✅ API Excel dosyası başarıyla oluşturuldu!

================================================================================
  ÖZET RAPOR
================================================================================

⏱️  Toplam Süre: 12.45 saniye

📊 Sonuçlar:
  ✅ Başarılı: 5 işlem
     - 📄 AK GİPS Excel
     - 📄 Birleşik Excel
     - 📄 FULLBOARD Excel
     - 🌐 API Veri Çekme
     - 📄 API Excel

================================================================================

✅ Tüm Excel dosyaları başarıyla güncellendi!
```

## 🔒 Güvenlik

- Şifre **görünmez** şekilde girilir (getpass)
- Şifre **hiçbir yere kaydedilmez**
- Sadece API çağrıları için kullanılır
- Şifre girmek istemezseniz boş bırakın (API veri çekme atlanır)

## ⚙️ Özellikler

### ✅ Otomatik İşlemler
- Veritabanı kontrolü (yoksa atlar)
- Hata yönetimi (bir dosya hata verse diğerleri devam eder)
- İlerleme takibi (1/5, 2/5, ...)
- Detaylı özet rapor
- Süre hesaplama

### ✅ Esneklik
- API veri çekme opsiyonel (--skip-api)
- Tek tek veya toplu çalıştırma
- Python veya bash ile çalıştırma
- Veritabanı yoksa o adımı atlar

### ✅ Bilgilendirme
- Renkli terminal çıktısı
- İşlem durumu gösterimi
- Başarı/hata mesajları
- Toplam süre raporu

## 📁 Oluşturulan Dosyalar

### Excel Çıktıları
```
data/excel/
├── akgips/
│   └── efatura_akgips_YYYYMMDD_HHMMSS.xlsx (sadece 1 dosya - eski otomatik silinir)
├── birlesik/
│   └── efatura_birlesik.xlsx (sabit isim, her seferinde üzerine yazar)
├── fullboard/
│   └── efatura_fullboard_YYYYMMDD_HHMMSS.xlsx (sadece 1 dosya - eski otomatik silinir)
└── api/
    └── (boş - yeni Excel'ler kayıtlar klasöründe)

kayıtlar/
└── API_Faturalar_YYYYMMDD_HHMMSS.xlsx (sadece 1 dosya - eski otomatik silinir)
```

**🗑️ Otomatik Temizlik:**
- Her Excel oluşturulurken eski dosyalar otomatik silinir
- Her klasörde sadece en güncel dosya tutulur
- Disk alanı tasarrufu sağlar
- Manuel temizlik gerekmez

## 🛠️ Sorun Giderme

### "Şifre hatalı" hatası
- İşbaşı API şifrenizi kontrol edin
- Şifreniz değiştiyse yeni şifreyle tekrar deneyin

### "Veritabanı bulunamadı" uyarısı
- Normal bir durumdur
- O veritabanı için XML parse veya API çekme yapılmamış demektir
- Script diğer veritabanları ile devam eder

### Excel dosyası boş
- Veritabanında veri olduğundan emin olun:
  ```bash
  sqlite3 data/db/birlesik.db "SELECT COUNT(*) FROM invoices"
  ```

### Port/bağlantı hatası (API)
- İnternet bağlantınızı kontrol edin
- API servisi çalışıyor mu kontrol edin
- Firewall ayarlarınızı kontrol edin

## 💡 İpuçları

1. **Düzenli Kullanım:** Haftada bir çalıştırarak tüm verileri güncel tutun
2. **API Limiti:** API'den çok sık veri çekmeyin (saatte 1-2 kez yeterli)
3. **Şifre Hatırlatma:** Şifrenizi not defterinizde saklayın (güvenli bir yerde)
4. **Yedekleme:** Excel dosyalarını düzenli yedekleyin
5. **Otomatik İş:** Cron job ile otomatikleştirebilirsiniz (--skip-api ile)

## 🔗 İlgili Komutlar

### Sadece API Veri Çekme
```bash
python3 src/api/api_data_extractor.py
```

### Sadece Birleşik Excel
```bash
python3 src/exporters/birlesik_exporter.py
```

### Veritabanı Görüntüleme
```bash
python3 tools/view_db.py
```

## 📚 Daha Fazla Bilgi

- `README.md` - Ana dokümantasyon
- `HIZLI_BASLANGIC.md` - Hızlı başlangıç kılavuzu
- `docs/` - Detaylı dokümantasyon klasörü

---

**Son Güncelleme:** 7 Kasım 2024  
**Versiyon:** 2.2 (Otomatik API Entegrasyonu)

