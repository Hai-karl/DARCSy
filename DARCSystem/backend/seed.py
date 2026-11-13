"""Create tables, demo users (one per role) and load synthetic records.
    python -m backend.seed [--no-data]
Change these demo passwords before any real use."""
import sys

import pandas as pd

from defect_analysis import generate_sample_records

from .app import create_app
from .models import DefectRecord, Threshold, User, db

DEMO_USERS = [("qc.engineer", "QC Engineer"), ("supervisor", "Line Supervisor"),
              ("manager", "Quality Manager"), ("admin", "IT Administrator")]


def seed(app, with_data=True):
    with app.app_context():
        db.create_all()
        for username, role in DEMO_USERS:
            if not User.query.filter_by(username=username).first():
                u = User(username=username, full_name=username.replace(".", " ").title(), role=role,
                         email=f"{username}@example.com",
                         assigned_line="Line A" if username == "supervisor" else None)
                u.set_password("Password123!")
                db.session.add(u)
        if Threshold.query.count() == 0:
            for line in ("Line A", "Line B", "Line C"):
                db.session.add(Threshold(production_line=line, max_defect_rate=0.02))
        db.session.commit()
        if with_data and DefectRecord.query.count() == 0:
            df = generate_sample_records()
            df["inspection_date"] = pd.to_datetime(df["inspection_date"]).dt.date
            df = df.astype(object).where(df.notna(), None)
            db.session.bulk_insert_mappings(DefectRecord, df.to_dict("records"))
            db.session.commit()


if __name__ == "__main__":
    app = create_app()
    if app.config["APP_ENV"] == "production":
        sys.exit("Refusing to create demo accounts in production. Use: python -m backend.manage create-admin")
    seed(app, with_data="--no-data" not in sys.argv)
    print("Seeded. Demo logins: qc.engineer / supervisor / manager / admin  (Password123!)")
