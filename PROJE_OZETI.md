# 📊 E-Fatura Yönetim Sistemi - Proje Özeti

## 🎯 Projenin Amacı

XML ve API'den gelen e-faturaları parse edip, veritabanında saklayan ve Excel raporları oluşturan kapsamlı bir sistem.

---

## 📂 Proje Yapısı

```
📁 gelen efaturalar deneme/
├── 📁 data/                    # Tüm veriler
│   ├── 📁 db/                  # SQLite veritabanları
│   ├── 📁 excel/               # Excel çıktıları
│   ├── 📁 xml/                 # XML dosyaları
│   └── 📁 logs/                # Log dosyaları
├── 📁 src/                     # Kaynak kodlar
│   ├── 📁 api/                 # API işlemleri
│   ├── 📁 parsers/             # XML parser'lar
│   ├── 📁 exporters/           # Excel oluşturucular
│   ├── 📁 database/            # DB işlemleri
│   ├── 📁 financial/           # Finansal modüller
│   └── 📁 web/                 # Web dashboard
├── 📁 tools/                   # Yardımcı araçlar
├── 📁 docs/                    # Dokümantasyon
└── 📁 kayıtlar/                # API Excel çıktıları
```

---

## 🗄️ Veritabanları

### 1. `akgips.db` - AK GİPS Firması
**Kaynak**: XML dosyaları (`data/xml/akgips/*.xml`)

**Tablolar**:
- `invoices` - Fatura ana bilgileri
- `invoice_lines` - Fatura satırları (ürün/hizmet detayları)
- `despatch_documents` - İrsaliye bilgileri
- `attachments` - XSLT ve ek dosyalar

**İçerik**: 3 fatura, 23 satır, 10 irsaliye

### 2. `fullboard.db` - FULLBOARD Firması
**Kaynak**: XML dosyaları (`data/xml/fullboard/*.xml`)

**Tablolar**: akgips.db ile aynı

**İçerik**: 3 fatura, 6 satır, 3 irsaliye

### 3. `api.db` - İşbaşı API
**Kaynak**: İşbaşı API (online)

**Tablolar**:
- `invoices` - Fatura bilgileri (8 sütun: id, date, invoiceNumber, totalTL, taxableAmount, firmName, description, irsaliyeNo)

**İçerik**: 1759 fatura (giden + gelen)

### 4. `birlesik.db` - ⭐ MASTER DATABASE
**Kaynak**: akgips.db + fullboard.db + api.db (otomatik birleştirme)

**Tablolar**: Tüm tabloları içerir

**Firma Kodları**:
- `A` = AK GİPS
- `F` = FULLBOARD
- `API` = İşbaşı API

**İçerik**: 1663+ fatura (tüm kaynaklar birleşik)

---

## 📊 Excel Dosyaları

### 1. `data/excel/akgips/efatura_akgips_YYYYMMDD_HHMMSS.xlsx`
**Sayfalar**:
- **Özet**: Genel istatistikler
- **Faturalar**: Tüm faturalar listesi
- **Fatura Satırları**: Detaylı kalem bilgileri + ADET hesaplaması
- **İrsaliyeler**: İrsaliye listesi

**Özel Hesaplama**: 
- TNE birimi → ADET = miktar × 1000 ÷ 35
- EA birimi → ADET = miktar

### 2. `data/excel/fullboard/efatura_fullboard_YYYYMMDD_HHMMSS.xlsx`
**İçerik**: akgips ile aynı format

### 3. `data/excel/birlesik/efatura_birlesik.xlsx`
**Sayfalar**: Tüm firmaların birleşik verileri
**Özellik**: Firma kodları (A, F, API) ile ayrıştırma

### 4. `kayıtlar/API_Faturalar_YYYYMMDD_HHMMSS.xlsx`
**İçerik**: 
- 8 sütun (id, date, invoiceNumber, totalTL, taxableAmount, firmName, description, irsaliyeNo)
- Giden + Gelen faturalar
- İstatistikler (giden/gelen ayrımı)
- Tarih formatı: gün.ay.yıl

**Özel Özellik**: Description'dan banka bilgileri otomatik temizlenir, irsaliye numaraları korunur

---

## 🔧 Ana Fonksiyonlar

### 📁 `src/parsers/`

#### `akgips_parser.py`
```python
def parse_xml(xml_file) -> Dict
```
- XML dosyasını parse eder
- UBL-TR 2.1 formatını okur
- Fatura, satır, irsaliye bilgilerini çıkarır
- İrsaliye numaralarını sadeleştirir (A-14740)

#### `fullboard_parser.py`
```python
def parse_xml(xml_file) -> Dict
```
- akgips_parser ile aynı mantık
- FULLBOARD formatına özgü düzenlemeler

---

### 📁 `src/api/`

#### `api_data_extractor.py`

**Ana Sınıf**: `IsbasiAPIDataExtractor`

```python
def __init__()
```
- API bağlantısını başlatır
- Session ve header'ları ayarlar
- Veritabanı bağlantısı kurar

```python
def secure_login() -> bool
```
- İşbaşı API'sine güvenli giriş
- Şifre getpass ile alınır (görünmez)
- Access token alır

```python
def fetch_invoices() -> bool
```
- API'den tüm faturaları çeker (giden + gelen)
- Sayfalama ile çalışır (100'er kayıt)
- Excel ve veritabanına kaydeder

```python
@staticmethod
def clean_bank_info_from_description(description: str) -> str
```
- **ÖNEMLİ**: Description'dan SADECE banka bilgilerini temizler
- İrsaliye numaraları KORUNUR
- IBAN ve banka adını siler
- Spesifik pattern'ler kullanır

#### `api_database.py`

**Ana Sınıf**: `APIDatabase`

```python
def insert_invoice(invoice_data: Dict) -> int
```
- Faturayı api.db'ye ekler
- Duplicate kontrolü yapar
- Description'ı temizler
- İrsaliye numaralarını çıkarır

```python
@staticmethod
def extract_irsaliye_numbers(description: str) -> List[str]
```
- Description'dan irsaliye numaralarını regex ile çıkarır
- IRS-12345, A-18146, F-9 99 formatlarını destekler

---

### 📁 `src/exporters/`

#### `akgips_exporter.py`
```python
def create_excel_export() -> str
```
- akgips.db'den Excel oluşturur
- 4 sayfa: Özet, Faturalar, Fatura Satırları, İrsaliyeler
- ADET hesaplaması yapar
- Eski Excel dosyalarını siler

#### `fullboard_exporter.py`
```python
def create_excel_export() -> str
```
- fullboard.db'den Excel oluşturur
- akgips_exporter ile aynı format

#### `birlesik_exporter.py`
```python
def create_excel_export() -> str
```
- birlesik.db'den Excel oluşturur
- Firma kodları ile gruplar
- Sabit dosya adı (üzerine yazar)

#### `api_exporter.py`
```python
def export_api_to_excel(db_path: str, output_path: str) -> bool
```
- api.db'den Excel oluşturur
- 8 sütun (kullanıcı hafızasına göre)
- Tarih formatı: gün.ay.yıl
- İstatistikler: giden/gelen ayrımı
- İrsaliye numaraları description'dan çıkarılır

---

### 📁 `src/database/`

#### `merge_databases.py`
```python
def merge_databases() -> bool
```
- akgips.db + fullboard.db + api.db → birlesik.db
- Firma kodları ekler (A, F, API)
- İrsaliyeleri sadeleştirir
- Duplicate kontrolü yapar

#### `schema_migration.py`
```python
def migrate_database(db_path: str) -> bool
```
- Veritabanı şemasını günceller
- Yeni sütunlar ekler
- Mevcut verileri korur

---

### 📁 `src/web/`

#### `app.py`

**Flask Web Dashboard**

```python
@app.route('/')
def index()
```
- Ana sayfa
- KPI kartları gösterir
- Fatura listesi gösterir
- Firma bazlı renklendirme (A=turuncu, F=mor, API=mavi)

**Özellikler**:
- Toplam fatura sayısı ve tutar
- Firma bazlı ayrıştırma
- İrsaliye sayısı
- Modern gradient tasarım
- Otomatik yenileme
- Port: 8080

---

### 📁 `src/financial/`

#### `balance_calculator.py`
```python
def calculate_balance(firm: str) -> Dict
```
- Firma bazlı bakiye hesaplar
- Gelen/giden dengesini bulur

#### `debt_tracker.py`
```python
def track_debts() -> List[Dict]
```
- Borç durumunu takip eder
- Ödenmeyen faturaları listeler

#### `irs_matcher.py`
```python
def match_invoices_with_irsaliye() -> List[Dict]
```
- Faturaları irsaliyelerle eşleştirir
- Eksik irsaliyeleri bulur

#### `payment_manager.py`
```python
def process_payment(invoice_id: int, amount: float) -> bool
```
- Ödeme işlemlerini yönetir
- Ödeme geçmişi tutar

---

## 🚀 Ana Script'ler

### 1. `exceli_guncelle.sh` / `update_all_excels.py`
**⭐ EN ÖNEMLİ SCRIPT**

**Ne Yapar**:
1. AK GİPS Excel oluşturur
2. Birleşik Excel oluşturur
3. FULLBOARD Excel oluşturur
4. API'den veri çeker (şifre ister)
5. API Excel oluşturur

**Kullanım**:
```bash
./exceli_guncelle.sh              # API veri çekme ile
./exceli_guncelle.sh --skip-api   # API'yi atla
```

**Özellikler**:
- Eski Excel dosyalarını otomatik siler
- Her klasörde sadece 1 dosya tutar
- İlerleme gösterir (1/5, 2/5, vb.)
- Hata yönetimi
- Özet rapor

### 2. `start_dashboard.sh`
**Web Dashboard Başlatıcı**

```bash
./start_dashboard.sh
```
→ http://localhost:8080

### 3. `yeniden_olustur.sh`
**Tüm Sistemi Yeniden Oluştur**

---

## 🛠️ Tools (Yardımcı Araçlar)

### `view_db.py`
```python
python3 tools/view_db.py
```
- Veritabanını terminalde görüntüler
- Tablo özetleri gösterir

### `irsaliye_rapor.py`
```python
python3 tools/irsaliye_rapor.py
```
- İrsaliye bazlı detaylı rapor
- Eksik irsaliyeleri bulur

### `clean_exports.py`
```python
python3 tools/clean_exports.py
```
- Eski Excel dosyalarını temizler
- En yeni dosyayı tutar

---

## 🔄 Veri Akışı

### XML → Veritabanı → Excel
```
1. XML Dosyaları (data/xml/akgips/*.xml)
   ↓
2. Parser (akgips_parser.py)
   ↓
3. Veritabanı (akgips.db)
   ↓
4. Exporter (akgips_exporter.py)
   ↓
5. Excel (data/excel/akgips/efatura_akgips_*.xlsx)
```

### API → Veritabanı → Excel
```
1. İşbaşı API (online)
   ↓
2. API Extractor (api_data_extractor.py)
   ↓ (şifre ister)
3. Veritabanı (api.db)
   ↓
4. Exporter (api_exporter.py)
   ↓
5. Excel (kayıtlar/API_Faturalar_*.xlsx)
```

### Birleştirme
```
akgips.db + fullboard.db + api.db
   ↓
merge_databases.py
   ↓
birlesik.db
   ↓
birlesik_exporter.py
   ↓
data/excel/birlesik/efatura_birlesik.xlsx
```

---

## 📋 Özel Özellikler

### 1. ADET Hesaplaması
```python
if birim == 'TNE':
    adet = miktar × 1000 ÷ 35
elif birim == 'EA':
    adet = miktar
```

### 2. İrsaliye Sadeleştirme
```
Önce: IRS00014740
Sonra: A-14740

Önce: IRS00007904
Sonra: F-07904
```

### 3. Banka Bilgisi Temizleme
```python
Önce: "IRSALIYE NO: F-9 99\nBanka Bilgileri\nGARANTİBANK - TR35..."
Sonra: "IRSALIYE NO: F-9 99"
```
**ÖNEMLİ**: İrsaliye numaraları KORUNUR!

### 4. Otomatik Excel Temizleme
- Her export'ta eski dosyalar silinir
- Sadece en güncel dosya tutulur
- Disk alanı tasarrufu

### 5. Firma Renklendirme (Dashboard)
- 🟠 **A** = AK GİPS (turuncu)
- 🟣 **F** = FULLBOARD (mor)
- 🔵 **API** = İşbaşı API (mavi)

---

## 🎯 Kullanım Senaryoları

### Senaryo 1: Yeni XML Faturaları Ekleme
```bash
# 1. XML'leri kopyala
cp yeni_faturalar/*.xml data/xml/akgips/

# 2. Parser'ı çalıştır
python3 src/parsers/akgips_parser.py

# 3. DB'leri birleştir
python3 src/database/merge_databases.py

# 4. Excel'leri güncelle
./exceli_guncelle.sh --skip-api
```

### Senaryo 2: API'den Veri Çekme + Tüm Excel'leri Güncelleme
```bash
./exceli_guncelle.sh
# Şifre: ******* (görünmez)
```

### Senaryo 3: Dashboard'u Başlatma
```bash
./start_dashboard.sh
# http://localhost:8080
```

### Senaryo 4: Sadece API Excel Güncelleme
```bash
python3 src/exporters/api_exporter.py
```

---

## 📊 İstatistikler

### Veritabanı Boyutları
- `akgips.db`: ~50 KB (3 fatura)
- `fullboard.db`: ~50 KB (3 fatura)
- `api.db`: ~500 KB (1759 fatura)
- `birlesik.db`: ~600 KB (1663+ fatura)

### Excel Boyutları
- AK GİPS: ~9 KB
- FULLBOARD: ~8 KB
- Birleşik: ~139 KB
- API: ~98 KB

### Tutar Toplamları
- AK GİPS: 835,855.80 TRY
- FULLBOARD: 238,275.00 TRY
- Birleşik: 180,603,584.25 TRY
- API: 190,302,742.00 TRY

---

## 🔒 Güvenlik

- API şifresi **getpass** ile alınır (görünmez)
- Şifre **hiçbir yere kaydedilmez**
- SSL doğrulaması devre dışı (internal API)
- Access token session'da saklanır

---

## 📝 Önemli Notlar

1. ✅ Birleşik DB her zaman en güncel veriyi içerir
2. ✅ Excel dosyaları otomatik temizlenir
3. ✅ İrsaliye numaraları korunur ve görünür
4. ✅ Banka bilgileri otomatik temizlenir
5. ✅ Dashboard otomatik yenilenir
6. ✅ Tüm path'ler proje kök dizinine göre relatif

---

## 🎓 Kısaltmalar

- **DB**: Database (Veritabanı)
- **API**: Application Programming Interface
- **XML**: eXtensible Markup Language
- **UBL-TR**: Universal Business Language - Türkiye
- **IBAN**: International Bank Account Number
- **TNE**: Ton (birim)
- **EA**: Each / Adet (birim)
- **KPI**: Key Performance Indicator

---

**Versiyon**: 2.2 (Otomatik API + Excel Temizleme)  
**Son Güncelleme**: 7 Kasım 2024  
**Geliştirici**: AI + sp383

🎉 **Tam Otomatik E-Fatura Yönetim Sistemi!**

