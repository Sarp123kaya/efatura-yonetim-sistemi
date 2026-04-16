# Komutlar

Projedeki tüm çalıştırılabilir komutların referans rehberi.

**Son Güncelleme:** 19 Şubat 2026

---

## Veri Çekme (API Agent'ları)

Bu komutlar İşbaşı API'sine bağlanıp faturaları PostgreSQL veritabanına kaydeder. Çalıştırıldığında API şifresi sorulur.

### Gelen Faturaları Çek

```bash
python3 backend/agents/incoming_agent.py
```

2026-01-01'den bugüne kadar olan gelen faturaları (AK GİPS, FULLBOARD vb.) API'den çeker. XML'den irsaliye bilgilerini parse eder, IRS-XXXXX formatında normalize eder ve `incoming_invoices` tablosuna yazar. İlk çalışmada tüm faturaları çeker, sonraki çalışmalarda sadece son tarihten itibaren yeni/değişenleri alır.

### Giden Faturaları Çek

```bash
python3 backend/agents/outgoing_agent.py
```

Giden faturaları (müşterilere kesilen) API'den çeker. Description alanından irsaliye kodlarını regex ile çıkarır, IBAN/banka bilgilerini temizler ve `outgoing_invoices` tablosuna yazar. PURCHASE_INVOICE tipindeki kayıtları otomatik filtreler.

### Her İkisini Sırayla Çalıştır

```bash
python3 backend/agents/incoming_agent.py && python3 backend/agents/outgoing_agent.py
```

Önce gelen, ardından giden faturaları çeker. `&&` sayesinde ilk komut başarılı olursa ikincisi çalışır.

---

## Excel Çıktıları

### Tüm Verileri Excel'e Aktar

```bash
python3 scripts/export_to_excel.py --type all
```

3 ayrı Excel dosyası oluşturur:
- `kayıtlar/Gelen_Faturalar_YYYYMMDD_HHMMSS.xlsx` - Gelen faturalar (tedarikçi, tutar, irsaliye kodları, tarih)
- `kayıtlar/Giden_Faturalar_YYYYMMDD_HHMMSS.xlsx` - Giden faturalar (firma, tutar, irsaliye kodları, tarih)
- `kayıtlar/Agent_Calismalari_YYYYMMDD_HHMMSS.xlsx` - Agent çalışma geçmişi (süre, eklenen/güncellenen sayılar)

### Sadece Gelen Faturaları Aktar

```bash
python3 scripts/export_to_excel.py --type incoming
```

### Sadece Giden Faturaları Aktar

```bash
python3 scripts/export_to_excel.py --type outgoing
```

### Sadece Agent Çalışma Geçmişini Aktar

```bash
python3 scripts/export_to_excel.py --type runs
```

### Çıktı Klasörünü Değiştir

```bash
python3 scripts/export_to_excel.py --type all --output-dir rapor_ciktilari
```

Varsayılan çıktı klasörü `kayıtlar/` dizinidir.

---

## Fatura Eşleştirme

### PostgreSQL Tabanlı Eşleştirme (Önerilen)

```bash
python3 scripts/pg_invoice_matcher.py
```

Giden faturaların irsaliye kodları (`irsaliye_codes`) ile gelen faturaların irsaliye kodlarını (`despatch_ids`) PostgreSQL üzerinden eşleştirir. Renk kodlu Excel raporu üretir:
- **Yeşil**: Eşleşen faturalar
- **Kırmızı**: İrsaliye kodu var ama gelen faturada karşılığı bulunamayan
- **Sarı**: İrsaliye kodu olmayan giden faturalar

Raporda fark tutarları ve istatistik özeti de yer alır. Çıktı: `kayıtlar/Fatura_Eslestirme_YYYYMMDD_HHMMSS.xlsx`

### Ters Eşleştirme: Gelen -> Giden Kontrol

```bash
python3 scripts/pg_reverse_matcher.py
```

Yukarıdaki eşleştirmenin tam tersi: **gelen faturaları** başlangıç noktası alır, her gelen faturanın irsaliye kodunu giden faturalarda arar. Karşılıksız gelen faturaları tespit eder. Renk kodlu Excel raporu üretir:
- **Yeşil**: Giden faturada karşılığı bulunan
- **Kırmızı**: Karşılıksız (gelen var ama giden yok)
- **Sarı**: İrsaliye kodu olmayan gelen faturalar

Çıktı: `kayıtlar/Ters_Eslestirme_YYYYMMDD_HHMMSS.xlsx`

---

## Fabrikalar Sayfası

Eşleşen faturalardaki kar (Fark TL) tutarlarını fabrika bazında (A=AK GİPS, F=FULLBOARD, T=TERMATECH) saklar ve toplam alacak raporu üretir.

### Ön Koşul: Migration

```bash
psql -d invoices -f sql/migration_factory_kar.sql
```

`factory_A_kar`, `factory_F_kar`, `factory_T_kar` tablolarını oluşturur.

### Fabrika Kar Senkronizasyonu

```bash
python3 scripts/sync_factory_kar.py
```

Fatura eşleştirmedeki "Eşleşti" satırlarını alır, irsaliye prefix'ine göre ilgili fabrika tablosuna upsert eder. Matcher çalıştırıldıktan sonra veya bağımsız çalıştırılabilir.

### Fabrikalar Excel Raporu

```bash
python3 scripts/export_fabrikalar.py
```

Her fabrika için ayrı sayfa (geçmişten bugüne sıralı) ve toplam alacak özeti içeren Excel raporu oluşturur. Çıktı: `kayıtlar/Fabrikalar_YYYYMMDD_HHMMSS.xlsx`

### Önerilen Akış

```bash
python3 scripts/pg_invoice_matcher.py && python3 scripts/sync_factory_kar.py && python3 scripts/export_fabrikalar.py
```

1. Eşleştirme raporu üret
2. Fabrika tablolarını güncelle
3. Fabrikalar Excel raporunu oluştur

---

## İrsaliye Kodu Düzeltme

Fatura açıklamasında yanlış girilen irsaliye kodlarını (örn. A-064 yerine F-064 olması gereken) kalıcı olarak düzeltir. Düzeltme `irsaliye_codes_override` kolonuna yazılır; agent çalıştığında silinmez.

### Tek Kod Düzeltme

```bash
python3 scripts/correct_irsaliye.py --invoice DKE2026000000005 --from A-00064 --to F-00064
```

- `--invoice`: Fatura no veya id (DKE2026000000005 gibi)
- `--from`: Yanlış kod (A-00064)
- `--to`: Doğru kod (F-00064)

Format: `A-00064`, `F-00956` (5 haneli zero-pad). Kısa format da kabul edilir: `A-64` otomatik `A-00064` olur.

### Override'ı Kaldır

```bash
python3 scripts/correct_irsaliye.py --invoice DKE2026000000005 --clear
```

Override silinir; eşleştirme ve export tekrar API'den çekilen (extracted) kodu kullanır.

### Mevcut Durumu Göster

```bash
python3 scripts/correct_irsaliye.py --invoice DKE2026000000005 --show
```

Extracted, override ve kullanılan (effective) irsaliye kodlarını gösterir.

### Eski Eşleştirme (SQLite + Excel Tabanlı)

```bash
python3 scripts/tools/invoice_matcher.py
```

Eski sistemle çalışır: `data/excel/api/API_Giden_Faturalar.xlsx` dosyasından giden faturaları, `data/db/akgips.db` ve `data/db/fullboard.db` SQLite veritabanlarından gelen faturaları okur. PostgreSQL yerine dosya tabanlı eşleştirme yapar. Yeni sistem kurulduktan sonra `pg_invoice_matcher.py` tercih edilmelidir.

---

## Veritabanı Görüntüleme

### Tüm Verileri Terminal'de Gör

```bash
python3 view_data.py
```

İstatistikler, agent çalışmaları, gelen ve giden faturaları terminal'de tablo formatında gösterir.

### Sadece İstatistikler

```bash
python3 view_data.py --type stats
```

Toplam fatura sayıları, eklenen/güncellenen kayıt sayıları.

### Sadece Gelen Faturalar

```bash
python3 view_data.py --type incoming --limit 20
```

Son 20 gelen faturayı gösterir. `--limit` ile gösterilecek kayıt sayısı ayarlanır.

### Sadece Giden Faturalar

```bash
python3 view_data.py --type outgoing --limit 20
```

### Agent Çalışma Geçmişi

```bash
python3 view_data.py --type runs
```

Her agent çalışmasının başlangıç zamanı, süresi, kaç kayıt eklediği/güncellediği, hata sayısı ve durumunu gösterir.

---

## Monitoring ve Agent İzleme

### Son Çalışmaları Gör

```bash
python3 scripts/agent_monitor.py --command recent --limit 10
```

### Agent Bazlı İstatistik

```bash
python3 scripts/agent_monitor.py --command stats --agent incoming_agent --days 30
```

Son 30 günde incoming_agent'ın toplam çalışma istatistiklerini gösterir.

### Sağlık Kontrolü

```bash
python3 scripts/agent_monitor.py --command health --agent incoming_agent
```

Agent'ın son çalışma zamanını ve durumunu kontrol eder.

---

## Veritabanı Yönetimi

### PostgreSQL'e Bağlan (SQL Sorguları İçin)

```bash
psql postgresql://sp383@localhost:5432/invoices
```

İnteraktif SQL terminali açar. Doğrudan sorgu yazabilirsiniz. Çıkmak için `\q`.

### Faydalı SQL Sorguları

```bash
# Kayıt sayıları
psql postgresql://sp383@localhost:5432/invoices -c "SELECT COUNT(*) FROM incoming_invoices;"
psql postgresql://sp383@localhost:5432/invoices -c "SELECT COUNT(*) FROM outgoing_invoices;"

# Agent durumu
psql postgresql://sp383@localhost:5432/invoices -c "SELECT agent_name, last_issue_date, last_run_at FROM agent_state;"

# Son agent çalışmaları
psql postgresql://sp383@localhost:5432/invoices -c "SELECT agent_name, status, insert_count, update_count, duration_sec FROM agent_runs ORDER BY start_time DESC LIMIT 5;"

# Tedarikçi bazlı dağılım
psql postgresql://sp383@localhost:5432/invoices -c "SELECT supplier, COUNT(*) as sayi, SUM(amount)::numeric(18,2) as toplam FROM incoming_invoices GROUP BY supplier ORDER BY toplam DESC;"

# Eşleşen faturaları doğrudan SQL ile gör
psql postgresql://sp383@localhost:5432/invoices -c "
SELECT o.invoice_no, LEFT(o.firm_name, 25), code.val, i.invoice_id, LEFT(i.supplier, 25), o.total_tl - i.amount as fark
FROM outgoing_invoices o
CROSS JOIN LATERAL jsonb_array_elements_text(o.irsaliye_codes) AS code(val)
JOIN incoming_invoices i ON i.despatch_ids @> jsonb_build_array(code.val)
ORDER BY o.issue_date DESC;"
```

### Agent State Sıfırla (Tüm Verileri Tekrar Çek)

```bash
psql postgresql://sp383@localhost:5432/invoices -c "UPDATE agent_state SET last_issue_date = '2026-01-01 00:00:00' WHERE agent_name IN ('incoming_agent', 'outgoing_agent');"
```

Agent'ların son tarihini sıfırlar. Bir sonraki çalışmada tüm faturalar baştan çekilir ve hash karşılaştırması ile güncelleme yapılır.

### PostgreSQL Durumunu Kontrol Et

```bash
pg_isready
```

PostgreSQL sunucusunun çalışıp çalışmadığını kontrol eder.

---

## Kurulum ve Doğrulama

### Kurulum Doğrulama

```bash
python3 scripts/verify_installation.py
```

Modül importları, konfigürasyon, normalizasyon fonksiyonları ve veritabanı bağlantısını test eder.

### Veritabanı Kurulumu (İlk Sefer)

```bash
createdb invoices
psql postgresql://sp383@localhost:5432/invoices -f sql/stateful_ingestion_schema_v2.sql
psql postgresql://sp383@localhost:5432/invoices -f sql/migration_v2.2_despatch_improvements.sql
psql postgresql://sp383@localhost:5432/invoices -f sql/migration_irsaliye_override.sql
```

Sırasıyla: veritabanını oluşturur, ana schema'yı uygular (4 tablo), v2.2 despatch iyileştirmelerini uygular, irsaliye override kolonunu ekler.

### Otomatik Veritabanı Kurulumu

```bash
./scripts/setup_postgres.sh
```

Yukarıdaki adımları otomatik yapar: `.env` kontrolü, bağlantı testi, schema migration, tablo doğrulaması.

### Bağımlılıkları Kur

```bash
pip install -r requirements.txt
```

### v2.2 Testlerini Çalıştır

```bash
python3 scripts/test_v2.2_despatch_improvements.py
```

Despatch normalizasyonu, IBAN temizleme ve irsaliye çıkarma fonksiyonlarının doğru çalıştığını test eder.

---

## Otomasyon (Cron Job)

### Crontab Düzenle

```bash
crontab -e
```

### Örnek Cron Tanımları

```cron
# Her gün saat 02:00'de gelen faturaları çek
0 2 * * * cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası" && /usr/bin/python3 backend/agents/incoming_agent.py >> /tmp/incoming_agent.log 2>&1

# Her gün saat 03:00'de giden faturaları çek
0 3 * * * cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası" && /usr/bin/python3 backend/agents/outgoing_agent.py >> /tmp/outgoing_agent.log 2>&1

# Her gün saat 04:00'de eşleştirme raporu oluştur
0 4 * * * cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası" && /usr/bin/python3 scripts/pg_invoice_matcher.py >> /tmp/matcher.log 2>&1
```

Cron ile otomatik çalıştırma için `.env` dosyasında `ISBASI_PASSWORD` alanının doldurulması gerekir, aksi halde agent şifre sorar ve cron'da takılır.

### Cron Loglarını İzle

```bash
tail -f /tmp/incoming_agent.log
tail -f /tmp/outgoing_agent.log
```

---

## Hızlı Referans

| Ne Yapmak İstiyorsun? | Komut |
|------------------------|-------|
| Gelen faturaları çek | `python3 backend/agents/incoming_agent.py` |
| Giden faturaları çek | `python3 backend/agents/outgoing_agent.py` |
| Excel'e aktar | `python3 scripts/export_to_excel.py --type all` |
| Eşleştirme raporu | `python3 scripts/pg_invoice_matcher.py` |
| İrsaliye kodu düzelt | `python3 scripts/correct_irsaliye.py --invoice X --from A-00064 --to F-00064` |
| Override durumunu gör | `python3 scripts/correct_irsaliye.py --invoice X --show` |
| Terminal'de verileri gör | `python3 view_data.py` |
| İstatistikleri gör | `python3 view_data.py --type stats` |
| Agent izleme | `python3 scripts/agent_monitor.py --command recent` |
| SQL terminali | `psql postgresql://sp383@localhost:5432/invoices` |
| Agent state sıfırla | `psql ... -c "UPDATE agent_state SET last_issue_date = '2026-01-01'..."` |
| PostgreSQL durumu | `pg_isready` |
| Kurulum doğrulama | `python3 scripts/verify_installation.py` |
