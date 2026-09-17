# FRONTEND_NOTES.md — chronos Frontend

Status: build verified (`npm run build` — `tsc -b && vite build` — completes
with zero errors; `npm run lint` passes with only non-blocking style warnings;
`npm run dev` boots and serves the app). Input: `BLUEPRINT.md` +
`DESIGN_SPEC.md`, both present and used as the sole source of UI truth.

This document tells the `backend` subagent exactly what contract the frontend
already assumes, and flags every place the frontend had to make a judgment
call because `BLUEPRINT.md`/`DESIGN_SPEC.md` didn't fully specify something.

---

## 1. What was built

Resumed a killed frontend run. The scaffold (Vite + React 19 + TypeScript,
Tailwind config with the exact DESIGN_SPEC §1 palette/type scale/spacing/
radii/shadows, `src/api/{client,endpoints,types}.ts`, `src/auth/*`,
`src/i18n/index.ts`, `src/lib/format.ts`, `Button.tsx`) was left in place
untouched except where noted in §4. Everything else was built from scratch:

- **i18n**: `src/i18n/locales/en.json` and `sq.json` were empty (`{}`) —
  filled in with the full bilingual string set for every page/component,
  Albanian default per BLUEPRINT §9. Where DESIGN_SPEC gave an exact Albanian
  string (e.g. login error, delete-device warning, finalize-payroll warning,
  resolve-punch toast, absence-rule seed banner), that exact string was used
  verbatim. All other Albanian copy is a professional-register translation I
  produced, not client-reviewed — **flag for a native-speaker review pass
  before go-live**, per DESIGN_SPEC Principle 6.
- **28 components** (`src/components/ui/*`, plus `ShiftDayGrid.tsx` and
  `AttendanceStatusTable.tsx`/`EffectiveDatedTable.tsx` as shared
  page-composition helpers) — all variants/states from DESIGN_SPEC §6:
  Button (6 variants incl. an added `success-outline`, see §3 below), Input
  incl. Currency/Search variants, Select incl. Searchable + a Multi-select
  (added, see §3), Textarea, Checkbox, Toggle, Radio Group, Badge with every
  status-color table (attendance/leave/employment/payroll/punch-type/role),
  Status Dot, Table/DataGrid with loading skeleton + empty state (with/without
  active filters) + mobile card-list conversion per the §6.10 table inventory,
  Pagination, Filter Bar (incl. mobile bottom Drawer), Card/KPI Card, Modal +
  Confirmation Dialog, Toast (4 variants, correct auto-dismiss rules), Tabs,
  Breadcrumb, Language Switcher (compact + large), Avatar (deterministic
  6-color hash), Empty State, File Download Button, Form Section + form/field
  error banners, Skeleton, Drawer (nav + filter), Shift Day Grid.
- **App shell**: role-scoped Sidebar (collapsible, `localStorage`-persisted,
  mobile off-canvas drawer), sticky Topbar (breadcrumb/title, language
  switcher, user menu with role badge), all per DESIGN_SPEC §2.
- **All 26 routes** from BLUEPRINT §9 / DESIGN_SPEC §5, wired into
  `src/App.tsx` using the existing `ProtectedRoute`/`RoleRoute`, role-gated
  exactly per the two nav trees in DESIGN_SPEC §2.2. Added `/403` (already
  referenced by DESIGN_SPEC §5.4) and a catch-all `*` → `NotFound` page (not
  in the spec — see §3, judgment call).
- **Mobile rules** (DESIGN_SPEC §4): breakpoint behavior implemented via
  Tailwind responsive classes throughout (sidebar drawer <1024px, filter bar
  → bottom drawer <640px, table → card list <640px per the §6.10 inventory,
  touch-target sizing left at component defaults which already meet 40px on
  `md`/`lg` buttons — `sm` buttons are 32px and are not used in any
  <1024px-only surface).
- All pages call the **real documented endpoints** in `src/api/endpoints.ts`
  — no mock data anywhere. Backend does not exist yet; that's expected.

## 2. API contract the backend must honor (read from `src/api/*`, not redefined here)

The frontend was built strictly against the existing
`src/api/{types.ts,endpoints.ts,client.ts}` files (written by the earlier
frontend pass, left untouched). Key points backend must match exactly:

- Base path `/api/v1`, overridable via `VITE_API_BASE_URL` at build time;
  defaults to a relative path assuming nginx proxies `/api` to the `api`
  service (per BLUEPRINT §2.4/§8).
- **Auth**: `POST /auth/login` sets an httpOnly, `SameSite=Lax` cookie
  (BLUEPRINT §6.1 — single JWT, 8h expiry, no refresh token). The frontend
  **never reads the token**; every request is sent with `credentials:
  'include'` and the frontend always calls `GET /auth/me` after login to
  learn `{id, username, role, employee_id, is_active, last_login_at}`. Logout
  is `POST /auth/logout` (clears cookie server-side).
- All list endpoints are expected to return `{items, page, page_size, total,
  total_pages}` (the `Paginated<T>` shape) — this matches BLUEPRINT §4's
  pagination requirement. Exceptions the frontend already assumes are
  **non-paginated arrays**: `/locations`, `/devices`, `/shift-schedules`,
  `/leave-types`, `/payroll/runs`, `/config/penalty|overtime|absence-rule`
  (all small, admin-managed lists per BLUEPRINT — confirm this is acceptable
  or backend must paginate and frontend will need a follow-up patch).
- Error bodies: frontend reads `detail` or `message` string fields for toast/
  banner display (`ApiError` in `client.ts`). Field-level validation errors
  are not parsed structurally anywhere yet (see §3, gap).
- Currency values are always plain numbers (euros, decimal) over the wire;
  all formatting (`€ X.XXX,XX`) happens client-side via `formatCurrency` —
  backend should **not** pre-format currency strings.
- Dates: `date` fields as `YYYY-MM-DD`, `datetime`/`timestamptz` fields as
  ISO 8601 strings — `formatDate`/`formatDateTime`/`formatTime` in
  `src/lib/format.ts` parse with `new Date(value)`.

## 3. Gaps in BLUEPRINT/DESIGN_SPEC — judgment calls made, flagged for review

These were not blocking (each has a reasonable, documented resolution below),
but backend/PM should confirm rather than assume the frontend guessed right:

1. **`PATCH` endpoint for `is_absence_excused`** — BLUEPRINT §4.6 doesn't list
   a write route for this field, but DESIGN_SPEC §5.12 requires HR to toggle
   it inline on the Attendance Daily Status table. Frontend calls `PATCH
   /attendance/daily-status/{id}/excused` (marked `ASSUMED` in
   `endpoints.ts`, pre-existing from the earlier pass). Backend must
   implement this exact path/verb or the frontend needs a follow-up patch.
2. **`GET /leave-records/{id}`** — not explicitly listed in BLUEPRINT §4.7 but
   required by DESIGN_SPEC §5.16 (`/leave/:id` detail page). Frontend calls
   `GET /leave-records/{id}` (marked `ASSUMED`, pre-existing).
3. **`/users` CRUD resource** — BLUEPRINT §4 has no Users section at all, but
   DESIGN_SPEC §5.23 requires a full `/settings/users` management page.
   Frontend calls `GET/POST /users`, `PATCH /users/{id}`, `PATCH
   /users/{id}/reset-password` (marked `ASSUMED`, pre-existing). Backend must
   add this resource.
4. **Manager's employee filter dropdowns** — DESIGN_SPEC §5.12 requires an
   "Employee Select (searchable; for M, options pre-filtered to their team
   server-side)" on the Attendance page, and similarly on Leave/Attendance
   Logs. But BLUEPRINT §4.4 scopes `GET /employees` to role `A` only — there
   is no documented endpoint a Manager can call to populate this dropdown
   with their own team's names. **Frontend currently calls `employeesApi.list()`
   for this regardless of role** and silently falls back to an empty option
   list if the call 403s. **Backend must either**: (a) relax `GET /employees`
   to allow `M` with server-side team-scoping (consistent with how
   `/attendance/daily-status` and `/leave-records` are already scoped for
   `M` per BLUEPRINT §6.2), or (b) add a dedicated scoped endpoint. Until
   resolved, Managers will see an empty Employee filter option list (the rest
   of the page — the actual scoped attendance/leave rows — still works,
   since those endpoints are correctly scoped per BLUEPRINT).
5. **Device `is_active` — no documented UI control to deactivate a device.**
   DESIGN_SPEC §5.10 says the Edit modal has "the same form fields as
   `/devices/new`" (Label, Location, IP, Port, Serial — no toggle), yet the
   device list/detail pages display an Active/Inactive status dot driven by
   `devices.is_active`. Frontend does not expose a way to flip this field
   from the UI (only Delete exists as a destructive action). Flagging rather
   than inventing a toggle DESIGN_SPEC didn't ask for.
6. **`success-outline` Button variant** — DESIGN_SPEC §6.1's variant table
   only lists Primary/Secondary/Ghost/Danger/Danger-outline/Link, but §6.18
   explicitly requires "Approve leave uses a success-outline Confirm button."
   Added a `success-outline` variant to `Button.tsx`, deriving hover/active/
   disabled states from the same pattern as `danger-outline` using the
   success color tokens (not explicitly specified). Used only for the
   Approve-leave confirm action and the `/leave/:id` page's inline Approve
   button, per §6.18's exact wording.
7. **Payroll run detail "Total Penalties" / "Total Bonuses" stat blocks**
   (DESIGN_SPEC §5.19) — no formula given. Implemented as
   `sum(total_lateness_penalty_eur)` and `sum(total_overtime_bonus_eur)`
   across the run's lines respectively (i.e. **excluding** absence
   deductions and manual `payroll_adjustments` from these two summary
   numbers). This is a reasonable reading but not spec-confirmed — flag for
   product sign-off if absence deductions should roll into "Total Penalties."
8. **Catch-all 404 route** — not in BLUEPRINT's route table or DESIGN_SPEC's
   page inventory. Added a minimal `NotFound` page (same visual treatment as
   the `/403` Forbidden page) purely so an unmatched URL doesn't render a
   blank screen. Zero business logic, not a new feature.
9. **Field-level validation error mapping from API responses** — DESIGN_SPEC
   §6.26 describes both field-level and form-level error banners, and forms
   render both, but there's no documented shape for how the API reports
   *which field* failed validation (e.g. a Pydantic 422 body). Frontend
   currently treats **all** non-2xx form-submit errors as a single form-level
   banner (`FormErrorBanner`) using the response's `detail`/`message` string;
   it does not attempt to map structured field errors onto individual inputs
   (e.g. the "Employee Code must be unique" error would show generically at
   the top of the form, not under the Employee Code field, except for the
   one case DESIGN_SPEC explicitly calls out: the payroll-run 409 duplicate-
   period error, §5.18, which **is** mapped to the Location field
   specifically). If backend returns a structured field-error format, a
   follow-up frontend patch can route it per-field.
10. **IANA timezone list source** (`/locations` timezone Select, DESIGN_SPEC
    §5.11) — spec says "IANA list" without specifying a source. Used the
    browser's built-in `Intl.supportedValuesOf('timeZone')` (full IANA
    database, zero bundle cost) with a small hardcoded fallback array for
    older browsers. No backend dependency.

## 4. Pre-existing files touched (surgical, minimal)

- `src/index.css`: reordered `@import` (Inter font) above `@tailwind`
  directives — CSS spec requires `@import` to precede other statements;
  Vite's PostCSS build emitted a warning (not a hard failure) with the
  original order. Purely a reorder, no content change.
- `src/components/ui/Button.tsx`: added the `success-outline` variant (see
  §3.6 above). No existing variant's classes were changed.
- `src/components/ui/Table.tsx`: added an optional `rowClassName` prop
  (used only by the effective-dated config tables, §5.21's "current row
  highlighted, history rows in muted text" requirement) and an optional
  `footer` prop (used to embed the Pagination component inside the same
  bordered/rounded card the table renders in, matching §6.11 "bottom of the
  table card"). Both are additive, non-breaking.
- `src/components/ui/Select.tsx`: added a `MultiSelect` export (used only by
  the Attendance Status filter, §5.12 — "Status Select (multi: ...)"; not a
  named component in §6, but required by the page spec). Additive only.
- `src/App.tsx`, `src/main.tsx`: fully rewritten (were still the unmodified
  Vite template — `App.tsx` imported nonexistent asset files and would not
  have built).

Everything else under `src/` besides the explicitly-listed pre-existing files
was newly authored for this phase.

## 5. Not built / explicitly out of scope (matches BLUEPRINT §11)

No employee self-service portal, no email delivery UI, no multi-location
aggregation/heartbeat-alerting UI, no 2FA/IP-allowlisting UI — none of these
are referenced anywhere in the frontend, consistent with BLUEPRINT §11.

## 6. Environment

`VITE_API_BASE_URL` — optional build-time env var, defaults to `/api/v1`
(relative). Set it if the `api` service isn't reachable via an nginx `/api`
proxy in front of the `frontend` static build.

## 7. Revision 2 restyle pass (2026-08-22)

Implemented `DESIGN_SPEC.md` Revision 2 (§1.1, §1.2, new §1.9) across the
existing codebase. Value-only/token-level restyle — no routes, data logic,
API calls, or component structure changed beyond what the new tokens
required. Build verified clean (`npm run build`, `npm run lint`, and
`docker compose up -d --build frontend`, all pass with zero errors).

- **§1.1 Palette**: `tailwind.config.js` `primary`/`violet` token hex values
  swapped to muted cobalt / dusty plum (keys unchanged, cascades everywhere).
  One spot needed a manual fix because it wasn't a Tailwind class:
  `components/ui/Avatar.tsx`'s hardcoded 6-color hash array had the *old*
  primary-500/violet-500 hex literals — updated to the new hex values.
  `index.css`'s hardcoded `:focus-visible` outline color (`#2563EB`) also
  updated to the new primary-600 (`#3D5A76`).
- **§1.2 Typography**: added `font-mono` (JetBrains Mono, weights 400/500,
  loaded via `@fontsource/jetbrains-mono` following the exact pattern Inter
  already uses in `index.css`) and applied it to every field on the
  Monospace Usage list (timestamps, `employee_code`, device IP:Port/Serial
  Number, Raw Status Code, all `formatCurrency()` output, minute/day
  counters, the 4 dashboard KPI figures, payroll summary stat blocks) across
  every page that renders them. Added a shared `components/ui/CodeChip.tsx`
  for the 4 identifier fields' chip treatment (used in Employees, Devices,
  Attendance Logs list/detail pages). Added `tracking-tight`/reduced
  line-height to `text-page-title`/`text-section-title`/`text-kpi` only, per
  spec's table, in `tailwind.config.js`.
- **§1.9 Micro-interactions**: `Button.tsx` — `active:scale-[0.98]` +
  `background-color 150ms / transform 100ms` transitions on
  Primary/Secondary/Danger/Danger-outline/success-outline only (Ghost/Link
  untouched). `Input.tsx`/`Select.tsx`/`Textarea.tsx` — replaced the halo-
  style `focus:ring-2 .../20` with the crisp doubled-line ring
  (`border-color` + flush `ring-1`, danger-500 variant on error); also fixed
  two raw `<input>` elements outside the shared components that had the same
  old halo pattern (`ShiftDayGrid.tsx`'s 4 time inputs, `FilterBar.tsx`'s
  Date Range inputs) and the `LeaveTypesConfigPage.tsx` inline-editable
  Annual Entitlement number field. `Badge.tsx`'s `StatusDot` resized
  8px→6px. `Modal.tsx` — added the `Esc` keycap hint (covers
  `ConfirmDialog` too, since it's built on `Modal`).
- **Judgment calls / gaps flagged, not fixed** (restyle scope only, no
  structural changes made):
  - §6.9/§5.8 call for a Status Dot + label on the Devices list/detail
    "Active" status; the existing (pre-Revision-2) implementation uses
    `ActiveBadge` there instead, with `StatusDot` currently unused anywhere
    in the app. Left as-is — wiring it in would be a component-usage change
    beyond a value-only restyle; the `StatusDot` component itself is fixed
    to the new 6px size for whenever it is adopted.
  - The Monospace Usage list (§1.2) doesn't explicitly name "Absence Days",
    "Paid Leave (days)", "Unpaid Leave (days)" on the payroll run line
    table, only the adjacent Late/Overtime minute columns in the same row.
    Applied `font-mono` to all of them for visual consistency within one
    table row — flagging in case that's over-scope.
  - The "Finalized on dd.MM.yyyy by [name]" caption (§1.2 item 1's own
    example) required wrapping only the date substring in `font-mono`
    without changing the translated sentence. Solved via `react-i18next`'s
    `Trans` component, which required adding a `<date>…</date>` markup tag
    around the existing `{{date}}` placeholder in both `en.json`/`sq.json`
    (`payroll.finalizedOn`) — no wording changed in either language, only
    markup added for the component mapping.

## 8. Revision 3 — location-based manager scoping (2026-08-22)

Implemented `DESIGN_SPEC.md` Revision 3 (§2.2, §5.23) against the now-live
backend change adding `location_id`/`location_name` to the `User` resource.
Copy-only + one new form field; no routing/logic changes. Build verified
clean (`tsc -b && vite build`, `oxlint`, and a live check against
`docker compose up -d --build frontend` — logged in as `admin`/`manager1` via
the same nginx `/api/` proxy path the SPA uses, confirmed `GET /users`
returns `location_id`/`location_name` and that `PATCH /users/{id}` 400s on
an invalid `location_id` and 200s with the field echoed back on a valid one).

- **`src/api/types.ts`**: `AppUser` gained `location_id: number | null` and
  `location_name?: string | null`, matching the pattern every other scoped
  resource (`Employee`, `Device`, `PenaltyConfig`, etc.) already uses.
- **`src/api/endpoints.ts`**: `usersApi.create`'s body type and
  `usersApi.update`'s `Partial<Pick<AppUser, ...>>` both gained
  `location_id`.
- **`src/pages/settings/UsersPage.tsx`** (§5.23):
  - New "Location" table column: plain location name for a manager with one
    assigned, a `bg-warning-100 text-warning-700` "Unassigned"/"Pa Caktuar"
    `Badge` when a manager's `location_id` is null, `—` for `hr_admin` rows.
  - Mobile card subtitle updated per §6.10's table inventory row for Users
    (`Location` for managers, `Linked Employee` for `hr_admin`).
  - New "Assigned Location" `Select` in the create/edit Modal, populated from
    `locationsApi.list()` (same call pattern as `EmployeeListPage.tsx`),
    conditionally rendered only when `form.role === 'manager'` using the
    same ternary/conditional-render pattern already established in
    `PenaltiesConfigPage.tsx`'s Rule Type field (no existing role-conditional
    field was actually present in this form to copy — `Linked Employee` is
    unconditional in the current codebase — so I matched the closest real
    precedent instead).
  - Visually required (asterisk) but **not** hard-blocked: added a new
    `requiredMark?: boolean` prop to the shared `Select` component
    (`src/components/ui/Select.tsx`) that renders the red-asterisk label
    styling without wiring the native HTML5 `required` attribute — needed
    because every existing usage of `required` on `Select` *does* rely on
    native browser validation to hard-block submit (`DeviceFormPage`,
    `EmployeeFormPage`, `PayrollRunNewPage`, etc.), so reusing that prop here
    would have silently made this field submission-blocking, contradicting
    §5.23's explicit "does not hard-block Save" requirement. When the field
    is empty, a non-blocking `text-caption text-warning-600` caption renders
    underneath with the spec's exact copy.
  - Switching Role away from Manager clears `location_id` from form state
    immediately (not just at submit); switching Role to Manager away from
    the create-default also leaves it empty (not pre-filled), per spec.
    Submit additionally re-derives `location_id` from the current role as a
    second guard so an `hr_admin` payload can never carry a stale value.
- **Nav relabel (§2.2)**: Manager sidebar labels for Attendance/Leave
  changed from "My Team"/"Ekipi Im" to "My Location"/"Lokacioni Im". I kept
  the i18n key names as-is (`nav.myTeamAttendance`, `nav.myTeamLeave`) and
  only changed the translated string values — lower-risk than a rename since
  no other file references these keys by name. Also updated the two
  manager-only page-header titles that reused "My Team" wording outside the
  nav (`attendance.myTeamTitle` → "My Location — Attendance", `leave
  .myTeamTitle` → "My Location — Leave"), same key-preserved approach.
- **Copy audit (§5.4/§5.12/§5.14/§5.16)**: grepped the whole `src/` tree
  (case-insensitive) for "team" after the above changes — no other
  user-facing string, empty-state message, or scoping-description copy
  referenced "team"; `Dashboard.tsx` and `EmployeeDetailPage.tsx` never had
  team-wording to begin with. Nothing else needed changing.
