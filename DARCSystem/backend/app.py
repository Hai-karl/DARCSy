"""Flask application factory and REST API.

Run (from the project root, the folder that contains `backend/` and `defect_analysis/`):
    python -m backend.seed          # create tables, demo users, sample data
    flask --app backend.app run     # http://127.0.0.1:5000
"""
import io
import json
import os

import pandas as pd
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from defect_analysis import (RootCauseClassifier, ValidationError, filter_records,
                             pareto_analysis, prepare_records, validate_records)
from defect_analysis.config import PERMISSIONS, ROLES
from defect_analysis.services import (dashboard_summary, suggest_root_causes,
                                      train_root_cause_model)

from .alerts import evaluate_new_records, smtp_mailer
from .auth import auth_required, make_token
from .bundle import build_bundle
from .config import Config
from .models import AuditLog, DefectRecord, User, db
from .security import validate_password

_FIELDS = DefectRecord.COLS


def _records_df() -> pd.DataFrame:
    rows = [r.to_dict() for r in DefectRecord.query.all()]
    if not rows:
        return pd.DataFrame()
    return prepare_records(pd.DataFrame(rows), strict=False)


def _scoped_df() -> pd.DataFrame:
    """Records the signed-in user may see: a user with an assigned line sees only that line."""
    df, line = _records_df(), getattr(g.user, "assigned_line", None)
    return df[df["production_line"] == line].reset_index(drop=True) if line and not df.empty else df


def _audit(action, detail=""):
    db.session.add(AuditLog(user_id=g.user.id if "user" in g else None, action=action, detail=detail[:255]))


def _to_json(df: pd.DataFrame):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _clean(row: dict) -> dict:
    """Keep known fields; turn blanks/NaN into None."""
    out = {}
    for k in _FIELDS:
        v = row.get(k)
        out[k] = None if (v is None or (isinstance(v, float) and pd.isna(v)) or v == "") else v
    return out


def _bootstrap_admin(app):
    """Create the first IT Administrator from environment variables (for hosts without a shell)."""
    c = app.config
    if not (c["BOOTSTRAP_ADMIN_USERNAME"] and c["BOOTSTRAP_ADMIN_PASSWORD"]):
        return
    if User.query.filter_by(role="IT Administrator").first():
        return
    problems = validate_password(c["BOOTSTRAP_ADMIN_PASSWORD"], c["BOOTSTRAP_ADMIN_USERNAME"], c["BOOTSTRAP_ADMIN_EMAIL"])
    if problems:
        app.logger.error("BOOTSTRAP_ADMIN_PASSWORD rejected: %s", " ".join(problems))
        return
    u = User(username=c["BOOTSTRAP_ADMIN_USERNAME"], full_name="Administrator", role="IT Administrator",
             email=c["BOOTSTRAP_ADMIN_EMAIL"] or None)
    u.set_password(c["BOOTSTRAP_ADMIN_PASSWORD"])
    db.session.add(u)
    try:
        db.session.commit()
    except IntegrityError:                                   # another worker created it first
        db.session.rollback()
        return
    app.logger.warning("Created first IT Administrator '%s'. Remove BOOTSTRAP_ADMIN_PASSWORD now.", u.username)


def create_app(config=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.from_object(Config)
    app.json.sort_keys = False          # keep Pareto categories in ranked order
    if config:
        app.config.update(config)
    cfg = app.config
    origins = [o.strip() for o in cfg["CORS_ORIGINS"].split(",") if o.strip()]
    if cfg["APP_ENV"] == "production":                       # refuse to start with unsafe settings
        if cfg["SECRET_KEY"] == "change-me-in-production" or len(cfg["SECRET_KEY"]) < 32:
            raise RuntimeError("Set SECRET_KEY to a random string of 32+ characters in production.")
        if not origins or "*" in origins:
            raise RuntimeError("Set CORS_ORIGINS to your frontend URL(s) in production, not *.")
    if cfg["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    CORS(app, resources={r"/api/*": {"origins": origins or "*"}})
    db.init_app(app)
    app.model = None
    app.mailer = smtp_mailer(app.config)
    with app.app_context():
        db.create_all()
        if os.path.exists(app.config["MODEL_PATH"]):
            try:
                app.model = RootCauseClassifier.load(app.config["MODEL_PATH"])
            except Exception:
                app.model = None
        _bootstrap_admin(app)
        if app.model is None:                                # hosts with a temporary disk lose the saved model
            try:
                df = _records_df()
                if not df.empty:
                    m = RootCauseClassifier()
                    m.train(df, tune=False)
                    m.save(app.config["MODEL_PATH"])
                    app.model = m
            except Exception:
                app.model = None
        db.session.remove()
        db.engine.dispose()                                  # workers forked after --preload open their own connections

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.get("/api/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok")
        except Exception:
            return jsonify(status="database unavailable"), 503

    @app.errorhandler(ValidationError)
    def _ve(e):
        return jsonify(error="Validation failed.", problems=str(e).split("; ")), 422

    @app.errorhandler(Exception)
    def _any(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        app.logger.exception(e)
        return jsonify(error="Unexpected server error."), 500

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # --------------------------------------------------------- records ----
    @app.get("/api/records")
    @auth_required("record:read")
    def list_records():
        q = DefectRecord.query
        a = request.args
        if a.get("line"): q = q.filter_by(production_line=a["line"])
        if a.get("machine"): q = q.filter_by(machine_id=a["machine"])
        if a.get("defect_type"): q = q.filter_by(defect_type=a["defect_type"])
        if a.get("start"): q = q.filter(DefectRecord.inspection_date >= pd.to_datetime(a["start"]).date())
        if a.get("end"): q = q.filter(DefectRecord.inspection_date <= pd.to_datetime(a["end"]).date())
        page = q.order_by(DefectRecord.inspection_date.desc(), DefectRecord.id.desc()).paginate(
            page=a.get("page", 1, int), per_page=min(a.get("per_page", 50, int), 200), error_out=False)
        return jsonify(items=[r.to_dict() for r in page.items], total=page.total, page=page.page)

    def _insert(rows):
        df = pd.DataFrame([_clean(r) for r in rows])
        prepare_records(df)                      # raises ValidationError -> 422
        objs = []
        for r in df.to_dict("records"):
            r = _clean(r)
            r["inspection_date"] = pd.to_datetime(r["inspection_date"]).date()
            objs.append(DefectRecord(**r, created_by=g.user.id))
        db.session.add_all(objs)
        _audit("records:create", f"{len(df)} rows")
        db.session.commit()
        evaluate_new_records(objs, app.mailer)
        return len(df)

    @app.post("/api/records")
    @auth_required("record:create")
    def create_records():
        body = request.get_json(silent=True)
        if not body:
            return jsonify(error="Send a record or a list of records as JSON."), 400
        n = _insert(body if isinstance(body, list) else [body])
        return jsonify(created=n), 201

    @app.post("/api/records/import")
    @auth_required("record:create")
    def import_records():
        f = request.files.get("file")
        if not f:
            return jsonify(error="Attach a CSV or Excel file as 'file'."), 400
        raw = pd.read_excel(f) if f.filename.lower().endswith((".xlsx", ".xls")) \
            else pd.read_csv(io.BytesIO(f.read()))
        n = _insert(raw.to_dict("records"))
        return jsonify(created=n), 201

    @app.put("/api/records/<int:rid>")
    @auth_required("record:update")
    def update_record(rid):
        rec = DefectRecord.query.get_or_404(rid)
        merged = {**rec.to_dict(), **(request.get_json(silent=True) or {})}
        prepare_records(pd.DataFrame([_clean(merged)]))
        for k, v in _clean(merged).items():
            setattr(rec, k, pd.to_datetime(v).date() if k == "inspection_date" else v)
        _audit("records:update", str(rid)); db.session.commit()
        return jsonify(rec.to_dict())

    @app.delete("/api/records/<int:rid>")
    @auth_required("record:delete")
    def delete_record(rid):
        db.session.delete(DefectRecord.query.get_or_404(rid))
        _audit("records:delete", str(rid)); db.session.commit()
        return "", 204

    # ------------------------------------------------------- dashboard ----
    @app.get("/api/dashboard/bundle")
    @auth_required("dashboard:view")
    def bundle():
        return jsonify(build_bundle(_scoped_df(), app.model))

    @app.get("/api/dashboard/summary")
    @auth_required("dashboard:view")
    def summary():
        df = _scoped_df()
        if df.empty:
            return jsonify(error="No records yet."), 404
        a = request.args
        s = dashboard_summary(df, freq=a.get("freq", "W"), role=g.user.role,
                              start=a.get("start"), end=a.get("end"),
                              production_line=a.get("line"), machine_id=a.get("machine"))
        return jsonify({k: (_to_json(v) if isinstance(v, pd.DataFrame) else v) for k, v in s.items()})

    @app.get("/api/dashboard/pareto")
    @auth_required("dashboard:view")
    def pareto():
        a, by = request.args, request.args.get("by", "defect_type")
        if by not in ("defect_type", "machine_id", "severity"):
            return jsonify(error="by must be defect_type, machine_id or severity."), 422
        df = _scoped_df()
        if df.empty:
            return jsonify({})
        d = filter_records(df, start=a.get("start"), end=a.get("end"), production_line=a.get("line"),
                           shift=a.get("shift"), machine_id=a.get("machine"))
        p = pareto_analysis(d, by=by) if not d.empty else pd.DataFrame({by: [], "defect_count": []})
        return jsonify({str(k): int(v) for k, v in zip(p[by], p["defect_count"])})

    # ------------------------------------------------------ root cause ----
    @app.post("/api/model/train")
    @auth_required("rootcause:train")
    def train():
        model = train_root_cause_model(_records_df(), role=g.user.role)
        model.save(app.config["MODEL_PATH"])
        app.model = model
        _audit("model:train", f"acc={model.metrics_['accuracy']:.3f}"); db.session.commit()
        m = model.metrics_
        return jsonify(accuracy=m["accuracy"], f1_weighted=m["f1_weighted"],
                       n_train=m["n_train"], n_test=m["n_test"], best_params=m["best_params"])

    @app.get("/api/model/status")
    @auth_required("rootcause:predict")
    def model_status():
        if app.model is None:
            return jsonify(trained=False)
        return jsonify(trained=True, accuracy=app.model.metrics_["accuracy"] if app.model.metrics_ else None)

    @app.post("/api/rootcause/predict")
    @auth_required("rootcause:predict")
    def predict():
        if app.model is None:
            return jsonify(error="Model not trained yet. A Quality Manager can train it first."), 409
        rows = request.get_json(silent=True)
        rows = rows if isinstance(rows, list) else [rows or {}]
        df = pd.DataFrame(rows)
        out = suggest_root_causes(app.model, df, role=g.user.role)
        return jsonify(note="ML-based suggestions, not confirmed causes.", suggestions=_to_json(out))

    from .accounts import register_accounts
    from .extras import register_extras
    from .ml_api import register_ml
    register_accounts(app)
    register_extras(app)
    register_ml(app)
    return app
