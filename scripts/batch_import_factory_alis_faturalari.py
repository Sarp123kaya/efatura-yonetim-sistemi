#!/usr/bin/env python3
"""
AKG / FULLBOARD Gelen E-Fatura → Alış Faturası Toplu İçe Aktarıcı
===================================================================

Tarayıcıda app.isbasi.com'a ZATEN GİRİŞ YAPILMIŞ olması gerekir.
Script, açık Cursor IDE tarayıcısına (cursor-ide-browser MCP) bağlanarak
'Kabul Edilmiş' statüsündeki AKG/FLL e-faturalarını otomatik alış
faturasına dönüştürür.

ÇALIŞTIRILMA:
  python scripts/batch_import_factory_alis_faturalari.py

NOT: Bu script bağımsız çalışmaz; Cursor IDE agent modu üzerinden
     ya da aşağıdaki JavaScript snippet'ini tarayıcı konsoluna yapıştırarak
     kullanılabilir.

TARAYICI KONSOLu İLE KULLANIM (önerilen):
  1. app.isbasi.com/invoice/myinvoices sayfasını açın.
  2. Durum filtresini "Kabul Edilmiş" olarak ayarlayın.
  3. F12 → Konsol sekmesini açın.
  4. Aşağıdaki BATCH_IMPORT_JS içeriğini yapıştırıp çalıştırın.

KESİNTİSİZ OTOMASYON (Playwright + CDP):
  Aşağıdaki Playwright tabanlı çözümü kullanmak için önce Chrome'u
  --remote-debugging-port=9222 ile başlatın:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug

  Ardından:
    pip install playwright
    python scripts/batch_import_factory_alis_faturalari.py --playwright
"""

import argparse
import json
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Tarayıcı konsoluna yapıştırılacak JavaScript
# ---------------------------------------------------------------------------
BATCH_IMPORT_JS = r"""
(async function batchImport() {
  // --- 1. Kabul Edilmiş filtresini uygula ---
  const selects = document.querySelectorAll('select');
  let statusSel = null;
  for (const s of selects) {
    if (Array.from(s.options).some(o => o.text.includes('Kabul'))) {
      statusSel = s; break;
    }
  }
  if (statusSel) { statusSel.value = '1'; $(statusSel).trigger('change'); }
  await new Promise(r => setTimeout(r, 2000));

  // --- 2. jQuery.ajax'ı yakala: navigasyonu engelle, 409'da retry ---
  const results = [];
  const origAjax = $.ajax;
  $.ajax = function (settings) {
    if (settings.url && settings.url.includes('AutoImportIncomingEInvoice')) {
      const uuid = (settings.url.match(/uuid=([^&]+)/) || ['', '?'])[1];
      const flexUrl = settings.url.replace(
        'allowFlexibleProductMatch=false', 'allowFlexibleProductMatch=true'
      );
      settings.success = function (data) {
        if (data && data.code === 409) {
          origAjax({
            url: flexUrl, type: 'POST',
            success: d2 => results.push({ uuid, data: d2, retried: true }),
            error: (_, s, e) => results.push({ uuid, retryErr: s + ': ' + e })
          });
        } else {
          results.push({ uuid, data });
        }
      };
      settings.error = (_, s, e) => results.push({ uuid, err: s + ': ' + e });
    }
    return origAjax.apply(this, arguments);
  };

  // --- 3. Tüm sayfalardaki AKG/FLL satırlarını işle ---
  async function processPage() {
    const rows = Array.from(document.querySelectorAll('tr[data-uid]')).filter(r =>
      (r.textContent.includes('AK GİPS') || r.textContent.includes('FULLBOARD')) &&
      Array.from(r.querySelectorAll('[title]')).some(b => b.title === 'Alış Faturası Oluştur')
    );
    for (const row of rows) {
      const btn = Array.from(row.querySelectorAll('[title]'))
        .find(b => b.title === 'Alış Faturası Oluştur');
      if (!btn) continue;
      btn.click();
      await new Promise(r => setTimeout(r, 1500));
      const otBtn = Array.from(document.querySelectorAll('button,a'))
        .find(b => b.textContent.replace(/\s+/g, '').includes('OtomatikE'));
      if (otBtn) { otBtn.click(); await new Promise(r => setTimeout(r, 3000)); }
      else {
        const x = document.querySelector('.swal2-cancel,.close,[data-dismiss]');
        if (x) x.click();
        await new Promise(r => setTimeout(r, 500));
      }
    }
    return rows.length;
  }

  let page = 1, totalProcessed = 0;
  while (page <= 50) {
    const cnt = await processPage();
    totalProcessed += cnt;
    const pi = document.querySelector('.k-pager-info')?.textContent?.trim() || '';
    const m = pi.match(/(\d+)\s*\/\s*(\d+)/);
    if (!m || parseInt(m[1]) >= parseInt(m[2])) break;
    const nextBtn = document.querySelector(
      'a[aria-label="Go to the next page"]:not(.k-state-disabled)'
    );
    if (!nextBtn) break;
    nextBtn.click();
    await new Promise(r => setTimeout(r, 2500));
    page++;
  }

  // --- 4. Özet ---
  const success = results.filter(r => r.data && r.data.code === 0).length;
  const failed  = results.filter(r => r.err || r.retryErr).length;
  console.log(`\n✅ Toplu import tamamlandı`);
  console.log(`   Toplam işlenen : ${totalProcessed}`);
  console.log(`   Başarılı       : ${success}`);
  console.log(`   Başarısız      : ${failed}`);
  console.log(`\nDetaylar: window.__importResults`);
  window.__importResults = results;
  return { totalProcessed, success, failed, results };
})();
"""


def run_playwright(cdp_url: str = "http://localhost:9222") -> None:
    """
    Mevcut bir Chrome CDP oturumuna bağlanarak batch import çalıştırır.
    Gereksinim: pip install playwright
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright kurulu değil. Kurmak için: pip install playwright", file=sys.stderr)
        sys.exit(1)

    print(f"Chrome CDP'ye bağlanılıyor: {cdp_url}")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page = context.pages[0]

        # Gelen E-Faturalar sayfasına git
        target_url = "https://app.isbasi.com/invoice/myinvoices"
        if target_url not in page.url:
            page.goto(target_url)
            page.wait_for_load_state("networkidle")

        print("Batch import başlatılıyor...")
        result_json = page.evaluate(BATCH_IMPORT_JS)
        result = json.loads(result_json) if isinstance(result_json, str) else result_json

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"data/logs/batch_import_{ts}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Tamamlandı!")
        print(f"   Toplam işlenen : {result.get('totalProcessed', '?')}")
        print(f"   Başarılı       : {result.get('success', '?')}")
        print(f"   Başarısız      : {result.get('failed', '?')}")
        print(f"   Log            : {out_path}")
        browser.close()


def print_console_instructions() -> None:
    """Tarayıcı konsolu kullanım talimatlarını yazdırır."""
    print("=" * 68)
    print(" AKG/FULLBOARD Alış Faturası Toplu İçe Aktarıcı")
    print("=" * 68)
    print()
    print("Tarayıcı konsolundan çalıştırmak için:")
    print()
    print("  1. https://app.isbasi.com/invoice/myinvoices adresine gidin")
    print("  2. Sayfayı açık bırakın (giriş yapılmış olmalı)")
    print("  3. F12 → Konsol sekmesini açın")
    print("  4. Aşağıdaki kodu yapıştırın ve Enter'a basın:")
    print()
    print("-" * 68)
    print(BATCH_IMPORT_JS)
    print("-" * 68)
    print()
    print("Playwright ile otomatik çalıştırmak için:")
    print()
    print("  # 1. Chrome'u debug modda başlatın:")
    print("  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\")
    print("      --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug")
    print()
    print("  # 2. Tarayıcıda app.isbasi.com'a giriş yapın")
    print()
    print("  # 3. Scripti çalıştırın:")
    print("  python scripts/batch_import_factory_alis_faturalari.py --playwright")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AKG/FULLBOARD gelen e-faturaları toplu alış faturasına çevirir"
    )
    parser.add_argument(
        "--playwright", action="store_true",
        help="Playwright CDP ile mevcut Chrome oturumuna bağlan"
    )
    parser.add_argument(
        "--cdp-url", default="http://localhost:9222",
        help="Chrome remote debugging URL (varsayılan: http://localhost:9222)"
    )
    parser.add_argument(
        "--print-js", action="store_true",
        help="Sadece JavaScript snippet'ini yazdır"
    )
    args = parser.parse_args()

    if args.print_js:
        print(BATCH_IMPORT_JS)
        return

    if args.playwright:
        run_playwright(args.cdp_url)
    else:
        print_console_instructions()


if __name__ == "__main__":
    main()
