"""Company-logo endpoint. It must be reachable without a session (the login
screen shows the logo before anyone authenticates) and, with no logo
configured, return 404 so the UI falls back to the built-in Chronos mark —
never 401/402 from the password-change or licence gates."""
import httpx

from conftest import API_BASE_URL


def test_branding_logo_is_public_and_404s_without_a_logo():
    # No cookie, no token — the gates must not intercept it.
    r = httpx.get(f"{API_BASE_URL}/branding/logo", timeout=10)
    assert r.status_code == 404, r.text
