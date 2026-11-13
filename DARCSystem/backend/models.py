"""SQLAlchemy models. Mirrors schema.sql."""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    assigned_line = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(12), default="active", nullable=False)      # pending | active | rejected
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    token_version = db.Column(db.Integer, default=1, nullable=False)         # bump to sign the user out everywhere
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)
    def to_dict(self):
        return dict(id=self.id, username=self.username, full_name=self.full_name,
                    role=self.role, email=self.email, assigned_line=self.assigned_line,
                    is_active=self.is_active, status=self.status,
                    last_login_at=self.last_login_at.isoformat() if self.last_login_at else None)


class DefectRecord(db.Model):
    __tablename__ = "defect_records"
    id = db.Column(db.Integer, primary_key=True)
    inspection_date = db.Column(db.Date, nullable=False, index=True)
    production_line = db.Column(db.String(30), nullable=False, index=True)
    product_type = db.Column(db.String(40), nullable=False)
    shift = db.Column(db.String(20), nullable=False)
    machine_id = db.Column(db.String(20), nullable=False, index=True)
    defect_type = db.Column(db.String(40), nullable=False, index=True)
    batch_number = db.Column(db.String(40), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False)
    units_inspected = db.Column(db.Integer, nullable=False)
    defect_count = db.Column(db.Integer, nullable=False)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    machine_age_months = db.Column(db.Integer)
    root_cause = db.Column(db.String(20))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    COLS = ["inspection_date", "production_line", "product_type", "shift", "machine_id",
            "defect_type", "batch_number", "severity", "units_inspected", "defect_count", "temperature", "humidity",
            "machine_age_months", "root_cause"]

    def to_dict(self):
        d = {c: getattr(self, c) for c in self.COLS}
        d["inspection_date"] = self.inspection_date.isoformat()
        d["id"] = self.id
        return d


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Threshold(db.Model):
    __tablename__ = "thresholds"
    id = db.Column(db.Integer, primary_key=True)
    production_line = db.Column(db.String(30), nullable=False)
    product_type = db.Column(db.String(40))          # None = whole line
    max_defect_rate = db.Column(db.Float, nullable=False)   # fraction, e.g. 0.02 = 2 %
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return dict(id=self.id, production_line=self.production_line,
                    product_type=self.product_type, max_defect_rate=self.max_defect_rate)


class Alert(db.Model):
    __tablename__ = "alerts"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(12), nullable=False)  # threshold | safety
    production_line = db.Column(db.String(30), nullable=False)
    product_type = db.Column(db.String(40))
    record_id = db.Column(db.Integer)
    defect_rate = db.Column(db.Float)
    threshold = db.Column(db.Float)
    message = db.Column(db.String(255), nullable=False)
    email_status = db.Column(db.String(20), default="none", nullable=False)
    email_attempts = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    acknowledged_at = db.Column(db.DateTime)

    def to_dict(self):
        return dict(id=self.id, kind=self.kind, production_line=self.production_line,
                    message=self.message, defect_rate=self.defect_rate, threshold=self.threshold,
                    email_status=self.email_status, created_at=self.created_at.isoformat(),
                    acknowledged=self.acknowledged_at is not None)


class CorrectiveAction(db.Model):
    __tablename__ = "corrective_actions"
    id = db.Column(db.Integer, primary_key=True)
    production_line = db.Column(db.String(30), nullable=False)
    machine_id = db.Column(db.String(20))
    defect_type = db.Column(db.String(40))
    root_cause = db.Column(db.String(20), nullable=False)       # confirmed by the engineer
    suggested_cause = db.Column(db.String(20))                  # what the model suggested (agreement rate)
    description = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(12), default="Proposed", nullable=False)
    logged_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    implemented_at = db.Column(db.Date)

    def to_dict(self):
        return dict(id=self.id, production_line=self.production_line, machine_id=self.machine_id,
                    defect_type=self.defect_type, root_cause=self.root_cause,
                    suggested_cause=self.suggested_cause, description=self.description,
                    status=self.status, implemented_at=self.implemented_at.isoformat() if self.implemented_at else None)


class SusResponse(db.Model):
    __tablename__ = "sus_responses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    role = db.Column(db.String(30), nullable=False)
    answers = db.Column(db.String(60), nullable=False)      # JSON list of 10 answers
    score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
