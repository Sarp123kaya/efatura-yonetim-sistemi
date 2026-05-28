#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask route'ları — AKG/FLL Alış Faturası Aktarımı
===================================================

Bu modül web paneline kayıt edilecek yeni route'ları sağlar.
Mevcut app.py'e dokunmadan, create_app() sonrasında blueprint olarak eklenir.

Kullanım (app.py değiştirilmeden, start_web_panel.py veya wsgi wrapper'da):
    from backend.web.purchase_import_routes import purchase_import_bp
    app.register_blueprint(purchase_import_bp)

Ya da mevcut app.py'de tek satır eklenerek (isteğe bağlı):
    from backend.web.purchase_import_routes import register_purchase_import_routes
    register_purchase_import_routes(app)
"""

from __future__ import annotations

import json
import secrets
from functools import wraps
from pathlib import Path
from typing import Any, Callable

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

from backend.web.actions_purchase_import import (
    list_factory_invoice_candidates,
    run_factory_purchase_import_dryrun,
    run_factory_purchase_import_execute,
)

purchase_import_bp = Blueprint("purchase_import", __name__, url_prefix="/purchase-import")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Auth yardımcıları (app.py'den kopyalanmaz, bağımsız tanımlanır) ──────────

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


# ── Inline HTML şablonu ───────────────────────────────────────────────────────
# Mevcut templates/ klasörüne yeni template dosyası eklemek yerine
# inline string kullanılır — böylece hiçbir mevcut dosya değişmez.

_TEMPLATE = """
{% extends "base.html" %}
{% block title %}AKG/FLL Alış Faturası Aktarımı{% endblock %}
{% block content %}
<div class="page-header">
  <div>
    <h1>🏭 AKG / FLL Alış Faturası Aktarımı</h1>
    <div style="margin-top:6px;font-size:13px;color:var(--text-3);">
      Kabul edilmiş e-faturaları İşbaşı'ya alış faturası olarak içeri alır.<br>
      <strong>Yalnızca AK GİPS (AKG) ve FULLBOARD (FLL)</strong> tedarikçi faturaları işlenir.
    </div>
  </div>
  <a class="button secondary sm" href="{{ url_for('dashboard') }}">← Ana Sayfa</a>
</div>

{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, msg in messages %}
<div class="alert {{ category }}" style="margin-bottom:12px;padding:10px 14px;border-radius:6px;
  background:{% if category=='error' %}#fef2f2{% else %}#f0fdf4{% endif %};
  border:1px solid {% if category=='error' %}#fca5a5{% else %}#86efac{% endif %};
  color:{% if category=='error' %}#b91c1c{% else %}#166534{% endif %};">
  {{ msg }}
</div>
{% endfor %}
{% endwith %}

<!-- ── Filtre Formu ── -->
<div class="card" style="margin-bottom:16px;">
  <div class="card-header"><h3>🔍 Aday Faturaları Listele</h3></div>
  <div class="card-body">
    <form method="POST" action="{{ url_for('purchase_import.list_candidates_view') }}">
      <input type="hidden" name="csrf_token" value="{{ session.csrf_token }}">
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
        <div>
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:4px;">Başlangıç Tarihi</label>
          <input type="date" name="start_date" value="{{ start_date or '2026-01-01' }}"
            style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
        </div>
        <div>
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:4px;">Bitiş Tarihi</label>
          <input type="date" name="end_date" value="{{ end_date or '' }}"
            style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;">
        </div>
        <div>
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:4px;">İşbaşı Şifresi</label>
          <input type="password" name="api_password" placeholder="Şifre (zorunlu)"
            style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:180px;">
        </div>
        <button type="submit" class="button secondary sm">Adayları Listele</button>
      </div>
    </form>
  </div>
</div>

<!-- ── Aday Listesi ── -->
{% if candidates is defined %}
<div class="card" style="margin-bottom:16px;">
  <div class="card-header">
    <h3>📋 Aktarım Adayları</h3>
    <span style="font-size:12px;color:var(--text-3);">{{ candidates | length }} fatura</span>
  </div>
  {% if candidates %}
  <div class="card-body" style="padding:0;">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Fatura No</th>
            <th>Tedarikçi</th>
            <th>Tarih</th>
            <th class="num">Tutar</th>
            <th>Status</th>
            <th>purchaseInvoiceId</th>
          </tr>
        </thead>
        <tbody>
        {% for c in candidates %}
        <tr>
          <td><code style="font-size:12px;">{{ c.invoice_id }}</code></td>
          <td style="font-size:13px;">{{ c.supplier[:40] }}</td>
          <td style="font-size:12px;color:var(--text-3);">{{ c.issue_date[:10] }}</td>
          <td class="num">{{ c.amount | default(0) | round(2) }} ₺</td>
          <td>
            <span style="font-size:12px;padding:2px 8px;border-radius:12px;
              background:{% if c.status_code == 1 %}#f0fdf4{% elif c.status_code == 0 %}#fefce8{% else %}#fef2f2{% endif %};
              color:{% if c.status_code == 1 %}#166534{% elif c.status_code == 0 %}#854d0e{% else %}#991b1b{% endif %};">
              {{ c.status or '-' }} ({{ c.status_code }})
            </span>
          </td>
          <td style="font-size:12px;color:var(--text-3);">{{ c.purchase_invoice_id or 0 }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Aktarım Formu -->
  <div class="card-body" style="border-top:1px solid var(--border);padding-top:16px;">
    <form method="POST" action="{{ url_for('purchase_import.execute_import') }}"
          onsubmit="return confirm('{{ candidates|length }} fatura İşbaşı\\'a alış faturası olarak aktarılacak. Emin misiniz?')">
      <input type="hidden" name="csrf_token" value="{{ session.csrf_token }}">
      <input type="hidden" name="start_date" value="{{ start_date or '2026-01-01' }}">
      <input type="hidden" name="end_date" value="{{ end_date or '' }}">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <input type="password" name="api_password" placeholder="İşbaşı şifresi (zorunlu)"
          style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:200px;">
        <button type="submit" class="button"
          style="background:#dc2626;border-color:#dc2626;"
          title="Seçili {{ candidates|length }} faturayı İşbaşı'ya alış faturası olarak aktarır">
          ⬆️ {{ candidates|length }} Faturayı Aktarım — GERÇEK
        </button>
      </div>
      <p style="font-size:11px;color:var(--text-3);margin-top:8px;">
        ⚠️ Bu işlem geri alınamaz. Önce dry-run sonucunu incelemeniz önerilir.
      </p>
    </form>
  </div>
  {% else %}
  <div class="card-body">
    <p style="color:var(--text-3);">Aktarım adayı AKG/FLL faturası bulunamadı.
      Tarih aralığını genişletmeyi deneyin.</p>
  </div>
  {% endif %}
</div>
{% endif %}

<!-- ── Rapor ── -->
{% if report is defined %}
<div class="card">
  <div class="card-header">
    <h3>{{ '🔍 Dry-Run Sonucu' if report.dry_run else '✅ Aktarım Sonucu' }}</h3>
    <span style="font-size:12px;color:var(--text-3);">{{ report.run_at }}</span>
  </div>
  <div class="card-body">
    <dl class="meta">
      <dt>Mod</dt><dd>{{ 'DRY-RUN' if report.dry_run else 'GERÇEK AKTARIM' }}</dd>
      <dt>Toplam Aday</dt><dd>{{ report.total_candidates }}</dd>
      <dt>Aktarıldı</dt><dd style="color:{% if report.imported > 0 %}#166534{% else %}var(--text-2){% endif %};">{{ report.imported }}</dd>
      <dt>Atlandı</dt><dd>{{ report.skipped }}</dd>
      <dt>Hata</dt><dd style="color:{% if report.failed > 0 %}#dc2626{% else %}var(--text-2){% endif %};">{{ report.failed }}</dd>
      {% if report.endpoint_discovered %}
      <dt>Endpoint</dt><dd><code style="font-size:12px;">{{ report.endpoint_discovered }}</code></dd>
      {% endif %}
    </dl>
  </div>
  {% if report.results %}
  <div class="card-body" style="padding:0;border-top:1px solid var(--border);">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Fatura No</th><th>Tedarikçi</th><th>Durum</th><th>purchaseInvoiceId</th><th>Hata</th></tr>
        </thead>
        <tbody>
        {% for r in report.results %}
        <tr>
          <td><code style="font-size:12px;">{{ r.invoice_id }}</code></td>
          <td style="font-size:13px;">{{ r.supplier[:35] }}</td>
          <td>
            {% if r.skipped %}<span style="color:#6b7280;">⏭ Atlandı</span>
            {% elif r.success %}<span style="color:#166534;">✅ Başarılı</span>
            {% else %}<span style="color:#dc2626;">❌ Hata</span>{% endif %}
          </td>
          <td style="font-size:12px;">{{ r.purchase_invoice_id or '—' }}</td>
          <td style="font-size:12px;color:#dc2626;max-width:300px;word-break:break-word;">{{ r.error[:120] if r.error else '—' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}
</div>
{% endif %}

{% endblock %}
"""


# ── Route'lar ─────────────────────────────────────────────────────────────────

@purchase_import_bp.route("/", methods=["GET"])
@_login_required
def index():
    return render_template_string(
        _TEMPLATE,
        start_date="2026-01-01",
        end_date="",
    )


@purchase_import_bp.route("/list", methods=["POST"])
@_login_required
def list_candidates_view():
    _validate_csrf()
    params = {
        "api_password": request.form.get("api_password", ""),
        "start_date": request.form.get("start_date", "2026-01-01"),
        "end_date": request.form.get("end_date", ""),
    }
    try:
        candidates = list_factory_invoice_candidates(params)
    except Exception as exc:
        flash(f"Fatura listesi alınamadı: {exc}", "error")
        candidates = []

    return render_template_string(
        _TEMPLATE,
        candidates=candidates,
        start_date=params["start_date"],
        end_date=params["end_date"],
    )


@purchase_import_bp.route("/execute", methods=["POST"])
@_login_required
def execute_import():
    _validate_csrf()
    params = {
        "api_password": request.form.get("api_password", ""),
        "start_date": request.form.get("start_date", "2026-01-01"),
        "end_date": request.form.get("end_date", ""),
        "import_endpoint": request.form.get("import_endpoint", ""),
    }
    try:
        report = run_factory_purchase_import_execute(params)
        if report.imported > 0:
            flash(f"{report.imported} fatura başarıyla aktarıldı.", "success")
        elif report.failed > 0:
            flash(f"{report.failed} faturada hata oluştu. Detaylar aşağıda.", "error")
        else:
            flash("Aktarılacak fatura bulunamadı.", "error")
    except Exception as exc:
        flash(f"Aktarım sırasında hata: {exc}", "error")
        from backend.core.purchase_invoice_importer import ImportReport
        report = ImportReport(dry_run=False)

    return render_template_string(
        _TEMPLATE,
        report=report,
        start_date=params["start_date"],
        end_date=params["end_date"],
    )


# ── Kayıt yardımcısı ─────────────────────────────────────────────────────────

def register_purchase_import_routes(app: Flask) -> None:
    """
    Mevcut Flask app'e purchase import blueprint'ini kayıt eder.

    app.py'de tek satır ekleyerek kullanım:
        from backend.web.purchase_import_routes import register_purchase_import_routes
        register_purchase_import_routes(app)
    """
    app.register_blueprint(purchase_import_bp)
