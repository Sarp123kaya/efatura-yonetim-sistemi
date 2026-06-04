# Web Panel Kullanım Rehberi

Bu web panel, mevcut Python scriptlerini değiştirmeden tarayıcıdan job olarak çalıştırmak için eklenmiştir. Uzun süren işlemler HTTP isteği içinde değil, `scripts/run_web_worker.py` worker süreci içinde çalışır.

## Yerel Çalıştırma

```bash
pip install -r requirements.txt
cp env.example .env
./scripts/setup_postgres.sh
flask --app backend.web.app run --host 127.0.0.1 --port 8000
```

Ayrı bir terminalde worker:

```bash
python3 scripts/run_web_worker.py
```

Tarayıcıdan `http://127.0.0.1:8000` adresine gidin. Varsayılan test girişi `admin/admin` şeklindedir; gerçek kullanımda `.env` içinde mutlaka `WEB_ADMIN_PASSWORD` ve `WEB_SECRET_KEY` ayarlayın.

## Zorunlu Production Ayarları

`.env` içinde en az şu değerler dolu olmalı:

```bash
DB_URL=postgresql://user:password@localhost:5432/invoices
ISBASI_API_KEY=...
ISBASI_USERNAME=...
ISBASI_PASSWORD=...
WEB_ADMIN_USER=admin
WEB_ADMIN_PASSWORD=uzun-ve-guclu-bir-parola
WEB_PERSONAL_USER=c
WEB_PERSONAL_PASSWORD=uzun-ve-guclu-bir-parola-2
WEB_SECRET_KEY=uzun-random-bir-secret
WEB_SESSION_COOKIE_SECURE=true
```

`ISBASI_PASSWORD` boş kalırsa worker terminalden şifre soramayacağı için veri çekme jobları takılır veya hata verir.

## Web Üzerinden Çalıştırılabilen İşler

- Gelen/giden verileri çek, eşleştir, Excel üret.
- Mevcut DB verisinden eşleştirme Excel’i üret.
- Tüm Excel paketini üret.
- Gelen e-irsaliye raporunu pipeline içinde üretir; formdan PDF klasörü ve açıklama cache yenileme seçilebilir.
- Sadece gelen faturaları Excel’e aktar.
- Sadece giden faturaları Excel’e aktar.
- Agent çalışma geçmişini Excel’e aktar.
- AK GIPS ve FULLBOARD ürün detay raporlarını üret.
- Müşteri ürün fiyat raporunu üret.
- Fabrika kar senkronizasyonu ve raporu üret.

`Fabrika Kar Senkronizasyonu ve Raporu` kalıcı DB upsert yaptığı için panelde onay kutusu ister.

## Job Mantığı

Web formu `web_jobs` tablosuna kayıt açar. Worker bekleyen jobı alır, logları `data/logs/web_jobs/` altında dosyaya ve `web_jobs.log_text` alanına yazar. Oluşturulan Excel dosyaları job detayında ve `Raporlar` ekranında indirilebilir.

Aynı anda birden fazla ana pipeline/export çalışmasın diye exclusive işler PostgreSQL advisory lock kullanır. Bu, `agent_state`, XML cache ve ortak çıktı klasöründeki çakışmaları azaltır.

## Güncel Form Alanları

- `Başlangıç tarihi` / `Bitiş tarihi`: API veri çekme tarih aralığı.
- `Çıktı klasörü`: Excel dosyalarının yazılacağı klasör.
- `E-irsaliye PDF klasörü`: Plaka/sevk yeri için kullanılan PDF export klasörü. Varsayılan: `data/incoming_despatch_pdfs`.
- `İşbaşı şifresi`: `.env` içinde `ISBASI_PASSWORD` yoksa sadece ilgili job için geçici kullanılır ve DB kaydından temizlenir.
- `XML cache yenile`: Fatura XML cache’lerini yeniden çeker.
- `E-irsaliye açıklama cache yenile`: PDF/API açıklama cache’ini yeniden işler.
- `API çekmeden mevcut DB ile çalış`: Sadece mevcut PostgreSQL verisiyle rapor üretir.
- `Gelen e-irsaliye raporunu atla`: Pipeline içinde `Irsaliye_Giden_Fatura_Eslestirme` raporunu üretmez.

## VPS Üzerinde Docker Compose

1. Repo VPS’e kopyalanır.
2. `.env` oluşturulur ve production değerleri doldurulur.
3. `POSTGRES_PASSWORD` ortam değişkeni ayarlanır.
4. Servisler başlatılır:

```bash
docker compose up -d --build
docker compose exec web ./scripts/setup_postgres.sh
```

Web servisi varsayılan olarak sadece `127.0.0.1:8000` adresine açılır. Dış erişim için Nginx reverse proxy ve HTTPS kullanın.

## VPS Üzerinde Systemd

Docker kullanılmayacaksa:

1. Projeyi `/opt/efatura-panel` altına kurun.
2. `.venv` oluşturup `pip install -r requirements.txt` çalıştırın.
3. `.env` dosyasını production değerleriyle doldurun.
4. `deploy/systemd/efatura-web.service` ve `deploy/systemd/efatura-worker.service` dosyalarını `/etc/systemd/system/` altına kopyalayın.
5. Servisleri başlatın:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now efatura-web efatura-worker
```

Nginx için `deploy/nginx/efatura-panel.conf` örneğini domain adınıza göre düzenleyin. HTTPS için Let’s Encrypt/certbot kullanın.

## Güvenlik Notları

- `.env` ve API anahtarları git’e eklenmemeli.
- Panel internetten erişilecekse HTTPS zorunlu kabul edilmeli.
- `WEB_ADMIN_PASSWORD` boş bırakılmamalı.
- `WEB_SESSION_COOKIE_SECURE=true` HTTPS arkasında açılmalı.
- Rapor indirme endpoint’i sadece proje içindeki `.xlsx` dosyalarını servis eder.
- Riskli bakım işleri web’e eklenirken önce önizleme ve onay ekranı tasarlanmalı.
