#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flask web panel for invoice operations."""

from __future__ import annotations

import os
import secrets
from functools import wraps
from pathlib import Path
from typing import Callable

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
from backend.web.actions import ACTIONS
from backend.web.jobs import create_job, dashboard_stats, ensure_web_job_schema, get_job, list_jobs


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("WEB_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("WEB_SESSION_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

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
        return render_template(
            "dashboard.html",
            stats=dashboard_stats(),
            jobs=list_jobs(limit=10),
            reports=list_reports(limit=10),
        )

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


if __name__ == "__main__":
    app.run(host=os.getenv("WEB_HOST", "127.0.0.1"), port=int(os.getenv("WEB_PORT", "8000")))
