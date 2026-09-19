from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import SessionLocal
from app.models import LicenseKey, User
from app.routers import (
    attendance,
    auth,
    config as config_router,
    devices,
    employees,
    holidays,
    internal,
    leave,
    license as license_router,
    locations,
    payroll,
    reports,
    rota,
    shift_schedules,
    users,
)
from app.security import COOKIE_NAME, decode_access_token
from app.services.license import license_status

app = FastAPI(title="chronos API", version="1.0.0")

# SECURITY: auth is cookie-based with credentials, so a wildcard origin must
# never be honored — Starlette's CORSMiddleware would otherwise reflect back
# whatever Origin the browser sends (see SECURITY_REPORT.md "CORS wildcard +
# credentials footgun"), which defeats the same-origin protection the cookie
# relies on. `CORS_ORIGINS=*` is therefore treated as "no origins configured"
# rather than "allow any origin".
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip() and o.strip() != "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# SECURITY: server-side enforcement of the "must change password" gate — see
# SECURITY_REPORT.md "bootstrap admin credential". Implemented as middleware
# (rather than a per-router dependency) so it's a single, unmissable
# enforcement point covering every current and future endpoint, without
# touching each router. Allowlists only the auth endpoints a locked-out user
# needs to change their password and log out.
_PASSWORD_GATE_ALLOWLIST = {
    "/api/v1/auth/me",
    "/api/v1/auth/me/password",
    "/api/v1/auth/logout",
}


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@app.middleware("http")
async def restrict_internal_to_loopback(request: Request, call_next):
    """Native deployment only (settings.internal_loopback_only).

    In Docker, nginx returns 404 for /api/v1/internal/ so the LAN can never
    reach the worker->api ingestion endpoints; the shared X-Internal-Key is
    then a second line of defence rather than the only one. The native Windows
    install has no nginx, so the same rule is enforced here: the worker runs on
    this machine and connects over loopback, and anything else gets the same
    404 — deliberately not 403, which would confirm the endpoint exists.

    `request.client.host` is the real peer address because the native server
    runs uvicorn with proxy headers disabled (there is no proxy in front of
    it), so a LAN client cannot claim 127.0.0.1 through X-Forwarded-For.
    """
    if settings.internal_loopback_only and request.url.path.startswith("/api/v1/internal/"):
        host = request.client.host if request.client else None
        if host not in _LOOPBACK_HOSTS:
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})
    return await call_next(request)


@app.middleware("http")
async def enforce_password_change_gate(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/api/v1/")
        and not path.startswith("/api/v1/internal/")
        and path != "/api/v1/auth/login"
        and path not in _PASSWORD_GATE_ALLOWLIST
    ):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            try:
                payload = decode_access_token(token)
            except Exception:
                payload = None
            if payload is not None:
                db = SessionLocal()
                try:
                    user = db.get(User, payload.get("user_id"))
                    if user is not None and user.must_change_password:
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={"detail": "Password change required before continuing."},
                        )
                finally:
                    db.close()
    return await call_next(request)


# Paths that must keep working after the licence expires, so an admin can sign
# in and paste a new key: the auth endpoints, and the licence endpoints. The
# internal ingestion endpoints are never gated here (they are handled by the
# loopback middleware above), so the worker keeps recording punches while the
# licence is expired and no attendance day is lost.
_LICENSE_GATE_ALLOWLIST = {
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
    "/api/v1/auth/me/password",
    "/api/v1/license/status",
}


@app.middleware("http")
async def enforce_license(request: Request, call_next):
    """Blocks the user-facing API when the licence has expired, with a 402 the
    frontend turns into the "licence expired, paste a new key" screen. Read
    per request (a newly pasted key must take effect immediately) but from a
    tiny single-row table, so the cost is negligible."""
    path = request.url.path
    if (
        path.startswith("/api/v1/")
        and not path.startswith("/api/v1/internal/")
        and path not in _LICENSE_GATE_ALLOWLIST
    ):
        db = SessionLocal()
        try:
            row = db.get(LicenseKey, 1)
            status_ = license_status(row.key if row else None)
        finally:
            db.close()
        if status_["expired"]:
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={"detail": "Licence expired", "license": status_},
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Flattens Pydantic's structured 422 error list into a single `detail`
    string. GAP RESOLUTION per FRONTEND_NOTES.md #9: the frontend's
    `extractMessage` only reads `detail`/`message` as a plain string (it does
    not parse FastAPI's default list-of-objects 422 body), so this keeps the
    existing frontend error-banner behavior working without a frontend patch.
    """
    messages = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(messages) or "Validation error"},
    )


API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(locations.router, prefix=API_PREFIX)
app.include_router(devices.router, prefix=API_PREFIX)
app.include_router(employees.router, prefix=API_PREFIX)
app.include_router(shift_schedules.router, prefix=API_PREFIX)
app.include_router(rota.router, prefix=API_PREFIX)
app.include_router(attendance.router, prefix=API_PREFIX)
app.include_router(leave.router, prefix=API_PREFIX)
app.include_router(config_router.router, prefix=API_PREFIX)
app.include_router(holidays.router, prefix=API_PREFIX)
app.include_router(license_router.router, prefix=API_PREFIX)
app.include_router(payroll.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(internal.router, prefix=API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok"}


def _mount_frontend(dist_dir: str) -> None:
    """Serve the built web UI from the API itself (native deployment only).

    Replaces nginx's `try_files $uri $uri/ /index.html`: a real file under the
    build directory is returned as-is (hashed assets, the manual, the
    favicon), and any other path falls back to index.html so the React router
    can handle deep links like /employees/12 on a page refresh.

    Registered last, after every API router, so it can never shadow an API
    route; and anything under /api/ that reached this point is a genuine API
    404, returned as JSON rather than the app's HTML shell.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    root = Path(dist_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"FRONTEND_DIST={dist_dir!r} has no index.html — build the frontend first")

    assets = root / "assets"
    if assets.is_dir():
        # Content-hashed filenames, so they can be cached hard; StaticFiles
        # also handles ranges and conditional requests.
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})
        if full_path:
            candidate = (root / full_path).resolve()
            # Stay inside the build directory: `..` segments or an absolute
            # path must never turn this into a way to read other files on the
            # machine.
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


if settings.frontend_dist:
    _mount_frontend(settings.frontend_dist)
