"""Document download / re-index / summary, work-order creation and work-order search."""
import re

import pytest

from backend.app.api.documents import _spread
from backend.app.core.config import settings
from backend.app.db import session_scope
from backend.app.models.db_models import WorkOrder

PAGES = [["Replace the oil separator element every 4000 operating hours."], ["Check the coolant level weekly."]]


@pytest.fixture()
def uploaded(docs):
    r = docs("extras.pdf", pages=PAGES)
    assert r.status_code == 201
    return r.json()


@pytest.fixture()
def new_orders():
    """Work orders created by a test are removed afterwards so other tests see the seeded data only."""
    created: list[str] = []
    yield created
    with session_scope() as db:
        for number in created:
            order = db.query(WorkOrder).filter_by(wo_number=number).one_or_none()
            if order:
                db.delete(order)


# ---- download ---------------------------------------------------------------------------
class TestDownload:
    def test_returns_the_original_pdf(self, client, uploaded):
        r = client.get(f"/api/documents/{uploaded['id']}/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF-")
        assert "extras.pdf" in r.headers["content-disposition"]

    def test_unknown_document_is_404(self, client):
        assert client.get("/api/documents/999999/download").status_code == 404

    def test_missing_file_is_404_with_a_clear_message(self, client, uploaded):
        (settings.uploads_dir / uploaded["filename"]).unlink()
        r = client.get(f"/api/documents/{uploaded['id']}/download")
        assert r.status_code == 404 and "missing" in r.json()["error"]["message"]


# ---- re-index ---------------------------------------------------------------------------
class TestReindex:
    def test_rebuilds_the_index_and_keeps_search_working(self, client, uploaded):
        r = client.post(f"/api/documents/{uploaded['id']}/reindex")
        assert r.status_code == 200
        body = r.json()
        assert (body["pages"], body["chunks"]) == (uploaded["pages"], uploaded["chunks"])
        hits = client.get("/api/knowledge/passages", params={"document": uploaded["filename"]}).json()
        assert len(hits) == body["chunks"]  # no duplicates and none lost

    def test_unknown_document_is_404(self, client):
        assert client.post("/api/documents/999999/reindex").status_code == 404

    def test_missing_file_is_404(self, client, uploaded):
        (settings.uploads_dir / uploaded["filename"]).unlink()
        assert client.post(f"/api/documents/{uploaded['id']}/reindex").status_code == 404

    def test_corrupt_stored_file_is_a_400_and_keeps_the_old_index(self, client, uploaded):
        (settings.uploads_dir / uploaded["filename"]).write_bytes(b"%PDF-1.4 not really a pdf")
        assert client.post(f"/api/documents/{uploaded['id']}/reindex").status_code == 400
        still = client.get("/api/knowledge/passages", params={"document": uploaded["filename"]}).json()
        assert len(still) == uploaded["chunks"]


# ---- summary ----------------------------------------------------------------------------
class TestSummary:
    def test_summarises_with_gemini_using_only_that_documents_text(self, client, uploaded, fake_gemini):
        fake = fake_gemini("It covers separator service [1].")
        r = client.post(f"/api/documents/{uploaded['id']}/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["generated_by"] == settings.gemini_model and "[1]" in body["answer"]
        assert body["passages_used"] >= 1
        assert "oil separator" in fake.prompt and "extras.pdf" in fake.prompt

    def test_works_without_a_key_by_returning_excerpts(self, client, uploaded):
        body = client.post(f"/api/documents/{uploaded['id']}/summary").json()
        assert body["generated_by"] == "extractive" and body["answer"]

    def test_unknown_document_is_404(self, client):
        assert client.post("/api/documents/999999/summary").status_code == 404


def test_spread_covers_first_to_last_without_repeats():
    picked = _spread(list(range(100)), 8)
    assert len(picked) == 8 and picked[0] == 0 and picked[-1] == 99
    assert picked == sorted(set(picked))
    assert _spread([1, 2, 3], 8) == [1, 2, 3]
    assert _spread([], 8) == []


# ---- create work order ------------------------------------------------------------------
class TestCreateWorkOrder:
    def equipment_id(self, client):
        return client.get("/api/equipment").json()[0]["id"]

    def test_creates_an_open_work_order_with_a_new_number(self, client, new_orders):
        eq = self.equipment_id(client)
        r = client.post("/api/maintenance", json={"equipment_id": eq, "title": "  Grease bearings  ",
                                                  "priority": "high", "technician": "A. Rao", "downtime_hours": 1.5})
        assert r.status_code == 201
        wo = r.json()
        new_orders.append(wo["wo_number"])
        assert re.fullmatch(r"WO-\d+", wo["wo_number"])
        assert (wo["status"], wo["priority"], wo["title"], wo["downtime_hours"]) == ("open", "high", "Grease bearings", 1.5)
        assert wo["equipment_id"] == eq and wo["created_at"]
        listed = client.get("/api/maintenance", params={"q": wo["wo_number"]}).json()
        assert [o["wo_number"] for o in listed] == [wo["wo_number"]]

    def test_numbers_increase(self, client, new_orders):
        eq = self.equipment_id(client)
        nums = []
        for title in ("First job", "Second job"):
            wo = client.post("/api/maintenance", json={"equipment_id": eq, "title": title}).json()
            new_orders.append(wo["wo_number"])
            nums.append(int(wo["wo_number"].split("-")[1]))
        assert nums[1] == nums[0] + 1

    @pytest.mark.parametrize(
        "payload, status",
        [
            ({"equipment_id": 999999, "title": "Valid title"}, 404),
            ({"equipment_id": 1, "title": "ab"}, 422),
            ({"equipment_id": 1, "title": "Valid title", "priority": "urgent"}, 422),
            ({"equipment_id": 1, "title": "Valid title", "downtime_hours": -1}, 422),
            ({"title": "Valid title"}, 422),
        ],
    )
    def test_rejects_bad_input(self, client, payload, status):
        assert client.post("/api/maintenance", json=payload).status_code == status


# ---- work-order search ------------------------------------------------------------------
class TestWorkOrderSearch:
    def test_matches_title_case_insensitively(self, client):
        everything = client.get("/api/maintenance").json()
        word = everything[0]["title"].split()[0]
        found = client.get("/api/maintenance", params={"q": word.upper()})
        assert found.status_code == 200
        assert everything[0]["wo_number"] in [o["wo_number"] for o in found.json()]
        assert int(found.headers["x-total-count"]) == len(found.json())

    def test_wildcard_characters_are_plain_text(self, client):
        for q in ("%", "_", "\\"):
            assert client.get("/api/maintenance", params={"q": q}).json() == []

    def test_blank_search_returns_everything(self, client):
        assert len(client.get("/api/maintenance", params={"q": "  "}).json()) == len(client.get("/api/maintenance").json())

    def test_combines_with_other_filters(self, client):
        closed = client.get("/api/maintenance", params={"status": "closed"}).json()
        word = closed[0]["title"].split()[0]
        both = client.get("/api/maintenance", params={"status": "closed", "q": word}).json()
        assert both and all(o["status"] == "closed" for o in both)