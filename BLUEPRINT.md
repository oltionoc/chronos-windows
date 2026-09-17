# BLUEPRINT.md — chronos: Attendance & Payroll Management System

Status: **FINAL** — ready for `uiux` handoff.
Input: `DISCOVERY.md` (status FINAL, ends "PROJECT READY FOR DEVELOPMENT").

This document is the single source of technical truth for Phase 1 (single-location
pilot). Downstream subagents (`uiux`, `frontend`, `backend`) must be able to build
from this without asking `architect` follow-up questions. Phase 2 (14-location
hub-and-spoke) is referenced only where it constrains Phase 1 schema/module
boundaries, per `DISCOVERY.md` Section 8.

---

## 1. Stack Decision — Override of `CLAUDE.md` Defaults

`CLAUDE.md` "Stack Defaults" specifies Next.js/Node/Prisma/JWT-with-refresh as
the generic default. This project uses a **client-directed override**, already
fixed in `DISCOVERY.md` Section 7. Recorded here per the CLAUDE.md rule that any
override must be justified in `BLUEPRINT.md`:

| Layer | CLAUDE.md default | This project (override) | Justification |
|---|---|---|---|
| Backend | Node.js + Express / Next.js API routes | **Python + FastAPI** | Device integration requires `pyzk`, a Python-only library for the ZKTeco proprietary protocol (TCP 4370). An all-Python backend avoids a cross-language sync layer (e.g. a Node API shelling out to a Python sync process). FastAPI gives async I/O (useful for polling multiple devices concurrently in Phase 2) and Pydantic-validated schemas that pair naturally with SQLAlchemy/Alembic. |
| Frontend | Next.js (App Router) + TypeScript + Tailwind | **React (Vite) + TypeScript + Tailwind CSS** | Discovery specifies "React", not Next.js. This is a LAN-only, no-SEO, no-SSR internal tool behind a login wall — Next.js's SSR/routing machinery adds no value here and would require a Node runtime alongside the Python stack for zero benefit. Vite + React + TypeScript is chosen (TypeScript kept from the default, since it pairs well with FastAPI's generated OpenAPI schema for typed API clients, and is cheap to keep — not a deviation, just the packaging tool changes from Next.js to Vite). Tailwind CSS is kept as-is. |
| Database | PostgreSQL via Prisma (relational) | **PostgreSQL via SQLAlchemy + Alembic** | Client-directed: PostgreSQL confirmed. ORM changes from Prisma (Node) to SQLAlchemy (Python) purely because the backend language changed; Alembic is Python's Prisma-Migrate equivalent, explicitly named in Discovery. |
| Auth | JWT access token (15 min) + refresh token in httpOnly cookie | **Single JWT access token (8 hr expiry) in httpOnly cookie, no refresh token** | See Section 6 for full justification: LAN-only Phase 1 deployment, no public internet exposure, small trusted user base (HR/Admin + Manager only, no employee self-service in Phase 1). Refresh-token rotation infrastructure adds complexity with no security benefit on an isolated LAN. Must be revisited before any Phase 2 internet-facing exposure. |
| Hosting | Vercel (frontend) + Railway (backend/DB) | **Docker Compose on client's on-site PC, LAN-only** | Client-directed (Discovery Section 8): no cloud hosting in Phase 1, client supplies/maintains the host machine, no internet dependency for daily operation. |

Additional fixed choices (not defaults, newly specified):
- Device integration: originally `pyzk` (ZKTeco, TCP 4370, direct connection,
  no agent/cloud/VPN) only. **Multi-vendor since 2026-09-16 — see Section
  5.5**: also supports Hikvision (HTTP/ISAPI, digest auth), dispatched by
  `devices.device_type` via a per-vendor adapter in `worker/worker/adapters/`.
- Containerization: Docker / Docker Compose.

---

## 2. System Architecture & Module Boundaries

Four containers, one Docker Compose stack, one host machine (client's on-site PC),
LAN-only:

```
┌─────────────────────────────────────────────────────────────────┐
│  Docker Compose stack (client on-site PC, LAN only)              │
│                                                                    │
│  ┌───────────┐   ┌───────────┐   ┌────────────┐   ┌────────────┐ │
│  │ frontend  │──▶│    api    │──▶│     db     │◀──│   worker   │ │
│  │ (nginx +  │   │ (FastAPI) │   │(PostgreSQL)│   │ (sync +    │ │
│  │  React    │   │           │   │            │   │  nightly   │ │
│  │  build)   │   │           │   │            │   │  jobs)     │ │
│  └───────────┘   └───────────┘   └────────────┘   └─────┬──────┘ │
│                         ▲                                │        │
│                         │ HTTP (internal ingestion API)   │        │
│                         └────────────────────────────────┘        │
│                                                          │         │
│                                                    ┌──────▼─────┐  │
│                                                    │ K40 device │  │
│                                                    │ (TCP 4370) │  │
│                                                    └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 `api` service (FastAPI)
Stateless request/response HTTP API. Owns all business logic: CRUD, payroll
calculation, PDF generation, auth. Does **not** talk to K40 devices directly.
Exposes both the public-facing API (consumed by `frontend`) and an
**internal ingestion API** (consumed only by `worker`, see 2.2).

### 2.2 `worker` service — isolated sync + batch module (Phase 2 seed)
This is the module explicitly called out in Discovery as needing to be
"isolated/relocatable... seeded for reuse as the Phase 2 agent." Design
consequence: **`worker` never writes to PostgreSQL directly.** It only:
1. Polls each active `device` row via `pyzk` on a schedule (default: every 5
   minutes, configurable via env var `SYNC_INTERVAL_SECONDS`).
2. Pushes newly-read raw punches to the `api` service's internal ingestion
   endpoint (`POST /api/v1/internal/ingest/punches`) over HTTP, authenticated
   with a shared internal API key (env var `INTERNAL_API_KEY`, injected via
   Docker Compose, never exposed to `frontend`).
3. Runs the nightly daily-status batch job (APScheduler, cron-style, default
   02:00 local time) by calling `POST /api/v1/internal/process/daily-status`
   on `api` for the target date — the actual computation logic lives in `api`
   (so it's also reachable via manual admin trigger), `worker` just owns the
   schedule/trigger.

**Why this matters:** Discovery's Phase 2 design explicitly avoids "direct
agent-to-central-DB writes" and requires "central ingestion API validates and
dedupes before writing to DB." By building Phase 1's `worker` to talk to `api`
over HTTP instead of touching the DB directly, Phase 1 already conforms to the
Phase 2 shape (local agent → HTTPS push → central ingestion API → DB). Moving
`worker`'s code to a remote site in Phase 2 becomes a deployment change
(point it at the central API's URL instead of `localhost`), not a rewrite.

`worker` has no other responsibilities — it is not the general job runner for
the app; it exists solely for device I/O and the nightly trigger, so it can be
lifted out wholesale.

### 2.3 `db` (PostgreSQL) + Alembic
Single source of truth. Alembic migrations run as a one-shot init container
step (`alembic upgrade head`) before `api` starts.

### 2.4 `frontend` (nginx serving a static Vite/React build)
Talks only to `api`'s public routes (`/api/v1/...`), never to `worker` or `db`
directly. Bilingual (Albanian default, English toggle) via `react-i18next`.

---

## 3. Data Model

All tables use `id` as `SERIAL`/`BIGSERIAL` primary key and `created_at`,
`updated_at` (`timestamptz`, default `now()`) unless noted. All timestamps are
stored in UTC; display conversion uses `locations.timezone`.

### 3.1 `locations`
Present from Phase 1 day one per Discovery (avoids Phase 2 retrofit).

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| name | text, not null | |
| address | text, nullable | |
| timezone | text, not null, default `'Europe/Belgrade'` | IANA tz name (Kosovo) |
| is_active | boolean, default true | |

Phase 1 will have exactly one row. Schema and API support many.

### 3.2 `devices`
Supports multiple devices per location from day one (Discovery confirmed,
even though pilot has exactly one).

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, not null | |
| label | text, not null | e.g. "Main Entrance K40" |
| ip_address | inet, not null | |
| port | integer, not null, default 4370 | |
| serial_number | text, nullable | from device, if available |
| is_active | boolean, default true | |
| last_synced_at | timestamptz, nullable | heartbeat; unused for alerting in Phase 1 (single device, HR checks manually), but populated now — this is the exact field Discovery's Phase 2 section names for stale-sync alerting, seeded early to avoid retrofit |

### 3.3 `employee_device_enrollments`
**Critical mapping table**, required because a K40's punch record contains a
`device_user_id` that is only unique *per device*, not globally. Without this
table, multi-device support is impossible to implement correctly (an
employee enrolled on two devices at the same location, or two employees with
colliding enrollment IDs on different devices, would collide).

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| employee_id | FK → employees, not null | |
| device_id | FK → devices, not null | |
| device_user_id | text, not null | the enrollment ID pyzk returns for this person on this device |
| enrolled_at | timestamptz, nullable | |

Constraint: `UNIQUE(device_id, device_user_id)`.

### 3.4 `employees`

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, not null | |
| employee_code | text, not null, unique | human-readable ID, HR-assigned |
| first_name | text, not null | |
| last_name | text, not null | |
| national_id | text, nullable | |
| hire_date | date, not null | |
| base_salary_eur | numeric(10,2), not null | |
| manager_user_id | FK → users, nullable | **Display/"reports to" only as of the 2026-08-22 access-control change — does NOT drive access control.** Retained in schema for showing an employee's direct-report line (e.g. `employee.manager` on the employee detail page). Manager visibility scoping is now location-based; see Section 6.2. |
| employment_status | enum: `active`, `inactive`, `terminated`, default `active` | |

No hardcoded row-count assumption anywhere (Discovery Section 11): all
employee list endpoints are paginated (Section 4.3).

### 3.5 `shift_schedules`, `shift_schedule_days`, `shift_break_windows`
New entity confirmed required in Discovery (shifts vary per employee/group).

**`shift_schedules`**

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, nullable | nullable = usable across locations if needed later; Phase 1 will scope to the single location |
| name | text, not null | e.g. "Morning Shift", "Weekend Rotation" |
| grace_minutes_late | integer, not null, default 0 | minutes after `work_start_time` before a punch counts as late — admin-configurable per Discovery Section 10 |
| is_active | boolean, default true | |

**`shift_schedule_days`** (one row per applicable day of week per schedule)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| shift_schedule_id | FK → shift_schedules, not null | |
| day_of_week | integer 0–6, not null | 0 = Monday |
| is_working_day | boolean, not null | |
| work_start_time | time, nullable | null if not a working day |
| work_end_time | time, nullable | |

Constraint: `UNIQUE(shift_schedule_id, day_of_week)`.

**`shift_break_windows`** (zero or more per schedule day — Discovery: "break
window(s)", plural)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| shift_schedule_day_id | FK → shift_schedule_days, not null | |
| break_start_time | time, not null | |
| break_end_time | time, not null | |
| is_paid | boolean, not null, default false | admin-configurable per Discovery Section 10 ("whether breaks are paid") |

### 3.6 `employee_shift_assignments`
Effective-dated so historical payroll recompute uses the shift schedule that
was actually in force on a given date, even if an employee's shift changes
later.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| employee_id | FK → employees, not null | |
| shift_schedule_id | FK → shift_schedules, not null | |
| effective_from | date, not null | |
| effective_to | date, nullable | null = still in effect |

App-layer invariant (enforced in `backend`, not DB-level): no two assignments
for the same employee may have overlapping `[effective_from, effective_to)`
ranges.

### 3.7 `attendance_logs` (raw punches)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| device_id | FK → devices, not null | |
| device_user_id | text, not null | raw ID as read from device |
| employee_id | FK → employees, nullable | null = unresolved punch (no matching `employee_device_enrollments` row); surfaced to HR for manual mapping rather than silently dropped |
| punch_timestamp | timestamptz, not null | |
| raw_status_code | integer, not null | raw `punch`/status value from `pyzk` (see Section 5.3 for interpretation) |
| punch_type | enum: `check_in_work`, `check_out_work`, `check_in_break`, `check_out_break`, `unclassified`, nullable until classified | derived value, see Section 5.3 |
| synced_at | timestamptz, not null, default now() | when `worker` ingested it |

Constraint (dedup key, Discovery's named acceptance criterion): `UNIQUE(device_id, device_user_id, punch_timestamp, raw_status_code)`.
Index: `(employee_id, punch_timestamp)`.

### 3.8 `attendance_daily_status` (nightly-computed, per employee per day)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| employee_id | FK → employees, not null | |
| work_date | date, not null | |
| shift_schedule_id | FK → shift_schedules, nullable | snapshot of the schedule in effect that date (via `employee_shift_assignments`) |
| scheduled_start | time, nullable | snapshot, for audit/display even if schedule later changes |
| scheduled_end | time, nullable | |
| actual_first_in | timestamptz, nullable | |
| actual_last_out | timestamptz, nullable | |
| late_minutes | integer, not null, default 0 | |
| early_departure_minutes | integer, not null, default 0 | |
| overtime_minutes | integer, not null, default 0 | |
| break_minutes_taken | integer, not null, default 0 | |
| status | enum: `present`, `late`, `absent`, `on_leave`, `holiday`, `not_scheduled` | |
| is_absence_excused | boolean, nullable | set when `status = absent` and an approved leave record overlaps retroactively, or manually overridden by HR |
| recompute_version | integer, not null, default 1 | incremented each time the nightly/recompute job overwrites this row (e.g. after late leave approval); idempotency + audit trail |
| computed_at | timestamptz, not null | |

Constraint: `UNIQUE(employee_id, work_date)`.

### 3.9 `leave_types`

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| name | text, not null | e.g. "Annual Leave", "Sick Leave" |
| is_paid | boolean, not null | admin-configurable, Discovery Section 10 |
| annual_entitlement_days | numeric(5,1), nullable | admin-configurable, Discovery Section 10 |
| requires_approval | boolean, not null, default true | |
| is_active | boolean, default true | |

### 3.10 `leave_records`

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| employee_id | FK → employees, not null | |
| leave_type_id | FK → leave_types, not null | |
| start_date | date, not null | |
| end_date | date, not null | |
| status | enum: `pending`, `approved`, `rejected`, `cancelled`, not null, default `pending` | |
| requested_by_user_id | FK → users, not null | HR creates on behalf of employee — no self-service in Phase 1 (Discovery Section 3) |
| approved_by_user_id | FK → users, nullable | |
| approved_at | timestamptz, nullable | |
| notes | text, nullable | |

### 3.11 `penalty_config` (lateness — euro-denominated, admin-configurable, effective-dated)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, nullable | null = applies to all locations |
| rule_type | enum: `flat_per_minute`, `threshold_allowance` | structure TBD with client per Discovery Section 10 — both supported, admin picks |
| rate_per_minute_eur | numeric(8,2), nullable | used when `rule_type = flat_per_minute` |
| allowance_minutes | integer, nullable | grace minutes before any penalty applies, used when `rule_type = threshold_allowance` |
| flat_amount_eur | numeric(8,2), nullable | flat penalty once allowance is exceeded |
| max_daily_penalty_eur | numeric(8,2), nullable | optional cap |
| early_departure_rate_per_minute_eur | numeric(8,2), nullable | Discovery: "how early departure is handled" — configurable, defaults to 0 (no penalty) until client decides |
| effective_from | date, not null | |
| effective_to | date, nullable | |
| is_active | boolean, default true | |

### 3.12 `overtime_config` (euro-denominated, admin-configurable, effective-dated)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, nullable | |
| threshold_basis | enum: `daily`, `weekly` | Discovery: TBD, admin-configurable |
| daily_threshold_minutes | integer, nullable | |
| weekly_threshold_minutes | integer, nullable | |
| rate_per_hour_eur | numeric(8,2), not null | |
| weekend_rate_per_hour_eur | numeric(8,2), nullable | null = same as `rate_per_hour_eur` |
| holiday_rate_per_hour_eur | numeric(8,2), nullable | |
| requires_preapproval | boolean, not null, default false | Discovery: TBD |
| monthly_cap_minutes | integer, nullable | |
| effective_from | date, not null | |
| effective_to | date, nullable | |
| is_active | boolean, default true | |

### 3.13 `absence_rule_config`
Directly implements Discovery Section 10's explicitly-unresolved default
absence rule as **data, not code**.

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, nullable | |
| rule_type | text, not null, default `'no_punch_no_leave'` | string enum, extensible for future rule types without a migration |
| deduction_basis | enum: `flat_amount`, `full_day_salary_fraction` | admin-configurable |
| deduction_value | numeric(8,2), not null | euro amount if `flat_amount`; fraction (e.g. 1.0) of daily salary if `full_day_salary_fraction` |
| effective_from | date, not null | |
| effective_to | date, nullable | |
| is_active | boolean, default true | |

Phase 1 seed value (inserted via migration seed data, not hardcoded in
application logic): one row, `rule_type = 'no_punch_no_leave'`,
`deduction_basis = 'full_day_salary_fraction'`, `deduction_value = 1.0`,
matching the proposed default in Discovery. HR/Admin can edit or add rows via
the config UI once the client confirms final policy.

### 3.14 `users` (login accounts — HR/Admin, Manager)

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| username | text, not null, unique | |
| password_hash | text, not null | bcrypt |
| role | enum: `hr_admin`, `manager`, not null | |
| employee_id | FK → employees, nullable | links a Manager's login to their own employee record if they're also on payroll; nullable since not required |
| location_id | FK → locations, nullable | **Added 2026-08-22, client-directed access-control change.** A Manager's assigned location — drives location-based visibility scoping (Section 6.2). Nullable: `hr_admin` users never need it; a `manager` row may also be temporarily null (before HR assigns a location, or if cleared later) — see Section 6.2's transition-behavior note for what a null value means at query time. One location per manager, no join table (Phase 1 is single-pilot-location per `DISCOVERY.md`; a manager-covers-multiple-locations model is not a confirmed requirement and is deliberately not built). |
| is_active | boolean, default true | |
| last_login_at | timestamptz, nullable | |

### 3.15 `payroll_runs`

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| location_id | FK → locations, nullable | null = all locations (Phase 1: effectively one) |
| period_year | integer, not null | |
| period_month | integer, not null | |
| status | enum: `draft`, `finalized`, not null, default `draft` | |
| generated_by_user_id | FK → users, not null | |
| finalized_at | timestamptz, nullable | |

Constraint: `UNIQUE(location_id, period_year, period_month)`.

### 3.16 `payroll_run_lines`

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| payroll_run_id | FK → payroll_runs, not null | |
| employee_id | FK → employees, not null | |
| base_salary_eur | numeric(10,2), not null | snapshot at run time |
| total_late_minutes | integer, not null, default 0 | |
| total_lateness_penalty_eur | numeric(10,2), not null, default 0 | |
| total_overtime_minutes | integer, not null, default 0 | |
| total_overtime_bonus_eur | numeric(10,2), not null, default 0 | |
| total_absence_days | numeric(5,1), not null, default 0 | |
| total_absence_deduction_eur | numeric(10,2), not null, default 0 | |
| paid_leave_days | numeric(5,1), not null, default 0 | |
| unpaid_leave_days | numeric(5,1), not null, default 0 | |
| net_pay_eur | numeric(10,2), not null | base − penalties − absence deductions + overtime bonus + adjustments |
| payslip_pdf_path | text, nullable | populated once PDF generated |

Constraint: `UNIQUE(payroll_run_id, employee_id)`.

### 3.17 `payroll_adjustments`
Manual, ad-hoc bonus/deduction entries HR can add per employee per run
(covers Discovery Section 10's "any additional pay components" until a
formal component system is needed).

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| payroll_run_line_id | FK → payroll_run_lines, not null | |
| type | enum: `bonus`, `deduction` | |
| amount_eur | numeric(10,2), not null | |
| reason | text, not null | |
| created_by_user_id | FK → users, not null | |

---

## 4. API Surface

Base path: `/api/v1`. All responses JSON. All list endpoints are paginated
(`?page=`, `?page_size=`, default 25, max 100) — no assumed employee-count
ceiling anywhere (Discovery Section 11). All non-auth, non-internal endpoints
require a valid session (Section 6) and are role-checked per row below
(`A` = hr_admin, `M` = manager).

### 4.1 Auth
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/auth/login` | public | body: username, password → sets httpOnly cookie |
| POST | `/auth/logout` | A, M | clears cookie |
| GET | `/auth/me` | A, M | current user + role |
| PATCH | `/auth/me/password` | A, M | change own password |

### 4.2 Locations
| Method | Path | Roles |
|---|---|---|
| GET | `/locations` | A |
| POST | `/locations` | A |
| GET/PUT | `/locations/{id}` | A |

### 4.3 Devices
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/devices?location_id=` | A | |
| POST | `/devices` | A | |
| GET/PUT/DELETE | `/devices/{id}` | A | |
| POST | `/devices/{id}/test-connection` | A | `api` calls `pyzk` synchronously to ping and report reachability; used for setup verification only, not the recurring sync path |
| POST | `/devices/{id}/sync` | A | manual on-demand sync trigger — proxies to `worker` (see Section 4.9) |

### 4.4 Employees & enrollments
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/employees?location_id=&status=&search=&page=&page_size=` | A | |
| POST | `/employees` | A | |
| GET/PUT | `/employees/{id}` | A, M (M read-only, own location only) | |
| GET | `/employees/{id}/device-enrollments` | A | |
| POST | `/employees/{id}/device-enrollments` | A | body: device_id, device_user_id |
| DELETE | `/employees/{id}/device-enrollments/{enrollment_id}` | A | |
| GET | `/employees/{id}/shift-assignments` | A | |
| POST | `/employees/{id}/shift-assignments` | A | |
| PUT/DELETE | `/employees/{id}/shift-assignments/{assignment_id}` | A | |

### 4.5 Shift schedules
| Method | Path | Roles |
|---|---|---|
| GET | `/shift-schedules?location_id=` | A |
| POST | `/shift-schedules` | A |
| GET/PUT/DELETE | `/shift-schedules/{id}` | A |
| PUT | `/shift-schedules/{id}/days` | A — bulk replace all `shift_schedule_days` + nested `shift_break_windows` for the schedule in one call |

### 4.6 Attendance
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/attendance/logs?employee_id=&device_id=&date_from=&date_to=&unresolved_only=&page=` | A | raw punch viewer, incl. unresolved (unmapped) punches |
| PATCH | `/attendance/logs/{id}/resolve` | A | manually assign an unresolved punch to an employee (also creates the missing `employee_device_enrollments` row for future punches) |
| GET | `/attendance/daily-status?employee_id=&location_id=&date_from=&date_to=&page=` | A, M (M own location only) | |
| POST | `/attendance/recompute` | A | body: date_from, date_to, optional employee_id — re-runs nightly logic synchronously for the given range (e.g. after a late leave approval) |

### 4.7 Leave
| Method | Path | Roles |
|---|---|---|
| GET | `/leave-types` | A, M |
| POST/PUT | `/leave-types` / `/leave-types/{id}` | A |
| GET | `/leave-records?employee_id=&location_id=&status=&page=` | A, M (M own location only) |
| POST | `/leave-records` | A |
| PATCH | `/leave-records/{id}/approve` | A, M (M own location only) |
| PATCH | `/leave-records/{id}/reject` | A, M (M own location only) |
| DELETE | `/leave-records/{id}` | A — only while `status = pending` |

### 4.8 Config (penalty / overtime / absence rule)
| Method | Path | Roles |
|---|---|---|
| GET/POST | `/config/penalty` | A |
| GET/PUT | `/config/penalty/{id}` | A |
| GET/POST | `/config/overtime` | A |
| GET/PUT | `/config/overtime/{id}` | A |
| GET/POST | `/config/absence-rule` | A |
| GET/PUT | `/config/absence-rule/{id}` | A |

Each `POST` creates a new effective-dated row rather than mutating history in
place, preserving correctness for already-finalized payroll runs.

### 4.9 Payroll
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/payroll/runs?location_id=&year=` | A | |
| POST | `/payroll/runs` | A | body: period_year, period_month, location_id — computes all `payroll_run_lines` from `attendance_daily_status` + `leave_records` + active configs |
| GET | `/payroll/runs/{id}` | A | |
| GET | `/payroll/runs/{id}/lines` | A | |
| GET | `/payroll/runs/{id}/lines/{employee_id}` | A | |
| POST | `/payroll/runs/{id}/lines/{employee_id}/adjustments` | A | manual bonus/deduction |
| POST | `/payroll/runs/{id}/finalize` | A | locks the run, generates PDFs for all lines |
| GET | `/payroll/runs/{id}/lines/{employee_id}/payslip.pdf` | A | streams the generated PDF |

### 4.10 Internal (worker → api only, not reachable from `frontend`)
| Method | Path | Notes |
|---|---|---|
| POST | `/internal/ingest/punches` | Header `X-Internal-Key`. Body: batch of `{device_id, device_user_id, punch_timestamp, raw_status_code}`. Applies dedup constraint, resolves `employee_id` via `employee_device_enrollments`, classifies `punch_type` (Section 5.3). Returns `{inserted, duplicates, unresolved}`. |
| POST | `/internal/process/daily-status` | Header `X-Internal-Key`. Body: `{work_date}`. Runs the nightly computation for all active employees for that date. |
| PATCH | `/internal/devices/{id}/heartbeat` | Header `X-Internal-Key`. Updates `last_synced_at`. |

### 4.11 Reports
Kept intentionally minimal — Discovery leaves report specifics open ("all
reports", structure not detailed). `uiux`/`frontend` compose dashboards from
the data endpoints above (`attendance/daily-status`, `payroll/runs/{id}/lines`,
`leave-records`) with query filters already provided. One aggregate endpoint
is added for the landing dashboard, since it can't be derived client-side
without N+1 calls:

| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/reports/dashboard-summary?location_id=&date=` | A, M | today's present/late/absent counts, pending leave request count (scoped to manager's assigned location for M) |

---

## 5. Sync & Nightly Processing — Design Decisions

These are specified explicitly so `backend` does not have to guess at
ZKTeco-specific behavior.

### 5.1 Polling & dedup
`worker` calls `pyzk`'s `get_attendance()` per active device every
`SYNC_INTERVAL_SECONDS` (default 300). K40 devices retain punch logs
on-device until explicitly cleared, so **every poll re-reads the full
on-device log** (Phase 1 will not clear device logs, to avoid data loss risk).
This makes deduplication mandatory on every sync, not just a one-time
concern — enforced by the DB constraint in `attendance_logs`
(`UNIQUE(device_id, device_user_id, punch_timestamp, raw_status_code)`), with
the ingestion endpoint using an upsert-or-skip (`ON CONFLICT DO NOTHING`)
pattern so re-syncing the same log is a cheap no-op.

### 5.2 Unresolved punches
If `device_user_id` has no matching `employee_device_enrollments` row, the
punch is still stored (`employee_id = NULL`) rather than discarded, and
surfaced in `/attendance/logs?unresolved_only=true` for HR to resolve. This
prevents silent data loss when a new employee is enrolled on the device
before being entered into chronos.

### 5.3 Punch classification (`raw_status_code` → `punch_type`)
ZKTeco's standard status codes (where firmware provides them): `0` =
check-in, `1` = check-out, `2` = break-out, `3` = break-in, `4` = overtime-in,
`5` = overtime-out. K40 base firmware is known to be inconsistent about
populating this beyond `0`/`1`. Classification logic (implemented in `api`'s
ingestion handler, not `worker`, so it can be corrected/replayed without
re-syncing):
1. If `raw_status_code` is one of the well-defined break codes (2/3), map
   directly to `check_out_break`/`check_in_break`.
2. Otherwise, classify by comparing `punch_timestamp` against the employee's
   `shift_schedule_days`/`shift_break_windows` for that date: a punch falling
   inside a configured break window → break punch; otherwise → work punch.
3. Within each category (work/break), the first chronological punch of the
   day is `check_in_*`, alternating punches thereafter. Odd-numbered
   occurrences = check-in, even = check-out.
4. If no shift schedule is assigned to the employee for that date, the punch
   is stored with `punch_type = unclassified` and excluded from lateness/OT
   calculation until an admin assigns a schedule and triggers `/attendance/recompute`.

### 5.4 Nightly daily-status computation
For each active employee, for the target date:
1. Resolve the effective `shift_schedule` via `employee_shift_assignments`.
2. If not a working day per the schedule → `status = not_scheduled`, skip.
3. If an approved `leave_records` row covers the date → `status = on_leave`.
4. Else, pull that day's classified `attendance_logs` for the employee.
   - No work punches at all → `status = absent`, deduction computed from the
     active `absence_rule_config` row for the employee's location.
   - Has punches → compute `late_minutes` (first work check-in vs.
     `scheduled_start` + `grace_minutes_late`), `early_departure_minutes`
     (last work check-out vs. `scheduled_end`), `overtime_minutes` (time
     beyond `scheduled_end` + configured overtime threshold), `break_minutes_taken`
     (sum of break check-in/out pairs) → `status = present` or `late`.
5. Upsert into `attendance_daily_status`, incrementing `recompute_version` if
   a row already existed for that `(employee_id, work_date)`.

This same routine backs both the nightly scheduled job and the manual
`POST /attendance/recompute` endpoint — one implementation, two triggers.

### 5.5 Multi-vendor device support (2026-09-16, client-directed)

Originally single-vendor (ZKTeco K40 only, per Section 5.1 above and the
Stack Defaults note "Device integration requires `pyzk`"). The client wants
chronos to be a product that works with more than one device — the next
real unit is a **Hikvision DS-K1T804BEF**, which does not speak the ZKTeco
protocol at all (HTTP-based ISAPI, not `pyzk`'s binary TCP 4370 protocol).

**Adapter pattern**: `worker/worker/adapters/` holds one module per vendor
(`zkteco.py` — the original `pyzk` logic, moved unchanged; `hikvision.py` —
new), each exposing a `poll(device: dict) -> list[dict]` function returning
punches shaped for `/internal/ingest/punches`. `worker/worker/sync.py`
dispatches on `devices.device_type` (`'zkteco' | 'hikvision'`, CHECK
constraint — extend this set, not the sync dispatch logic, when adding a
third vendor). `api`'s `POST /devices/{id}/test-connection` dispatches the
same way, for its own separate one-off synchronous check (Section 4.3
already documents that endpoint as an `api`→device exception to the
"`worker` polls, `api` doesn't talk to devices" rule).

**Schema changes**: `devices.ip_address` widened from Postgres `INET` to
plain `TEXT` — Hikvision's cloud/DDNS reachability (no static LAN IP
required) means this field may hold a hostname, which `INET` rejects.
`devices.device_type`, `devices.auth_username`, `devices.auth_password`
added (the latter two only meaningful for HTTP/ISAPI-style vendors that need
credentials — ZKTeco/`pyzk` doesn't). `auth_password` is never returned by
the admin-facing `DeviceOut`/`GET /devices`; only the internal
worker-facing `InternalDeviceOut`/`GET /internal/devices` includes it
(shared-secret protected, not frontend-reachable — same trust boundary as
the rest of Section 4.10).

**Classification**: Hikvision's ISAPI events arrive pre-classified
(`attendanceStatus`: `checkIn`/`checkOut`/`breakIn`/`breakOut`/...) —
unlike ZKTeco's bare numeric `raw_status_code`, which Section 5.3's
heuristic has to *infer* a classification from. Rather than force every
vendor through that heuristic, `attendance_logs.punch_type_hint` was added:
when a vendor adapter sets it, `services/classify.py` trusts it directly
and skips the alternating-parity/break-window inference entirely for that
punch. `null` (ZKTeco, and any future vendor that doesn't self-classify)
falls through to the existing Section 5.3 logic, unchanged.

**Timestamps**: Hikvision's ISAPI events carry their own UTC offset
(`"2026-09-16T08:00:00+02:00"`), so unlike ZKTeco's naive device-local
timestamps (Section 2.2's `DEVICE_TIMEZONE` env var workaround), no
timezone guessing is needed for this vendor.

**Connectivity — both transports built (client-directed, 2026-09-16).** The
Hikvision device has cloud + DDNS remote access ("connect from anywhere, no
VPN, no public IP needed"), and rather than pick one path, both are
supported as separate `device_type` values, chosen per device:

| `device_type` | Transport | Depends on | Adapter |
|---|---|---|---|
| `hikvision` | Direct HTTP/ISAPI to the device's own address (LAN IP **or** DDNS hostname) | device + router + DDNS provider | `adapters/hikvision.py` |
| `hikvision_cloud` | Hik-Connect Open Platform — the device is reached through Hikvision's cloud | Hikvision's platform staying up | `adapters/hikvision_cloud.py` |

Both normalize to the identical punch shape, so ingestion, classification,
and payroll are transport-agnostic — switching a device between them is a
config change on the device record, not a code change.

For `hikvision_cloud`, existing device columns are reused rather than
adding cloud-only ones: `ip_address`/`port` hold the *cloud API* host/port
(e.g. `open.hik-connect.com:443`), `auth_username`/`auth_password` hold the
Open Platform appKey/appSecret, and `serial_number` (already on the model,
and now also exposed on `InternalDeviceOut` for `worker`) identifies which
device to pull events for — the cloud API addresses devices by serial, not
by network address, so it is **required** for this type and validated in
the device form.

**Verification status.** Neither Hikvision path has been exercised against
real hardware/credentials — no DS-K1T804BEF unit and no Hik-Connect
developer account were available at implementation time. The direct
adapter's ISAPI shapes follow the documented protocol. For the cloud
adapter, the token exchange (`/api/lapp/token/get`, `{"code":"200",
"data":{"accessToken":...}}`) is the stable, well-documented part; the
**event-search path and its response field names are the unverified
surface** and are isolated as module-level constants
(`EVENT_PATH`, the `_to_punch` parser) so confirming them against the
client's actual account tier is a one-place change. That adapter
deliberately raises on an unrecognized event shape rather than returning
zero punches silently — a loud per-device error (and the resulting
stale-device alert) beats an attendance system that quietly records
nothing or, worse, guesses check-in vs. check-out wrong and corrupts
payroll. Both paths need a real-device pass before go-live.

**Not yet verified against real hardware** — no Hikvision unit was
available during this implementation; the ISAPI request/response shapes in
`worker/worker/adapters/hikvision.py` are built from the documented ISAPI
protocol, not tested against a physical DS-K1T804BEF. Flag for real-device
verification before go-live on that device.

### 5.5 Monthly payroll computation
`POST /payroll/runs` aggregates, per employee, all `attendance_daily_status`
rows in the period against the *active* `penalty_config`/`overtime_config`/
`absence_rule_config` rows whose `[effective_from, effective_to)` covers each
individual day (not just "whatever config is active today") — so a
mid-month rate change is applied correctly to each day. Leave days reduce the
absence count and are split into `paid_leave_days`/`unpaid_leave_days` via
`leave_types.is_paid`. Result is written as `draft` `payroll_run_lines`; HR
may add `payroll_adjustments` before finalizing. `POST /finalize` locks the
run (no further edits) and generates one PDF per line via a Jinja2 HTML
template rendered through WeasyPrint (Section 7).

---

## 6. Auth Model

### 6.1 Mechanism
- Plain username/password login (Discovery Section 9: confirmed sufficient
  for Phase 1, LAN-only, no 2FA/IP-allowlisting requirement).
- Passwords hashed with bcrypt (`passlib`).
- On successful login, `api` issues a single JWT (HS256, secret from env var
  `JWT_SECRET`), containing `user_id` and `role`, expiry **8 hours**, set as
  an `httpOnly`, `SameSite=Lax` cookie. No refresh token.
- **Deviation from `CLAUDE.md` default** (15-min access + httpOnly refresh
  cookie): justified because (a) the deployment is LAN-only with no public
  internet exposure in Phase 1, (b) the user base is a handful of HR/Manager
  accounts, not the general public, (c) refresh-token rotation adds
  meaningful backend complexity (rotation storage, revocation) for zero
  measurable security gain on an isolated network, violating CLAUDE.md's own
  "Simplicity First" principle. **Must be revisited before Phase 2** if any
  location gains internet-facing exposure (VPN or otherwise) — flagged here
  so it isn't forgotten.
- Logout clears the cookie client-side; since there's no refresh token there
  is nothing server-side to revoke (accepted tradeoff of the no-refresh
  design — a stolen cookie remains valid until its 8-hour expiry).

### 6.2 Authorization
Two roles only (Discovery Section 3 — employee self-service explicitly
deferred):
- `hr_admin`: full access to all endpoints in Section 4.
- `manager`: read-only access to attendance/leave for everyone at their
  **assigned location** (`users.location_id`), regardless of direct-report
  relationship. Managers may approve/reject leave for that location (Discovery
  Section 3) but cannot edit employees, configs, devices, or run payroll.

**Scoping rule — CHANGED 2026-08-22 (client-directed, confirmed via
orchestrator; supersedes the original team-based rule this section shipped
with):**

- Manager visibility is now **location-based**, not team-based: every
  list/detail endpoint scoped to a manager filters `WHERE employees.location_id
  = :current_user.location_id` at the query level (not just hidden in the UI)
  — enforced in `api`, not trusted to `frontend`.
- This *replaces* the prior rule, which filtered on `employees.manager_user_id
  = :current_user_id` (a direct-report relationship). That column
  (`employees.manager_user_id`) **still exists in the schema and is still
  populated** — it is retained purely for display purposes (e.g. showing "reports
  to X" on the employee detail page) and **no longer participates in any
  access-control check, anywhere.** Do not use it in a `WHERE` clause for
  scoping purposes going forward.
- **Transition behavior — intended, not a bug:** a `manager` user whose
  `users.location_id` is `NULL` (e.g. every existing manager row immediately
  after the migration below runs, until HR assigns them a location) matches
  no `employees.location_id` value and therefore sees an empty result set on
  every scoped endpoint — not an error, not all-employees, not their old
  team. This is the correct fail-closed behavior: absence of an assigned
  location means absence of access, matching `DESIGN_SPEC.md` §0 Principle 4
  ("absence of access is communicated by absence of the control"). HR
  restores a manager's visibility by setting their `location_id` via the
  existing Users CRUD screen (`/settings/users` — Section 9; no new page
  needed, see Section 6.4).

### 6.3 Manager-Scoping Enforcement Checklist (for `backend` agent)
The following are the **exact, exhaustive** call-sites in the current
codebase that filter on the old `employees.manager_user_id == user.id` /
`!= user.id` rule and **must** be changed to `Employee.location_id ==
user.location_id` (or `!=`, for the negated view-guards). This list is the
definition of "done" for this change at the backend level — every one of
these must be updated, and no others should be (this is a scoping change,
not a refactor).

Verified directly against the current code (`grep -n "manager_user_id"
backend/app/routers/*.py`): **8 distinct predicates**, not 9 — noting this
discrepancy explicitly rather than papering over it, per the file/line
locations supplied, which do match the code exactly:

| # | File | Line | Context |
|---|---|---|---|
| 1 | `backend/app/routers/attendance.py` | 109 | `list_daily_status` — daily-status list, manager branch |
| 2 | `backend/app/routers/leave.py` | 36 | `_assert_manager_can_view` — leave record detail view-guard |
| 3 | `backend/app/routers/leave.py` | 86 | `list_leave_records` — leave list scoping |
| 4 | `backend/app/routers/leave.py` | 177 | `_approve_reject` — approve/reject view-guard |
| 5 | `backend/app/routers/employees.py` | 55 | `_assert_manager_can_view` — employee detail view-guard |
| 6 | `backend/app/routers/employees.py` | 71 | `list_employees` — employee list scoping |
| 7 | `backend/app/routers/reports.py` | 32 | `dashboard_summary` — attendance-status query, manager branch |
| 8 | `backend/app/routers/reports.py` | 33 | `dashboard_summary` — leave query, manager branch |

Each change is mechanical: replace the filter predicate
`Employee.manager_user_id == user.id` (or `!= user.id`) with
`Employee.location_id == user.location_id` (or `!=`). Do not change anything
else in these functions (query structure, other filters, pagination,
serialization) — this is a single-predicate swap per call-site, not a
rewrite. `backend` should re-grep `manager_user_id` in
`backend/app/routers/*.py` after the change and confirm zero remaining
`==`/`!=` comparisons against `user.id` (the only legitimate remaining
matches should be the `manager_user_id` column definition/writes elsewhere,
e.g. in `employees.py` create/update payload handling, which are unaffected
by this change).

### 6.4 Data & Schema Changes Required (for `backend` agent)
- **Model:** `backend/app/models.py` — add `location_id` to the `User` class
  (around line 66), following the exact pattern already used on
  `Device`/`Employee`/`ShiftSchedule`:
  `location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"),
  nullable=True)`, plus a `location: Mapped["Location | None"] =
  relationship()` attribute, matching `Device.location`.
- **Migration:** new Alembic migration adding a nullable `location_id` column
  (FK → `locations.id`) to `users`. No backfill/default needed — existing rows
  get `NULL`, which is the correct starting state per the transition-behavior
  note in Section 6.2 (existing managers see nothing until HR assigns a
  location; this is intended). No column is dropped — `employees.manager_user_id`
  is untouched by this migration.
- **Schemas (`backend/app/schemas.py`):** add `location_id: int | None = None`
  to `AppUserCreate` and `AppUserUpdate` (and to `AppUserOut`, so the field is
  readable in the Users list/detail response — currently at lines ~547–572).
  No new endpoint is needed: this is a new field on the existing `POST /users`
  / `PUT /users/{id}` (or equivalent, per `backend/app/routers/users.py`)
  request/response bodies.

### 6.5 Manager Operational Access + Opt-In Payroll Access (2026-08-24, client-directed)

Supersedes the "cannot edit employees, configs, devices, or run payroll" line
in Section 6.2 for the operational half — Section 6.2's payroll/config
restriction still stands by default, and is now an explicit opt-in rather
than an absolute rule.

- **Operational access — default for every manager:** a `manager` may now
  create/update Employees, Shift Schedules, and Devices (including nested
  device-enrollments and employee-shift-assignments), scoped to their own
  `users.location_id`. Enforced via `require_manager_or_admin` (role gate)
  plus `assert_location_access(user, location_id)` (per-endpoint location
  guard) in `backend/app/deps.py`. Admin is unrestricted, as before. A
  manager with no assigned location matches nothing (fail-closed, same
  transition behavior as Section 6.2).
- **Payroll/config access — still admin-only by default:** Payroll runs and
  Penalty/Overtime/Absence-rule config remain gated behind
  `require_payroll_access`, which admin always passes and a manager only
  passes if `users.can_manage_payroll` is `true`. This is deliberately kept
  separate from the operational grant above — a manager setting their own
  team's pay policy is a conflict-of-interest risk regardless of location
  scoping, so it requires an explicit per-manager Admin decision, not a
  blanket role capability. A flagged manager is still scoped to their own
  location by the same `assert_location_access` check (cannot touch another
  location's payroll even with the flag).
- **Schema:** `users.can_manage_payroll` (`boolean`, `not null`, default
  `false`) — migration `0005_manager_payroll_access`. Set via the existing
  Users CRUD screen (`/settings/users`) — a toggle visible only when editing
  a `manager` row, admin-only to change.
- **Leave-types config and Locations CRUD are unaffected** — still
  admin-only (not part of the payroll/config opt-in; not requested as
  operational either).

---

## 7. Third-Party Integrations & Key Dependencies

| Concern | Choice | Notes |
|---|---|---|
| Device protocol | `pyzk` | TCP 4370, per Discovery |
| ORM / migrations | SQLAlchemy 2.x + Alembic | |
| API schema validation | Pydantic v2 | |
| Password hashing | `passlib[bcrypt]` | |
| JWT | `python-jose` or `PyJWT` | either is fine; `backend` picks one |
| Scheduler (in `worker`) | `APScheduler` | cron-style nightly trigger + interval sync polling |
| PDF payslip generation | `WeasyPrint` (HTML/CSS + Jinja2 template → PDF) | Chosen over ReportLab for easier bilingual (Albanian/English) template maintenance — payslip layout as HTML/CSS is far easier for a non-engineer to later restyle than ReportLab's imperative drawing API. Requires system packages (Pango, Cairo, GDK-Pixbuf) in the `api` Docker image — must be included in the `api` Dockerfile's base image or `apt-get install` step. |
| Frontend build tool | Vite | React + TypeScript template |
| Frontend i18n | `react-i18next` | Albanian default locale, English toggle, per Discovery Section 9 |
| Frontend styling | Tailwind CSS | per CLAUDE.md default, retained |
| Internal service auth | Shared secret (`INTERNAL_API_KEY` env var, header `X-Internal-Key`) | defense-in-depth on top of Docker network isolation between `worker` and `api` |

No other third-party/external services in Phase 1 (no email provider, no
payment gateway, no cloud storage — payslips are stored on a local volume and
downloaded/printed per Discovery Section 9).

---

## 8. Deployment (Phase 1)

Docker Compose, 4 services (`db`, `api`, `worker`, `frontend`), all on the
client's on-site PC, LAN-only, no reverse proxy/TLS required for Phase 1
(internal LAN traffic only — if the client's IT later wants HTTPS even on
LAN, that's a `devops`-phase decision, not blocking here).

Environment variables (`.env`, not committed):
`POSTGRES_*`, `JWT_SECRET`, `INTERNAL_API_KEY`, `SYNC_INTERVAL_SECONDS`.

Volumes: `db` data volume (persistent), `api` payslip-storage volume
(persistent, holds generated PDFs referenced by `payroll_run_lines.payslip_pdf_path`).

Startup order: `db` → (Alembic migration + seed, one-shot) → `api` → `worker`,
`frontend` (both depend on `api` being healthy).

---

## 9. Frontend Route Inventory

Route list only — visual hierarchy, component breakdown, and mobile rules are
`uiux`'s responsibility (`DESIGN_SPEC.md`). Roles: `A` = hr_admin, `M` = manager.

| Route | Purpose | Roles |
|---|---|---|
| `/login` | Username/password login | public |
| `/` | Dashboard: today's attendance summary, pending leave count | A, M (scoped) |
| `/employees` | Paginated, searchable/filterable employee list | A |
| `/employees/new` | Create employee | A |
| `/employees/:id` | Employee detail: profile, device enrollments, shift assignment history, attendance history | A, M (own location, read-only) |
| `/employees/:id/edit` | Edit employee | A |
| `/shift-schedules` | List shift schedules | A |
| `/shift-schedules/new` | Create schedule (days + break windows) | A |
| `/shift-schedules/:id/edit` | Edit schedule | A |
| `/devices` | Device list + connection status | A |
| `/devices/new` | Register device | A |
| `/devices/:id` | Device detail: test connection, manual sync trigger, last-synced timestamp | A |
| `/locations` | Location list (single row in Phase 1; full CRUD screen present for Phase 2 readiness) | A |
| `/attendance` | Daily status browser (filter by date range/employee) | A, M (own location) |
| `/attendance/logs` | Raw punch log viewer, incl. unresolved-punch resolution | A |
| `/leave` | Leave request list | A, M (own location; M sees approve/reject actions) |
| `/leave/new` | HR creates a leave request on behalf of an employee (no self-service) | A |
| `/leave/:id` | Leave request detail | A, M (own location) |
| `/payroll/runs` | List payroll runs by period | A |
| `/payroll/runs/new` | Trigger a new run for a period | A |
| `/payroll/runs/:id` | Run detail: per-employee lines, adjustments, finalize action | A |
| `/payroll/runs/:id/employees/:employeeId` | Line detail + payslip PDF download/preview | A |
| `/config/penalties` | Manage `penalty_config` | A |
| `/config/overtime` | Manage `overtime_config` | A |
| `/config/absence-rule` | Manage `absence_rule_config` | A |
| `/config/leave-types` | Manage `leave_types` | A |
| `/settings/users` | Manage HR/Manager login accounts | A |
| `/settings/profile` | Change own password, language toggle | A, M |

---

## 10. Explicitly Unresolved — Must Remain DB-Configurable, Not Hardcoded

Carried forward from `DISCOVERY.md` Section 10–11. Nothing below blocks
`uiux`/`frontend`/`backend` from building — each already has a config table
and admin-facing route (Section 9) to enter final values once the client
confirms them. Flagging again here so no downstream agent hardcodes a
placeholder value into logic:

- **Absence rule default** (Section 3.13 / 5.4): Phase 1 ships with one seed
  row in `absence_rule_config` (`no_punch_no_leave`, full-day deduction).
  This is a *default*, not a confirmed client policy — must stay editable via
  `/config/absence-rule`, never inlined into payroll calculation code.
- **Grace period, break paid/unpaid, standard hours per shift**: live on
  `shift_schedules` / `shift_schedule_days` / `shift_break_windows` — set per
  schedule via `/shift-schedules`, no global constant.
- **Penalty structure** (flat vs. threshold/allowance, early-departure
  handling): both structures supported by `penalty_config`'s `rule_type`
  column; final rate values entered via `/config/penalties`.
- **Overtime structure** (daily vs. weekly threshold, weekend/holiday rate,
  pre-approval requirement, monthly cap): all columns exist on
  `overtime_config`; final values via `/config/overtime`.
- **Leave types, entitlements, approval flow**: `leave_types` table +
  `/config/leave-types`; approval flow is the fixed Manager
  approve/reject action already specified (Section 4.7) — only the type list
  and entitlement numbers are open.
- **Payroll run date, additional pay components**: `payroll_runs` can be
  triggered for any period on demand (no fixed calendar-day cron requirement
  built in for Phase 1 — HR triggers it manually via `/payroll/runs/new`);
  ad-hoc components handled via `payroll_adjustments` until/unless the client
  specifies a fixed recurring component structure.
- **Pilot employee headcount and start date** (Discovery Section 11): no
  schema or UI limit assumes a specific count — pagination throughout
  (Section 4). No fixed start date is assumed anywhere in the schema (all
  date-driven logic is period/range-parameterized, not anchored to a
  hardcoded calendar date). This is an operational-scheduling concern only,
  not a blocker for `uiux`/`frontend`/`backend`.

---

## 11. Out of Scope for Phase 1 (confirmed, not to be built)

- Employee self-service portal (personal attendance/payslip view/login).
- Email delivery of payslips.
- Multi-location aggregation UI, hub-and-spoke ingestion, agent heartbeat
  alerting UI (schema fields like `devices.last_synced_at` are seeded now,
  but no alerting logic/UI ships in Phase 1).
- 2FA, IP allowlisting, refresh-token rotation (see Section 6.1).
- ZKTeco Cloud/ADMS integration, VPN, Raspberry Pi agents (Phase 2 fallback
  options — design-aware only, not built now).
