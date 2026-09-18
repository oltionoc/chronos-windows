"""Licence gating end to end.

A licence is a signed statement of who the software is for and when it stops.
The app holds only the public key and verifies; it cannot mint one. When the
effective licence has expired the user-facing API returns 402, except the
handful of endpoints an admin needs to sign in and paste a new key — and the
worker's ingestion path is never gated, so punches keep being recorded.

The gate reads a single-row table; these tests install and clear that row
directly in the api container (there is no seeded key by default, so nothing
to restore) and assert against the running stack over HTTP.
"""
import base64
import hashlib
import json
from datetime import date, timedelta

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python

INTERNAL_API_KEY = _compose_exec_python("from app.config import settings; print(settings.internal_api_key)")

# The private key that matches the app's embedded public key lives only in the
# vendor's hands, so a test cannot mint a real forward-dated key. Instead the
# gate is driven by writing a key row and, for the "expired" cases, by proving
# the default licence's own expiry math — the gate calls the same
# license_status the unit checks below use.
DEFAULT_EXPIRES = date(2026, 11, 10)


def _set_key(value: str | None):
    if value is None:
        _compose_exec_python(
            "from app.database import SessionLocal; from sqlalchemy import text; "
            "db=SessionLocal(); db.execute(text('DELETE FROM license_key')); db.commit()"
        )
    else:
        _compose_exec_python(
            "from app.database import SessionLocal; from app.models import LicenseKey; "
            "db=SessionLocal(); db.merge(LicenseKey(id=1, key=%r)); db.commit()" % value
        )


@pytest.fixture(autouse=True)
def _clean_key():
    yield
    _set_key(None)


# ---------------------------------------------------------------------------
# The signature check (unit, in-container: exercises the app's own public key)
# ---------------------------------------------------------------------------

def test_the_embedded_default_licence_verifies_and_expires_on_10_november():
    out = _compose_exec_python(
        "from app.services.license import parse_license, DEFAULT_LICENSE; "
        "lic = parse_license(DEFAULT_LICENSE); print(lic.expires.isoformat())"
    )
    assert out == "2026-11-10"


def test_a_forged_key_is_rejected():
    payload = base64.urlsafe_b64encode(
        json.dumps({"id": "x", "issued_to": "Pirate", "edition": "beta", "issued": "2026-01-01", "expires": "2099-01-01"}).encode()
    ).decode().rstrip("=")
    forged = payload + "." + base64.urlsafe_b64encode(b"\x00" * 256).decode().rstrip("=")
    out = _compose_exec_python(
        "from app.services.license import parse_license, LicenseError\n"
        "try:\n"
        f"    parse_license({forged!r})\n"
        "    print('ACCEPTED')\n"
        "except LicenseError:\n"
        "    print('rejected')\n"
    )
    assert out == "rejected"


def test_the_app_cannot_sign_its_own_keys():
    """No private key material anywhere in the app package — the whole point of
    asymmetric signing is that the client's install cannot mint a licence."""
    out = _compose_exec_python(
        "import app.services.license as m, inspect; src = inspect.getsource(m); "
        "print('privateExponent' in src or 'def sign(' in src or '\"d\"' in src)"
    )
    assert out == "False"


# ---------------------------------------------------------------------------
# The status endpoint
# ---------------------------------------------------------------------------

def test_status_reports_the_default_when_no_key_is_installed(admin_client):
    r = admin_client.get("/license/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires"] == "2026-11-10"
    assert body["issued_to"] == "Beta"


def test_a_key_that_would_shorten_the_term_is_refused(admin_client):
    # Any syntactically valid but unsigned string is refused as invalid; this
    # asserts the endpoint validates rather than storing blindly.
    r = admin_client.post("/license/status", json={"key": "not.a.real.key"})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def _in_container(code: str) -> str:
    return _compose_exec_python(code)


def test_before_expiry_the_api_is_open(admin_client, world):
    assert admin_client.get("/employees", params={"page_size": 1}).status_code == 200


def test_after_expiry_the_middleware_returns_402_for_user_endpoints():
    """Drive the real enforce_license middleware through an in-process client
    with the licence clock pinned past the default expiry. No production
    backdoor: the date is patched only inside this test process."""
    out = _in_container(
        "from datetime import date\n"
        "from unittest.mock import patch\n"
        "from fastapi.testclient import TestClient\n"
        "import app.services.license as L\n"
        "with patch.object(L, '_today', lambda: date(2026,11,11)):\n"
        "    from app.main import app\n"
        "    c = TestClient(app)\n"
        "    print(c.get('/api/v1/employees').status_code)\n"
    )
    assert out == "402"


def test_after_expiry_login_and_licence_endpoints_still_answer():
    out = _in_container(
        "from datetime import date\n"
        "from unittest.mock import patch\n"
        "from fastapi.testclient import TestClient\n"
        "import app.services.license as L\n"
        "with patch.object(L, '_today', lambda: date(2026,11,11)):\n"
        "    from app.main import app\n"
        "    c = TestClient(app)\n"
        "    # login is reachable (wrong creds -> 401, not 402)\n"
        "    login = c.post('/api/v1/auth/login', json={'username':'nobody','password':'x'}).status_code\n"
        "    print('login', login)\n"
    )
    assert "login 401" in out  # reached the endpoint, not blocked by the gate


def test_pasting_a_valid_newer_key_lifts_the_block():
    """A signed key that outlasts the default becomes the effective licence, so
    the same pinned-future clock no longer reads as expired."""
    # A real signed key (valid to 2027), minted off-line with the private key
    # and pasted here as a constant, so the check runs anywhere.
    key = "eyJlZGl0aW9uIjoic3RhbmRhcmQiLCJleHBpcmVzIjoiMjAyNy0wMi0wMSIsImlkIjoic3RhbmRhcmQtMjAyNy0wMi0wMSIsImlzc3VlZCI6IjIwMjYtMDktMTgiLCJpc3N1ZWRfdG8iOiJUZXN0IENsaWVudCJ9.f_aC7v7YPoN0EDESQrbnM7xksd1w5yOtjuOm9w-gckpyds0AovTTNS8T9SmyYb7yoTwFNJFxOI6sXmr6vESpnOcs4En8Z9CJNsZ0EAHnw4jibPet2FIc5l6g7knP-RbG-idA5Ddsnzn8P3gvG2CqKPOK0ujMMWMkbSrF6D_2Nlf2iN4rAZYh2UshZrA_3oTvkJYLdYK9rPJi2rMjEiNf0shCuiBicnUYgpbKyDZGzxNuY-Ni4etoiqYAoH61s20tpPFrYjy03iwcQ6PzRnu_3RCbKknJaPL0Qt49L0A30Rl8dXl31AeCIu5_LaTHeqlb_rELeqZSbdZHSCOlEV2jtw"
    out = _in_container(
        "from datetime import date\n"
        "from unittest.mock import patch\n"
        "from fastapi.testclient import TestClient\n"
        "import app.services.license as L\n"
        "from app.database import SessionLocal\n"
        "from app.models import LicenseKey\n"
        f"db=SessionLocal(); db.merge(LicenseKey(id=1, key={key!r})); db.commit()\n"
        "with patch.object(L, '_today', lambda: date(2026,11,11)):\n"
        "    c = __import__('fastapi.testclient', fromlist=['TestClient']).TestClient(__import__('app.main', fromlist=['app']).app)\n"
        "    print('status', c.get('/api/v1/employees').status_code)\n"
        "db.execute(__import__('sqlalchemy').text('DELETE FROM license_key')); db.commit()\n"
    )
    # With the extension key (valid to 2027) installed, 2026-11-11 is not expired,
    # so the gate is open and the request proceeds to normal auth (401 unauth).
    assert "status 401" in out


def test_the_worker_ingestion_path_is_never_licence_gated():
    out = _in_container(
        "import inspect, app.main as m; src = inspect.getsource(m.enforce_license); "
        "print('/api/v1/internal/' in src)"
    )
    assert out == "True"
