# DISCOVERY.md — chronos: Attendance & Payroll Management System

Status: **FINAL** — ready for `architect` handoff.

## 1. Project Overview

Full-stack attendance and payroll management system for a Kosovo-based client
operating ZKTeco K40 biometric terminals. The system records employee work and
break check-ins/check-outs from the terminals, applies configurable
euro-denominated penalties (lateness) and bonuses (overtime), and automatically
computes monthly payroll per employee from base salary, lateness, absences,
leave, and overtime.

Rollout is phased:
- **Phase 1 (this engagement's build target):** single-location pilot, 1 month.
- **Phase 2 (design-aware only, not built now):** scale to 14 locations,
  hub-and-spoke architecture, all reporting to one central system.

## 2. Business Context

- Client: Kosovo-based, multi-location business (14 locations at full rollout).
- Currency: EUR.
- Devices: ZKTeco K40 biometric terminals (fingerprint), proprietary protocol
  on TCP port 4370, integrated via `pyzk`.
- Pricing anchor: ~EUR 4,500 total, milestone-based (30% upfront / 40% working
  demo / 30% delivery). Phase 1 is priced/prioritized now; Phase 2 commercial
  terms TBD later.
- Delivery structure: Milestone 1 = pilot (single location, full attendance
  sync + payroll calc, validated over one real payroll cycle). Milestone 2 =
  rollout to remaining 13 locations, in batches of 3–4.

## 3. Users / Roles (Phase 1)

| Role | Access |
|---|---|
| HR/Admin | Full access: employee management, rule configuration (penalty/overtime rates), payroll runs, all reports. |
| Manager | Approve/reject leave requests; view attendance for own team only. |
| Employee self-service | **Explicitly out of scope for Phase 1** — confirmed future phase (personal attendance/payslip portal). |

## 4. Functional Requirements — Phase 1 Pilot Scope

1. Record work check-in / check-out per employee via K40 device punches.
2. Record break check-in / check-out per employee via K40 device punches.
3. HR/Admin can configure euro-denominated lateness penalties (structure TBD,
   see Section 10 — must be configurable, not hardcoded).
4. HR/Admin can configure euro-denominated overtime bonuses (structure TBD,
   see Section 10 — must be configurable, not hardcoded).
5. HR/Admin manages payroll per individual employee (base salary, adjustments).
6. System automatically computes monthly payroll per employee from: base
   salary, lateness, absences, leave/vacation, overtime — using the
   configured rules.
7. Manager leave-approval workflow feeds into daily attendance processing and
   monthly payroll calculation.
8. Nightly batch job processes raw punches into per-employee daily status
   (late minutes, absent, overtime minutes), evaluated against each
   employee's assigned shift schedule (see Section 5 — shift model varies per
   employee/group, not a single fixed shift).
9. Monthly payroll run produces a payslip (PDF) per employee, HR-downloaded
   and/or printed. No email delivery in Phase 1 (confirmed — Section 9).
10. Device sync must be resilient to duplicate punches (deduplication is a
    named acceptance criterion for the pilot).
11. HR/Admin manages shift schedules and assigns them to employees/groups
    (confirmed — shifts vary, see Section 5).
12. Device/employee mapping must support multiple devices per location from
    day one, even though the pilot site has exactly one device (confirmed —
    Section 9), to avoid a Phase 2 schema retrofit.

## 5. Data Model — Baseline (subject to `architect` refinement)

- `employees`
- `devices` — device/employee association designed for many-to-many-capable
  reality: a location can have multiple devices, and an employee's punches
  are resolved by device-enrolled user ID → employee, not by a hardcoded
  single-device assumption. Pilot deployment happens to have exactly one
  device, but the schema/sync logic must not assume that.
- `locations` (`location_id` included in schema from day one, even though
  Phase 1 is single-location, specifically to avoid a Phase 2 retrofit)
- `shift_schedules` — **new entity, confirmed required for Phase 1.**
  Employees/groups have differing shift schedules (start/end time, break
  window(s), applicable days) — not a single fixed shift for all staff. Each
  employee is assigned a shift schedule, which the nightly processing job
  uses as the basis for computing late/absent/overtime minutes.
- `attendance_logs` — raw punches: user_id, timestamp, punch type (work
  in/out, break in/out), device_id; deduplicated on ingest
- `attendance_daily_status` — processed per-employee daily result: late
  minutes, absent flag, overtime minutes (computed relative to the
  employee's assigned `shift_schedule`)
- `leave_records` — leave type, dates, approval status, approved_by
- `penalty_config` — euro amount/rate for lateness (values TBD with client,
  structure must be admin-configurable)
- `overtime_config` — euro/hour rate for overtime; threshold basis
  (daily/weekly) TBD, must be admin-configurable
- `payroll_runs` — monthly calculated result per employee: base, penalties,
  bonuses, net pay

## 6. System Flow

**Daily:** employee punches device → device stores log locally → sync
mechanism pulls new punches → raw punches written to `attendance_logs`
(deduplicated) → nightly job computes daily status (late/absent/overtime
minutes) per employee, evaluated against that employee's assigned shift
schedule, using configured rules.

**Monthly:** daily statuses + approved leave records + penalty/overtime
config → payroll run → net salary per employee → PDF payslip generated,
available to HR for download/print.

**Leave approval (side flow):** employee/HR submits leave request → manager
approves/rejects → result feeds daily processing and payroll calculation.

## 7. Tech Stack (fixed — client/architect direction, overrides project
CLAUDE.md stack defaults; justification: all-Python backend avoids a
cross-language sync layer for device integration, `pyzk` is the most mature
open-source option for ZKTeco K40 communication)

- Backend: Python, FastAPI
- Frontend: React (bilingual UI — Albanian default, English available; see
  Section 9)
- Database: PostgreSQL
- Migrations: Alembic
- Device integration: `pyzk`, TCP port 4370
- Containerization: Docker / Docker Compose

`architect` should record this override explicitly in `BLUEPRINT.md` per
project CLAUDE.md ("Stack Defaults" section) — this is a deviation from the
default Next.js/Node/Prisma stack and must be justified there, not silently
substituted.

## 8. Deployment Plan

### Phase 1 — single-location pilot
- Docker Compose stack on the client's existing on-site PC on the office LAN:
  FastAPI backend + PostgreSQL + React frontend + sync worker (confirmed —
  client supplies/maintains the host machine, no separate hardware
  procurement in scope).
- Sync worker connects directly to the K40 via `pyzk` — no agent, cloud, or
  VPN required for Phase 1.
- HR/managers access the web app over LAN via the host machine's local IP,
  authenticated with plain username/password login (confirmed sufficient for
  Phase 1 — no 2FA/IP-allowlisting requirement at this stage).
- No internet dependency for daily operation; no email delivery of payslips
  in Phase 1 (HR download/print only).
- Sync logic built as an isolated/relocatable module — intentionally seeded
  for reuse as the Phase 2 agent.
- `location_id` present in schema now to avoid retrofit later.
- One K40 device at the pilot site currently, but device/employee mapping and
  sync logic must support multiple devices without rework (confirmed).

**Pilot success criteria (from client brief):**
- Device sync validated — no duplicated punches.
- At least one full real payroll cycle run end-to-end with no manual
  corrections needed.
- HR using the UI daily, surfacing gaps before Phase 2 scaling begins.

### Phase 2 — 14-location rollout (design-aware only, not built in this
engagement)
- Hub-and-spoke: all locations report to central, never to each other.
- Investigate ZKTeco Cloud Server Setting / ADMS (device push to remote
  server, zero extra hardware) before building custom agents.
- Fallback options, in order of preference: (a) local agent on existing
  on-site hardware — `pyzk` + local SQLite queue + HTTPS push, outbound only;
  (b) VPN through existing router; (c) dedicated cheap hardware (Raspberry
  Pi) where no existing PC/VPN.
- Explicitly avoid: port-forwarding devices to the public internet, and
  direct agent-to-central-DB writes.
- Central ingestion API validates and dedupes before writing to DB.
- Rollout in batches of 3–4 locations.
- `last_synced_at` heartbeat monitoring with stale-sync alerting.
- Agent updates via scheduled pull + restart — no manual per-site access.

## 9. Confirmed Decisions

- Tech stack as listed in Section 7 (client-directed override of default
  stack).
- Roles limited to HR/Admin and Manager for Phase 1; employee self-service is
  explicitly deferred.
- UI is bilingual, **Albanian default**, English available.
- Shift model **varies by employee/group** — a `shift_schedules` entity is
  required in Phase 1 (not a single fixed shift for all staff).
- Device/employee mapping designed to support **multiple devices per
  location** from day one, even though the pilot has exactly one device now.
- Pilot host machine: **client's existing PC** — no hardware procurement in
  this engagement's scope.
- Payslip delivery: **HR download/print only** in Phase 1 — no email
  delivery.
- LAN access security: **plain username/password login** is sufficient for
  Phase 1 (no 2FA / IP allowlisting requirement).
- `location_id` and `device_id` present in schema from Phase 1 onward.
- Payslips generated as PDF.
- Penalties and bonuses are euro-denominated and must be admin-configurable
  (no hardcoded rule values), because exact rules are not yet finalized with
  the end client.
- Budget/pricing anchor and milestone split as stated in Section 2.

## 10. Open Questions — Unresolved but Configurable (business-rule values;
NOT blocking architecture, because the system is required to expose these as
admin-editable configuration rather than hardcoded constants; final numbers
to be supplied by the client before go-live and entered via the config UI)

- Standard work hours per shift schedule, break duration, whether breaks are
  paid, and grace period before a punch counts as "late" (per shift
  schedule, since shifts vary — see Section 5/9).
- Penalty structure: flat euro rate per late-minute vs. threshold/allowance
  before penalty applies; how early departure is handled.
- Overtime: daily vs. weekly threshold basis; flat vs. weekend/holiday
  differentiated rate; whether overtime requires pre-approval; monthly cap.
- Leave types, annual entitlement per type, approval flow detail, and
  unexcused-absence deduction rules.
- **Default absence rule (client has no strong opinion yet — explicitly
  unresolved):** proposed Phase 1 default is "no punch recorded on a
  scheduled workday, and no approved leave covering that date, = unexcused
  absence." This is being implemented as a **default, admin-tunable rule**,
  not a final client-approved policy. Must remain editable via
  `penalty_config`/absence-rule configuration, not hardcoded as a fixed
  business rule.
- Payroll: fixed monthly run date, any additional pay components (bonuses,
  contributions/social security), payslip template/branding, and any
  accounting-system integration requirement.

These will be built as first-class admin-configurable settings
(`penalty_config`, `overtime_config`, `shift_schedules`, leave-type table,
etc.) so the client can adjust them without a code change once final numbers
are agreed. They do not need to be resolved before `architect` proceeds,
since the requirement is "support configurable X," not "hardcode value X."

## 11. Open Questions — Scale & Timeline (explicitly unresolved; do not
assume a specific value — architecture and UI must not hardcode or design
around an assumed employee count or start date)

- **Pilot employee count: unknown.** Client has not yet confirmed headcount
  at the pilot location. `architect` and `frontend` must design for a
  reasonable small-to-mid business range (not a hardcoded fixed count) —
  e.g., paginated employee lists, no assumptions baked into schema or UI
  limits.
- **Pilot start date: unknown / device not yet on-site.** The K40 device for
  the pilot location has not been procured/installed yet, so the 1-month
  pilot clock has not started. Build and delivery planning should not assume
  a fixed calendar start date; the "1 month" pilot duration begins once the
  device is on-site and the system is deployed to the client's host PC.

Both items are recorded here as explicitly TBD with the client and must be
revisited (headcount confirmed, start date set) before the pilot's real
payroll cycle can be scheduled — this does not block `architect` from
producing `BLUEPRINT.md`, since neither affects the technical approach, only
operational scheduling and data volume assumptions (which should already be
handled generically, not hardcoded).

## 12. Timeline & Budget

- Phase 1 pilot duration: 1 month, start date TBC — pending device
  procurement/installation and confirmed employee headcount (see Section 11).
- Budget anchor: ~EUR 4,500 total (both phases), milestone payments 30% /
  40% / 30%.
- Phase 2 scope, timeline, and pricing: deferred, design-aware planning only.

---

PROJECT READY FOR DEVELOPMENT
