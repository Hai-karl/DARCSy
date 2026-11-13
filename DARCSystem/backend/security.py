"""Password rules, input checks and a small in-memory rate limiter."""
import re
import time
from collections import defaultdict, deque

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
COMMON = {"password1234", "1234567890", "qwerty12345", "letmein1234", "admin12345", "welcome1234",
          "iloveyou123", "changeme123", "p@ssw0rd123"}
REGISTRABLE_ROLES = ("QC Engineer", "Line Supervisor", "Quality Manager")   # never IT Administrator


def validate_password(pw, username="", email="") -> list:
    if not isinstance(pw, str) or not pw:
        return ["Password is required."]
    out, low = [], pw.lower()
    if len(pw) < 10:
        out.append("Password must be at least 10 characters.")
    if len(pw) > 128:
        out.append("Password must be at most 128 characters.")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        out.append("Password needs at least one letter and one number.")
    if username and len(username) >= 3 and username.lower() in low:
        out.append("Password must not contain your username.")
    if email and email.split("@")[0] and len(email.split("@")[0]) >= 4 and email.split("@")[0].lower() in low:
        out.append("Password must not contain your email name.")
    if low in COMMON:
        out.append("That password is too common.")
    return out


class RateLimiter:
    """Allow `max_calls` per `window` seconds for each key (one process; use a proxy limit for more)."""

    def __init__(self, max_calls: int, window: float):
        self.max, self.window, self.hits = max_calls, window, defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True
