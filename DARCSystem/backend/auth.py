"""JWT authentication + RBAC enforcement for HTTP routes."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from defect_analysis.rbac import has_permission

from .models import User


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=current_app.config["JWT_HOURS"])
    return jwt.encode({"sub": str(user.id), "role": user.role, "tv": user.token_version, "exp": exp},
                      current_app.config["SECRET_KEY"], algorithm="HS256")


def auth_required(permission: str = None):
    """Require a valid token; if `permission` is given, the user's role must hold it."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify(error="Missing bearer token."), 401
            try:
                data = jwt.decode(header[7:], current_app.config["SECRET_KEY"],
                                  algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return jsonify(error="Session expired. Please sign in again."), 401
            except jwt.InvalidTokenError:
                return jsonify(error="Invalid token."), 401
            user = User.query.get(int(data["sub"]))
            if (not user or not user.is_active or user.status != "active"
                    or data.get("tv") != user.token_version):
                return jsonify(error="Session no longer valid. Please sign in again."), 401
            if permission and not has_permission(user.role, permission):
                return jsonify(error=f"Role '{user.role}' cannot perform '{permission}'."), 403
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco
