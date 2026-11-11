"""Accounts and sign-in: password hashing, signed session cookies, role checks and login throttling.

Only the standard library is used. Passwords are stored as salted scrypt hashes. The session cookie holds
``<payload>.<signature>``: the payload is the user's email and an expiry time, the signature is HMAC-SHA256 with
``SESSION_SECRET``. The cookie is HttpOnly, so page scripts cannot read it. On every request the user is loaded
from the database, so a changed role or a deactivated account takes effect immediately.
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select

from ..db import DbSession
from ..models.db_models import User
from .config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "forgemind_session"
LOCAL_USER = "local"  # the identity used when AUTH_ENABLED=false
ADMIN, TECHNICIAN = "admin", "technician"

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200

# Used when SESSION_SECRET is blank (development only; production refuses to start without one).
_EPHEMERAL_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True)
class CurrentUser:
    """Who is making the request."""

    email: str
    name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN


LOCAL_ACCOUNT = CurrentUser(email=LOCAL_USER, name="Local user", role=ADMIN)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---- passwords ------------------------------------------------------------------------
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash; malformed hashes never match."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = _scrypt(password, _unb64(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))  # compared against when the email is unknown (same timing)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def password_problem(password: str) -> str | None:
    """A message for a password that is not acceptable, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"The password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"The password must be at most {MAX_PASSWORD_LENGTH} characters."
    return None


def authenticate(db, email: str, password: str) -> User | None:
    """The active user with this email and password, or None. Unknown emails cost the same time as wrong passwords."""
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    return user if user is not None and user.is_active and ok else None


def ensure_first_admin(db) -> bool:
    """Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD when no user exists. True if created."""
    password = settings.admin_password.get_secret_value()
    email = normalise_email(settings.admin_email)
    if not password or not EMAIL_PATTERN.match(email) or password_problem(password):
        return False
    if db.scalar(select(func.count()).select_from(User)):
        return False
    db.add(User(email=email, name="Administrator", role=ADMIN, password_hash=hash_password(password)))
    db.commit()
    return True


# ---- session tokens -------------------------------------------------------------------
def _secret() -> bytes:
    configured = settings.session_secret.get_secret_value()
    key = configured.encode("utf-8") if configured else _EPHEMERAL_SECRET
    # A new random value on every start: cookies from an earlier run no longer verify, so the login page comes first.
    return key + _EPHEMERAL_SECRET if settings.login_on_start else key


def _sign(body: str) -> str:
    return _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())


def create_session_token(email: str, ttl_seconds: int, now: float | None = None) -> str:
    payload = {"sub": email, "exp": int((now if now is not None else time.time()) + ttl_seconds)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_session_token(token: str | None, now: float | None = None) -> str | None:
    """Return the email in a valid, unexpired token, or None for anything else (missing, forged, expired)."""
    if not token or token.count(".") != 1:
        return None
    body, signature = token.split(".")
    try:
        if not hmac.compare_digest(signature.encode("ascii"), _sign(body).encode("ascii")):
            return None
        payload = json.loads(_unb64(body))
        if not isinstance(payload, dict) or payload.get("exp", 0) <= (now if now is not None else time.time()):
            return None
        subject = payload.get("sub")
        return subject if isinstance(subject, str) and subject else None
    except (ValueError, UnicodeError):
        return None


# ---- request dependencies -------------------------------------------------------------
def require_user(request: Request, db: DbSession) -> CurrentUser:
    """FastAPI dependency: the signed-in, active user, or HTTP 401. Everybody is an admin when AUTH_ENABLED=false."""
    if not settings.auth_enabled:
        return LOCAL_ACCOUNT
    email = verify_session_token(request.cookies.get(COOKIE_NAME))
    user = db.scalar(select(User).where(User.email == email)) if email else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return CurrentUser(email=user.email, name=user.name, role=user.role)


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """FastAPI dependency: the signed-in user must be an administrator, otherwise HTTP 403."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only an administrator can do this.")
    return user


class LoginThrottle:
    """Allow a few failed sign-ins per client in a time window, to stop password guessing."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 60):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Seconds to wait before another attempt (0 when allowed)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - recent[0])) + 1)

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._failures) > 5000:  # bound memory under a flood of distinct clients
                for stale in [k for k in self._failures if not self._recent(k, now)]:
                    self._failures.pop(stale, None)
            self._failures.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()