from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.routers import (
    attendance,
    auth,
    config as config_router,
    devices,
    employees,
    holidays,
    internal,
    leave,
    locations,
    payroll,
    reports,
    shift_schedules,
    users,
)
from app.security import COOKIE_NAME, decode_access_token

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
app.include_router(attendance.router, prefix=API_PREFIX)
app.include_router(leave.router, prefix=API_PREFIX)
app.include_router(config_router.router, prefix=API_PREFIX)
app.include_router(holidays.router, prefix=API_PREFIX)
app.include_router(payroll.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(internal.router, prefix=API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok"}
