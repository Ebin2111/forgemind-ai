"""Troubleshooting: service logic (isolated in-memory DB) and POST /api/troubleshoot."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.models.db_models import Equipment, WorkOrder
from backend.app.schemas import TroubleshootRequest
from backend.app.services import troubleshooting as svc

URL = "/api/troubleshoot"


# --- service, on a private in-memory database ----------------------------------------------
@pytest.fixture()
def db():
    from backend.app.models import db_models  # noqa: F401

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        pump = Equipment(tag="P-101", name="Feed Pump", type="Pump", location="Bay 1", manufacturer="Grundfos")
        fan = Equipment(tag="F-201", name="Exhaust Fan", type="Fan", location="Roof")
        session.add_all([pump, fan])
        session.flush()
        session.add_all(
            [
                WorkOrder(wo_number="WO-1", equipment_id=pump.id, title="Bearing noise",
                          description="Replaced worn bearing after vibration alarm", status="closed",
                          created_at=date(2026, 1, 10), downtime_hours=4.0),
                WorkOrder(wo_number="WO-2", equipment_id=pump.id, title="Seal leak",
                          description="Mechanical seal dripping", status="open",
                          created_at=date(2026, 3, 1), downtime_hours=1.5),
                WorkOrder(wo_number="WO-3", equipment_id=fan.id, title="Fan fault E-204",
                          description="Controller showed E-204 overload trip", status="closed",
                          created_at=date(2026, 2, 1), downtime_hours=2.0),
            ]
        )
        session.commit()
        yield session
    engine.dispose()  # close the in-memory connection so no ResourceWarning is left behind


def test_find_equipment_ignores_case_and_whitespace(db):
    assert svc.find_equipment(db, " p-101 ").tag == "P-101"
    assert svc.find_equipment(db, "nope") is None


def test_history_is_computed_in_sql(db):
    h = svc.equipment_history(db, svc.find_equipment(db, "P-101"))
    assert (h.work_orders_total, h.work_orders_open, h.downtime_hours_total) == (2, 1, 5.5)
    assert h.last_work_order_date == date(2026, 3, 1)


def test_history_of_machine_without_work_orders(db):
    eq = Equipment(tag="X-1", name="New", type="T", location="L")
    db.add(eq)
    db.flush()
    h = svc.equipment_history(db, eq)
    assert (h.work_orders_total, h.work_orders_open, h.downtime_hours_total) == (0, 0, 0.0)
    assert h.last_work_order_date is None


def test_similar_orders_are_scoped_to_one_machine(db):
    pump = svc.find_equipment(db, "P-101")
    found = svc.similar_work_orders(db, "strong vibration and bearing noise", None, pump.id)
    assert [w.wo_number for w in found] == ["WO-1"]
    assert "bearing" in found[0].matched_terms  # real words, not stems like 'bear'
    assert all(t not in found[0].matched_terms for t in ("bear", "nois"))


def test_fleet_wide_search_finds_other_machines(db):
    found = svc.similar_work_orders(db, "controller overload trip", None)
    assert [w.wo_number for w in found] == ["WO-3"]


def test_fault_code_outweighs_shared_words(db):
    # WO-1 shares two words with the symptom; WO-3 shares one word plus the exact fault code.
    found = svc.similar_work_orders(db, "vibration bearing trip", "E-204")
    assert found[0].wo_number == "WO-3"


def test_unrelated_symptom_matches_nothing(db):
    assert svc.similar_work_orders(db, "zzzz qqqq", None) == []


def test_limit_is_respected(db):
    assert len(svc.similar_work_orders(db, "bearing seal overload", None, limit=1)) == 1


def test_gather_context_respects_include_history(db):
    pump = svc.find_equipment(db, "P-101")
    off = TroubleshootRequest(symptom="bearing noise", include_history=False)
    ctx = svc.gather_context(db, off, pump)
    assert ctx.equipment is pump and ctx.history is None and ctx.related == []
    on = svc.gather_context(db, TroubleshootRequest(symptom="bearing noise"), pump)
    assert on.history.work_orders_total == 2 and on.related


def test_search_query_includes_machine_and_code(db):
    req = TroubleshootRequest(symptom="loud noise", fault_code="E-204")
    q = svc.build_search_query(req, svc.find_equipment(db, "P-101"))
    assert all(part in q for part in ("loud noise", "E-204", "Feed Pump", "Grundfos"))
    assert svc.build_search_query(TroubleshootRequest(symptom="loud noise"), None) == "loud noise"


def test_question_contains_context_and_task(db):
    pump = svc.find_equipment(db, "P-101")
    req = TroubleshootRequest(symptom="loud noise", fault_code="E-204")
    q = svc.build_question(req, svc.gather_context(db, req, pump))
    for expected in ("Feed Pump (P-101)", "Fault code: E-204", "Symptom: loud noise",
                     "2 work orders (1 not closed)", "WO-1", "only the passages"):
        assert expected in q
    assert "WO-3" not in q  # the fan's order belongs to another machine


# --- HTTP ----------------------------------------------------------------------------------
def test_unknown_equipment_is_404(client):
    r = client.post(URL, json={"symptom": "makes a noise", "equipment_tag": "NOPE-1"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "payload",
    [{}, {"symptom": "ab"}, {"symptom": "ok noise", "equipment_tag": "bad tag!"}, {"symptom": "ok noise", "top_k": 11}],
)
def test_invalid_requests_are_422(client, payload):
    assert client.post(URL, json=payload).status_code == 422


def test_known_machine_returns_context_even_without_documents(client):
    body = client.post(URL, json={"symptom": "spindle vibration at high speed", "equipment_tag": "cnc-101"}).json()
    assert body["equipment"]["tag"] == "CNC-101"
    assert body["history"]["work_orders_total"] >= 1
    assert body["related_work_orders"][0]["wo_number"] == "WO-1001"
    assert body["sources"] == [] and body["generated_by"] == "none"


def test_without_tag_there_is_no_equipment_or_history(client):
    body = client.post(URL, json={"symptom": "servo alarm axis 3"}).json()
    assert body["equipment"] is None and body["history"] is None
    assert body["related_work_orders"][0]["wo_number"] == "WO-1005"  # fleet-wide match


def test_include_history_false_skips_work_orders(client):
    body = client.post(URL, json={"symptom": "spindle vibration", "equipment_tag": "CNC-101", "include_history": False}).json()
    assert body["equipment"]["tag"] == "CNC-101"
    assert body["history"] is None and body["related_work_orders"] == []


def test_answers_with_sources_from_uploaded_manuals(client, docs):
    docs("cnc_manual.pdf", pages=[["Spindle vibration: check drawbar torque and inspect the spindle bearings."]])
    body = client.post(URL, json={"symptom": "spindle vibration", "equipment_tag": "CNC-101"}).json()
    assert body["sources"][0]["document"] == "cnc_manual.pdf"
    assert body["generated_by"] == "extractive" and "cnc_manual.pdf" in body["answer"]


def test_model_receives_machine_history_and_passages(client, docs, fake_gemini):
    docs("cnc_manual.pdf", pages=[["Spindle vibration: check drawbar torque and inspect the spindle bearings."]])
    fake = fake_gemini("Check the drawbar torque [1].")
    body = client.post(URL, json={"symptom": "spindle vibration", "equipment_tag": "CNC-101", "fault_code": "SP-12"}).json()
    assert body["generated_by"] != "extractive" and "[1]" in body["answer"]
    for expected in ("CNC Machining Center (CNC-101)", "Fault code: SP-12", "WO-1001", "drawbar torque"):
        assert expected in fake.prompt


def test_matched_terms_show_the_fault_code_as_typed(db):
    found = svc.similar_work_orders(db, "controller trip", "E-204")
    assert "e-204" in found[0].matched_terms