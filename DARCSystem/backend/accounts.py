"""Sign-in, registration with administrator approval, password change and user management."""
from datetime import datetime, timedelta

from flask import current_app, g, jsonify, request
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from defect_analysis.config import PERMISSIONS, ROLES

from .auth import auth_required, make_token
from .models import User, db
from .security import EMAIL_RE, REGISTRABLE_ROLES, USERNAME_RE, RateLimiter, validate_password

_DUMMY_HASH = generate_password_hash("not-a-real-password")      # equalises timing for unknown users


def _public(user):
    return {**user.to_dict(), "permissions": sorted(PERMISSIONS[user.role])}


def _other_admins(excluding_id):
    return User.query.filter(User.role == "IT Administrator", User.is_active.is_(True),
                             User.status == "active", User.id != excluding_id).count()


def register_accounts(app):
    from .app import _audit

    cfg = app.config
    limiters = {"login": RateLimiter(cfg["RATE_LOGIN_PER_MIN"], 60),
                "register": RateLimiter(cfg["RATE_REGISTER_PER_HOUR"], 3600)}
    limited = cfg["RATE_LIMIT_ENABLED"] and (not cfg.get("TESTING") or cfg.get("RATE_LIMIT_FORCE"))

    def too_many(name):
        return limited and not limiters[name].allow(request.remote_addr or "?")

    # ------------------------------------------------------------- sign in ----
    @app.post("/api/auth/login")
    def login():
        if too_many("login"):
            return jsonify(error="Too many sign-in attempts. Wait a minute and try again."), 429
        b = request.get_json(silent=True) or {}
        name, pw = str(b.get("username") or "").strip(), str(b.get("password") or "")
        user = User.query.filter(func.lower(User.username) == name.lower()).first() if name else None
        now = datetime.utcnow()
        if user and user.locked_until and user.locked_until > now:
            mins = int((user.locked_until - now).total_seconds() // 60) + 1
            return jsonify(error=f"Too many wrong passwords. This account is locked for about {mins} more minutes."), 429
        if not (user.check_password(pw) if user else (check_password_hash(_DUMMY_HASH, pw) and False)):
            if user:
                user.failed_logins += 1
                if user.failed_logins >= cfg["MAX_FAILED_LOGINS"]:
                    user.locked_until, user.failed_logins = now + timedelta(minutes=cfg["LOCKOUT_MINUTES"]), 0
                    g.user = user
                    _audit("login:locked", user.username)
                db.session.commit()
            return jsonify(error="Wrong username or password."), 401
        if user.status == "pending":
            return jsonify(error="Your registration is waiting for approval by an administrator."), 403
        if user.status == "rejected":
            return jsonify(error="This registration was not approved. Contact your administrator."), 403
        if not user.is_active:
            return jsonify(error="This account is disabled. Contact your administrator."), 403
        user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
        g.user = user
        _audit("login")
        db.session.commit()
        return jsonify(token=make_token(user), user=_public(user))

    @app.get("/api/auth/me")
    @auth_required()
    def me():
        return jsonify(_public(g.user))

    # ------------------------------------------------------------ register ----
    @app.post("/api/auth/register")
    def register():
        if too_many("register"):
            return jsonify(error="Too many registrations from this address. Try again later."), 429
        b = request.get_json(silent=True) or {}
        username, full_name = str(b.get("username") or "").strip(), str(b.get("full_name") or "").strip()
        email, role, pw = str(b.get("email") or "").strip().lower(), b.get("role"), b.get("password")
        problems = []
        if not USERNAME_RE.match(username):
            problems.append("Username must be 3 to 30 characters: letters, numbers, dot, dash or underscore.")
        if not 2 <= len(full_name) <= 120:
            problems.append("Enter your full name.")
        if not EMAIL_RE.match(email) or len(email) > 120:
            problems.append("Enter a valid email address.")
        if role not in REGISTRABLE_ROLES:
            problems.append(f"Role must be one of {list(REGISTRABLE_ROLES)}.")
        problems += validate_password(pw, username, email)
        if problems:
            return jsonify(error="Please fix the problems below.", problems=problems), 422
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            return jsonify(error="That username is already taken."), 409
        if User.query.filter(func.lower(User.email) == email).first():
            return jsonify(error="An account with that email already exists."), 409
        u = User(username=username, full_name=full_name, email=email, role=role, status="pending")
        u.set_password(pw)
        db.session.add(u)
        _audit("register", username)
        db.session.commit()
        return jsonify(message="Registration received. An administrator must approve it before you can sign in."), 201

    # ------------------------------------------------------ own password ----
    @app.post("/api/auth/change-password")
    @auth_required()
    def change_password():
        b, u = request.get_json(silent=True) or {}, g.user
        if not u.check_password(str(b.get("current_password") or "")):
            return jsonify(error="Your current password is not correct."), 403
        problems = validate_password(b.get("new_password"), u.username, u.email or "")
        if b.get("new_password") == b.get("current_password"):
            problems.append("The new password must be different from the current one.")
        if problems:
            return jsonify(error="Please fix the problems below.", problems=problems), 422
        u.set_password(b["new_password"])
        u.token_version += 1                                   # signs out every other session
        _audit("password:change")
        db.session.commit()
        return jsonify(token=make_token(u))

    @app.post("/api/auth/logout-all")
    @auth_required()
    def logout_all():
        g.user.token_version += 1
        _audit("logout:all")
        db.session.commit()
        return "", 204

    # --------------------------------------------------- user management ----
    @app.get("/api/users")
    @auth_required("user:manage")
    def users():
        order = db.case((User.status == "pending", 0), else_=1)
        return jsonify([u.to_dict() for u in User.query.order_by(order, User.id)])

    @app.post("/api/users")
    @auth_required("user:manage")
    def add_user():
        b = request.get_json(silent=True) or {}
        username, email = str(b.get("username") or "").strip(), (str(b.get("email") or "").strip().lower() or None)
        problems = []
        if b.get("role") not in ROLES:
            problems.append(f"Role must be one of {ROLES}.")
        if not USERNAME_RE.match(username):
            problems.append("Username must be 3 to 30 characters: letters, numbers, dot, dash or underscore.")
        if email and not EMAIL_RE.match(email):
            problems.append("Enter a valid email address.")
        problems += validate_password(b.get("password"), username, email or "")
        if problems:
            return jsonify(error="Please fix the problems below.", problems=problems), 422
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            return jsonify(error="Username already exists."), 409
        if email and User.query.filter(func.lower(User.email) == email).first():
            return jsonify(error="Email already in use."), 409
        u = User(username=username, full_name=(b.get("full_name") or username).strip(), role=b["role"],
                 email=email, assigned_line=b.get("assigned_line") or None)
        u.set_password(b["password"])
        db.session.add(u)
        _audit("user:create", username)
        db.session.commit()
        return jsonify(u.to_dict()), 201

    @app.patch("/api/users/<int:uid>")
    @auth_required("user:manage")
    def edit_user(uid):
        u, b = User.query.get_or_404(uid), request.get_json(silent=True) or {}
        role = b.get("role", u.role)
        status = b.get("status", u.status)
        active = bool(b["is_active"]) if "is_active" in b else u.is_active
        if role not in ROLES or status not in ("pending", "active", "rejected"):
            return jsonify(error="Invalid role or status."), 422
        if status == "pending" and u.status != "pending":
            return jsonify(error="An account cannot go back to pending."), 422
        if status == "active" and u.status == "rejected":
            active = True
        stays_admin = role == "IT Administrator" and active and status == "active"
        if u.role == "IT Administrator" and not stays_admin and not _other_admins(u.id):
            return jsonify(error="At least one active IT Administrator is required."), 422
        if u.id == g.user.id and (role != u.role or not active):
            return jsonify(error="You can't change your own role or disable your own account."), 422
        changed = (role, status, active) != (u.role, u.status, u.is_active)
        u.role, u.status, u.is_active = role, status, active
        if "assigned_line" in b:
            u.assigned_line = b["assigned_line"] or None
        if changed:
            u.token_version += 1                               # their open sessions end now
        _audit("user:update", f"{uid} role={role} status={status} active={active}")
        db.session.commit()
        return jsonify(u.to_dict())

    @app.post("/api/users/<int:uid>/reset-password")
    @auth_required("user:manage")
    def reset_password(uid):
        u, b = User.query.get_or_404(uid), request.get_json(silent=True) or {}
        problems = validate_password(b.get("new_password"), u.username, u.email or "")
        if problems:
            return jsonify(error="Please fix the problems below.", problems=problems), 422
        u.set_password(b["new_password"])
        u.token_version, u.failed_logins, u.locked_until = u.token_version + 1, 0, None
        _audit("password:reset", str(uid))
        db.session.commit()
        return jsonify(message="Password reset. Give the user the temporary password and ask them to change it.")
