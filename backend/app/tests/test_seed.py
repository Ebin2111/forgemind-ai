import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.db import Base
from backend.app.models.db_models import Equipment, WorkOrder
from backend.app.services.seed import seed_sample_data


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()  # close the in-memory connection so no ResourceWarning is left behind


def _write(path, equipment, work_orders):
    path.write_text(json.dumps({"equipment": equipment, "work_orders": work_orders}), encoding="utf-8")
    return path


EQ = {"tag": "T-1", "name": "Pump", "type": "Pump", "location": "A"}
WO = {"wo_number": "WO-1", "equipment_tag": "T-1", "title": "Check", "created_at": "2026-10-01"}


def test_default_sample_file_seeds_and_is_idempotent(db):
    first = seed_sample_data(db)
    assert first and first.equipment_added == 6 and first.work_orders_added == 6 and first.skipped == 0
    second = seed_sample_data(db)
    assert not second  # nothing new on a re-run
    assert db.scalar(select(func.count()).select_from(Equipment)) == 6


def test_only_missing_records_are_added(db, tmp_path):
    seed_sample_data(db, _write(tmp_path / "a.json", [EQ], [WO]))
    result = seed_sample_data(
        db, _write(tmp_path / "b.json", [EQ, {**EQ, "tag": "T-2"}], [WO, {**WO, "wo_number": "WO-2", "equipment_tag": "T-2"}])
    )
    assert (result.equipment_added, result.work_orders_added) == (1, 1)


def test_invalid_records_are_skipped_not_fatal(db, tmp_path):
    path = _write(
        tmp_path / "bad.json",
        [EQ, {**EQ, "tag": "T-BAD", "status": "exploded"}],
        [
            WO,
            {**WO, "wo_number": "WO-NOTAG", "equipment_tag": "MISSING"},
            {**WO, "wo_number": "WO-NEG", "downtime_hours": -2},
            {**WO, "wo_number": "WO-DATE", "created_at": "not-a-date"},
        ],
    )
    result = seed_sample_data(db, path)
    assert (result.equipment_added, result.work_orders_added, result.skipped) == (1, 1, 4)
    assert db.scalar(select(func.count()).select_from(WorkOrder)) == 1


def test_missing_or_corrupt_file_returns_empty_result(db, tmp_path):
    assert not seed_sample_data(db, tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert not seed_sample_data(db, broken)