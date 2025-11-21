# 🔗 Birleşik E-Fatura Sistemi

## 📊 Genel Bakış

Bu sistem, farklı tedarikçilerden gelen e-faturaları tek bir veritabanında birleştirir ve firma bazlı raporlama sağlar.

## 🏢 Firma Kodları

| Kod | Firma | İrsaliye Formatı |
|-----|-------|------------------|
| **A** | AK GİPS YAPI KİMYASALLARI | A-##### (örn: A-14740) |
| **F** | FULLBOARD YAPI ELEMANLARI | F-##### (örn: F-07904) |

## 📈 Toplam Veriler

### Özet İstatistikler

```
┌─────────────────────────────────────────────────┐
│  BİRLEŞİK VERİTABANI İSTATİSTİKLERİ            │
├─────────────────────────────────────────────────┤
│  • Toplam Fatura       : 6 adet                 │
│  • Toplam İrsaliye     : 13 adet                │
│  • Toplam Satır        : 29 adet                │
│                                                  │
│  • AK GİPS (A)         : 3 fatura               │
│    └─ Tutar           : 835,855.80 TRY         │
│    └─ İrsaliye        : 10 adet                 │
│                                                  │
│  • FULLBOARD (F)       : 3 fatura               │
│    └─ Tutar           : 238,275.00 TRY         │
│    └─ İrsaliye        : 3 adet                  │
│                                                  │
│  • GENEL TOPLAM        : 1,074,130.80 TRY       │
│  • TOPLAM KDV          : 179,021.80 TRY         │
└─────────────────────────────────────────────────┘
```

## 🚀 Kullanım Adımları

### 1. Veritabanlarını Birleştir

```bash
python3 birlestir_veritabanlari.py
```

**Ne yapar?**
- `efatura.db` (AK GİPS) verilerini alır → A- prefix ekler, IRS kelimesini kaldırır
- `gelen efaturalar fullboard/efatura_fullboard.db` verilerini alır → F- prefix ekler, IRS kelimesini kaldırır
- Tek bir `efatura_birlesik.db` oluşturur
- İrsaliye formatı: A-14740, F-07904 gibi

**Çıktı:**
```
================================================================================
VERİTABANLARI BİRLEŞTİRME
================================================================================

✓ Birleşik veritabanı şeması oluşturuldu

📊 AK GİPS verileri aktarılıyor...
  ✓ 3 AK GİPS faturası eklendi (A- prefix)

📊 FULLBOARD verileri aktarılıyor...
  ✓ 3 FULLBOARD faturası eklendi (F- prefix)

================================================================================
BİRLEŞTİRME TAMAMLANDI
================================================================================
```

### 2. Birleşik Excel Raporu Oluştur

```bash
python3 export_to_excel_birlesik.py
```

**Ne yapar?**
- Tüm faturaları tek bir Excel'de birleştirir
- Her satırda firma kodu gösterir (A veya F)
- İrsaliye numaraları prefix ile gösterilir

**Oluşturulan dosya:**
`kayıtlar_birlesik/efatura_birlesik_20251009_151728.xlsx`

## 📋 Excel İçeriği

### 1. Özet Sayfası
- Toplam istatistikler
- Firma bazlı dağılım
- Fatura listesi

### 2. Faturalar Sayfası

| Firma | Fatura No | Tarih | Toplam Tutar | Vergi Matrahı | KDV | Satıcı | Müşteri |
|-------|-----------|-------|--------------|---------------|-----|--------|---------|
| A | AKG2025000006382 | 2025-09-23 | 370,645.80 | 308,871.50 | 61,774.30 | AK GİPS | D.KAYA |
| F | FLL2025000007254 | 2025-10-03 | 79,425.00 | 66,187.50 | 13,237.50 | FULLBOARD | D.KAYA |

### 3. Fatura Satırları Sayfası

| Firma | Fatura No | Satır | Ürün | Miktar | Birim | Birim Fiyat | Toplam | ADET |
|-------|-----------|-------|------|--------|-------|-------------|--------|------|
| A | AKG... | 1 | 02.MAKT (35 KG) | 34.02 | TNE | 2,150.00 | 73,143.00 | 972.00 |
| F | FLL... | 1 | FULLGİPS TURBO... | 750.0 | EA | 88.25 | 66,187.50 | 750.00 |

### 4. İrsaliyeler Sayfası

| Firma | Fatura No | İrsaliye (Kısa) | İrsaliye (Tam) | Tarih | Toplam Tutar |
|-------|-----------|-----------------|----------------|-------|--------------|
| A | AKG2025000006382 | **A-14703** | IRS2025000014703 | 2025-09-22 | 370,645.80 |
| A | AKG2025000006382 | **A-14704** | IRS2025000014704 | 2025-09-22 | 370,645.80 |
| F | FLL2025000007254 | **F-07904** | IRS2025000007904 | 2025-10-04 | 79,425.00 |

## 🔍 Veritabanı Sorguları

### Firma Bazlı Özet

```sql
SELECT 
    firma_kodu,
    COUNT(*) as fatura_sayisi,
    SUM(total_amount) as toplam_tutar
FROM invoices
GROUP BY firma_kodu;
```

### İrsaliye Listesi (Prefix'li)

```sql
SELECT 
    i.firma_kodu,
    i.invoice_number,
    d.despatch_id_short,
    d.issue_date
FROM despatch_documents d
JOIN invoices i ON d.invoice_id = i.id
ORDER BY i.firma_kodu, d.despatch_id_short;
```

### Firma Bazlı Ürün Analizi

```sql
SELECT 
    i.firma_kodu,
    il.item_name,
    SUM(il.quantity) as toplam_miktar,
    il.unit,
    SUM(il.line_total) as toplam_tutar
FROM invoice_lines il
JOIN invoices i ON il.invoice_id = i.id
GROUP BY i.firma_kodu, il.item_name
ORDER BY i.firma_kodu, toplam_tutar DESC;
```

## 📁 Dosyalar

```
.
├── efatura_birlesik.db                    # Birleşik veritabanı
├── birlestir_veritabanlari.py            # Birleştirme scripti
├── export_to_excel_birlesik.py           # Birleşik Excel export
└── kayıtlar_birlesik/                    # Birleşik Excel raporları
    └── efatura_birlesik_*.xlsx
```

## 🔄 Güncelleme

Yeni faturalar geldiğinde:

1. Her klasördeki XML'leri parse et:
   ```bash
   # Ana klasör (AK GİPS)
   python3 xml_parser.py
   
   # Fullboard klasörü
   cd "gelen efaturalar fullboard"
   python3 xml_parser_fullboard.py
   cd ..
   ```

2. Veritabanlarını yeniden birleştir:
   ```bash
   python3 birlestir_veritabanlari.py
   ```

3. Yeni birleşik Excel oluştur:
   ```bash
   python3 export_to_excel_birlesik.py
   ```

## 💡 Avantajlar

✅ **Tek Noktadan Yönetim:** Tüm faturalar tek veritabanında
✅ **Firma Ayırımı:** A- ve F- prefix ile kolay ayırt edilebilir
✅ **Kapsamlı Raporlama:** Firma bazlı veya genel raporlar
✅ **Excel Uyumlu:** Tüm veriler Excel'de filtrelenebilir
✅ **Genişletilebilir:** Yeni firmalar için kolayca C-, D-, vb. eklenebilir

---

**Son Güncelleme:** 9 Ekim 2025

