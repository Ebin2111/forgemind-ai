"""Shared test setup.

Tests run against a throw-away database and data folders, never your real ./data, and with no
Gemini key, so a developer's .env cannot leak into (or be modified by) the test run. The
environment variables below must be set before any ``backend.app`` module reads its settings.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="forgemind-tests-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

os.environ.update(
    APP_ENV="test",
    LOG_LEVEL="WARNING",
    DATABASE_URL=f"sqlite:///{_TMP / 'test.db'}",
    UPLOADS_DIR=str(_TMP / "uploads"),
    PROCESSED_DIR=str(_TMP / "processed"),
    INDEXES_DIR=str(_TMP / "indexes"),
    GEMINI_API_KEY="",
    AUTO_REGISTER_EQUIPMENT="false",  # uploads in tests must not add machines to the shared registry
    ADMIN_EMAIL="admin@forgemind.test",  # tests must not depend on the admin settings in your .env
    ADMIN_PASSWORD="",
    AUTH_ENABLED="false",  # the API tests call endpoints directly; test_auth.py switches sign-in on
    ENABLE_SEMANTIC_SEARCH="false",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.generation import gemini_client  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.tests.helpers import FakeGemini, make_pdf_bytes  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create the schema and sample data once, exactly as app startup does, so any test file can run
    alone and in any order (both steps are idempotent)."""
    from backend.app.db import init_db, session_scope
    from backend.app.services.seed import seed_sample_data

    init_db()
    with session_scope() as db:
        seed_sample_data(db)


@pytest.fixture(scope="session")
def client():
    """One app instance for the whole run (startup creates tables and seeds sample data)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_pdf():
    pytest.importorskip("reportlab")
    return make_pdf_bytes


@pytest.fixture()
def docs(client, make_pdf):
    """Upload PDFs through the real API; every document is removed again after the test."""

    def upload(name="manual.pdf", pages=None, **kwargs):
        pages = pages or [["Replace the oil separator element every 4000 operating hours."]]
        return client.post(
            "/api/documents/upload", files={"file": (name, make_pdf(pages), "application/pdf")}, **kwargs
        )

    yield upload
    for doc in client.get("/api/documents").json():
        client.delete(f"/api/documents/{doc['id']}")


@pytest.fixture()
def fake_gemini(monkeypatch):
    """Enable Gemini with a scripted fake client: ``fake = fake_gemini(reply, error, ...)``."""
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-key"))
    monkeypatch.setattr(gemini_client, "_sleep", lambda _seconds: None)

    def install(*outcomes):
        fake = FakeGemini(*outcomes)
        monkeypatch.setattr(gemini_client, "_get_client", lambda: fake)
        return fake

    return install


ADMIN_EMAIL = "admin@forgemind.test"
TECH_EMAIL = "tech@forgemind.test"
PASSWORD = "correct-horse-battery"


@pytest.fixture()
def accounts(monkeypatch):
    """Sign-in switched on, with exactly two accounts: an administrator and a technician (same password).

    Yields a function ``sign_in(email)`` that returns a new test client already signed in as that user."""
    from sqlalchemy import delete

    from backend.app.core import security
    from backend.app.db import session_scope
    from backend.app.models.db_models import User

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "session_secret", SecretStr("s" * 40))
    security.login_throttle.clear()

    def wipe():
        with session_scope() as db:
            db.execute(delete(User))

    wipe()
    with session_scope() as db:
        for email, name, role in ((ADMIN_EMAIL, "Ada Admin", "admin"), (TECH_EMAIL, "Tom Tech", "technician")):
            db.add(User(email=email, name=name, role=role, password_hash=security.hash_password(PASSWORD)))

    def sign_in(email=ADMIN_EMAIL, password=PASSWORD):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return c

    yield sign_in
    security.login_throttle.clear()
    wipe()