"""Entering your own data: equipment from uploaded manuals, add/edit/delete, CSV import, analytics from uploads."""
import pytest

from backend.app.core.config import settings
from backend.app.db import session_scope
from backend.app.models.db_models import Equipment, WorkOrder
from backend.app.services.equipment_naming import guess_name


@pytest.fixture()
def cleanup():
    """Equipment and work orders a test creates are removed afterwards so other tests see the seeded data only."""
    tags: list[str] = []
    yield tags
    with session_scope() as db:
        for tag in tags:
            machine = db.query(Equipment).filter(Equipment.tag == tag).one_or_none()
            if machine:
                db.delete(machine)


def _csv(text: str, name: str = "data.csv"):
    return {"file": (name, text.encode(), "text/csv")}


# ---- naming a machine from its manual ------------------------------------------------------
@pytest.mark.parametrize("filename, expected", [
    ("Atlas_Copco-GA30_Operation_Manual.pdf", "Atlas Copco GA30"),
    ("Siemens S7-1500 user guide (2).pdf", "Siemens S7 1500"),
    ("pump-p101-manual-v2.pdf", "pump p101"),
    ("manual.pdf", ""),
    ("SOP.pdf", ""),
])
def test_guess_name(filename, expected):
    assert guess_name(filename) == expected


# ---- upload registers the machine ---------------------------------------------------------
class TestUploadRegistersEquipment:
    def test_new_machine_appears_in_the_registry(self, client, docs, monkeypatch, cleanup):
        monkeypatch.setattr(settings, "auto_register_equipment", True)
        r = docs("Zephyr Boiler ZB9 Manual.pdf")
        assert r.status_code == 201
        machine = r.json()["registered_equipment"]
        assert machine["name"] == "Zephyr Boiler ZB9" and machine["tag"] == "ZBZ-001" and machine["status"] == "operational"
        cleanup.append(machine["tag"])
        assert any(e["tag"] == machine["tag"] for e in client.get("/api/equipment").json())

    def test_same_machine_is_not_added_twice(self, client, docs, monkeypatch, cleanup):
        monkeypatch.setattr(settings, "auto_register_equipment", True)
        first = docs("Quasar Press QP2 Manual.pdf").json()["registered_equipment"]
        cleanup.append(first["tag"])
        second = docs("Quasar Press QP2 Guide.pdf").json()
        assert second["registered_equipment"] is None

    def test_can_be_switched_off(self, docs, monkeypatch):
        monkeypatch.setattr(settings, "auto_register_equipment", False)
        assert docs("Nimbus Chiller NC4 Manual.pdf").json()["registered_equipment"] is None


# ---- add / edit / delete equipment --------------------------------------------------------
class TestEquipmentCrud:
    def test_create_edit_and_delete(self, client, cleanup):
        r = client.post("/api/equipment", json={"tag": "tst-1", "name": "Test Lathe", "type": "Lathe", "location": "Hall 2"})
        assert r.status_code == 201 and r.json()["tag"] == "TST-1" and r.json()["status"] == "operational"
        cleanup.append("TST-1")
        eid = r.json()["id"]

        r = client.patch(f"/api/equipment/{eid}", json={"status": "fault", "location": "Hall 3"})
        assert r.status_code == 200 and r.json()["status"] == "fault" and r.json()["location"] == "Hall 3"
        assert r.json()["name"] == "Test Lathe"  # untouched fields stay

        assert client.delete(f"/api/equipment/{eid}").json() == {"deleted": "TST-1"}
        assert client.patch(f"/api/equipment/{eid}", json={"status": "fault"}).status_code == 404

    def test_duplicate_tag_is_refused(self, client, cleanup):
        assert client.post("/api/equipment", json={"tag": "DUP-1", "name": "First"}).status_code == 201
        cleanup.append("DUP-1")
        assert client.post("/api/equipment", json={"tag": "dup-1", "name": "Second"}).status_code == 409

    @pytest.mark.parametrize("payload", [{"tag": "", "name": "Valid"}, {"tag": "A", "name": "x"}, {"tag": "A", "name": "Valid", "status": "broken"}])
    def test_bad_input_is_rejected(self, client, payload):
        assert client.post("/api/equipment", json=payload).status_code == 422

    def test_deleting_equipment_removes_its_work_orders(self, client, cleanup):
        eid = client.post("/api/equipment", json={"tag": "CAS-1", "name": "Cascade Test"}).json()["id"]
        cleanup.append("CAS-1")
        wo = client.post("/api/maintenance", json={"equipment_id": eid, "title": "Check belts"}).json()
        client.delete(f"/api/equipment/{eid}")
        with session_scope() as db:
            assert db.query(WorkOrder).filter_by(wo_number=wo["wo_number"]).count() == 0


# ---- update / delete work orders -----------------------------------------------------------
def test_work_order_can_be_closed_and_deleted(client, cleanup):
    eid = client.post("/api/equipment", json={"tag": "WOU-1", "name": "WO Update Test"}).json()["id"]
    cleanup.append("WOU-1")
    wo = client.post("/api/maintenance", json={"equipment_id": eid, "title": "Replace seal"}).json()
    r = client.patch(f"/api/maintenance/{wo['id']}", json={"status": "closed", "downtime_hours": 3.5, "technician": "R. Das"})
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["downtime_hours"] == 3.5
    assert client.patch(f"/api/maintenance/{wo['id']}", json={"status": "nope"}).status_code == 422
    assert client.delete(f"/api/maintenance/{wo['id']}").status_code == 200
    assert client.delete(f"/api/maintenance/{wo['id']}").status_code == 404


# ---- CSV import ---------------------------------------------------------------------------
class TestImport:
    def test_equipment_csv(self, client, cleanup):
        cleanup.extend(["IMP-1", "IMP-2"])
        text = "Tag,Name,Type,Location,Manufacturer,Status\nimp-1,Press One,Press,Hall 1,Acme,operational\nIMP-2,Press Two,Press,Hall 1,Acme,fault\n"
        r = client.post("/api/import/equipment", files=_csv(text))
        assert r.status_code == 200 and r.json() == {"added": 2, "skipped": 0, "errors": []}
        again = client.post("/api/import/equipment", files=_csv(text)).json()
        assert again["added"] == 0 and again["skipped"] == 2 and "already exists" in again["errors"][0]

    def test_bad_rows_are_reported_not_fatal(self, client, cleanup):
        cleanup.append("IMP-3")
        text = "tag,name,status\nIMP-3,Good Machine,operational\nIMP-4,Bad Status,broken\n,No Tag,operational\n"
        r = client.post("/api/import/equipment", files=_csv(text)).json()
        assert r["added"] == 1 and r["skipped"] == 2 and len(r["errors"]) == 2 and r["errors"][0].startswith("Row 3")

    def test_work_orders_csv_and_semicolons(self, client, cleanup):
        cleanup.append("IMP-5")
        eid = client.post("/api/equipment", json={"tag": "IMP-5", "name": "Import Target"}).json()["id"]
        text = ("equipment_tag;title;priority;status;created_at;downtime_hours\n"
                "imp-5;Oil leak;High;In Progress;2026-03-04;2.5\n"
                "imp-5;Belt noise;low;closed;2026-04-10;\n"
                "nope-9;Orphan job;low;open;2026-04-10;0\n")
        r = client.post("/api/import/work-orders", files=_csv(text)).json()
        assert r["added"] == 2 and r["skipped"] == 1 and "not in the registry" in r["errors"][0]
        orders = [o for o in client.get("/api/maintenance", params={"q": "Oil leak"}).json() if o["equipment_id"] == eid]
        assert orders[0]["priority"] == "high" and orders[0]["status"] == "in_progress" and orders[0]["downtime_hours"] == 2.5

    def test_json_file(self, client, cleanup):
        cleanup.append("IMP-6")
        body = b'{"equipment": [{"tag": "IMP-6", "name": "Json Machine"}]}'
        r = client.post("/api/import/equipment", files={"file": ("e.json", body, "application/json")})
        assert r.json()["added"] == 1

    @pytest.mark.parametrize("name, body, code", [("data.xlsx", b"x", 400), ("data.csv", b"", 422), ("data.csv", b"\xff\xfe\x00", 400)])
    def test_unusable_files(self, client, name, body, code):
        assert client.post("/api/import/equipment", files={"file": (name, body, "text/csv")}).status_code == code


# ---- the dashboard numbers come from uploads ---------------------------------------------------
def test_analytics_lists_uploaded_documents(client, docs):
    docs("Analytics Probe.pdf")
    stats = client.get("/api/analytics/summary").json()["document_stats"]
    row = next(d for d in stats if d["filename"] == "Analytics_Probe.pdf")  # spaces in a file name are stored as underscores
    assert row["pages"] == 1 and row["passages"] >= 1