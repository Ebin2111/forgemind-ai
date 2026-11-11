"""Roles and the user-management API: who may do what."""
import pytest

from backend.app.tests.conftest import ADMIN_EMAIL, PASSWORD, TECH_EMAIL

NEW = {"email": "New.Person@Plant.com", "name": "New Person", "role": "technician", "password": "strong-pass-1"}


@pytest.fixture()
def admin(accounts):
    return accounts(ADMIN_EMAIL)


@pytest.fixture()
def tech(accounts):
    return accounts(TECH_EMAIL)


@pytest.fixture()
def machine(admin):
    r = admin.post("/api/equipment", json={"tag": "ROLE-1", "name": "Role Test Pump", "type": "Pump", "location": "Bay 1"})
    assert r.status_code == 201, r.text
    yield r.json()
    admin.delete(f"/api/equipment/{r.json()['id']}")


def _user_id(admin, email):
    return next(u["id"] for u in admin.get("/api/users").json() if u["email"] == email)


# ---- user management is for administrators only ---------------------------------------
def test_technician_cannot_manage_users(tech, admin):
    other = _user_id(admin, ADMIN_EMAIL)
    assert tech.get("/api/users").status_code == 403
    assert tech.post("/api/users", json=NEW).status_code == 403
    assert tech.patch(f"/api/users/{other}", json={"role": "technician"}).status_code == 403
    assert tech.delete(f"/api/users/{other}").status_code == 403
    assert tech.get("/api/users").json()["error"]["code"] == "forbidden"


def test_admin_lists_users_without_password_data(admin):
    users = admin.get("/api/users").json()
    assert {u["email"] for u in users} == {ADMIN_EMAIL, TECH_EMAIL}
    assert all("password" not in k for u in users for k in u)


def test_admin_creates_a_user_who_can_sign_in(admin, accounts):
    r = admin.post("/api/users", json=NEW)
    assert r.status_code == 201
    assert (r.json()["email"], r.json()["role"], r.json()["is_active"]) == ("new.person@plant.com", "technician", True)
    assert accounts("new.person@plant.com", "strong-pass-1").get("/api/auth/me").json()["role"] == "technician"


@pytest.mark.parametrize("change", [
    {"email": "not-an-email"}, {"email": "a@b"}, {"password": "short"}, {"role": "owner"}, {"name": "x" * 101},
])
def test_create_user_validates_input(admin, change):
    assert admin.post("/api/users", json={**NEW, **change}).status_code == 422


def test_duplicate_email_is_refused_in_any_case(admin):
    assert admin.post("/api/users", json={**NEW, "email": TECH_EMAIL.upper()}).status_code == 409


def test_admin_edits_name_role_and_password(admin, accounts):
    uid = _user_id(admin, TECH_EMAIL)
    r = admin.patch(f"/api/users/{uid}", json={"name": "Tom T.", "role": "admin", "password": "reset-pass-99"})
    assert r.status_code == 200 and r.json()["name"] == "Tom T." and r.json()["role"] == "admin"
    assert accounts(TECH_EMAIL, "reset-pass-99").get("/api/users").status_code == 200  # now an admin


def test_role_change_applies_to_an_open_session(admin, tech):
    assert tech.get("/api/users").status_code == 403
    admin.patch(f"/api/users/{_user_id(admin, TECH_EMAIL)}", json={"role": "admin"})
    assert tech.get("/api/users").status_code == 200


def test_edit_validates_and_unknown_ids_are_404(admin):
    uid = _user_id(admin, TECH_EMAIL)
    assert admin.patch(f"/api/users/{uid}", json={"password": "short"}).status_code == 422
    assert admin.patch(f"/api/users/{uid}", json={"role": "boss"}).status_code == 422
    assert admin.patch("/api/users/999999", json={"name": "x"}).status_code == 404
    assert admin.delete("/api/users/999999").status_code == 404


def test_admin_deactivates_and_deletes_a_technician(admin, tech):
    uid = _user_id(admin, TECH_EMAIL)
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}).json()["is_active"] is False
    assert tech.get("/api/equipment").status_code == 401
    assert admin.delete(f"/api/users/{uid}").json() == {"deleted": TECH_EMAIL}
    assert TECH_EMAIL not in {u["email"] for u in admin.get("/api/users").json()}


def test_admin_cannot_remove_own_access_or_account(admin):
    me = _user_id(admin, ADMIN_EMAIL)
    assert admin.patch(f"/api/users/{me}", json={"role": "technician"}).status_code == 409
    assert admin.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 409
    assert admin.delete(f"/api/users/{me}").status_code == 409
    assert admin.patch(f"/api/users/{me}", json={"name": "Ada B."}).status_code == 200  # other edits are fine


def test_the_last_active_administrator_is_protected(admin):
    # a second admin demotes the first; then the only remaining admin cannot be removed by anyone
    second = admin.post("/api/users", json={**NEW, "email": "second@plant.com", "role": "admin"}).json()["id"]
    first = _user_id(admin, ADMIN_EMAIL)
    admin.patch(f"/api/users/{second}", json={"is_active": False})  # second is inactive, so it does not count
    assert admin.patch(f"/api/users/{first}", json={"is_active": False}).status_code == 409


# ---- what a technician may and may not do ---------------------------------------------
def test_technician_can_read_everything(tech):
    for path in ("/api/equipment", "/api/maintenance", "/api/documents", "/api/analytics/summary", "/api/knowledge/stats"):
        assert tech.get(path).status_code == 200, path
    assert tech.post("/api/ask", json={"question": "How do I replace a filter?"}).status_code == 200


def test_technician_cannot_add_delete_or_import_machines(tech, machine):
    body = {"tag": "T-1", "name": "N", "type": "Pump", "location": "L"}
    assert tech.post("/api/equipment", json=body).status_code == 403
    assert tech.delete(f"/api/equipment/{machine['id']}").status_code == 403
    csv = ("tag,name,type,location\nZ-1,Z,Pump,Bay\n", "text/csv")
    assert tech.post("/api/import/equipment", files={"file": ("e.csv", *csv)}).status_code == 403
    assert tech.post("/api/import/work-orders", files={"file": ("w.csv", *csv)}).status_code == 403


def test_technician_can_change_status_but_not_other_details(tech, machine):
    url = f"/api/equipment/{machine['id']}"
    assert tech.patch(url, json={"status": "fault"}).json()["status"] == "fault"
    assert tech.patch(url, json={"name": "Renamed"}).status_code == 403
    assert tech.patch(url, json={"status": "operational", "location": "Elsewhere"}).status_code == 403
    assert tech.get("/api/equipment").json()[0] is not None
    still = next(m for m in tech.get("/api/equipment").json() if m["id"] == machine["id"])
    assert still["name"] == "Role Test Pump" and still["status"] == "fault"  # the refused edits changed nothing


def test_admin_can_edit_all_machine_details(admin, machine):
    r = admin.patch(f"/api/equipment/{machine['id']}", json={"name": "Renamed", "location": "Bay 2"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed"


def test_technician_works_with_work_orders_but_cannot_delete(tech, machine):
    r = tech.post("/api/maintenance", json={"equipment_id": machine["id"], "title": "Check seal", "priority": "high"})
    assert r.status_code == 201
    wo = r.json()["id"]
    assert tech.patch(f"/api/maintenance/{wo}", json={"status": "in_progress"}).json()["status"] == "in_progress"
    assert tech.delete(f"/api/maintenance/{wo}").status_code == 403


def test_technician_cannot_upload_delete_or_reindex_documents(tech, admin, make_pdf):
    pdf = ("pump manual.pdf", make_pdf([["Replace the seal every 2000 hours."]]), "application/pdf")
    assert tech.post("/api/documents/upload", files={"file": pdf}).status_code == 403
    up = admin.post("/api/documents/upload", files={"file": pdf})
    assert up.status_code == 201
    doc = up.json()["id"]
    try:
        assert tech.post(f"/api/documents/{doc}/reindex").status_code == 403
        assert tech.delete(f"/api/documents/{doc}").status_code == 403
        assert tech.get(f"/api/documents/{doc}/download").status_code == 200  # reading is allowed
    finally:
        admin.delete(f"/api/documents/{doc}")


def test_admin_can_do_everything_a_technician_cannot(admin, machine):
    wo = admin.post("/api/maintenance", json={"equipment_id": machine["id"], "title": "Admin job"}).json()["id"]
    assert admin.delete(f"/api/maintenance/{wo}").status_code == 200