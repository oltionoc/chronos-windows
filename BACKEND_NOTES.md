# BACKEND_NOTES.md — chronos Backend

Status: implemented and verified end-to-end against a real PostgreSQL instance
(migrations + full API surface exercised via an automated smoke test covering
auth, every resource's CRUD, device-punch ingestion + dedup + classification,
nightly recompute, leave approval feeding back into daily status, manager
row-level scoping, payroll run creation + adjustments + finalize + PDF
payslip download, and the 422 error-flattening handler). Frontend (`npm run
build`) builds cleanly unmodified against this backend's contract — no
frontend changes were needed.

Input: `BLUEPRINT.md`, `FRONTEND_NOTES.md`, `frontend/src/api/{types,endpoints,client}.ts`.

---

## 1. What was built

```
backend/            FastAPI app — public + internal API, all business logic
  app/
    models.py        19 SQLAlchemy tables (BLUEPRINT.md Section 3, in full)
    schemas.py        Pydantic request/response schemas mirroring frontend/src/api/types.ts exactly
    security.py        bcrypt + JWT (HS256, 8h, httpOnly cookie, no refresh — BLUEPRINT.md 6.1)
    deps.py             auth dependencies (current user, hr_admin gate, internal-key gate)
    pagination.py       shared Paginated<T> helper
    routers/            one file per resource, matches BLUEPRINT.md Section 4 + gap resolutions (Section 3 below)
    services/
      classify.py        punch classification (BLUEPRINT.md 5.3)
      recompute.py        nightly/manual daily-status computation (BLUEPRINT.md 5.4) — one routine, two callers
      payroll_calc.py     monthly payroll aggregation (BLUEPRINT.md 5.5)
      pdf.py               WeasyPrint + Jinja2 payslip generation
      shift_lookup.py, config_lookup.py   shared effective-dated lookups
    templates/payslip.html
  alembic/versions/0001_initial.py   hand-written migration: all 19 tables + Phase 1 seed data
  Dockerfile

worker/              Isolated sync + nightly-trigger module (BLUEPRINT.md 2.2) — never touches Postgres
  worker/
    main.py             FastAPI app: APScheduler (interval sync + nightly cron) + manual /sync/{device_id}
    sync.py              pyzk polling + BLUEPRINT.md 5.3-compliant punch extraction
    api_client.py        all communication with `api` over HTTP, X-Internal-Key header
    config.py
  Dockerfile

frontend/Dockerfile, frontend/nginx.conf   added — nginx multi-stage build, proxies /api/ to `api` service
docker-compose.yml, .env.example            added at project root — 4 services per BLUEPRINT.md Section 2
```

---

## 2. How to run it

```bash
cp .env.example .env
# edit .env: set real JWT_SECRET and INTERNAL_API_KEY (openssl rand -hex 32)
docker compose up --build
```

- `api` runs `alembic upgrade head` on container start (before `uvicorn`), then serves on `:8000`.
- `worker` starts its APScheduler jobs on boot (interval device sync, nightly cron).
- `frontend` (nginx) serves on `:8080`, proxying `/api/*` to `api:8000`.
- First login: **username `admin`, password `ChangeMe123!`** (seeded by the migration —
  see Section 5 below). **Change this password immediately** via
  `PATCH /auth/me/password` or `/settings/profile` in the UI.
- A single seed `locations` row ("Main Location", `Europe/Belgrade`) is created so the
  system is usable immediately; HR/Admin can rename/add more via `/locations`.

### Local development (no Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# requires a running Postgres reachable per POSTGRES_* env vars, and system
# packages for WeasyPrint (see Dockerfile) if generating PDFs
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev   # VITE_API_BASE_URL defaults to /api/v1; set it to http://localhost:8000/api/v1
              # for local dev since there's no nginx proxy — CORS_ORIGINS on
              # the api already allows http://localhost:5173 by default
```

### Migrations

- `alembic upgrade head` — applies `0001_initial.py` (all tables + seed data).
- To add new migrations later: `alembic revision -m "description"` then edit manually
  (this project does not rely on autogenerate given the hand-tuned constraint/seed setup).

---

## 3. Environment variables (devops reference)

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `checkin` / `checkin` / `checkin` | must match between `db` and `api` |
| `JWT_SECRET` | — (required, no safe default) | HS256 signing secret, BLUEPRINT.md 6.1. `docker-compose.yml` fails fast if unset. |
| `INTERNAL_API_KEY` | — (required) | shared secret for `worker`<->`api` internal endpoints (`X-Internal-Key` header), BLUEPRINT.md Section 7. Also used by `api` to call `worker`'s manual-sync endpoint. |
| `WORKER_INTERNAL_URL` | `http://worker:8100` | `api` -> `worker` (manual sync trigger only, see Section 4 below) |
| `SYNC_INTERVAL_SECONDS` | `300` | `worker`'s device poll interval, BLUEPRINT.md 2.2 |
| `NIGHTLY_HOUR` / `NIGHTLY_MINUTE` | `2` / `0` | `worker`'s nightly daily-status trigger time (local to host clock) |
| `DEVICE_TIMEZONE` | `Europe/Belgrade` | see Section 6 "Timezone source" below — **read carefully** |
| `PAYSLIP_STORAGE_DIR` | `/app/payslips` (container path, backed by the `payslips` named volume) | where generated payslip PDFs are stored |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | only exercised by `npm run dev` against a local `api`; production nginx path is same-origin |
| `VITE_API_BASE_URL` (frontend build arg) | `/api/v1` | only needs overriding if not served behind the provided nginx proxy |

---

## 4. FRONTEND_NOTES.md gap resolutions

Each of the 10 gaps FRONTEND_NOTES.md flagged, and how the backend resolved it:

1. **`PATCH /attendance/daily-status/{id}/excused`** — implemented exactly at this
   path/verb (`app/routers/attendance.py:set_excused`). HR/Admin only.
2. **`GET /leave-records/{id}`** — implemented (`app/routers/leave.py:get_leave_record`),
   manager-scoped (403 if the record's employee isn't on that manager's team).
3. **`/users` resource** — implemented in full: `GET /users` (paginated), `POST /users`,
   `PATCH /users/{id}`, `PATCH /users/{id}/reset-password`. HR/Admin only, matches
   `usersApi` in `endpoints.ts` exactly, including the `employee_name` derived field.
4. **Manager employee-filter scoping** — resolved via **option (a)** from
   FRONTEND_NOTES.md: `GET /employees` and `GET /employees/{id}` are relaxed to allow
   role `manager`, with results filtered server-side to `employees.location_id =
   current_user.location_id` (same pattern BLUEPRINT.md 6.2 already established for
   `/attendance/daily-status` and `/leave-records`). Write endpoints stay
   HR/Admin-only. See `app/routers/employees.py` module docstring. **Note:** this was
   originally `employees.manager_user_id = current_user.id` (team-based); superseded
   2026-08-22, see Section 8 below.
5. **Device `is_active` toggle** — no dedicated endpoint added (FRONTEND_NOTES.md
   explicitly said not to invent a UI control DESIGN_SPEC didn't ask for). The field
   **is** accepted by the existing `PUT /devices/{id}` (it's part of `DeviceUpdate`), so
   if a future UI adds a toggle, no backend change is needed.
6. **`success-outline` Button variant** — frontend-only, no backend action.
7. **Payroll "Total Penalties"/"Total Bonuses" stat-block formula** — confirmed
   compatible: `payroll_run_lines.total_lateness_penalty_eur` and
   `total_overtime_bonus_eur` are exactly the two fields the frontend sums, and the
   backend never folds absence deductions or adjustments into either (see
   `services/payroll_calc.py` module docstring for the full formula breakdown).
8. **Catch-all 404** — frontend-only, no backend action.
9. **Field-level validation error shape** — FastAPI's default 422 body (`detail` as a
   list of `{loc, msg, type}` objects) does **not** match what the frontend's
   `extractMessage` parses (it only reads a plain string `detail`/`message`). Added a
   `RequestValidationError` handler (`app/main.py`) that flattens Pydantic's error list
   into a single readable string, e.g. `"body.name: Field required"`, so existing
   frontend error banners work unmodified. Structured per-field mapping was **not**
   built (would require a frontend contract change beyond this backend's scope) — the
   one case DESIGN_SPEC calls out explicitly (payroll-run 409 duplicate period) is
   already a plain-string `detail` on a 409, which the frontend already handles.
10. **IANA timezone list source** — frontend-only (browser `Intl.supportedValuesOf`),
    no backend dependency. Backend stores whatever string the frontend sends in
    `locations.timezone` and uses it as the IANA zone name for all local-time
    conversions (punch classification, late/overtime calculation) — see Section 6.

---

## 5. Assumptions made where BLUEPRINT.md was silent

Flagged explicitly per the task's instructions — **business-rule *values* remain
DB-configurable** (penalty/overtime/absence config tables, per Discovery.md Section
10); what's below is backend *algorithm* judgment calls only, not hardcoded policy:

- **Bootstrap seed data**: migration seeds one `locations` row and one `hr_admin`
  user (`admin` / `ChangeMe123!`) purely so the freshly-deployed system has a way to
  log in at all — this is an operational bootstrap step, not a business rule.
  **Must be changed on first login** (documented above and should be called out again
  in `DEPLOYMENT.md` by `devops`).
- **Overtime threshold apportionment** (`services/recompute.py` / `payroll_calc.py`
  docstrings have the full detail): when `overtime_config.threshold_basis = 'daily'`,
  the daily threshold is subtracted at the day level (matches BLUEPRINT.md 5.4's literal
  wording). When `'weekly'`, raw daily overtime minutes are summed per ISO week and the
  weekly threshold is subtracted once per week at payroll-aggregation time (a single day
  cannot know its week's running total in isolation) — the weekday/weekend split of the
  post-threshold total is apportioned by each week's weekday/weekend minute ratio.
  `monthly_cap_minutes` scales the whole-month total proportionally if exceeded.
- **`holiday_rate_per_hour_eur` is defined but unused** — BLUEPRINT.md's data model
  (Section 3) has no holiday-calendar table, so there is no data source to know which
  dates are holidays. The column exists (per BLUEPRINT.md 3.12) and is accepted/stored
  via `/config/overtime`, but payroll calculation never applies it in Phase 1. Flagged
  as a genuine gap for `devops`/product, not silently worked around.
- **Lateness penalty cap scope**: `penalty_config.max_daily_penalty_eur` caps the
  *lateness* component only; early-departure penalty
  (`early_departure_minutes * early_departure_rate_per_minute_eur`) is added
  uncapped, since BLUEPRINT.md's schema comment doesn't specify whether the cap should
  cover both.
- **Absence deduction daily-rate basis**: `full_day_salary_fraction` converts to euros
  via `base_salary_eur / days_in_month * deduction_value` (calendar days in month, not
  working days) — BLUEPRINT.md doesn't specify the divisor.
- **Leave day paid/unpaid split**: derived from `attendance_daily_status` rows already
  marked `on_leave` by the recompute routine (only ever set for scheduled working days
  with an approved, overlapping leave record), rather than raw calendar-day counting —
  keeps the payroll numbers consistent with what HR sees on the Attendance page.
- **`worker` <-> `api` bidirectional calls** (BLUEPRINT.md Section 4.3's
  "`POST /devices/{id}/sync` ... proxies to worker" implies a call path BLUEPRINT.md
  never fully specifies, since Section 2.2 only describes `worker` calling `api`, not
  the reverse): resolved by giving `worker` its own tiny FastAPI app exposing
  `POST /sync/{device_id}` (shared-secret protected, same `X-Internal-Key`), which `api`
  calls for the manual on-demand trigger. This keeps `worker` outbound-initiated for its
  *scheduled* work (matching the Phase 2 "local agent, outbound only" shape) while still
  allowing an on-demand trigger in the Phase 1 LAN topology where both containers are
  mutually reachable — documented as Phase-1-specific; Phase 2's remote-agent design will
  need to revisit on-demand triggering separately (NAT/outbound-only agents can't be
  called into directly), consistent with Discovery.md's "design-aware only" framing for
  Phase 2 networking.
- **`GET /internal/devices`** — added beyond BLUEPRINT.md Section 4.10's explicit list.
  Necessary consequence of `worker` never touching Postgres directly (BLUEPRINT.md 2.2):
  `worker` has no way to discover which devices exist/are active/what IP:port to poll
  without asking `api`. Shared-secret protected like the other internal endpoints.
- **Device clock timezone** (`worker/worker/config.py` `DEVICE_TIMEZONE` env var):
  pyzk returns naive datetimes read directly off the K40's onboard clock. `worker` has
  no DB access to look up the punching employee's `locations.timezone` per device, so a
  single env var (default `Europe/Belgrade`, matching BLUEPRINT.md 3.1's default) is
  used to localize every device's punches to UTC before pushing to `api`. **For Phase 2
  multi-location rollout, this becomes a per-device concern** — flagged for whoever
  extends `worker` per-location.
- **Punch classification detail**: BLUEPRINT.md 5.3 step 3 ("within each category,
  first chronological = check-in, alternating") is applied literally, including for
  the codes 2/3 break punches which are otherwise directly mapped by step 1 — i.e. a
  code-2/3 punch keeps its explicit direction rather than being re-numbered by ordinal
  position, while all other punches in that day's work/break buckets are alternated.
  This produced correct results in testing (see Section 1) but is worth a sanity check
  against real device output once the pilot K40 is on-site, since BLUEPRINT.md's
  own prose is slightly ambiguous about how steps 1 and 3 interact.

---

## 6. Bug found and fixed during verification

While writing the end-to-end smoke test (real PostgreSQL, full FastAPI app, every
endpoint), one real bug was caught and fixed: `PenaltyConfig`, `OvertimeConfig`, and
`AbsenceRuleConfig` SQLAlchemy models were missing their `location` relationship
(only the `location_id` FK column existed), which crashed `POST /config/penalty` (and
the other two config resources) at serialization time. Fixed in `app/models.py`.
Also pinned `pydyf==0.11.0` in `backend/requirements.txt` — WeasyPrint 62.3 is
incompatible with pydyf 0.12+ (a breaking upstream API change), which broke PDF
payslip generation until pinned.

---

## 7. Known limitations / out of scope (matches BLUEPRINT.md Section 11)

- No employee self-service, no email delivery, no multi-location aggregation/heartbeat
  alerting UI, no 2FA/IP allowlisting — none implemented, per BLUEPRINT.md.
- `devices.last_synced_at` is populated (via the internal heartbeat endpoint) but no
  stale-sync alerting exists yet (Phase 2 concern per BLUEPRINT.md).
- No holiday calendar (see Section 5 above) — `overtime_config.holiday_rate_per_hour_eur`
  is stored but unused.
- Session cookie is issued with `secure=False` (LAN-only HTTP, no TLS in Phase 1, per
  BLUEPRINT.md Section 8) — `devops`/`security` should confirm this is still correct
  before any internet-facing exposure.

---

## 8. 2026-08-22 access-control change — manager scoping: team-based → location-based

Implements BLUEPRINT.md Sections 3.4, 3.14, 6.2, 6.3, 6.4 (client-directed change,
architect-approved). Manager visibility now filters on `employees.location_id ==
users.location_id` instead of `employees.manager_user_id == users.id`.

- **Model** (`app/models.py`): added `User.location_id` (nullable FK →
  `locations.id`) + `User.location` relationship, matching the `Device`/`Employee`
  pattern already in the file.
- **Migration**: `backend/alembic/versions/0002_users_location_id.py` (revision
  `0002_users_location_id`, down-revision `0001_initial`) — adds nullable
  `users.location_id` + FK. No backfill/default (existing rows get `NULL`, which is
  the correct fail-closed starting state per BLUEPRINT.md 6.2's transition-behavior
  note). `employees.manager_user_id` is untouched — still written on
  employee create/update, still returned as `manager_name` for display, but no
  longer read in any authorization `WHERE` clause.
- **Auth rewrite** — all 8 call-sites BLUEPRINT.md 6.3 lists, converted from
  `Employee.manager_user_id == user.id` (or `!=`) to `Employee.location_id ==
  user.location_id` (or `!=`): `attendance.py:list_daily_status`,
  `leave.py:_assert_manager_can_view`, `leave.py:list_leave_records`,
  `leave.py:_approve_reject`, `employees.py:_assert_manager_can_view`,
  `employees.py:list_employees`, `reports.py:dashboard_summary` (both the
  attendance-status and leave-query branches). Re-grepped `manager_user_id` in
  `app/routers/*.py` afterward — zero remaining `==`/`!=` comparisons against
  `user.id`; only display/write references remain (unaffected, as expected).
  Null-safety: every list-query call-site does an explicit `if user.location_id is
  None: q = q.filter(false())` branch rather than relying on `Employee.location_id
  == user.location_id` to fail correctly under SQL `NULL = NULL` semantics; every
  single-record view-guard uses `user.location_id is None or emp.location_id !=
  user.location_id` for the same reason.
- **Schemas** (`app/schemas.py`): `AppUserCreate`/`AppUserUpdate` gained
  `location_id: int | None = None`; `AppUserOut` gained `location_id` and a
  computed `location_name` (serialized in `app/routers/users.py:_serialize`,
  same pattern as `employees.py`'s `location_name`/`manager_name`).
- **`users.py` router**: `POST /users` and `PATCH /users/{id}` now accept
  `location_id`, validating existence (400 `"Location not found"` if the id doesn't
  resolve to a row — same pattern as `employees.py:create_employee`).
- **Verified end-to-end against the real running stack** (not mocks): rebuilt
  `api` via `docker compose up -d --build api`; `docker compose logs api` showed
  `0001_initial -> 0002_users_location_id` applying cleanly with no errors. Then,
  against the live API with real cookie-based sessions:
  - `manager1`/`manager2` (both seeded with `location_id = NULL`) hit
    `/employees`, `/attendance/daily-status`, `/leave-records`, and
    `/reports/dashboard-summary` — all returned empty result sets (200, not 403,
    not all-rows) confirming the fail-closed transition behavior.
  - Logged in as `hr_admin`, `PATCH /users/{id}` assigned `manager1 → location 1`
    (Main Location) and `manager2 → location 2` (North Branch); confirmed
    `location_name` round-trips correctly in the response.
  - Re-hit the same manager1/manager2 endpoints: each manager now saw exactly
    their assigned location's employees/attendance/leave, and — critically —
    **South Branch employees (location 3), which also carry `manager_user_id =
    manager2.id` from seed data, were correctly excluded from manager2's
    results**, proving the scoping is genuinely location-based and not
    incidentally still keying off `manager_user_id`.
  - Confirmed the employee-detail view-guard: manager2 got `403` on a Main
    Location employee, `200` on a North Branch employee.
  - `hr_admin` (`admin`, password reset to a fresh value during this
    verification session since the seeded/previous credential no longer worked —
    devops/whoever owns demo creds should note this if it matters) continued to
    see all employees/locations unfiltered, confirming role `hr_admin` is
    unaffected by this change.
- **Judgment calls**: (1) used `sqlalchemy.false()` for the "manager has no
  location" list-query branch rather than a tautological `1 == 0` filter, for
  clarity; (2) did not add a backend-side rejection of `location_id` being sent
  for `hr_admin`-role user payloads — BLUEPRINT.md/DESIGN_SPEC only specify the
  frontend form conditionally hides the field for that role, and neither
  BLUEPRINT.md 6.4 nor the task instructions asked for an API-level role/field
  cross-validation, so none was added (the column is simply ignored by
  authorization logic for `hr_admin` regardless of its stored value); (3) also
  corrected the stale `manager_user_id`-based description in
  `employees.py`'s module docstring (not code) since leaving it would
  misdocument the very mechanism just changed.
- **Pre-existing bug noticed, not fixed** (out of scope for this pass):
  `app/pagination.py`'s `total` count is wrong for queries with no `.join()` (e.g.
  `GET /users`, `GET /employees` as `hr_admin` with no filters) — `total` comes back
  as `1` regardless of actual row count, while joined queries (e.g.
  `/attendance/daily-status`) compute `total` correctly. Reproduced directly via
  `query.order_by(None).with_entities(func.count()).scalar()` vs `query.count()`
  returning different values on an unfiltered `db.query(User)`. Unrelated to the
  location-scoping change (pagination.py wasn't touched, and the affected paths
  don't run through the new manager-scoping code at all — `hr_admin` never hits
  those branches). Flagged here for `qa`/whoever picks this up next, since it
  affects every unfiltered/unjoined paginated list in the app, not just Users.

## 9. 2026-09-17 split shifts, parallel assignments, overtime pre-approval

Client-directed change: an employee can now hold several shifts at once, in both
senses of the word, and overtime outside the ordinary pattern can be made to
require sign-off before it is paid.

- **Split shifts** — new table `shift_work_windows` (migration
  `0011_split_shifts_ot_approval`): one row per work block per weekday, so Monday
  can be `08:00-12:00` **and** `17:00-21:00`. Existing days were backfilled into
  one window each, so nothing about an already-configured schedule changed.
  `shift_schedule_days.work_start_time/work_end_time` are KEPT but are now a
  **derived cache of the day's outer bounds** (earliest start, latest end),
  written only by `PUT /shift-schedules/{id}/days`. Consumers that want the day's
  span (the not-checked-in alert, the attendance table's "Scheduled" column, the
  payslip) read them unchanged; per-block math reads the new table via
  `services/shift_lookup.get_work_windows`.
- **Per-block payroll math** (`services/recompute.py::_window_deltas`): the day is
  cut at the midpoint between consecutive blocks, each work punch is judged
  against the block it falls nearest to, and late / early-departure / overtime are
  summed over blocks. With one block this is arithmetically identical to the
  previous day-level code (the full 140-test suite passed unchanged before the new
  tests were added). A block with no punches at all contributes nothing —
  consistent with the existing rule that a missing punch is an alert, never a
  silent penalty. The gap between blocks is NOT an early departure.
- **Parallel assignments** — `_assert_no_overlap` in `routers/employees.py` became
  `_assert_no_conflict`: overlapping date ranges are allowed when the schedules
  behind them work disjoint weekdays (Cafe Shift Mon-Tue + Office Shift Wed-Fri,
  both open-ended), and refused when they claim the same weekday, which would make
  "which schedule owns this Monday" unanswerable.
  `shift_lookup.get_effective_shift_schedule` resolves a date by picking the
  covering assignment whose schedule marks that weekday as working, falling back
  to the most recent covering assignment so an off day still reads as
  `not_scheduled` against a known schedule.
- **Overtime pre-approval** — `overtime_config.requires_preapproval` existed in
  the schema since Phase 1 and nothing read it. Now: `attendance_daily_status`
  carries `overtime_approved_at` / `overtime_approved_by_user_id`,
  `PATCH /attendance/daily-status/{id}/overtime-approval` sets them (admin, or a
  manager within their own location), and `services/payroll_calc.py` excludes
  unapproved days from the overtime buckets where the flag is on. An approval is
  tied to the figure that was approved: `recompute_employee_date` clears it if a
  later punch changes `overtime_minutes`, so a day approved at 20 minutes can
  never quietly pay 200.
- **Two new alerts** (`routers/reports.py`): `punch_outside_schedule` (a punch on
  an unscheduled day, or more than `OUTSIDE_SCHEDULE_TOLERANCE` = 2h outside the
  day's outer bounds — a punch in a split shift's midday gap is normal and is not
  flagged) and `overtime_pending_approval` (raised only where the flag is on, so
  approval-gated money is never simply forgotten).
- **Fixed in passing, because this change touched the same write path**:
  `PUT /shift-schedules/{id}/days` bulk-deleted `shift_schedule_days` while
  `shift_break_windows.shift_schedule_day_id` carries no `ON DELETE`, so replacing
  the days of a schedule that had breaks configured could hit a foreign-key
  violation. Child rows are now deleted explicitly first.
- **Tests**: `backend/tests/test_split_shifts_and_overtime_approval.py` (12 tests)
  covers split-shift math per block, the overlap-vs-conflict rule, weekday
  resolution across two live assignments, unapproved-vs-approved overtime through
  a real payroll run, approval invalidation, and both new alerts. Suite total 152.

## 10. 2026-09-17 clock drift, automated backups, holiday calendar

Three operational gaps closed in one pass. All three protect numbers that were
already being computed wrongly or silently, rather than adding features.

### Device clock drift (migration `0012_device_clock_skew`)

Every punch carries the timestamp the DEVICE wrote, so a terminal whose clock
has drifted produces lateness and overtime wrong by exactly that drift, with
nothing in the data to show it. Observed on real hardware: a DS-K1T804AMF
still on factory UTC+8 stamped events `+08:00` and recorded an on-time arrival
as 61 minutes late.

- `worker/worker/adapters/hikvision.py::device_time` reads
  `/ISAPI/System/time`; `zkteco.py::device_time` reads the K40's clock via
  pyzk and anchors it with `DEVICE_TIMEZONE`, the same setting used for its
  punches. A local time with no UTC offset returns None rather than being
  guessed at, since a guess would invent drift (or hide it).
- `sync.read_clock_skew` never raises: a device that will not answer a clock
  query still has punches worth collecting. Hik-Connect has no verified clock
  endpoint, so cloud devices simply report no reading.
- The value rides on the existing heartbeat into `devices.clock_skew_seconds`
  / `clock_checked_at`. A "no reading" heartbeat deliberately does NOT clear a
  previous measurement, otherwise one failed read would silently clear a live
  alert.
- `GET /reports/alerts` raises `device_clock_drift` (danger) past
  `CLOCK_DRIFT_TOLERANCE_SECONDS` = 120: below two minutes the error is
  smaller than any grace period and cannot flip a lateness decision.

### Automated backups (`ops/backup.sh`, `ops/restore.sh`, compose service)

Nothing backed up the database; DEP.md said "you need a cron pg_dump". On
premise that is one machine holding every punch and every payroll run.

- A `backup` container (same postgres image as `db`) dumps nightly into
  `./backups` on the HOST — deliberately not the Postgres volume — verifies
  each dump with `pg_restore --list`, prunes past
  `BACKUP_RETENTION_DAYS`, and writes `./backups/LAST_BACKUP`. A long-running
  container rather than host cron because the target machines are the
  client's own PCs, often Windows, sometimes switched off at night: it comes
  back with the machine and takes a catch-up dump if it missed a run.
- `api` mounts `./backups` read-only purely so `GET /reports/alerts` can raise
  `backup_missing` / `backup_failed` / `backup_stale` (admin-only). The
  failure mode being guarded against is silence.
- `ops/restore.sh` verifies the dump before touching the live database, stops
  api and worker, restores, restarts. Typed confirmation required.
- Verified end to end: a real dump was restored into a scratch database and
  row counts compared against live (attendance_logs, attendance_daily_status,
  employees, payroll_run_lines, shift_work_windows all matched).
- STILL MANUAL: copying the dumps off that machine. Same disk, same fire.

### Public holiday calendar (migration `0013_holidays`)

`attendance_daily_status.status` has allowed `'holiday'` since 0001 and
`overtime_config.holiday_rate_per_hour_eur` has existed just as long, but
nothing could set either — there was no source of truth for which dates are
holidays (flagged as a gap in `services/payroll_calc.py`'s own docstring).
Every public holiday therefore deducted an absence from everyone correctly at
home, and paid holiday work at the ordinary rate.

- `holidays` table: `location_id` NULL = every location (same convention as
  the config tables), `recurs_annually` for fixed-date holidays so 1 January
  is entered once. Uniqueness is two partial indexes, not one composite
  unique: in SQL NULLs are distinct from each other, so a plain unique index
  would allow ten org-wide rows on the same date.
- `services/holiday_lookup.py` resolves a date, preferring a location-specific
  row over an org-wide one so a single branch can override the national
  calendar.
- `services/recompute.py` checks holidays BEFORE leave on purpose: a public
  holiday inside someone's annual leave should not consume a leave day. A
  holiday worked records the hours as holiday work in `overtime_minutes`;
  nobody is late or absent on one.
- `services/payroll_calc.py` gained a third overtime bucket paid at
  `holiday_rate_per_hour_eur`, falling back to the ORDINARY rate when unset,
  never to the weekend rate — an unset holiday rate means "not configured",
  and applying the weekend premium would be inventing a policy nobody chose.
- No Kosovo holiday list is seeded. The official dates (especially the moving
  religious ones) are a legal question, not a code one, and inventing them
  would be worse than leaving the calendar empty and visible.
- UI: Configuration > Holidays, bilingual names, year filter, managers limited
  to their own location (org-wide stays admin-only).

Suite total: 177.

## 11. 2026-09-17 explicit overtime punches (migration `0014_overtime_punch_types`)

The terminal's own attendance vocabulary includes "start overtime" / "end
overtime" (`overtimeIn`/`overtimeOut` in the DS-K1T804AMF's declared
`attendanceStatus` enum; punch codes 4/5 on ZKTeco units). Both used to be
folded into ordinary check-in/check-out, so the device's own statement that a
stretch was overtime was discarded and overtime was only ever inferred from
the schedule.

- `punch_type` / `punch_type_hint` gained `check_in_overtime` /
  `check_out_overtime`. `hikvision.RAW_CODE` now encodes them as 4/5,
  matching ZKTeco's native codes so `services/classify.py` reads one rule for
  both vendors. `classify.py` gives overtime its own bucket, entered ONLY via
  those codes — unlike a break, there is no "overtime window" in a schedule to
  infer from, so overtime exists only when the device says so. The IN comes
  first (you start overtime, then end it), the opposite of the break pair.
- **Threshold policy (a money decision, made deliberately):** badged overtime
  is added WITHOUT `overtime_config.daily_threshold_minutes`; overtime merely
  inferred from staying past the shift still goes through it. The threshold
  exists to ignore someone drifting ten minutes past the end of a shift, and
  pressing the overtime key is not drift — subtracting it from deliberately
  clocked overtime just produces a dispute to settle by hand. `requires_preapproval`
  is unaffected and still gates whether any of it is paid, which is the real
  control on badged overtime. One-line change in `_compute` if the client
  later wants both treated identically.
- An unclosed overtime punch contributes nothing rather than running to the
  end of the day, the same rule this module already applies to a forgotten
  check-out.
- A day with ONLY overtime punches is no longer read as an absence (they were
  at work), but those punches are deliberately kept out of `work_in`/
  `work_out` so they cannot make anyone late or early for a shift they did
  not work.
- `reports.py::_on_site_now` now treats `check_out_overtime` as having gone
  home, alongside `check_out_work`.
- Re-encoding check before shipping: no stored punch anywhere carried an
  overtime code, so no device event could be re-ingested under a new
  `raw_status_code` and double-counted through the dedup key.
- Tests: `backend/tests/test_overtime_punches.py` (8) covers the Hikvision
  hint path, the ZKTeco raw-code path, exempt-vs-thresholded arithmetic side
  by side, both kinds on one day, an unclosed pair, an overtime-only day, and
  payment through a real payroll run. Suite total 185.

## 12. 2026-09-18 Windows edition (native install, no Docker)

A second delivery of the same application: a Windows installer
(`ChronosSetup.exe`) that installs compiled programs as Windows services, so
the client gets no Docker and no readable source. The Docker line is
unchanged (and unaffected: every native behaviour below is opt-in).

- **Native mode in the API.** Without nginx, the API takes over nginx's two
  jobs when `FRONTEND_DIST` / `INTERNAL_LOOPBACK_ONLY` are set: it serves the
  built UI with SPA fallback (resolved paths confined to the build directory),
  and answers `/api/v1/internal/` only to 127.0.0.1/::1 with the same 404 nginx
  gives. `chronos_server.py` forces loopback-only on and runs uvicorn with
  proxy headers off, so `X-Forwarded-For: 127.0.0.1` from the LAN is ignored.
  The worker's internal endpoint binds 127.0.0.1.
- **Entry points** `backend/chronos_server.py` (migrate, then serve) and
  `worker/chronos_worker.py`, compiled with Nuitka. uvicorn's loop, protocol
  and websocket implementations are pinned (`asyncio`, `h11`, none) because it
  otherwise picks them by module name at run time, which a compiled build may
  not contain.
- **One config file** for both services via `CHRONOS_ENV_FILE`; the backup
  marker path moved into Settings for the same reason (the services' config
  never reaches `os.environ`).
- **`tzdata`** added to the backend: Windows has no system timezone database,
  so `ZoneInfo("Europe/Tirane")` would fail on the first recompute.
- **Compile flags** live in `packaging/nuitka/*.args`, read by both
  `packaging/linux-compile-check.sh` and `packaging/windows/build.ps1`. Three
  things the Linux compile check caught that a normal run never would:
  1. `--include-data-dir` silently drops `.py` files, so the migrations never
     made it into the build and a fresh install could not create its database.
     Now `--include-raw-dir=alembic=alembic`; the build fails if any other
     `.py` file ships.
  2. APScheduler finds its thread-pool executor through package entry points,
     so its distribution metadata must be included explicitly.
  3. ~45 MB per program of optional accelerators that are never used (uvloop,
     httptools, watchfiles, websockets, zstandard) are excluded.
  Verified on Linux: both compiled programs pass the 14 native-mode tests and
  the compiled server migrates an empty database to head with the bootstrap
  admin seeded.
- **Windows packaging** (`packaging/windows/`): `install.ps1` (idempotent:
  config with generated secrets, ACL'd to SYSTEM/Administrators; PostgreSQL 16
  cluster on 127.0.0.1:55432 as service ChronosPostgres under NETWORK SERVICE;
  role and database; migrations run synchronously so failures stop the
  installer; WinSW services ChronosServer/ChronosWorker with restart-on-failure;
  firewall rule on private/domain profiles only; "Chronos Backup" task daily
  and at boot), `uninstall.ps1` (keeps data unless `-RemoveData`),
  `backup.ps1`, `restore.ps1`, Inno Setup script, `build.ps1`.
  **Not yet run on Windows**: parse-checked with Windows PowerShell only.
  `.github/workflows/windows-installer.yml` builds on a clean Windows runner,
  installs silently, smoke-tests (services, UI, login, loopback vs network on
  internal endpoints, worker bound to loopback, verified backup, no source
  shipped), upgrades in place, uninstalls, and uploads the installer.

### Bugs found along the way

- **Sessions dropped right after login** (fixed here, also present in the
  Docker line and its published images): a backward wall-clock step between
  issuing and checking a token made PyJWT reject it as issued in the future.
  Measured on Docker Desktop for Windows: 1 in ~2.1M mint-then-verify cycles;
  it was the cause of the intermittent 401s in this suite (and, in hindsight,
  of the "transient" backup-test failure attributed to rate limiting earlier).
  Tokens are now verified with a 30 s leeway. `tests/test_token_clock_skew.py`.
- **"Sync now" on an offline ZKTeco reports the wrong thing** (not fixed): an
  unreachable ZKTeco takes 30 s to fail (pyzk retries), which is exactly the
  API's 30 s wait for the worker, so the user sees "Could not reach sync
  worker" (502) instead of "device unreachable". Hikvision fails in 15 s and
  reports correctly.
