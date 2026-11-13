"""Role-Based Access Control (QC Engineer, Line Supervisor, Quality Manager,
IT Administrator)."""
from functools import wraps

from .config import PERMISSIONS, ROLES


class PermissionDenied(Exception):
    """Raised when a role lacks the permission for an action."""


def has_permission(role: str, permission: str) -> bool:
    if role not in ROLES:
        return False
    return permission in PERMISSIONS[role]


def require_permission(permission: str):
    """Decorator: the wrapped function must receive a `role` keyword argument.

    In the Flask layer, `role` would come from the authenticated session/JWT.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, role=None, **kwargs):
            if not has_permission(role, permission):
                raise PermissionDenied(
                    f"Role '{role}' is not allowed to perform '{permission}'."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
