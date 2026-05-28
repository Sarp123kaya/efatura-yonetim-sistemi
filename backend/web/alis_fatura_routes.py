#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask route'ları — Alış Faturası Oluştur (AKG/FLL Browser Import)
==================================================================

Bu modül mevcut app.py'e dokunmadan app'e blueprint olarak eklenir.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, Flask, redirect, render_template, session, url_for

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_LOGS_DIR = PROJECT_ROOT / "data" / "logs"

alis_fatura_bp = Blueprint("alis_fatura", __name__, url_prefix="/alis-fatura")


# ── Auth yardımcısı ───────────────────────────────────────────────────────────

def _login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

_BATCH_IMPORT_JS = r"""(async function batchImport() {
  // --- 1. Kabul Edilmiş filtresini uygula ---
  const selects = document.querySelectorAll('select');
  let statusSel = null;
  for (const s of selects) {
    if (Array.from(s.options).some(o => o.text.includes('Kabul'))) {
      statusSel = s; break;
    }
  }
  if (statusSel) {
    statusSel.value = '1';
    $(statusSel).trigger('change');
  }
  await new Promise(r => setTimeout(r, 2000));

  // --- 2. jQuery.ajax'ı yakala: navigasyonu engelle, 409'da retry ---
  const results = [];
  const origAjax = $.ajax;
  $.ajax = function (settings) {
    if (settings.url && settings.url.includes('AutoImportIncomingEInvoice')) {
      const uuid = (settings.url.match(/uuid=([^&]+)/) || ['', '?'])[1];
      const flexUrl = settings.url.replace(
        'allowFlexibleProductMatch=false',
        'allowFlexibleProductMatch=true'
      );
      settings.success = function (data) {
        if (data && data.code === 409) {
          // Eşleşmeyen ürün → flexible ile tekrar dene
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
      if (otBtn) {
        otBtn.click();
        await new Promise(r => setTimeout(r, 3000));
      } else {
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
  console.log('%c✅ AKG/FLL Alış Faturası Aktarımı Tamamlandı', 'color:#22c55e;font-size:16px;font-weight:bold;');
  console.log(`   Toplam işlenen : ${totalProcessed}`);
  console.log(`   Başarılı       : ${success}`);
  console.log(`   Başarısız      : ${failed}`);
  console.log('   Detaylar için: window.__importResults');
  window.__importResults = results;
  return { totalProcessed, success, failed, results };
})();"""


def _load_import_logs(limit: int = 10) -> list[dict]:
    """data/logs/ içindeki batch_import_*.json loglarını döndürür."""
    if not DATA_LOGS_DIR.exists():
        return []
    logs = []
    for path in sorted(DATA_LOGS_DIR.glob("batch_import_*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results = data.get("results", [])
            logs.append({
                "filename": path.name,
                "date": _parse_log_date(path.name),
                "total": data.get("totalProcessed", len(results)),
                "success": len([r for r in results if r.get("data", {}).get("code") == 0]),
                "failed": len([r for r in results if r.get("err") or r.get("retryErr")]),
            })
        except Exception:
            pass
    return logs


def _parse_log_date(filename: str) -> str:
    """batch_import_20260529_012345.json → 29.05.2026 01:23"""
    try:
        parts = filename.replace("batch_import_", "").replace(".json", "").split("_")
        d = parts[0]
        t = parts[1]
        dt = datetime.strptime(d + t, "%Y%m%d%H%M%S")
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return filename


def _factory_incoming_count() -> int:
    """Veritabanından AKG/FLL gelen fatura sayısını döndürür."""
    try:
        from backend.core.db import db
        row = db.query_one(
            """
            SELECT COUNT(*) AS cnt FROM incoming_invoices
            WHERE supplier ILIKE '%AK G%P%' OR supplier ILIKE '%FULLBOARD%'
            """
        )
        return int(row["cnt"]) if row else 0
    except Exception:
        return 0


# ── Route ─────────────────────────────────────────────────────────────────────

@alis_fatura_bp.route("/", methods=["GET"])
@_login_required
def index():
    return render_template(
        "alis_fatura_import.html",
        batch_js=_BATCH_IMPORT_JS,
        import_logs=_load_import_logs(),
        factory_incoming_count=_factory_incoming_count(),
    )


# ── Kayıt yardımcısı ──────────────────────────────────────────────────────────

def register_alis_fatura_routes(app: Flask) -> None:
    """Mevcut Flask app'e alış faturası import blueprint'ini kayıt eder."""
    app.register_blueprint(alis_fatura_bp)
