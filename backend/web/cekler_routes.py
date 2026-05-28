#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask route'ları — Çek Yönetimi
================================

Excel veya görüntü dosyalarından çek verilerini okuyup veritabanına kaydeder.
Mevcut app.py'e dokunmadan blueprint olarak eklenir.

Kullanım (app.py'de):
    from backend.web.cekler_routes import register_cekler_routes
    register_cekler_routes(app)
"""

from __future__ import annotations

import secrets
import sys
import tempfile
from datetime import date
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

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

# ── statement_extractor paketini yükle ────────────────────────────────────────
_CEKLER_DIR = Path(__file__).resolve().parent.parent.parent / "çekler"
if str(_CEKLER_DIR) not in sys.path:
    sys.path.insert(0, str(_CEKLER_DIR))

from backend.core.config import config  # noqa: E402  (path manipulation above)
from backend.core.db import db  # noqa: E402

# ── Blueprint ─────────────────────────────────────────────────────────────────
cekler_bp = Blueprint("cekler", __name__, url_prefix="/cekler")


# ── Auth yardımcıları ─────────────────────────────────────────────────────────

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


# ── DB yardımcıları (psycopg2 üzerinden) ─────────────────────────────────────

def _upsert_import_session(conn, session_obj) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO check_import_sessions (
            id, source_type, source_file, status, account_code, account_name, company_name,
            total_rows, parsed_count, warning_count, error_count, message, created_at, completed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            parsed_count = EXCLUDED.parsed_count,
            warning_count = EXCLUDED.warning_count,
            error_count = EXCLUDED.error_count,
            message = EXCLUDED.message,
            completed_at = EXCLUDED.completed_at
        """,
        (
            session_obj.import_session_id,
            session_obj.source_type.value,
            session_obj.source_file,
            session_obj.status.value,
            session_obj.statement_metadata.account_code,
            session_obj.statement_metadata.account_name,
            session_obj.statement_metadata.company_name,
            session_obj.total_rows,
            session_obj.parsed_count,
            session_obj.warning_count,
            session_obj.error_count,
            session_obj.message,
            session_obj.created_at,
            session_obj.completed_at,
        ),
    )


def _find_existing_check_id(conn, record) -> Optional[int]:
    from statement_extractor.src.validators import duplicate_key
    customer_name, check_no, bank, maturity_date, amount = duplicate_key(record)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id FROM checks
        WHERE COALESCE(account_name, '') = COALESCE(%s, '')
          AND check_no = %s
          AND bank_name = %s
          AND maturity_date = %s
          AND COALESCE(amount, 0) = COALESCE(%s, 0)
        LIMIT 1
        """,
        (customer_name, check_no, bank, maturity_date, amount),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _insert_check(conn, record, source_file: Optional[str] = None) -> int:
    from datetime import datetime
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO checks (
            account_code, account_name, company_name, movement_type, check_no, bank_name,
            sent_to, amount, currency, maturity_date, transaction_date, document_date, voucher_no,
            document_no, status, source_file, source_page, raw_description, raw_line,
            parse_warning, source_type, import_session_id, review_status, source_row_index,
            source_sheet, source_image_region, created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            None,
            record.customer_name,
            record.company_name,
            record.movement_type.value,
            record.check_no,
            record.bank,
            record.sent_to,
            record.amount,
            record.currency,
            record.maturity_date,
            record.transaction_date,
            record.document_date,
            record.voucher_no,
            record.document_no,
            "PORTFOLIO",
            source_file or record.source_file,
            record.source_page,
            record.raw_description,
            record.raw_line,
            record.parse_warning,
            record.source_type.value,
            record.import_session_id,
            record.review_status.value,
            record.source_row_index,
            record.source_sheet,
            record.source_image_region,
            record.created_at,
            datetime.utcnow(),
        ),
    )
    row = cur.fetchone()
    return int(row[0])


def _insert_import_row(
    conn,
    record,
    canonical_check_id: Optional[int] = None,
    duplicate_of_check_id: Optional[int] = None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO check_import_rows (
            import_session_id, canonical_check_id, source_type, source_file, source_sheet,
            source_row_index, check_no, bank_name, amount, currency, maturity_date,
            transaction_date, document_date, account_name, company_name, review_status,
            sent_to, raw_description, raw_line, parse_warning, duplicate_of_check_id, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record.import_session_id,
            canonical_check_id,
            record.source_type.value,
            record.source_file,
            record.source_sheet,
            record.source_row_index,
            record.check_no,
            record.bank,
            record.amount,
            record.currency,
            record.maturity_date,
            record.transaction_date,
            record.document_date,
            record.customer_name,
            record.company_name,
            record.review_status.value,
            record.sent_to,
            record.raw_description,
            record.raw_line,
            record.parse_warning,
            duplicate_of_check_id,
            record.created_at,
        ),
    )


def _write_import_result(import_result) -> dict[str, int]:
    """İmport sonucunu psycopg2 ile veritabanına yazar."""
    inserted = skipped = errors = 0
    with db.get_connection(auto_commit=False) as conn:
        _upsert_import_session(conn, import_result.import_session)
        for record in import_result.records:
            try:
                existing_id = _find_existing_check_id(conn, record)
                if existing_id is not None:
                    _insert_import_row(conn, record, duplicate_of_check_id=existing_id)
                    skipped += 1
                else:
                    new_id = _insert_check(conn, record, source_file=import_result.import_session.source_file)
                    _insert_import_row(conn, record, canonical_check_id=new_id)
                    inserted += 1
            except Exception:
                errors += 1
        conn.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors, "total": len(import_result.records)}


def _db_tables_exist() -> bool:
    try:
        db.query_one("SELECT 1 FROM checks LIMIT 1")
        return True
    except Exception:
        return False


def _load_checks_summary() -> dict[str, Any]:
    try:
        row = db.query_one(
            """
            SELECT
                COUNT(*) AS toplam,
                COALESCE(SUM(amount), 0) AS toplam_tutar,
                COUNT(*) FILTER (WHERE maturity_date < CURRENT_DATE) AS vadesi_gecmis,
                COUNT(*) FILTER (WHERE maturity_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30) AS bu_ay_vadeli,
                COUNT(*) FILTER (WHERE maturity_date > CURRENT_DATE + 30) AS ileri_vadeli
            FROM checks
            WHERE review_status IN ('APPROVED', 'IMPORTED')
            """
        )
        return dict(row) if row else {}
    except Exception:
        return {}


def _load_checks_list(limit: int = 300) -> list[dict]:
    try:
        return db.query(
            """
            SELECT
                id, check_no, bank_name, account_name, company_name, amount, currency,
                maturity_date, status, review_status, source_type, source_file, sent_to,
                created_at
            FROM checks
            ORDER BY
                CASE WHEN maturity_date >= CURRENT_DATE THEN 0 ELSE 1 END,
                maturity_date ASC,
                created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    except Exception:
        return []


def _load_import_sessions(limit: int = 20) -> list[dict]:
    try:
        return db.query(
            """
            SELECT id, source_type, source_file, status, account_name, company_name,
                   total_rows, parsed_count, warning_count, error_count, message, created_at
            FROM check_import_sessions
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    except Exception:
        return []


# ── HTML Şablonu ──────────────────────────────────────────────────────────────

_TEMPLATE = """
{% extends "base.html" %}
{% block title %}Çek Yönetimi{% endblock %}
{% block content %}
<div class="page-header">
  <div>
    <h1>💳 Çek Yönetimi</h1>
    <div style="margin-top:6px;font-size:13px;color:var(--text-3);">
      Excel veya görüntü dosyalarından çek verilerini içeri aktarın ve takip edin.
    </div>
  </div>
  <a class="button secondary sm" href="{{ url_for('dashboard') }}">← Ana Sayfa</a>
</div>

{% if not tables_exist %}
<div class="alert error" role="alert" style="margin-bottom:16px;">
  ⚠️ Çek tabloları veritabanında bulunamadı. <code>sql/migration_check_pool.sql</code> migration'ını çalıştırın.
</div>
{% else %}

<!-- ── Özet Kartlar ── -->
{% if summary %}
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;">
  <div class="card" style="padding:16px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:var(--accent);">{{ summary.toplam or 0 }}</div>
    <div style="font-size:12px;color:var(--text-3);margin-top:4px;">Toplam Çek</div>
  </div>
  <div class="card" style="padding:16px;text-align:center;">
    <div style="font-size:18px;font-weight:700;color:var(--accent);">{{ summary.toplam_tutar | default(0) | float | round(0) | int | format_tl }}</div>
    <div style="font-size:12px;color:var(--text-3);margin-top:4px;">Toplam Tutar</div>
  </div>
  <div class="card" style="padding:16px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#dc2626;">{{ summary.vadesi_gecmis or 0 }}</div>
    <div style="font-size:12px;color:var(--text-3);margin-top:4px;">Vadesi Geçmiş</div>
  </div>
  <div class="card" style="padding:16px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#d97706;">{{ summary.bu_ay_vadeli or 0 }}</div>
    <div style="font-size:12px;color:var(--text-3);margin-top:4px;">30 Gün İçinde</div>
  </div>
  <div class="card" style="padding:16px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#059669;">{{ summary.ileri_vadeli or 0 }}</div>
    <div style="font-size:12px;color:var(--text-3);margin-top:4px;">İleri Vadeli</div>
  </div>
</div>
{% endif %}

<!-- ── Yükleme Formu ── -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">

  <!-- Excel Yükleme -->
  <div class="card">
    <div class="card-header"><h3>📊 Excel Yükle</h3></div>
    <div class="card-body">
      <form method="POST" action="{{ url_for('cekler.upload_excel') }}" enctype="multipart/form-data">
        <input type="hidden" name="csrf_token" value="{{ session.get('csrf_token') }}">
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:6px;">
            Excel Dosyası (.xlsx / .xlsm)
          </label>
          <input type="file" name="excel_file" accept=".xlsx,.xlsm" required
            style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);">
        </div>
        <button type="submit" class="button sm" style="width:100%;">
          ⬆️ Excel Yükle &amp; Kaydet
        </button>
      </form>
      <p style="font-size:11px;color:var(--text-3);margin-top:8px;">
        Ekstre veya çek listesi içeren Excel dosyalarını yükleyin. Mevcut çekler atlanır.
      </p>
    </div>
  </div>

  <!-- Görüntü Yükleme -->
  <div class="card">
    <div class="card-header"><h3>🖼️ Görüntü (OCR) Yükle</h3></div>
    <div class="card-body">
      <form method="POST" action="{{ url_for('cekler.upload_image') }}" enctype="multipart/form-data">
        <input type="hidden" name="csrf_token" value="{{ session.get('csrf_token') }}">
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:var(--text-2);display:block;margin-bottom:6px;">
            Çek Görüntüsü (.jpg / .jpeg / .png)
          </label>
          <input type="file" name="image_file" accept=".jpg,.jpeg,.png" required
            style="width:100%;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);">
        </div>
        <button type="submit" class="button secondary sm" style="width:100%;">
          🔍 OCR ile Çıkar &amp; Kaydet
        </button>
      </form>
      <p style="font-size:11px;color:var(--text-3);margin-top:8px;">
        OCR ile çek verisini okur. Tesseract kurulu olmalı. Sonuç "İnceleme Bekliyor" olarak kaydedilir.
      </p>
    </div>
  </div>

</div>

<!-- ── Çek Tablosu ── -->
<div class="card" style="margin-bottom:20px;">
  <div class="card-header">
    <h3>📋 Çek Listesi</h3>
    <span style="font-size:12px;color:var(--text-3);">{{ checks | length }} çek</span>
  </div>
  {% if checks %}
  <div class="card-body" style="padding:0;">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Vade Tarihi</th>
            <th>Çek No</th>
            <th>Banka</th>
            <th>Müşteri / Keşideci</th>
            <th class="num">Tutar</th>
            <th>Durum</th>
            <th>İnceleme</th>
            <th>Kaynak</th>
          </tr>
        </thead>
        <tbody>
        {% for c in checks %}
        {% set today = today_date %}
        {% set overdue = c.maturity_date and c.maturity_date < today %}
        {% set soon = c.maturity_date and not overdue and (c.maturity_date - today).days <= 30 %}
        <tr style="{% if overdue %}background:rgba(220,38,38,0.04);{% elif soon %}background:rgba(217,119,6,0.04);{% endif %}">
          <td style="font-size:13px;font-weight:{% if overdue or soon %}600{% else %}400{% endif %};
                     color:{% if overdue %}#dc2626{% elif soon %}#d97706{% else %}var(--text-1){% endif %};">
            {{ c.maturity_date.strftime('%d.%m.%Y') if c.maturity_date else '-' }}
            {% if overdue %}<span style="font-size:10px;color:#dc2626;"> ⚠️</span>{% endif %}
          </td>
          <td><code style="font-size:12px;">{{ c.check_no or '-' }}</code></td>
          <td style="font-size:13px;">{{ c.bank_name or '-' }}</td>
          <td style="font-size:12px;color:var(--text-2);">
            {{ c.account_name or '' }}
            {% if c.company_name and c.company_name != c.account_name %}
              <span style="color:var(--text-3);">/ {{ c.company_name }}</span>
            {% endif %}
          </td>
          <td class="num" style="font-weight:600;">
            {{ c.amount | format_tl if c.amount else '-' }}
          </td>
          <td>
            <span style="font-size:11px;padding:2px 8px;border-radius:12px;
              background:{% if c.status == 'PORTFOLIO' %}#f0f9ff{% elif c.status == 'CASHED' %}#f0fdf4{% elif c.status == 'RETURNED' %}#fef2f2{% else %}#fafafa{% endif %};
              color:{% if c.status == 'PORTFOLIO' %}#0369a1{% elif c.status == 'CASHED' %}#166534{% elif c.status == 'RETURNED' %}#991b1b{% else %}var(--text-2){% endif %};">
              {{ c.status or '-' }}
            </span>
          </td>
          <td>
            <span style="font-size:11px;padding:2px 8px;border-radius:12px;
              background:{% if c.review_status == 'APPROVED' %}#f0fdf4{% elif c.review_status == 'NEEDS_REVIEW' %}#fefce8{% elif c.review_status == 'REJECTED' %}#fef2f2{% else %}#fafafa{% endif %};
              color:{% if c.review_status == 'APPROVED' %}#166534{% elif c.review_status == 'NEEDS_REVIEW' %}#854d0e{% elif c.review_status == 'REJECTED' %}#991b1b{% else %}var(--text-2){% endif %};">
              {% if c.review_status == 'APPROVED' %}Onaylandı
              {% elif c.review_status == 'NEEDS_REVIEW' %}İnceleme Bekliyor
              {% elif c.review_status == 'IMPORTED' %}Aktarıldı
              {% elif c.review_status == 'REJECTED' %}Reddedildi
              {% else %}{{ c.review_status }}{% endif %}
            </span>
          </td>
          <td style="font-size:11px;color:var(--text-3);">{{ c.source_type or '-' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% else %}
  <div class="card-body">
    <p style="color:var(--text-3);text-align:center;padding:24px 0;">
      Henüz çek kaydı yok. Yukarıdan Excel veya görüntü yükleyin.
    </p>
  </div>
  {% endif %}
</div>

<!-- ── Son Import Oturumları ── -->
{% if sessions %}
<div class="card">
  <div class="card-header"><h3>📥 Son Yükleme Oturumları</h3></div>
  <div class="card-body" style="padding:0;">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Tarih</th>
            <th>Dosya</th>
            <th>Kaynak</th>
            <th>Durum</th>
            <th class="num">Satır</th>
            <th class="num">Çekilen</th>
            <th class="num">Uyarı</th>
            <th class="num">Hata</th>
          </tr>
        </thead>
        <tbody>
        {% for s in sessions %}
        <tr>
          <td style="font-size:12px;color:var(--text-3);">{{ s.created_at | format_dt }}</td>
          <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            {{ s.source_file or '-' }}
          </td>
          <td style="font-size:12px;">{{ s.source_type or '-' }}</td>
          <td>
            <span style="font-size:11px;padding:2px 8px;border-radius:12px;
              background:{% if s.status == 'IMPORTED' %}#f0fdf4{% elif s.status == 'FAILED' %}#fef2f2{% else %}#fafafa{% endif %};
              color:{% if s.status == 'IMPORTED' %}#166534{% elif s.status == 'FAILED' %}#991b1b{% else %}var(--text-2){% endif %};">
              {{ s.status }}
            </span>
          </td>
          <td class="num" style="font-size:12px;">{{ s.total_rows }}</td>
          <td class="num" style="font-size:12px;">{{ s.parsed_count }}</td>
          <td class="num" style="font-size:12px;color:{% if s.warning_count > 0 %}#d97706{% else %}var(--text-3){% endif %};">{{ s.warning_count }}</td>
          <td class="num" style="font-size:12px;color:{% if s.error_count > 0 %}#dc2626{% else %}var(--text-3){% endif %};">{{ s.error_count }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endif %}

{% endif %}{# tables_exist #}
{% endblock %}
"""


# ── Route'lar ─────────────────────────────────────────────────────────────────

@cekler_bp.route("/", methods=["GET"])
@_login_required
def index():
    tables_exist = _db_tables_exist()
    return render_template_string(
        _TEMPLATE,
        tables_exist=tables_exist,
        summary=_load_checks_summary() if tables_exist else {},
        checks=_load_checks_list() if tables_exist else [],
        sessions=_load_import_sessions() if tables_exist else [],
        today_date=date.today(),
    )


@cekler_bp.route("/upload-excel", methods=["POST"])
@_login_required
def upload_excel():
    _validate_csrf()

    file = request.files.get("excel_file")
    if not file or not file.filename:
        flash("Lütfen bir Excel dosyası seçin.", "error")
        return redirect(url_for("cekler.index"))

    filename = file.filename
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        flash("Sadece .xlsx veya .xlsm dosyaları kabul edilir.", "error")
        return redirect(url_for("cekler.index"))

    # Geçici dosyaya kaydet
    suffix = Path(filename).suffix
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp)
            tmp_path = Path(tmp.name)

        try:
            from statement_extractor.src.excel_importer import extract_checks_from_excel
        except ImportError as exc:
            flash(f"statement_extractor modülü yüklenemedi: {exc}", "error")
            return redirect(url_for("cekler.index"))

        try:
            import_result = extract_checks_from_excel(tmp_path)
        except Exception as exc:
            flash(f"Excel okunamadı: {exc}", "error")
            return redirect(url_for("cekler.index"))

        # Orijinal dosya adını koru
        import_result.import_session.source_file = filename
        for record in import_result.records:
            record.source_file = filename

        try:
            stats = _write_import_result(import_result)
        except Exception as exc:
            flash(f"Veritabanına yazılamadı: {exc}", "error")
            return redirect(url_for("cekler.index"))

        flash(
            f"Excel aktarıldı — {stats['inserted']} yeni çek eklendi, "
            f"{stats['skipped']} tekrar atlandı"
            + (f", {stats['errors']} hata" if stats["errors"] else "") + ".",
            "success",
        )

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    return redirect(url_for("cekler.index"))


@cekler_bp.route("/upload-image", methods=["POST"])
@_login_required
def upload_image():
    _validate_csrf()

    file = request.files.get("image_file")
    if not file or not file.filename:
        flash("Lütfen bir görüntü dosyası seçin.", "error")
        return redirect(url_for("cekler.index"))

    filename = file.filename
    if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        flash("Sadece .jpg, .jpeg veya .png dosyaları kabul edilir.", "error")
        return redirect(url_for("cekler.index"))

    suffix = Path(filename).suffix
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp)
            tmp_path = Path(tmp.name)

        try:
            from statement_extractor.src.image_ocr_reader import (
                OcrUnavailableError,
                extract_checks_from_image,
            )
        except ImportError as exc:
            flash(f"statement_extractor modülü yüklenemedi: {exc}", "error")
            return redirect(url_for("cekler.index"))

        try:
            import_result = extract_checks_from_image(tmp_path)
        except OcrUnavailableError as exc:
            flash(f"OCR çalıştırılamadı: {exc}", "error")
            return redirect(url_for("cekler.index"))
        except Exception as exc:
            flash(f"Görüntü işlenemedi: {exc}", "error")
            return redirect(url_for("cekler.index"))

        import_result.import_session.source_file = filename
        for record in import_result.records:
            record.source_file = filename

        if not import_result.records:
            warning_msgs = "; ".join(w.message for w in import_result.warnings)
            flash(
                f"OCR çek verisi çıkaramadı. "
                + (f"Uyarılar: {warning_msgs}" if warning_msgs else "Görüntü okunamadı."),
                "error",
            )
            return redirect(url_for("cekler.index"))

        try:
            stats = _write_import_result(import_result)
        except Exception as exc:
            flash(f"Veritabanına yazılamadı: {exc}", "error")
            return redirect(url_for("cekler.index"))

        flash(
            f"Görüntü aktarıldı — {stats['inserted']} çek eklendi (inceleme gerektirir)"
            + (f", {stats['errors']} hata" if stats["errors"] else "") + ".",
            "success",
        )

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    return redirect(url_for("cekler.index"))


# ── Kayıt yardımcısı ──────────────────────────────────────────────────────────

def register_cekler_routes(app: Flask) -> None:
    """Mevcut Flask app'e çekler blueprint'ini kayıt eder."""
    app.register_blueprint(cekler_bp)
