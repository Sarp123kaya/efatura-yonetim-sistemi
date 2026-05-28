#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask route'ları — Fabrika Ekstre Yönetimi
==========================================
PDF ekstre dosyalarını yükleyip parse eder ve veritabanına kaydeder.
"""
from __future__ import annotations

import secrets
import tempfile
from decimal import Decimal
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
    try:
        return db.query(
            """
            SELECT
                fabrika,
                cari_hesap_kodu,
                COUNT(*)                                              AS satir_adedi,
                COALESCE(SUM(borc),  0)                              AS toplam_borc,
                COALESCE(SUM(alacak),0)                              AS toplam_alacak,
                MIN(tarih)                                           AS ilk_tarih,
                MAX(tarih)                                           AS son_tarih,
                MAX(bakiye)    FILTER (WHERE bakiye_yon = 'A')       AS son_bakiye_a,
                MAX(bakiye)    FILTER (WHERE bakiye_yon = 'B')       AS son_bakiye_b
            FROM factory_statements
            GROUP BY fabrika, cari_hesap_kodu
            ORDER BY fabrika, cari_hesap_kodu
            """
        )
    except Exception:
        return []


def _load_rows(fabrika: Optional[str], hesap: Optional[str], limit: int = 500) -> list[dict]:
    filters = []
    params: list[Any] = []
    if fabrika:
        filters.append("fabrika = %s")
        params.append(fabrika)
    if hesap:
        filters.append("COALESCE(cari_hesap_kodu,'') = %s")
        params.append(hesap)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(limit)
    try:
        return db.query(
            f"""
            SELECT tarih, fis_no, fis_turu, aciklama, borc, alacak,
                   bakiye, bakiye_yon, cari_hesap_kodu, fabrika, source_file
            FROM factory_statements
            {where}
            ORDER BY tarih DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
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
      Fabrikadan gelen PDF cari hesap ekstrelerini yükleyin ve işlem geçmişini görüntüleyin.
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

<!-- ── Yükleme Formu ── -->
<div class="card" style="margin-bottom:20px;">
  <div class="card-header"><h3>📤 PDF Ekstre Yükle</h3></div>
  <div class="card-body">
    <form method="POST" action="{{ url_for('ekstre.upload') }}" enctype="multipart/form-data">
      <input type="hidden" name="csrf_token" value="{{ session.get('csrf_token') }}">
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
        <div>
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:6px;">
            Ekstre PDF Dosyası
          </label>
          <input type="file" name="pdf_file" accept=".pdf" required
            style="padding:6px;border:1px solid var(--border);border-radius:6px;
                   font-size:13px;background:var(--bg-2);min-width:280px;">
        </div>
        <button type="submit" class="button sm">⬆️ Yükle &amp; Kaydet</button>
      </div>
    </form>
    <p style="font-size:11px;color:var(--text-3);margin-top:8px;">
      AK GİPS ve FULLBOARD formatları desteklenir. Aynı dosya tekrar yüklense mevcut satırlar atlanır.
    </p>
  </div>
</div>

<!-- ── Özet Kartlar ── -->
{% if summary %}
<div class="card" style="margin-bottom:20px;">
  <div class="card-header"><h3>📊 Cari Hesap Özeti</h3></div>
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
            <th>Filtre</th>
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
          <td>
            <a class="button secondary sm"
               href="{{ url_for('ekstre.index') }}?fabrika={{ s.fabrika | urlencode }}&hesap={{ (s.cari_hesap_kodu or '') | urlencode }}"
               style="font-size:11px;padding:2px 8px;">Göster</a>
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
      {% if sel_fabrika or sel_hesap %}
      <a href="{{ url_for('ekstre.index') }}" class="button secondary sm">✕ Temizle</a>
      {% endif %}
    </form>
  </div>
</div>

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

{% endif %}{# tables_exist #}
{% endblock %}
"""


# ── Route'lar ─────────────────────────────────────────────────────────────────

@ekstre_bp.route("/", methods=["GET"])
@_login_required
def index():
    tables_ok = _tables_exist()
    sel_fabrika = request.args.get("fabrika", "")
    sel_hesap   = request.args.get("hesap", "")
    return render_template_string(
        _TEMPLATE,
        tables_exist=tables_ok,
        summary=_load_summary() if tables_ok else [],
        rows=_load_rows(sel_fabrika or None, sel_hesap or None) if tables_ok else [],
        fabrikalara=_load_fabrikalara() if tables_ok else [],
        hesaplar=_load_hesaplar(sel_fabrika) if (tables_ok and sel_fabrika) else [],
        sel_fabrika=sel_fabrika,
        sel_hesap=sel_hesap,
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

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    return redirect(url_for("ekstre.index"))


# ── Kayıt yardımcısı ──────────────────────────────────────────────────────────

def register_ekstre_routes(app: Flask) -> None:
    app.register_blueprint(ekstre_bp)
