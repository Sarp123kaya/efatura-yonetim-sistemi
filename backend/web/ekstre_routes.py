#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask route'ları — Fabrika Ekstre Yönetimi
==========================================
PDF ekstre dosyalarını yükleyip parse eder ve veritabanına kaydeder.
Gelen e-faturalarla karşılaştırma desteği içerir.
"""
from __future__ import annotations

import secrets
import tempfile
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

from flask import (
    Blueprint,
    Flask,
    abort,
    flash,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

from backend.core.db import db
from backend.core.ekstre_invoice_matcher import compare_ekstre_with_incoming
from backend.core.ekstre_live_balance import compute_live_balance

ekstre_bp = Blueprint("ekstre", __name__, url_prefix="/ekstre")


# ── Auth ──────────────────────────────────────────────────────────────────────

def _login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _validate_csrf() -> None:
    token = request.form.get("csrf_token", "")
    if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
        abort(400, "Geçersiz form oturumu.")


# ── DB yardımcıları ───────────────────────────────────────────────────────────

def _tables_exist() -> bool:
    try:
        db.query_one("SELECT 1 FROM factory_statements LIMIT 1")
        return True
    except Exception:
        return False


def _write_rows(rows, source_file: str) -> dict[str, int]:
    """Satırları DB'ye yazar; duplicate'ları atlar."""
    inserted = skipped = errors = 0
    with db.get_connection(auto_commit=False) as conn:
        cur = conn.cursor()
        for row in rows:
            try:
                cur.execute(
                    """
                    INSERT INTO factory_statements (
                        fabrika, cari_hesap_kodu, musteri_adi, tarih, fis_no, fis_turu,
                        aciklama, borc, alacak, bakiye, bakiye_yon, source_file
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (fabrika, COALESCE(cari_hesap_kodu,''), tarih, COALESCE(fis_no,''))
                    DO NOTHING
                    """,
                    (
                        row.fabrika,
                        row.cari_hesap_kodu or None,
                        row.musteri_adi or None,
                        row.tarih,
                        row.fis_no or None,
                        row.fis_turu or None,
                        row.aciklama or None,
                        row.borc,
                        row.alacak,
                        row.bakiye,
                        row.bakiye_yon or None,
                        source_file,
                    ),
                )
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1
            except Exception:
                errors += 1
        conn.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def _load_summary() -> list[dict]:
    """Her fabrika + cari hesap için yalnızca son yüklenen PDF (source_file) özeti."""
    try:
        return db.query(
            """
            WITH latest_batch AS (
                SELECT DISTINCT ON (fabrika, COALESCE(cari_hesap_kodu, ''))
                    fabrika,
                    COALESCE(cari_hesap_kodu, '') AS hesap_key,
                    cari_hesap_kodu,
                    source_file,
                    created_at AS yukleme_tarihi
                FROM factory_statements
                ORDER BY fabrika, COALESCE(cari_hesap_kodu, ''),
                         created_at DESC NULLS LAST, id DESC
            )
            SELECT
                fs.fabrika,
                fs.cari_hesap_kodu,
                lb.source_file,
                lb.yukleme_tarihi,
                COUNT(*)                         AS satir_adedi,
                COALESCE(SUM(fs.borc), 0)        AS toplam_borc,
                COALESCE(SUM(fs.alacak), 0)      AS toplam_alacak,
                MIN(fs.tarih)                    AS ilk_tarih,
                MAX(fs.tarih)                    AS son_tarih,
                MAX(fs.bakiye) FILTER (WHERE fs.bakiye_yon = 'A') AS son_bakiye_a,
                MAX(fs.bakiye) FILTER (WHERE fs.bakiye_yon = 'B') AS son_bakiye_b
            FROM factory_statements fs
            INNER JOIN latest_batch lb
                ON fs.fabrika = lb.fabrika
               AND COALESCE(fs.cari_hesap_kodu, '') = lb.hesap_key
               AND fs.source_file = lb.source_file
            GROUP BY fs.fabrika, fs.cari_hesap_kodu, lb.source_file, lb.yukleme_tarihi
            ORDER BY fs.fabrika, fs.cari_hesap_kodu
            """
        )
    except Exception:
        return []


def _latest_source_file(fabrika: str, hesap: Optional[str]) -> Optional[str]:
    filters = ["fabrika = %s"]
    params: list[Any] = [fabrika]
    if hesap is not None:
        filters.append("COALESCE(cari_hesap_kodu, '') = %s")
        params.append(hesap)
    where = " AND ".join(filters)
    try:
        row = db.query_one(
            f"""
            SELECT source_file
            FROM factory_statements
            WHERE {where}
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            tuple(params),
        )
        return row.get("source_file") if row else None
    except Exception:
        return None


def _load_rows(fabrika: Optional[str], hesap: Optional[str], limit: int = 500) -> list[dict]:
    try:
        if fabrika and hesap is not None:
            latest = _latest_source_file(fabrika, hesap)
            if not latest:
                return []
            return db.query(
                """
                SELECT tarih, fis_no, fis_turu, aciklama, borc, alacak,
                       bakiye, bakiye_yon, cari_hesap_kodu, fabrika, source_file
                FROM factory_statements
                WHERE fabrika = %s
                  AND COALESCE(cari_hesap_kodu, '') = %s
                  AND source_file = %s
                ORDER BY tarih DESC, id DESC
                LIMIT %s
                """,
                (fabrika, hesap, latest, limit),
            )

        if fabrika:
            return db.query(
                """
                WITH latest_batch AS (
                    SELECT DISTINCT ON (COALESCE(cari_hesap_kodu, ''))
                        COALESCE(cari_hesap_kodu, '') AS hesap_key,
                        source_file
                    FROM factory_statements
                    WHERE fabrika = %s
                    ORDER BY COALESCE(cari_hesap_kodu, ''),
                             created_at DESC NULLS LAST, id DESC
                )
                SELECT fs.tarih, fs.fis_no, fs.fis_turu, fs.aciklama, fs.borc, fs.alacak,
                       fs.bakiye, fs.bakiye_yon, fs.cari_hesap_kodu, fs.fabrika, fs.source_file
                FROM factory_statements fs
                INNER JOIN latest_batch lb
                    ON COALESCE(fs.cari_hesap_kodu, '') = lb.hesap_key
                   AND fs.source_file = lb.source_file
                WHERE fs.fabrika = %s
                ORDER BY fs.tarih DESC, fs.id DESC
                LIMIT %s
                """,
                (fabrika, fabrika, limit),
            )

        return db.query(
            """
            SELECT tarih, fis_no, fis_turu, aciklama, borc, alacak,
                   bakiye, bakiye_yon, cari_hesap_kodu, fabrika, source_file
            FROM factory_statements
            ORDER BY tarih DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
    except Exception:
        return []


def _load_fabrikalara() -> list[str]:
    try:
        return [r["fabrika"] for r in db.query("SELECT DISTINCT fabrika FROM factory_statements ORDER BY fabrika")]
    except Exception:
        return []


def _load_hesaplar(fabrika: Optional[str]) -> list[str]:
    if not fabrika:
        return []
    try:
        rows = db.query(
            "SELECT DISTINCT COALESCE(cari_hesap_kodu,'') AS k FROM factory_statements WHERE fabrika=%s ORDER BY k",
            (fabrika,),
        )
        return [r["k"] for r in rows if r["k"]]
    except Exception:
        return []


# ── HTML Şablonu ──────────────────────────────────────────────────────────────

_TEMPLATE = """
{% extends "base.html" %}
{% block title %}Fabrika Ekstre{% endblock %}
{% block content %}
<div class="page-header">
  <div>
    <h1>🏭 Fabrika Ekstre</h1>
    <div style="margin-top:6px;font-size:13px;color:var(--text-3);">
      Fabrikadan gelen PDF cari hesap ekstrelerini yükleyin; fatura satırlarını gelen e-faturalarla karşılaştırın.
    </div>
  </div>
  <a class="button secondary sm" href="{{ url_for('dashboard') }}">← Ana Sayfa</a>
</div>

{% if not tables_exist %}
<div class="alert error">
  ⚠️ <code>factory_statements</code> tablosu bulunamadı.
  <code>sql/migration_factory_statements.sql</code> dosyasını çalıştırın.
</div>
{% else %}

<!-- ── Yükleme + Özet Karşılaştırma ── -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">

  <div class="card">
    <div class="card-header"><h3>📤 Güncel Ekstre Yükle</h3></div>
    <div class="card-body">
      <form method="POST" action="{{ url_for('ekstre.upload') }}" enctype="multipart/form-data">
        <input type="hidden" name="csrf_token" value="{{ session.get('csrf_token') }}">
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:6px;">
            Ekstre PDF Dosyası
          </label>
          <input type="file" name="pdf_file" accept=".pdf" required
            style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;
                   font-size:13px;background:var(--bg-2);">
        </div>
        <button type="submit" class="button sm" style="width:100%;">⬆️ Yükle &amp; Kaydet</button>
      </form>
      <p style="font-size:11px;color:var(--text-3);margin-top:8px;">
        AK GİPS ve FULLBOARD cari hesap ekstreleri (PDF). Aynı satırlar tekrar yüklenince atlanır.
      </p>
    </div>
  </div>

  <div class="card" style="border-left:3px solid var(--primary);">
    <div class="card-header"><h3>🔍 Gelen Fatura Karşılaştırması</h3></div>
    <div class="card-body">
      {% if compare and not compare.error %}
      <p style="font-size:12px;color:var(--text-3);margin:0 0 12px;">
        {% if compare.date_from and compare.date_to %}
          {{ compare.date_from.strftime('%d.%m.%Y') }} – {{ compare.date_to.strftime('%d.%m.%Y') }}
        {% endif %}
        · {{ compare.fabrika }}
        {% if compare.source_file %} · {{ compare.source_file }}{% endif %}
      </p>
      <div class="summary-row" style="margin-bottom:12px;">
        <span class="summary-pill green"><span class="dot"></span>Eşleşti <strong>{{ compare.summary.eslesti }}</strong></span>
        <span class="summary-pill yellow"><span class="dot"></span>Fark <strong>{{ compare.summary.tutar_farki + compare.summary.tarih_farki }}</strong></span>
        <span class="summary-pill red"><span class="dot"></span>Ekstrede Yok <strong>{{ compare.summary.ekstrede_yok }}</strong></span>
        <span class="summary-pill red"><span class="dot"></span>Faturada Yok <strong>{{ compare.summary.faturada_yok }}</strong></span>
      </div>
      {% if compare.summary.eslesti == compare.summary.toplam and compare.summary.toplam > 0 %}
      <div class="alert success" style="margin:0;font-size:12px;padding:8px 12px;">
        ✅ Tüm fatura satırları gelen e-faturalarla bire bir eşleşiyor.
      </div>
      {% elif sel_fabrika %}
      <a class="button sm"
         href="{{ url_for('ekstre.index') }}?fabrika={{ sel_fabrika | urlencode }}{% if sel_hesap %}&hesap={{ sel_hesap | urlencode }}{% endif %}&compare=1">
        Detaylı Karşılaştırma →
      </a>
      {% endif %}
      {% elif compare and compare.error %}
      <div class="alert error" style="margin:0;font-size:12px;">{{ compare.error }}</div>
      {% elif sel_fabrika %}
      <p style="font-size:13px;color:var(--text-3);margin:0;">Ekstrede fatura satırı bulunamadı veya karşılaştırma yapılamadı.</p>
      {% else %}
      <p style="font-size:13px;color:var(--text-3);margin:0;">
        Fabrika filtresi seçin; ekstredeki fatura satırları gelen e-faturalarla otomatik karşılaştırılır
        (fiş no = fatura no).
      </p>
      {% endif %}
    </div>
  </div>

</div>

<!-- ── Özet Kartlar ── -->
{% if summary %}
<div class="card" style="margin-bottom:20px;">
  <div class="card-header">
    <h3>📊 Cari Hesap Özeti</h3>
    <span style="font-size:12px;color:var(--text-3);">Son yüklenen ekstre dosyasına göre</span>
  </div>
  <div class="card-body" style="padding:0;">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Fabrika</th>
            <th>Cari Hesap</th>
            <th class="num">Satır</th>
            <th class="num">Toplam Borç</th>
            <th class="num">Toplam Alacak</th>
            <th>İlk Tarih</th>
            <th>Son Tarih</th>
            <th>Kaynak Dosya</th>
            <th>İşlem</th>
          </tr>
        </thead>
        <tbody>
        {% for s in summary %}
        <tr>
          <td style="font-size:13px;">{{ s.fabrika }}</td>
          <td style="font-size:12px;color:var(--text-2);">{{ s.cari_hesap_kodu or '—' }}</td>
          <td class="num" style="font-size:12px;">{{ s.satir_adedi }}</td>
          <td class="num">{{ s.toplam_borc | format_tl }}</td>
          <td class="num">{{ s.toplam_alacak | format_tl }}</td>
          <td style="font-size:12px;color:var(--text-3);">
            {{ s.ilk_tarih.strftime('%d.%m.%Y') if s.ilk_tarih else '—' }}
          </td>
          <td style="font-size:12px;color:var(--text-3);">
            {{ s.son_tarih.strftime('%d.%m.%Y') if s.son_tarih else '—' }}
          </td>
          <td style="font-size:11px;color:var(--text-3);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="{{ s.source_file or '' }}{% if s.yukleme_tarihi %} · {{ s.yukleme_tarihi.strftime('%d.%m.%Y %H:%M') }}{% endif %}">
            {{ s.source_file or '—' }}
          </td>
          <td style="white-space:nowrap;">
            <a class="button secondary sm"
               href="{{ url_for('ekstre.index') }}?fabrika={{ s.fabrika | urlencode }}&hesap={{ (s.cari_hesap_kodu or '') | urlencode }}"
               style="font-size:11px;padding:2px 8px;">Göster</a>
            <a class="button sm"
               href="{{ url_for('ekstre.index') }}?fabrika={{ s.fabrika | urlencode }}&hesap={{ (s.cari_hesap_kodu or '') | urlencode }}&compare=1"
               style="font-size:11px;padding:2px 8px;margin-left:4px;">Karşılaştır</a>
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endif %}

<!-- ── Filtre ── -->
<div class="card" style="margin-bottom:16px;">
  <div class="card-body">
    <form method="GET" action="{{ url_for('ekstre.index') }}"
          style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
      <div>
        <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:4px;">Fabrika</label>
        <select name="fabrika"
          style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);">
          <option value="">— Tümü —</option>
          {% for f in fabrikalara %}
          <option value="{{ f }}" {{ 'selected' if f == sel_fabrika else '' }}>{{ f }}</option>
          {% endfor %}
        </select>
      </div>
      {% if hesaplar %}
      <div>
        <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:4px;">Cari Hesap</label>
        <select name="hesap"
          style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);">
          <option value="">— Tümü —</option>
          {% for h in hesaplar %}
          <option value="{{ h }}" {{ 'selected' if h == sel_hesap else '' }}>{{ h }}</option>
          {% endfor %}
        </select>
      </div>
      {% endif %}
      <button type="submit" class="button secondary sm">Filtrele</button>
      {% if sel_fabrika %}
      <a class="button sm"
         href="{{ url_for('ekstre.index') }}?fabrika={{ sel_fabrika | urlencode }}{% if sel_hesap %}&hesap={{ sel_hesap | urlencode }}{% endif %}&compare=1">
        🔍 Gelen Faturalarla Karşılaştır
      </a>
      {% endif %}
      {% if sel_fabrika or sel_hesap %}
      <a href="{{ url_for('ekstre.index') }}" class="button secondary sm">✕ Temizle</a>
      {% endif %}
    </form>
  </div>
</div>

{% if sel_fabrika and live_balance %}
<!-- ── Canlı Bakiye Takibi ── -->
<div class="card" style="margin-bottom:16px;border-left:3px solid #6366f1;">
  <div class="card-header">
    <h3>📈 Canlı Bakiye Takibi</h3>
    {% if live_balance.has_baseline %}
    <span style="font-size:12px;color:var(--text-3);">
      {{ live_balance.fabrika }}{% if live_balance.cari_hesap_kodu %} · {{ live_balance.cari_hesap_kodu }}{% endif %}
    </span>
    {% endif %}
  </div>
  <div class="card-body">
    <p style="font-size:12px;color:var(--text-3);margin:0 0 14px;line-height:1.5;">
      Son ekstre yüklemesinden sonra gelen faturalar otomatik düşülür.
      Bir sonraki ekstre gelene kadar tahmini bakiyeyi buradan takip edebilirsiniz.
    </p>

    {% if not live_balance.has_baseline %}
    <div class="alert warning" style="margin:0;font-size:13px;">
      {{ live_balance.message or 'Önce güncel ekstre PDF yükleyin.' }}
    </div>
    {% else %}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:16px;">
      <div style="padding:12px;background:var(--bg-2);border-radius:8px;">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:4px;">Ekstre baz bakiye</div>
        <strong style="font-size:18px;">
          {{ live_balance.baseline_balance | format_tl }}
          <span style="font-size:12px;color:{% if live_balance.baseline_balance_yon == 'A' %}#059669{% else %}#dc2626{% endif %};">
            ({{ live_balance.baseline_balance_yon }})
          </span>
        </strong>
      </div>
      <div style="padding:12px;background:var(--bg-2);border-radius:8px;">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:4px;">Baz tarih</div>
        <strong style="font-size:15px;">
          {{ live_balance.baseline_date.strftime('%d.%m.%Y') if live_balance.baseline_date else '—' }}
        </strong>
        {% if live_balance.baseline_source_file %}
        <div style="font-size:10px;color:var(--text-3);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
             title="{{ live_balance.baseline_source_file }}">
          {{ live_balance.baseline_source_file }}
        </div>
        {% endif %}
      </div>
      <div style="padding:12px;background:var(--bg-2);border-radius:8px;">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:4px;">Düşülen yeni fatura</div>
        <strong style="font-size:18px;">{{ live_balance.adjustment_count }}</strong>
      </div>
      <div style="padding:12px;background:rgba(99,102,241,0.08);border-radius:8px;border:1px solid rgba(99,102,241,0.2);">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:4px;">Güncel tahmini bakiye</div>
        <strong style="font-size:20px;color:#4338ca;">
          {{ live_balance.projected_balance | format_tl }}
          <span style="font-size:13px;color:{% if live_balance.projected_balance_yon == 'A' %}#059669{% else %}#dc2626{% endif %};">
            ({{ live_balance.projected_balance_yon }})
          </span>
        </strong>
      </div>
    </div>

    <p style="font-size:12px;color:var(--text-2);margin:0 0 12px;">{{ live_balance.message }}</p>

    {% if live_balance.adjustments %}
    <h4 style="font-size:13px;margin:0 0 8px;">Son ekstreden sonra düşülen faturalar</h4>
    <div class="table-wrap" style="max-height:280px;overflow-y:auto;">
      <table>
        <thead>
          <tr>
            <th>Fatura No</th>
            <th>Tarih</th>
            <th class="num">Tutar</th>
            <th class="num">Kalan Bakiye</th>
          </tr>
        </thead>
        <tbody>
        {% for adj in live_balance.adjustments %}
        <tr>
          <td>
            <a href="{{ url_for('invoice_incoming_detail', invoice_id=adj.invoice_id) }}"
               style="color:var(--primary);text-decoration:none;">
              <code style="font-size:11px;color:inherit;">{{ adj.invoice_id }}</code>
            </a>
          </td>
          <td style="font-size:12px;white-space:nowrap;">
            {{ adj.issue_date.strftime('%d.%m.%Y') if adj.issue_date else '—' }}
          </td>
          <td class="num" style="color:#dc2626;">−{{ adj.amount | format_tl }}</td>
          <td class="num" style="font-size:12px;">
            {{ adj.running_balance | format_tl }}
            <span style="font-size:10px;color:{% if adj.running_balance_yon == 'A' %}#059669{% else %}#dc2626{% endif %};">
              ({{ adj.running_balance_yon }})
            </span>
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% endif %}
    {% endif %}
  </div>
</div>
{% endif %}

<!-- ── İşlem Tablosu ── -->
<div class="card">
  <div class="card-header">
    <h3>📋 İşlem Satırları</h3>
    <span style="font-size:12px;color:var(--text-3);">{{ rows | length }} satır (en fazla 500)</span>
  </div>
  {% if rows %}
  <div class="card-body" style="padding:0;">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Tarih</th>
            <th>Fiş No</th>
            <th>Fiş Türü</th>
            <th>Açıklama</th>
            <th class="num">Borç</th>
            <th class="num">Alacak</th>
            <th class="num">Bakiye</th>
            <th>Cari Hesap</th>
          </tr>
        </thead>
        <tbody>
        {% for r in rows %}
        {% set is_alacak = r.alacak and not r.borc %}
        {% set is_borc   = r.borc  and not r.alacak %}
        <tr style="{% if is_alacak %}background:rgba(5,150,105,0.04);{% elif is_borc %}background:rgba(220,38,38,0.03);{% endif %}">
          <td style="font-size:12px;white-space:nowrap;">
            {{ r.tarih.strftime('%d.%m.%Y') if r.tarih else '—' }}
          </td>
          <td><code style="font-size:11px;">{{ r.fis_no or '—' }}</code></td>
          <td style="font-size:12px;">{{ r.fis_turu or '—' }}</td>
          <td style="font-size:12px;color:var(--text-2);max-width:200px;
                     overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="{{ r.aciklama or '' }}">
            {{ r.aciklama or '—' }}
          </td>
          <td class="num" style="color:{% if r.borc %}#dc2626{% else %}var(--text-3){% endif %};">
            {% if r.borc %}{{ r.borc | format_tl }}{% else %}—{% endif %}
          </td>
          <td class="num" style="color:{% if r.alacak %}#059669{% else %}var(--text-3){% endif %};">
            {% if r.alacak %}{{ r.alacak | format_tl }}{% else %}—{% endif %}
          </td>
          <td class="num" style="font-size:12px;">
            {% if r.bakiye %}
              {{ r.bakiye | format_tl }}
              <span style="font-size:10px;color:{% if r.bakiye_yon == 'A' %}#059669{% else %}#dc2626{% endif %};">
                ({{ r.bakiye_yon }})
              </span>
            {% else %}—{% endif %}
          </td>
          <td style="font-size:11px;color:var(--text-3);">{{ r.cari_hesap_kodu or '—' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% else %}
  <div class="card-body" style="text-align:center;padding:32px;color:var(--text-3);">
    Henüz ekstre verisi yok. Yukarıdan PDF yükleyin.
  </div>
  {% endif %}
</div>

{% if show_compare %}
<!-- ── Karşılaştırma Yan Paneli ── -->
<div class="side-panel-overlay open" id="compareOverlay"></div>
<aside class="side-panel open" id="comparePanel" aria-label="Ekstre karşılaştırma paneli">
  <div class="side-panel-header">
    <div>
      <h2 style="margin:0 0 4px;font-size:17px;">🔍 Ekstre ↔ Gelen Fatura</h2>
      <div style="font-size:12px;color:var(--text-3);line-height:1.5;">
        <strong>{{ compare.fabrika }}</strong>
        {% if compare.cari_hesap_kodu %}
          · Cari: <code>{{ compare.cari_hesap_kodu }}</code>
        {% else %}
          · Tüm cari hesaplar
        {% endif %}
        {% if compare.date_from and compare.date_to %}
          · {{ compare.date_from.strftime('%d.%m.%Y') }} – {{ compare.date_to.strftime('%d.%m.%Y') }}
        {% endif %}
      </div>
    </div>
    <a class="side-panel-close"
       href="{{ url_for('ekstre.index') }}?fabrika={{ sel_fabrika | urlencode }}{% if sel_hesap %}&hesap={{ sel_hesap | urlencode }}{% endif %}"
       title="Kapat">✕</a>
  </div>

  <div class="side-panel-body">
    {% if compare.error %}
    <div class="alert error">Karşılaştırma yapılamadı: {{ compare.error }}</div>
    {% elif compare.rows %}

    {% if sel_hesap %}
    <div class="alert warning" style="margin-bottom:14px;font-size:12px;">
      Seçili cari hesap filtresi uygulanıyor. Fabrika geneli için cari hesabı temizleyin.
    </div>
    {% endif %}

    <div class="summary-row">
      <span class="summary-pill all">Toplam <strong>{{ compare.summary.toplam }}</strong></span>
      <span class="summary-pill green"><span class="dot"></span>Eşleşti <strong>{{ compare.summary.eslesti }}</strong></span>
      <span class="summary-pill yellow"><span class="dot"></span>Fark <strong>{{ compare.summary.tutar_farki + compare.summary.tarih_farki }}</strong></span>
      <span class="summary-pill red"><span class="dot"></span>Ekstrede Yok <strong>{{ compare.summary.ekstrede_yok }}</strong></span>
      <span class="summary-pill red"><span class="dot"></span>Faturada Yok <strong>{{ compare.summary.faturada_yok }}</strong></span>
    </div>

    <div class="filter-tabs" id="compareFilterTabs" style="margin-bottom:14px;">
      <button class="filter-tab active" data-filter="all">Tümü</button>
      <button class="filter-tab tab-eslesti" data-filter="Eşleşti">✅ Eşleşti</button>
      <button class="filter-tab tab-yok" data-filter="Fark">⚠️ Fark</button>
      <button class="filter-tab tab-bulunamadi" data-filter="Ekstrede Yok">❌ Ekstrede Yok</button>
      <button class="filter-tab tab-bulunamadi" data-filter="Faturada Yok">❌ Faturada Yok</button>
    </div>

    <div class="table-wrap">
      <table id="compareTable">
        <thead>
          <tr>
            <th>Durum</th>
            <th>Ekstre Fiş No</th>
            <th>Ekstre Tarih</th>
            <th class="num">Ekstre Tutar</th>
            <th>Gelen Fatura No</th>
            <th>Fatura Tarih</th>
            <th class="num">Fatura Tutar</th>
            <th class="num">Fark</th>
          </tr>
        </thead>
        <tbody>
        {% for r in compare.rows %}
        {% set is_match = r.durum == 'Eşleşti' %}
        {% set is_missing_stmt = r.durum == 'Ekstrede Yok' %}
        {% set is_missing_inv = r.durum == 'Faturada Yok' %}
        {% set is_diff = not is_match and not is_missing_stmt and not is_missing_inv %}
        <tr class="{{ 'row-eslesti' if is_match else ('row-bulunamadi' if is_missing_stmt or is_missing_inv else 'row-yok') }}"
            data-durum="{{ r.durum }}"
            data-filter-group="{{ 'Fark' if is_diff else r.durum }}">
          <td><span class="badge {{ 'eslesti' if is_match else ('bulunamadi' if is_missing_stmt or is_missing_inv else 'yok') }}">{{ r.durum }}</span></td>
          <td><code style="font-size:11px;">{{ r.fis_no or '—' }}</code></td>
          <td style="font-size:12px;white-space:nowrap;">{{ r.ekstre_tarih.strftime('%d.%m.%Y') if r.ekstre_tarih else '—' }}</td>
          <td class="num">{{ r.ekstre_tutar | format_tl if r.ekstre_tutar else '—' }}</td>
          <td style="font-weight:500;">
            {% if r.invoice_id %}
              <a href="{{ url_for('invoice_incoming_detail', invoice_id=r.invoice_id) }}"
                 style="color:var(--primary);text-decoration:none;">
                <code style="font-size:11px;color:inherit;">{{ r.invoice_id }}</code>
              </a>
            {% else %}—{% endif %}
          </td>
          <td style="font-size:12px;white-space:nowrap;">{{ r.fatura_tarih.strftime('%d.%m.%Y') if r.fatura_tarih else '—' }}</td>
          <td class="num">{{ r.fatura_tutar | format_tl if r.fatura_tutar else '—' }}</td>
          <td class="num" style="{% if r.tutar_fark and r.tutar_fark != 0 %}color:var(--danger);font-weight:600;{% endif %}">
            {% if r.tutar_fark is not none %}{{ r.tutar_fark | format_tl }}{% else %}—{% endif %}
            {% if r.tarih_fark_gun and r.tarih_fark_gun != 0 %}
              <span style="display:block;font-size:10px;color:var(--warning);">{{ r.tarih_fark_gun }} gün</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>

    <p style="font-size:11px;color:var(--text-3);margin-top:14px;line-height:1.5;">
      Eşleştirme: ekstre <code>fis_no</code> = gelen fatura <code>invoice_id</code>.
      Yalnızca fatura fiş türleri karşılaştırılır. Tutar toleransı: ±0,01 TL.
    </p>

    {% else %}
    <div style="text-align:center;padding:40px 16px;color:var(--text-3);">
      Karşılaştırılacak fatura satırı bulunamadı.
    </div>
    {% endif %}
  </div>
</aside>

<script>
(function () {
  var closeUrl = "{{ url_for('ekstre.index') }}?fabrika={{ sel_fabrika | urlencode }}{% if sel_hesap %}&hesap={{ sel_hesap | urlencode }}{% endif %}";
  var overlay = document.getElementById('compareOverlay');
  if (overlay) overlay.addEventListener('click', function () { window.location.href = closeUrl; });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') window.location.href = closeUrl;
  });
  var tabs = document.querySelectorAll('#compareFilterTabs .filter-tab');
  var rows = document.querySelectorAll('#compareTable tbody tr');
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      tabs.forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var f = tab.dataset.filter;
      rows.forEach(function (row) {
        var g = row.dataset.filterGroup;
        var d = row.dataset.durum;
        row.style.display = (f === 'all' || g === f || d === f) ? '' : 'none';
      });
    });
  });
})();
</script>
{% endif %}

{% endif %}{# tables_exist #}
{% endblock %}
"""


# ── Route'lar ─────────────────────────────────────────────────────────────────

@ekstre_bp.route("/", methods=["GET"])
@_login_required
def index():
    tables_ok = _tables_exist()
    sel_fabrika = request.args.get("fabrika", "")
    sel_hesap = request.args.get("hesap", "")
    show_compare = request.args.get("compare") == "1" and bool(sel_fabrika)

    compare_result = None
    live_balance = None
    if sel_fabrika and tables_ok:
        compare_result = compare_ekstre_with_incoming(
            fabrika=sel_fabrika,
            cari_hesap_kodu=sel_hesap or None,
        )
        live_balance = compute_live_balance(
            fabrika=sel_fabrika,
            cari_hesap_kodu=sel_hesap or None,
        )

    return render_template_string(
        _TEMPLATE,
        tables_exist=tables_ok,
        summary=_load_summary() if tables_ok else [],
        rows=_load_rows(sel_fabrika or None, sel_hesap or None) if tables_ok else [],
        fabrikalara=_load_fabrikalara() if tables_ok else [],
        hesaplar=_load_hesaplar(sel_fabrika) if (tables_ok and sel_fabrika) else [],
        sel_fabrika=sel_fabrika,
        sel_hesap=sel_hesap,
        show_compare=show_compare,
        compare=compare_result,
        live_balance=live_balance,
    )


@ekstre_bp.route("/upload", methods=["POST"])
@_login_required
def upload():
    _validate_csrf()

    pdf_file = request.files.get("pdf_file")
    if not pdf_file or not pdf_file.filename:
        flash("Lütfen bir PDF dosyası seçin.", "error")
        return redirect(url_for("ekstre.index"))

    if not pdf_file.filename.lower().endswith(".pdf"):
        flash("Sadece PDF dosyaları kabul edilir.", "error")
        return redirect(url_for("ekstre.index"))

    original_name = pdf_file.filename
    tmp_path: Optional[Path] = None
    parsed_fabrika: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf_file.save(tmp)
            tmp_path = Path(tmp.name)

        from backend.core.factory_statement_parser import parse_factory_statement_pdf

        try:
            result = parse_factory_statement_pdf(tmp_path)
        except Exception as exc:
            flash(f"PDF okunamadı: {exc}", "error")
            return redirect(url_for("ekstre.index"))

        if not result.rows:
            warnings_str = "; ".join(result.warnings[:5]) if result.warnings else "Satır bulunamadı."
            flash(f"PDF'den işlem satırı çıkarılamadı. ({warnings_str})", "error")
            return redirect(url_for("ekstre.index"))

        try:
            stats = _write_rows(result.rows, source_file=original_name)
        except Exception as exc:
            flash(f"Veritabanına yazılamadı: {exc}", "error")
            return redirect(url_for("ekstre.index"))

        msg = (
            f"✅ {result.fabrika} — {stats['inserted']} satır eklendi"
            + (f", {stats['skipped']} tekrar atlandı" if stats["skipped"] else "")
            + (f", {stats['errors']} hata" if stats["errors"] else "")
            + f". (Toplam {len(result.rows)} satır parse edildi)"
        )
        if result.warnings:
            msg += f" | {len(result.warnings)} uyarı var."
        flash(msg, "success")
        parsed_fabrika = result.fabrika

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    if parsed_fabrika:
        return redirect(url_for("ekstre.index", fabrika=parsed_fabrika, compare=1))
    return redirect(url_for("ekstre.index"))


def register_ekstre_routes(app: Flask) -> None:
    app.register_blueprint(ekstre_bp)
