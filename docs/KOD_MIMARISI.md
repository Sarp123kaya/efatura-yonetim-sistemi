# E-Fatura Yönetim Sistemi — Kod Mimarisi ve Fonksiyon Şeması

Bu doküman projenin kod mimarisini, modül ilişkilerini ve ana fonksiyon akışlarını özetler.

**Depo:** https://github.com/Sarp123kaya/efatura-yonetim-sistemi  
**Güncel geliştirme dalı:** `VPS`

---

## 1. Üst seviye mimari

```mermaid
flowchart TB
    subgraph UI["Web Panel (Flask)"]
        APP[app.py — ana route'lar]
        BP1[cekler_routes]
        BP2[ekstre_routes]
        BP3[alis_fatura / purchase_import]
        BP4[irsaliye_routes]
        JOBS[jobs + worker]
    end

    subgraph CORE["backend/core — iş kuralları"]
        DB[(db.py — PostgreSQL)]
        ISB[isbasi_client]
        NORM[normalize]
        AGENT_STATE[agent_state]
        CACHE[XML / irsaliye cache]
        CHK[check_pool + dedupe + incremental]
        EKS[ekstre parser / matcher / live balance]
        PUR[purchase_invoice_importer]
    end

    subgraph AGENTS["backend/agents"]
        INC[incoming_agent]
        OUT[outgoing_agent]
    end

    subgraph ING["ingestion"]
        API_IN[api_incoming_invoices_extractor]
        API_DATA[api_data_extractor]
    end

    subgraph SCRIPTS["scripts — CLI / batch"]
        PIPE[run_invoice_pipeline]
        MATCH[pg_invoice_matcher]
        EXPORT[export_*]
    end

    subgraph CEK["çekler/statement_extractor"]
        XLS[excel_importer / compare]
        PDF[pdf_reader / OCR]
    end

    ISBASI[(İşbaşı API)]
    PG[(PostgreSQL)]

    UI --> CORE
    JOBS --> SCRIPTS
    JOBS --> AGENTS
    AGENTS --> ING
    ING --> ISBASI
    AGENTS --> DB
    SCRIPTS --> DB
    SCRIPTS --> ISBASI
    BP1 --> CEK
    BP1 --> DB
    BP2 --> EKS
    BP2 --> DB
    BP3 --> PUR
    PUR --> ISBASI
    CORE --> PG
    CEK --> PG
```

### Katman özeti

| Katman | Rol |
|--------|-----|
| `ingestion/` | Ham API çağrıları, sayfalama, JSON |
| `backend/agents/` | Artımlı çekme, hash, DB upsert |
| `backend/core/` | Ortak DB, normalize, İşbaşı client, domain modülleri |
| `backend/web/` | Kullanıcı arayüzü, iş kuyruğu, blueprint'ler |
| `scripts/` | Tek komutla pipeline, eşleştirme, export |
| `çekler/` | Excel/PDF/OCR ile çek parse (web `/cekler` bunu kullanır) |
| `sql/` | Şema ve migration dosyaları |

### Klasör yapısı (özet)

```text
.
├── backend/
│   ├── agents/          # incoming_agent, outgoing_agent
│   ├── core/            # db, config, domain modülleri
│   └── web/             # Flask app, templates, worker
├── ingestion/           # İşbaşı API extractor'ları
├── scripts/             # CLI pipeline ve raporlar
├── sql/                 # PostgreSQL şema + migration
├── çekler/              # statement_extractor (Excel/OCR)
├── docs/                # Rehberler (bu dosya dahil)
├── deploy/                # nginx, systemd
├── data/                # Yerel cache, log (Git dışı)
└── kayıtlar/            # Üretilen Excel raporları
```

---

## 2. Veri akışı (ana iş hattı)

```mermaid
sequenceDiagram
    participant U as Kullanıcı / Cron
    participant W as Web Worker
    participant A as incoming/outgoing agent
    participant API as İşbaşı API
    participant DB as PostgreSQL
    participant M as pg_invoice_matcher

    U->>W: Job başlat (dashboard)
    W->>A: Agent çalıştır
    A->>API: Faturaları listele (tarih + watermark)
    API-->>A: JSON faturalar
    A->>A: row_hash, normalize, XML cache
    A->>DB: INSERT/UPDATE (incremental)
    W->>M: Eşleştirme raporu
    M->>DB: Gelen + giden oku
    M-->>U: Excel (kayıtlar/)
```

**Stateful ingestion:** `agent_state` tablosunda son işlenen tarih tutulur. Her çalıştırmada yalnızca yeni veya değişen kayıtlar işlenir (`change_type`: `insert` / `update` / `nochange`).

**Ana pipeline:** `scripts/run_invoice_pipeline.py`

1. Gelen faturaları API'den çek → PostgreSQL  
2. Giden faturaları API'den çek → PostgreSQL  
3. Eşleştirme Excel'i (`pg_invoice_matcher`)  
4. Opsiyonel ters eşleştirme, irsaliye raporu, fabrika/müşteri export'ları  

---

## 3. PostgreSQL — ana tablolar

```mermaid
erDiagram
    incoming_invoices ||--o{ incoming_invoice_xml_cache : uuid
    outgoing_invoices ||--o{ outgoing_invoice_xml_cache : id
    checks ||--o{ check_import_rows : id
    check_import_sessions ||--o{ check_import_rows : session

    incoming_invoices {
        text invoice_id PK
        text uuid
        timestamp issue_date
        text supplier
        numeric amount
        jsonb raw_json
    }

    outgoing_invoices {
        text id PK
        text invoice_no
        timestamp issue_date
        jsonb raw_json
        jsonb irsaliye_codes
        jsonb irsaliye_codes_override
    }

    checks {
        bigint id PK
        text check_no
        date maturity_date
        numeric amount
        text account_name
    }

    factory_statements {
        bigint id PK
        text fabrika
        text fis_no
        date tarih
        numeric borc
        numeric alacak
        numeric bakiye
        text source_file
    }

    web_jobs {
        uuid id PK
        text action_key
        text status
        text log_text
    }

    agent_state {
        text agent_name PK
        timestamp last_issue_date
        int lookback_days
    }
```

### Migration dosyaları (kurulum sırası özeti)

| Dosya | İçerik |
|-------|--------|
| `sql/stateful_ingestion_schema_v2.sql` | Gelen/giden fatura, agent_state, agent_runs |
| `sql/migration_v2.2_despatch_improvements.sql` | İrsaliye iyileştirmeleri |
| `sql/migration_incoming_xml_cache.sql` | Gelen XML önbellek |
| `sql/migration_outgoing_xml_cache.sql` | Giden XML önbellek |
| `sql/migration_irsaliye_override.sql` | Manuel irsaliye override |
| `sql/migration_check_pool.sql` | Çek havuzu |
| `sql/migration_factory_statements.sql` | Fabrika ekstre |
| `sql/migration_web_jobs.sql` | Panel arka plan işleri |
| `sql/migration_factory_kar.sql` | Fabrika kâr tabloları (opsiyonel) |

---

## 4. Web panel — sayfalar ve modüller

`backend/web/app.py` çekirdek uygulamadır. Ek özellikler **Blueprint** ile eklenir.

```mermaid
flowchart LR
    subgraph Routes["Ana route'lar (app.py)"]
        D[dashboard]
        ST[stats]
        CU[customers]
        IN[invoice detail]
        JB[jobs]
        RP[reports]
    end

    subgraph Blueprints["Blueprint modülleri"]
        CEK["/cekler"]
        EKS["/ekstre"]
        ALI["/alis-fatura"]
        PUR["/purchase-import"]
        IRS["/irsaliye"]
    end

    LOGIN[login]
    LOGIN --> Routes
    LOGIN --> Blueprints
```

| Modül | Dosya | Fonksiyon |
|-------|--------|-----------|
| **Dashboard** | `app.py`, `actions.py` | Eşleştirme özeti, job tetikleme |
| **İşler** | `jobs.py`, `worker.py` | Uzun script/agent arka planda |
| **Müşteriler** | `app.py`, `check_customer_views.py` | Ciro, bakiye; çek özeti (gelecek / ödenen) |
| **Çekler** | `cekler_routes.py` | Excel/OCR import, diff, mükerrer birleştirme |
| **Ekstre** | `ekstre_routes.py` | PDF parse, özet, fatura karşılaştırma, canlı bakiye |
| **Alış faturası** | `purchase_import_routes.py`, `alis_fatura_routes.py` | AKG/FLL → İşbaşı alış faturası |
| **İrsaliye düzelt** | `irsaliye_routes.py`, `irsaliye_override.py` | Giden fatura irsaliye override |
| **İstatistik / Rapor** | `stats`, `reports` | Aggregasyon, Excel indirme |

### Kimlik doğrulama

| Kullanıcı | Varsayılan (yerel) | Ortam değişkenleri |
|-----------|-------------------|---------------------|
| Admin | `admin` / `admin` | `WEB_ADMIN_USER`, `WEB_ADMIN_PASSWORD` |
| Kişisel | `c` / `c` | `WEB_PERSONAL_USER`, `WEB_PERSONAL_PASSWORD` |

Dış ağdan giriş için ilgili parola `.env` içinde tanımlı olmalıdır.

---

## 5. `backend/core` — domain modülleri

| Modül | Görev |
|-------|--------|
| `db.py` | PostgreSQL bağlantı, sorgu, batch |
| `config.py` | `.env` yapılandırması |
| `isbasi_client.py` | İşbaşı API oturum ve çağrılar |
| `isbasi_endpoints.py` | Endpoint sabitleri / dokümantasyon |
| `normalize.py` | İrsaliye kodu normalize (A-/F- önek) |
| `agent_state.py` | Agent watermark yönetimi |
| `agent_run_logger.py` | Agent çalışma logları |
| `incoming_xml_cache.py` | Gelen fatura XML önbelleği |
| `outgoing_xml_cache.py` | Giden fatura XML önbelleği |
| `incoming_despatch_cache.py` | Gelen irsaliye açıklama cache |
| `ubl_line_parser.py` | UBL satır kalemleri |
| `purchase_invoice_importer.py` | AKG/FLL alış faturası aktarımı |
| `factory_statement_parser.py` | Fabrika PDF ekstre parse |
| `ekstre_invoice_matcher.py` | Ekstre ↔ gelen fatura eşleştirme |
| `ekstre_live_balance.py` | Son ekstre bakiyesi − yeni faturalar |
| `ekstre_fatura_compare.py` | Fabrika VKN yardımcıları |
| `check_pool.py` | Çek modeli ve import altyapısı |
| `check_excel_incremental.py` | Excel sürüm diff |
| `check_dedupe.py` | Çek no mükerrer birleştirme |
| `check_customer_views.py` | Müşteri sayfası çek özetleri |
| `irsaliye_override.py` | İrsaliye override kalıcılığı |
| `payment_import.py` | Ödeme/çek import (script entegrasyonu) |

---

## 6. Agent'lar

```mermaid
flowchart TD
    START[Agent başlat] --> WM[agent_state oku]
    WM --> FETCH[API fatura listesi]
    FETCH --> LOOP[Her fatura]
    LOOP --> HASH[row_hash]
    HASH -->|yeni| INS[INSERT]
    HASH -->|değişti| UPD[UPDATE]
    HASH -->|aynı| SKIP[nochange]
    LOOP --> XML[XML cache / satır parse]
    INS --> END[agent_runs]
    UPD --> END
    SKIP --> END
```

| Agent | Dosya | Kaynak | Hedef tablo |
|-------|--------|--------|-------------|
| Gelen | `incoming_agent.py` | `myInvoicesList` | `incoming_invoices` |
| Giden | `outgoing_agent.py` | giden fatura API | `outgoing_invoices` |

---

## 7. Scripts — operasyon komutları

| Script | Rol |
|--------|-----|
| `run_invoice_pipeline.py` | Uçtan uca ana akış |
| `pg_invoice_matcher.py` | Giden ↔ gelen eşleştirme |
| `pg_reverse_matcher.py` | Gelen → giden ters kontrol |
| `match_incoming_despatches_to_outgoing.py` | E-irsaliye eşleştirme |
| `export_supplier_invoice_details.py` | AK GİPS / FULLBOARD ürün Excel |
| `export_customer_product_prices.py` | Müşteri fiyat analizi |
| `export_to_excel.py` | Genel Excel export |
| `import_factory_purchase_invoices.py` | CLI alış faturası |
| `import_customer_checks.py` | Müşteri çek import |
| `sync_factory_kar.py` | Fabrika kâr senkronu |
| `start_web_panel.py` | Web panel başlat |
| `run_web_worker.py` | Job worker başlat |
| `setup_postgres.sh` | DB kurulum |
| `verify_installation.py` | Kurulum doğrulama |
| `probe_*.py` | API keşif / debug (üretim akışı değil) |

Web panel **İşler** sayfası `backend/web/actions.py` içindeki `ActionDefinition` kayıtlarıyla bu script'leri parametreli çalıştırır.

---

## 8. Çekler alt sistemi

```text
çekler/statement_extractor/
├── src/
│   ├── excel_importer.py      # Excel → StoredCheckRecord
│   ├── excel_compare.py       # İki Excel diff (check_no kimliği)
│   ├── snapshot_manager.py    # Snapshot (web: data/check_excel_snapshots/)
│   ├── zirve_muavin_excel.py  # Zirve muavin formatı
│   ├── image_ocr_reader.py    # Çek görüntü OCR
│   └── validators.py        # duplicate_key, validasyon
└── tests/
```

**Web entegrasyonu:** `backend/web/cekler_routes.py` → tablolar `checks`, `check_import_sessions`, `check_import_rows`.

**İş kuralları (özet):**

- Yeni Excel önceki snapshot ile karşılaştırılır; yalnızca eklenen/değişen satırlar işlenir.  
- Aynı **çek numarası** tek kayıt sayılır (mükerrer birleştirme).  
- Liste varsayılan: vadesi gelecek; vadesi geçmiş ayrı butonla.  
- Müşteri sayfasında: vadesi gelecek listelenir; vadesi geçmiş = ödenmiş kabul (tutar özeti).

---

## 9. Fabrika ekstre modülü

```mermaid
flowchart LR
    PDF[PDF yükle] --> PARSE[factory_statement_parser]
    PARSE --> DB[(factory_statements)]
    DB --> OZET[Cari Hesap Özeti\nson source_file]
    DB --> CMP[ekstre_invoice_matcher]
    INV[(incoming_invoices\nAKG / FLL)]
    CMP --> INV
    DB --> LIVE[ekstre_live_balance]
    LIVE --> INV
```

| Bileşen | Açıklama |
|---------|----------|
| Parser | AK GİPS ve FULLBOARD PDF formatları |
| Özet | Her fabrika/cari hesap için en son yüklenen dosya |
| Karşılaştırma | Ekstre fatura satırları ↔ gelen e-fatura |
| Canlı bakiye | Son ekstre kapanış bakiyesi − sonraki gelen faturalar |

---

## 10. Eşleştirme mantığı (irsaliye)

1. Giden faturada `irsaliye_codes` (API/XML'den).  
2. Gelen faturada / irsaliyede kodlar `normalize.py` ile `A-xxxxx` / `F-xxxxx` formatına çekilir.  
3. `pg_invoice_matcher` PostgreSQL üzerinden eşleştirir.  
4. Manuel düzeltme: `irsaliye_codes_override` (`irsaliye_override.py`).

---

## 11. Dağıtım ve çalıştırma

| Bileşen | Konum |
|---------|--------|
| Docker | `Dockerfile`, `docker-compose.yml` |
| Systemd | `deploy/systemd/efatura-web.service`, `efatura-worker.service` |
| Nginx | `deploy/nginx/efatura-panel.conf` |
| Bağımlılıklar | `requirements.txt` |

**Tipik yerel başlatma:**

```bash
# PostgreSQL + .env hazır olduktan sonra
python scripts/start_web_panel.py
python scripts/run_web_worker.py
```

**İlgili dokümanlar:**

- `docs/WEB_PANEL.md` — panel yapılandırması  
- `docs/KOMUTLAR.md` — komut referansı  
- `docs/PROJECT_STRUCTURE.md` — klasör yapısı  
- `docs/YENI_BILGISAYAR_KURULUM_REHBERI.md` — kurulum  

---

## 12. Özet

| Soru | Cevap |
|------|--------|
| Veri nerede? | PostgreSQL (`backend/core/db.py`) |
| API kim? | İşbaşı (`isbasi_client.py`) |
| Otomatik çekme? | `incoming_agent` / `outgoing_agent` |
| UI? | Flask `backend/web/` + blueprint'ler |
| Uzun işler? | `web_jobs` + `worker.py` |
| Raporlar? | `scripts/` → `kayıtlar/*.xlsx` |
| Çekler? | `çekler/` + `cekler_routes` |
| Fabrika ekstre? | `ekstre_routes` + `factory_statement_parser` |

---

*Son güncelleme: VPS dalı özellikleri (ekstre karşılaştırma, canlı bakiye, çek incremental import, çift giriş, irsaliye düzeltme) dahil edilmiştir.*
