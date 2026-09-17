# SECURITY_REPORT.md — chronos

Status: **all findings resolved** — zero unresolved high/critical findings.

**Revision 3 (2026-09-16)** covers the multi-vendor device integration
(`BLUEPRINT.md` Section 5.5): the `hikvision` and `hikvision_cloud` adapters,
DB-resident device credentials, the `INET` → `TEXT` widening of
`devices.ip_address`, `attendance_logs.punch_type_hint`, and the
manager-write access-control changes made after `users.can_manage_payroll`
was dropped. 10 findings (2 critical, 3 high, 3 medium, 2 low), all patched;
4 items accepted as-is with reasoning. **One regression against a
previously-closed finding** was found and fixed (Revision 3 finding 34 vs.
Revision 2 finding 28). See the "Revision 3" section at the end of this file.

**Revision 2 (2026-08-23)** covers new surface added since the pass below:
CSV bulk-import (employees + leave records), the location-based access-control
rewrite, `/reports/alerts` + `/reports/analytics`, payroll-run deletion,
config CRUD reachability, the `employees.job_title` field, and `/auth/me`'s
new `location_name`/`employee_name` fields. See "Revision 2" section below
for that pass's findings; everything under "Findings & Patches Applied"
(Revision 1) is the original pass and still holds — re-verified, not
re-litigated, in Revision 2.

Scope audited: `backend/` (FastAPI + SQLAlchemy + Alembic), `worker/` (sync +
nightly-trigger service), `frontend/` (React/Vite), `docker-compose.yml`,
`.env.example`, `frontend/nginx.conf`. Reviewed against OWASP Top 10 (2021)
and the specific risk areas called out in this project's brief (auth/JWT
cookie handling, manager row-level scoping, internal endpoint isolation,
SQL injection, XSS/CSRF, input validation, secrets handling, PDF-generation
SSRF/XXE-style risk, Docker exposure).

Per `DISCOVERY.md`, this is a LAN-only Phase 1 pilot, but audited as if it
could be internet-exposed (Phase 2), per the task brief — findings are not
waved off as "LAN-only so it doesn't matter."

---

## Findings & Patches Applied

### 1. [HIGH] Bootstrap admin account ships with a well-known default password, no enforced change
**CWE-798 / CWE-521.** The Alembic seed migration creates `admin` /
`ChangeMe123!` (`hr_admin` role) so the system is reachable after a fresh
deploy. `BACKEND_NOTES.md` documented "must be changed immediately" but
nothing enforced it — a freshly deployed instance would be exploitable by
anyone who knows this well-published tutorial-style default password, for as
long as the operator forgets (or never gets around) to change it.

**Fix applied** (defense actually enforced server-side, not just documented):
- Added `users.must_change_password` (boolean) — `backend/app/models.py`,
  `backend/alembic/versions/0001_initial.py`. Seeded `true` for the bootstrap
  admin account.
- `POST /users` (new account) and `PATCH /users/{id}/reset-password` now set
  `must_change_password = True` — an HR/Admin choosing a password on someone
  else's behalf always forces a change on next login
  (`backend/app/routers/users.py`).
- `PATCH /auth/me/password` clears the flag on a successful self-service
  change (`backend/app/routers/auth.py`).
- **Server-side gate**, not just a UI nicety: new middleware
  `enforce_password_change_gate` in `backend/app/main.py` returns `403` for
  every `/api/v1/*` request (except `/auth/me`, `/auth/me/password`,
  `/auth/logout`, `/auth/login`, and the shared-secret-protected
  `/internal/*` routes) when the authenticated user's `must_change_password`
  is `true`. This means the restriction holds even if the frontend is
  bypassed entirely (curl/Postman/a modified SPA build).
- `CurrentUser`/`AppUserOut` schemas now expose `must_change_password`
  (`backend/app/schemas.py`).
- Frontend: `CurrentUser`/`AppUser` types updated
  (`frontend/src/api/types.ts`); `ProtectedRoute`
  (`frontend/src/auth/ProtectedRoute.tsx`) redirects to `/settings/profile`
  whenever `must_change_password` is true (mirrors, but does not replace,
  the backend gate); `ProfilePage`
  (`frontend/src/pages/settings/ProfilePage.tsx`) shows an explanatory
  banner and calls `refresh()` after a successful change so the redirect
  clears immediately. New i18n strings added in both `en.json`/`sq.json`.

**Residual risk:** none — this is now enforced end-to-end, server-side.

---

### 2. [HIGH] Internal ingestion API reachable through the public-facing frontend port
**BLUEPRINT.md Section 2.4 / 4.10** states `/internal/*` is "worker → api
only, not reachable from frontend," protected only by a shared secret
(`X-Internal-Key`), explicitly *not* by network segmentation
(`app/routers/internal.py`'s own docstring says as much). However,
`frontend/nginx.conf`'s `location /api/ { proxy_pass http://api:8000/api/; }`
is a blanket prefix match that also forwards `/api/v1/internal/*` — meaning
these endpoints (which can inject arbitrary attendance punches, trigger the
nightly recompute, or overwrite `devices.last_synced_at`) were reachable from
any LAN client hitting the public port `8080`, with the shared secret as the
*only* line of defense instead of defense-in-depth as the architecture
intended.

**Fix applied:** added a `location /api/v1/internal/ { return 404; }` block
in `frontend/nginx.conf`, placed before the generic `/api/` proxy, so these
routes are never forwarded through the public frontend at all. `worker`
already talks to `api` directly over the Docker-internal network
(`API_BASE_URL=http://api:8000/api/v1` in `worker/worker/api_client.py`), so
this doesn't affect any legitimate call path.

**Residual risk:** none for Phase 1. Also removed the unnecessary
`ports: ["8100:8100"]` publish for the `worker` service in
`docker-compose.yml` — the only caller of `worker`'s `/sync/{device_id}` is
`api`, over the internal Docker network; publishing it to the host/LAN was
never required. See finding 8.

---

### 3. [HIGH] `X-Internal-Key` compared with non-constant-time `!=`
**CWE-208 (timing side-channel).** Both `backend/app/deps.py`'s
`verify_internal_key` and `worker/worker/main.py`'s identical check compared
the caller-supplied key to the real secret with plain `!=`, which
short-circuits on the first differing byte — in principle allowing an
attacker with LAN access (and, in Phase 2, network access to the ingestion
API) to recover the key faster than brute force via response-time
measurement. This key guards write access to `attendance_logs` and
`attendance_daily_status` (payroll input data), so it's a meaningful target.

**Fix applied:** both call sites now use `hmac.compare_digest()` instead of
`!=` (`backend/app/deps.py`, `worker/worker/main.py`).

**Residual risk:** none.

---

### 4. [MEDIUM] Insecure secrets have silently-usable defaults outside Docker Compose
`JWT_SECRET` and `INTERNAL_API_KEY` both defaulted to obvious placeholder
strings (`"change-me-in-production"`, `"change-me-internal-key"`) in
`backend/app/config.py` and `worker/worker/config.py`. `docker-compose.yml`
already guards the Compose path with `${VAR:?VAR must be set}`, but that
guard does not cover any other way of running the app (bare `uvicorn`,
`alembic` invoked directly, a future non-Compose deployment, or a `.env`
that's present but incomplete) — in any of those cases the app would boot
silently with the well-known secret and a valid-looking JWT/internal-key
could be forged by anyone who read the source (which they can — this is
effectively a public secret at that point).

**Fix applied:** both `Settings` classes now raise `ValueError` at startup
(pydantic `model_validator`) if `jwt_secret`/`internal_api_key` still equal
the placeholder value, unless the explicit escape hatch
`CHECKIN_ALLOW_INSECURE_SECRETS=1` is set (intended only for isolated tooling
that imports the config module without serving traffic). Verified: importing
`app.config`/`app.main` without real secrets now fails fast with a clear
message; with real secrets, it imports and serves normally (tested with an
in-process `TestClient` against the patched `app.main`).

**Residual risk:** none.

---

### 5. [MEDIUM] CORS wildcard + credentialed cookies footgun
`backend/app/main.py` special-cased `CORS_ORIGINS=*` into
`allow_origins=["*"]` combined with `allow_credentials=True`. Starlette's
`CORSMiddleware` does not send a literal `*` back when credentials are
enabled — it reflects the request's actual `Origin` header instead, which
means (if an operator ever set `CORS_ORIGINS=*`, e.g. copy-pasted from an
unrelated project or "to make CORS errors go away") **any** origin could
make credentialed (cookie-carrying) cross-origin requests, defeating the
same-origin protection the session cookie relies on. Not currently
exploitable (the shipped default is a fixed origin list, and production
serves same-origin via nginx), but a live footgun for anyone who touches
`CORS_ORIGINS` later.

**Fix applied:** `backend/app/main.py` now filters out `*` entirely when
parsing `CORS_ORIGINS` — a wildcard entry is treated as "no origin
configured," never as "allow any origin," given credentialed auth is always
in use. Documented in `.env.example`.

**Residual risk:** none.

---

### 6. [MEDIUM] Unescaped Jinja2 template used for HTML → PDF payslip generation
`backend/app/services/pdf.py` created its Jinja2 `Environment` without
`autoescape`, and the payslip pipeline (`WeasyPrint`) renders arbitrary
HTML/CSS, including following `<img>`/`@import`/`<link>` URLs. Several
values reaching the template are free-text fields with no length/character
restriction: `employees.first_name`/`last_name`/`employee_code`,
`locations.name`, and `payroll_adjustments.reason`
(`PayrollAdjustmentCreate.reason` in `app/schemas.py` is an unconstrained
`str`). All of these are currently only settable by `hr_admin` (a trusted
role in this app), so this was not exploitable by an untrusted party today,
but it is exactly the class of risk called out in this audit's brief
("unsanitized user input reaching HTML-to-PDF rendering — SSRF/XXE-style
risk") and would become directly exploitable the moment any less-trusted
input source feeds these fields (e.g. a future employee self-service portal,
Phase 2 per `BLUEPRINT.md` Section 11) or if an HR workstation is
compromised.

**Fix applied:** `backend/app/services/pdf.py` now constructs the Jinja2
`Environment` with `autoescape=select_autoescape(["html"])`. Verified with a
standalone render test: a `<script>` payload placed in `employee_name` comes
out HTML-entity-escaped in the rendered output rather than as live markup,
which also closes the secondary "injected `<img src=...>` triggers an
outbound WeasyPrint fetch" vector, since any Jinja-supplied string can no
longer break out of its text context to form a new tag/attribute.

**Residual risk:** none for the escaping issue itself. Not fixed (out of
scope / no code change made): WeasyPrint's default remote-URL fetcher is
still active for URLs that are part of the *static* template
(`app/templates/payslip.html` contains none today) — if a future template
edit adds an image/font `src="http://..."`, that's a legitimate outbound
request WeasyPrint will make at generation time. This is not a current
vulnerability (no template today does this) but is worth a one-line note for
whoever edits `payslip.html` next: avoid remote URLs, or pass
`url_fetcher`/`base_url` restrictions to `HTML(...)` if one is ever needed.

---

### 7. [MEDIUM] No brute-force protection on `POST /auth/login`
Login accepted unlimited attempts with no lockout/backoff/rate limiting,
making offline-guessed or credential-stuffed password attacks
straightforward for the small, fixed set of HR/Manager accounts.

**Fix applied:** `backend/app/routers/auth.py` now tracks failed attempts
per-username (case-insensitive) in-memory, and returns `429 Too Many
Requests` after 5 failures within a 15-minute rolling window; the counter is
cleared on a successful login. Verified with a standalone unit test (5
failures → 429; `clear()` → allowed again).

**Residual risk (documented, not fixed):** the counter is per-process,
in-memory state. It resets on container restart and does **not** share state
across multiple `uvicorn` worker processes/replicas. Phase 1 runs a single
`api` container/process (per `docker-compose.yml`'s `command:`, no
`--workers` flag), so this is effective as shipped. **Before any deployment
that runs multiple `api` replicas or worker processes (Phase 2 or a future
scale-out), this must move to a shared store (Redis, or the Postgres `users`
table itself via a `failed_login_count`/`locked_until` column)** — flagging
explicitly so it isn't silently ineffective later. A dedicated library
(`slowapi`, etc.) was intentionally not introduced for a five-account Phase 1
pilot, per this project's simplicity-first guidance; revisit if the
mitigation needs to become distributed.

---

### 8. [MEDIUM] `worker` service published to the host/LAN unnecessarily
`docker-compose.yml` published `worker`'s port with `"8100:8100"`, making its
shared-secret-protected `/sync/{device_id}` endpoint reachable from the LAN
directly. Its only legitimate caller is the `api` service
(`backend/app/routers/devices.py:trigger_sync`), over the Docker-internal
network — the host/LAN never needs to reach it.

**Fix applied:** removed the `ports:` mapping for `worker` in
`docker-compose.yml`. Inter-container calls over the Compose network are
unaffected (no `expose:`/`ports:` directive is required for containers on
the same network to reach each other).

**Residual risk:** none. (`api`'s port `8000` remains published — this is
intentional, matches the documented local-dev workflow in
`BACKEND_NOTES.md` Section 2, and doesn't add meaningful attack surface
beyond what's already reachable via the nginx-proxied `8080`, since both
paths hit the same authenticated API with the same CORS/cookie protections.)

---

### 9. [MEDIUM] No password length/strength floor
`LoginRequest`/`ChangePasswordRequest`/`AppUserCreate`/`ResetPasswordRequest`
in `backend/app/schemas.py` accepted any non-empty string as a password,
including a single character, for both self-service changes and HR/Admin-set
passwords.

**Fix applied:** added `Field(min_length=8)` to `ChangePasswordRequest.new_password`,
`AppUserCreate.password`, and `ResetPasswordRequest.new_password`
(`backend/app/schemas.py`). Verified: a 5-character password is now rejected
with a `422`. (`LoginRequest.password` intentionally left unconstrained — it
must accept whatever a pre-existing account's password is, regardless of
this new floor, so login itself isn't the place to enforce it.)

**Residual risk:** minimum length only, no composition/complexity rules
(uppercase/digit/symbol) and no breached-password check (e.g. HaveIBeenPwned
k-anonymity lookup). Judged proportionate for a 5-10 account internal HR
tool per this project's simplicity-first guidance; revisit if Phase 2 widens
the user base.

---

### 10. [LOW] No root-level `.gitignore` — `.env` had nothing preventing accidental commit
The project has no git repo yet (`devops` will presumably initialize one),
but there was no root `.gitignore` at all. `BACKEND_NOTES.md`'s own setup
instructions are `cp .env.example .env` at the project root — without a
`.gitignore`, the first `git add .`/`git init` in this directory would have
happily staged the real `.env` (containing `JWT_SECRET`, `INTERNAL_API_KEY`,
DB credentials) alongside the code.

**Fix applied:** added `/home/olti/web-agency/chronos/.gitignore` excluding
`.env`/`.env.*` (keeping `.env.example` tracked), Python/Node build
artifacts, and the payslip PDF output directory (contains employee PII).

**Residual risk:** none, provided `devops` doesn't force-add ignored files.

---

### 11. [LOW] Session cookie ships with `Secure=False`
`backend/app/routers/auth.py` sets the session cookie without the `Secure`
flag, meaning it would be sent over plain HTTP. This is a **documented,
deliberate Phase 1 architecture decision** (`BLUEPRINT.md` Section 6.1/8:
LAN-only, no TLS termination in Phase 1; `BACKEND_NOTES.md` Section 7
explicitly flags it for `security`/`devops` review before any internet
exposure) — not an oversight, and not something to silently "fix" by forcing
`Secure=True`, since that would break login entirely over the plain-HTTP LAN
deployment this phase targets (browsers drop `Secure` cookies on non-HTTPS
origins).

**Fix applied:** made it configurable instead of hardcoded — added
`COOKIE_SECURE` setting (`backend/app/config.py`, default `false`, wired
through `docker-compose.yml` and documented in `.env.example`). Default
behavior is unchanged (still `Secure=False`, matching the approved Phase 1
design); flipping it to `true` once TLS is added is now a one-line env
change instead of a code change.

**Residual risk (documented, not fixed — by design):** `Secure=False` remains
the shipped default, appropriate only for the LAN-only, no-TLS Phase 1
deployment this project targets. **Must be set to `true` (and TLS
terminated in front of the app) before any Phase 2 internet-facing
exposure** — this was already flagged by `backend` in `BACKEND_NOTES.md`
and is reconfirmed here.

---

### 12. [LOW / accepted, no fix] CSRF — no anti-CSRF token
Auth is cookie-based (`httpOnly`, `SameSite=Lax`). There is no separate CSRF
token/double-submit-cookie mechanism.

**Assessment (not a gap requiring a fix):** `SameSite=Lax` is an effective,
standard mitigation here because (a) every state-changing endpoint in this
codebase requires `POST`/`PUT`/`PATCH`/`DELETE` — verified by reading every
router (`attendance.py`, `employees.py`, `leave.py`, `payroll.py`,
`devices.py`, `config.py`, `users.py`, `locations.py`,
`shift_schedules.py`); no `GET` endpoint mutates state anywhere — and
`SameSite=Lax` cookies are withheld on cross-site subrequests (the vector
CSRF relies on), only sent on top-level navigation `GET`s, which never
mutate data here. Production also serves frontend and API same-origin via
the nginx proxy (`frontend/nginx.conf`), which is a second independent
layer. Adding a CSRF token on top would be defense-in-depth but not fixing
an active gap; left as-is per this project's simplicity-first guidance.
**Revisit if any future endpoint ever performs a mutation on `GET`, or if
`SameSite` is ever loosened to `None`.**

---

### 13. [LOW / accepted, no fix] `POST /devices/{id}/test-connection` lets `hr_admin` connect to an arbitrary IP:port
`backend/app/routers/devices.py`'s `test_connection` opens a raw TCP
connection (via `pyzk`) to whatever `ip_address`/`port` is stored on the
`devices` row, which `hr_admin` fully controls via `POST/PUT /devices`. In
principle this lets a trusted `hr_admin` account probe arbitrary hosts/ports
reachable from the `api` container (a mild SSRF-adjacent capability).

**Assessment (not fixed):** this is the intended feature (BLUEPRINT.md
Section 4.3: "used for setup verification"), gated to `hr_admin` only
(the same role that already has full read/write access to all business
data, payroll, and user accounts). Restricting it further (e.g. an
IP-range allowlist) isn't specified by `BLUEPRINT.md`/`DISCOVERY.md` and
would require client input on what ranges are legitimate (multi-location
Phase 2 devices). Flagged for `devops`/product to consider a private-IP-range
allowlist if `hr_admin` accounts are ever less trusted than they are today.

---

### 14. [Reviewed, no issue found] SQL injection
Every database access path was checked (`grep` across `app/routers` and
`app/services` for raw string interpolation/`f"...SELECT"`/`.format(`-style
query building — none found). All queries go through the SQLAlchemy ORM
`Query`/`select()` API with bound parameters. No issue.

### 15. [Reviewed, no issue found] XSS in React frontend
No `dangerouslySetInnerHTML`, `innerHTML`, or `eval` usage anywhere in
`frontend/src`. All rendering goes through JSX's default escaping.

### 16. [Reviewed, no issue found] Manager row-level scoping ("own team")
Verified server-side (not just client-filtered) on every endpoint
`BLUEPRINT.md` Section 6.2 and the `FRONTEND_NOTES.md` gap resolution
require it for: `GET /employees`, `GET /employees/{id}`,
`GET /attendance/daily-status`, `GET /leave-records`,
`GET /leave-records/{id}`, `PATCH /leave-records/{id}/approve|reject`,
`GET /reports/dashboard-summary`. Each filters/asserts
`employees.manager_user_id == current_user.id` at the query or object level
before returning data, and returns `403`/empty results rather than relying
on the frontend to hide rows. Write endpoints (`POST/PUT` on employees,
configs, devices, payroll, users) are correctly `hr_admin`-only via
`require_hr_admin`.

### 17. [Reviewed, no issue found] Internal endpoint shared-secret check
`verify_internal_key` (now using `hmac.compare_digest`, see finding 3) is
applied via `dependencies=[Depends(verify_internal_key)]` at the router level
in `backend/app/routers/internal.py`, covering all three internal routes
uniformly; equivalent check exists in `worker/worker/main.py` for the
reverse (`api → worker`) call. Combined with finding 2's nginx fix, these
are now genuinely unreachable from the public frontend port and
secret-gated.

### 18. [Reviewed, no issue found] Input validation via Pydantic
All mutation endpoints (`POST`/`PUT`/`PATCH`) take a typed Pydantic request
model; FastAPI rejects malformed bodies with `422` before the handler runs.
The existing `RequestValidationError` handler in `app/main.py` (pre-existing,
not modified) flattens these into a readable string for the frontend.

### 19. [Reviewed, no issue found] Dependency versions
Checked `backend/requirements.txt`, `worker/requirements.txt`,
`frontend/package.json` against known CVEs. `fastapi==0.115.0` pulls
`starlette<0.39.0`, which is in the range affected by the multipart
form-data DoS (CVE-2024-47874, fixed in starlette 0.40.0) — but
`python-multipart` is **not installed** in this project (`fastapi` is
pinned without the `[standard]` extra that would pull it in, and no
endpoint declares a `Form`/`File`/`UploadFile` parameter anywhere in
`backend/app/routers`), so the vulnerable code path is not reachable in this
codebase. No action taken; noted so a future contributor doesn't
reflexively add file-upload support without revisiting this. No other
dependency in either `requirements.txt` had a known unpatched CVE at time
of review.

---

## Summary (Revision 1)

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Bootstrap admin default credential, no forced change | High | **Fixed** |
| 2 | Internal API reachable via public nginx proxy | High | **Fixed** |
| 3 | Non-constant-time internal-key comparison | High | **Fixed** |
| 4 | Insecure default secrets usable outside Compose | Medium | **Fixed** |
| 5 | CORS wildcard + credentials footgun | Medium | **Fixed** |
| 6 | Unescaped Jinja2 template in PDF pipeline | Medium | **Fixed** |
| 7 | No login brute-force protection | Medium | **Fixed** (residual: single-process only, documented) |
| 8 | `worker` port needlessly published to LAN | Medium | **Fixed** |
| 9 | No password length floor | Medium | **Fixed** |
| 10 | No root `.gitignore` for `.env` | Low | **Fixed** |
| 11 | Cookie `Secure=False` | Low | **Made configurable** (default intentionally unchanged — Phase 1 LAN/no-TLS by design; flip `COOKIE_SECURE=true` before Phase 2) |
| 12 | No CSRF token | Low | **Accepted** — `SameSite=Lax` + no state-changing `GET` + same-origin nginx is adequate |
| 13 | `hr_admin` can probe arbitrary IP:port via test-connection | Low | **Accepted** — intended feature, admin-only, already max-trust role |
| 14–19 | SQLi, XSS, manager scoping, internal-key gating, Pydantic validation, dependency CVEs | — | **Reviewed, no issue found** |

**Zero unresolved high/critical findings (Revision 1).**

## Files changed (Revision 1)

- `backend/app/config.py`, `backend/app/deps.py`, `backend/app/main.py`,
  `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/app/security.py` (no functional change, referenced only),
  `backend/app/routers/auth.py`, `backend/app/routers/users.py`,
  `backend/app/services/pdf.py`,
  `backend/alembic/versions/0001_initial.py`
- `worker/worker/config.py`, `worker/worker/main.py`
- `frontend/src/api/types.ts`, `frontend/src/auth/ProtectedRoute.tsx`,
  `frontend/src/pages/settings/ProfilePage.tsx`,
  `frontend/src/i18n/locales/en.json`, `frontend/src/i18n/locales/sq.json`
- `docker-compose.yml`, `.env.example`, `frontend/nginx.conf`, `.gitignore` (new)

## Verification performed (Revision 1)

- `npm run build` (frontend): succeeds, no TypeScript errors.
- Backend: all `.py` files parse (`ast.parse`); `app.main` and `app.config`
  import successfully in an isolated venv with the real dependency set
  (`fastapi==0.115.0`, `sqlalchemy==2.0.35`, `pydantic==2.9.2`, etc.).
- Config validator: confirmed it raises with placeholder secrets and passes
  with real ones.
- Login rate limiter: unit-tested directly (5 failures → 429; clears after
  success/explicit clear).
- Jinja2 autoescape: rendered `payslip.html` with a `<script>` payload in
  `employee_name`; confirmed the output is HTML-entity-escaped, not live
  markup.
- Password `min_length`: confirmed a 5-character password is rejected with
  `422`.
- Middleware routing: exercised via Starlette `TestClient` against the
  patched `app.main` — confirmed `/health` and unauthenticated `/employees`
  (401, not the gate's 403) behave correctly; `/auth/login` correctly passes
  through the gate to the router (fails only on the DB connection, which is
  expected in a sandbox with no Postgres available).
- No end-to-end run against a live Postgres/Docker Compose stack was
  performed in this pass (no DB available in this environment) — `qa` should
  re-run the full smoke test referenced in `BACKEND_NOTES.md` Section 1
  (auth, CRUD, ingestion/dedup, recompute, manager scoping, payroll +
  payslip PDF) against these patches before deploy, with particular
  attention to: the seeded admin login now requiring an immediate password
  change (finding 1), and the nginx `/api/v1/internal/` block (finding 2)
  not being hit by any legitimate frontend call path.

---

# Revision 2 (2026-08-23) — new surface audit

Scope: everything added since Revision 1 that had never been security-reviewed
— CSV bulk-import (`POST /employees/bulk-import`, `POST
/leave-records/bulk-import`, shared `app/services/bulk_import.py`), the
location-based access-control rewrite (`_scope_employee_query` /
`_assert_manager_can_view` across `employees.py`, `leave.py`,
`attendance.py`, `reports.py`), the new `GET /reports/alerts` and `GET
/reports/analytics` endpoints, `DELETE /payroll/runs/{run_id}`, `config.py`
CRUD reachability, the new `employees.job_title` field, and `GET /auth/me`'s
`location_name`/`employee_name` fields. Read against the same OWASP Top 10
lens as Revision 1; Revision 1's findings were re-verified (spot-checked
their fixes are still in place) but not re-audited from scratch.

## Findings & Patches Applied (Revision 2)

### 20. [HIGH] Newly-reachable vulnerable dependency: `python-multipart==0.0.9`
Revision 1 finding 19 explicitly noted `python-multipart` was **not**
installed/reachable at the time ("no endpoint declares a
`Form`/`File`/`UploadFile` parameter... noted so a future contributor doesn't
reflexively add file-upload support without revisiting this"). That warning
is now live: `POST /employees/bulk-import` and `POST
/leave-records/bulk-import` both declare `file: UploadFile = File(...)`,
which pulls `python-multipart` into the request-parsing path for every
request to those routes (both `hr_admin`-gated, but still a live attack
surface — any authenticated `hr_admin` session, including one obtained via a
future credential leak, now exercises this code).

Pinned version `0.0.9` is affected by:
- **CVE-2024-53981** — form-data preamble/epilogue parsing emits a log line
  per skipped byte; an attacker-controlled request body can drive high CPU
  and stall the request-handling thread. Fixed in 0.0.18.
- **CVE-2026-42561** — unbounded multipart part-header parsing (no cap on
  header count or size of a single header value), a DoS vector. Fixed in
  0.0.27; the pinned `0.0.9` predates the mitigations entirely.

Additionally, `fastapi==0.115.0` (pinned) requires `starlette<0.39.0`, which
is the range affected by **CVE-2024-47874** (starlette's own multipart
form-data handling could be driven into unbounded memory/temp-file
consumption before python-multipart is even reached) — Revision 1 correctly
judged this "not reachable" because nothing used `UploadFile` yet. It is
reachable now, for the same reason as above.

**Fix applied:**
- `backend/requirements.txt`: `python-multipart` bumped `0.0.9` → `0.0.20`
  (well past both CVE fixes; latest at time of writing is `0.0.32`, `0.0.20`
  chosen as a conservative, well-established patched release).
- `backend/requirements.txt`: `fastapi` bumped `0.115.0` → `0.115.6`, which
  requires `starlette>=0.40.0,<0.42.0` (closes CVE-2024-47874). No breaking
  API changes between these two `fastapi` patch releases affect anything used
  in this codebase.
- Verified: `docker compose up -d --build api frontend` rebuilds cleanly;
  confirmed inside the running `api` container that `fastapi==0.115.6`,
  `starlette==0.41.3`, `python-multipart==0.0.20` are actually installed;
  `/health` and `/openapi.json` both return `200`; login/auth/internal-block
  smoke checks (below) all pass against the rebuilt image.

**Residual risk:** none for the CVEs above. General note: this bulk-import
surface is the app's first user-uploaded-file code path — worth `qa`/`devops`
keeping an eye on `python-multipart`/`starlette` advisories going forward
given this project's otherwise-conservative pinning style.

---

### 21. [MEDIUM] No upload size cap on CSV bulk-import — memory-exhaustion DoS
`app/services/bulk_import.py`'s `run_csv_bulk_import` did `raw = (await
file.read()).decode("utf-8-sig")` — an unbounded read of the entire upload
into memory as bytes, then a second full copy as a decoded string. Nothing in
the application layer capped file size (FastAPI/Starlette impose no default
limit; `UploadFile` transparently spools to disk past 1MB but `.read()` with
no argument still returns the whole thing at once). In production, requests
reach `nginx` first, whose *default* `client_max_body_size` (1 MB) would
incidentally limit this — but (a) that's not configured explicitly in
`frontend/nginx.conf` so it's one config change away from silently
disappearing, and (b) `api`'s port `8000` is also published directly to the
host/LAN (a documented, intentional decision — see Revision 1 finding 8's
residual-risk note), bypassing nginx entirely for anyone who can reach that
port with valid `hr_admin` credentials.

**Fix applied:** `backend/app/services/bulk_import.py` now reads with an
explicit bound — `await file.read(MAX_BULK_IMPORT_BYTES + 1)` — and returns
`413 Request Entity Too Large` if the result exceeds `MAX_BULK_IMPORT_BYTES`
(10 MB, generous for a CSV of HR/leave records while ruling out
multi-hundred-MB uploads), before any CSV parsing or DB work happens.

**Verification:** in-process test against the patched module: an
`(10 MB + 1 byte)` CSV upload raises `HTTPException(413)` with zero calls to
the row-insert callback; a normal-size file passes the size gate unaffected.
(Full docs in "Verification performed (Revision 2)" below.)

**Residual risk:** none.

---

### 22. [LOW] Bulk-import per-row error messages could leak raw DB/driver text
`run_csv_bulk_import`'s exception handling caught both `IntegrityError` and
`ValueError` together and returned `str(getattr(exc, "orig", exc))` verbatim
to the client as the row's error message. For `ValueError` (raised
deliberately by each router's `insert()` closure with clean messages like
`"Location not found"`) this was fine — but for an `IntegrityError` (any DB
constraint not already pre-checked in Python), this returns the raw
psycopg2/Postgres driver message, which can include internal constraint/index
names and table names (e.g. `insert or update on table "employees" violates
foreign key constraint "employees_manager_user_id_fkey"`). Concretely
reachable: `employees.py`'s bulk-import `insert()` validated `location_id`
and `employee_code` uniqueness explicitly, but never validated
`manager_user_id` — a CSV row with a nonexistent `manager_user_id` would fall
through to the DB's foreign-key constraint and surface this raw text. Low
severity (only `hr_admin`, an already-maximally-trusted role, can reach this
endpoint at all) but inconsistent with the rest of this codebase's practice
of always returning clean, app-controlled error strings, and a real instance
of "per-row error messages could leak sensitive info" called out in this
audit's brief.

**Fix applied:**
- `backend/app/services/bulk_import.py`: split the combined `except
  (IntegrityError, ValueError)` into two handlers. `ValueError` (app-raised,
  already clean) is still returned as-is. `IntegrityError` now returns a
  fixed, generic message ("Row conflicts with an existing record or
  references a value that doesn't exist") instead of `exc.orig`.
- `backend/app/routers/employees.py`: the bulk-import `insert()` closure now
  also validates `manager_user_id` explicitly (`db.get(User,
  payload.manager_user_id) is None` → `ValueError("Manager not found")`),
  matching the existing pattern for `location_id`/`employee_code`, so this
  now surfaces a clean, specific message instead of ever reaching the generic
  `IntegrityError` fallback for the one previously-unvalidated FK.

**Residual risk:** none for information disclosure. The generic
`IntegrityError` fallback message is intentionally less specific than a
per-field check would be — acceptable since it's a backstop for constraints
not worth individually pre-validating (this endpoint's `hr_admin` caller can
still see which CSV row number failed, just not the exact DB reason).

---

### 23. [Reviewed, low risk, no fix] CSV-injection / spreadsheet formula injection on bulk-import
Checked whether imported CSV data (`employees.first_name`/`last_name`/
`national_id`/`job_title`, `leave_records.notes`, etc.) could later be
re-exported as CSV and opened in Excel/Sheets, where a cell value starting
with `=`, `+`, `-`, or `@` can be interpreted as a formula (classic CSV/
formula-injection, e.g. `=HYPERLINK(...)`, `=cmd|...`). **Confirmed there is
no CSV (or any spreadsheet-format) export anywhere in this codebase** — the
only file-download path in the entire app is the payslip PDF
(`GET /payroll/runs/{run_id}/lines/{employee_id}/payslip.pdf`, backed by
WeasyPrint HTML→PDF, not CSV), verified by grepping both `backend/app` and
`frontend/src` for `FileResponse`/`StreamingResponse`/`Content-Disposition`/
CSV-writer usage. Since the data these CSV *imports* populate is never
handed back out as CSV/Excel, there is no current path for a formula payload
to reach a spreadsheet application. **Not fixed** (would require guessing at
sanitization rules for a feature that doesn't exist yet, and mutating stored
identifier-like fields such as `employee_code`/`national_id` defensively
would be an incorrect, surprising side effect for a non-currently-exploitable
risk). **Flagged for whoever builds a CSV/Excel export feature next:**
neutralize leading `=`/`+`/`-`/`@`/tab/CR in free-text *display* fields
(not identifiers) at export time, not import time.

---

### 24. [Reviewed, no issue found] CSV bulk-import auth
Both `POST /employees/bulk-import` (`backend/app/routers/employees.py`) and
`POST /leave-records/bulk-import` (`backend/app/routers/leave.py`) carry
`dependencies=[Depends(require_hr_admin)]`. Verified with a live request
against the rebuilt stack: an unauthenticated `POST
/employees/bulk-import` returns `401`, not `200`/`422`.

### 25. [Reviewed, no issue found] Location-based access-control rewrite — consistency across call-sites
Grepped every router for `user.role == "manager"` / `_scope_employee_query` /
`_assert_manager_can_view` and manually walked every manager-reachable
endpoint:
- `employees.py`: `GET /employees` (list, via inline filter),
  `GET /employees/{id}` (via `_assert_manager_can_view`).
- `leave.py`: `GET /leave-records` (list, inline filter),
  `GET /leave-records/{id}`, `PATCH /leave-records/{id}/approve`,
  `PATCH /leave-records/{id}/reject}` (all via `_assert_manager_can_view` or
  the equivalent inline check in `_approve_reject`).
- `attendance.py`: `GET /attendance/daily-status` (inline filter;
  `GET /attendance/logs` and all mutating routes are correctly
  `hr_admin`-only, not manager-reachable at all, so no location scoping is
  needed there).
- `reports.py`: `GET /reports/dashboard-summary`, `GET /reports/analytics`,
  `GET /reports/alerts` — all route every `Employee`-joined query through the
  shared `_scope_employee_query` helper.

Every one of the above applies the identical fail-closed rule: `user.role ==
"manager"` with `user.location_id is None` → filtered to zero rows (`false()`
in list endpoints) or `403` (detail endpoints), never "falls through" to
seeing all locations. Every other router in the app
(`locations.py`, `devices.py`, `users.py`, `shift_schedules.py`,
`config.py`, `payroll.py`) is gated `hr_admin`-only at the router level
(`dependencies=[Depends(require_hr_admin)]` on the `APIRouter(...)` itself),
so managers cannot reach them at all — no location-scoping gap is possible
there because there's no manager access path to begin with. No missed
call-site found. No code change required.

### 26. [Reviewed, no issue found] `GET /reports/alerts` / `GET /reports/analytics` scoping and role-gated alert types
Both endpoints take `user: User = Depends(get_current_user)` (both roles
allowed) and route every query through `_scope_employee_query` exactly like
`dashboard-summary`. The `hr_admin`-only alert types (`unresolved_punches`,
`device_stale`, `manager_no_location`) are generated inside an `if
user.role == "hr_admin":` block in `alerts()` — a `manager` calling this
endpoint physically cannot reach that code path, so these alert types cannot
leak into a manager's response regardless of query params. Verified by
reading the full function body (`backend/app/routers/reports.py:173-268`).
No issue found.

### 27. [Reviewed, no issue found] `DELETE /payroll/runs/{run_id}`
Router-level `dependencies=[Depends(require_hr_admin)]` on
`backend/app/routers/payroll.py`'s `APIRouter(...)` — confirmed managers get
`403` before the handler runs at all (not just UI-hidden). The finalized-run
check (`if run.status == "finalized": raise HTTPException(400, ...)`) is the
first and only thing the handler does after the existence check, with no
other code path (no separate "force delete" flag, no way to delete lines
before the run itself) — cannot be bypassed. No issue found.

### 28. [Reviewed, no issue found] Config CRUD (`config.py`) reachability
`backend/app/routers/config.py`'s `APIRouter(..., dependencies=[Depends
(require_hr_admin)])` gates *all* penalty/overtime/absence-rule routes
(`GET`/`POST`/`PUT` for all three resource types) at the router level.
Confirmed managers cannot reach any of these routes, including read-only
`GET` — so the "can a manager use a location-scoped config update to affect
another location's pay calculation" question is moot: managers have zero
access to this router, full stop. No issue found.

### 29. [Reviewed, no issue found] `employees.job_title` — injection/escaping
Grepped `backend/app/services/pdf.py` and `app/templates/payslip.html`:
`job_title` is never passed to the Jinja2 template context for payslip
generation (only `employee_name`, `employee_code`, `location_name`, and
adjustment `reason`/amounts are — all already covered by Revision 1 finding
6's `autoescape` fix). On the frontend, every render site
(`EmployeeDetailPage.tsx`, `EmployeeListPage.tsx`, `EmployeeFormPage.tsx`)
renders `job_title` through plain JSX expression interpolation (`{e.job_title
?? '—'}`), which React escapes by default — consistent with Revision 1
finding 15 (no `dangerouslySetInnerHTML`/`innerHTML`/`eval` anywhere in
`frontend/src`, re-confirmed still true in this pass via the same grep). No
issue found.

### 30. [Reviewed, no issue found] `GET /auth/me` — `location_name`/`employee_name` cross-tenant leak
`backend/app/routers/auth.py`'s `me()` sets `out.location_name =
user.location.name if user.location else None` — this is the **calling
user's own** `location_id` relationship (a `User`, not an `Employee`), not a
query parameter or any other user-controllable input; there is no code path
by which a manager's `/auth/me` call could resolve a different user's
location. Same reasoning for `employee_name` (`user.employee`, the calling
user's own linked employee record, relevant only for the bootstrap admin/HR
accounts that have one). No issue found.

## Summary (Revision 2)

| # | Finding | Severity | Status |
|---|---|---|---|
| 20 | `python-multipart==0.0.9` newly reachable via bulk-import (CVE-2024-53981, CVE-2026-42561) + `starlette<0.40.0` via pinned `fastapi==0.115.0` (CVE-2024-47874) | High | **Fixed** — bumped `python-multipart` to `0.0.20`, `fastapi` to `0.115.6` (pulls `starlette>=0.40.0`) |
| 21 | No upload size cap on CSV bulk-import (memory-exhaustion DoS) | Medium | **Fixed** — 10 MB cap, `413` before parsing |
| 22 | Bulk-import per-row errors could leak raw DB/driver text | Low | **Fixed** — generic message for `IntegrityError`; added missing `manager_user_id` pre-validation |
| 23 | CSV/formula injection if bulk-imported data is ever re-exported to CSV/Excel | Low | **Accepted, no fix** — no CSV/spreadsheet export exists anywhere in the app today; flagged for whoever builds one |
| 24–30 | Bulk-import auth, location-scoping consistency across all manager-reachable endpoints, alerts/analytics scoping + role-gated alert types, payroll-run deletion, config CRUD reachability, `job_title` escaping, `/auth/me` cross-tenant leak | — | **Reviewed, no issue found** |

**Zero unresolved high/critical findings (Revision 2).**

## Files changed (Revision 2)

- `backend/requirements.txt` (`python-multipart` 0.0.9→0.0.20, `fastapi`
  0.115.0→0.115.6)
- `backend/app/services/bulk_import.py` (upload size cap, sanitized
  `IntegrityError` message)
- `backend/app/routers/employees.py` (bulk-import `insert()` now validates
  `manager_user_id`)

No other files required changes in this pass — findings 24–30 were "reviewed,
no issue found," not fixes.

## Verification performed (Revision 2)

- `docker compose up -d --build api frontend` — rebuilt both images clean,
  both containers reach `healthy`/`Started` with no errors in `docker compose
  logs api`.
- Confirmed inside the rebuilt `api` container: `fastapi==0.115.6`,
  `starlette==0.41.3` (>=0.40.0, closes CVE-2024-47874),
  `python-multipart==0.0.20` (closes CVE-2024-53981/CVE-2026-42561) are the
  versions actually installed and running — not just pinned in
  `requirements.txt`.
- `GET /health` → `200`; `GET /openapi.json` → `200` (confirms all routers,
  including the modified ones, import and wire up without error).
- `GET /api/v1/internal/attendance-logs` via the public frontend port
  (`:8080`, through nginx) → `404`, confirming Revision 1 finding 2's nginx
  block still holds after the rebuild.
- `POST /employees/bulk-import` with no auth cookie → `401` (confirms
  `require_hr_admin` gate is active).
- In-process test of the patched `run_csv_bulk_import` (run inside the live
  `api` container, using the real `fastapi`/`starlette` `UploadFile`): a
  `(10 MB + 1 byte)` CSV upload raises `HTTPException(413)` with zero calls
  to the row-insert callback; a normal-size file passes the size gate.
- Did not attempt a full end-to-end bulk-import-to-database run: the
  database was recently reset to bootstrap state at the user's request (only
  the `admin` account + `Main Location` exist) and the bootstrap admin
  password has already been changed by the user (confirmed via
  `must_change_password = false` in the `users` table), so this agent does not have valid
  application credentials to drive an authenticated end-to-end flow.
  **`qa` should exercise, against a real logged-in `hr_admin` session:** a
  successful multi-row CSV import for both employees and leave records, a
  CSV row with a bad `manager_user_id` (should now return the clean "Manager
  not found" message, not raw DB text), and — if convenient — an oversized
  (>10 MB) upload to confirm the `413` end-to-end through the real HTTP
  client used by the frontend (`BulkImportModal.tsx`).

---
---

# Revision 3 (2026-09-16) — multi-vendor device integration audit

Scope: the multi-vendor device work added 2026-09-16 (`BLUEPRINT.md` Section
5.5) and the access-control changes made since Revision 2.

New/changed surface audited:

- `devices.device_type` dispatch and the two new vendor adapters —
  `worker/worker/adapters/hikvision.py` (ISAPI over HTTP + digest auth) and
  `worker/worker/adapters/hikvision_cloud.py` (Hik-Connect Open Platform).
- `devices.auth_username` / `devices.auth_password` — plaintext credentials
  now resident in Postgres (migration `0009_multi_vendor_devices`).
- `devices.ip_address` widened from `INET` to `TEXT` (same migration) and the
  outbound requests `api` and `worker` now build from it.
- `attendance_logs.punch_type_hint` and its effect on
  `backend/app/services/classify.py`.
- The `DeviceOut` / `InternalDeviceOut` schema split and every consumer of
  `GET /internal/devices`.
- Managers' new full write access scoped by `require_manager_or_admin` +
  `assert_location_access`, after `users.can_manage_payroll` was dropped in
  migration `0008`.

Method: real HTTP against the live `docker compose` stack (no mocks, per this
project's convention). Throwaway accounts/locations/devices prefixed `__sec`,
plus two attacker-controlled containers on the `checkin_default` Docker
network standing in for a hostile device/cloud. All test data removed
afterwards — verified (see "Verification performed (Revision 3)").

Result: **10 findings — 2 critical, 3 high, 3 medium, 2 low — all patched.**
Plus 4 items reviewed and accepted as-is with reasoning, and 6 reviewed with
no issue found.

---

## Findings & Patches Applied (Revision 3)

### 31. [CRITICAL] Device credentials exfiltrate to an attacker-chosen host by retargeting the device row

`DeviceOut` deliberately never returns `auth_password`, so no API caller can
read a device's stored secret. But `POST /devices/{id}/test-connection` — and
the `worker` poll path — *send* that secret to whatever host
`devices.ip_address` names, and `PUT /devices/{id}` let any admin **or
manager** change `ip_address`/`port`/`device_type` while leaving the stored
`auth_password` untouched.

For `device_type='hikvision_cloud'` the credential is POSTed **preemptively,
in the clear**, as form fields:

```
POST /api/lapp/token/get
appKey=<auth_username>&appSecret=<auth_password>
```

Confirmed live. As `__sec_mgr_a` (a plain manager, who gets `403` even trying
to *read* another location's device):

1. `PUT /devices/24  {"ip_address":"sec-catcher","port":80}` → `200`
   (no password supplied, stored one retained)
2. `POST /devices/24/test-connection` → `{"reachable":true,...}`
3. Attacker listener received:
   `BODY: b'appKey=APPKEY-SECRET-1234&appSecret=APPSECRET-SUPER-SECRET-9999'`

Note step 1 also set `port: 80`, which the old code used to select the scheme
(`"http" if port == 80 else "https"`) — so the attacker also chose *cleartext*
for the exchange.

The `hikvision` direct path leaks less but still leaks: `httpx.DigestAuth`
answers the attacker's own `WWW-Authenticate` challenge, handing over the
username in cleartext plus an MD5 digest computed over an attacker-chosen
`realm`/`nonce` — an offline-crackable oracle for the device admin password.
Also confirmed live.

This completely defeats the `DeviceOut`/`InternalDeviceOut` split: the split
stops the secret being *read*, but not *used on the attacker's behalf*. Any
manager, or anyone who lands an authenticated session (session theft, an
insider, a stolen browser session), can harvest every device credential in
their scope.

**Patched** (`backend/app/routers/devices.py`, `backend/app/schemas.py`,
`backend/app/services/device_net.py`,
`worker/worker/adapters/hikvision_cloud.py`):

1. **Re-supply-on-retarget.** `PUT /devices/{id}` now rejects a change to
   `ip_address`, `port` or `device_type` unless `auth_password` is supplied in
   the same request, whenever the row has a stored password. The attacker can
   still repoint a device — but only by *overwriting* the secret, so there is
   nothing left to harvest. A legitimate operator moving a device knows its
   password, so the flow is unchanged for them; the error is explicit.
2. **Cloud host allowlist.** A `hikvision_cloud` device's `ip_address` must be
   a Hikvision Open Platform host (`hik-connect.com`, `ezvizlife.com`,
   `ys7.com`, `hikvision.com`, or a subdomain). Enforced on create, on update,
   and again in the worker adapter. The appKey/appSecret can no longer be sent
   anywhere but Hikvision.
3. **Forced TLS.** The port-keyed scheme selection is gone from both
   `api` and `worker`; the cloud transport is always `https://`.

Verified after patch: step 1 → `400 "Changing a device's address, port or
type also requires re-entering its password..."`; flipping to
`hikvision_cloud` pointed at `sec-catcher` → `400 "...must be a Hikvision Open
Platform host"`; retargeting *with* a fresh password → `200`, and the listener
then receives a digest computed over the attacker's **own** newly-supplied
password, not the previously stored secret.

---

### 32. [CRITICAL] `devices.ip_address` gave full control of the outbound URL (SSRF)

Migration 0009 replaced Postgres `INET` with `TEXT` and nothing replaced the
validation `INET` had been providing. Both `api` and `worker` build URLs by
string concatenation:

```python
f"http://{device['ip_address']}:{device['port']}/ISAPI/AccessControl/AcsEvent"
```

A `#` in `ip_address` terminates the path, so the rest of the template becomes
a URL fragment and the caller controls the **entire** path and query — the
request is no longer constrained to the vendor's API path at all. Confirmed:

```
ip_address = "sec-catcher/PATH-FULLY-CONTROLLED?q=1#"
-> GET /PATH-FULLY-CONTROLLED?q=1   (received by the attacker's listener)
```

`test-connection` also returned `str(exc)` verbatim, echoing the full
constructed URL and the exact transport error, which turned the endpoint into
a precise internal-network probe from inside the Docker network:

```
api:8000/health#                  -> reachable:true
api:8000/api/v1/internal/devices# -> "Client error '401 Unauthorized' for url 'http://api:8000/api/v1/internal/devices#:80/ISAPI/...'"
db:5432#                          -> "Server disconnected without sending a response."
169.254.169.254/latest/meta-data/# -> "timed out"
worker:8100/health#               -> reachable:true
```

Note `worker:8100` — deliberately unpublished to the host (Revision 1 finding
8) — was reachable this way, and `169.254.169.254` (the cloud-metadata
endpoint) was an in-reach target for any Phase 2 cloud deployment.

**Patched:**

- `backend/app/services/device_net.py` (new) and
  `worker/worker/adapters/_target.py` (new): `ip_address` must be a bare IPv4
  / IPv6 / DNS-name — no scheme, port, path, query, fragment, userinfo or
  whitespace. Resolved addresses that are loopback, link-local (covers
  `169.254.169.254`), multicast, reserved or unspecified are refused.
- `backend/app/schemas.py`: `DeviceCreate`/`DeviceUpdate` use
  `DeviceHost = Annotated[str, AfterValidator(validate_device_host)]` and
  `DevicePort` (1–65535), so bad values cannot enter the DB at all.
- `backend/app/routers/devices.py`: `_assert_target_allowed()` re-checks the
  stored value immediately before connecting — rows written before this
  validation existed are not covered by the schema, so this is the enforcement
  point for them. `_connection_error_detail()` replaces `str(exc)` with a
  failure *class* (`"Device rejected the request: HTTP 401"`, `"Could not
  connect to the device"`, `"Timed out connecting to the device"`).
- The guard is applied in all three worker adapters, including `zkteco.py` —
  a raw pyzk TCP connect to loopback/link-local is no more legitimate than an
  HTTP one, and it costs two lines.

Verified after patch: `host/path#`, `user:pw@host`, `a b` → `422` at the
schema; `127.0.0.1`, `localhost`, `169.254.169.254` → `{"reachable":false,
"detail":"address ... is not a permitted device address"}`; error details no
longer contain a URL.

**Residual (accepted, documented):** private RFC1918 ranges remain reachable,
because that is exactly where a real LAN attendance device lives, and the
Docker service network (`172.x`) is indistinguishable from it. A manager can
therefore still use `test-connection` as a coarse open/closed port oracle
against the Docker network — but with a fixed vendor path, a generic error
string, and no credential delivery. Narrowing further needs a
deployment-specific device subnet allowlist, which requires client input
(see item R3 below). There is also an inherent TOCTOU gap between our
`getaddrinfo()` check and `httpx`'s own resolution (classic DNS rebinding);
closing it needs a custom `httpx` transport that pins the resolved IP, which
is disproportionate for a manager-gated setup endpoint.

---

### 33. [HIGH] Unauthenticated device-credential disclosure and attendance forgery via `device-simulator`

`device-simulator` is labelled temporary dev tooling, but it was running,
published on `0.0.0.0:8090`, holds `INTERNAL_API_KEY`, and has **no
authentication of its own**. Two consequences:

1. `GET /api/status` returned the `/internal/devices` record verbatim —
   which is `InternalDeviceOut`, i.e. **including `auth_password`**. Confirmed
   live with no credentials of any kind:

   ```
   $ curl -s http://localhost:8090/api/status
   {"device_id":10,"device":{...,"auth_username":"__sec_probe_user",
    "auth_password":"__SEC_PROBE_PASSWORD__"},...}
   ```

   This is the concrete answer to "does the `DeviceOut`/`InternalDeviceOut`
   split hold everywhere?" — it held in `api` (verified: `GET /devices` and
   `GET /devices/{id}` never emit `auth_password`), and the nginx block plus
   `X-Internal-Key` held, but a *second consumer* of the internal endpoint
   republished the credential on an open port.

2. `POST /api/punch` writes straight into `attendance_logs` — and therefore
   into payroll — with no credential at all, for anyone on the LAN.

**Patched:**

- `device-simulator/app/api_client.py`: `get_device()` now projects only the
  fields the simulator UI renders (`id`, `location_id`, `location_name`,
  `label`, `device_type`). Credentials never leave the function.
- `docker-compose.yml`: the published port is now `127.0.0.1:8090:8090`
  instead of `8090:8090`. The simulator UI still works from the host browser
  at `http://127.0.0.1:8090`; it is no longer an unauthenticated
  payroll-write API for the whole LAN.

Verified after patch: `/api/status` returns no `auth_password` field even
with a credential set on the device; port mapping shows
`127.0.0.1:8090->8090/tcp`.

**Still recommended:** delete the `device-simulator` service and folder before
any non-development deployment, as its own docstring already says. Loopback
binding reduces the blast radius but does not change the fact that an
unauthenticated punch-injection API exists in the compose file.

---

### 34. [HIGH] Manager can rewrite another location's — or every location's — pay rules

Revision 2 finding 28 examined exactly this question and concluded it was
moot, because `config.py` was gated to `hr_admin` and managers had no access
at all. The 2026-08-24/25 access-control change (managers get full write
access to their own location; `users.can_manage_payroll` dropped in migration
0008) opened the router to managers — and the guard that made the conclusion
safe was never added. **This is a regression against a previously-closed
finding.**

`update_penalty`, `update_overtime` and `update_absence_rule` checked
`assert_location_access(user, row.location_id)` — the row's *current* location
— but never the `location_id` **in the payload**, which all three Update
schemas accept. `devices.py`, `employees.py` and `shift_schedules.py` all get
this right; `config.py` was the odd one out.

Confirmed live as `__sec_mgr_a` (manager of location 26 only):

```
POST /config/penalty {"location_id":27,...}            -> 403   (direct create blocked)
PUT  /config/penalty/18 {"location_id":27,"rate_per_minute_eur":99.99}
                                                       -> 200   location_id now 27
PUT  /config/overtime/15 {"location_id":null,"rate_per_hour_eur":500}
                                                       -> 200   location_id now null
```

The second call plants a €99.99-per-minute lateness penalty on another
location's payroll. The third promotes the config to **org-wide** (`location_id
is null` is the global scope used by `services/config_lookup.py`) at €500/hour
overtime — every employee in the company, from a single manager account.

**Patched** (`backend/app/routers/config.py`): all three update endpoints now
read `data = payload.model_dump(exclude_unset=True)` and call
`assert_location_access(user, data["location_id"])` when the key is present,
matching the pattern already used elsewhere.

Verified after patch: both escalations → `403 "Not your location"`; a manager
creating and editing a config **in their own location** still returns `200`
(no functional regression to the new manager-write model); an admin performing
the same cross-location move still returns `200`.

The two polluted config rows created during this test were deleted.

---

### 35. [HIGH] Hostile/misbehaving device wedges the `worker` permanently (unbounded paging)

Both HTTP adapters ended their paging loop only when the *device* said to:

```python
# hikvision.py
while True:
    ...
    if num_matches < PAGE_SIZE or data.get("responseStatusStrg") == "NO MATCH":
        break

# hikvision_cloud.py
while True:
    ...
    if len(items) < PAGE_SIZE:
        break
    page += 1
```

A device (or cloud) that always answers with a full page loops forever,
appending to `punches` the whole time. Because the scheduled sync job runs
with `max_instances=1`, that one stuck device also stops **every other
device** from ever syncing again, and stops the nightly processing job's
sibling from being scheduled behind it.

Confirmed live against a hostile ISAPI server on the Docker network that
always returns `numOfMatches: 30` with 30 items:

```
worker RSS before:      38.94 MiB
worker RSS after ~40s:  292   MiB
worker RSS after ~65s:  505.7 MiB   (~49,000 pages fetched, still climbing)
```

The loop only ended when the hostile server was killed. This does not require
a compromised vendor — buggy firmware that mis-reports `numOfMatches` produces
the same outcome, which makes it a reliability defect as much as a security
one.

**Patched** (`worker/worker/adapters/hikvision.py`,
`worker/worker/adapters/hikvision_cloud.py`):

- `MAX_PAGES = 400` on both loops (`for page in range(MAX_PAGES)` with a
  `for...else` that raises if the device never signalled the end), plus a
  `MAX_PUNCHES` guard on the accumulated list.
- `MAX_RESPONSE_BYTES = 8 MiB` per response — 48h of one terminal's events is
  kilobytes; anything near this is an attempt to exhaust worker memory in a
  single reply.
- Non-positive / non-integer `numOfMatches` now ends the loop instead of
  leaving `position` stuck.

Verified after patch, same hostile server:

```
{"device_id":24,"error":"Device never signalled end of results after 400 pages — aborting"}
real 0m0.597s      worker RSS 36.96 MiB -> 45.85 MiB
```

The device is marked failed in the sync result, the worker stays healthy, and
every other device keeps syncing.

---

### 36. [MEDIUM] `punch_type_hint` could be asserted for devices that cannot produce one

`punch_type_hint` short-circuits `services/classify.py` entirely:

```python
if log.punch_type_hint is not None:
    log.punch_type = log.punch_type_hint
    continue
```

It is well-validated *as a value* — `IngestPunch` pins it to a Pydantic
`Literal` of four strings and `ck_punch_type_hint` enforces the same set in
Postgres. Both confirmed live (`"unclassified"` → `422`; the DB constraint
exists). So there is no injection or arbitrary-string risk here.

What was missing was the link between the hint and the **device**. Any caller
reaching `/internal/ingest/punches` could set `punch_type_hint` on a punch
attributed to a **ZKTeco** device — hardware that only ever reports a bare
numeric status code and whose adapter never sets a hint. That let such a
caller dictate check-in/check-out for punches the ZKTeco path would otherwise
have had to derive from alternating parity and break-window overlap, i.e.
choose the precise `actual_first_in`/`actual_last_out` pair that drives
late-minutes, overtime and absence deductions.

The bar for this is the `X-Internal-Key`, which is why it is Medium and not
High — but it composed directly with finding 33 (the simulator republishes
that trust on an open port).

**Patched** (`backend/app/routers/internal.py`): `_SELF_CLASSIFYING_DEVICE_TYPES
= {"hikvision", "hikvision_cloud"}`; a punch carrying a hint for any other
device type is rejected with `400`. The device-type lookup is memoised per
batch so a large ingest is still one query per distinct device.

Verified after patch: hint on ZKTeco device 10 → `400 "Device 10 does not
self-classify punches; punch_type_hint is not accepted for it"`; a normal
hintless ZKTeco punch → `200 inserted:1`; a hint on a `hikvision` device →
`200 inserted:1`.

---

### 37. [MEDIUM] Manager can enrol an employee onto another location's device

`POST /employees/{id}/device-enrollments` checked the **employee's** location
(`_assert_manager_can_view`) but never the **device's**. Confirmed live:
`__sec_mgr_a` gets `403` on `GET /devices/10` (location 1, not theirs) yet
succeeds at binding their own employee to device 10 — and the `201` body
echoes back that device's `label`, a small cross-tenant information leak on
top.

The practical impact is on attendance integrity: `(device_id, device_user_id)`
is the key `/internal/ingest/punches` resolves punches through, so a manager
could capture another location's reader traffic for an unenrolled
`device_user_id` into their own employee's record — which feeds payroll. The
`uq_device_enrollment` constraint prevents hijacking an *already* enrolled ID.

The same handler also 500'd on a non-existent `device_id` (raw FK violation,
never pre-validated) — a missing-input-validation gap at a system boundary.

**Patched** (`backend/app/routers/employees.py`): the device is now fetched
(`400 "Device not found"` if absent) and passed through
`assert_location_access` before the enrolment is created.

---

### 38. [MEDIUM] Known-vulnerable dependencies in the session-token and multipart paths

`pip-audit` against the running pins:

| Package | Was | Now | Notes |
|---|---|---|---|
| `PyJWT` | 2.9.0 | **2.13.0** | PYSEC-2026-120 (`crit` header never validated, RFC 7515 §4.1.11 MUST), PYSEC-2026-178 (oversized base64 payload segment decoded *before* the signature is checked — a pre-auth CPU/memory amplifier, bounded here only by the HTTP header-size limit on the session cookie). The PyJWKClient advisories (PYSEC-2026-175/176/177/179) are **not** reachable: this app uses a static HS256 secret and never fetches a JWKS. |
| `python-multipart` | 0.0.20 | **0.0.31** | PYSEC-2026-3038/3039 (preamble + part-header parsing DoS), PYSEC-2026-3040 (a negative `Content-Length` turned the bounded chunked read into read-until-EOF, loading the whole body in one go), PYSEC-2026-3036/3037 (`;`-separator parser differential). Reachable via the CSV bulk-import endpoints, the only multipart surface here. |
| `fastapi` (worker) | 0.115.0 | **0.115.6** | Aligns `worker` with `backend`'s pin, which requires `starlette>=0.40.0` (CVE-2024-47874). Not reachable in `worker` (no form/multipart endpoint), fixed so the two services stop drifting on a shared transitive dependency. |

Rebuilt and confirmed installed in the running containers. Full stack
re-verified healthy afterwards.

---

### 39. [LOW] Manager with no assigned location saw every org-wide payroll run

`payroll.py`'s `list_runs` used `q.filter(PayrollRun.location_id == user.location_id)`.
When `user.location_id` is `None` — explicitly allowed by the model comment
("a manager row may also be temporarily null") — SQLAlchemy compiles that to
`location_id IS NULL`, which is the **org-wide** scope, so the manager saw
every company-wide payroll run instead of nothing. Every other scoped list in
the codebase (`employees.py`, `attendance.py`, `leave.py`, `devices.py`) uses
an explicit fail-closed `q.filter(false())` for this case.

**Patched** (`backend/app/routers/payroll.py`): matched the fail-closed
pattern.

---

### 40. [LOW] Untrusted third-party text reflected into API responses and logs

`hikvision_cloud._unwrap()` embedded the Hik-Connect platform's `msg` field
verbatim into a `RuntimeError`; `sync.py` put `str(exc)` into the sync result,
which `POST /devices/{id}/sync` returns to the caller and which is written to
the worker log. `test-connection` did the same for the cloud path
(`f"Hik-Connect rejected the credentials: {payload.get('msg')}"`). Newlines in
that text allow forged log lines, and there was no length bound.

React escapes it in the UI, so this is not XSS — it is log injection plus
unbounded reflection of third-party content.

**Patched:** `_unwrap()` truncates `msg` to 200 chars and strips
non-printable characters; `_to_punch` truncates the unrecognised
`attendanceStatus` value; `sync.py` gained `_safe_error()` (300 chars,
printable only) applied to both the log line and the returned `error` field,
and the operator-supplied `device["label"]` is sanitised the same way before
it reaches the log; `test-connection`'s cloud branch no longer echoes `msg` at
all.

---

## Reviewed — accepted as-is, with reasoning (Revision 3)

### R1. Plaintext device credentials at rest — **defensible to defer, with conditions**

The brief asked for an honest cost/benefit read rather than a reflexive
demand for crypto. Assessment:

**What encryption at rest would actually buy here.** The app has no existing
secret-encryption infrastructure, so the key would have to live in the same
`.env` that already holds `POSTGRES_PASSWORD`, `JWT_SECRET` and
`INTERNAL_API_KEY`. Anyone who can read that file can read the database
anyway. So app-level encryption protects against exactly one thing the
current design doesn't: **a database dump that travels without the `.env`** —
a backup file, a snapshot handed to a vendor, a restore into a staging box, a
read-only replica. That is a real scenario, but a narrow one.

**What it would not buy.** It would not have prevented a single finding in
this revision. Findings 31 and 33 both delivered the plaintext credential to
an attacker *through the application*, which would have decrypted it on the
way out either way. Encryption at rest is orthogonal to how these credentials
actually leaked.

**Cost.** A `cryptography` dependency, a new required env var, a data
migration, a key-rotation procedure, and a new class of "device stopped
working after a restore because the key didn't come along" incident.

**Conclusion.** Deferring is defensible for Phase 1 **provided the leak paths
are closed**, which findings 31, 32 and 33 now do. The inline note in
`backend/app/models.py` accurately describes the tradeoff and should stay.
Two conditions attach to that acceptance:

1. **Before Phase 2 / internet exposure**, encrypt these columns. At that
   point the device credential becomes a remote-administration credential for
   hardware on a customer site, and the DB-dump scenario stops being
   hypothetical.
2. **Now**: treat DB backups of this system as containing live device
   credentials, and handle them accordingly (encrypted at rest, not shared
   with third parties). This is a `devops` action, not a code change.

Worth noting for scale: the credential's blast radius is per-device for
`hikvision` (one terminal's admin login) but per-*account* for
`hikvision_cloud` — an Open Platform appKey/appSecret typically covers the
customer's whole Hik-Connect account, not one camera. The cloud credential is
materially more valuable than the direct one and is the stronger argument for
condition 1.

### R2. `punch_type_hint` as a payroll-integrity concept

Even with finding 36 patched, a *genuinely compromised* Hikvision terminal
can assert arbitrary punch classifications, and there is no way to
distinguish that from real attendance. This is inherent: the entire feature is
"trust the vendor's own classification instead of inferring it," which is
what makes it more accurate than the ZKTeco parity heuristic. Accepting the
device as an authority on its own events is the design, and a compromised
device could equally well just emit fabricated *timestamps* — which the old
ZKTeco path trusted just as completely. The hint changes the precision of the
manipulation, not the fact of it. The correct control is device custody plus
the existing HR review path (Attendance → Raw Logs), not a schema change.

### R3. `test-connection` as a private-network port oracle

Carried over from Revision 1 finding 13 and narrowed, not eliminated (see
finding 32's residual). Still gated to admin/manager, still returns only a
boolean plus a generic error class, no longer delivers credentials, no longer
permits path control, and no longer reaches loopback or link-local. Fully
closing it needs a deployment-specific "these are the subnets our devices live
on" allowlist, which `BLUEPRINT.md`/`DISCOVERY.md` do not specify and which
would break the multi-location Phase 2 case if guessed. Flagged for
`devops`/product.

### R4. `EVENT_PATH` and the Hik-Connect event field names are unverified

`worker/worker/adapters/hikvision_cloud.py` documents this itself. It is not a
security finding, but it is a security-relevant unknown: the untrusted-input
handling in that adapter (findings 35, 40) was hardened against the shapes the
code expects, and a different real-world response shape will exercise the
raise-loudly path rather than a silently-wrong one — which is the correct
failure mode for payroll input. Confirm the two constants against the client's
real account before relying on this transport.

---

## Reviewed — no issue found (Revision 3)

### 41. `DeviceOut` / `InternalDeviceOut` split inside `api`
Verified live that `GET /devices` and `GET /devices/{id}` never emit
`auth_password` (only `auth_username`, which is not secret), for both admin
and manager sessions, on both `hikvision` and `hikvision_cloud` devices. The
only leak of `InternalDeviceOut` was outside `api` — finding 33.

### 42. `/api/v1/internal/` isolation
The nginx block holds against every bypass tried:
`/api/v1/INTERNAL/devices`, `/api/v1//internal/devices`,
`/api/v1/%69nternal/devices`, `/api/v1/internal%2fdevices`,
`//api/v1/internal/devices`, `/api/v1/internal/devices;x=1`,
`/api/v1/internal/../internal/devices`, `/api/./v1/internal/devices`,
`/api/v1/foo/../internal/devices` — all `404`. Without the key the endpoint
is `401`; `hmac.compare_digest` is still in place in both `api` and `worker`.
As defence-in-depth the `api` container's published port was additionally
narrowed to loopback (see below), so the LAN cannot bypass nginx to reach it.

### 43. Frontend bundle secret scan
Grepped the *served* build in the running `frontend` container for
`INTERNAL_API_KEY`, `X-Internal-Key`, `JWT_SECRET`, `auth_password` and the
literal `.env` secret values. The only hits are the string `auth_password` as
a **request payload key** in `DeviceFormPage`/`DeviceDetailPage` (the form
posts a new password; it never reads one back — `Device` in
`frontend/src/api/types.ts` has `auth_username` but no `auth_password`). No
secret values in the bundle.

### 44. CORS with credentialed cookies
`Origin: http://evil.test` gets `access-control-allow-credentials: true` but
**no** `Access-Control-Allow-Origin`, so the browser blocks the response.
Preflight for the same origin likewise omits ACAO. Revision 1 finding 5's
wildcard guard is intact.

### 45. Injection via the new fields
`device_type`, `punch_type_hint` and `ip_address` all reach the DB through
SQLAlchemy ORM binds; `device_type` and `punch_type_hint` are additionally
pinned by Pydantic `Literal` *and* a Postgres `CHECK` (`ck_device_type`,
`ck_punch_type_hint`). A `'; drop table users; --` value for
`punch_type_hint` is rejected at the schema with `422`. No SQL injection.

### 46. Manager location scoping across the rest of the surface
Re-walked every `require_manager_or_admin` router after the
`can_manage_payroll` removal. `devices`, `employees`, `shift_schedules`,
`payroll` and `leave` all check both the row's location **and** an incoming
`location_id` on update. Cross-location reads are `403`, cross-location
creates are `403`, and a manager with a null location fails closed. The two
gaps found (`config.py`, `employees.py` enrolments) are findings 34 and 37;
everything else is sound. Revision 1 findings 1, 3, 5, 8, 11 and Revision 2
findings 20–22 were all re-verified as still in place.

---

## Hardening applied beyond the findings (Revision 3)

**`api` published port narrowed to loopback.** `docker-compose.yml` published
`8000:8000` on all interfaces. LAN clients reach the API through the
`frontend` nginx proxy on `:8080`, which is where the `/api/v1/internal/`
block lives (Revision 1 finding 2) — so the wide binding let anyone on the LAN
bypass that block entirely and make the shared secret the only defence, which
is precisely what finding 2's patch set out to avoid. Now
`127.0.0.1:8000:8000`. Local tooling and the Vite dev-server CORS origins are
unaffected; the frontend proxy path is unchanged.

> If you rely on hitting `:8000` directly from another machine on the LAN,
> revert this one line — it is the only change in this revision that could
> alter an existing workflow.

---

## Files changed (Revision 3)

| File | Change |
|---|---|
| `backend/app/services/device_net.py` | **new** — host validation + outbound-target guard for `api` |
| `backend/app/schemas.py` | `DeviceHost`/`DevicePort` on `DeviceCreate`/`DeviceUpdate` |
| `backend/app/routers/devices.py` | re-supply-on-retarget guard, cloud-host allowlist, forced HTTPS, `_assert_target_allowed`, sanitised error details |
| `backend/app/routers/config.py` | incoming-`location_id` check on all three update endpoints |
| `backend/app/routers/employees.py` | device existence + location check on enrolment creation |
| `backend/app/routers/internal.py` | `punch_type_hint` restricted to self-classifying device types |
| `backend/app/routers/payroll.py` | fail-closed manager scoping in `list_runs` |
| `backend/requirements.txt` | `PyJWT` 2.9.0 → 2.13.0, `python-multipart` 0.0.20 → 0.0.31 |
| `worker/worker/adapters/_target.py` | **new** — worker-side host/port guard |
| `worker/worker/adapters/hikvision.py` | target guard, page/size/punch caps, response shape checks |
| `worker/worker/adapters/hikvision_cloud.py` | forced HTTPS + cloud-host allowlist, page/size/punch caps, token-cache + TTL bounds, hostile-payload shape checks, truncated `msg` |
| `worker/worker/adapters/zkteco.py` | same target guard applied to the pyzk connect |
| `worker/worker/sync.py` | `_safe_error()` on the reflected/logged error and device label |
| `worker/requirements.txt` | `fastapi` 0.115.0 → 0.115.6 |
| `device-simulator/app/api_client.py` | device record projected to non-secret fields only |
| `docker-compose.yml` | `api` and `device-simulator` ports bound to `127.0.0.1` |

---

## Verification performed (Revision 3)

All against the live `docker compose` stack, real HTTP, no mocks.

**Environment.** Throwaway `__sec_admin` (admin), `__sec_mgr_a` (manager,
location `__sec_loc_a`), `__sec_mgr_b` (manager, location `__sec_loc_b`),
created directly in the DB the same way `backend/tests/conftest.py` does.
Two attacker containers on `checkin_default`: `sec-catcher` (logs every
request, issues a Digest challenge, answers the cloud token exchange) and
`sec-evil` (an ISAPI server that always returns a full page).

**Exploit → patch → re-test.** Every finding above was reproduced before the
patch and re-tested after. Results are quoted inline in each finding.

**Non-regression.**
- Manager creating a config in their own location, then editing it: `200`.
  Cross-location edit: `403`. Admin cross-location edit: `200`.
- Retargeting a device *with* the password re-supplied: `200`, and the
  outbound request then carries the new password.
- Hintless ZKTeco punch ingestion: `200 inserted:1`. Hinted `hikvision`
  punch: `200 inserted:1`.
- `POST /devices/10/sync` (the real ZKTeco device) still dispatches through
  the unchanged pyzk path and reports the ordinary `timed out` for hardware
  that isn't present in this environment — the private-IP target guard passes
  it through as intended.
- Worker target-guard unit matrix, run inside the live container:
  `192.168.1.50` allow / `open.hik-connect.com` allow / `open.ys7.com` allow /
  `evil.hik-connect.com.attacker.net` blocked for cloud (suffix match is
  correctly anchored) / `127.0.0.1`, `169.254.169.254`, `host/path#`,
  `user:pw@host`, `a b` blocked / ports `0`, `-1`, `65536` blocked.
- Full stack healthy after rebuild: `api` healthy, `worker` scheduler started,
  `device-simulator` up, login through the nginx proxy returns `401` for bad
  credentials and the internal path still `404`s.

**QA suite.** `backend/tests/` was run before and after: **18 passed, 5 failed
→ 19 passed, 3 failed** (one deselected). All failures are **pre-existing test
rot, not regressions**, and were each traced to a cause in code this revision
did not touch:

- `test_manager_payroll_access_requires_opt_in_flag` asserts on
  `users.can_manage_payroll`, dropped by migration `0008`.
- Three tests fail in the shared fixture's teardown on
  `DELETE FROM leave_types WHERE name ...` — `leave_types.name` was split into
  `name_en`/`name_sq` by migration `0007`. Patching only that column name in a
  scratch copy made `test_leave_approval_scoped_and_feeds_recompute` pass,
  confirming the cause. The scratch edits were reverted; `tests/` is
  byte-identical to how this pass found it (`diff` clean).
- `test_reports_alerts_flags_missing_checkout` and
  `test_manager_alerts_excludes_admin_only_types` depend on a hard-coded
  fixture week of `2026-08-10`, which is now 37 days old and has aged out of
  the tests' own `days=30` alert window. Confirmed by querying the same
  endpoint: `days=30` → `0` matching alerts, `days=45` → matches present.

These belong to `qa` to fix; they are recorded here only to show they are not
caused by this revision's patches.

**Note for `qa` (not a security finding).** `frontend/nginx.conf` uses
`proxy_pass http://api:8000/...`, which nginx resolves once at startup and
caches. Recreating the `api` container gives it a new IP and the frontend
then `502`s until `docker compose restart frontend`. This was observed during
this pass and cleared by restarting the frontend. Worth a `resolver` directive
or a variable `proxy_pass` if `api` is ever restarted independently in
production.

**Cleanup.** Every `__sec*` account, location, device, employee, enrolment,
config row and attendance log created by this audit was deleted, along with
the residue from the four QA suite runs (whose own teardown aborts on the
stale `leave_types.name` column, so it commits nothing). Both attacker
containers were removed. Final DB state verified back to its pre-audit
contents: 3 real users (`admin`, `manager1`, `ensar.dauti`), 1 real device
(`Main Entrance`), 1 real location (`Main Location`), and no rows matching
`__sec%` or `qa\_%` in any table.

---

## Summary (Revision 3)

| # | Severity | Finding | Status |
|---|---|---|---|
| 31 | CRITICAL | Device credentials exfiltrate via device retargeting | **Fixed** |
| 32 | CRITICAL | `ip_address` gave full outbound-URL control (SSRF) | **Fixed** (residual documented) |
| 33 | HIGH | Unauthenticated credential disclosure + punch forgery via `device-simulator` | **Fixed** |
| 34 | HIGH | Manager can rewrite another location's / all locations' pay rules (regression vs. Rev 2 #28) | **Fixed** |
| 35 | HIGH | Hostile/buggy device wedges `worker` via unbounded paging | **Fixed** |
| 36 | MEDIUM | `punch_type_hint` accepted for devices that cannot produce one | **Fixed** |
| 37 | MEDIUM | Manager can enrol an employee onto another location's device | **Fixed** |
| 38 | MEDIUM | Vulnerable `PyJWT` / `python-multipart` / worker `fastapi` pins | **Fixed** |
| 39 | LOW | Null-location manager saw all org-wide payroll runs | **Fixed** |
| 40 | LOW | Untrusted third-party text reflected into responses and logs | **Fixed** |
| R1 | — | Plaintext device credentials at rest | Accepted for Phase 1, with two conditions |
| R2 | — | Compromised device can assert punch classifications | Accepted (inherent to the design) |
| R3 | — | `test-connection` private-range port oracle | Accepted, narrowed; needs client input to close |
| R4 | — | Hik-Connect event path/fields unverified | Accepted; fails loudly by design |

**Zero unresolved high/critical findings.**
