"""Contract tests for the troubleshooting request/response models."""
from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    EquipmentHistory,
    RelatedWorkOrder,
    TroubleshootRequest,
    TroubleshootResponse,
)


def test_request_defaults():
    r = TroubleshootRequest(symptom="Pump is noisy")
    assert r.equipment_tag is None and r.fault_code is None
    assert r.include_history is True
    assert r.top_k is None


def test_request_strips_whitespace():
    r = TroubleshootRequest(symptom="  Pump is noisy  ", equipment_tag=" P-101 ", fault_code=" E-204")
    assert r.symptom == "Pump is noisy"
    assert r.equipment_tag == "P-101"
    assert r.fault_code == "E-204"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_optional_fields_become_none(value):
    r = TroubleshootRequest(symptom="Pump is noisy", equipment_tag=value, fault_code=value)
    assert r.equipment_tag is None and r.fault_code is None


@pytest.mark.parametrize("symptom", ["", "  ", "ab", "x" * 1001])
def test_symptom_length_and_blank_rejected(symptom):
    with pytest.raises(ValidationError):
        TroubleshootRequest(symptom=symptom)


@pytest.mark.parametrize("bad", ["P 101", "-P101", "P-101;DROP", "P-101'", "../etc", "x" * 51])
def test_tag_and_code_pattern_rejected(bad):
    with pytest.raises(ValidationError):
        TroubleshootRequest(symptom="Pump is noisy", equipment_tag=bad)
    with pytest.raises(ValidationError):
        TroubleshootRequest(symptom="Pump is noisy", fault_code=bad)


@pytest.mark.parametrize("ok", ["P-101", "E204", "F0003", "A1.2", "ZONE:3/B"])
def test_tag_and_code_pattern_accepted(ok):
    assert TroubleshootRequest(symptom="Pump is noisy", equipment_tag=ok).equipment_tag == ok


@pytest.mark.parametrize("k,valid", [(0, False), (1, True), (10, True), (11, False)])
def test_top_k_range(k, valid):
    if valid:
        assert TroubleshootRequest(symptom="Pump is noisy", top_k=k).top_k == k
    else:
        with pytest.raises(ValidationError):
            TroubleshootRequest(symptom="Pump is noisy", top_k=k)


def test_request_openapi_example_is_valid():
    example = TroubleshootRequest.model_config["json_schema_extra"]["examples"][0]
    assert TroubleshootRequest(**example).equipment_tag == "P-101"


def test_history_rejects_negative_numbers():
    with pytest.raises(ValidationError):
        EquipmentHistory(work_orders_total=-1, work_orders_open=0, downtime_hours_total=0)
    with pytest.raises(ValidationError):
        EquipmentHistory(work_orders_total=1, work_orders_open=0, downtime_hours_total=-0.5)


def test_related_work_order_from_orm_object():
    class Row:
        wo_number = "WO-1"
        title = "Replace bearing"
        description = "Bearing worn"
        priority = "high"
        status = "closed"
        created_at = date(2026, 1, 5)
        downtime_hours = 4.5

    wo = RelatedWorkOrder.model_validate(Row())
    assert wo.matched_terms == []
    assert wo.created_at == date(2026, 1, 5)


def test_response_minimal_and_serialisation():
    resp = TroubleshootResponse(
        answer="Check the bearing [1].",
        retrieval_mode="hybrid",
        generated_by="extractive",
        latency_ms=12,
        history=EquipmentHistory(
            work_orders_total=2,
            work_orders_open=1,
            downtime_hours_total=6.5,
            last_work_order_date=date(2026, 3, 1),
        ),
    )
    data = resp.model_dump(mode="json")
    assert data["equipment"] is None
    assert data["related_work_orders"] == [] and data["sources"] == []
    assert data["history"]["last_work_order_date"] == "2026-03-01"


def test_response_rejects_unknown_retrieval_mode_and_negative_latency():
    with pytest.raises(ValidationError):
        TroubleshootResponse(answer="x", retrieval_mode="magic", generated_by="g", latency_ms=1)
    with pytest.raises(ValidationError):
        TroubleshootResponse(answer="x", retrieval_mode="hybrid", generated_by="g", latency_ms=-1)


def test_list_defaults_are_not_shared_between_instances():
    a = TroubleshootResponse(answer="x", retrieval_mode="hybrid", generated_by="g", latency_ms=1)
    b = TroubleshootResponse(answer="y", retrieval_mode="hybrid", generated_by="g", latency_ms=1)
    a.sources.append(object())  # type: ignore[arg-type]
    assert b.sources == []