"""Sign-in: session tokens, passwords, throttling, cookie handling and API protection."""
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from backend.app.core import security
from backend.app.core.config import Settings, settings
from backend.app.core.security import (
    COOKIE_NAME, LoginThrottle, create_session_token, hash_password, verify_password, verify_session_token,
)
from backend.app.db import session_scope
from backend.app.main import app
from backend.app.models.db_models import User
from backend.app.tests.conftest import ADMIN_EMAIL as EMAIL, PASSWORD, TECH_EMAIL


@pytest.fixture()
def http(accounts):
    return TestClient(app)  # signed out; the two accounts exist


def _login(http, email=EMAIL, password=PASSWORD, remember=False):
    return http.post("/api/auth/login", json={"email": email, "password": password, "remember": remember})


@pytest.fixture()
def auth_on(accounts):
    return None


# ---- tokens ---------------------------------------------------------------------------
def test_token_round_trip(auth_on):
    assert verify_session_token(create_session_token("a@b.co", 60)) == "a@b.co"


def test_token_expires(auth_on):
    token = create_session_token("a@b.co", 60, now=1_000)
    assert verify_session_token(token, now=1_059) == "a@b.co"
    assert verify_session_token(token, now=1_060) is None


@pytest.mark.parametrize("bad", [None, "", "abc", "a.b.c", "....", "e30.AAAA", "💥.💥"])
def test_garbage_tokens_are_rejected(auth_on, bad):
    assert verify_session_token(bad) is None


def test_tampered_or_foreign_tokens_are_rejected(auth_on, monkeypatch):
    token = create_session_token("a@b.co", 60)
    body, signature = token.split(".")
    assert verify_session_token(f"{body}x.{signature}") is None
    assert verify_session_token(f"{body}.{signature[:-2]}AA") is None
    monkeypatch.setattr(settings, "session_secret", SecretStr("other-" + "x" * 40))
    assert verify_session_token(token) is None  # signed with a different secret


# ---- passwords ------------------------------------------------------------------------
def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password("my-password-1"), hash_password("my-password-1")
    assert a != b and a.startswith("scrypt$") and "my-password-1" not in a  # random salt, never plain text
    assert verify_password("my-password-1", a)
    assert not verify_password("My-password-1", a)


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$1$2", "md5$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$16384$8$1$💥$💥"])
def test_malformed_hashes_never_match(stored):
    assert verify_password("anything", stored) is False


def test_password_rules():
    assert security.password_problem("1234567") and security.password_problem("x" * 201)
    assert security.password_problem("12345678") is None


def test_authenticate(accounts):
    with session_scope() as db:
        assert security.authenticate(db, f"  {EMAIL.upper()} ", PASSWORD).email == EMAIL  # email is not case-sensitive
        assert security.authenticate(db, EMAIL, PASSWORD.upper()) is None  # password is
        assert security.authenticate(db, "nobody@else.com", PASSWORD) is None
        assert security.authenticate(db, EMAIL, "") is None


def test_inactive_user_cannot_authenticate(accounts):
    with session_scope() as db:
        db.scalar(select(User).where(User.email == TECH_EMAIL)).is_active = False
    with session_scope() as db:
        assert security.authenticate(db, TECH_EMAIL, PASSWORD) is None


# ---- first administrator --------------------------------------------------------------
def test_first_admin_is_created_from_settings_only_when_no_user_exists(monkeypatch):
    with session_scope() as db:
        db.execute(delete(User))
    monkeypatch.setattr(settings, "admin_email", " Boss@Plant.com ")
    monkeypatch.setattr(settings, "admin_password", SecretStr("first-admin-pw"))
    try:
        with session_scope() as db:
            assert security.ensure_first_admin(db) is True
            assert security.ensure_first_admin(db) is False  # a user exists now
            boss = db.scalar(select(User))
            assert (boss.email, boss.role, boss.is_active) == ("boss@plant.com", "admin", True)
            assert verify_password("first-admin-pw", boss.password_hash)
    finally:
        with session_scope() as db:
            db.execute(delete(User))


@pytest.mark.parametrize("email, password", [("boss@plant.com", ""), ("boss@plant.com", "short"), ("not-an-email", "long-enough-pw")])
def test_first_admin_needs_valid_settings(monkeypatch, email, password):
    with session_scope() as db:
        db.execute(delete(User))
    monkeypatch.setattr(settings, "admin_email", email)
    monkeypatch.setattr(settings, "admin_password", SecretStr(password))
    with session_scope() as db:
        assert security.ensure_first_admin(db) is False
        assert db.scalar(select(User)) is None


# ---- throttle -------------------------------------------------------------------------
def test_throttle_blocks_after_limit_and_recovers():
    t = LoginThrottle(max_failures=3, window_seconds=60)
    for i in range(3):
        assert t.retry_after("ip", now=i) == 0
        t.record_failure("ip", now=i)
    assert 0 < t.retry_after("ip", now=3) <= 60
    assert t.retry_after("other", now=3) == 0  # per client
    assert t.retry_after("ip", now=62) == 0  # window passed
    t.record_failure("ip", now=62)
    t.reset("ip")
    assert t.retry_after("ip", now=62) == 0


# ---- API ------------------------------------------------------------------------------
def test_protected_endpoints_need_sign_in(http):
    for path in ("/api/equipment", "/api/analytics/summary", "/api/documents", "/api/maintenance", "/api/knowledge/stats",
                 "/api/users"):
        r = http.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "unauthorized"
    assert http.post("/api/ask", json={"question": "How are you?"}).status_code == 401
    assert http.get("/api/auth/me").status_code == 401


def test_public_endpoints_stay_open(http):
    assert http.get("/api/health/live").status_code == 200
    assert http.get("/api/health").status_code == 200


def test_login_sets_httponly_cookie_and_unlocks_api(http):
    r = _login(http)
    assert r.status_code == 200
    assert r.json() == {"email": EMAIL, "name": "Ada Admin", "role": "admin", "auth_required": True}
    cookie = r.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age" not in cookie  # no "Remember me": ends with the browser session
    assert http.get("/api/auth/me").json()["email"] == EMAIL
    assert http.get("/api/equipment").status_code == 200


def test_login_reports_the_role(http):
    assert _login(http, TECH_EMAIL).json()["role"] == "technician"


def test_remember_me_sets_a_long_lived_cookie(http, monkeypatch):
    monkeypatch.setattr(settings, "remember_days", 7)
    assert f"max-age={7 * 86400}" in _login(http, remember=True).headers["set-cookie"].lower()


def test_wrong_credentials_are_rejected_without_a_cookie(http):
    for email, password in ((EMAIL, "nope"), ("x@y.co", PASSWORD)):
        r = _login(http, email, password)
        assert r.status_code == 401
        assert r.json()["error"]["message"] == "Incorrect email or password."  # does not reveal which field
        assert "set-cookie" not in r.headers
    assert http.get("/api/equipment").status_code == 401


def test_deactivated_user_cannot_sign_in(http):
    with session_scope() as db:
        db.scalar(select(User).where(User.email == TECH_EMAIL)).is_active = False
    assert _login(http, TECH_EMAIL).status_code == 401


def test_deactivating_a_user_ends_their_open_session(accounts):
    tech = accounts(TECH_EMAIL)
    assert tech.get("/api/equipment").status_code == 200
    with session_scope() as db:
        db.scalar(select(User).where(User.email == TECH_EMAIL)).is_active = False
    assert tech.get("/api/equipment").status_code == 401


def test_deleted_user_cookie_stops_working(accounts):
    tech = accounts(TECH_EMAIL)
    with session_scope() as db:
        db.execute(delete(User).where(User.email == TECH_EMAIL))
    assert tech.get("/api/auth/me").status_code == 401


def test_too_many_failures_are_throttled_then_even_correct_password_waits(http):
    for _ in range(5):
        assert _login(http, password="wrong").status_code == 401
    blocked = _login(http, password="wrong")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert _login(http).status_code == 429


def test_successful_login_clears_earlier_failures(http):
    for _ in range(4):
        _login(http, password="wrong")
    assert _login(http).status_code == 200
    for _ in range(4):
        assert _login(http, password="wrong").status_code == 401  # counter started again


def test_logout_ends_the_session(http):
    _login(http)
    r = http.post("/api/auth/logout")
    assert r.status_code == 204 and COOKIE_NAME in r.headers["set-cookie"]
    http.cookies.clear()
    assert http.get("/api/auth/me").status_code == 401


def test_forged_cookie_is_rejected(http):
    http.cookies.set(COOKIE_NAME, "e30.AAAA")
    assert http.get("/api/equipment").status_code == 401


def test_cookie_for_an_unknown_email_is_rejected(http):
    http.cookies.set(COOKIE_NAME, create_session_token("ghost@nowhere.com", 600))
    assert http.get("/api/equipment").status_code == 401


def test_login_validates_input(http):
    assert http.post("/api/auth/login", json={"email": "", "password": "x"}).status_code == 422
    assert http.post("/api/auth/login", json={"email": "a@b.co"}).status_code == 422
    assert http.post("/api/auth/login", json={"email": "a@b.co", "password": "x" * 201}).status_code == 422


def test_when_auth_is_disabled_everyone_is_an_admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    http = TestClient(app)
    assert http.get("/api/equipment").status_code == 200
    assert http.get("/api/users").status_code == 200
    me = http.get("/api/auth/me").json()
    assert me["role"] == "admin" and me["auth_required"] is False
    assert http.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}).json()["auth_required"] is False


# ---- change password ------------------------------------------------------------------
def test_change_password(accounts):
    tech = accounts(TECH_EMAIL)
    ok = tech.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "brand-new-pass"})
    assert ok.status_code == 204
    fresh = TestClient(app)
    assert _login(fresh, TECH_EMAIL, PASSWORD).status_code == 401  # the old one no longer works
    assert _login(fresh, TECH_EMAIL, "brand-new-pass").status_code == 200


@pytest.mark.parametrize("current, new, status", [
    ("wrong-current", "brand-new-pass", 400),
    (PASSWORD, "short", 422),
    (PASSWORD, PASSWORD, 422),
])
def test_change_password_rejects_bad_input(accounts, current, new, status):
    r = accounts(TECH_EMAIL).post("/api/auth/change-password", json={"current_password": current, "new_password": new})
    assert r.status_code == status


def test_change_password_needs_sign_in(http):
    assert http.post("/api/auth/change-password", json={"current_password": "a", "new_password": "b"}).status_code == 401


# ---- production safety ----------------------------------------------------------------
def test_production_requires_strong_secrets():
    # Field names (not env names) are used, because the test run sets AUTH_ENABLED=false in the environment.
    ok = dict(app_env="production", auth_enabled=True, admin_password="a-long-private-password", session_secret="r" * 40)
    Settings(_env_file=None, **ok)
    for bad in ({"admin_password": ""}, {"admin_password": "short"}, {"admin_password": "ChangeMe-Now-123"},
                {"session_secret": ""}, {"session_secret": "short"}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **{**ok, **bad})
    Settings(_env_file=None, app_env="production", auth_enabled=False)  # explicitly open: allowed


def test_settings_summary_never_contains_secrets():
    summary = Settings(_env_file=None, admin_password="a-long-private-password", session_secret="r" * 40).safe_summary()
    assert "a-long-private-password" not in str(summary) and "r" * 40 not in str(summary)
    assert summary["admin_password_set"] is True


# ---- the login page comes first after every start ---------------------------------------------
def test_cookies_from_an_earlier_run_stop_working(monkeypatch):
    token = create_session_token("a@b.co", 3600)
    assert verify_session_token(token) == "a@b.co"
    monkeypatch.setattr(security, "_EPHEMERAL_SECRET", b"x" * 32)  # what a restart does: a new random value
    assert verify_session_token(token) is None


def test_restart_does_not_sign_out_when_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "login_on_start", False)
    monkeypatch.setattr(settings, "session_secret", SecretStr("s" * 40))  # a configured secret survives restarts
    token = create_session_token("a@b.co", 3600)
    monkeypatch.setattr(security, "_EPHEMERAL_SECRET", b"x" * 32)
    assert verify_session_token(token) == "a@b.co"