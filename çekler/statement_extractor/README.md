# Statement Check Extractor

Bu modül cari/muavin ekstre PDF dosyalarından `ALINAN ÇEK` hareketlerini çıkarır, normalize edilmiş `CheckRecord` nesneleri üretir ve vadeye göre sıralanmış Excel çıktısı oluşturur. PDF herhangi bir dış API'dan çekilmez; kullanıcı ERP ekranından manuel PDF yükler.

## Beklenen PDF Formatı

İlk sürüm text tabanlı Muavin Defter PDF'lerini destekler. OCR yoktur. Taranmış görsel PDF dosyalarında şu hata döner:

`PDF metni okunamadı veya taranmış görsel PDF olabilir.`

Üst bölümdeki şu alanlar metadata olarak okunmaya çalışılır:

- `Firma`
- `Alt Hesap Kodu`
- `Alt Hesap Adı`

Parser sadece `ALINAN ÇEK`, `ALINAN CEK`, `Alınan Çek`, `ALINAN ÇEK(...)` ve `ALINAN ÇEK (...)` varyasyonlarını işler. `VERİLEN ÇEK`, EFT, HAVALE veya ödeme satırları bu aşamada kapsam dışıdır.

## Çıkarılan Veri

Her satırdan işlem tarihi, fiş no, evrak tarihi, evrak no, çek no, banka, vade tarihi, tutar, açıklama, kaynak sayfa ve parse uyarısı alanları çıkarılır. Hareket tipi enum olarak `RECEIVED_CHECK` üretilir.

Banka isimleri yaygın varyasyonlardan normalize edilir:

- Halkbank
- Denizbank
- Ziraat Bankası
- Garanti BBVA
- Yapı Kredi
- İş Bankası
- Akbank
- QNB Finansbank

## CLI Kullanımı

Bağımlılıkları kur:

```bash
pip install -r statement_extractor/requirements.txt
```

PDF'ten Excel üret:

```bash
python statement_extractor/main.py input.pdf output.xlsx
```

Deneme PDF'lerini `statement_extractor/uploads/` klasörüne koyabilirsin:

```bash
python statement_extractor/main.py statement_extractor/uploads/ekstre.pdf
```

Output verilmezse her çalıştırmada yeni bir dosya oluşturulur:

`statement_extractor/outputs/cekler_vadeye_gore_detayli_YYYYMMDD_HHMMSS.xlsx`

Opsiyonel parametreler:

```bash
python statement_extractor/main.py input.pdf --today 2026-05-03
python statement_extractor/main.py input.pdf --json-output statement_extractor/outputs/parse_result.json
python statement_extractor/main.py input.pdf --no-excel
python statement_extractor/main.py input.pdf --include-overdue-in-value-calc
```

Örnek terminal çıktısı:

```text
10 çek bulundu.
Toplam çek tutarı: 12.250.000,00 TL
En erken vade: 30.04.2026
En geç vade: 30.09.2026
Excel oluşturuldu: statement_extractor/outputs/cekler_vadeye_gore_detayli_20260503_175245.xlsx
```

## Watch Mode

PDF dosyalarını otomatik işlemek için `statement_extractor/input/` klasörünü izleyen watcher kullanılabilir:

```bash
python statement_extractor/watcher.py --input-dir statement_extractor/input --output-dir statement_extractor/outputs
```

Referans tarih vermek için:

```bash
python statement_extractor/watcher.py --input-dir statement_extractor/input --output-dir statement_extractor/outputs --today 2026-05-03
```

Watcher sadece `.pdf` dosyalarını işler. `.DS_Store`, gizli dosyalar, geçici dosyalar ve yarım yazılmış dosyalar görmezden gelinir. Dosya eklendiğinde veya güncellendiğinde kısa süre beklenir, aynı dosyaya ait peş peşe event'ler tek işleme düşürülür ve rapor timestamp ile `statement_extractor/outputs/` klasörüne yazılır:

`cek_raporu_EKREM_YENI_CARI_2026-05-03_18-45-12.xlsx`

Başlangıçta klasördeki mevcut PDF'leri de işlemek için:

```bash
python statement_extractor/watcher.py --process-existing
```

Vadesi geçmiş çekler varsayılan olarak ağırlıklı ortalama vade hesabına dahil edilmez. Dahil etmek için:

```bash
python statement_extractor/watcher.py --include-overdue-in-value-calc
```

Watcher logları `statement_extractor/logs/` altında günlük dosyaya yazar.

## Çift Upload ve Konsolide Takip

Yeni ERP akışında yüklenen her dosya için ayrı Excel çıktısı üretmek yerine, veriler PostgreSQL hedefli ortak çek kayıtlarına dönüştürülür. Kullanıcıya tek rapor gerektiğinde DB'deki kayıtlar konsolide edilerek tek Excel oluşturulur.

Klasörler:

- `statement_extractor/uploads/excel/`: Kullanıcının yüklediği çek listesi Excel dosyaları.
- `statement_extractor/uploads/images/`: JPG/PNG çek görüntüleri.
- `statement_extractor/ocr_drafts/`: OCR sonrası kontrol edilecek taslak JSON çıktıları.
- `statement_extractor/outputs/`: Tek konsolide rapor ve manuel inceleme çıktıları.

PostgreSQL için `DATABASE_URL` tanımlı olmalıdır:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
```

Migration önerileri:

- `backend/migrations/001_statement_checks.sql`
- `backend/migrations/002_check_import_sessions.sql`

Excel upload dosyalarını PostgreSQL'e aktarmak için:

```bash
python3 statement_extractor/import_excel_uploads.py --input-dir statement_extractor/uploads/excel
```

Her çalıştırma yeni bir `check_import_sessions` kaydı oluşturur. Dosyadaki tüm satırlar `check_import_rows` içinde saklanır. Aynı çek daha önce ana `checks` tablosunda varsa tekrar ana listeye eklenmez; yeni yükleme satırı `duplicate_of_check_id` ile eski çekten ayrıştırılır.

DB'ye yazmadan sadece Excel'leri okuyup kontrol etmek için:

```bash
python3 statement_extractor/preview_excel_uploads.py --input-dir statement_extractor/uploads/excel --excel-output statement_extractor/outputs/excel_preview.xlsx
```

Ekstreleri tek adımda parse edip müşteri bazlı ödeme/hareket ve çek raporu üretmek için:

```bash
python3 statement_extractor/create_customer_report.py --input-dir statement_extractor/uploads/excel --output statement_extractor/outputs/musteri_bazli_odeme_cek_raporu.xlsx
```

Bu rapor önce ekstreleri parse eder, sonra verileri Excel'de şu sayfalarda gösterir:

- `Müşteri Özeti`
- `Müşteri Bazlı Hareketler`
- `Müşteri Bazlı Çekler`

Görüntü dosyalarını OCR ile taslak kayda dönüştürüp PostgreSQL'e aktarmak için:

```bash
python3 statement_extractor/import_image_uploads.py --input-dir statement_extractor/uploads/images
```

OCR için Python paketlerine ek olarak sistemde Tesseract binary gerekir. macOS için örnek:

```bash
brew install tesseract tesseract-lang
```

OCR kayıtları varsayılan olarak `NEEDS_REVIEW` durumunda kaydedilir. Bu kayıtlar kullanıcının kontrolünden sonra onaylanmalıdır.

DB'deki çeklerden tek konsolide rapor üretmek için:

```bash
python3 statement_extractor/export_consolidated_checks.py --output statement_extractor/outputs/all_checks.xlsx
```

Taslak/OCR kayıtlarını da rapora dahil etmek için:

```bash
python3 statement_extractor/export_consolidated_checks.py --include-drafts
```

Konsolide rapor sayfaları:

- `Tüm Çekler`
- `Cari Bazlı Özet`
- `Banka Özeti`
- `Vade Takvimi`
- `Değer Hesabı`
- `Kaynak ve Kontrol Geçmişi`

Bu yapı ileride cari hesap ekranında her çekin hangi kaynaktan geldiğini, OCR/Excel/PDF sonrası kullanıcı tarafından nasıl kontrol edildiğini ve import session geçmişini göstermeye hazırlanmıştır.

## Taslak Excel Doğrulama

JPEG gibi manuel okunan çekler için oluşturulan taslak Excel dosyası güncellendikçe doğrulanabilir:

```bash
python3 statement_extractor/watch_excel_draft.py statement_extractor/outputs/jpeg_cek_taslak.xlsx
```

Bu komut dosyayı izler. Excel'i güncelleyip kaydettiğinde:

- `Doğrulama Durumu` ve `Doğrulama Notu` kolonlarını günceller.
- `Doğrulama Özeti` sayfasını yeniden oluşturur.
- Eksik çek no, banka, vade tarihi, tutar ve duplicate kayıtları işaretler.
- Dosyayı tekrar açar.

Tek sefer doğrulama için:

```bash
python3 statement_extractor/watch_excel_draft.py statement_extractor/outputs/jpeg_cek_taslak.xlsx --once
```

Snapshot ve fark raporu da üretmek için:

```bash
python3 statement_extractor/watch_excel_draft.py statement_extractor/outputs/jpeg_cek_taslak.xlsx --with-snapshot-diff
```

İlk çalıştırmada sadece ilk snapshot alınır. Sonraki kayıtlarda son snapshot ile güncel Excel karşılaştırılır, diff raporu üretilir ve yeni snapshot saklanır.

## Snapshot ve Excel Versiyon Karşılaştırma

Snapshot sistemi, PDF/JPEG'den çıkarılan ilk taslak Excel ile kullanıcının sonradan manuel düzelttiği Excel arasındaki farkları audit izi olarak saklamak için tasarlanmıştır. Bu sadece Excel farkı bulmak için değil, ileride ERP'de “kullanıcı OCR/PDF sonucu üzerinde hangi düzeltmeleri yaptı?” sorusuna cevap vermek için kullanılacaktır.

Klasörler:

- `statement_extractor/snapshots/`: timestamp'li Excel kopyaları ve JSON metadata dosyaları.
- `statement_extractor/diff_reports/`: Excel fark raporları.

Tek sefer iki Excel karşılaştırmak için:

```bash
python3 statement_extractor/compare_excel_versions.py old.xlsx new.xlsx --output statement_extractor/diff_reports/report.xlsx
```

Output verilmezse rapor otomatik adla yazılır:

`statement_extractor/diff_reports/diff_report_<source>_YYYYMMDD_HHMMSS.xlsx`

Diff raporu sayfaları:

- `Fark Özeti`: eski/yeni toplamlar, tutar farkı, eklenen/silinen/değişen/değişmeyen satır sayıları.
- `Değişen Satırlar`: değişen alan, eski değer ve yeni değer.
- `Eklenen Satırlar`: yeni Excel'de olup eski snapshot'ta olmayan satırlar.
- `Silinen Satırlar`: eski snapshot'ta olup yeni Excel'de olmayan satırlar.
- `Tüm Karşılaştırma`: her satır için diff tipi ve değişiklik özeti.

Satır eşleştirme önceliği:

1. `Çek No`
2. `Banka + Vade Tarihi + Tutar`
3. `row_index`

Diff raporunda kullanılan identity yöntemi ayrıca yazılır. Karşılaştırılan alanlar: `Çek No`, `Banka`, `Vade Tarihi`, `Vadeye Kalan Gün`, `Tutar`, `Lehtar`, `Keşideci`, `Açıklama`, `Doğrulama Durumu`, `Doğrulama Notu`.

Cari hesap entegrasyonunda snapshot/diff kayıtları şu alanlarla ilişkilendirilebilir:

- `account_code`
- `account_name`
- `company_name`
- `source_file`
- `import_session_id`
- `original_snapshot_id`
- `corrected_snapshot_id`
- `diff_report_id`

## Excel Çıktısı

Excel dosyasında şu sayfalar oluşturulur:

- `Çek Listesi`: vadeye göre sıralı kayıtlar, vade durumu, haftalık periyot ve toplam satırı.
- `Özet`: firma, hesap, toplam tutar, vade aralığı ve uyarı sayısı.
- `Banka Özeti`: banka bazında adet, toplam, ortalama ve vade aralığı.
- `Vade Takvimi`: ay ve hafta bazında vade toplamları.
- `Değer Hesabı`: `Vadeye Kalan Gün × Tutar` üzerinden ağırlıklı ortalama vade hesabı.
- `Parse Debug`: ham satır, bulunan alanlar, kullanılan tutar ve uyarılar.

Başlıklar renklidir, filtre açıktır, ilk satır dondurulur, TL ve tarih formatları uygulanır. Vadesi geçmiş ve parse uyarısı olan kayıtlar ayrıca renklendirilir.

## FastAPI Akışı

Router dosyası: `backend/app/routers/statement_checks.py`

Mevcut FastAPI uygulamasına eklemek için uygulama başlangıcında router dahil edilmelidir:

```python
from backend.app.routers.statement_checks import router as statement_checks_router

app.include_router(statement_checks_router)
```

Endpoint'ler:

- `POST /api/statements/checks/preview`: PDF dosyasını `multipart/form-data` ile alır, geçici dosyada işler, DB'ye yazmadan JSON preview döner.
- `POST /api/statements/checks/import`: Kullanıcının onayladığı/düzelttiği `CheckRecord` listesini alır. Mevcut DB katmanı olmadığı için repository arayüzü hazırdır; PostgreSQL entegrasyonu bağlanınca duplicate kontrolüyle kayıt yapar.
- `POST /api/statements/checks/export-excel`: Preview veya import edilmiş kayıt listesinden indirilebilir `.xlsx` döner.

Önce preview, sonra import yapılmasının sebebi kullanıcının çek no, banka, vade tarihi, tutar ve açıklama alanlarını kontrol edip düzeltebilmesidir. Bu sayede PDF parser hataları doğrudan PostgreSQL'e kalıcı yazılmaz.

## PostgreSQL Tasarımı

Mevcut migration sistemi bulunamadığı için öneri SQL dosyası `backend/migrations/001_statement_checks.sql` içine eklendi. İlk statü `PORTFOLIO` olarak tasarlanmıştır.

Duplicate kontrol anahtarı:

- `account_name`
- `check_no`
- `bank`
- `maturity_date`
- `amount`

## Parser Limitleri

- Sadece text extraction yapılır, OCR yoktur.
- İlk sürüm sadece `ALINAN ÇEK` hareketlerini işler.
- Çek no veya vade tarihi bulunamazsa kayıt oluşturulmaz, warning listesine eklenir.
- Tutar bulunamazsa kayıt oluşturulur ancak `parse_warning` dolar.
- PDF tablosu çok bozuk veya satırlar PDF extraction sırasında parçalanmışsa manuel düzeltme gerekebilir.

## ERP'ye Bağlantı

Modülün ana giriş noktaları `statement_extractor/src/service.py` içindedir:

- `extract_checks_from_pdf(pdf_path, today=None)`
- `create_excel_from_parse_result(parse_result, output_path, today=None)`

Bu fonksiyonlar hem CLI hem FastAPI tarafından kullanılabilir. İleride çek/tahsilat modülüne bağlanırken `CheckRecord` modeli doğrudan editable preview tabloya, import servisindeki repository arayüzü de mevcut PostgreSQL/ORM katmanına bağlanmalıdır.
