# Yeni Bilgisayar 0'dan Kurulum Rehberi

Bu rehber, e-fatura yönetim sistemini yeni bir bilgisayara sıfırdan kurmak için hazırlanmıştır.

Amaç:
- GitHub'dan doğru branch'i indirmek
- Python paketlerini kurmak
- PostgreSQL veritabanını hazırlamak
- İşbaşı API bilgilerini `.env` dosyasına tanımlamak
- İlk veri çekişini ve Excel üretimini çalıştırmak

> Bu dosya tek başına indirilebilir. Yeni bilgisayarda Claude/terminal kullanıyorsan bu dosyayı yükleyip "bu rehbere göre projeyi kur" diyebilirsin.

---

## 1. Gerekli Programlar

Yeni bilgisayarda şunlar kurulu olmalı:

- Git
- Python 3.9 veya üzeri
- PostgreSQL 15 veya uyumlu sürüm
- Terminal erişimi

macOS için örnek:

```bash
brew install git python postgresql@15
brew services start postgresql@15
```

PostgreSQL zaten kuruluysa bu adımı atlayabilirsin.

---

## 2. Projeyi GitHub'dan İndir

Son çalışan sistem `VPS` branch'indedir. Bu yüzden repo bu branch ile klonlanmalı:

```bash
git clone -b VPS https://github.com/Sarp123kaya/efatura-yonetim-sistemi.git
cd efatura-yonetim-sistemi
```

Branch kontrolü:

```bash
git branch
```

Beklenen:

```text
* VPS
```

---

## 3. Python Paketlerini Kur

```bash
python3 -m pip install -r requirements.txt
```

Eğer `pip` izin hatası verirse:

```bash
python3 -m pip install --user -r requirements.txt
```

---

## 4. PostgreSQL Database Oluştur

Local PostgreSQL kullanıyorsan:

```bash
createdb invoices
```

Eğer database zaten varsa bu komut hata verebilir; sorun değil, devam edebilirsin.

Bağlantıyı test et:

```bash
psql postgresql://$(whoami)@localhost:5432/invoices -c "SELECT 1;"
```

Şifreli kullanıcı kullanıyorsan bağlantı formatı şu şekildedir:

```text
postgresql://KULLANICI:SIFRE@localhost:5432/invoices
```

---

## 5. Database Migration'larını Uygula

Kendi PostgreSQL bağlantı adresini aşağıdaki komutlarda kullan.

Şifresiz local kullanıcı örneği:

```bash
export DB_URL="postgresql://$(whoami)@localhost:5432/invoices"
```

Şifreli kullanıcı örneği:

```bash
export DB_URL="postgresql://KULLANICI:SIFRE@localhost:5432/invoices"
```

Migration sırası:

```bash
psql "$DB_URL" -f sql/stateful_ingestion_schema_v2.sql
psql "$DB_URL" -f sql/migration_v2.2_despatch_improvements.sql
psql "$DB_URL" -f sql/migration_irsaliye_override.sql
psql "$DB_URL" -f sql/migration_incoming_xml_cache.sql
psql "$DB_URL" -f sql/migration_outgoing_xml_cache.sql
```

Tabloları kontrol et:

```bash
psql "$DB_URL" -c "\dt"
```

Önemli tablolar:

- `incoming_invoices`
- `outgoing_invoices`
- `incoming_invoice_xml_cache`
- `outgoing_invoice_xml_cache`
- `agent_state`
- `agent_runs`

---

## 6. `.env` Dosyasını Oluştur

```bash
cp env.example .env
```

Sonra `.env` dosyasını düzenle:

```bash
nano .env
```

Gerekli alanlar:

```bash
ISBASI_API_KEY=BURAYA_API_KEY
ISBASI_USERNAME=BURAYA_EMAIL
ISBASI_PASSWORD=BURAYA_SIFRE
ISBASI_BASE_URL=https://mw-jplatform.isbasi.com
ISBASI_VERIFY_SSL=true
ISBASI_OUTGOING_UBL_ENDPOINT=

DB_URL=postgresql://KULLANICI:SIFRE@localhost:5432/invoices
```

Local şifresiz PostgreSQL kullanıyorsan:

```bash
DB_URL=postgresql://KULLANICI@localhost:5432/invoices
```

Notlar:
- `.env` GitHub'a gönderilmez.
- API bilgileri gizlidir.
- `ISBASI_PASSWORD` dolu olursa sistem şifre sormadan çalışır. Cron/otomasyon için önerilir.

---

## 7. Kurulumu Kontrol Et

```bash
python3 scripts/verify_installation.py
```

Database bağlantısı `.env` doğruysa başarılı olmalıdır.

---

## 8. İlk Veri Çekişi

İlk kurulumda XML cache'i de doldurmak için `--refresh-xml` ile çalıştır:

```bash
python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml
```

Bu komut:
1. Gelen faturaları API'den çeker
2. Gelen fatura XML'lerini çeker ve `incoming_invoice_xml_cache` içine yedekler
3. Giden faturaları API'den çeker
4. Giden fatura XML'lerini çeker ve `outgoing_invoice_xml_cache` içine yedekler
5. PostgreSQL'e kaydeder
6. Normal eşleştirme ve ters eşleştirme Excel raporlarını üretir

İlk çalıştırma uzun sürebilir çünkü XML cache doldurulur.

---

## 9. Sonraki Güncellemeler

Cache dolduktan sonra normal güncelleme için:

```bash
python3 scripts/run_invoice_pipeline.py
```

Bu çalıştırmada:
- Fatura listesi API'den kontrol edilir
- Cache'te olan XML'ler tekrar çekilmez
- Sadece yeni/cache'te olmayan XML'ler API'den çekilir
- Normal eşleştirme ve ters eşleştirme raporları birlikte üretilir

XML'leri zorla yeniden çekmek gerekirse:

```bash
python3 scripts/run_invoice_pipeline.py --refresh-xml
```

---

## 10. Fabrika Excel'lerini Oluştur

AK GIPS ve FULLBOARD ürün/adet/fiyat detay Excel'leri:

```bash
python3 scripts/export_supplier_invoice_details.py
```

Çıktılar:

```text
kayıtlar/AK_GIPS_Fabrikasi_YYYYMMDD_HHMMSS.xlsx
kayıtlar/FULLBOARD_Fabrikasi_YYYYMMDD_HHMMSS.xlsx
```

Excel içerikleri:
- Fatura detayları
- Giden müşteri
- Giden müşteri fiyatı
- İrsaliye açıklaması
- Ürün adı/kodu
- Miktar
- Birim fiyat
- KDV dahil birim fiyat
- Torba KG
- Torba alış fiyatı
- FULLBOARD için ek `Pivot Özet` sayfası

---

## 11. Müşteri Ürün Fiyat Raporunu Oluştur

Müşterilere kesilen giden faturaların ürün/fiyat detayları:

```bash
python3 scripts/export_customer_product_prices.py
```

Çıktı:

```text
kayıtlar/Musteri_Urun_Fiyatlari_YYYYMMDD_HHMMSS.xlsx
```

Excel içerikleri:
- `Tüm Detaylar`
- `Müşteri Özeti`
- Her müşteri için ayrı sayfa

Not: Ürün satırlarının dolması için `outgoing_invoice_xml_cache` tablosunda XML içerikleri bulunmalıdır. İlk kurulumda `--refresh-xml` ile pipeline çalıştırmak gerekir.

---

## 12. En Sık Kullanılan Komutlar

Tek komutla çek, aktar, eşleştir:

```bash
python3 scripts/run_invoice_pipeline.py
```

Tüm Excel raporları tek komutta (eşleştirme, ters eşleştirme, gelen/giden listeleri, agent geçmişi, fabrikalar, müşteri fiyat):

```bash
python3 scripts/run_invoice_pipeline.py --all-excel
```

İlk kurulum veya XML cache yenileme:

```bash
python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml
```

İlk kurulumda tüm raporları birlikte almak için:

```bash
python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml --all-excel
```

Fabrika Excel'leri:

```bash
python3 scripts/export_supplier_invoice_details.py
```

Müşteri ürün fiyat raporu:

```bash
python3 scripts/export_customer_product_prices.py
```

Sadece gelen faturalar:

```bash
python3 backend/agents/incoming_agent.py
```

Sadece giden faturalar:

```bash
python3 backend/agents/outgoing_agent.py
```

Sadece eşleştirme raporu:

```bash
python3 scripts/run_invoice_pipeline.py --skip-ingest
```

---

## 13. Claude Terminal İçin Hazır Talimat

Yeni bilgisayarda Claude terminal açınca bu dosyayı yükleyip şu talimatı verebilirsin:

```text
Bu Markdown dosyasındaki kurulum rehberini uygula.
Önce sistemde git, python3, pip ve postgresql var mı kontrol et.
Sonra GitHub'dan VPS branch'ini klonla:
https://github.com/Sarp123kaya/efatura-yonetim-sistemi.git
requirements.txt paketlerini kur.
PostgreSQL'de invoices database oluştur.
sql migration dosyalarını bu rehberdeki sırayla uygula.
.env dosyasını env.example'dan oluştur.
Benden ISBASI_API_KEY, ISBASI_USERNAME, ISBASI_PASSWORD ve DB_URL değerlerini iste.
Kurulum bittikten sonra scripts/verify_installation.py çalıştır.
Sonra ilk veri çekişi için scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml komutunu çalıştırmadan önce benden onay al.
```

---

## 13. Sorun Giderme

### `psql: command not found`

PostgreSQL client kurulu değildir.

macOS:

```bash
brew install postgresql@15
```

### `database "invoices" does not exist`

```bash
createdb invoices
```

### `password authentication failed`

`.env` içindeki `DB_URL` kullanıcı/şifre bilgisini kontrol et.

### `ISBASI_API_KEY eksik`

`.env` dosyasını oluşturup API bilgilerini doldur:

```bash
cp env.example .env
```

### Ürün/adet/birim fiyat kolonları boş geliyor

XML cache dolu değildir. Şunu çalıştır:

```bash
python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml
```

Sonra fabrika Excel'lerini tekrar üret:

```bash
python3 scripts/export_supplier_invoice_details.py
```

---

## 14. GitHub'dan Tek Dosya İndirme

Bu rehberi tek başına indirmek için GitHub'da `docs/YENI_BILGISAYAR_KURULUM_REHBERI.md` dosyasını açıp `Raw` seçeneğiyle kaydedebilirsin.

Komutla indirmek istersen:

```bash
curl -L -o docs/YENI_BILGISAYAR_KURULUM_REHBERI.md \
https://raw.githubusercontent.com/Sarp123kaya/efatura-yonetim-sistemi/VPS/docs/YENI_BILGISAYAR_KURULUM_REHBERI.md
```

