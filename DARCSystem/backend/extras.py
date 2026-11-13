"""Alerts, thresholds, corrective actions, root cause investigation, reports."""
import io
import json
from datetime import datetime

import pandas as pd
from flask import g, jsonify, request, send_file

from defect_analysis.analytics import corrective_action_effectiveness, similar_periods, what_changed
from defect_analysis.config import ROOT_CAUSES
from defect_analysis.services import dashboard_summary
from defect_analysis.sus import sus_score, sus_verdict

from .alerts import retry_failed
from .auth import auth_required
from .models import Alert, CorrectiveAction, SusResponse, Threshold, db


def register_extras(app):
    from .app import _audit, _records_df, _scoped_df

    # ---------------------------------------------------------- thresholds ----
    @app.get("/api/thresholds")
    @auth_required("dashboard:view")
    def thresholds():
        return jsonify([t.to_dict() for t in Threshold.query.order_by(Threshold.production_line)])

    @app.put("/api/thresholds")
    @auth_required("threshold:configure")
    def set_threshold():
        b = request.get_json(silent=True) or {}
        rate, line = b.get("max_defect_rate"), (b.get("production_line") or "").strip()
        if not line or not isinstance(rate, (int, float)) or not 0 < rate <= 1:
            return jsonify(error="Enter a production line and a threshold between 0% and 100%."), 422
        product = b.get("product_type") or None
        t = Threshold.query.filter_by(production_line=line, product_type=product).first() or Threshold(
            production_line=line, product_type=product)
        t.max_defect_rate, t.updated_by = rate, g.user.id
        db.session.add(t)
        _audit("threshold:set", f"{line} {rate:.3f}")
        db.session.commit()
        return jsonify(t.to_dict())

    # -------------------------------------------------------------- alerts ----
    @app.get("/api/alerts")
    @auth_required("alert:view")
    def alerts():
        q = Alert.query.order_by(Alert.created_at.desc())
        if g.user.assigned_line:
            q = q.filter(Alert.production_line == g.user.assigned_line)
        if request.args.get("open"):
            q = q.filter(Alert.acknowledged_at.is_(None))
        return jsonify([a.to_dict() for a in q.limit(100)])

    @app.post("/api/alerts/<int:aid>/ack")
    @auth_required("alert:ack")
    def ack(aid):
        a = Alert.query.get_or_404(aid)
        a.acknowledged_by, a.acknowledged_at = g.user.id, datetime.utcnow()
        _audit("alert:ack", str(aid))
        db.session.commit()
        return jsonify(a.to_dict())

    @app.post("/api/alerts/retry-emails")
    @auth_required("alert:ack")
    def retry():
        return jsonify(sent=retry_failed(app.mailer))

    # ---------------------------------------------------- corrective actions ----
    @app.get("/api/corrective-actions")
    @auth_required("action:view")
    def actions():
        return jsonify([a.to_dict() for a in CorrectiveAction.query.order_by(CorrectiveAction.id.desc())])

    @app.post("/api/corrective-actions")
    @auth_required("action:log")
    def log_action():
        b = request.get_json(silent=True) or {}
        if not b.get("production_line") or not (b.get("description") or "").strip():
            return jsonify(error="Production line and a description are required."), 422
        if b.get("root_cause") not in ROOT_CAUSES or b.get("suggested_cause") not in (None, "", *ROOT_CAUSES):
            return jsonify(error=f"Root cause must be one of {ROOT_CAUSES}."), 422
        a = CorrectiveAction(production_line=b["production_line"], machine_id=b.get("machine_id") or None,
                             defect_type=b.get("defect_type") or None, root_cause=b["root_cause"],
                             suggested_cause=b.get("suggested_cause") or None,
                             description=b["description"].strip()[:500], logged_by=g.user.id)
        db.session.add(a)
        _audit("action:log", b["production_line"])
        db.session.commit()
        return jsonify(a.to_dict()), 201

    @app.post("/api/corrective-actions/<int:aid>/approve")
    @auth_required("action:approve")
    def approve(aid):
        a = CorrectiveAction.query.get_or_404(aid)
        if a.status != "Proposed":
            return jsonify(error="Only proposed actions can be approved."), 422
        a.status, a.approved_by = "Approved", g.user.id
        _audit("action:approve", str(aid))
        db.session.commit()
        return jsonify(a.to_dict())

    @app.post("/api/corrective-actions/<int:aid>/implement")
    @auth_required("action:log")
    def implement(aid):
        a = CorrectiveAction.query.get_or_404(aid)
        if a.status != "Approved":
            return jsonify(error="The Quality Manager must approve the action first."), 422
        day = (request.get_json(silent=True) or {}).get("date")
        a.status, a.implemented_at = "Implemented", (pd.to_datetime(day).date() if day else datetime.utcnow().date())
        _audit("action:implement", str(aid))
        db.session.commit()
        return jsonify(a.to_dict())

    @app.get("/api/corrective-actions/<int:aid>/effectiveness")
    @auth_required("action:view")
    def effectiveness(aid):
        a = CorrectiveAction.query.get_or_404(aid)
        if a.status != "Implemented":
            return jsonify(error="Effectiveness can be checked once the action is implemented."), 422
        return jsonify(corrective_action_effectiveness(
            _records_df(), a.production_line, a.machine_id, a.defect_type, a.implemented_at))

    @app.get("/api/model/agreement")
    @auth_required("rootcause:train")
    def agreement():
        rated = CorrectiveAction.query.filter(CorrectiveAction.suggested_cause.isnot(None)).all()
        n = len(rated)
        return jsonify(n=n, rate=(sum(a.suggested_cause == a.root_cause for a in rated) / n) if n else None)

    # --------------------------------------------------------- investigate ----
    @app.post("/api/rootcause/investigate")
    @auth_required("rootcause:predict")
    def investigate():
        if app.model is None:
            return jsonify(error="Model not trained yet. A Quality Manager can train it first."), 409
        b, df = request.get_json(silent=True) or {}, _scoped_df()
        if df.empty:
            return jsonify(error="No records yet."), 404
        for key, col in [("defect_type", "defect_type"), ("line", "production_line"),
                         ("machine", "machine_id"), ("shift", "shift")]:
            if b.get(key):
                df = df[df[col] == b[key]]
        df = df[df["defect_count"] > 0].tail(200)
        if df.empty:
            return jsonify(n=0, ranked=[], low_confidence=True,
                           message="No matching defect records. Use the Pareto and correlation views instead.")
        out = app.model.investigate(df)
        out["message"] = ("Low confidence: too few records or no clear leading cause. Cross-check with the "
                          "Pareto chart and correlation heatmap." if out["low_confidence"]
                          else f"Based on {out['n']} recent matching records. Treat as a lead to verify.")
        out["top_machines"] = {k: int(v) for k, v in df.groupby("machine_id")["defect_count"].sum()
                               .nlargest(3).items()}
        out["rules"] = app.model.decision_rules(max_depth=3)
        return jsonify(out)

    # ------------------------------------------------------------- reports ----
    @app.get("/api/reports/quality")
    @auth_required("report:export")
    def report():
        fmt = request.args.get("format", "xlsx")
        df = _scoped_df()
        if df.empty:
            return jsonify(error="No records yet."), 404
        a = request.args
        s = dashboard_summary(df, freq="W", role=g.user.role, start=a.get("start"), end=a.get("end"),
                              production_line=a.get("line"))
        tables = {"Weekly trend": s["trend"], "Pareto defect type": s["pareto_defect_type"],
                  "Pareto machine": s["pareto_machine"], "Correlations": s["correlations"]}
        head = [("Overall defect rate", f"{s['overall_defect_rate']:.2%}"),
                ("Trend", s["trend_direction"]["direction"]),
                ("Weeks outside control limits", int(s["control_chart"]["out_of_control"].sum())),
                ("Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))]
        buf = io.BytesIO()
        if fmt == "pdf":
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
            st, parts = getSampleStyleSheet(), []
            parts.append(Paragraph("Quality Control Report", st["Title"]))
            for k, v in head:
                parts.append(Paragraph(f"<b>{k}:</b> {v}", st["Normal"]))
            for name, t in tables.items():
                if name == "Weekly trend":
                    t = t.tail(12)
                parts += [Spacer(1, 14), Paragraph(name, st["Heading3"])]
                t = t.round(4).astype(str)
                tb = Table([list(t.columns)] + t.values.tolist(), repeatRows=1)
                tb.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), .25, colors.grey),
                                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
                parts.append(tb)
            SimpleDocTemplate(buf, title="Quality Control Report").build(parts)
            mime, name = "application/pdf", "quality_report.pdf"
        else:
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                pd.DataFrame(head, columns=["Item", "Value"]).to_excel(w, sheet_name="Summary", index=False)
                for n, t in tables.items():
                    t.to_excel(w, sheet_name=n, index=False)
            mime, name = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "quality_report.xlsx"
        buf.seek(0)
        _audit("report:export", fmt)
        db.session.commit()
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=name)

    # ----------------------------------------------------------------- SUS ----
    @app.post("/api/sus")
    @auth_required()
    def sus_submit():
        answers = (request.get_json(silent=True) or {}).get("answers")
        try:
            score = sus_score(answers)
        except ValueError as e:
            return jsonify(error=str(e)), 422
        db.session.add(SusResponse(user_id=g.user.id, role=g.user.role, answers=json.dumps(answers), score=score))
        db.session.commit()
        return jsonify(score=score, verdict=sus_verdict(score)), 201

    @app.get("/api/sus/summary")
    @auth_required("sus:view")
    def sus_summary():
        rows = SusResponse.query.all()
        if not rows:
            return jsonify(n=0, mean=None, by_role={})
        by = {}
        for r in rows:
            by.setdefault(r.role, []).append(r.score)
        mean = sum(r.score for r in rows) / len(rows)
        return jsonify(n=len(rows), mean=round(mean, 1), verdict=sus_verdict(mean),
                       min=min(r.score for r in rows), max=max(r.score for r in rows),
                       by_role={k: round(sum(v) / len(v), 1) for k, v in by.items()})

    # --------------------------------------------- investigate a chart period ----
    def _period_args():
        a = request.args
        try:
            return pd.Timestamp(a["start"]), pd.Timestamp(a["end"]), a.get("line")
        except (KeyError, ValueError):
            return None

    @app.get("/api/dashboard/what-changed")
    @auth_required("dashboard:view")
    def what_changed_ep():
        p = _period_args()
        if p is None:
            return jsonify(error="Send start and end dates (YYYY-MM-DD)."), 422
        df = _scoped_df()
        if df.empty:
            return jsonify(error="No records yet."), 404
        if p[2]:
            df = df[df["production_line"] == p[2]]
        out = what_changed(df, p[0], p[1])
        out["suggested_causes"] = []
        if app.model is not None:
            cur = df[(df["inspection_date"] >= p[0]) & (df["inspection_date"] <= p[1])
                     & (df["defect_count"] > 0) & (df["defect_type"] != "None")]
            if len(cur):
                inv = app.model.investigate(cur)
                out["suggested_causes"], out["low_confidence"] = inv["ranked"][:3], inv["low_confidence"]
        return jsonify(out)

    @app.get("/api/dashboard/similar")
    @auth_required("dashboard:view")
    def similar_ep():
        p = _period_args()
        freq = {"D": "D", "W": "W", "M": "MS"}.get(request.args.get("freq", "W"))
        if p is None or freq is None:
            return jsonify(error="Send start, end (YYYY-MM-DD) and freq D, W or M."), 422
        df = _scoped_df()
        return jsonify(results=[] if df.empty else similar_periods(df, p[0], p[1], freq, p[2]))

    @app.get("/api/events")
    @auth_required("dashboard:view")
    def events():
        line, out = g.user.assigned_line, []
        for a in CorrectiveAction.query.filter(CorrectiveAction.implemented_at.isnot(None)):
            if not line or a.production_line == line:
                out.append(dict(kind="action", date=a.implemented_at.isoformat(), line=a.production_line,
                                label=a.description[:80]))
        q = Alert.query.order_by(Alert.created_at.desc())
        for a in (q.filter(Alert.production_line == line) if line else q).limit(200):
            out.append(dict(kind="alert", date=a.created_at.date().isoformat(), line=a.production_line, label=a.message))
        return jsonify(out)
