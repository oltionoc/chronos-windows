"""Reading the users enrolled on a device, and matching them to employees.

The device read is read-only and proxies through the worker exactly like
"Sync now"; the new logic here is the annotation: each device user is marked
with the employee it is already linked to (if any), so the UI can offer "link"
or "create employee" without anyone typing device IDs by hand.

The proxy leg is proven over HTTP (an unreachable device fails cleanly); the
annotation is proven in-container with the worker call mocked, since CI has no
real terminal.
"""
import httpx
import pytest

from conftest import RUN_SUFFIX, _compose_exec_python


@pytest.fixture(scope="module")
def user_world(admin_client: httpx.Client, world):
    c = admin_client
    sfx = RUN_SUFFIX
    loc = world["loc_a"]["id"]
    device = c.post(
        "/devices",
        json={
            "location_id": loc,
            "label": f"QA Users Device {sfx}",
            "device_type": "hikvision",
            "ip_address": "10.255.255.7",
            "port": 80,
            "auth_username": "admin",
            "auth_password": "DevicePw123",
            "is_active": True,
        },
    ).json()
    emp = c.post(
        "/employees",
        json={
            "location_id": loc,
            "employee_code": f"DU-{sfx}",
            "first_name": "Device",
            "last_name": "Linked",
            "hire_date": "2025-01-01",
            "base_salary_eur": 1000.0,
            "employment_status": "active",
        },
    ).json()
    # Enrol that employee as device user "1".
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": device["id"], "device_user_id": "1"})
    return {"device": device, "employee": emp}



def test_device_users_are_annotated_with_their_employee_link(user_world):
    """Mock the worker so two device users come back — one already linked to an
    employee, one not — and assert the annotation. Runs in the api container
    with the worker HTTP call patched."""
    device_id = user_world["device"]["id"]
    emp_id = user_world["employee"]["id"]
    out = _compose_exec_python(
        "from unittest.mock import patch\n"
        "import httpx\n"
        "from fastapi.testclient import TestClient\n"
        "class FakeResp:\n"
        "    status_code = 200\n"
        "    def raise_for_status(self): pass\n"
        "    def json(self): return {'users': [\n"
        "        {'device_user_id': '1', 'name': 'Device Linked'},\n"
        "        {'device_user_id': '9', 'name': 'Somebody New'},\n"
        "    ]}\n"
        "with patch.object(httpx, 'post', lambda *a, **k: FakeResp()):\n"
        "    from app.main import app\n"
        "    from app.security import create_access_token, COOKIE_NAME\n"
        "    from app.database import SessionLocal\n"
        "    from app.models import User\n"
        "    db = SessionLocal(); admin = db.query(User).filter(User.role=='admin', User.must_change_password==False).first()\n"
        "    tok = create_access_token(admin.id, 'admin')\n"
        "    c = TestClient(app); c.cookies.set(COOKIE_NAME, tok)\n"
        f"    r = c.post('/api/v1/devices/{device_id}/users')\n"
        "    body = r.json()\n"
        "    rows = {u['device_user_id']: u for u in body['users']}\n"
        f"    print(rows['1']['linked_employee_id'] == {emp_id}, rows['9']['linked_employee_id'] is None, rows['1']['linked_employee_name'])\n"
    )
    assert out.startswith("True True Device Linked"), out
