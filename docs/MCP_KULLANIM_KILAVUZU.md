# MCP Kullanim Kilavuzu

Bu projede MCP sunuculari proje bazli olarak `.cursor/mcp.json` dosyasinda tanimlanir. Cursor'da `Cmd + Shift + J` ile ayarlari acip `Tools & MCP` bolumunden sunucularin durumunu gorebilir, acip kapatabilir ve hata durumunda MCP loglarini inceleyebilirsiniz.

## On Kosullar

- Node.js ve `npx` kurulu olmali.
- GitHub MCP icin Docker calisiyor olmali.
- GitHub MCP icin `GITHUB_PERSONAL_ACCESS_TOKEN` ortam degiskeni tanimli olmali.
- PostgreSQL MCP icin `DB_URL` ortam degiskeni tanimli olmali.

Ornek:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="github_pat_..."
export DB_URL="postgresql://kullanici:sifre@localhost:5432/veritabani"
cursor .
```

Cursor macOS'ta Dock/Finder uzerinden acilirsa terminaldeki ortam degiskenlerini gormeyebilir. MCP'ler token veya DB baglantisini bulamazsa Cursor'u yukaridaki gibi terminalden acin ya da degiskenleri sistem ortaminda tanimlayip Cursor'u yeniden baslatin.

## Filesystem MCP

`filesystem` sunucusu agent'in bu proje klasorunu MCP uzerinden okumasini, dosya aramasini ve gerekirse dosya yazmasini saglar. Erisim sadece `.cursor/mcp.json` icindeki proje yolu ile sinirlidir.

Kullanim ornekleri:

- "Filesystem MCP ile `docs` klasorundeki rehberleri listele."
- "Bu projede `DB_URL` nerelerde geciyor, MCP filesystem ile ara."
- "Bir dosyanin icerigini MCP uzerinden oku ve ozetle."

Not: Cursor zaten workspace dosyalarina erisebildigi icin bu MCP daha cok standart MCP araclariyla dosya islemi denemek veya baska MCP istemcileriyle ayni konfigurasyonu kullanmak icin faydalidir.

## GitHub MCP

`github` sunucusu GitHub'in resmi MCP sunucusunu Docker imaji ile calistirir. PR, issue, repository, branch ve review gibi GitHub islemleri icin kullanilir.

Gereken ortam degiskeni:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="github_pat_..."
```

Token icin minimum yetkiyi secin. Sadece issue/PR okumak icin read-only izinler, PR yorumlama veya issue guncelleme icin ilgili write izinleri yeterlidir.

Kullanim ornekleri:

- "GitHub MCP ile acik issue'lari listele."
- "Son PR'lardaki review yorumlarini ozetle."
- "Bu branch icin GitHub'daki PR durumunu kontrol et."

## PostgreSQL MCP

`postgres` sunucusu `DB_URL` ile baglandigi PostgreSQL veritabaninda sema inceleme ve read-only sorgular icin kullanilir. Bu proje zaten `env.example` icinde `DB_URL` kullaniyor; ayni baglanti bilgisini ortam degiskeni olarak Cursor'a da vermek yeterlidir.

Gereken ortam degiskeni:

```bash
export DB_URL="postgresql://kullanici:sifre@localhost:5432/veritabani"
```

Kullanim ornekleri:

- "PostgreSQL MCP ile tablolarin listesini cikar."
- "Fatura tablolarindaki kolonlari ve indeksleri ozetle."
- "Son 10 gelen faturayi read-only sorguyla kontrol et."

Guvenlik icin mumkunse sadece gerekli tablolara erisebilen read-only bir PostgreSQL kullanicisi kullanin.

## Playwright MCP

`playwright` sunucusu web sayfalarini acma, tiklama, form doldurma, ekran goruntusu alma ve tarayici uzerinden test akisi calistirma isleri icin kullanilir. Bu, Cursor'in yerlesik Browser aracina benzer; farki, standart Playwright MCP sunucusu olarak proje konfigurasyonuna eklenmis olmasidir.

Kullanim ornekleri:

- "Playwright MCP ile `http://127.0.0.1:8000` adresini ac ve login ekranini kontrol et."
- "Web panelde pipeline baslatma butonunun gorunur oldugunu dogrula."
- "Form alanlarini doldurup hata mesajlarini kontrol et."

Web paneli test etmek icin once uygulamayi ayri bir terminalde baslatin:

```bash
flask --app backend.web.app run --host 127.0.0.1 --port 8000
```

## Sorun Giderme

- MCP sunucularini ekledikten sonra Cursor'u yeniden baslatin veya `Tools & MCP` ekranindan sunucuyu yeniden etkinlestirin.
- GitHub MCP calismiyorsa Docker'in acik oldugunu ve `GITHUB_PERSONAL_ACCESS_TOKEN` degiskeninin Cursor tarafindan goruldugunu kontrol edin.
- PostgreSQL MCP calismiyorsa `DB_URL` degerini ve veritabaninin ayakta oldugunu kontrol edin.
- Playwright ilk calismada npm paketini indirebilir; internet baglantisi ve Node.js surumu sorunlarini MCP loglarindan kontrol edin.
