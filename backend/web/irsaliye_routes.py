#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask route'ları — İrsaliye kodu manuel düzeltme."""

from __future__ import annotations

import secrets
from functools import wraps
from typing import Any, Callable

from flask import (
    Blueprint,
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from backend.core.irsaliye_override import (
    apply_correction,
    clear_override,
    find_invoice,
    invoice_code_state,
    list_overridden_invoices,
    search_invoices,
)

irsaliye_bp = Blueprint("irsaliye", __name__, url_prefix="/irsaliye-duzelt")


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


def _invalidate_match_cache() -> None:
    try:
        from backend.web.app import _invalidate_match_cache as invalidate

        invalidate()
    except Exception:
        pass


def _enrich_invoice(row: dict[str, Any]) -> dict[str, Any]:
    state = invoice_code_state(row)
    return {**row, **state}


@irsaliye_bp.route("", methods=["GET"])
@_login_required
def index():
    query = request.args.get("q", "").strip()
    invoice_ref = request.args.get("invoice", "").strip() or query
    selected = None
    search_results: list[dict[str, Any]] = []

    if invoice_ref:
        row = find_invoice(invoice_ref)
        if row:
            selected = _enrich_invoice(row)
        else:
            search_results = [_enrich_invoice(r) for r in search_invoices(invoice_ref)]

    overrides = list_overridden_invoices(limit=50)
    return render_template(
        "irsaliye_duzelt.html",
        query=query or invoice_ref,
        selected=selected,
        search_results=search_results,
        overrides=overrides,
    )


@irsaliye_bp.route("/apply", methods=["POST"])
@_login_required
def apply():
    _validate_csrf()
    invoice_ref = request.form.get("invoice_ref", "").strip()
    from_code = request.form.get("from_code", "").strip()
    to_code = request.form.get("to_code", "").strip()

    if not invoice_ref or not from_code or not to_code:
        flash("Fatura no, kaynak kod ve hedef kod zorunludur.", "error")
        return redirect(url_for("irsaliye.index", invoice=invoice_ref))

    result = apply_correction(invoice_ref, from_code, to_code)
    if not result.get("ok"):
        flash(result.get("error", "Düzeltme uygulanamadı."), "error")
        return redirect(url_for("irsaliye.index", invoice=invoice_ref))

    msg = (
        f"{result['invoice_no']}: {result['from_code']} → {result['to_code']} "
        f"(override: {', '.join(result['override'])})"
    )
    if result.get("warning"):
        flash(f"{msg} — Uyarı: {result['warning']}", "warning")
    else:
        flash(msg, "success")

    _invalidate_match_cache()
    return redirect(url_for("irsaliye.index", invoice=result["invoice_no"]))


@irsaliye_bp.route("/clear", methods=["POST"])
@_login_required
def clear():
    _validate_csrf()
    invoice_ref = request.form.get("invoice_ref", "").strip()
    if not invoice_ref:
        flash("Fatura no gerekli.", "error")
        return redirect(url_for("irsaliye.index"))

    result = clear_override(invoice_ref)
    if not result.get("ok"):
        flash(result.get("error", "Override kaldırılamadı."), "error")
        return redirect(url_for("irsaliye.index", invoice=invoice_ref))

    flash(f"{result['invoice_no']}: override kaldırıldı, API kodu kullanılacak.", "success")
    _invalidate_match_cache()
    return redirect(url_for("irsaliye.index", invoice=result["invoice_no"]))


def register_irsaliye_routes(app: Flask) -> None:
    app.register_blueprint(irsaliye_bp)
