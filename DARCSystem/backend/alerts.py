"""Threshold and safety-critical alerts (UC-06 / UC-07).

Flow (Figure 7): after a record is saved, a Safety-Critical defect raises an
alert at once; otherwise the 7-day defect rate of the affected line/product is
compared with the configured threshold. Alerts always appear in-app; e-mail is
best-effort and failures are logged for retry.
"""
from datetime import timedelta

from sqlalchemy import func

from .models import Alert, DefectRecord, Threshold, User, db

NOTIFY_ROLES = ("Line Supervisor", "Quality Manager")


def smtp_mailer(cfg):
    """Return send(to_list, subject, body) or None when no mail server is configured."""
    if not cfg.get("MAIL_SERVER"):
        return None
    import smtplib
    from email.message import EmailMessage

    def send(to, subject, body):
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = cfg["MAIL_FROM"], ", ".join(to), subject
        m.set_content(body)
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as s:
            s.starttls()
            if cfg.get("MAIL_USER"):
                s.login(cfg["MAIL_USER"], cfg["MAIL_PASSWORD"])
            s.send_message(m)
    return send


def _send(alert, mailer):
    to = [u.email for u in User.query.filter(User.is_active.is_(True), User.role.in_(NOTIFY_ROLES))
          if u.email]
    if mailer is None:
        alert.email_status = "not_configured"
        return
    if not to:
        alert.email_status = "no_recipients"
        return
    alert.email_attempts = (alert.email_attempts or 0) + 1
    try:
        mailer(to, f"[QC alert] {alert.production_line}: {alert.kind}", alert.message)
        alert.email_status = "sent"
    except Exception:            # server unreachable: keep the in-app alert, retry later
        alert.email_status = "failed"


def retry_failed(mailer) -> int:
    ok = 0
    for a in Alert.query.filter_by(email_status="failed").all():
        _send(a, mailer)
        ok += a.email_status == "sent"
    db.session.commit()
    return ok


def _week_rate(line, product, end):
    q = db.session.query(func.sum(DefectRecord.units_inspected), func.sum(DefectRecord.defect_count)).filter(
        DefectRecord.production_line == line,
        DefectRecord.inspection_date > end - timedelta(days=7),
        DefectRecord.inspection_date <= end)
    if product:
        q = q.filter(DefectRecord.product_type == product)
    units, defects = q.one()
    return (defects or 0) / units if units else 0.0


def evaluate_new_records(records, mailer):
    made = []
    for r in records:
        if r.severity == "Safety-Critical":
            a = Alert(kind="safety", production_line=r.production_line, product_type=r.product_type,
                      record_id=r.id, message=f"Safety-critical {r.defect_type} defect on {r.production_line}, "
                      f"machine {r.machine_id}, batch {r.batch_number}.")
            db.session.add(a)
            made.append(a)
    for key in {(r.production_line, r.product_type) for r in records}:
        line, product = key
        th = (Threshold.query.filter_by(production_line=line, product_type=product).first()
              or Threshold.query.filter_by(production_line=line, product_type=None).first())
        if not th:
            continue
        end = max(r.inspection_date for r in records if (r.production_line, r.product_type) == key)
        rate = _week_rate(line, product if th.product_type else None, end)
        open_alert = Alert.query.filter_by(kind="threshold", production_line=line,
                                           product_type=th.product_type, acknowledged_at=None).first()
        if rate > th.max_defect_rate and not open_alert:
            a = Alert(kind="threshold", production_line=line, product_type=th.product_type,
                      defect_rate=rate, threshold=th.max_defect_rate,
                      message=f"{line} defect rate over the last 7 days is {rate:.1%}, above the "
                              f"{th.max_defect_rate:.1%} threshold.")
            db.session.add(a)
            made.append(a)
    db.session.flush()
    for a in made:
        _send(a, mailer)
    db.session.commit()
    return made
