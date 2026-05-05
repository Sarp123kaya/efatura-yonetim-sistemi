# Proje Yapısı

Bu doküman, temizlenmiş klasör mimarisinin güncel halini özetler.

## Ana Klasörler

```text
.
├── backend/                 # Aktif agent ve ortak backend kodları
│   ├── agents/              # incoming_agent.py, outgoing_agent.py
│   └── core/                # config, db, state, normalize, logging, XML cache
├── ingestion/               # İşbaşı API extractor modülleri
├── scripts/                 # Güncel operasyon, rapor ve bakım scriptleri
├── sql/                     # Güncel PostgreSQL schema ve migration dosyaları
│   └── archive/             # Eski SQL baseline dosyaları
├── docs/                    # Güncel rehberler ve teknik dokümanlar
│   └── archive/             # Tarihi changelog/complete/not dosyaları
├── archive/                 # Legacy kod ve eski araçlar
│   ├── legacy_src/          # Eski src kodları
│   └── legacy_tools/        # Eski SQLite/Excel matcher aracı
├── local_archive/           # Silinmeyen yerel çıktı yedekleri; Git dışında
├── data/                    # Yerel/generate edilen DB, XML, log alanları
└── kayıtlar/                # Oluşturulan Excel raporları
```

## Aktif Kod Alanları

### `backend/`

Stateful PostgreSQL ingestion sisteminin ana paketidir. Agent dosyaları API extractorları çağırır, veriyi normalize eder ve PostgreSQL’e yazar.

Önemli dosyalar:

- `backend/agents/incoming_agent.py`
- `backend/agents/outgoing_agent.py`
- `backend/core/db.py`
- `backend/core/config.py`
- `backend/core/agent_state.py`
- `backend/core/normalize.py`
- `backend/core/incoming_xml_cache.py`

### `ingestion/`

İşbaşı API ile konuşan extractor kodlarıdır. Bu klasör aktif pipeline tarafından kullanılmaya devam eder.

Önemli not: `ingestion/api_data_extractor.py` ve `ingestion/api_incoming_invoices_extractor.py`, `archive/legacy_src/api_database.py` dosyasını import eder. Bu yüzden o dosya legacy klasörde olsa bile silinmemelidir.

### `scripts/`

Güncel çalıştırılabilir komutlar burada durur.

- `run_invoice_pipeline.py`: ana uçtan uca akış
- `pg_invoice_matcher.py`: PostgreSQL tabanlı eşleştirme
- `pg_reverse_matcher.py`: gelen -> giden ters kontrol
- `export_supplier_invoice_details.py`: AK GIPS/FULLBOARD ürün detay Excel raporları
- `export_to_excel.py`: genel Excel export
- `setup_postgres.sh`: DB kurulum scripti
- `verify_installation.py`: kurulum doğrulama

Eski SQLite matcher artık `archive/legacy_tools/` altındadır.

### `sql/`

Güncel kurulum sırası:

1. `sql/stateful_ingestion_schema_v2.sql`
2. `sql/migration_v2.2_despatch_improvements.sql`
3. `sql/migration_irsaliye_override.sql`
4. `sql/migration_incoming_xml_cache.sql`

Opsiyonel fabrika kâr akışı için `sql/migration_factory_kar.sql` kullanılır.

Eski baseline dosyaları `sql/archive/` altındadır:

- `sql/archive/postgres_schema.sql`
- `sql/archive/stateful_ingestion_schema.sql`

## Doküman Alanları

Güncel rehberler `docs/` altında toplanmıştır:

- `docs/KOMUTLAR.md`
- `docs/YENI_BILGISAYAR_KURULUM_REHBERI.md`
- `docs/TROUBLESHOOTING.md`
- `docs/TEMIZLIK_ANALIZI.md`
- `docs/ADVANCED_MONITORING.md`
- `docs/AGENT_RUN_LOGGING.md`

Tarihi veya tamamlandı notları `docs/archive/` altında tutulur.

## Yerel Çıktılar

Aşağıdaki alanlar çalışma sırasında oluşur ve Git’e eklenmez:

- `data/`
- `kayıtlar/`
- `.env`
- `*.db`, `*.sqlite*`
- `*.log`
- XML ve Excel çıktıları

Bu dosyalar kullanıcı verisi içerebileceği için otomatik silinmez; temizlikte `local_archive/` altına alınır.
