# Temizlik Analizi

Bu doküman, projede aktif kullanılan dosyaları ve arşivlenen/eski kabul edilen alanları gösterir.

## Aktif Sistem

Ana akış PostgreSQL tabanlıdır:

```bash
python3 scripts/run_invoice_pipeline.py
```

Fabrika ürün detay Excel’leri için:

```bash
python3 scripts/export_supplier_invoice_details.py
```

Aktif akışın ana dosyaları:

- `scripts/run_invoice_pipeline.py`
- `backend/agents/incoming_agent.py`
- `backend/agents/outgoing_agent.py`
- `ingestion/api_incoming_invoices_extractor.py`
- `ingestion/api_data_extractor.py`
- `backend/core/db.py`
- `backend/core/config.py`
- `backend/core/agent_state.py`
- `backend/core/normalize.py`
- `backend/core/agent_run_logger.py`
- `backend/core/incoming_xml_cache.py`
- `scripts/pg_invoice_matcher.py`
- `scripts/pg_reverse_matcher.py`
- `scripts/export_supplier_invoice_details.py`
- `scripts/export_to_excel.py`

Aktif SQL sırası:

1. `sql/stateful_ingestion_schema_v2.sql`
2. `sql/migration_v2.2_despatch_improvements.sql`
3. `sql/migration_irsaliye_override.sql`
4. `sql/migration_incoming_xml_cache.sql`

Opsiyonel fabrika kâr akışı:

- `sql/migration_factory_kar.sql`
- `scripts/sync_factory_kar.py`
- `scripts/export_fabrikalar.py`

## Kesin Silinmemesi Gerekenler

- `.env`: API ve DB bilgileri içerir, Git’e eklenmez.
- `kayıtlar/`: Excel çıktıları burada üretilir. Kullanıcı çıktısıdır.
- `data/`: log, XML, SQLite scratch DB veya başka yerel veri içerebilir.
- `local_archive/`: silinmeyen eski yerel çıktıların yedek alanıdır; Git’e eklenmez.
- PostgreSQL database: asıl fatura verisi ve XML cache burada bulunur.
- `archive/legacy_src/api_database.py`: adı legacy olsa da aktif `ingestion/*` dosyaları tarafından import edilir.

## Arşivlenen / Legacy Alanlar

### Eski SQLite/Excel Matcher Akışı

- `archive/legacy_tools/invoice_matcher.py`
- `archive/legacy_tools/README_invoice_matcher.md`
- `archive/legacy_src/parsers/akgips_parser.py`
- `archive/legacy_src/parsers/fullboard_parser.py`

Bu akış `data/db/akgips.db`, `data/db/fullboard.db` ve manuel XML parser mantığına dayanır. Güncel PostgreSQL pipeline için ana yol değildir.

### Eski SQL Dosyaları

- `sql/archive/postgres_schema.sql`
- `sql/archive/stateful_ingestion_schema.sql`

Güncel kurulum `sql/stateful_ingestion_schema_v2.sql` ve migration dosyalarıyla ilerler.

### Tarihi Dokümanlar

Tarihi changelog, “complete” ve yeniden yapılandırma notları `docs/archive/` altında tutulur. Güncel kullanım için `README.md`, `QUICKSTART.md`, `docs/KOMUTLAR.md` ve `docs/YENI_BILGISAYAR_KURULUM_REHBERI.md` tercih edilmelidir.

## Yerel Çıktı Temizliği

Eski Excel raporları, loglar, SQLite DB ve XML klasörleri silinmeden `local_archive/20260504_cleanup/` altına taşındı. `data/` ve `kayıtlar/` klasörleri yeni çıktılar için boş şekilde bırakıldı.

## Temizlik Sonrası Kontrol

Temizlik veya taşıma sonrası şu kontroller çalıştırılabilir:

```bash
python3 scripts/verify_installation.py
python3 scripts/run_invoice_pipeline.py --help
python3 scripts/export_supplier_invoice_details.py --help
python3 scripts/export_to_excel.py --help
```
