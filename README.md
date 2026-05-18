# Gelen E-Faturalar Yönetim Sistemi

Bu proje, İşbaşı API üzerinden gelen ve giden e-faturaları PostgreSQL veritabanına aktarır, irsaliye kodlarına göre eşleştirir ve Excel raporları üretir.

## Hızlı Başlangıç

```bash
pip install -r requirements.txt
cp env.example .env
./scripts/setup_postgres.sh
python3 scripts/run_invoice_pipeline.py
```

Ana çıktı dosyaları varsayılan olarak `kayıtlar/` klasörüne yazılır.

## Web Panel

CLI komutlarını tarayıcıdan job olarak çalıştırmak için Flask tabanlı web panel eklenmiştir.

```bash
flask --app backend.web.app run --host 127.0.0.1 --port 8000
python3 scripts/run_web_worker.py
```

Panel; pipeline başlatma, Excel rapor üretme, job loglarını izleme ve `kayıtlar/` altındaki raporları indirme ekranları sağlar. VPS/Docker/systemd kurulum detayları için `docs/WEB_PANEL.md` dosyasına bakın.

## Güncel Komutlar

```bash
# Gelen/giden faturaları çek, DB’ye aktar ve normal + ters eşleştirme raporlarını üret
python3 scripts/run_invoice_pipeline.py

# Sadece mevcut DB verisiyle normal + ters eşleştirme Excel’lerini üret
python3 scripts/run_invoice_pipeline.py --skip-ingest

# Tam paket: eşleştirme + ters eşleştirme + Gelen/Giden listeleri + Agent + AK GIPS & FULLBOARD + müşteri ürün fiyat
python3 scripts/run_invoice_pipeline.py --all-excel

# İlk kurulum veya XML cache tam yenileme ile tam paket
python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml --all-excel

# AK GIPS ve FULLBOARD ürün detay Excel’lerini üret
python3 scripts/export_supplier_invoice_details.py

# Müşteri bazlı giden fatura ürün/fiyat Excel’ini üret
python3 scripts/export_customer_product_prices.py

# Tüm DB verilerini Excel’e aktar
python3 scripts/export_to_excel.py --type all
```

Daha fazla komut için `docs/KOMUTLAR.md`, yeni bilgisayar kurulumu için `docs/YENI_BILGISAYAR_KURULUM_REHBERI.md` dosyasına bakın.

## Proje Yapısı

```text
.
├── backend/                 # Aktif agent ve ortak backend kodları
├── ingestion/               # İşbaşı API extractor modülleri
├── scripts/                 # Güncel çalıştırılabilir bakım/rapor/pipeline scriptleri
├── sql/                     # Güncel PostgreSQL schema ve migration dosyaları
│   └── archive/             # Eski SQL baseline dosyaları
├── docs/                    # Güncel rehberler ve teknik dokümanlar
│   └── archive/             # Tarihi changelog/complete/kurulum notları
├── archive/                 # Legacy kod ve eski araçlar
│   ├── legacy_src/          # Eski src kodları; api_database.py hâlâ aktif import ediliyor
│   └── legacy_tools/        # Eski SQLite/Excel matcher aracı
├── data/                    # Yerel DB/XML/log alanı; Git dışında
└── kayıtlar/                # Oluşturulan Excel raporları; Git dışında
```

Detaylı yapı açıklaması için `docs/PROJECT_STRUCTURE.md` dosyasına bakın.

## Aktif Pipeline

Canlı akış PostgreSQL tabanlıdır:

```text
scripts/run_invoice_pipeline.py
  -> backend/agents/incoming_agent.py
  -> backend/agents/outgoing_agent.py
  -> ingestion/*
  -> PostgreSQL
  -> scripts/pg_invoice_matcher.py
```

`archive/legacy_src/api_database.py` dosyası adı legacy olsa da `ingestion/*` tarafından import edildiği için korunur.

## Veritabanı Kurulumu

Önerilen kurulum:

```bash
./scripts/setup_postgres.sh
```

Manuel sıra:

```bash
psql "$DB_URL" -f sql/stateful_ingestion_schema_v2.sql
psql "$DB_URL" -f sql/migration_v2.2_despatch_improvements.sql
psql "$DB_URL" -f sql/migration_irsaliye_override.sql
psql "$DB_URL" -f sql/migration_incoming_xml_cache.sql
psql "$DB_URL" -f sql/migration_outgoing_xml_cache.sql
```

Opsiyonel fabrika kâr akışı için `sql/migration_factory_kar.sql`, `scripts/sync_factory_kar.py` ve `scripts/export_fabrikalar.py` kullanılır.

## Yerel Çıktılar

`data/`, `kayıtlar/`, `.env`, `.db`, `.log`, XML ve Excel çıktıları Git’e eklenmez. Temizlik sırasında eski yerel çıktılar silinmeden `local_archive/` altına taşınır; bu klasör de Git dışında kalır.

## Faydalı Rehberler

- `QUICKSTART.md`: kısa kurulum ve ilk çalıştırma
- `docs/KOMUTLAR.md`: tüm operasyon komutları
- `docs/WEB_PANEL.md`: web panel ve VPS dağıtım rehberi
- `docs/PROJECT_STRUCTURE.md`: klasör mimarisi
- `docs/TROUBLESHOOTING.md`: hata çözüm notları
- `docs/TEMIZLIK_ANALIZI.md`: aktif/legacy dosya ayrımı
