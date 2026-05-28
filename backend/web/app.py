#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask web panel for invoice operations."""

from __future__ import annotations

import os
import secrets
import sys
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from backend.core.config import PROJECT_ROOT, config
from backend.core.db import db
from backend.web.actions import ACTIONS
from backend.web.jobs import create_job, dashboard_stats, ensure_web_job_schema, get_job, list_jobs

# Ensure scripts/ is on the path (actions.py already does this, but be explicit)
_scripts_dir = str(PROJECT_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# ── Matching preview cache ────────────────────────────────────────────────────
_MATCH_CACHE: dict[str, Any] = {}
_MATCH_CACHE_TTL = 600  # seconds (10 minutes)


def _invalidate_match_cache() -> None:
    _MATCH_CACHE.clear()


def _fetch_extra_stats() -> dict[str, Any]:
    """Fetch last_invoice_date and last_api_fetch from the database."""
    extra: dict[str, Any] = {"last_invoice_date": None, "last_api_fetch": None}
    try:
        row = db.query_one("SELECT MAX(issue_date) AS v FROM outgoing_invoices")
        if row:
            extra["last_invoice_date"] = row["v"]
    except Exception:
        pass
    try:
        row = db.query_one("SELECT MAX(end_time) AS v FROM agent_runs WHERE status = 'success'")
        if row:
            extra["last_api_fetch"] = row["v"]
    except Exception:
        pass
    return extra


def get_matching_preview() -> dict[str, Any]:
    """Return matching data from cache or freshly computed.

    Returns a dict with keys:
      rows              – list of row dicts
      cached_at         – datetime when cache was last filled (or None)
      error             – error string if something failed (or None)
      summary           – dict with Eşleşti/Bulunamadı/İrsaliye kodu yok counts
      last_invoice_date – MAX(issue_date) from outgoing_invoices (or None)
      last_api_fetch    – MAX(end_time) from agent_runs where status='success' (or None)
    """
    now = time.monotonic()
    if _MATCH_CACHE and now - _MATCH_CACHE.get("_ts", 0) < _MATCH_CACHE_TTL:
        return {
            "rows": _MATCH_CACHE["rows"],
            "cached_at": _MATCH_CACHE["cached_at"],
            "summary": _MATCH_CACHE["summary"],
            "last_invoice_date": _MATCH_CACHE.get("last_invoice_date"),
            "last_api_fetch": _MATCH_CACHE.get("last_api_fetch"),
            "error": None,
        }

    try:
        from scripts.pg_invoice_matcher import get_matching_data

        df = get_matching_data()
        rows = df.to_dict("records")

        summary = {
            "eslesti": int((df["Durum"] == "Eşleşti").sum()),
            "bulunamadi": int((df["Durum"] == "Bulunamadı").sum()),
            "kod_yok": int((df["Durum"] == "İrsaliye kodu yok").sum()),
            "toplam": len(df),
        }

        extra = _fetch_extra_stats()
        _MATCH_CACHE.clear()
        _MATCH_CACHE.update({
            "rows": rows,
            "cached_at": datetime.now(),
            "summary": summary,
            "_ts": now,
            **extra,
        })

        return {
            "rows": rows,
            "cached_at": _MATCH_CACHE["cached_at"],
            "summary": summary,
            "last_invoice_date": extra["last_invoice_date"],
            "last_api_fetch": extra["last_api_fetch"],
            "error": None,
        }

    except Exception as exc:
        cached_rows = _MATCH_CACHE.get("rows", [])
        cached_at = _MATCH_CACHE.get("cached_at")
        summary = _MATCH_CACHE.get("summary", {"eslesti": 0, "bulunamadi": 0, "kod_yok": 0, "toplam": 0})
        extra = _fetch_extra_stats()
        return {
            "rows": cached_rows,
            "cached_at": cached_at,
            "summary": summary,
            "last_invoice_date": extra["last_invoice_date"],
            "last_api_fetch": extra["last_api_fetch"],
            "error": str(exc),
        }


# ─────────────────────────────────────────────────────────────────────────────


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("WEB_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB (Excel ve görüntü yüklemeleri için)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("WEB_SESSION_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    @app.template_filter("format_dt")
    def format_dt_filter(value) -> str:
        if not value:
            return "-"
        if isinstance(value, (int, float)):
            try:
                value = datetime.fromtimestamp(value)
            except (OSError, OverflowError, ValueError):
                return str(value)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        try:
            return value.strftime("%d.%m.%Y %H:%M")
        except AttributeError:
            return str(value)

    @app.template_filter("format_tl")
    def format_tl_filter(value) -> str:
        try:
            f = float(value or 0)
            return f"{f:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return str(value or "-")

    @app.template_filter("urlencode")
    def urlencode_filter(value: str) -> str:
        from urllib.parse import quote_plus
        return quote_plus(str(value or ""))

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "actions": ACTIONS,
            "project_root": PROJECT_ROOT,
            "setup_warnings": setup_warnings(),
        }

    @app.route("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok"}, 200

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            expected_user = os.getenv("WEB_ADMIN_USER", "admin")
            expected_password = os.getenv("WEB_ADMIN_PASSWORD", "admin")
            if not os.getenv("WEB_ADMIN_PASSWORD") and not is_local_request():
                flash("Varsayılan parola ile dış ağdan giriş engellendi. WEB_ADMIN_PASSWORD ayarlayın.", "error")
                return render_template("login.html"), 403
            if secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password):
                session.clear()
                session["user"] = username
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))
            flash("Kullanıcı adı veya parola hatalı.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        validate_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        ensure_web_job_schema()
        matching = get_matching_preview()
        return render_template(
            "dashboard.html",
            stats=dashboard_stats(),
            matching=matching,
        )

    @app.route("/refresh-matching", methods=["POST"])
    @login_required
    def refresh_matching():
        validate_csrf()
        _invalidate_match_cache()
        flash("Eşleştirme verisi yenileniyor — sayfa tekrar açıldığında güncel veri gösterilecek.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/jobs", methods=["GET"])
    @login_required
    def jobs():
        return render_template("jobs.html", jobs=list_jobs(limit=50))

    @app.route("/jobs", methods=["POST"])
    @login_required
    def start_job():
        validate_csrf()
        action_key = request.form.get("action")
        if action_key not in ACTIONS:
            abort(400, "Bilinmeyen aksiyon.")

        action = ACTIONS[action_key]
        if action.requires_confirmation and request.form.get("confirm") != "on":
            flash("Bu işlem için onay kutusunu işaretleyin.", "error")
            return redirect(url_for("dashboard"))

        params = {
            "start_date": request.form.get("start_date", "").strip(),
            "end_date": request.form.get("end_date", "").strip(),
            "output_dir": request.form.get("output_dir", "kayıtlar").strip() or "kayıtlar",
            "refresh_xml": request.form.get("refresh_xml") == "on",
            "refresh_despatch_descriptions": request.form.get("refresh_despatch_descriptions") == "on",
            "skip_reverse": request.form.get("skip_reverse") == "on",
            "skip_despatches": request.form.get("skip_despatches") == "on",
            "all_excel": request.form.get("all_excel") == "on",
            "skip_ingest": request.form.get("skip_ingest") == "on",
            "despatch_description_pdf": request.form.get("despatch_description_pdf", "data/incoming_despatch_pdfs").strip()
            or "data/incoming_despatch_pdfs",
        }
        api_password = request.form.get("api_password", "")
        if api_password:
            params["api_password"] = api_password
        job_id = create_job(action_key, params, created_by=session.get("user"))
        flash(f"Job kuyruğa alındı: {action.label}", "success")
        return redirect(url_for("job_detail", job_id=job_id))

    @app.route("/jobs/<job_id>")
    @login_required
    def job_detail(job_id: str):
        job = get_job(job_id)
        if not job:
            abort(404)
        return render_template("job_detail.html", job=job)

    @app.route("/invoice/outgoing/<invoice_id>")
    @login_required
    def invoice_outgoing_detail(invoice_id: str):
        import json as _json

        invoice = db.query_one(
            """
            SELECT o.id, o.invoice_no, o.issue_date, o.firm_name, o.total_tl, o.taxable_amount,
                   o.description,
                   COALESCE(o.irsaliye_codes_override, o.irsaliye_codes) AS irsaliye_codes,
                   o.change_type, o.last_change_at, o.created_at, o.updated_at,
                   x.line_items, x.fetched_at AS xml_fetched_at
            FROM outgoing_invoices o
            LEFT JOIN outgoing_invoice_xml_cache x ON x.id = o.id
            WHERE o.id = %s
            """,
            (invoice_id,),
        )
        if not invoice:
            abort(404)
        for field in ("irsaliye_codes", "line_items"):
            val = invoice.get(field)
            if isinstance(val, str):
                try:
                    invoice[field] = _json.loads(val)
                except Exception:
                    invoice[field] = []
            elif val is None:
                invoice[field] = []
        return render_template("invoice_detail_outgoing.html", invoice=invoice)

    @app.route("/invoice/incoming/<invoice_id>")
    @login_required
    def invoice_incoming_detail(invoice_id: str):
        import json as _json
        from backend.core.ubl_line_parser import parse_invoice_lines

        invoice = db.query_one(
            """
            SELECT i.invoice_id, i.uuid, i.issue_date, i.supplier, i.supplier_tckn_vkn,
                   i.amount, i.total_vat_base, i.currency,
                   COALESCE(i.despatch_ids_override, i.despatch_ids) AS despatch_ids,
                   i.change_type, i.last_change_at, i.created_at, i.updated_at,
                   c.despatch_documents, c.xml_content, c.fetched_at AS xml_fetched_at
            FROM incoming_invoices i
            LEFT JOIN incoming_invoice_xml_cache c ON c.uuid = i.uuid
            WHERE i.invoice_id = %s
            """,
            (invoice_id,),
        )
        if not invoice:
            abort(404)
        for field in ("despatch_ids", "despatch_documents"):
            val = invoice.get(field)
            if isinstance(val, str):
                try:
                    invoice[field] = _json.loads(val)
                except Exception:
                    invoice[field] = []
            elif val is None:
                invoice[field] = []
        invoice["line_items"] = parse_invoice_lines(invoice.get("xml_content") or "")
        return render_template("invoice_detail_incoming.html", invoice=invoice)

    @app.route("/stats")
    @login_required
    def stats():
        outgoing_daily = db.query(
            """
            SELECT issue_date::date AS gun, COUNT(*) AS adet, COALESCE(SUM(total_tl),0) AS toplam
            FROM outgoing_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY gun ORDER BY gun DESC
            """
        )
        outgoing_weekly = db.query(
            """
            SELECT DATE_TRUNC('week', issue_date)::date AS hafta_baslangic,
                   COUNT(*) AS adet, COALESCE(SUM(total_tl),0) AS toplam
            FROM outgoing_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '12 weeks'
            GROUP BY hafta_baslangic ORDER BY hafta_baslangic DESC
            """
        )
        outgoing_monthly = db.query(
            """
            SELECT TO_CHAR(issue_date, 'YYYY-MM') AS ay, COUNT(*) AS adet, COALESCE(SUM(total_tl),0) AS toplam
            FROM outgoing_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY ay ORDER BY ay DESC
            """
        )

        def _group_by_supplier(rows: list[dict]) -> dict[str, list[dict]]:
            result: dict[str, list[dict]] = {}
            for row in rows:
                sup = row["supplier"]
                if sup not in result:
                    result[sup] = []
                result[sup].append(row)
            return result

        _SUPPLIER_FILTER = (
            'AK GİPS YAPI KİMYASALLARI İNŞ. ENERJİ ÜR A.Ş.',
            'AK GİPS YAPI KİMYASALLARI İNŞAAT ENERJİ ÜRETİM ANONİM ŞİRKETİ',
            'FULLBOARD YAPI ELEMANLARI A.Ş.',
            'FULLBOARD YAPI ELEMANLARI ANONİM ŞİRKETİ',
        )

        incoming_daily_by_supplier = _group_by_supplier(db.query(
            """
            SELECT issue_date::date AS gun, supplier,
                   COUNT(*) AS adet, COALESCE(SUM(amount),0) AS toplam
            FROM incoming_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '30 days'
              AND supplier = ANY(%s)
            GROUP BY gun, supplier ORDER BY gun DESC, supplier
            """,
            (list(_SUPPLIER_FILTER),),
        ))
        incoming_weekly_by_supplier = _group_by_supplier(db.query(
            """
            SELECT DATE_TRUNC('week', issue_date)::date AS hafta_baslangic, supplier,
                   COUNT(*) AS adet, COALESCE(SUM(amount),0) AS toplam
            FROM incoming_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '12 weeks'
              AND supplier = ANY(%s)
            GROUP BY hafta_baslangic, supplier ORDER BY hafta_baslangic DESC, supplier
            """,
            (list(_SUPPLIER_FILTER),),
        ))
        incoming_monthly_by_supplier = _group_by_supplier(db.query(
            """
            SELECT TO_CHAR(issue_date, 'YYYY-MM') AS ay, supplier,
                   COUNT(*) AS adet, COALESCE(SUM(amount),0) AS toplam
            FROM incoming_invoices
            WHERE issue_date >= CURRENT_DATE - INTERVAL '12 months'
              AND supplier = ANY(%s)
            GROUP BY ay, supplier ORDER BY ay DESC, supplier
            """,
            (list(_SUPPLIER_FILTER),),
        ))

        return render_template(
            "stats.html",
            outgoing_daily=outgoing_daily,
            outgoing_weekly=outgoing_weekly,
            outgoing_monthly=outgoing_monthly,
            incoming_daily_by_supplier=incoming_daily_by_supplier,
            incoming_weekly_by_supplier=incoming_weekly_by_supplier,
            incoming_monthly_by_supplier=incoming_monthly_by_supplier,
        )

    @app.route("/customers")
    @login_required
    def customers():
        rows = db.query(
            """
            SELECT
                f.firm_id, f.name, f.tax_id, f.city, f.district,
                f.balance, f.beginning_balance, f.beginning_balance_date,
                f.currency, f.ar_ap_type, f.balance_updated_at, f.is_active,
                COUNT(o.id)               AS fatura_adedi,
                COALESCE(SUM(o.total_tl), 0) AS toplam_ciro,
                MAX(o.issue_date)         AS son_fatura_tarihi
            FROM firm_cards f
            LEFT JOIN outgoing_invoices o
                   ON o.raw_json->>'firmVknNo' = f.tax_id
                  AND o.issue_date >= '2026-01-01'
            GROUP BY f.firm_id, f.name, f.tax_id, f.city, f.district,
                     f.balance, f.beginning_balance, f.beginning_balance_date,
                     f.currency, f.ar_ap_type, f.balance_updated_at, f.is_active
            ORDER BY toplam_ciro DESC NULLS LAST
            """
        )

        cek_rows = db.query(
            """
            SELECT account_name,
                   COUNT(*)            AS cek_adedi,
                   COALESCE(SUM(amount), 0) AS cek_toplam,
                   MAX(maturity_date)  AS son_vade
            FROM checks
            WHERE review_status = 'APPROVED'
            GROUP BY account_name
            """
        )
        cek_by_name = {r["account_name"]: r for r in cek_rows}

        customers_out = []
        for c in rows:
            c = dict(c)
            firm_name = c.get("name") or ""
            cek_info = cek_by_name.get(firm_name) or {}
            c["cek_adedi"] = cek_info.get("cek_adedi", 0)
            c["cek_toplam"] = cek_info.get("cek_toplam", 0)
            c["cek_son_vade"] = cek_info.get("son_vade")
            customers_out.append(c)

        return render_template("customers.html", customers=customers_out)

    @app.route("/customers/<firm_id>")
    @login_required
    def customer_detail(firm_id: str):
        firm = db.query_one(
            "SELECT * FROM firm_cards WHERE firm_id = %s", (firm_id,)
        )
        if not firm:
            abort(404)

        invoices = db.query(
            """
            SELECT id, invoice_no, issue_date, total_tl, taxable_amount, description,
                   COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes
            FROM outgoing_invoices
            WHERE raw_json->>'firmVknNo' = %s
              AND issue_date >= '2026-01-01'
            ORDER BY issue_date DESC
            """,
            (firm["tax_id"],),
        )

        monthly_summary = db.query(
            """
            SELECT TO_CHAR(issue_date, 'YYYY-MM') AS ay,
                   COUNT(*) AS adet,
                   COALESCE(SUM(total_tl), 0) AS toplam
            FROM outgoing_invoices
            WHERE raw_json->>'firmVknNo' = %s
              AND issue_date >= '2026-01-01'
            GROUP BY ay ORDER BY ay DESC
            """,
            (firm["tax_id"],),
        )

        import json as _json
        raw = firm.get("raw_json")
        if isinstance(raw, str):
            try:
                firm["raw_json"] = _json.loads(raw)
            except Exception:
                firm["raw_json"] = {}
        for inv in invoices:
            val = inv.get("irsaliye_codes")
            if isinstance(val, str):
                try:
                    inv["irsaliye_codes"] = _json.loads(val)
                except Exception:
                    inv["irsaliye_codes"] = []
            elif val is None:
                inv["irsaliye_codes"] = []

        checks = db.query(
            """
            SELECT id, check_no, bank_name, amount, currency,
                   maturity_date, transaction_date, status, review_status,
                   raw_description
            FROM checks
            WHERE account_name = %s
              AND review_status = 'APPROVED'
            ORDER BY maturity_date DESC
            """,
            (firm["name"],),
        )

        return render_template(
            "customer_detail.html",
            firm=firm,
            invoices=invoices,
            monthly_summary=monthly_summary,
            checks=checks,
        )

    @app.route("/customers/<firm_id>/profit")
    @login_required
    def customer_profit(firm_id: str):
        from collections import defaultdict
        from decimal import Decimal, InvalidOperation

        firm = db.query_one("SELECT * FROM firm_cards WHERE firm_id = %s", (firm_id,))
        if not firm:
            abort(404)

        import json as _json
        raw = firm.get("raw_json")
        if isinstance(raw, str):
            try:
                firm["raw_json"] = _json.loads(raw)
            except Exception:
                firm["raw_json"] = {}

        def to_float(v):
            if v is None:
                return 0.0
            try:
                return float(Decimal(str(v)))
            except (InvalidOperation, TypeError, ValueError):
                return 0.0

        rows = db.query(
            """
            SELECT giden_fatura_no, irsaliye_kodu, tarih,
                   giden_tutar, gelen_tutar, fark_tl, 'AK' AS fabrika,
                   outgoing_invoice_id
            FROM factory_a_kar WHERE giden_firma = %s
            UNION ALL
            SELECT giden_fatura_no, irsaliye_kodu, tarih,
                   giden_tutar, gelen_tutar, fark_tl, 'FULL' AS fabrika,
                   outgoing_invoice_id
            FROM factory_f_kar WHERE giden_firma = %s
            UNION ALL
            SELECT giden_fatura_no, irsaliye_kodu, tarih,
                   giden_tutar, gelen_tutar, fark_tl, 'TERMA' AS fabrika,
                   outgoing_invoice_id
            FROM factory_t_kar WHERE giden_firma = %s
            ORDER BY tarih DESC
            """,
            (firm["name"], firm["name"], firm["name"]),
        )

        rows = [dict(r) for r in rows]
        for r in rows:
            r["giden_tutar"] = to_float(r.get("giden_tutar"))
            r["gelen_tutar"] = to_float(r.get("gelen_tutar"))
            r["fark_tl"] = to_float(r.get("fark_tl"))
            if r["giden_tutar"] > 0:
                r["kar_yuzde"] = r["fark_tl"] / r["giden_tutar"] * 100
            else:
                r["kar_yuzde"] = 0.0
            r["negatif"] = r["fark_tl"] < 0

        toplam_kar = sum(r["fark_tl"] for r in rows)
        toplam_satis = sum(r["giden_tutar"] for r in rows)
        toplam_maliyet = sum(r["gelen_tutar"] for r in rows)
        kar_marji_yuzde = (toplam_kar / toplam_satis * 100) if toplam_satis else 0.0

        aylik_ozet: dict = {}
        for r in rows:
            tarih = r.get("tarih")
            ay = str(tarih)[:7] if tarih else "Bilinmiyor"
            if ay not in aylik_ozet:
                aylik_ozet[ay] = {"satis": 0.0, "maliyet": 0.0, "kar": 0.0, "adet": 0}
            aylik_ozet[ay]["satis"] += r["giden_tutar"]
            aylik_ozet[ay]["maliyet"] += r["gelen_tutar"]
            aylik_ozet[ay]["kar"] += r["fark_tl"]
            aylik_ozet[ay]["adet"] += 1
        for ay_data in aylik_ozet.values():
            ay_data["marj"] = (ay_data["kar"] / ay_data["satis"] * 100) if ay_data["satis"] else 0.0
        aylik_ozet = dict(sorted(aylik_ozet.items(), reverse=True)[:24])

        fabrika_ozet: dict = {}
        for r in rows:
            fab = r["fabrika"]
            if fab not in fabrika_ozet:
                fabrika_ozet[fab] = {"satis": 0.0, "maliyet": 0.0, "kar": 0.0, "adet": 0}
            fabrika_ozet[fab]["satis"] += r["giden_tutar"]
            fabrika_ozet[fab]["maliyet"] += r["gelen_tutar"]
            fabrika_ozet[fab]["kar"] += r["fark_tl"]
            fabrika_ozet[fab]["adet"] += 1
        for fab_data in fabrika_ozet.values():
            fab_data["marj"] = (fab_data["kar"] / fab_data["satis"] * 100) if fab_data["satis"] else 0.0

        return render_template(
            "customer_profit.html",
            firm=firm,
            rows=rows,
            toplam_kar=toplam_kar,
            toplam_satis=toplam_satis,
            toplam_maliyet=toplam_maliyet,
            kar_marji=kar_marji_yuzde,
            aylik_ozet=aylik_ozet,
            fabrika_ozet=fabrika_ozet,
        )

    @app.route("/customers/<firm_id>/price-analysis")
    @login_required
    def customer_price_analysis(firm_id: str):
        import json as _json
        from collections import defaultdict
        from decimal import Decimal, InvalidOperation

        firm = db.query_one("SELECT * FROM firm_cards WHERE firm_id = %s", (firm_id,))
        if not firm:
            abort(404)

        raw = firm.get("raw_json")
        if isinstance(raw, str):
            try:
                firm["raw_json"] = _json.loads(raw)
            except Exception:
                firm["raw_json"] = {}

        rows = db.query(
            """
            SELECT
                o.id          AS invoice_id,
                o.issue_date::date AS tarih,
                o.invoice_no,
                item->>'Ürün Kodu'                          AS urun_kodu,
                item->>'Ürün Adı'                           AS urun_adi,
                (item->>'Miktar')::numeric                  AS miktar,
                item->>'Birim'                              AS birim,
                (item->>'Birim Fiyat')::numeric             AS birim_fiyat,
                (item->>'KDV Oranı')::numeric               AS kdv_orani,
                (item->>'KDV Dahil Birim Fiyat')::numeric   AS kdv_dahil_fiyat,
                (item->>'Satır Tutarı')::numeric            AS satir_tutari
            FROM outgoing_invoices o
            JOIN outgoing_invoice_xml_cache x ON x.id = o.id
            CROSS JOIN LATERAL jsonb_array_elements(x.line_items) AS item
            WHERE o.raw_json->>'firmVknNo' = %s
              AND jsonb_array_length(x.line_items) > 0
            ORDER BY o.issue_date DESC, item->>'Ürün Adı'
            """,
            (firm["tax_id"],),
        )

        def to_float(v):
            if v is None:
                return None
            try:
                return float(Decimal(str(v)))
            except (InvalidOperation, TypeError, ValueError):
                return None

        detail_rows = []
        for r in rows:
            detail_rows.append({
                "invoice_id": r["invoice_id"],
                "tarih": r["tarih"],
                "invoice_no": r["invoice_no"],
                "urun_kodu": r["urun_kodu"] or "",
                "urun_adi": r["urun_adi"] or "—",
                "miktar": to_float(r["miktar"]),
                "birim": r["birim"] or "",
                "birim_fiyat": to_float(r["birim_fiyat"]),
                "kdv_orani": to_float(r["kdv_orani"]),
                "kdv_dahil_fiyat": to_float(r["kdv_dahil_fiyat"]),
                "satir_tutari": to_float(r["satir_tutari"]),
            })

        by_product: dict = defaultdict(list)
        for row in detail_rows:
            key = row["urun_kodu"] or row["urun_adi"]
            by_product[key].append(row)

        products = []
        for key, prows in by_product.items():
            prows_sorted = sorted(prows, key=lambda x: x["tarih"] or "")
            prices = [r["birim_fiyat"] for r in prows_sorted if r["birim_fiyat"] is not None]
            amounts = [r["satir_tutari"] for r in prows_sorted if r["satir_tutari"] is not None]
            miktarlar = [r["miktar"] for r in prows_sorted if r["miktar"] is not None]

            last_row = next((r for r in reversed(prows_sorted) if r["birim_fiyat"] is not None), None)
            son_fiyat = last_row["birim_fiyat"] if last_row else None
            son_tarih = last_row["tarih"] if last_row else None

            total_amount = sum(amounts) if amounts else None
            total_miktar = sum(miktarlar) if miktarlar else None

            if total_amount and total_miktar and total_miktar > 0:
                avg_fiyat = total_amount / total_miktar
            elif prices:
                avg_fiyat = sum(prices) / len(prices)
            else:
                avg_fiyat = None

            min_fiyat = min(prices) if prices else None
            max_fiyat = max(prices) if prices else None

            trend = "→"
            if len(prices) >= 2:
                last3 = prices[-3:]
                diffs = [last3[i + 1] - last3[i] for i in range(len(last3) - 1)]
                if all(d > 0 for d in diffs):
                    trend = "↑"
                elif all(d < 0 for d in diffs):
                    trend = "↓"
                else:
                    trend = "→"

            invoice_ids = list({r["invoice_id"] for r in prows})

            products.append({
                "urun_kodu": prows[0]["urun_kodu"],
                "urun_adi": prows[0]["urun_adi"],
                "birim": prows[0]["birim"],
                "fatura_adedi": len(invoice_ids),
                "toplam_miktar": total_miktar,
                "son_fiyat": son_fiyat,
                "son_tarih": son_tarih,
                "avg_fiyat": avg_fiyat,
                "min_fiyat": min_fiyat,
                "max_fiyat": max_fiyat,
                "trend": trend,
                "anchor": key.replace(" ", "_").replace("/", "_"),
            })

        products.sort(key=lambda p: -(p["fatura_adedi"] or 0))

        return render_template(
            "customer_price_analysis.html",
            firm=firm,
            products=products,
            detail_rows=detail_rows,
        )

    @app.route("/reports")
    @login_required
    def reports():
        return render_template("reports.html", reports=list_reports(limit=200))

    @app.route("/download/<path:relative_path>")
    @login_required
    def download(relative_path: str):
        path = safe_download_path(relative_path)
        return send_file(path, as_attachment=True)

    return app


def login_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def validate_csrf() -> None:
    token = request.form.get("csrf_token", "")
    if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
        abort(400, "Geçersiz form oturumu.")


def setup_warnings() -> list[str]:
    warnings = []
    if not os.getenv("WEB_ADMIN_PASSWORD"):
        warnings.append("WEB_ADMIN_PASSWORD ayarlı değil; varsayılan admin/admin sadece yerel test için uygundur.")
    if not os.getenv("WEB_SECRET_KEY"):
        warnings.append("WEB_SECRET_KEY ayarlı değil; servis restart sonrası oturumlar geçersiz olur.")
    if not config.ISBASI_PASSWORD:
        warnings.append("ISBASI_PASSWORD boş; API gerektiren joblarda İşbaşı şifresini formdan girin.")
    return warnings


def is_local_request() -> bool:
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return remote_addr in {"127.0.0.1", "::1", "localhost"}


def list_reports(limit: int = 50) -> list[dict]:
    reports_dir = PROJECT_ROOT / "kayıtlar"
    if not reports_dir.exists():
        return []
    files = sorted(reports_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:limit]:
        stat = path.stat()
        result.append(
            {
                "name": path.name,
                "relative_path": str(path.relative_to(PROJECT_ROOT)),
                "size_kb": round(stat.st_size / 1024, 1),
                "mtime": stat.st_mtime,
            }
        )
    return result


def safe_download_path(relative_path: str) -> Path:
    root = PROJECT_ROOT.resolve()
    path = (PROJECT_ROOT / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        abort(404)
    if path.suffix.lower() != ".xlsx" or not path.exists():
        abort(404)
    return path


app = create_app()

# ── Ek blueprint'ler (mevcut route'lara dokunmaz) ─────────────────────────────
try:
    from backend.web.purchase_import_routes import register_purchase_import_routes
    register_purchase_import_routes(app)
except Exception:
    pass

try:
    from backend.web.cekler_routes import register_cekler_routes
    register_cekler_routes(app)
except Exception:
    pass

try:
    from backend.web.ekstre_routes import register_ekstre_routes
    register_ekstre_routes(app)
except Exception:
    pass

try:
    from backend.web.alis_fatura_routes import register_alis_fatura_routes
    register_alis_fatura_routes(app)
except Exception:
    pass


if __name__ == "__main__":
    app.run(host=os.getenv("WEB_HOST", "127.0.0.1"), port=int(os.getenv("WEB_PORT", "8000")))
