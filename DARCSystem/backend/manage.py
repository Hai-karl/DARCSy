"""Administration commands.

    python -m backend.manage create-admin --username admin --email you@example.com
    python -m backend.manage init-db

Works against whatever DATABASE_URL points to, so you can run it from your own computer
against the hosted database. The password is read from ADMIN_PASSWORD or asked for.
"""
import argparse
import getpass
import os
import sys

from .app import create_app
from .models import User, db
from .security import validate_password


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    ca = sub.add_parser("create-admin")
    ca.add_argument("--username", required=True)
    ca.add_argument("--email", default="")
    a = ap.parse_args()
    app = create_app()
    with app.app_context():
        db.create_all()
        if a.cmd == "init-db":
            print("Tables are ready.")
            return
        pw = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Password for the new administrator: ")
        problems = validate_password(pw, a.username, a.email)
        if problems:
            sys.exit(" ".join(problems))
        if User.query.filter_by(username=a.username).first():
            sys.exit("That username already exists.")
        u = User(username=a.username, full_name="Administrator", role="IT Administrator", email=a.email or None)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        print(f"Created IT Administrator '{a.username}'.")


if __name__ == "__main__":
    main()
