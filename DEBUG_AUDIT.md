# DEBUG_AUDIT.md — chronos

Date: 2026-09-16
Status: **Clean — approved. 3 bugs found and fixed here** (1 backend, 2
frontend/CSS), **2 handed-off items closed**, **3 items escalated** (none in
an audited category, none blocking).

This pass is the final gate on the multi-vendor device-integration batch. It
covered the five mandated audit categories — mobile layout breakage, z-index
stacking, overflow/scroll, broken/janky animation, and visual regression
against `DESIGN_SPEC.md` — plus the two open items handed to `debug`
explicitly by the orchestrator, plus the residual items in `QA_REPORT.md`
Section 8.

Input reviewed: `SECURITY_REPORT.md` Revision 3 (findings 31–40, R1–R4),
`QA_REPORT.md` (2026-09-16 pass, Sections 2 and 8), `DESIGN_SPEC.md`
§1.9 / §5.8–5.10 / §6.1 / §6.10 / §6.17 / §6.25–6.26, and direct source
review of every file the device batch touched.

Method: real browser (Chromium via Playwright, headless) against the running
Docker Compose stack through nginx on `http://localhost:8080` — the path a
real client takes, and the only one still open now that `api` binds
`127.0.0.1:8000`. **Every finding below was measured in the DOM
(`getBoundingClientRect`, `getComputedStyle`, `getAnimations`,
`document.elementFromPoint`, `scrollWidth` vs `clientWidth`), not eyeballed
from a screenshot** — the two frontend bugs in this pass are both invisible
to a static screenshot at the wrong viewport, and one of them is invisible to
screenshots entirely.

Coverage: 6 viewport widths (1440 / 1024 / 834 / 640 / 375 / 320) × 2
languages (`sq` default, `en`) × 3 device types (`zkteco`, `hikvision`,
`hikvision_cloud`). Albanian is tested as a first-class case throughout
because every hint string in this batch is 20–25% longer in `sq` than in
`en` (`ipAddressHint` is 110 chars vs 90), so `sq` is the binding constraint
on every wrap.

Environment bring-up (nothing added to the project): Chromium was already
cached at `~/.cache/ms-playwright/chromium_headless_shell-1243/`; its four
missing shared libraries (`libnspr4`, `libnss3`, `libnssutil3`,
`libasound.so.2`) were resolved by `apt-get download` + `dpkg -x` into the
session scratch dir and `LD_LIBRARY_PATH` — no root, no `sudo`, no
`apt-get install`. `pytest` is not in the runtime `api` image (by design —
`requirements-dev.txt` is excluded from the Dockerfile), so the suite was run
from a throwaway venv in the scratch dir against `127.0.0.1:8000`.

Test data: one throwaway admin (`__debug_admin`) and three throwaway devices,
one per vendor, with deliberately hostile content — a 39-char label, a
32-char serial number, and the real `open.hik-connect.com` cloud host — to
stress the widened table and the card truncation. **All removed at the end of
this pass**; DB verified back to its original 1 device / 3 users / 8
employees / 1 payroll run, config tables byte-identical (§7).

---

## 1. Handed-off item 1 — `config_lookup.py` money bug: fix CONFIRMED correct,
## complete, and zero-impact on existing data

`backend/app/services/config_lookup.py:29`. QA's one-line change from
`(model.location_id == location_id).desc()` to `model.location_id.is_(None)`.

### 1.1 The fix is correct

Verified against the live DB, not by reading. The emitted SQL is now:

```sql
... WHERE penalty_config.is_active IS true
      AND (penalty_config.location_id = 1 OR penalty_config.location_id IS NULL)
 ORDER BY penalty_config.location_id IS NULL, penalty_config.effective_from DESC
```

`location_id IS NULL` yields a real boolean, so ascending order puts `false`
(location-specific) first. No NULL can enter the sort key, so Postgres's
`NULLS FIRST`-on-`DESC` default can no longer invert the ranking.

Proven behaviourally with a planted competing row, in a rolled-back
transaction, with the location-specific row given a **deliberately older**
`effective_from` (2020-01-01) than the org-wide one (2026-08-24) so it could
not win by recency:

```
PICKED with planted loc-specific row: id=60 location_id=1 effective_from=2020-01-01
  -> location-specific wins: True
PICKED for location_id=None:          id=11 location_id=None
```

This is the behaviour the module docstring documents — specificity is the
primary key, recency is only the tiebreaker — and the second line confirms the
`location_id=None` caller (org-wide payroll run, or an employee with no
location) is unaffected: it still gets the org-wide row. That path was never
broken, because `model.location_id == None` compiles to `IS NULL`, which is
already a real boolean; the defect only bit when a bound integer was passed.

### 1.2 The fix is complete — no other instance of the pattern exists

Audited all 26 `order_by(...)` call sites in `backend/app/`, `worker/` and
`device-simulator/`. `config_lookup.py:29` is now the **only** ORDER BY in the
codebase whose sort key is a boolean or NULL-able expression rather than a
plain column or an aggregate. Everything else sorts on a name, a timestamp, a
date, or a `func.sum()`.

Two near-misses checked rather than assumed, since both are `DESC` (where
`NULLS FIRST` would hurt):

- `routers/reports.py:263` and `:286` — `func.sum(late_minutes).desc()` /
  `func.sum(overtime_minutes).desc()` for the "top late / top overtime"
  leaderboards. A group summing to NULL would sort to the top of a `DESC`
  leaderboard. It cannot happen: both columns are `nullable=False,
  server_default="0"` (`models.py:274`, `:276`), and both queries are INNER
  JOINs with filters (`status == "late"`, `overtime_minutes > 0`) that
  guarantee every group is non-empty. `SUM()` over a non-empty group of
  non-null integers is never NULL.
- `services/shift_lookup.py:29` — the other effective-dated lookup, and the
  structural twin of `config_lookup`. It orders on `effective_from.desc()`
  alone, with no specificity tier, so there is no comparison in its sort key
  and nothing to invert.

### 1.3 Data impact is nil — the orchestrator's reading is confirmed, and
### proven rather than inferred

The current DB state matches what the orchestrator reported:

```
 absence  | id 1  | location_id NULL | 2020-01-01 | active
 overtime | id 8  | location_id NULL | 2026-08-24 | active
 penalty  | id 10 | location_id NULL | 2026-08-24 | inactive
 penalty  | id 11 | location_id NULL | 2026-08-24 | active
payroll_runs: id 21, location 1, 2026-08, finalized (finalized_at 2026-08-24 13:26)
```

Zero location-specific rows in any of the three config tables, and one
location (id 1). But rather than reason from that, I ran the **old and new
ordering side by side** over the live data across every input the function
can receive — every location plus `None`, every config table, swept weekly
from 2019-01-01 to 2027-12-31:

```
PenaltyConfig:     location-specific rows present = 0
OvertimeConfig:    location-specific rows present = 0
AbsenceRuleConfig: location-specific rows present = 0
checked=2820  mismatches=0
```

**2820 lookups, zero divergence.** With no location-specific row in the
candidate set, both orderings collapse to `effective_from DESC` and select
the identical row. The fix is a provable no-op on all existing data, so
payroll run 21 cannot have been computed under a different config than it
would be today. **No remediation needed — confirmed.**

One caveat recorded for honesty rather than as a concern: there is no audit
table, so a location-specific config row that existed *and was deleted*
before run 21 was finalized would be unrecoverable. Every surviving config
row in all three tables is org-wide, and run 21 finalized 81 minutes after
the currently-active penalty row was created, so there is no positive
evidence of one having existed. I also attempted a direct replay of run 21's
8 lines under the current code; it is not a usable signal, because the
Aug-2026 `attendance_daily_status` rows have themselves changed since
finalization (QA's new fixtures and later recomputes), so the diff reflects
attendance data movement, not config selection. The 2820-lookup differential
above isolates the config-selection question cleanly and is the stronger
evidence.

## 2. Handed-off item 2 — `bulk_import.py` 500 on a non-UTF-8 upload: FIXED

`backend/app/services/bulk_import.py`. The CSV branch called
`raw_bytes.decode("utf-8-sig")` unguarded while the `.xlsx` branch 40 lines
below already returned a clean 400 for its own parse failure.

Fixed at the call site, mirroring the `.xlsx` branch's shape, in
`run_csv_bulk_import()`:

```python
    else:
        try:
            rows = list(_parse_csv_rows(raw_bytes))
        except UnicodeDecodeError:
            raise HTTPException(400, "Could not read CSV file: it is not valid UTF-8 text. ...")
        except csv.Error as exc:
            raise HTTPException(400, f"Could not read CSV file: {exc}")
```

Guarding at the call site rather than inside `_parse_csv_rows` matters:
that function is a generator, so nothing in it executes until `list()` pulls
it — a `try` around the `decode` alone would still be correct, but the call
site is where the second failure mode below also surfaces.

**A second, separate 500 was found while fixing the first.** The
`csv.Error` arm is not defensive padding; it closes a reachable hole:

- The NUL-byte case that used to raise `_csv.Error: line contains NUL` no
  longer does — modern CPython accepts NUL in a field (verified:
  `list(csv.DictReader(io.StringIO('a,b\n\x001,X\n')))` parses fine).
- But `csv.field_size_limit()` is 131072 chars, and this endpoint's own cap
  is **10 MB**. A perfectly valid-UTF-8 CSV with one field longer than 128 KB
  therefore sails past the size cap and raises
  `_csv.Error: field larger than field limit (131072)` — an unhandled 500 on
  exactly the same boundary, which nothing had caught.

Deliberately caught `UnicodeDecodeError` and `csv.Error` specifically rather
than reusing the `.xlsx` branch's blanket `except Exception`, so a genuine
programming error inside the row loop still surfaces as a 500 instead of
being silently relabelled a client error.

Affects both `/employees/bulk-import` and `/leave-records/bulk-import`.

**Tests:** QA's `xfail` marker on
`test_bulk_import_of_undecodable_bytes_is_not_a_500` is **removed**, and the
test tightened from `< 500` to assert the exact 400 and its message. Two
tests added alongside it in `backend/tests/test_qa_smoke.py`:

- `test_bulk_import_of_csv_with_oversized_field_is_not_a_500` — the
  field-size-limit hole found above.
- `test_bulk_import_of_valid_utf8_csv_still_works` — a real 1-row import that
  must return `created: 1`, so the new `try/except` cannot pass by swallowing
  the happy path. Its employee code carries the suite's `RUN_SUFFIX` so
  `conftest.py`'s teardown reclaims it.

```
$ pytest tests/ -q
136 passed in 41.77s        (was 133 passed, 1 xfailed)
```

`api` image rebuilt; `frontend` restarted afterwards for the nginx-DNS reason
in §8.3.

---

# Visual / mobile / z-index / overflow / animation audit

## 3. `DeviceListPage.tsx` — the new "Device Type" column

### 3.1 Overflow and horizontal page scroll — clean at every breakpoint

The table is now 7 columns wide (label, location, type, IP:port, serial,
status, last synced) and intrinsically ~1080–1150px. **No breakpoint forces
horizontal page scroll.** Measured `documentElement.scrollWidth` vs
`clientWidth` at all six widths in both languages — equal at every one.

The table does exceed its container below ~1150px, but it is contained by
`DataTable`'s `hidden sm:block sm:overflow-x-auto` wrapper, which scrolls
independently:

```
1440: table 1150 / wrapper 1150   (fits)
1024: table 1080 / wrapper  734   (scrolls inside)
 834: table 1080 / wrapper  784   (scrolls inside)
 640: table 1080 / wrapper  590   (scrolls inside)
```

To distinguish "contained scroller" from "leaking overflow" I re-ran the
whole matrix with a check that walks each over-wide element's ancestors and
only reports it if **no** ancestor has `overflow-x: auto|scroll|hidden`.
Across 5 device pages × 6 widths × 2 languages (60 page-checks): **zero
uncontained overflows.**

### 3.2 z-index under horizontal scroll — clean

The widened table makes the sticky first column load-bearing for the first
time (`Table.tsx` applies it when `columns.length > 3`, which the 7-column
device table now is). Scrolled the wrapper fully right at 834px and 640px and
checked what is actually painted on top:

```
834: scrollLeft=296  td position=sticky z-index=1  bg=rgb(255,255,255)  elementFromPoint -> "Main Entrance"
640: scrollLeft=490  td position=sticky z-index=1  bg=rgb(255,255,255)  elementFromPoint -> "Main Entrance"
```

The pinned label cell is opaque and is the topmost element at its own
coordinates — cells scrolling underneath do not bleed through. `thead` is
`z-10`, the sticky `td` is `z-[1]`; both sit far below the app's
`zIndex` scale (`topbar/sidebar:20 < popover:30 < drawer:40 <
modal-backdrop:50 < modal:51 < toast:60`) and cannot collide with it.

### 3.3 [BUG — FIXED] Device Type was missing entirely from the mobile card

**Found:** the "Device Type" column was added to the desktop table today but
**not** to `DataTable`'s `mobileCard` mapping, so below 640px the attribute
simply vanished. Measured card content at 375px and 320px:

```
'__debug Hik Cloud Warehouse Gate\nopen.hik-connect.com:443\nAktiv\nLokacioni\nMain Location\nSinkronizuar Së Fundmi\nKurrë'
'__debug Hik Direct Lobby Entrance North\n10.0.0.151:80\nAktiv\nLokacioni\nMain Location\nSinkronizuar Së Fundmi\nKurrë'
```

This is a mobile-parity regression introduced by this batch, and it has real
operational bite: the whole point of the batch is that there are now three
vendors, and on a phone an operator could not tell a `hikvision` device from
a `hikvision_cloud` one — the two rows above differ only by a hostname that
also truncates. The card title truncates at `...Warehous...`, so the label is
not a reliable fallback either.

**Fixed** in `frontend/src/pages/devices/DeviceListPage.tsx` — device type is
now the first card row, above location, using the same `t()` key as the
table column so the two can never drift:

```tsx
rows: [
  { label: t('devices.deviceType'), value: t(`devices.deviceTypes.${d.device_type}`) },
  { label: t('devices.location'), value: d.location_name ?? '–' },
  { label: t('devices.lastSynced'), value: ... },
]
```

Re-verified at 375px and 320px in both languages: the type now renders
(`Lloji i Pajisjes / Hikvision (cloud)`, `Device Type / Hikvision (cloud)`),
and the extra ~18px per card introduces no overflow — `scrollWidth ==
clientWidth` still holds at 320px.

Serial number is also absent from the card. Left alone deliberately: it is
not part of this batch's diff, and a 32-char serial in a right-aligned
`text-caption` card row would be the overflow problem this section is
supposed to be preventing. Noted in §8 for whoever next touches the card
mapping.

## 4. `DeviceFormPage.tsx` — conditional credential fields in the 2-column grid

### 4.1 No layout jump at the interaction point — clean

This was the primary concern: switching `device_type` mutates the same grid
the `<select>` lives in (row 2 shares a grid row with the address field,
whose label *and* hint both change), so a naive layout would move the control
out from under the operator's cursor mid-interaction.

Measured the top of every field plus the type `<select>` itself across a full
round trip — `zkteco → hikvision → hikvision_cloud → hikvision → zkteco` —
at 1440, 640 and 375:

```
1440  zkteco           typeSelectTop=293  Etiketa=211 Lokacioni=211 Adresa IP=293 Porti=411
      hikvision        typeSelectTop=293  ... + Emri i përdoruesit=493 Fjalëkalimi=493
      hikvision_cloud  typeSelectTop=293  ... + App Key=529 App Secret=529
      hikvision        typeSelectTop=293  (identical to the first hikvision reading)
      zkteco           typeSelectTop=293  (identical to the opening reading)
```

**The type select never moves** — 293px at desktop, 363px at 375px, in every
state and in both directions. Nothing above it moves either. The round trip
returns to byte-identical geometry, so there is no cumulative drift from
repeated switching. Fields *below* the select grow and shrink as the
conditional row appears, which is the intended behaviour and is below the
interaction point.

One sub-pixel-honest note: at 375px in Albanian, `Porti` moves up 16px
(579 → 563) on the `hikvision → hikvision_cloud` switch, because
`ipAddressHint` (110 chars) wraps to 3 lines there while `cloudHostHint`
(89 chars) wraps to 2. It is a field below the control being operated,
moving by half a line. Not a defect.

### 4.2 Long hint text wraps correctly, including Albanian — clean

Checked every label and every hint for clipping via `scrollWidth >
clientWidth` and `scrollHeight > clientHeight` on the actual elements, at all
six widths in both languages, in all three type states.

**Zero clipped labels, zero clipped hints.** The worst cases behave:

| String | `en` | `sq` | 320px height |
|---|---|---|---|
| `cloudHostHint` | 88 ch | 89 ch | 48px (3 lines) |
| `serialNumberCloudHint` | 84 ch | **108 ch** | 48px (3 lines) |
| `ipAddressHint` | 90 ch | **110 ch** | 48px (3 lines) |

The longest label, `Hosti i API-t të Cloud-it *` (Albanian for "Cloud API
Host"), stays on one 20px line at every width down to 320px.

No page overflow in any state: `scrollWidth == clientWidth` at 1440 / 1024 /
834 / 640 / 375 / 320, both languages, all three device types.

`FormFooterBar`'s `sticky bottom-0` behaves: at 375px it stayed pinned at
y=594 across all three type states, so the Save/Cancel pair never gets pushed
off-screen by the taller cloud form.

## 5. `DeviceDetailPage.tsx` — the edit modal at mobile width

All three vendors × six widths × two languages (30 modal opens). **Clean
throughout** — no clipped label, no clipped hint, no horizontal overflow
inside the modal body, no page overflow, and the dialog is never positioned
off-screen top or bottom.

The `Modal`'s `max-h-[70vh] overflow-y-auto` body does the work on a phone,
where the cloud form is nearly twice the available height:

```
375x667  cloud  dialog 343x526 @ y=71   body 467 visible / 848 scrollable
320x640  cloud  dialog 288x507 @ y=67   body 448 visible / 880 scrollable
320x640  zkteco dialog 288x507 @ y=67   body 448 visible / 628 scrollable
```

Scrolling reaches the footer: `Ruaj`/`Anulo` sit at y=918 (off-screen) on
open and at y=537 (visible) after scrolling the body to the bottom, at both
375 and 320, in both languages. They are inside the scroll area rather than
in the `Modal`'s pinned `footer` slot — that is the same pattern every other
modal in the app uses (including `ConfirmDialog`), so it is a consistent
house style rather than a regression here; noted in §8.

The cloud-mode relabelling all lands correctly in the modal: `Hosti i API-t
të Cloud-it` / `Cloud API Host`, `App Key` / `App Secret`, and `Numri Serik`
carries the required marker and its own hint. `Fjalëkalimi (opsionale)` keeps
`authPasswordHint` ("leave blank to keep the current password"), which is
what makes the whole-form PUT safe.

Two-card body stacking per `DESIGN_SPEC` §5.10 ("side by side on desktop,
stacked on tablet/mobile") verified by comparing the two cards'
`getBoundingClientRect().top`: side-by-side at 1440/1024, stacked at
834/640/375/320 — matching the `lg:grid-cols-2` breakpoint exactly, with no
off-by-one at 1024.

## 6. Error surfacing — the security-hardened messages

### 6.1 Inline `test-connection` result banner — clean

Exercised live against an unreachable `hikvision` device at every width.
The banner renders the generic failure class from
`devices.py:_connection_error_detail()` with no clipping and no overflow at
any width:

```
1440: box 514x54  'I paarritshëm\nTimed out connecting to the device'
 834: box 736x54  (same)
 375: box 301x54  (same)
 320: box 246x54  (same)
```

Matches `DESIGN_SPEC` §5.10's banner spec (danger-50 background, danger-700
heading, detail in `text-caption` below). The spec says "the raw error
detail"; the security pass deliberately replaced raw text with a failure
class (Revision 3 finding 32). That is intentional drift, not a regression —
recorded in §8 for `docs`.

### 6.2 `FormErrorBanner` on the create form — clean

The cloud-host allowlist rejection (the 400 an operator is most likely to
hit) renders in full and wraps cleanly at the narrowest width:

```
1440: banner L=289 R=959  H=66   "a hikvision_cloud device's address must be a
 375: banner L=37  R=338  H=86    Hikvision Open Platform host (e.g.
 320: banner L=37  R=283  H=106   open.hik-connect.com)"
```

No clipping in either axis, no page overflow, symmetric 37px insets.

### 6.3 [BUG — FIXED] The retarget 400 toast hung off the left edge of a 320px screen

**Found:** triggering the finding-31 guard (change a device's address without
re-supplying its password) produced a 130-character toast that rendered
**partly off-screen** at 320px:

```
[320] TOAST  L=-16  R=304  W=320  vw=320   FLAGS=['offL']
      "Changing a device's address, port or type also requires re-entering
       its password, because the stored one is sent to the new target."
```

Confirmed visually: the danger accent bar (`border-l-4`) and the left half of
the alert icon were cut off by the viewport edge.

**Cause:** `Toast.tsx`'s container is `fixed right-4 top-4` with no left
anchor, so it is shrink-to-fit with only `100vw - 16px` available — 304px on
a 320px screen. The toast item's `min-w-[320px]` then forces it 16px wider
than that, and with only a right anchor it grows leftward, off-screen.
`position: fixed` means this produces no page scrollbar, so the standard
`scrollWidth > clientWidth` overflow check does **not** catch it — it is only
visible by measuring the element's own `left` against the viewport.

This is squarely in this pass's remit: it is the delivery mechanism for the
exact error message the orchestrator asked me to verify "renders legibly
rather than disappearing or overflowing", and 320px is a mandated width.

**Fixed** in `frontend/src/components/ui/Toast.tsx` — anchor both sides below
`sm`, and let the toast shrink there instead of forcing a 320px floor:

```tsx
<div className="fixed left-4 right-4 top-4 z-toast flex flex-col items-end gap-3 sm:left-auto">
  ...
  'flex w-full max-w-[420px] items-start gap-3 ... sm:w-auto sm:min-w-[320px]'
```

`items-end` + `sm:w-auto` preserve the right-aligned shrink-to-fit behaviour
from `sm` up, so desktop is untouched. Verified — desktop geometry is
byte-identical to before the fix, and the phone widths are now inside the
viewport:

```
        before            after
1440    L=1004 R=1424 W=420      L=1004 R=1424 W=420   (unchanged)
1024    L= 588 R=1008 W=420      L= 588 R=1008 W=420   (unchanged)
 834    L= 398 R= 818 W=420      L= 398 R= 818 W=420   (unchanged)
 640    L= 204 R= 624 W=420      L= 204 R= 624 W=420   (unchanged)
 375    L=   0 R= 359 W=359      L=  16 R= 359 W=343   (now inset both sides)
 320    L= -16 R= 304 W=320      L=  16 R= 304 W=288   (was off-screen)
```

The toast is a global component, so this was re-swept app-wide (§7.2) rather
than only on the device pages. Toast stacking (`z-toast` = 60) still paints
above the modal (51), the backdrop (50) and the mobile drawer (40) —
confirmed by capturing every `position: fixed` element with `z-index >= 30`
with the drawer open at 834/640/375/320.

## 7. Animation

### 7.1 [BUG — FIXED] The DESIGN_SPEC §1.9 button timing was invalid CSS and
### silently dropped by the browser on every filled/bordered button

**Found** by reading `getComputedStyle` rather than trusting the class name.
`Button.tsx`'s `pressClasses` was:

```
active:scale-[0.98] transition-[background-color_150ms_ease-out,transform_100ms_ease-out]
```

Tailwind's `transition-[...]` sets **`transition-property`**, which accepts
only property *names*. The built stylesheet contained, verbatim:

```css
transition-property:background-color .15s ease-out,transform .1s ease-out
```

which is invalid and dropped by the CSS parser, while the same utility's
sibling `transition-duration` / `transition-timing-function` declarations
survived. Net computed result on every primary / secondary / danger /
danger-outline / success-outline button in the app:

```
transitionProperty: "all"                              <- the initial value; the rule was dropped
transitionDuration: "0.15s"
transitionTimingFunction: "cubic-bezier(0.4, 0, 0.2, 1)"   <- ease-in-out, not ease-out
```

So the spec'd timing was in force nowhere: `transform` eased over 150ms
instead of 100ms, the easing was `ease-in-out` instead of `ease-out`, and
`transition-property: all` meant *every* animatable property — width, height,
colour, border-colour, box-shadow — transitioned on state change rather than
just background and transform. That is the definition of the "janky
animation" category, and it is invisible to a screenshot.

**Fixed** in `frontend/src/components/ui/Button.tsx` by expressing it as an
arbitrary *property* (the CSS shorthand) instead of an arbitrary *value* on
`transition-*` — one token, and it reproduces `DESIGN_SPEC` §1.9 exactly:

```
active:scale-[0.98] [transition:background-color_150ms_ease-out,transform_100ms_ease-out]
```

Built CSS now emits the valid shorthand
(`transition:background-color .15s ease-out,transform .1s ease-out`), and the
computed style on all three affected variants is exactly the spec:

```
primary   (Testo Lidhjen):  property "background-color, transform"  duration "0.15s, 0.1s"  timing "ease-out, ease-out"
secondary (Ndrysho):        property "background-color, transform"  duration "0.15s, 0.1s"  timing "ease-out, ease-out"
danger    (Fshij):          property "background-color, transform"  duration "0.15s, 0.1s"  timing "ease-out, ease-out"
```

`ghost` and `link` correctly keep `transition-colors duration-150 ease-out`
and were not touched — `DESIGN_SPEC` §1.9 excludes them from the press-scale
treatment.

This bug is pre-existing rather than introduced by the device batch, but it
falls in two audited categories (broken animation; visual regression against
`DESIGN_SPEC`), the fix is one token in one file, and the buttons it affects
are the ones this batch's flows run through ("Test Connection", "Save",
"Delete").

### 7.2 Loading-state animation — clean, no layout jank

`DESIGN_SPEC` §6.1 requires the spinner to *replace* the label without the
button resizing. Measured the "Test Connection" button's box through a real
in-flight request:

```
before loading: 122x36
during loading: 122x36   spinner animation 'spin', duration 1000ms, playState 'running'
after  loading: 122x36   -> SAME SIZE: True
```

`Button.tsx` keeps the label mounted as `invisible` under an absolutely
positioned `Loader2`, so the box is stable and nothing around it reflows.
Confirmed running (not paused or dropped), not merely present in the class
list.

## 8. Regression sweep after the three fixes

Two of the three fixes are global components (`Toast.tsx`, `Button.tsx`), so
they were re-verified beyond the device pages.

- **Device pages:** 5 routes × 6 widths × 2 languages = **60 page-checks**.
  Zero page overflow, zero uncontained overflow, card stacking correct at
  every breakpoint boundary. **0 problems.**
- **App-wide:** 16 routes (dashboard, alerts, employees, shift schedules,
  devices, locations, daily status, logs, leave, payroll, all four config
  pages, users, profile) × 4 widths × 2 languages = **128 page-checks**,
  asserting both no horizontal overflow and no console/page errors.
  **0 problems.** The only console entry anywhere in this pass is the
  expected pre-login `401` from the app's own `/auth/me` probe on the login
  screen.
- **Backend suite:** `136 passed` (from `133 passed, 1 xfailed`).
- **Stack:** all five containers up, `api` healthy, `/health` 200 via
  loopback, SPA and `/api/v1/*` 200 through nginx on `:8080`, and the
  `/api/v1/internal/` block still returning 404 through the proxy (the
  Revision 3 patch is intact — worth stating explicitly because §8.3 below
  is about that same nginx file).

## 9. Cleanup

`__debug_admin` and the three `__debug` devices removed; DB verified back to
its pre-pass state:

```
devices: 1 (Main Entrance)     users: 3 (admin, manager1, ensar.dauti)
employees: 8                   payroll_runs: 1 (id 21, finalized)
configs: absence 1, overtime 8, penalty 10+11 — unchanged, all org-wide
leftovers matching '%qa_%' / '%__debug%' / 'QA %': 0
```

The planted config row in §1.1 was created inside a rolled-back transaction
and never committed (it consumed one sequence value, id 60 — no row). The
temporary scripts copied into the `api` container are gone (the container was
rebuilt since). Nothing was written to the project directory except the four
source files in §11. Browser, venv and extracted `.deb` libraries all live in
the session scratch dir, not in the project.

---

## 10. Escalated — not fixed here, none in an audited category, none blocking

1. **nginx caches the `api` upstream IP at startup** (`frontend/nginx.conf`)
   — **for `devops`.** Recreating the `api` container 502s the frontend until
   `frontend` is also restarted. I hit this twice this session rebuilding
   `api`, so it is real, not theoretical. QA correctly identified a
   `resolver` directive as the fix, but it is **not a drop-in**: making
   `proxy_pass` use a variable (which is what forces re-resolution) requires
   a regex `location`, and **an nginx regex location beats a plain prefix
   location** — which would silently disable the `location /api/v1/internal/
   { return 404; }` block, a Revision 3 security patch. Anyone doing this
   must promote that block to `location ^~ /api/v1/internal/` in the same
   change, and re-assert that
   `curl http://localhost:8080/api/v1/internal/devices` still returns 404
   afterwards. Deliberately not attempted at the final gate: it is a
   deploy-time topology concern owned by `devops`, it is outside all five
   audited categories, and rewriting a security-critical proxy config
   unprompted at the last gate is exactly the wrong trade.

2. **Manual ZKTeco sync blames the worker** (`backend/app/routers/devices.py:229`)
   — **for `backend`.** Unchanged from `QA_REPORT.md` §2.3: the api→worker
   budget is `timeout=30` while pyzk's internal retries take ~28s wall, so a
   dead terminal returns `502 "Could not reach sync worker: timed out"` when
   the worker is healthy. Not fixed here because the remedy is a timeout-budget
   change (which ties up an API worker thread for longer) rather than CSS, and
   it needs a decision, not a patch. Two things to fix together while in there:
   the same line does `detail=f"Could not reach sync worker: {exc}"`, which
   echoes raw `httpx` exception text — the pattern `_connection_error_detail()`
   two functions above exists specifically to avoid, and httpx puts the
   internal worker URL in that text.

3. **Backend error text is English inside an Albanian UI** — **for `frontend`
   / `docs`.** Every `ApiError` surfaces as `showToast('error', err.message)`,
   so an `sq` operator sees "I paarritshëm" (translated) above "Timed out
   connecting to the device" (not), and the retarget 400 arrives entirely in
   English. This is app-wide and pre-existing, not introduced by this batch,
   and fixing it properly means keying backend errors for translation — a
   structural change, not a layout one. Recorded because this pass was asked
   to confirm those specific messages "render legibly", and they render
   correctly but not in the user's language.

Also noted, deliberately not changed:

- **`DataTable` mobile cards omit serial number** on `/devices` (§3.3) — out
  of this batch's diff, and a 32-char serial in a right-aligned card row
  would create the overflow this audit exists to prevent. For whoever next
  touches that mapping.
- **Modal footer buttons live inside the scrollable body**, so on a phone the
  cloud edit form needs a scroll to reach Save (§5). Consistent with every
  other modal in the app including `ConfirmDialog`; changing it is a
  `Modal`-wide pattern change, not a device-page fix.
- **`DESIGN_SPEC` §5.8–5.10 predate multi-vendor** — no `device_type` column,
  field or credential inputs, and §5.10 still says the test-connection banner
  shows "the raw error detail" which Revision 3 finding 32 deliberately
  replaced with a generic failure class. The build is a correct superset in
  every case; this is documentation drift for `docs`, alongside the §5.8–5.10
  and §5.14 drift `QA_REPORT.md` §8 already logged.

## 11. Files changed by this pass

| File | Change |
|---|---|
| `backend/app/services/bulk_import.py` | **Fix** — 400 instead of 500 on a non-UTF-8 CSV, and on a CSV field over `csv.field_size_limit()` (§2) |
| `backend/tests/test_qa_smoke.py` | `xfail` marker removed and the test tightened to assert the exact 400; 2 tests added (oversized field, valid-UTF-8 happy path) |
| `frontend/src/components/ui/Toast.tsx` | **Fix** — toast no longer renders off the left edge of a 320px viewport (§6.3) |
| `frontend/src/components/ui/Button.tsx` | **Fix** — `DESIGN_SPEC` §1.9 press transition was invalid CSS and silently dropped (§7.1) |
| `frontend/src/pages/devices/DeviceListPage.tsx` | **Fix** — Device Type restored to the mobile card view (§3.3) |

`backend/app/services/config_lookup.py` was **reviewed and left unchanged** —
QA's fix is correct, complete, and provably zero-impact (§1).

`api` and `frontend` images rebuilt; stack up and healthy.

---

## Summary

Three bugs found and fixed: a second unhandled-500 path in the CSV bulk
import beyond the one handed over; a mobile-parity regression where this
batch's new Device Type column never reached the phone card view; and a toast
that rendered off the edge of a 320px screen — the delivery mechanism for the
very error messages this pass was asked to verify. A fourth, the invalid
`DESIGN_SPEC` §1.9 button transition, was pre-existing but sits in two
audited categories and cost one token to fix.

Both handed-off items are closed: the `config_lookup.py` money-bug fix is
confirmed correct, confirmed to be the only instance of the pattern in the
codebase, and confirmed zero-impact by a 2820-lookup old-vs-new differential
over the live data — the orchestrator's reading that no remediation is needed
is correct. The `bulk_import.py` 500 is fixed and its `xfail` is now a
passing test.

All five audited categories were re-verified green after the fixes across 188
page-checks (60 device-specific + 128 app-wide), 6 viewport widths, 2
languages and 3 device types, with 136 backend tests passing and no console
errors. All throwaway data removed and the database verified back to its
pre-pass state.

Every audited category is clean.

---
---

# Prior pass (2026-08-25) — reproduced verbatim

Date: 2026-08-25
Status: **Clean. No blockers. No fixes required.** This pass audited the 5
frontend areas flagged as newly-changed/unreviewed in `QA_REPORT.md`
(2026-08-25 pass) for mobile layout breakage, z-index stacking, overflow/
scroll issues, animation jank, and visual regression against
`DESIGN_SPEC.md`. All 5 areas rendered correctly, at every breakpoint
tested, against the real running stack. Zero CSS/layout fixes were needed
this pass.

Method: real browser (Chromium via Playwright, headless), driven against the
actual running Docker Compose stack's frontend container at
`http://localhost:8080` (the port `docker-compose.yml` publishes — not
`5173`, which is the Vite dev-server port and isn't exposed by this stack's
`frontend` service; it builds and serves via nginx on `:80`, mapped to host
`:8080`). No mocks — same real Postgres-backed API the rest of the pipeline
has used throughout. Chromium wasn't preinstalled in this environment;
brought it up via a throwaway `pip install playwright` + `playwright install
chromium` in `/tmp` (outside the project, cleaned up after), and resolved
its missing shared-library dependencies (`libnspr4`, `libnss3`,
`libnssutil3`, `libasound2`) by extracting `.deb`s (two of which — `libnspr4`,
`libnss3` — were already sitting in the project root from a prior session;
`libasound2t64` fetched fresh via `apt-get download`, no `sudo`/root needed)
into a scratch dir and setting `LD_LIBRARY_PATH` — this was environment
bring-up only, nothing added to the project itself.

Test accounts: three throwaway users created directly in the DB via `docker
compose exec -T api python -c "..."` with `app.security.hash_password`
(same convention as `backend/tests/conftest.py` / this pass's own
`QA_REPORT.md`), all prefixed `__debug_` — `__debug_admin` (admin),
`__debug_mgr_flagged` (manager, `location_id=1`, `can_manage_payroll=true`),
`__debug_mgr_plain` (manager, `location_id=1`, `can_manage_payroll=false`).
Also inserted one extra `leave_records` row (employee `EMP-001` Arben
Berisha, leave type "Leje për Punë Zyrtare", today, `approved`) alongside
the pre-existing "Leje për Çështje Private" record for Jeta Bytyqi, so the
on-leave KPI/modal had two real long-Albanian-name badges to render
simultaneously, per this pass's task brief. **All three accounts and the
extra leave row were deleted at the end of this pass** — verified via direct
DB query (`select * from users where username like '%debug%'` → 0 rows;
on-leave-today record count back to the original 1). Stack confirmed healthy
after (`docker compose ps`, `api` `/health` → 200) — no state left behind.

---

## 1. Dashboard KPI row (5→6 cards, `Dashboard.tsx`)

**Checked:** overflow at `lg` (1440px, 1024px — 6-col), `sm`/tablet (834px,
640px — 2-col), and mobile (375px, 320px — 1-col); whether the new violet
"On Leave Today" card collides visually/reads as a bug next to "On Break
Now" (also violet).

**Result: clean.**
- No horizontal overflow at any tested width (`document.documentElement
  .scrollWidth` == `clientWidth` at 1440/1024/834/640/375/320 — measured via
  `page.evaluate`, not just eyeballed).
- Row wraps sensibly: 6-across at `lg`, 2×3 at `sm`, 1-column stack on
  mobile — screenshots confirm no card ever gets clipped or squeezed.
- Violet-color reuse: the KPI row actually has **three** consecutive violet
  cards ("On Break Now" / Coffee icon, "On Leave Today" / CalendarOff icon,
  "Pending Leave Requests" / CalendarClock icon) — one more than the task
  brief called out. Zoomed screenshot review: icons are clearly distinct
  shapes, labels are distinct Albanian text, and this reads as an
  intentional "secondary/leave-related metrics" visual grouping (same
  pattern as "Present"=green / "Late"=amber / "Absent"=red being a primary
  group) — not as a rendering glitch or duplicated card. No fix needed.

## 2. KpiCard `subValue`/`subLabel` (`Card.tsx`) — row-height consistency

**Checked:** whether the "Present" card (has `subValue`/`subLabel`, taller)
next to 5 cards without it causes visibly broken/misaligned heights, at
every breakpoint (this is exactly where a grid `align-items: stretch`
assumption could quietly break, since a `<button>` grid item's *content* box
doesn't auto-fill the stretched button height without an explicit flex/h-full
rule on the inner content div).

**Result: clean — verified by exact `getBoundingClientRect()` measurement,
not just visual impression.**
- At `lg` (1440/1024, all 6 in one row): all 6 cards measured **identical**
  `top`/`bottom`/`height` (e.g. 1440px: every card `top:132, bottom:327,
  height:195`).
- At `sm`/tablet (834/640, 2-per-row): the two cards sharing a row also
  measured identical height (e.g. 834px row 1: both `height:179`) — CSS
  Grid's default `align-items: stretch` is doing its job because a grid
  item's `display` is blockified regardless of the underlying element being
  a `<button>`, so it does fill the row height even though it's a
  button-not-div. My first-pass visual read of a full-page screenshot
  *looked* like a mismatch (compression/scaling artifact); a tight crop and
  the DOM measurement both confirmed the borders align exactly.
- Where a card has no `subValue`, the stretched box just has quiet empty
  padding below the label — no clipped content, no misaligned borders, no
  jank. This is fine as designed; no `min-height` fix needed.

## 3. "On Leave" detail modal (`Dashboard.tsx`, `detail === 'on_leave'`)

**Checked:** `LeaveTypeBadge` (which uses `whitespace-nowrap`, i.e. does NOT
wrap internally) with the two longest real Albanian leave-type names in the
system — "Leje për Punë Zyrtare" and "Leje për Çështje Private" — at modal
widths down to a 320px viewport (smallest realistic phone).

**Result: clean.**
- At 1440/834/375/320px, the modal row (`flex flex-wrap ... gap-3`)
  degrades gracefully: name + badge stay on one line as long as they fit;
  once space is tight (320px), the **employee name** (not the badge) wraps
  onto a second line first since it's plain text with no `nowrap`, and the
  badge stays intact and legible next to it — no badge text got cut off,
  no horizontal scrollbar, no overflow (`row.scrollWidth === row.clientWidth`
  measured directly at 320px for both rows: `240 === 240`).
- The date range wraps to its own line below when the row doesn't have room
  for it (already covered by `flex-wrap` on the parent), consistent at
  every width tested.

## 4. `UsersPage` payroll-access toggle (`UsersPage.tsx`, `Table.tsx`)

**Checked:** desktop table alignment of the new "Qasje në Pagesa" (Payroll
Access) toggle column next to the existing "Aktiv" (Active) toggle column;
mobile card view (`mobileCard` prop) rendering; the create/edit modal's
conditional Toggle (shown only when role=manager).

**Result: clean.**
- Desktop (1440px, 834px): both toggle columns render as tidy centered
  switches under their own headers, consistent column widths, no
  misalignment — confirmed on real data (`admin`/`manager1` seed rows plus
  the three throwaway accounts, one with the flag on, one off, one N/A for
  admin which correctly renders `—`).
- Mobile card view (<640px): payroll access renders as a static "Po"/"Jo"
  text row (not an interactive toggle) inside the card, shown only for
  manager rows — a deliberate, reasonable choice for the compact card
  layout, not a bug. (Note, out of scope for this pass since it's pre-
  existing and untouched by this batch: the mobile card also doesn't show
  an "Active" status row at all, for any role — that gap already existed
  before this batch's payroll-access addition and isn't something this
  pass's diff introduced, so it isn't flagged as a regression here, just
  noted for whoever next touches `UsersPage.tsx`'s `mobileCard` mapping.)
- Interaction-tested (not just static render): toggled `__debug_mgr_plain`'s
  payroll access on and back off directly in the table — UI updated
  correctly both times (optimistic `reload()`), no console/page errors, no
  layout shift.
- Create/edit modal's Toggle (role=manager only): renders correctly at
  1440px and 375px, with its hint text below, doesn't affect modal height
  in a way that pushes the footer buttons off-screen or requires scrolling
  on a normal phone viewport.

## 5. Sidebar nav for managers (`Sidebar.tsx` / `navConfig.tsx`)

**Checked:** whether the expanded manager nav (Employees/Shift Schedules/
Devices added unconditionally, Payroll/Configuration added conditionally on
`can_manage_payroll`) still fits without scrolling, per the project's
earlier sidebar-density fix — for both a flagged and unflagged manager, at a
deliberately short viewport height (1440×700, well below a typical laptop's
900+) to stress-test it.

**Result: clean.**
- Desktop sidebar: both `__debug_mgr_plain` (7 nav rows/groups) and
  `__debug_mgr_flagged` (11, with the extra Payroll link + Configuration
  group of 4) fit fully within a 700px-tall viewport with visible margin to
  spare (footer "Powered by Solis Labs" + collapse toggle both visible, no
  scrollbar) — confirmed via screenshot for both accounts.
- Mobile off-canvas drawer (375×667, `AppLayout.tsx`'s `Drawer` +
  `MobileUserSection` + `SidebarContent`): the flagged manager's longer nav
  (which doesn't fit in one screen at this height) scrolls correctly within
  the drawer's own `<nav>` (`overflow-y-auto`), independent of the pinned
  user-info header above it and the "Powered by Solis Labs" footer below —
  scrolled to the bottom and confirmed "Profili Im" is reachable and the
  footer stays put. This is pre-existing `Drawer`/`AppLayout` scroll
  behavior (not part of this batch's diff) but is exercised differently now
  that a flagged manager's nav is long enough to actually need it — worth
  having verified rather than assumed.
- z-index sanity check (not part of the 5 listed areas, but relevant to this
  pass's "z-index stacking" mandate): confirmed the project's `zIndex` scale
  in `tailwind.config.js` (`content:0 < topbar/sidebar:20 < popover:30 <
  drawer:40 < modal-backdrop:50 < modal:51 < toast:60`) is coherent and
  unchanged by this batch; the `DataTable`'s sticky header/first-column
  `z-10`/`z-[1]` values sit safely below all of it. No stacking conflicts
  found anywhere touched this pass.

---

## Summary

No bugs found in any of the 5 audited areas. No CSS/layout fixes were
necessary — the frontend batch under review holds up cleanly across mobile,
tablet, and desktop widths, with no z-index conflicts, no overflow/scroll
issues, and no visual regression against `DESIGN_SPEC.md`. All findings
above are analysis notes (deliberate design choices, or pre-existing
behavior exercised differently by this batch) rather than defects — none of
them block deploy, and none required a fix.

Every audited category is clean.

APPROVED FOR DEPLOY
