# QA_REPORT.md — chronos

Date: 2026-09-16
Status: **Test suite passes — 133 passed, 1 xfail, 0 failures.**
**2 bugs found (1 fixed here, 1 handed to `debug`). 2 test-suite defects
fixed. No regression found in any SECURITY_REPORT.md Revision 3 patch.**

This pass had two assigned jobs:

1. **Verify the Revision 3 security patches did not break legitimate use.**
   Result: all 10 patched findings re-verified against the live stack. Every
   legitimate flow still works, including the ones the patches sit directly
   on top of (device create/edit for all three vendors, punch ingestion,
   payroll, config edits, device enrolment, LAN access after the loopback
   rebinding). **Zero functional regressions attributable to the security
   pass.**
2. **Fix the rotted test suite and extend it to the multi-vendor work.**
   Result: the suite went from 24 collected / 5 failing / broken teardown to
   **134 collected, 133 passing, 1 xfail** (the xfail is an open app bug,
   documented below).

Input reviewed: `BLUEPRINT.md` (Section 5.5 multi-vendor architecture),
`DESIGN_SPEC.md` (Sections 2.2, 5.1–5.24), `SECURITY_REPORT.md` Revision 3
(findings 31–40 plus R1–R4), and direct source review of every file the
security pass touched.

Method: no mocks on any integration path. Everything below was exercised
against the running `docker compose` stack over real HTTP — `pytest` against
`api` on `127.0.0.1:8000`, plus `docker compose exec` for DB state and for
the bootstrap/teardown of throwaway accounts. The only tests that do not go
over the network are the vendor adapters' pure parsing functions, and even
their paging caps are driven by a real HTTP server rather than a transport
mock (see Section 3.2). All test data is namespaced with a random
per-session suffix and removed afterwards; cleanup was verified empty after
two consecutive full runs (Section 7).

---

## 1. Headline results

| | Before this pass | After |
|---|---|---|
| Tests collected | 24 | **134** |
| Passing | 18 (+1 teardown error) | **133** |
| Failing | 5 | **0** |
| xfail (tracked open bug) | 0 | 1 |
| Test files | 1 | 3 |
| Runtime (full suite) | ~8s | ~40s |

```
$ cd backend && pytest tests/ -q
........................................................................ [ 53%]
...................................................x..........           [100%]
133 passed, 1 xfailed in 39.87s
```

Run twice back-to-back to prove repeatability and clean teardown: identical
result both times.

---

## 2. Bugs found

### 2.1 [FIXED HERE] Location-specific pay configs were silently ignored

**`backend/app/services/config_lookup.py:24`** (pre-existing; not caused by
the security pass).

`get_effective_config()` documents, in its own module docstring, that it
prefers "a location-specific row over a `location_id=NULL` ('applies to all
locations') row". It did the opposite:

```python
.order_by(
    (model.location_id == location_id).desc(),   # <-- the defect
    model.effective_from.desc(),
)
```

For an org-wide row, `location_id = :loc` evaluates to **NULL**, not false —
and Postgres orders `DESC` as **NULLS FIRST**. So the org-wide row sorted
ahead of the location-specific one and won.

Impact: whenever an org-wide penalty / overtime / absence-rule config is in
effect on the same date as a location-specific one, **the location-specific
rule is discarded** and every employee at that location is paid on the
org-wide rule. This runs in both `services/recompute.py` (nightly and live
recompute) and `services/payroll_calc.py` (payroll run construction), i.e. it
changes money.

Reproduced directly against the live DB before fixing:

```
PICKED id=11 location_id=None flat=5.00     # org-wide row won
[(11, None, None), (28, 1, True)]           # ORDER BY put the NULL first
```

**Why it surfaced now:** the suite's fixture week was hard-coded to
`2026-08-10`, which predates the seeded org-wide config's `effective_from`
of `2026-08-24` — so the two rows never competed and the bug stayed hidden.
Making the fixture relative to "now" (job 2) put them in contention
immediately.

**Fix applied** — order on `IS NULL`, which yields a real boolean instead of
NULL:

```python
.order_by(
    model.location_id.is_(None),      # false (location-specific) sorts first
    model.effective_from.desc(),
)
```

`api` image rebuilt and restarted. Regression test:
`backend/tests/test_devices_multivendor.py::test_location_specific_config_beats_org_wide_config`
— it plants a competing org-wide row so the assertion cannot pass by
default.

**For `debug`:** this is the one production behaviour change QA made. It is
one line, and it makes the code match its own documented contract, but it
does move payroll numbers for any location that has both a location-specific
and an org-wide config. Worth a confirming look, and worth checking whether
any already-finalized payroll run was computed under the old ordering.

### 2.2 [OPEN — handed to `debug`] Bulk import 500s on a non-UTF-8 upload

**`backend/app/services/bulk_import.py:35`**

```python
def _parse_csv_rows(raw_bytes: bytes):
    raw = raw_bytes.decode("utf-8-sig")     # <-- unguarded
```

A file whose bytes are not valid UTF-8 raises `UnicodeDecodeError`, which is
unhandled and returns **HTTP 500**. Confirmed live:

```
POST /employees/bulk-import   file=b"\xff\xfe\x00\x00binary garbage"
-> 500 Internal Server Error
```

```
$ docker compose exec -T api python -c "...(_parse_csv_rows(b'\xff\xfe...'))"
UnicodeDecodeError 'utf-8' codec can't decode byte 0xff in position 0
```

The `.xlsx` branch 40 lines below (`bulk_import.py:76-80`) already wraps its
parse and returns a clean `400 "Could not read Excel file: ..."`. The CSV
branch is simply missing the equivalent guard. Affects both
`/employees/bulk-import` and `/leave-records/bulk-import`.

Severity: low — admin-only endpoint, no data corruption, no DoS (the 10 MB
cap still applies first). But it is an unhandled server error at a system
boundary, and the fix is the same three lines already present next to it.

Tracked by `backend/tests/test_qa_smoke.py::test_bulk_import_of_undecodable_bytes_is_not_a_500`,
marked `xfail(strict=False)` with the file:line in the reason string. **Delete
the marker when fixed** — it will report `XPASS` in the meantime.

### 2.3 [OBSERVATION — for `debug`] Manual sync of an unreachable ZKTeco device reports the wrong cause

`POST /devices/{id}/sync` on an unreachable ZKTeco device returns:

```
502 {"detail":"Could not reach sync worker: timed out"}
```

...which blames the `worker` service. The worker is healthy; it just took
longer than the caller's budget. Measured inside the worker container:

```
zkteco.poll({'ip_address':'10.0.0.170','port':4370})
raised ZKNetworkError timed out
elapsed 28.4s
```

`backend/app/routers/devices.py:229` gives the worker `timeout=30`, and
`worker/worker/adapters/zkteco.py:26` passes pyzk `timeout=10` — but pyzk
retries internally, so wall time is ~28s and the round trip exceeds 30s. The
worker log shows it completing correctly a moment later:

```
ERROR:worker.sync:Failed to poll device 113 (...): timed out
```

Both Hikvision transports return the correct `202 {"error": "..."}` shape,
so this is ZKTeco-path-specific and **pre-existing** — neither the timeout
nor pyzk's behaviour was touched by Revision 3. Not a blocker; an operator
diagnosing a dead terminal is told to look at the wrong service.

---

## 3. Test-suite defects fixed (job 2)

### 3.1 The teardown had been silently failing for weeks

`backend/tests/conftest.py` deleted leave types with
`DELETE FROM leave_types WHERE name LIKE ...`, but migration
`0007_leave_type_bilingual_name` replaced `name` with `name_en`/`name_sq`.
That statement threw `UndefinedColumn`, which **aborted the whole teardown
transaction** — so none of the 20 preceding `DELETE`s committed either. Every
suite run since that migration left its entire world behind. Confirmed: the
baseline run's locations, employees, devices, managers, shift schedules and
configs were all still in the database afterwards.

Fixed (`name_en`), and the leftovers from the aborted runs were removed.
Additional teardown gaps closed at the same time:

- `attendance_logs` and `employee_device_enrollments` are now also deleted
  **by device**, not only by employee — the new `punch_type_hint` tests
  deliberately ingest punches for unenrolled `device_user_id`s, which land
  with `employee_id IS NULL` and were unreachable through the employee-keyed
  deletes (and would then block the `devices` delete on its FK).
- `absence_rule_config` added.

### 3.2 The fixture could fail after creating its account and never clean up

`admin_client` created the throwaway admin, then asserted on the login
*before* `yield`. When that assert failed, the teardown after `yield` never
ran and the account was orphaned with no suffix left to find it by — which
is exactly what happened during this pass (see 3.4). Login + yield are now
wrapped in `try/finally`.

### 3.3 Hard-coded fixture week replaced with a relative one

`world["monday"]` was `date(2026, 8, 10)`. Today is 2026-09-16, so that week
had aged out of the `days=30` window that `/reports/alerts` queries with, and
two date-relative tests failed. Replaced with
`conftest._recent_complete_work_week(today)`, which returns the Monday of the
most recent Mon–Fri that is **both** entirely in the past **and** entirely
inside one calendar month:

- fully elapsed, because the fixture asserts on a finished week (Wednesday
  absence, Friday early departure);
- single month, because the payroll assertions build one run for that
  month and expect the whole week's totals in it.

Result is never more than 20 days old, so it stays inside the 30-day alerts
window permanently. `test_alerts_sorted_newest_first_by_date` was likewise
re-anchored to two *working* days either side of it (`monday - 7`,
`monday + 3`) — its old `monday + 10` offset would now land in the future.

### 3.4 A latent flake in the login test

`test_login_rejects_bad_password` used the fixed username
`nonexistent_user_xyz`. `auth.py` rate-limits **per account** (5 attempts /
15 min, in-process), so the 6th suite run inside that window got `429` instead
of `401`. Hit this for real during the pass. Now uses a per-run username.

The same throttle also bit the new JWT tests: they logged in before
`admin_client` had created the account, burning that account's budget and
locking out the fixture's own login (which is how 3.2's orphan happened).
They now depend on `admin_client` and reuse its cookie. The throttle itself
now has explicit coverage
(`test_repeated_failed_logins_are_rate_limited`, on a dedicated account).

### 3.5 Schema drift in the assertions

- `leave_types.name` → `name_en` + `name_sq` (migration 0007) in three
  places, including the dashboard's `on_leave_employees` entry, which now
  carries `leave_type_name_en` / `leave_type_name_sq`.
- `users.can_manage_payroll` (dropped in migration 0008):
  `test_manager_payroll_access_requires_opt_in_flag` was rewritten as
  `test_manager_payroll_and_config_access_by_role_scoped_to_location`. It
  asserts the *current* model — the field is absent from `/auth/me`
  entirely, and a manager reaches payroll and config by role alone, still
  row-scoped to their own location.

### 3.6 `world` moved to `conftest.py`

The session-scoped world fixture lived in `test_qa_smoke.py`, so the new
modules could not use it. Moved to `conftest.py` (along with
`INTERNAL_API_KEY`) so all three files share one world and one teardown.
No assertions changed in the move; `test_qa_smoke.py` re-verified green
immediately afterwards.

---

## 4. Security-patch re-verification (job 1)

Every Revision 3 finding, checked for *both* halves: the attack is still
blocked, **and** the legitimate flow still works. All automated unless noted.

| # | Patch | Attack still blocked | Legitimate use still works |
|---|---|---|---|
| 31 | Re-supply password on retarget | `PUT` changing `ip_address` / `port` / `device_type` without `auth_password` → `400`, row unchanged (3 parametrized cases) | Retarget **with** password → `200`; rename / `is_active` / `serial_number` edits need no password; resubmitting the *same* address is not treated as a retarget; a device with no stored password retargets freely |
| 31 | Cloud host allowlist | Create and update to `attacker.example.com` → `400`; flipping a LAN device to `hikvision_cloud` while pointed elsewhere → `400` | `open.hik-connect.com` and `isgpopen.ezvizlife.com` → `200` |
| 31 | Forced TLS on cloud | `_base_url()` is `https://` for ports 80/443/8080 | — |
| 32 | Bare-host validation | `host/PATH?q=1#`, `http://…`, `user:pw@…`, `10.0.0.1:99`, whitespace → `422`; ports 0 / 65536 / −1 → `422` | `10.0.0.150`, `192.168.1.20`, DNS names, IPv6 literals all accepted; RFC1918 explicitly still allowed |
| 32 | SSRF guard on test-connection | `127.0.0.1`, `localhost`, `169.254.169.254` → `reachable:false, "… is not a permitted device address"` — on the **ZKTeco** path too | A reachable-looking private address still attempts a real connection |
| 32 | Generic error details | No `http://`, `https://`, `/ISAPI/`, `/api/lapp/` or the device address appears in any `test-connection` detail, across all three vendors | Detail still distinguishes failure classes (`"Device rejected the request: HTTP 401"` vs `"Could not connect…"`) |
| 33 | Simulator credential redaction | `GET http://127.0.0.1:8090/api/status` returns only `id`/`location_id`/`location_name`/`label`/`device_type` — **no `auth_password`, no `auth_username`** (manual) | Simulator UI still reachable on loopback (manual) |
| 33 | Simulator loopback binding | Unreachable from the LAN IP (manual) | — |
| 34 | Config location scoping | Manager moving a penalty / overtime / absence config to another location **or** to `location_id: null` → `403 "Not your location"`, row unchanged | Manager creating and editing a config **in their own location** → `200`; admin performing the same cross-location move → `200` |
| 35 | Paging caps | A real always-full-page HTTP server → `RuntimeError "never signalled end of results after 400 pages"` in ~18s instead of looping; oversized single response → `RuntimeError "too large"` | A well-behaved server's 2 events parse and map correctly, and the trailing non-attendance event is skipped rather than choking the poll |
| 36 | `punch_type_hint` device gating | Hint on a `zkteco` device → `400 "does not self-classify punches"`; a mixed batch is rejected **whole** (0 rows written, verified in the DB) | Hint accepted for `hikvision` and `hikvision_cloud`; hintless `zkteco` punch → `200` |
| 36 | Hint value constraint | `"unclassified"` → `422` | The four valid values round-trip |
| 37 | Enrolment device-location check | Manager binding their own employee to another location's device → `403`, and the response does **not** echo that device's label | Same-location enrolment → `201` |
| 37 | Missing-device pre-validation | `device_id: 999999999` → clean `400 "Device not found"` (was a raw FK 500) | — |
| 38 | PyJWT 2.13.0 | Broken signature, empty signature, `alg:none` downgrade, garbage token → all `401` | Real login issues a working `httpOnly`+`SameSite` cookie; `/auth/me` and every scoped endpoint work through it |
| 38 | python-multipart 0.0.31 | — | CSV upload (3 rows, clean per-row errors), **binary `.xlsx` upload** (real OOXML workbook, 1 employee created), 10 MB cap → `413`, unauthenticated → `401` |
| 38 | Versions actually installed | — | Asserted in the *running container*: `PyJWT >= 2.13.0`, `python-multipart >= 0.0.31` |
| 39 | Manager with no location / payroll | Org-wide payroll run planted directly in the DB; location-less manager sees `[]` while admin sees the run | Manager **with** a location still sees their own location's runs |
| 40 | Error-text sanitisation | Platform `msg` truncated to 200 chars and stripped of `\n`/`\r`/`\t`; unmapped `attendanceStatus` truncated; `sync._safe_error()` bounded to 300 printable chars | Live worker sync returns readable, sanitised errors for both Hikvision transports (`"timed out"`, `"[Errno -2] Name or service not known"`) |

### 4.1 Docker rebinding — verified manually

The riskiest change for legitimate use, since it moves where every LAN client
must connect:

```
api                127.0.0.1:8000->8000/tcp
device-simulator   127.0.0.1:8090->8090/tcp
frontend           0.0.0.0:8080->80/tcp
worker             8100/tcp            (unpublished)
db                 5432/tcp            (unpublished)
```

```
http://127.0.0.1:8000/health                      -> 200
http://192.168.0.24:8000/health                   -> 000 (refused, as intended)
http://192.168.0.24:8080/                         -> 200 (SPA)
http://192.168.0.24:8080/api/v1/internal/devices  -> 404 (nginx block holds)
http://127.0.0.1:8100/health                      -> 000 (refused)
worker:8100/health from inside the network        -> 200
```

Full LAN user journey through nginx on `:8080` — the path every real client
now takes — exercised end to end: `login → 204` with an `httpOnly` cookie,
then `/auth/me`, `/employees`, `/reports/dashboard-summary`, `/devices` and
`/payroll/runs` all `200`. **The rebinding did not break LAN access.**

---

## 5. New coverage for the multi-vendor work

Previously zero. Now 96 tests across two new files.

### 5.1 `backend/tests/test_devices_multivendor.py` — 39 tests, live stack

- **All three `device_type` values** round-trip through the real API
  (create → read → list), including `serial_number` and `auth_username` for
  the vendors that use them.
- `device_type` **defaults to `zkteco`** when omitted (pre-multi-vendor
  clients and the existing seed data depend on this).
- An unknown vendor (`"suprema"`) → `422`.
- `auth_password` never appears in `GET /devices`, `GET /devices/{id}`, or
  anywhere in the list response body.
- The finding 31 / 32 / 34 / 36 / 37 invariants in the table above.
- **The feature itself:** `punch_type_hint` bypasses
  `services/classify.py`'s inference. Proven by sending a sequence the
  ZKTeco heuristic would classify *differently* — four punches hinted
  `in, in, out, out`, which alternating parity would turn into
  `in, out, in, out`. They come back exactly as hinted. The contrast case
  (same shape, no hint, ZKTeco device) is asserted to come back alternating,
  so the test proves the hint is doing the work rather than coinciding with
  the heuristic.
- Hint → classification → **daily status**: the hinted first-in/last-out pair
  produces a real `actual_first_in` ≠ `actual_last_out` day, i.e. it reaches
  the values that drive late minutes, overtime and the dashboard.

### 5.2 `backend/tests/test_device_adapters.py` — 57 tests, no DB

Imports `worker/worker/adapters/` directly (the two services share no
package, so `sys.path` is extended to the worker source).

- `_target.safe_host` / `safe_port` / `safe_cloud_host`: URL-rewriting
  payloads, loopback / link-local / unspecified, port ranges, and
  suffix-confusion attempts against the cloud allowlist
  (`hik-connect.com.attacker.example`, `nothik-connect.com` — both rejected).
- `STATUS_MAP` / `RAW_CODE`: the full documented Hikvision vocabulary, the
  `overtimeIn`/`overtimeOut` fold into the work pair, and that the raw codes
  agree with `classify.py`'s ZKTeco break convention (2 = break-out,
  3 = break-in) — a divergence there would silently misclassify a hintless
  replay.
- Both adapters share **the same** `STATUS_MAP`/`RAW_CODE` objects, so the
  two transports cannot drift and classify one device's events differently.
- `_to_punch`: normal event, numeric-`employeeNo` fallback, the alternate
  `eventTime` field, non-attendance events skipped, unrecognised
  `attendanceStatus` **raised** (never guessed — the documented design), and
  its text truncated before it reaches a log.
- `_unwrap`: application-level failure behind HTTP 200, control-character
  stripping, 200-char truncation, the 8 MiB response cap, non-object
  payloads.
- **Paging caps against a real HTTP server** (stdlib `http.server`, bound to
  this machine's own private-LAN address — loopback is refused by the very
  guard under test, which is itself the proof it works). A well-behaved
  device parses correctly; an always-full-page device aborts at 400 pages;
  an oversized body is rejected.
- `sync._ADAPTERS` dispatch for all three vendors, unknown vendor raises,
  and `_safe_error` bounding.

---

## 6. `DESIGN_SPEC.md` functional conformance

Checked functionally (pixels are `debug`'s remit).

**All 24 routes in `DESIGN_SPEC.md` Sections 5.1–5.24 exist** in
`frontend/src/App.tsx` with matching paths and role guards, plus one addition
(`/alerts`) that post-dates the spec and is backed by `/reports/alerts`.

The frontend has kept up with the schema changes that broke the tests — no
stale references remain:

- `can_manage_payroll`: **zero** references anywhere in `frontend/src`.
- Leave types are bilingual (`src/lib/leaveTypes.ts` picks by language,
  `LeaveTypesConfigPage.tsx` edits both fields).
- Devices are multi-vendor: `device_type` is a field on the create and edit
  forms and a column on the list; `auth_username`/`auth_password` are shown
  only for the non-ZKTeco vendors.

One interaction worth recording, because it is where the finding-31 patch
meets the UI: `DeviceDetailPage.tsx:78-83` always submits `ip_address`,
`port` and `device_type` (whole-form PUT) but only submits `auth_password`
when the operator actually typed one. That combination is safe **only**
because the backend compares against the stored value rather than merely
checking whether the key is present — otherwise every device edit would
demand the password. That behaviour is now pinned by
`test_resubmitting_the_same_address_is_not_a_retarget`. When the operator
*does* change the address without a password, the `400` detail is surfaced
through `ApiError` → `showToast('error', …)`, so they are told what to do.

Two places where the spec now lags the build (documentation drift, not
defects — both are the result of later client direction recorded in
`BLUEPRINT.md` / `SECURITY_REPORT.md`):

- Sections 5.8–5.10 mark `/devices` as admin-only; managers have had scoped
  device access since the 2026-08-24 change.
- Section 5.14 describes manager approve/reject on `/leave`; leave types now
  default to `requires_approval: false` and auto-approve on creation. The
  approval workflow still exists and still works for a type that opts into
  it — both paths are covered by tests.

---

## 7. Cleanup verification

After two consecutive full runs:

```
LEFTOVERS: 0
payroll_runs: [(21, 1, 'finalized')]      <- pre-existing, not ours
configs p/o/a: 2 1 1                       <- pre-existing seed rows, unchanged
unresolved logs: 1                         <- pre-existing (device 10, 2026-08-24)
```

Checked `users`, `locations`, `employees`, `devices`, `leave_types` and
`shift_schedules` for anything matching this suite's naming. Nothing
remained. The orphans left behind by the previously-broken teardown
(Section 3.1) and by the fixture crash (Section 3.2) were also removed.

The two temporary rows the new tests plant directly in the DB — the org-wide
payroll run for finding 39 and the org-wide penalty config for the
config-lookup regression — are removed in `finally` blocks.

---

## 8. Handed to `debug`

1. **`backend/app/services/bulk_import.py:35`** — unguarded
   `raw_bytes.decode("utf-8-sig")` → 500 on a non-UTF-8 upload. Fix mirrors
   lines 76-80. Remove the `xfail` marker on
   `test_bulk_import_of_undecodable_bytes_is_not_a_500` when done.
2. **Review `backend/app/services/config_lookup.py:24`** — the one
   production change QA made this pass (Section 2.1). Correct per the
   module's own contract, but it moves payroll numbers wherever a
   location-specific and an org-wide config overlap. Worth checking whether
   any finalized payroll run was computed under the old ordering.
3. **`backend/app/routers/devices.py:229` vs `worker/worker/adapters/zkteco.py:26`**
   — a manual sync of an unreachable ZKTeco device blames the worker
   (`502 "Could not reach sync worker"`) when the worker is fine and the
   device simply took ~28s to time out. Cosmetic but misleading during
   incident diagnosis.
4. **`DESIGN_SPEC.md` Sections 5.8–5.10 and 5.14** lag the current access
   model and leave workflow (Section 6). Documentation drift for `docs` to
   reconcile, not a build defect.

**No blockers.** Nothing found this pass prevents `debug` from proceeding.

---

## 9. Files changed by this pass

| File | Change |
|---|---|
| `backend/app/services/config_lookup.py` | Bug fix (Section 2.1) — the only production change |
| `backend/tests/conftest.py` | Teardown fixes, `try/finally`, `world` + `INTERNAL_API_KEY` moved here |
| `backend/tests/test_qa_smoke.py` | 5 rotted tests fixed, flake fixed, 14 tests added (JWT/cookie, rate limit, dependency pins, payroll finalize + Excel, leave auto-approve, xlsx upload) |
| `backend/tests/test_devices_multivendor.py` | **New** — 39 tests |
| `backend/tests/test_device_adapters.py` | **New** — 57 tests |

`api` image was rebuilt (`docker compose up -d --build api`) to pick up the
`config_lookup.py` fix; the stack is up and healthy.

---
---

# Prior pass (2026-08-25) — reproduced verbatim

Date: 2026-08-25
Status: **Test suite passes (23/23). Zero blockers for `debug`.** One
build-tooling bug found and fixed (Docker build broke if a local dev `.venv`
was present in `backend/`). All 7 recently-changed areas listed in this
pass's task verified against the real running stack; no functional
regressions found.

Input reviewed: `BLUEPRINT.md`, `DESIGN_SPEC.md`, `SECURITY_REPORT.md`, plus
direct source review of every file touched by the batch of changes this pass
was asked to focus on (`backend/app/deps.py`, `backend/app/routers/internal.py`,
`backend/app/routers/reports.py`, `backend/app/routers/leave.py`,
`backend/app/routers/employees.py`, `devices.py`, `shift_schedules.py`,
`payroll.py`, `config.py`, `users.py`, `backend/app/schemas.py`,
`frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ui/Card.tsx`).
This is a follow-up pass on top of the prior QA pass dated 2026-08-23 (see
git-less history: `QA_REPORT.md` timestamps) — that pass's 16 tests and 2
bug fixes (pagination `total` miscount, Alerts bilingual gap) are unaffected
and still pass; this pass adds 7 new tests covering the newer changes without
touching the previous ones.

Method: no mocks. Every flow below was exercised against the real running
Docker Compose stack (`api` at `localhost:8000`, real Postgres) via real HTTP
requests — `pytest` (`backend/tests/test_qa_smoke.py`, extended this pass)
plus direct `docker compose exec` DB inspection for before/after state and
cleanup verification. No real credentials were used or requested; all test
accounts were throwaway, created directly in the DB via
`docker compose exec -T api python -c "..."` (the pattern already established
in `backend/tests/conftest.py`), namespaced with a random per-session suffix,
and torn down automatically at session end.

---

## 1. Automated test suite

**Location:** `backend/tests/test_qa_smoke.py` (extended) +
`backend/tests/conftest.py` (unchanged).

**Result:** `23 passed in ~8.5s` — the 16 tests from the prior pass plus 7
new ones added this pass. Ran twice in a row to confirm idempotency
(self-cleaning namespaced data); confirmed via direct DB query afterward that
only the app's pre-existing seed/demo data remains (`admin`, `manager1`,
`EMP-001`..`EMP-008`, `Main Location`, `Main Entrance` device, `Standard
08:00-16:00` schedule, 3 real leave types) — zero rows matching `%qa%`
anywhere.

**How to run** (unchanged from the prior pass):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```
**Important:** delete `backend/.venv` (or build from a clean checkout) before
running `docker compose build api` — see §2 for why this matters now (a
`.dockerignore` was added this pass specifically so this is no longer a trap,
but it's worth calling out since running the suite is the very thing that
creates the venv).

**New tests added this pass (7):**

| Test | Verifies |
|---|---|
| `test_manager_operational_crud_scoped_to_location` | Manager gets CRUD on employees/devices/shift-schedules (+ nested enrollments/shift-assignments) at their own location; 403 on every one of those at another location |
| `test_admin_unrestricted_across_locations` | Admin unaffected by the new location-scoping additions |
| `test_manager_payroll_access_requires_opt_in_flag` | Manager without `can_manage_payroll` gets 403 on `/payroll/runs` and `/config/penalty` (even for their own location); admin grants the flag via `PATCH /users/{id}`; manager then gets 200, correctly scoped to their own location only; flag revoked afterward restores the 403 baseline |
| `test_admin_payroll_and_config_access_unrestricted` | Admin never needs the flag |
| `test_live_recompute_and_onsite_kpi_update_immediately_on_ingest` | A punch ingested via `/internal/ingest/punches` is reflected in `/attendance/daily-status` and `/reports/dashboard-summary` (`present_today`, `late_today`, `on_site_now`) with no separate recompute call — confirms the fix in `internal.py`'s `ingest_punches`; also confirms `on_site_now` doesn't drop someone to "left" on a break-out punch, and does drop them the instant a real check-out lands |
| `test_alerts_sorted_newest_first_by_date` | `/reports/alerts` items are sorted by `work_date` descending across the whole list, verified with two `missing_checkout` alerts at different dates for the same employee |
| `test_manager_created_leave_and_requires_approval_and_on_leave_kpi` | Manager can create a leave request for their own-location employee (403 for another location's); `requires_approval=true` type lands as `pending`; `requires_approval=false` type auto-approves immediately and is reflected in `/attendance/daily-status` and the dashboard's `on_leave_employees` (name + leave-type "reason" + date range) without a separate approval step; scoped correctly for managers (own location only); deleting the auto-approved record is allowed; deleting an admin-manually-approved record is still blocked (400) |

All 16 tests from the prior pass are unchanged and still pass (see that
pass's write-up below in §7 for their original coverage table, preserved for
history).

---

## 2. Bug found — Docker build breaks if a local `backend/.venv` exists (fixed)

Found while doing this pass's final "rebuild + confirm stack health" step
(the same step §10 of the prior QA_REPORT documents). Running
`docker compose build api` after creating `backend/.venv` (exactly per this
project's own documented convention for running `pytest` — see
`conftest.py`'s docstring, unchanged from the prior pass) failed:
```
ERROR: invalid file request .venv/bin/python
```
**Root cause:** `backend/` had no `.dockerignore`, so the entire `backend/`
directory — including a local `.venv` if one exists — is sent to the Docker
build context. `python -m venv` creates `.venv/bin/python3` as a symlink to
the *absolute host path* `/usr/bin/python3` (outside the build context
entirely), which BuildKit refuses to include in the context tarball at all,
failing the whole build rather than just skipping the file.

This is a real trap for the next person: `conftest.py`'s own "how to run"
instructions tell you to create `backend/.venv`, and nothing warns you to
delete it again before touching Docker — so the most natural sequence
(follow the QA docs to run the tests, then rebuild) breaks the build.

**Fix applied:** added `backend/.dockerignore` excluding `.venv/`, `venv/`,
`__pycache__/`, `*.pyc`, `.pytest_cache/` — mirrors the existing top-level
`.gitignore` entries for the same directories (which git respects but Docker
build context never did, since `.dockerignore` is a separate, Docker-only
mechanism).

**Verified:** recreated `backend/.venv`, ran `docker compose build api` —
succeeded. Removed the venv afterward. Confirmed `docker compose build api
frontend` succeeds cleanly from this state, containers restarted healthy
(`docker compose ps` — all healthy/up), `pytest tests/ -v` re-run against the
freshly rebuilt containers — still 23/23 passing.

**File added:** `backend/.dockerignore`.

---

## 3. Task-specified area verification (all 7, all pass)

### 3.1 Manager operational + opt-in payroll access
`backend/app/deps.py`'s `require_manager_or_admin`, `require_payroll_access`,
`assert_location_access` reviewed line-by-line and confirmed live:
- A manager can `POST`/`PUT`/`DELETE` employees, shift schedules, devices
  (and their nested device-enrollments / employee-shift-assignments) at
  their own location; every one of those same operations returns `403 "Not
  your location"` at another location. Confirmed for all three resource
  types plus the two nested sub-resources — `test_manager_operational_crud_scoped_to_location`.
- Payroll (`/payroll/runs`, including `POST`) and Config
  (`/config/penalty|overtime|absence-rule`) return `403` for a manager
  without `users.can_manage_payroll` — even for their own location. Confirmed
  the flag is a genuine per-manager admin-settable grant (`PATCH
  /users/{id}` with `can_manage_payroll: true/false`), and that once granted
  a manager still can't touch another location's payroll/config (`403`
  persists for cross-location, only the role gate itself opens up) —
  `test_manager_payroll_access_requires_opt_in_flag`.
- Admin is unrestricted throughout (`require_admin`-gated `/users` endpoints
  untouched; `require_payroll_access` and `assert_location_access` both
  short-circuit `if user.role == "admin"`) —
  `test_admin_unrestricted_across_locations`,
  `test_admin_payroll_and_config_access_unrestricted`.
- Spot-checked the real seed data: `manager1` (id 44) already has
  `location_id=1, can_manage_payroll=true` in the live DB — consistent with
  this being an intentionally-configured demo account, not a bug.

### 3.2 Live daily-status recompute on punch ingest
Confirmed `backend/app/routers/internal.py`'s `ingest_punches` (lines
120-131) calls `recompute_employee_date` for every affected
`(employee_id, work_date)` pair immediately after classification, in the
same request — not deferred to the nightly job. Verified end-to-end: a fresh
employee with zero `attendance_daily_status` rows for today got a `present`/
`late` row the instant a punch was ingested via
`/internal/ingest/punches`, with no separate `/attendance/recompute` call
anywhere in the test — `test_live_recompute_and_onsite_kpi_update_immediately_on_ingest`.

### 3.3 Dashboard "Present" includes late arrivals
Confirmed `backend/app/routers/reports.py`'s `dashboard_summary` (line 174):
`present_today = status_q.filter(AttendanceDailyStatus.status.in_(("present",
"late"))).count()`. Verified live: ingesting a late check-in increased
`present_today` by exactly 1 (not 0), and `present_today >= late_today` held
before and after — `test_live_recompute_and_onsite_kpi_update_immediately_on_ingest`.
Also confirmed by code read that `analytics()`'s stacked trend chart
deliberately keeps present/late/absent/on_leave mutually exclusive (a
different view, correctly untouched) — matches the code comment's own stated
intent, no inconsistency between the two views' semantics.

### 3.4 "On Site Now" sub-metric
Confirmed `_on_site_now` (`reports.py` lines 42-76): most-recent-punch-per-
employee today, excluding only `check_out_work`. Verified live:
- Check-in → `on_site_now` +1 immediately.
- Break-out punch (`raw_status_code=2`, classified as `check_out_break`) on
  top of that → `on_site_now` **unchanged** (still counted as on-site, not
  "left") — confirms it doesn't misread a break as a departure.
- Real check-out punch (`check_out_work`) → `on_site_now` drops back to
  baseline **immediately**, same request, no nightly wait.
All three confirmed in the same test,
`test_live_recompute_and_onsite_kpi_update_immediately_on_ingest`. Frontend
wiring (`Dashboard.tsx` line 101-102 → `KpiCard`'s `subValue`/`subLabel` →
`Card.tsx` lines 39-70) reviewed and matches the API contract exactly
(`data?.on_site_now`, `dashboard.onSiteNow` i18n key present in both
`en.json`/`sq.json`).

### 3.5 "On Leave Today" KPI card
Confirmed `_on_leave_today` (`reports.py` lines 79-103) and the
`OnLeaveEmployee` schema (`schemas.py` line 752) return employee name, the
leave type's `name` as the "reason" (not just a boolean/status), and the
date range, for any `approved` leave overlapping the target date — and that
it's run through the same `_scope_employee_query` as everything else
(fail-closed for a manager with no location, own-location-only otherwise).
Verified live: created a leave record via a manager with an auto-approving
leave type, confirmed the on-leave KPI shows the correct `leave_type_name`
(matching the real leave type's `name`, not e.g. its id), correct
`start_date`/`end_date`, and that a same-location manager sees it while a
different-location manager does not —
`test_manager_created_leave_and_requires_approval_and_on_leave_kpi`. Frontend
(`Dashboard.tsx` lines 128-135, 323-340) reviewed — modal branch, badge, and
date-range rendering all match the API contract; `dashboard.onLeaveToday`/
`noOneOnLeave` i18n keys present both locales.

### 3.6 Leave workflow changes
Confirmed in `backend/app/routers/leave.py`:
- `POST /leave-records` now allows `require_manager_or_admin`
  (line 121) and calls `assert_location_access(user, employee.location_id)`
  (line 126) — a manager can create a request for their own-location
  employee, `403` for another location's. Verified live both directions.
- `LeaveType.requires_approval` is honored (lines 133-147): `auto_approved =
  not leave_type.requires_approval`; when true, status lands `"approved"`
  immediately with `approved_by_user_id`/`approved_at` set to the creator,
  and `recompute_range` is called inline (not deferred) so
  `/attendance/daily-status` reflects `on_leave` in the same request.
  Verified live: a `requires_approval=true` type request lands `pending`
  (unaffected, unapproved); a `requires_approval=false` type request lands
  `approved` and the daily-status/dashboard reflect it immediately with zero
  separate approval step — same test as §3.5. Same logic confirmed present
  and consistent in the bulk-import `insert()` closure (lines 174-198).
- `delete_leave_record` (lines 244-260): `auto_approved = rec.status ==
  "approved" and not rec.leave_type.requires_approval` — an auto-approved
  record (from a `requires_approval=false` type) can now be deleted; a
  record an admin **manually** approved (via `PATCH .../approve`, from a
  `requires_approval=true` type) still returns `400 "Only pending leave
  requests can be deleted"`. Verified both branches live in the same test.

### 3.7 Alerts sorted newest-first by date
Confirmed `reports.py`'s `alerts()` (lines 517-523): two stable sorts —
severity ascending first, then `work_date` descending (undated alerts sort
to `date_type.min`, which lands last under `reverse=True`) — achieving
"newest-first by date, severity as tiebreaker, undated last" without needing
a combined sort key (the two need opposite directions). Verified live with
two `missing_checkout` alerts at different dates for the same test employee
— the more recent one's index in the response was confirmed lower than the
older one's, and the full list of dated alerts' `work_date` values were
confirmed non-increasing end-to-end —
`test_alerts_sorted_newest_first_by_date`.

### 3.8 Role rename `hr_admin` → `admin` / `checkIN` → `chronos` naming — spot-check
```
grep -rln "hr_admin" --include="*.py" --include="*.ts" --include="*.tsx" .
  -> only backend/alembic/versions/0004_role_admin_rename.py (expected —
     historical migration content, references the old value it migrates
     FROM/TO by design, not a regression)
grep -rln "checkIN" --include="*.py" --include="*.ts" --include="*.tsx" .
  -> only backend/tests/conftest.py, which is a literal filesystem path
     (cwd="/home/olti/web-agency/chronos") — the project directory is
     genuinely named that; not a naming regression
```
`backend/app/models.py`'s `ck_users_role` check constraint is `role in
('admin','manager')` (no `hr_admin`) — confirmed at the schema level, not
just application code. No regressions found.

---

## 4. Residual gaps handed to `debug` (not fixed here, with reasoning)

Carried forward from the prior pass (still applicable, not re-litigated):
1. No browser-based visual/interaction verification — squarely `debug`'s
   lane per `CLAUDE.md`. Worth a specific pass over the Dashboard's two new
   KPI cards ("On Site Now" sub-metric, "On Leave Today" card + modal) and
   the Alerts page ordering, since those are what's visually new this batch.
2. No frontend automated test framework exists (`vitest`/`jest`/`playwright`
   — still none installed); not stood up this pass either, same reasoning as
   before (out of scope for a verification-focused QA pass).
3. Device sync / `pyzk` hardware integration — no physical K40 device
   available in this environment, unchanged from prior passes.
4. `worker`'s APScheduler nightly job firing on its own schedule — not
   observed live; the underlying `recompute_range` it calls is the same code
   path thoroughly exercised via the manual-trigger endpoint and the new
   live-ingest path this pass, per `BLUEPRINT.md`'s "one implementation, two
   triggers".
5. Everything already accepted/by-design in `SECURITY_REPORT.md` is
   unchanged and still applies.

New from this pass:
6. `backend/app/routers/payroll.py`'s router carries both a router-level
   `dependencies=[Depends(require_payroll_access)]` *and* a per-endpoint
   `user: User = Depends(require_payroll_access)` parameter on every route
   function. Functionally harmless (FastAPI caches a dependency's result
   per-request by default, so it only actually runs once), and not something
   this pass's task asked to change — flagging only as a minor readability
   note for whoever next touches that file, not a bug.

---

## 5. Cleanup performed

All test data created this pass is namespaced with `RUN_SUFFIX` (random
per-session suffix) and torn down automatically by `conftest.py`'s existing
session-scoped fixture teardown — same mechanism as the prior pass, extended
transparently to cover this pass's new fixtures (new employees, devices,
leave types, users) since they all reuse existing tables already covered by
the teardown's `LIKE '%suffix%'` deletes. Verified post-run via direct DB
query (§1) that zero rows matching `%qa%` remain anywhere, and that the only
data present is the application's own pre-existing seed/demo data
(untouched). Ran the suite twice in a row to confirm this holds
consistently, not just on a lucky single run.

No manual (non-pytest) throwaway accounts were created this pass — all
verification for the 7 task-specified areas was done through the automated
suite, which was judged sufficient (each area got a dedicated live-HTTP
test, no gaps that needed ad-hoc `curl` exploration beyond what pytest
already covers).

---

## 6. Final stack health confirmation

```
$ docker compose build api frontend        # after backend/.dockerignore added (§2)
 api       Built
 frontend  Built

$ docker compose up -d api frontend
 Container checkin-db-1        Healthy
 Container checkin-api-1       Started (healthy)
 Container checkin-frontend-1  Started

$ docker compose ps
NAME                  STATUS
checkin-api-1         Up (healthy)
checkin-db-1          Up (healthy)
checkin-device-simulator-1  Up
checkin-frontend-1    Up
checkin-worker-1      Up

$ curl http://localhost:8000/health        -> 200 {"status":"ok"}
$ curl http://localhost:8080/              -> 200

$ cd backend && pytest tests/ -v
23 passed in ~8.5s
```

DB confirmed at expected baseline after cleanup (only the app's own
pre-existing seed data — `admin`, `manager1`, 8 seed employees, 1 seed
location/device/schedule, 3 seed leave types — zero leftover QA rows).
Stack is healthy and ready for `debug`.

---

## 7. Prior pass (2026-08-23) — full write-up, reproduced verbatim

The original 16-test suite, the pagination `total`-miscount fix
(`backend/app/pagination.py`), and the Alerts-page bilingual-gap fix
(`backend/app/schemas.py`, `reports.py`, `AlertsPage.tsx`, both locale files)
from the prior QA pass are unchanged and still pass (all 16 of these tests
are still present, unmodified, in `backend/tests/test_qa_smoke.py`, and ran
clean as part of this pass's `23 passed` result in §1). This project has no
git history, so this file's own previous content would otherwise be lost the
moment it's overwritten — reproduced in full below rather than just
summarized, so nothing from that pass is lost.

> Date: 2026-08-23
> Status: **Test suite passes (16/16). Zero blockers for `debug`.** Two bugs found
> during this pass, both fixed and re-verified end-to-end against the live
> Docker Compose stack. One pre-existing pagination bug (flagged by `backend`
> in `BACKEND_NOTES.md` Section 8 for QA to pick up) also fixed.
>
> Input reviewed: `BLUEPRINT.md`, `DESIGN_SPEC.md`, `SECURITY_REPORT.md`
> (Revisions 1 & 2), `FRONTEND_NOTES.md`, `BACKEND_NOTES.md`. This is the first
> QA pass this project has received (a prior attempt was killed mid-run before
> producing any artifact).
>
> Method: no mocks. Every flow below was exercised against the real running
> stack (`docker compose`, real Postgres) via real HTTP requests — first
> interactively (`curl`) to build up and validate each scenario, then formalized
> into an automated `pytest` suite (`backend/tests/`) that reproduces the same
> scenarios and is safe to re-run (self-cleaning, namespaced test data).
> Credentials: the real `admin` password was already changed by the user before
> this session (confirmed via `must_change_password=false` in `users`), so — per
> this project's established convention (documented precedent in
> `SECURITY_REPORT.md`'s own verification notes) — a throwaway `hr_admin` test
> account was created directly in the DB via `docker compose exec -T api
> python -c "..."`, used for the session, and removed at the end.
>
> **Coverage (16 tests, all still present/passing in `test_qa_smoke.py`
> unchanged):** login rejects bad password; admin login + `/auth/me`;
> must-change-password server-side gate blocks all API access until cleared;
> pagination `total` regression; manager location-scoping on
> `/employees` list + detail; manager-with-no-location fail-closed empty
> result; missing-checkout has no bogus early-departure/overtime; alerts
> surfaces missing-checkout; role-gated alert types excluded from managers;
> full payroll math (two-layer lateness grace, daily-threshold overtime,
> absence deduction, adjustments, net pay, payslip PDF); leave
> approve/reject location-scoping + recompute trigger; bulk-import clean
> error messages (no raw DB text) for employees + leave records; bulk-import
> 10MB cap enforced with a real >10MB upload; bulk-import auth gate; config
> penalty edit/deactivate round-trip.
>
> **Bug #1 — pagination `total` miscount on unjoined queries (fixed):**
> `query.order_by(None).with_entities(func.count())` on a query with no
> explicit join drops the implicit `FROM` clause, so Postgres evaluates it as
> a scalar expression (always `1`) rather than a row count. Fixed in
> `backend/app/pagination.py` by counting via a wrapping subquery instead
> (`db.query(func.count()).select_from(query.order_by(None).subquery())`),
> which preserves `FROM` unconditionally. Verified both the broken (unjoined)
> and working (joined) cases compute correctly post-fix.
>
> **Bug #2 — Alerts page dynamic messages were English-only regardless of UI
> language (fixed):** `GET /reports/alerts` built each alert's `message`
> field as a hardcoded English f-string server-side; the Alerts page rendered
> it directly, silently regressing on this app's otherwise-complete
> Albanian/English parity. Fixed by adding structured fields (`count`,
> `device_label`, `username`) to `AlertItem` alongside `employee_name`/
> `work_date`, populating them server-side, and having the frontend build a
> translated message per alert `type` via new `alerts.types.*` i18n keys
> (falls back to the raw `message` field for any future unrecognized `type`).
>
> **Security-patch re-verification (all confirmed live):** real CSV
> bulk-import through real cookie auth for both employees and leave records,
> confirming clean per-row error messages (no raw driver/constraint text) and
> that valid rows actually land in the DB; the specific bad-`manager_user_id`
> row returns exactly `"Manager not found"`; a real >10MB file upload
> returns `413` with zero rows inserted.
>
> **Business-logic verification:** location-based manager scoping confirmed
> live across `/employees`, `/attendance/daily-status`, leave
> approve/reject, and `/reports/alerts`, including the fail-closed
> `location_id = NULL` transition case; full payroll calculation
> hand-verified against the two-layer grace period (shift-level grace
> subtracted first, then `penalty_config`'s own allowance on the already-net
> late figure), daily-threshold overtime, absence deduction formula, manual
> adjustments, and finalized-run payslip PDF generation; missing-checkout
> handling confirmed to produce zero bogus penalty/bonus all the way through
> to payroll, while still surfacing via `/reports/alerts` for both admin and
> location-scoped managers; config CRUD edit/deactivate round-trip confirmed
> for the Penalties page (Overtime/Absence-Rule pages share the identical
> code path, judged low-risk, not independently re-run); full bilingual key-
> parity audit (332 static + all dynamic `t()` call sites, 422 keys each
> locale, zero gaps either direction beyond the Alerts fix above).
>
> **Residual gaps handed to `debug` at the time:** no browser-based
> visual/interaction testing available in that environment (flagged as
> squarely `debug`'s lane); Overtime/Absence-Rule config pages' edit/
> deactivate not independently re-run over HTTP (shared code path with the
> tested Penalties page, low risk); no frontend test framework exists;
> device sync/`pyzk` hardware integration untestable without a physical K40;
> `worker`'s APScheduler nightly firing not observed live (same
> `recompute_range` code path tested via the manual-trigger endpoint,
> "one implementation, two triggers" per `BLUEPRINT.md`); single-process
> login rate-limiting accepted as documented in `SECURITY_REPORT.md`.
>
> **Cleanup:** all throwaway data (test admin/manager accounts, locations,
> employees, shift schedules, device, leave type/record, penalty/overtime
> config, payroll run) removed via direct DB statements, confirmed DB back
> at bootstrap state (`locations`=1, `users`=1, all other domain tables=0,
> seed `absence_rule_config` untouched) afterward.
