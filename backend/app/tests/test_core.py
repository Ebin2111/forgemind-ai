"""Configuration and database-model tests."""
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import Settings
from backend.app.db import check_db, session_scope
from backend.app.models.db_models import Document, Equipment, WorkOrder


# --- configuration ---------------------------------------------------------------
class TestSettings:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"chunk_size": 200, "chunk_overlap": 300},
            {"chunk_size": 200, "chunk_overlap": 200},
            {"app_env": "production", "cors_origins": "*"},
            {"app_env": "production", "cors_origins": "https://a.example, *"},
            {"top_k": 0},
            {"max_upload_mb": 0},
            {"gemini_temperature": 1.5},
            {"gemini_max_retries": 99},
            {"gemini_timeout_seconds": 1},
            {"log_level": "CHATTY"},
        ],
    )
    def test_invalid_combinations_are_rejected_at_startup(self, overrides):
        with pytest.raises(ValidationError):
            Settings(**overrides)

    @pytest.mark.parametrize("raw, expected", [("v1/", "/v1"), ("/api", "/api"), ("//api//", "/api"), ("", "")])
    def test_api_prefix_is_normalised(self, raw, expected):
        assert Settings(api_prefix=raw).api_prefix == expected

    def test_values_are_normalised_and_derived(self):
        s = Settings(log_level="debug", app_env="PRODUCTION", cors_origins="https://a.example, https://b.example", max_upload_mb=2)
        assert (s.log_level, s.app_env, s.is_production) == ("DEBUG", "production", True)
        assert s.cors_origin_list == ["https://a.example", "https://b.example"]
        assert s.max_upload_bytes == 2 * 1024 * 1024

    def test_secrets_never_appear_in_logs_or_repr(self):
        s = Settings(gemini_api_key="super-secret", database_url="postgresql://user:hunter2@db/forge")
        assert s.gemini_enabled is True
        dump = f"{s.safe_summary()} {s!r} {s}"
        assert "super-secret" not in dump and "hunter2" not in dump

    def test_gemini_is_disabled_without_a_key(self):
        assert Settings(gemini_api_key="   ").gemini_enabled is False

    def test_defaults_are_sensible_for_an_industrial_assistant(self):
        s = Settings()
        assert s.gemini_model != "gemini-2.0-flash"  # retired model must not be the default
        assert s.gemini_temperature <= 0.3  # factual, repeatable answers
        assert s.chunk_overlap < s.chunk_size


# --- database ---------------------------------------------------------------------
class TestModels:
    def test_database_is_reachable(self):
        assert check_db() is True

    @pytest.mark.parametrize(
        "make",
        [
            lambda: Equipment(tag="BAD-STATUS", name="x", type="x", location="x", status="exploded"),
            lambda: Document(filename="neg.pdf", pages=-1, chunks=0),
        ],
    )
    def test_invalid_rows_are_rejected_by_the_database(self, make):
        with pytest.raises(IntegrityError):
            with session_scope() as db:
                db.add(make())

    @pytest.mark.parametrize(
        "fields",
        [{"priority": "urgent"}, {"status": "paused"}, {"downtime_hours": -1.0}],
    )
    def test_invalid_work_orders_are_rejected(self, fields):
        with pytest.raises(IntegrityError):
            with session_scope() as db:
                eq = db.scalar(select(Equipment).limit(1))
                db.add(WorkOrder(wo_number="WO-BAD", equipment_id=eq.id, title="t", **fields))

    def test_orphan_work_orders_are_rejected(self):
        with pytest.raises(IntegrityError):
            with session_scope() as db:
                db.add(WorkOrder(wo_number="WO-ORPHAN", equipment_id=987654, title="t"))

    def test_duplicate_tags_are_rejected(self):
        with pytest.raises(IntegrityError):
            with session_scope() as db:
                db.add(Equipment(tag="CNC-101", name="dup", type="x", location="x"))

    def test_deleting_equipment_removes_its_work_orders(self):
        with session_scope() as db:
            eq = Equipment(tag="TMP-1", name="Temp", type="Pump", location="Lab")
            eq.work_orders.append(WorkOrder(wo_number="WO-TMP-1", title="Temp job"))
            db.add(eq)
        with session_scope() as db:
            db.delete(db.scalar(select(Equipment).where(Equipment.tag == "TMP-1")))
        with session_scope() as db:
            assert db.scalar(select(WorkOrder).where(WorkOrder.wo_number == "WO-TMP-1")) is None

    def test_session_scope_rolls_back_on_error(self):
        with pytest.raises(RuntimeError):
            with session_scope() as db:
                db.add(Equipment(tag="ROLLED-BACK", name="x", type="x", location="x"))
                db.flush()
                raise RuntimeError("fail after flush")
        with session_scope() as db:
            assert db.scalar(select(Equipment).where(Equipment.tag == "ROLLED-BACK")) is None


class TestDbProbe:
    def test_db_status_reports_ok(self):
        from backend.app.db import db_status

        assert db_status() == (True, None)

    def test_db_status_reports_error_type_without_traceback(self, monkeypatch, caplog):
        from backend.app import db

        class Broken:
            def connect(self):
                raise RuntimeError("secret-password-in-message")

        monkeypatch.setattr(db, "engine", Broken())
        with caplog.at_level("WARNING", logger="backend.app.db"):
            assert db.db_status() == (False, "RuntimeError")
            assert db.check_db() is False
        assert "secret-password" not in caplog.text
        assert all(r.exc_info is None for r in caplog.records)

    def test_missing_sqlite_folder_is_created(self, tmp_path):
        from backend.app.db import _ensure_sqlite_dir

        target = tmp_path / "a" / "b" / "forgemind.db"
        _ensure_sqlite_dir(f"sqlite:///{target}")
        assert target.parent.is_dir()

    def test_memory_sqlite_needs_no_folder(self):
        from backend.app.db import _ensure_sqlite_dir

        _ensure_sqlite_dir("sqlite://")  # must not raise
        _ensure_sqlite_dir("sqlite:///:memory:")