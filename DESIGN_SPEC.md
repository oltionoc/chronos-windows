# DESIGN_SPEC.md — chronos: Attendance & Payroll Management System

Status: **FINAL** — ready for `frontend` handoff.

**Revision 2 (2026-08-22):** Section 1 (Design System) revised in place —
palette (§1.1), typography/monospace usage (§1.2), and a new Micro-
interactions subsection (§1.9) — to remove "AI-aesthetic" clichés (generic
indigo/violet accent, loose heading line-heights, undersized status dots)
per an explicit design brief. Sections 0 and 2–7 (principles, app shell,
page templates, mobile rules, route hierarchy, component map, checklist) are
**unchanged** from Revision 1 except where a component-map entry directly
referenced a value that changed (flagged inline at each such spot: §1.5,
§5.13, §6.1, §6.2, §6.8, §6.9, §6.17, §6.18). All Tailwind token **names**
(`primary`, `violet`, etc.) are unchanged — only hex values and the specific
sizing/motion values below changed — so this is a value-only update for
`frontend`, not a rename/refactor.

**Revision 3 (2026-08-22):** Manager scoping reworded from team-based to
location-based throughout, to match `BLUEPRINT.md`'s same-day access-control
change (§3.4, §3.14, §6.2–§6.4: Manager visibility now filters on
`employees.location_id = users.location_id`, not on
`employees.manager_user_id = current_user.id`). Every "My Team"/"own team"/
"team-scoped" reference that described *access control* has been reworded to
"My Location"/"own location". This is a wording-only pass — colors,
typography, spacing, radii, shadows, and every other Section 1 value are
**unchanged** from Revision 2, and no component variant/state was added or
removed. Sections touched: §2.2 (Manager nav label), §5.2, §5.4, §5.12,
§5.14, §5.16 (per-route Manager-scoping descriptions), §5.23 (new Location
field added to the Users form/table, per BLUEPRINT §6.4). `employees
.manager_user_id` remains a **display-only** "reports to" field per
BLUEPRINT §3.4 and is unaffected by this revision — references to it as
display data (the "Manager" column in §5.3's Employees table, the "Manager"
row in §5.4's Profile tab, the "Manager Select" field in §5.5's employee
form) are unchanged, since they show an employee's reporting line, not an
access-control scope.

Input: `BLUEPRINT.md` (FINAL). Route inventory, roles, and data model are taken
as fixed and are **not** re-derived here — see `BLUEPRINT.md` Section 9 for
the authoritative route list and Section 3 for the data model backing every
field/enum referenced below.

This is an **internal operations tool**, not a marketing site. Every design
decision below optimizes for: data density, scan-ability, fast repeated task
completion (HR reviewing attendance daily, running payroll monthly, managers
approving leave), and zero ambiguity for bilingual (Albanian/English)
euro-denominated data. Visual flourish is intentionally minimized.

`frontend` must build every page from this document with zero open design
decisions. If a value isn't specified here, that is a gap in this document,
not a license to improvise — flag it rather than guessing.

---

## 0. Design Principles (governs every decision below)

1. **Density over whitespace.** Base UI text is 14px, not 16px. Tables are
   the primary UI surface; rows are compact (36–40px), not card-spaced.
2. **Status is always a color + a label**, never color alone (colorblind
   safety, and Albanian/English label swap must not break comprehension).
3. **Numbers align.** All numeric/currency columns are right-aligned with
   tabular figures, so HR can visually scan a payroll column top-to-bottom.
4. **Role scoping is visible, not just enforced.** A Manager's UI never shows
   a grayed-out/disabled version of an HR-only feature — it simply isn't in
   the nav or on the page. Absence of access is communicated by absence of
   the control.
5. **Every destructive or irreversible action (delete, finalize payroll,
   resolve a punch) requires an explicit confirmation dialog** — never a
   single accidental click.
6. **Bilingual by default.** No UI copy is ever hardcoded to one language in
   a way that breaks layout in the other — button/label containers must
   tolerate Albanian strings running ~20–30% longer than English equivalents
   (e.g. "Konfirmo" vs "Confirm", "Në pritje" vs "Pending").

---

## 1. Design System

### 1.1 Color Palette

Provide these as a Tailwind theme extension (`tailwind.config.js` →
`theme.extend.colors`). Values are final — do not adjust.

**Redesign note (Revision 2):** the accent color changed from a generic
saturated SaaS blue to a desaturated **muted cobalt**, and the `violet`
token was repurposed from a saturated indigo/violet (`#8B5CF6` — explicitly
disallowed by the design brief) to a desaturated **dusty plum**. Both are
*value-only* swaps: the Tailwind token keys `primary` and `violet` are
unchanged, so no component, class name, or import in the codebase needs to
change — only the hex values in `tailwind.config.js` do.

**Redesign note (Revision 4):** `primary` changed again, from muted cobalt to
**graphite**, to match the chronos logo mark's own near-black (`#232326`,
essentially true neutral gray — R≈G, B negligibly higher). `primary-700`
(hover/pressed) is set to that exact hex, so the button's pressed state
literally is the logo's own color. Deliberately *not* full monochrome:
`primary-600` (default/resting state, `#4A4A50`) stays visibly lighter than
`neutral-900` (`#0F172A`, used for headings/sidebar bg) so buttons and links
keep reading as actionable rather than blending into body text — chosen over
matching the logo exactly, which would have removed that visual cue. Same
non-collision reasoning as Revision 2 still holds (graphite has ~0
saturation, nowhere near the green/amber/red status triad or any of the
sage/terracotta/amber traps ruled out there).

**Primary (actions, links, active nav, focus rings) — Graphite**
| Token | Hex |
|---|---|
| primary-50 | `#F7F7F8` |
| primary-100 | `#EEEEF0` |
| primary-200 | `#D9D9DE` |
| primary-300 | `#B8B8C0` |
| primary-400 | `#8F8F99` |
| primary-500 | `#68686F` |
| primary-600 | `#4A4A50` ← default button/link/active-state color |
| primary-700 | `#232326` ← hover/active-pressed — the logo mark's own color |
| primary-800 | `#19191B` |
| primary-900 | `#101012` |

**Neutral (backgrounds, borders, text) — Slate**
| Token | Hex |
|---|---|
| neutral-50 | `#F8FAFC` ← app background |
| neutral-100 | `#F1F5F9` ← subtle hover fill (table row hover) |
| neutral-200 | `#E2E8F0` ← default borders/dividers |
| neutral-300 | `#CBD5E1` ← input borders |
| neutral-400 | `#94A3B8` ← disabled text, placeholder text |
| neutral-500 | `#64748B` ← secondary/meta text |
| neutral-600 | `#475569` ← icon default |
| neutral-700 | `#334155` ← form labels |
| neutral-800 | `#1E293B` ← primary body text on white |
| neutral-900 | `#0F172A` ← headings, sidebar background |

**Success (Green)** — used for: `present`, `approved`, `active`, `finalized`, online device
| success-50 `#F0FDF4` | success-100 `#DCFCE7` | success-500 `#22C55E` | success-600 `#16A34A` | success-700 `#15803D` |

**Warning (Amber)** — used for: `late`, `pending`, `draft`, unresolved punches
| warning-50 `#FFFBEB` | warning-100 `#FEF3C7` | warning-500 `#F59E0B` | warning-600 `#D97706` | warning-700 `#B45309` |

**Danger (Red)** — used for: `absent`, `rejected`, `terminated`, offline device, delete actions, validation errors
| danger-50 `#FEF2F2` | danger-100 `#FEE2E2` | danger-500 `#EF4444` | danger-600 `#DC2626` | danger-700 `#B91C1C` |

**Violet token, repurposed to Dusty Plum** — used for: `on_leave` status,
Manager role badge (visually distinct from Primary cobalt used for
actions). Token key stays `violet`; only the hex values below changed from
the old saturated indigo/violet scale.
| violet-50 `#F5F1F4` | violet-100 `#E9E0E6` | violet-500 `#8C7086` | violet-600 `#715A6C` | violet-700 `#5A4655` |

Non-collision check: dusty plum sits at hue ≈325°, ~15% saturation —
clearly distinct from cobalt primary (≈210°), success (≈142°), warning
(≈38°), and danger (≈0°). No two semantic colors in this palette can be
confused for one another even for a colorblind user relying on
lightness/position rather than hue, since Principle 2 (§0) already mandates
label text alongside every color use.

**Surface tokens (semantic aliases, define alongside the scales above)**
| Token | Value | Usage |
|---|---|---|
| `bg-app` | neutral-50 | page background |
| `bg-surface` | `#FFFFFF` | cards, tables, modals, inputs |
| `bg-sidebar` | `#232326` (Revision 4 — the logo mark's own near-black, no longer tied to neutral-900) | left nav |
| `border-default` | neutral-200 | card/table borders, dividers |
| `border-input` | neutral-300 | input/select/textarea borders |
| `text-primary` | neutral-900 | headings |
| `text-body` | neutral-800 | table cells, body copy |
| `text-muted` | neutral-500 | meta text, timestamps, helper text |
| `text-disabled` | neutral-400 | disabled control text |

### 1.2 Typography

Font family: **Inter** (self-hosted or `@fontsource/inter`; supports Albanian
diacritics ë, ç, and all Latin Extended-A glyphs). Fallback stack:
`Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.

**Monospace family (new, Revision 2): `JetBrains Mono`** (self-hosted or
`@fontsource/jetbrains-mono`, weights 400 and 500 only). Fallback stack:
`"JetBrains Mono", "SF Mono", ui-monospace, Menlo, Consolas, monospace`.
Register as a second Tailwind font family token, `font-mono` (i.e.
`theme.extend.fontFamily.mono`), alongside the existing `font-sans` (Inter).
See **Monospace Usage** below for exactly which elements use it — nothing
outside that list switches font family.

Numeric contexts (currency, minutes, dates, IDs) use `font-variant-numeric:
tabular-nums` so digits align in columns — apply via a `.tabular-nums`
utility class on every numeric table cell and KPI figure, **in addition to**
`font-mono` where the Monospace Usage list below calls for it (JetBrains
Mono is already tabular by default, but the explicit utility class stays
mandatory for the few numeric fields that render in `font-sans`, e.g. plain
integer counts that aren't on the mono list).

**Heading tightening (Revision 2):** three tokens — `text-page-title`,
`text-section-title`, `text-kpi` — are the only tokens that get tight
line-height and negative tracking. All other tokens are unchanged from
Revision 1 (body text at 14px stays at normal tracking/line-height for
readability; tightening small body copy hurts scan-ability more than it
helps the "tool-like" feel this brief wants).

| Style token | Size / line-height | Tracking | Weight | Color | Usage |
|---|---|---|---|---|---|
| `text-page-title` | 24px / 28px | `-0.02em` (tight) | 600 | neutral-900 | Page `<h1>`, top of every route |
| `text-section-title` | 18px / 24px | `-0.01em` (tight) | 600 | neutral-900 | Card/panel `<h2>`, tab panel titles |
| `text-group-label` | 14px / 20px, uppercase | `0.04em` (unchanged — uppercase eyebrow label, not a heading, needs *positive* tracking for legibility) | 600 | neutral-500 | Table group headers, form section dividers |
| `text-body` | 14px / 20px | `0` (normal) | 400 | neutral-800 | Table cells, paragraph text, primary body copy |
| `text-body-muted` | 14px / 20px | `0` | 400 | neutral-500 | Secondary table cell content, meta info |
| `text-caption` | 12px / 16px | `0` | 400 | neutral-500 | Helper text, timestamps under a value, footnotes |
| `text-label` | 14px / 20px | `0` | 500 | neutral-700 | Form field labels |
| `text-error` | 12px / 16px | `0` | 500 | danger-600 | Field validation error text |
| `text-kpi` | 30px / 32px (tightened from 36px) | `-0.02em` (tight) | 700 | neutral-900 | Dashboard KPI card big number — renders in `font-mono` (see Monospace Usage below) |
| `text-button` | 14px / 20px | `0` | 500 | (per variant) | Button label |
| `text-nav-item` | 14px / 20px | `0` | 500 | (per state) | Sidebar nav item |
| `text-badge` | 12px / 16px | `0` | 600 | (per variant) | Status pill label |

No font size smaller than 12px is used anywhere in the product.

#### Monospace Usage (exhaustive — nothing outside this list uses `font-mono`)

Applies to these fields wherever they render anywhere in the app (this list
is authoritative across all of Section 5 — it supersedes/fills in any
inline mention or silence there; no per-route re-specification needed):

1. **All timestamps** — date+time and date-only values: punch Actual
   In/Out, Scheduled Start–End, `last_synced_at`, `approved_at`/
   `rejected_at`, `created_at`, `Last Login`, "Finalized on dd.MM.yyyy by
   [name]" caption. When a date/time is embedded inside a prose sentence
   (like the "Finalized on…" caption), wrap only the date/time substring in
   `font-mono`, not the whole sentence.
2. `employees.employee_code` — table cells, detail-page subtitle, form
   display.
3. Device **IP Address:Port** and **Serial Number** — table cells and the
   device detail Connection card.
4. `attendance_logs` **Raw Status Code** (the numeric code only, per §5.13).
5. **All currency figures** — every `formatCurrency()` output, in tables,
   KPI cards, key:value grids, and the Adjustments list. Weight follows the
   surrounding text token (e.g. Net Pay stays `font-semibold`, just adds
   `font-mono` on top).
6. **Minute/day counters**: Late (min), Early Departure (min), Overtime
   (min), Break (min), Grace Minutes, Days (leave span), Annual Entitlement
   (days), payroll run Line Count. The numeral **and** its unit label both
   render in `font-mono` (e.g. `12 min`, `3 days`) so the string reads as
   one tool-like token, not mixed fonts mid-string.
7. `text-kpi` figures (all 4 dashboard KPI cards + the payroll run summary
   stat blocks, §5.19).

**Does not apply to:** names, addresses, notes/reasons, free text, form
labels, buttons, nav items, badge/status labels, group labels — anything
that is prose or a proper noun stays in `font-sans` (Inter).

**Inline "code chip" treatment** (visual texture): the four *identifier*
mono fields — Employee Code, Device IP:Port, Device Serial Number, and Raw
Status Code — additionally render with a subtle background chip wherever
they appear as a standalone cell/value: `font-mono text-xs bg-neutral-100
text-neutral-700 px-1.5 py-0.5 rounded-sm`, `inline-block`. Timestamps,
currency, and minute/day counters use `font-mono` only, **no chip** — the
chip is reserved for identifier-style data so it stays meaningful rather
than decorative.

### 1.3 Spacing Scale

Tailwind's default 4px-base spacing scale, used unmodified:
`1=4px, 2=8px, 3=12px, 4=16px, 5=20px, 6=24px, 8=32px, 10=40px, 12=48px, 16=64px`.

Fixed application rules (do not deviate per-component):
- Page content padding: `24px` (desktop/tablet), `16px` (mobile, <640px).
- Card/panel internal padding: `24px` (header/body), `16px 24px` (footer).
- Table cell padding: `10px 16px` (vertical 10px keeps rows compact at ~40px
  height including a 1px bottom border).
- Form field vertical gap: `20px` between fields, `32px` between form
  sections, `12px` between label and input.
- Button internal padding: sm `6px 12px`, md `8px 16px`, lg `10px 20px`.
- Gap between filter-bar controls: `12px`.
- Sidebar nav item padding: `6px 12px` (Revision 4 — tightened from `10px
  16px` so the full nav tree fits in the viewport without scrolling; `2px`
  vertical gap between items, icon size `18px` not `20px`).

### 1.4 Border Radius

| Token | Value | Usage |
|---|---|---|
| `rounded-sm` | 4px | badges, small inline chips, checkboxes |
| `rounded-md` | 6px | buttons, inputs, selects, textareas |
| `rounded-lg` | 8px | cards, modals, dropdown menus, KPI cards |
| `rounded-full` | 9999px | avatars, status dots, pill toggles (language switch), leave/status badges |

### 1.5 Shadows & Elevation

| Token | Value | Usage |
|---|---|---|
| `shadow-sm` | `0 1px 2px 0 rgba(15,23,42,0.06)` | cards at rest, inputs on focus (combined with ring) |
| `shadow-md` | `0 4px 6px -1px rgba(15,23,42,0.08), 0 2px 4px -2px rgba(15,23,42,0.06)` | dropdown menus, popovers |
| `shadow-lg` | `0 10px 15px -3px rgba(15,23,42,0.10), 0 4px 6px -4px rgba(15,23,42,0.08)` | modals, mobile drawers |
| focus ring | `outline: 2px solid <primary-600>; outline-offset: 2px` (see §1.9 for the Input/Select/Textarea-specific crisp-ring override, which replaces this for that component class only) | every focusable interactive element (`:focus-visible` only, not `:focus`) |

**Z-index scale:** content `0` · sticky topbar `20` · desktop sidebar `20` ·
dropdown/popover `30` · mobile drawer (nav or filters) `40` · modal backdrop
`50` · modal panel `51` · toast stack `60`.

### 1.6 Iconography

Icon set: **lucide-react** (consistent 1.5px stroke, matches Inter's
geometry). Icon sizes: `16px` inline with 14px text, `20px` in buttons/nav
items, `24px` in KPI cards and empty states. Icon color inherits `currentColor`
unless a status color is specified (e.g. status dots).

### 1.7 Breakpoints

Tailwind defaults, used unmodified: `sm 640px · md 768px · lg 1024px · xl
1280px · 2xl 1536px`. Primary design target is desktop (**≥1280px**, an
office PC) — see Section 4 for full per-breakpoint behavior. Mobile support
exists for viewport robustness (a manager glancing at their phone), not as a
first-class redesigned experience.

### 1.8 Data Formatting Rules (apply everywhere, no per-page exceptions)

- **Currency:** format is `€ X.XXX,XX` — euro symbol, non-breaking space,
  period as thousands separator, comma as decimal separator, always exactly
  2 decimals, tabular-nums, right-aligned in tables. This format is **fixed
  regardless of the active UI language** (Albanian or English toggle) — only
  interface copy translates, not number formatting, so HR never has to
  mentally re-parse figures when switching languages. Negative amounts
  (deductions) render as `− € 45,00` in `danger-600` text; positive
  bonuses/net pay render in `text-body`/neutral-900 (not green — green is
  reserved for status, not "good news" framing of money).
  Implement as a single `formatCurrency(amountEur: number): string` utility;
  every currency value in the app must go through it.
- **Dates:** `dd.MM.yyyy` (e.g. `22.08.2026`) everywhere, both languages.
- **Date + time:** `dd.MM.yyyy HH:mm` (24-hour clock, e.g. `22.08.2026
  14:35`) — used for punch timestamps, `last_synced_at`, `approved_at`.
- **Time only:** `HH:mm` 24-hour (e.g. `08:00`) — used for shift start/end,
  break windows.
- **Minutes:** displayed as plain integer + unit label, e.g. `12 min`
  (translated: `12 min` / `12 min` — same abbreviation both languages).
- **Relative time** (used only for `last_synced_at` in device list/detail):
  `"5 min ago"` / `"5 min më parë"` if <60 min, else falls back to the
  absolute `dd.MM.yyyy HH:mm` format.

### 1.9 Micro-interactions

Applies globally; Section 6 component entries reference this section rather
than repeating these values. Where a Section 6 entry gives a more specific
override, Section 6 wins.

**Buttons** (Primary, Secondary, Danger, Danger-outline — **not** Ghost/Link,
which stay flat with no press-scale since they carry no fill/border to
visually compress):
- Hover: `background-color` transition only, `150ms ease-out`. No scale, no
  shadow change, no glow.
- Active/pressed: `transform: scale(0.98)`, `100ms ease-out`, layered on top
  of the existing one-step-darker background already defined per variant in
  §6.1. Transform origin center. Combined transition:
  `transition: background-color 150ms ease-out, transform 100ms ease-out`.
- Focus-visible: unchanged from §1.5 — `outline: 2px solid <variant color>;
  outline-offset: 2px`. Buttons keep the offset-outline style (not the
  crisp doubled-ring below) because their filled/bordered shape already
  reads clearly with a detached ring.
- Disabled: zero hover/active/transform — cursor `not-allowed`, no visual
  transition at all.

**Inputs, Selects, Textareas** (crisp deliberate ring, overriding the
generic offset-outline for this component class only):
- Default → Focus transition: `border-color 100ms ease-out`.
- Focus-visible spec (exact, replaces §1.5's generic rule for this class):
  `border: 1px solid <primary-600>` (border changes from neutral-300 to
  primary-600) **plus** `box-shadow: 0 0 0 1px <primary-600>` — a second
  1px ring flush against the border, zero offset, zero blur radius. Reads
  as a crisp doubled line, never a floating halo.
- Error + focus: same doubled-line technique in `danger-500` instead of
  `primary-600` (`border-danger-500` + `box-shadow: 0 0 0 1px <danger-500>`).
- This override applies only to text/number/date/time/currency/search
  Inputs, Selects (including Searchable Select's trigger box), and
  Textareas. Checkboxes, Toggles, Radio options, Tabs, and nav items keep
  the generic §1.5 outline (they have no border to double up against).

**Badges / Status Dots:**
- Status Dot size is **`6px`** (Tailwind `h-1.5 w-1.5`) — this **supersedes**
  §6.9's previously specified `8px`/`h-2 w-2` (and the current codebase's
  `StatusDot` in `components/ui/Badge.tsx`, which also needs updating to
  match). Color-per-status rules in §6.9 are unchanged.
- Badge pill itself is unchanged: `rounded-full`, `padding 2px 10px`,
  `text-badge` (12px/600). Where §6.8 mentions an "optional leading dot,"
  that dot is also `6px`/`h-1.5 w-1.5`, with a `4px` gap between the dot
  and the label text (gap value not previously specified — now fixed at
  4px).
- No hover/active state on badges — never interactive, never a button.

**Dividers & structural texture:**
- Every horizontal divider already specified elsewhere in this document
  (Card header/footer borders, Form Section top-border, Table header/row
  borders, Sidebar group-label spacing, Tabs underline) continues to use
  `border-default`/neutral-200 — no new divider tokens are introduced. This
  is the product's primary "visual texture" device per the design brief,
  and it's already pervasive; nothing further to add structurally.
- **Esc hint (new):** every Modal (§6.17) and Confirmation Dialog (§6.18)
  panel renders a small keycap-styled hint immediately to the left of the
  `×` close icon-button: `Esc`, styled `font-mono text-xs text-neutral-400
  bg-neutral-100 border border-neutral-200 rounded-sm px-1.5 py-0.5`, `4px`
  gap from the `×` button. This is a direct affordance for real, already-
  specified behavior (Esc already closes/cancels every modal per §6.17) —
  it is not decorative, and no other keybinding hint is introduced anywhere
  in the product (this app has no command palette; do not add a `⌘K` hint
  or any shortcut that isn't already real and implemented).

---

## 2. App Shell & Navigation

### 2.1 Layout structure (desktop ≥1024px)

```
┌────────────┬──────────────────────────────────────────────┐
│            │  Topbar (56px height, sticky, bg-surface,      │
│  Sidebar   │  border-bottom border-default)                 │
│  240px     ├──────────────────────────────────────────────┤
│  bg-sidebar│                                                │
│  (neutral- │   Main content area                            │
│  900)      │   padding: 24px                                │
│            │   bg-app                                       │
│            │                                                │
└────────────┴──────────────────────────────────────────────┘
```

- Sidebar is fixed, full viewport height, `240px` wide, does not scroll with
  content. Collapsible to a `64px` icon-only rail via a toggle at its bottom
  (icon only, tooltip on hover shows label) — state persisted in
  `localStorage`. Below `1024px` it becomes an off-canvas drawer (Section 4).
- Topbar is sticky (`position: sticky; top: 0; z-index: 20`), `56px` height,
  contains (left to right): current page title (`text-section-title`,
  neutral-900) or breadcrumb when nested, spacer, Language Switcher, vertical
  divider, User Menu (avatar + name + role badge, opens dropdown: "Profile
  Settings" → `/settings/profile`, "Log out").

### 2.2 Sidebar content — role-scoped

Sidebar renders a **different nav tree per role**; items the current user
cannot access are not rendered at all (Principle 4).

**HR/Admin (`hr_admin`) nav tree:**
```
chronos [logo/wordmark, 24px, white, top of sidebar, 56px header block]
—
Dashboard                     → /
—
Employees                     → /employees
Shift Schedules                → /shift-schedules
Devices                        → /devices
Locations                      → /locations
—
Attendance
  Daily Status                 → /attendance
  Raw Logs                     → /attendance/logs
Leave                          → /leave
Payroll                        → /payroll/runs
—
Configuration
  Penalties                    → /config/penalties
  Overtime                     → /config/overtime
  Absence Rule                 → /config/absence-rule
  Leave Types                  → /config/leave-types
—
Settings
  User Accounts                → /settings/users
  My Profile                   → /settings/profile
```

**Manager (`manager`) nav tree:**
```
chronos
—
Dashboard                     → /
Attendance                     → /attendance   (label: "My Location")
Leave                          → /leave         (label: "My Location")
—
My Profile                     → /settings/profile
```

**Label note (updated 2026-08-22):** these two items were previously labeled
"My Team" under the old direct-report scoping rule. They are relabeled "My
Location" because Manager visibility is now location-based (BLUEPRINT
§6.2): a manager sees every employee whose `location_id` matches the
manager's own `users.location_id`, regardless of who they report to, so
"Team" would now be inaccurate (it would imply direct reports only). If the
current manager has no `location_id` assigned, both routes still render (the
nav item itself is not hidden — the manager still has the *role*), but the
page content renders the table's genuine Empty State (§6.10) rather than an
error, per BLUEPRINT §6.2's transition-behavior note and Principle 4 (§0):
absence of an assigned location means absence of *data*, not absence of the
page.

Section labels above ("Attendance", "Configuration", "Settings") render as
`text-group-label` with `16px` top margin from the previous group. Nav item
states: default (neutral-400 text, transparent bg), hover (neutral-100 text
on neutral-800 bg... i.e. lighten on dark sidebar: text `#F1F5F9`, bg
`#1E293B`), active/current route (bg `primary-600`, text `#FFFFFF`, left
`3px` accent bar not needed since full-pill fill is sufficient), disabled —
not used (items are omitted, never disabled).

---

## 3. Page Templates

Every route in Section 5 is built from one of these four templates. Do not
invent a fifth pattern.

### T1 — List Page
`Page header` → `Filter bar` → `Data table` → `Pagination footer`.
- **Page header:** `text-page-title` left, primary "+ New X" Button
  (top-right) if the role may create. Optional secondary button (e.g.
  "Export" — not in Phase 1 scope, omit unless a route explicitly needs it).
- **Filter bar:** horizontal row, `bg-surface`, `rounded-lg`, `border
  border-default`, padding `16px`, contains Search Input + relevant Select
  filters + Date Range where applicable, right-aligned "Clear filters" Link
  button (only visible when ≥1 filter active).
- **Data table:** see Component Map §6.10. Row click navigates to the
  detail/edit route; a trailing icon-button column holds explicit
  view/edit/delete actions only where row-click navigation would be
  ambiguous (e.g. list pages where the primary row action isn't "view").
- **Pagination footer:** page-size Select (10/25/50/100, default 25 per
  BLUEPRINT §4) + Prev/Next + "Page X of Y" — bottom of the table card,
  `bg-surface`, `border-top border-default`, padding `12px 16px`.

### T2 — Detail Page
`Page header (title + status badge + breadcrumb + action buttons)` →
optional `Tabs` → `Content sections` (Cards).
- Page header action buttons are right-aligned, ordered secondary→primary
  left-to-right (e.g. `[Edit] [Delete]` or `[Recompute] [Finalize]`),
  destructive actions always in Danger variant regardless of position.
- Tabs used only where a single entity has genuinely distinct sub-views
  (Employee detail — see §5.4). Otherwise sections stack vertically as
  separate Cards with `24px` gap.

### T3 — Form Page (Create/Edit)
Single-column Card, max-width `720px`, centered within the content area
(left-aligned on wide viewports, not centered in the full 1280px+ canvas —
i.e. `margin: 0` with `max-w-[720px]`, not `mx-auto`, so it sits directly
under the page header rather than floating center-screen).
- Grouped into `Form Section`s (see §6.13), each with a `text-group-label`
  header and a `border-default` top divider except the first.
- **Sticky footer bar** pinned to the bottom of the viewport (not the card)
  once the form scrolls: `bg-surface`, `border-top border-default`, `padding
  12px 24px`, contains `[Cancel] [Save]` right-aligned. `Cancel` is Secondary
  variant, navigates back without saving (confirms via native browser only
  if the form is dirty — no custom "unsaved changes" modal needed for Phase
  1, keep it simple per CLAUDE.md).

### T4 — Dashboard
`KPI card row` (4 cards, equal width, `16px` gap) → `Content panel(s)` below
(e.g. pending leave list). See §5.2 for exact composition per role.

---

## 4. Mobile Rules

Global rules apply to **every** route unless a per-page exception is listed
in §5. Breakpoints per §1.7.

### 4.1 Global responsive behavior

| Breakpoint | Sidebar | Topbar | Content padding | Filter bar | Tables |
|---|---|---|---|---|---|
| `≥1280px` (target) | Fixed, 240px, expanded | Full | 24px | Inline row | Full columns |
| `1024–1279px` | Fixed, 240px (or user-collapsed to 64px rail) | Full | 24px | Inline row, wraps to 2 lines if needed | Full columns, horizontal scroll permitted on wide tables (payroll lines) |
| `768–1023px` (`md`–below `lg`) | **Off-canvas drawer**: hidden by default, opened via hamburger icon button (24px, left of page title in topbar); overlay backdrop `rgba(15,23,42,0.5)`, drawer slides in from left, `280px` wide, closes on backdrop click or route change | Hamburger + title, language switcher + user menu collapse into a single "more" icon-menu if width is tight | 16px | Controls wrap to 2 rows; Search full-width on its own row | Table remains tabular but non-essential columns hidden per §4.2; horizontal scroll as fallback |
| `640–767px` (`sm`) | Off-canvas drawer (same as above) | Hamburger + title only; language + user menu inside the hamburger drawer's top section instead of topbar | 16px | Collapses into a "Filters" button that opens a bottom Drawer (slide up, `rounded-t-lg`, `shadow-lg`) containing all filter controls stacked vertically + "Apply"/"Clear" buttons | **Tables convert to a stacked card list**: each row becomes a `bg-surface border border-default rounded-md` card, padding 12px, with label:value pairs stacked vertically (label = `text-caption` muted, value = `text-body`); primary identifying field (name/date) at top in `text-body` font-medium; status badge top-right of the card |
| `<640px` | Same as sm | Same as sm | 12px | Same as sm | Same as sm |

### 4.2 Column priority for the sm/mobile card-list conversion

Every data table defines a "primary 2–3 fields" that remain visible as the
card's title/subtitle even at the smallest width; everything else appears as
stacked label:value rows inside the card. Defined per table in §6.10's table
inventory. Forms (T3) are single-column at every breakpoint already, so no
additional form-specific mobile rule is needed beyond padding.

### 4.3 Touch targets

Below `1024px` (touch-likely), minimum interactive target size is `40px ×
40px` (buttons/icon-buttons/checkboxes grow from their desktop sm size to
this minimum via padding, not font size change).

---

## 5. Visual Hierarchy per Route

Roles: `A` = hr_admin, `M` = manager, per `BLUEPRINT.md` §9 (authoritative —
not re-derived here).

### 5.1 `/login` — public

Not part of the app shell (no sidebar/topbar). Centered card on `bg-app`,
`max-width 400px`, `shadow-md`, `rounded-lg`, `padding 32px`.
Hierarchy top to bottom: chronos wordmark (24px, neutral-900, centered) →
`8px` gap → Language Switcher (top-right corner of the card, small) →
Username Input → Password Input (`type=password`) → inline error banner
(danger-50 bg, danger-700 text, `rounded-md`, `padding 12px`, only rendered
after a failed attempt: "Invalid username or password" / "Emri i
përdoruesit ose fjalëkalimi është i pasaktë") → primary "Log in"/"Kyçu"
Button, full width of the card. No "forgot password" flow (out of scope —
plain username/password per BLUEPRINT §6.1, account resets are an HR/Admin
action via `/settings/users`, not self-service).

### 5.2 `/` — Dashboard — A, M (scoped)

Template T4. KPI row (4 equal Cards, each: icon top-left `24px` in a
`rounded-full` tinted background matching the metric's status color, big
number `text-kpi` below, label `text-caption` muted below that):
1. **Present today** — success color accent, count of `status=present` for
   today, scoped: all active employees (A) / employees at the manager's
   assigned location only (M).
2. **Late today** — warning color accent, count of `status=late`.
3. **Absent today** — danger color accent, count of `status=absent`.
4. **Pending leave requests** — violet color accent, count of
   `leave_records.status=pending`, scoped to the manager's assigned
   location for M; card is clickable, navigates to `/leave?status=pending`.

Below the KPI row: a single Card, `text-section-title` "Pending Leave
Requests" / "Kërkesa Në Pritje", showing up to 5 most recent pending leave
rows (Employee name, Leave type badge, dates, `[Approve] [Reject]` inline
buttons for M and A) with a "View all" Link to `/leave?status=pending` in
the card header if more than 5 exist. If zero pending, render Empty State
("No pending leave requests" / "Nuk ka kërkesa në pritje").
A sees no company-wide chart/graph in Phase 1 (reports are query-filtered
table views per BLUEPRINT §4.11, not a charting surface — do not build
charts).

### 5.3 `/employees` — A

Template T1. Filter bar: Search Input (by name/employee_code), Location
Select (A only — no-op single option in Phase 1 but rendered per schema),
Employment Status Select (`active`/`inactive`/`terminated`/All). Table
columns: Employee Code, Name (first+last, font-medium), Location, Hire
Date, Base Salary (currency, right-aligned), Employment Status (badge),
Manager (name or "—"). Row click → `/employees/:id`. Primary action "+ New
Employee"/"+ Punonjës i Ri" → `/employees/new`.
Mobile card primary fields: Name (title) + Employee Code (subtitle);
Employment Status badge top-right of card; salary and hire date as
stacked rows.

### 5.4 `/employees/:id` — A (full), M (read-only, own location only)

Template T2. Header: `First Last` as title, Employee Code as subtitle
(`text-caption`), Employment Status badge next to title. Actions (A only):
`[Edit]` → `/employees/:id/edit`.
Tabs: **Profile** | **Device Enrollments** | **Shift Assignments** |
**Attendance History**.
- *Profile* tab: read-only key:value grid (2 columns desktop, 1 column
  mobile) — National ID, Hire Date, Base Salary, Location, Manager.
- *Device Enrollments* tab: small table (Device label, Device User ID,
  Enrolled At) + "+ Add Enrollment" button (A only) opening a Modal (Device
  Select + Device User ID text input).
- *Shift Assignments* tab: table (Shift Schedule name, Effective From,
  Effective To or "Current" badge) ordered newest first + "+ Assign Shift"
  button (A only) opening a Modal (Shift Schedule Select, Effective From
  date).
- *Attendance History* tab: same table component as `/attendance` (§5.9)
  pre-filtered to this employee, date range picker defaulting to current
  month.
M sees all 4 tabs but zero write controls anywhere in this page (no Edit
button, no "+ Add Enrollment"/"+ Assign Shift" buttons) — enforced by
omission per Principle 4, and only reachable for employees at the manager's
own assigned location (a direct URL to an employee record at a different
location returns a 403 page: centered message "You don't have access to
this record" / "Nuk keni qasje në këtë të dhënë", with a Button back to
`/`).

### 5.5 `/employees/new`, `/employees/:id/edit` — A

Template T3. Sections: **Basic Info** (First Name, Last Name, Employee Code,
National ID, Hire Date) → **Employment** (Location Select, Base Salary
[currency input], Manager Select [users with role=manager], Employment
Status Select — Status field hidden/defaulted to `active` on the `new` form
only).

### 5.6 `/shift-schedules` — A

Template T1. No filter bar beyond a Location Select and an "Active only"
Toggle (defaults on). Table columns: Name, Location, Working Days (compact
chip row, e.g. `Mon Tue Wed Thu Fri` highlighted, `Sat Sun` muted),
Grace Minutes, Active (badge). Row click → `/shift-schedules/:id/edit`.
Primary action "+ New Schedule" → `/shift-schedules/new`.

### 5.7 `/shift-schedules/new`, `/shift-schedules/:id/edit` — A

Template T3, but wider: `max-width 880px` (this form needs more horizontal
room than a standard form). Sections:
- **Schedule Info**: Name, Location Select, Grace Minutes Late (number
  input, suffix "min"), Active Toggle.
- **Weekly Pattern** (custom component, see §6.15 "Shift Day Grid"): 7 fixed
  rows, Monday→Sunday. Each row: Day label (fixed, not editable) → Working
  Day Toggle → (if on) Start Time input + End Time input → Break Windows
  repeater (each break: Start Time, End Time, "Paid" Toggle, remove `×`
  icon button) + "+ Add break" Link-button under the row's break list. If
  Working Day is off, the time/break controls for that row are hidden
  entirely (not disabled/grayed — removed from the row, row collapses to
  just the day label + toggle + muted "Not a working day"/"Jo ditë pune"
  text).
Save persists via the bulk `PUT /shift-schedules/{id}/days` call (per
BLUEPRINT §4.5) — all 7 rows submitted together on Save, not per-row.

### 5.8 `/devices` — A

Template T1. Filter bar: Location Select. Table columns: Label, Location, IP
Address:Port, Serial Number, Status (Status Dot + label: Active/Inactive
from `is_active`), Last Synced (relative time). Row click → `/devices/:id`.
Primary action "+ Register Device" → `/devices/new`.
Mobile card primary fields: Label (title) + IP:Port (subtitle); Status dot
top-right.

### 5.9 `/devices/new` — A

Template T3. Fields: Label, Location Select, IP Address, Port (default
`4370`), Serial Number (optional). No test-connection on the create form —
that only appears once the device exists (detail page), since
`test-connection` requires a saved device id.

### 5.10 `/devices/:id` — A

Template T2, no tabs (single content panel — page is short). Header: device
Label as title, Status Dot + Active/Inactive badge, `[Edit]` (opens the same
form fields as `/devices/new` inline in an Edit Modal rather than a separate
route — acceptable deviation from T3 since the field set is tiny; keep it
simple per CLAUDE.md) and `[Delete]` (Danger, opens Confirmation Dialog: "This
will stop syncing punches from this device. This cannot be undone." /
"Kjo do të ndalojë sinkronizimin e regjistrimeve nga ky pajisje. Nuk mund të
zhbëhet.").
Body, two Cards side by side on desktop (stacked on tablet/mobile):
1. **Connection** Card: IP:Port, Serial Number, Last Synced (absolute
   dd.MM.yyyy HH:mm + relative underneath in `text-caption`), primary Button
   "Test Connection" → shows an inline result banner directly below the
   button after the call resolves (success-50/danger-50 banner, "Reachable"
   / "I arritshëm" in success-700, or "Unreachable" / "I paarritshëm" in
   danger-700, plus the raw error detail in `text-caption` if failed) —
   button shows a Loading state (spinner replaces label) while the request
   is in flight, per §6.1.
2. **Sync** Card: secondary Button "Sync Now" / "Sinkronizo Tani" (manual
   trigger, proxies to worker per BLUEPRINT §4.3), disabled with a tooltip
   "A sync is already in progress" while a triggered sync is pending; a
   toast confirms "Sync started" on trigger (the actual result surfaces via
   `last_synced_at` updating, not a live progress bar — Phase 1 keeps this
   simple, no websocket).

### 5.11 `/locations` — A

Template T1, but no filter bar (Phase 1 will render a single row — table
renders as normal regardless, no special-casing for "only one row").
Columns: Name, Address, Timezone, Active (badge). Row click →
edit via Modal (small enough for a Modal instead of a full route — Name,
Address, Timezone Select [IANA list, defaulted `Europe/Belgrade`], Active
Toggle). Primary action "+ New Location" → same Modal, empty.
(Note: BLUEPRINT §9 does not list a separate `/locations/new` or
`/locations/:id` route — both create and edit are handled via Modal on the
list page, consistent with the route table.)

### 5.12 `/attendance` — A (all), M (own location, label "My Location")

Template T1. Filter bar: Date Range picker (defaults to today→today), 
Employee Select (searchable; for M, options pre-filtered to their assigned
location server-side per BLUEPRINT §6.2 — the dropdown never lists
employees outside scope), Location Select (A only), Status Select (multi:
present/late/absent/on_leave/holiday/not_scheduled).
Table columns: Date, Employee, Scheduled (Start–End as `08:00–16:00`),
Actual In, Actual Out, Late (min), Early Departure (min), Overtime (min),
Break (min), Status (badge), Excused (only rendered when Status=Absent — a
small check/x icon + "Excused"/"Unexcused" tag, editable inline by A only:
clicking it opens a 2-option inline menu, since `is_absence_excused` is
HR-overridable per BLUEPRINT §3.8).
A-only page-level action: "Recompute" Button in the page header, opens a
Modal (Date Range, optional Employee Select) → triggers
`POST /attendance/recompute`, confirmation toast on success. Not shown to M.
Mobile card primary fields: Employee name (title) + Date (subtitle); Status
badge top-right; Late/OT/Break minutes and scheduled/actual times as
stacked rows.

### 5.13 `/attendance/logs` — A

Template T1. Filter bar: Date Range, Employee Select, Device Select,
"Unresolved only" Toggle. Table columns: Timestamp (date+time), Device,
Employee (name, or a Warning-colored "Unresolved" badge if `employee_id` is
null), Punch Type (badge: Check-in/Check-out/Break-in/Break-out/
Unclassified — Unclassified rendered muted/neutral), Raw Status Code
(`text-caption`, `font-mono` with the identifier code-chip styling — see
§1.2 Monospace Usage — for the numeric code only).
Trailing action column: "Resolve" Button (only rendered on rows where
`employee_id` is null) → opens Modal "Resolve Punch" (Employee Select
[searchable, all active employees], on submit calls `PATCH
/attendance/logs/{id}/resolve`, success toast "Punch resolved and future
punches from this device ID will map automatically" /
"Regjistrimi u zgjidh; regjistrimet e ardhshme nga ky ID pajisje do të
mapohen automatikisht").
Mobile card primary fields: Employee (or "Unresolved" badge) as title,
Timestamp as subtitle; Punch Type badge top-right.

### 5.14 `/leave` — A (all), M (own location; sees approve/reject)

Template T1. Filter bar: Status Select (pending/approved/rejected/
cancelled/All, default "pending" when arriving from a dashboard link, "All"
otherwise), Employee Select (scoped for M), Date Range.
Table columns: Employee, Leave Type (badge, colored by `leave_types` — use
neutral outline badge with the type name, since leave type is an open admin
list not a fixed enum, so it cannot get a fixed color; color is always
neutral/outline for this one badge, only the *status* badge is
color-coded), Start Date, End Date, Days (computed span), Status (badge:
pending=warning, approved=success, rejected=danger, cancelled=neutral
strike-through text), Requested By.
Trailing action column, only for rows where `status=pending` **and** the
current user is authorized (A always; M only if the employee is at their
assigned location — already guaranteed by the row-scoped query):
`[Approve] [Reject]` small icon+label Buttons inline (Approve = success
outline, Reject = danger outline). Clicking either opens a small
Confirmation Dialog with an optional Notes textarea, then calls the
respective endpoint.
Primary action "+ New Leave Request" (A only — "no self-service", HR files
on behalf of the employee per BLUEPRINT §3.10) → `/leave/new`. Not shown to
M (they only approve/reject, never create).
Mobile card primary fields: Employee (title) + date range (subtitle);
Status badge top-right; Approve/Reject buttons full-width stacked at the
bottom of the card when applicable.

### 5.15 `/leave/new` — A

Template T3. Fields: Employee Select (searchable), Leave Type Select
(from `leave_types`, active only), Start Date, End Date, Notes (textarea,
optional). No Status field (always created as `pending`).

### 5.16 `/leave/:id` — A, M (own location)

Template T2, no tabs. Header: "Leave Request" / "Kërkesë për Leje" as title
subtitle showing Employee name, Status badge next to title.
Body, single Card, key:value grid: Employee, Leave Type, Start Date, End
Date, Days, Requested By, Notes, and — once actioned — Approved/Rejected By
+ Approved/Rejected At. If `status=pending` and the current user is
authorized, `[Approve] [Reject]` buttons render in the page header
(top-right), same Confirmation Dialog + Notes pattern as the list page.
A additionally sees `[Delete]` (Danger, only enabled while
`status=pending`, per BLUEPRINT §4.7) with a Confirmation Dialog.

### 5.17 `/payroll/runs` — A

Template T1. Filter bar: Year Select, Location Select. Table columns:
Period (e.g. "August 2026" / "Gusht 2026" — month name localized), Location,
Status (badge: draft=warning, finalized=success), Generated By, Line Count
(employee count in the run), Total Net Pay (currency, sum of lines,
right-aligned). Row click → `/payroll/runs/:id`. Primary action "+ New Run"
→ `/payroll/runs/new`.

### 5.18 `/payroll/runs/new` — A

Template T3, compact (`max-width 480px` — only 3 fields). Fields: Period
Year (number input, current year default), Period Month (Select of month
names, localized), Location Select. Submit button label "Generate Run" /
"Gjenero Listën" (not "Save" — this triggers a real computation, per
BLUEPRINT §5.5, so the verb should communicate that). On submit, navigates
to the created `/payroll/runs/:id` on success. If a run already exists for
that `(location, year, month)` per the DB unique constraint, show the field-
level error on Location: "A run already exists for this period and
location" / "Ekziston tashmë një listë për këtë periudhë dhe lokacion".

### 5.19 `/payroll/runs/:id` — A

Template T2, no tabs. Header: "Payroll — August 2026" / "Lista e Pagave —
Gusht 2026" as title, Status badge (draft/finalized) next to title.
Header actions: while `draft`, primary Button "Finalize Run" / "Finalizo
Listën" (opens Confirmation Dialog with explicit warning: "This will lock
the run and generate a payslip PDF for every employee. This cannot be
undone." / "Kjo do të kyçë listën dhe do të gjenerojë fletëpagesë PDF për
çdo punonjës. Nuk mund të zhbëhet."); while `finalized`, no Finalize button
(it's gone, not disabled), instead a muted `text-caption` "Finalized on
dd.MM.yyyy by [name]" under the title.
Above the table: a summary Card, 3–4 stat blocks in a row (Employees count,
Total Net Pay, Total Penalties, Total Bonuses) — same visual style as
dashboard KPI cards but smaller (`text-lg` figure instead of `text-kpi`).
Table (the payroll run lines) columns — this is the widest table in the
app, expect horizontal scroll below `xl`: Employee, Base Salary, Late (min),
Lateness Penalty (currency, danger-600 text), Overtime (min), Overtime Bonus
(currency), Absence Days, Absence Deduction (currency, danger-600), Paid
Leave (days), Unpaid Leave (days), Net Pay (currency, font-semibold,
neutral-900). Row click → `/payroll/runs/:id/employees/:employeeId`.
Mobile: this table's card-list primary fields are Employee (title) + Net
Pay (subtitle, prominent since it's the figure HR scans for); every other
column becomes a stacked label:value row inside the card — this is the one
table in the app where the mobile card is allowed to be tall/scrollable
given the column count, rather than trimming columns.

### 5.20 `/payroll/runs/:id/employees/:employeeId` — A

Template T2, no tabs. Header: Employee name as title, run Period as
subtitle, Status badge (draft/finalized) inherited from the parent run.
Header action: "Download Payslip" Button (secondary, icon: download) —
enabled only once `payslip_pdf_path` is populated (i.e. after finalize);
before that, shown disabled with `text-caption` note underneath: "Available
once the run is finalized" / "Do të jetë e disponueshme pas finalizimit".
Body: **Breakdown** Card — same fields as the run-line table row, presented
as a vertical key:value list (label left, value right, currency
right-aligned, tabular-nums) ending in a visually separated Net Pay row
(`border-top`, `text-lg font-semibold`).
**Adjustments** Card below (only while `draft`; while `finalized`, the same
card renders read-only with no "+ Add" button): table of existing
`payroll_adjustments` (Type badge [bonus=success outline / deduction=danger
outline], Amount, Reason, Created By) + "+ Add Adjustment" Button opening a
Modal (Type radio [Bonus/Deduction], Amount currency input, Reason text
input, required).

### 5.21 `/config/penalties`, `/config/overtime`, `/config/absence-rule` — A

These three follow one shared pattern (**T1 variant: Effective-Dated Config
List**), since BLUEPRINT §4.8 specifies `POST` always creates a new row
rather than mutating history. No delete action anywhere on these three
pages (history must be preserved for already-finalized payroll runs, per
BLUEPRINT §5.5).

Layout: Location Select filter at top (nullable = "All Locations" option).
Table, ordered by `effective_from` descending, with the row where
`effective_from ≤ today` and (`effective_to` is null or `≥ today`) **and**
`is_active` visually pinned/highlighted as "Current" (a small "Current" /
"Aktuale" badge in a leading column, success-colored, plus a subtle
success-50 row background tint) — all other rows render as plain history,
read-only-looking (neutral-500 text) even though they're technically still
viewable/editable records. Primary action "+ New Rule" → Modal (not a
separate route — kept as a Modal since fields are few and this is a
frequent, quick admin task) whose fields vary by page:

- **Penalties** (`/config/penalties`): Rule Type radio
  (`flat_per_minute`/`threshold_allowance`) — selecting one toggles the
  visible fields below via conditional rendering (not disabling): if
  `flat_per_minute`, show Rate per Minute (currency); if
  `threshold_allowance`, show Allowance Minutes (number) + Flat Amount
  (currency). Always-visible fields regardless of type: Max Daily Penalty
  (currency, optional), Early Departure Rate per Minute (currency, optional,
  default 0), Effective From (date), Location Select.
- **Overtime** (`/config/overtime`): Threshold Basis radio
  (`daily`/`weekly`) → conditionally shows Daily Threshold Minutes or Weekly
  Threshold Minutes. Always-visible: Rate per Hour (currency, required),
  Weekend Rate per Hour (currency, optional — helper text "Leave blank to
  use the standard rate" / "Lëreni bosh për të përdorur normën standarde"),
  Holiday Rate per Hour (currency, optional), Requires Pre-Approval
  (Toggle), Monthly Cap Minutes (number, optional), Effective From, Location
  Select.
- **Absence Rule** (`/config/absence-rule`): Rule Type (text input,
  defaulted `no_punch_no_leave`, since BLUEPRINT §3.13 defines it as an
  extensible string not a fixed enum — render as a plain text field, not a
  Select, with helper text explaining it's a rule identifier), Deduction
  Basis radio (`flat_amount`/`full_day_salary_fraction`) → conditionally
  labels the Deduction Value field ("Amount (€)" vs "Fraction of daily
  salary, e.g. 1.0"), Effective From, Location Select.
  This page additionally shows a one-time `info` banner (info/primary-50
  bg) above the table on first load if only the seed row exists: "This is
  the Phase 1 default rule. Confirm the final policy with the client before
  go-live." / "Ky është rregulli i parazgjedhur për Fazën 1. Konfirmoni
  politikën përfundimtare me klientin para nisjes." — this banner is
  dismissible (stored dismissed in `localStorage`, not a DB field).

### 5.22 `/config/leave-types` — A

Template T1 (simpler — this one *does* support in-place edit, no effective-
dating per BLUEPRINT §3.9/§4.7). Table columns: Name, Paid (Toggle,
directly editable inline in the table — clicking flips `is_paid` with an
inline save, no modal needed for a single boolean), Annual Entitlement
(days, editable inline number field), Requires Approval (Toggle, inline),
Active (Toggle, inline). Primary action "+ New Leave Type" → small Modal
(Name, Paid Toggle, Annual Entitlement number, Requires Approval Toggle
default on).

### 5.23 `/settings/users` — A

Template T1. No filter bar beyond a Role Select (All/HR Admin/Manager).
Table columns: Username, Role (badge: hr_admin=primary, manager=violet —
same violet used for the manager role badge in the topbar user menu, kept
consistent), Location (only meaningful for `manager` rows — shows the
location name in plain text, or a `warning`-colored "Unassigned" / "Pa
Caktuar" badge when `users.location_id` is null; renders as a plain "—" for
`hr_admin` rows, which never carry a location per BLUEPRINT §3.14), Linked
Employee (name or "—"), Active (Toggle inline), Last Login (date+time or
"Never" / "Kurrë"). Primary action "+ New Account" → Modal (Username,
Password [only on create; on edit this field is replaced by a "Reset
Password" Button that opens a nested confirm+new-password sub-modal], Role
Select, **Location Select** [see below], Linked Employee Select [optional,
searchable], Active Toggle).

**Location field (new, 2026-08-22 access-control change — BLUEPRINT
§3.14/§6.4):**
- **Label:** "Assigned Location" / "Lokacioni i Caktuar".
- **Type:** standard Select (§6.3), options populated from `GET /locations`
  (active locations only) — the same data source as every other Location
  Select in the app.
- **Conditional rendering, not disabling** (consistent with the pattern
  already established in §5.21): the field renders **only when Role =
  Manager** in the Modal. Switching Role from Manager to HR Admin unmounts
  the field and clears any selected value before submit; switching to
  Manager mounts it, initially empty (not pre-filled). `hr_admin` accounts
  never submit a `location_id` — per BLUEPRINT §3.14 this column does not
  apply to that role.
- **Required/optional:** visually marked required (red asterisk on the
  label) when shown, but **the form does not hard-block Save when it's
  left empty.** BLUEPRINT §6.2 explicitly defines a Manager with no
  assigned location as a valid, intentional transition state (every
  existing manager row gets `location_id = NULL` immediately after the
  migration, until HR assigns one) — so blocking Save here would contradict
  the data model. Instead, whenever Role = Manager and the field is empty
  (on open, or after being cleared), an inline **non-blocking** warning
  renders directly under the field: "This manager will see no attendance or
  leave data until a location is assigned." / "Ky menaxher nuk do të shohë
  të dhëna për vijueshmërinë apo lejet deri sa t'i caktohet një lokacion." —
  styled `text-caption` in `warning-600` (not `text-error`/danger-600 —
  this is a heads-up about scope, not a validation failure).
- The same unassigned state is surfaced in the table's Location column
  (above), so HR can spot managers with no location without opening each
  row individually.

### 5.24 `/settings/profile` — A, M

Template T3-like but rendered as two stacked Cards on one page (no
create/edit route split — this is a single persistent settings page).
1. **Change Password** Card: Current Password, New Password, Confirm New
   Password, "Save Password" Button.
2. **Language** Card: Language Switcher rendered large-form here (two full-
   width radio-style option cards: "Shqip" and "English", each showing a
   small flag-free text label only — no flag icons, since Albanian/Kosovo
   flag iconography can be a sensitivity point for an internal HR tool;
   text-only pill selection is safer and simpler), applies immediately on
   selection (no separate Save button for this card — persists to
   `localStorage` + reflected instantly via `react-i18next`).

---

## 6. Component Map

Every component below lists its variants and every state that must be
implemented (default / hover / active / focus / disabled / error as
applicable — "n/a" where a state doesn't apply to that component).

### 6.1 Button
**Variants:** Primary, Secondary (outline), Ghost (text-only, no border/bg),
Danger, Danger-outline, Link (inline text, no padding/border).
**Sizes:** sm (32px height, `text-sm`, padding `6px 12px`), md (36px height,
padding `8px 16px`, default), lg (40px height, padding `10px 20px`).
See §1.9 for the exact hover/active-press transition timing (`scale(0.98)`
on press, applies to Primary/Secondary/Danger/Danger-outline; excludes
Ghost/Link).
| State | Primary | Secondary | Danger |
|---|---|---|---|
| Default | bg primary-600, text white | bg white, border neutral-300, text neutral-700 | bg danger-600, text white |
| Hover | bg primary-700 | bg neutral-50, border neutral-400 | bg danger-700 |
| Active/pressed (+ `scale(0.98)`, §1.9) | bg primary-800 | bg neutral-100 | bg danger-800 (darken danger-700 by 10%) |
| Focus-visible | + 2px primary-600 outline, 2px offset | same | + 2px danger-600 outline |
| Disabled | bg neutral-200, text neutral-400, no hover/active, `cursor: not-allowed` | bg white, border neutral-200, text neutral-300 | bg danger-100, text danger-300 |
| Loading | spinner (16px, white, replaces label text but preserves button width via a hidden-but-space-reserved label), button non-interactive, same bg as default | same pattern, spinner in neutral-600 | same pattern, spinner in white |
Icon-only variant: square, `36×36` (md) or `32×32` (sm), icon centered,
no visible border for Ghost icon-buttons (used in table row actions).

### 6.2 Input (text, number, email/username, date, time)
Height `36px`, `padding 8px 12px`, `rounded-md`, `border 1px solid
border-input`, `bg-surface`, `text-body`.
| State | Style |
|---|---|
| Default | border neutral-300 |
| Hover | border neutral-400 |
| Focus | border primary-600, + crisp 1px ring per §1.9 (not the generic 2px offset outline) |
| Filled | no visual change from default (border stays neutral-300 once blurred) |
| Error | border danger-500, + `text-error` message below (`4px` gap), optional danger-50 bg tint |
| Disabled | bg neutral-50, border neutral-200, text neutral-400, `cursor: not-allowed` |
| Readonly | bg neutral-50, border neutral-200, text neutral-800 (readable but visibly non-editable) |
Date/Time inputs use native `<input type="date">` / `<input type="time">`
(explicit decision: no custom calendar-popover component is built for Phase
1 — native controls styled to match the input chrome above are sufficient
for an internal tool and avoid a large component-build surface).
**Currency Input** variant: same base style, `€` prefix rendered inside the
input's left padding (neutral-500, non-editable), value right-aligned,
`tabular-nums`, formats to 2 decimals on blur (typing is free-form numeric,
formatting applied on blur only, not per-keystroke).
**Search Input** variant: `magnifying-glass` icon (16px, neutral-400)
left-padded inside the field; once text is entered, an `×` clear icon-button
appears right-padded inside the field. Debounce: 300ms before firing the
filter query.

### 6.3 Select (native-styled single-select)
Same box model/states as Input. Chevron-down icon (16px, neutral-500)
right-padded inside, non-interactive decoration. Placeholder option
("All" / "Të gjitha" for filters, or field-specific like "Select
Employee…") renders in neutral-400 text until a real value is chosen.
**Searchable Select** variant (used for Employee/Manager pickers where lists
may be long — Discovery §11 confirms unbounded headcount): opens a popover
(`shadow-md`, `rounded-lg`, max-height `280px`, scrollable) with a Search
Input pinned at the top of the popover and a filtered option list below;
same trigger box styling as a normal Select.

### 6.4 Textarea
Same states as Input. Default `3` visible rows, `resize: vertical` only,
`min-height` locked to 3 rows.

### 6.5 Checkbox
`16×16`, `rounded-sm`, `border 1.5px solid neutral-300`.
| State | Style |
|---|---|
| Unchecked | white bg, neutral-300 border |
| Checked | primary-600 bg, white checkmark icon |
| Indeterminate | primary-600 bg, white horizontal dash icon |
| Hover (unchecked) | border neutral-400 |
| Focus | + focus ring |
| Disabled | bg neutral-100, border neutral-200, checkmark (if checked) in neutral-400 |

### 6.6 Radio Group
Same states/coloring as Checkbox but circular (`rounded-full`), used in
Modal option pickers (e.g. Penalty Rule Type). Options rendered as full
clickable rows (not just the 16px circle) — `padding 10px 12px`,
`rounded-md`, hover bg neutral-50, selected row gets a `1px primary-600`
border + primary-50 bg tint, per §5.21's conditional-field pattern.

### 6.7 Toggle/Switch
`40×22` track, `rounded-full`.
| State | Track | Thumb |
|---|---|---|
| Off | neutral-300 | white, left position |
| On | primary-600 | white, right position |
| Hover | darken track 10% | n/a |
| Focus | + focus ring around track | n/a |
| Disabled (off) | neutral-200 | neutral-100 |
| Disabled (on) | primary-200 | white |
Used for all boolean fields: `is_active`, `is_paid`, `requires_approval`,
etc. Inline-editable table toggles (§5.22, §5.23) show a small inline
spinner overlapping the thumb for ~300ms while the PATCH request is in
flight, then settle to the new state (optimistic UI is **not** used — wait
for the server response before flipping, to avoid showing a false state on
a failed request).

### 6.8 Badge / Status Pill
`rounded-full`, `padding 2px 10px`, `text-badge` (12px/600), no icon by
default (text-only pill is sufficient at this size; an optional leading
`6px` (`h-1.5 w-1.5`) dot, `4px` gap before the label — see §1.9 — is used
only for the two dot-based indicators in §6.9).

**Attendance daily status** (`attendance_daily_status.status`):
| Value | Background | Text |
|---|---|---|
| `present` | success-100 | success-700 |
| `late` | warning-100 | warning-700 |
| `absent` | danger-100 | danger-700 |
| `on_leave` | violet-100 | violet-700 |
| `holiday` | neutral-100 | neutral-600 |
| `not_scheduled` | neutral-100 (outline variant: transparent bg, neutral-300 border) | neutral-500 |

**Leave status** (`leave_records.status`):
| Value | Background | Text |
|---|---|---|
| `pending` | warning-100 | warning-700 |
| `approved` | success-100 | success-700 |
| `rejected` | danger-100 | danger-700 |
| `cancelled` | neutral-100 | neutral-500 (label text additionally rendered with `line-through`) |

**Employment status** (`employees.employment_status`):
| Value | Background | Text |
|---|---|---|
| `active` | success-100 | success-700 |
| `inactive` | neutral-100 | neutral-600 |
| `terminated` | danger-100 | danger-700 |

**Payroll run status:** `draft` = warning-100/warning-700, `finalized` =
success-100/success-700.

**Punch type** (`attendance_logs.punch_type`): all six values render as
neutral-outline badges (transparent bg, neutral-300 border, neutral-700
text) — punch type is informational, not a health/status signal, so it
doesn't use the success/warning/danger palette. Label mapping: `check_in_work`
→ "Check-in" / "Hyrje", `check_out_work` → "Check-out" / "Dalje",
`check_in_break` → "Break-in" / "Hyrje pushimi", `check_out_break` →
"Break-out" / "Dalje pushimi", `unclassified` → "Unclassified" /
"E paklasifikuar" (this last one gets a subtle warning-500 left border, 2px,
since it needs an admin's attention per BLUEPRINT §5.3.4, without using a
full warning badge which would overstate severity).

**Role badge** (`users.role`): `hr_admin` = primary-100/primary-700, label
"HR Admin"; `manager` = violet-100/violet-700, label "Manager" / "Menaxher".

### 6.9 Status Dot (small, non-text indicator)
`6px` (`h-1.5 w-1.5`) circle, `rounded-full` — see §1.9 (Revision 2
supersedes the earlier `8px`/`h-2 w-2` value) — used only for: (a) Device
active/inactive in the devices table (green `success-500` = active,
`neutral-300` = inactive), (b) Device connection test result
(`success-500` reachable, `danger-500` unreachable, `neutral-300`
untested/unknown, `warning-500` checking-in-progress — animated pulse via
`animate-pulse` while checking). Always paired with an adjacent text label
— never used as the sole signal.

### 6.10 Table / Data Grid
`bg-surface`, `rounded-lg`, `border 1px solid border-default`, contained
within a Card wrapper that also holds the pagination footer (§ Page
Templates T1).
- Header row: `bg-neutral-50`, `text-group-label` styling per column,
  `border-bottom 1px solid border-default`, sticky within the table's own
  scroll container (`position: sticky; top: 0`) for tall tables. Sortable
  columns show a chevron icon (neutral-400 default, primary-600 when that
  column is the active sort) — click toggles asc/desc.
- Row: `border-bottom 1px solid neutral-200` (not neutral-300 — subtler
  than the header/card border), `padding 10px 16px` per cell, hover bg
  `neutral-50`, clickable rows additionally get `cursor: pointer`.
- Numeric/currency columns: header label right-aligned, cell content right-
  aligned, `tabular-nums`.
- **Empty state:** centered within the table body area (`padding 48px 24px`),
  a 24px neutral-400 icon (contextual — e.g. inbox for lists, calendar for
  attendance), `text-body-muted` message ("No employees found" /
  "Nuk u gjetën punonjës"), and — only when caused by active filters, not a
  genuinely empty dataset — a "Clear filters" Link button underneath.
- **Loading state:** skeleton rows (5 rows of `neutral-100` pulsing
  rectangles matching each column's approximate width) replace the table
  body while the initial fetch is in flight; subsequent page/filter changes
  show a thin `2px` primary-600 indeterminate progress bar at the very top
  of the table card instead of a full skeleton swap (avoids layout jump on
  every filter change).
- **Row selection / bulk actions:** not used anywhere in Phase 1 — no table
  requires multi-row bulk operations per the route inventory, so no
  checkbox-select column is built.

**Mobile card-list conversion** (below `640px`, per §4.1/§4.2) — table
inventory with each table's designated primary title/subtitle fields:
| Table (route) | Card title | Card subtitle | Badge (top-right) |
|---|---|---|---|
| Employees | Name | Employee Code | Employment Status |
| Shift Schedules | Name | Location | Active |
| Devices | Label | IP:Port | Active status dot |
| Attendance Daily Status | Employee | Date | Status |
| Attendance Logs | Employee / "Unresolved" | Timestamp | Punch Type |
| Leave | Employee | Start–End dates | Status |
| Payroll Runs | Period | Location | Run Status |
| Payroll Run Lines | Employee | Net Pay (currency) | — |
| Config (penalty/overtime/absence) | Effective From | Location | "Current" (if applicable) |
| Leave Types | Name | — | Active |
| Users | Username | Location (or Linked Employee if role=hr_admin) | Role |
| Locations | Name | Timezone | Active |

### 6.11 Pagination Footer
`bg-surface`, `border-top 1px solid border-default`, `padding 12px 16px`,
flex row: left = page-size Select (10/25/50/100, default 25), center/right =
"Showing 1–25 of 143" / "Duke shfaqur 1–25 nga 143" (`text-caption`) +
`[< Prev]` `[Next >]` icon-buttons (Ghost variant, disabled at first/last
page). No numbered page-jump control — Prev/Next is sufficient given the
data volumes expected (Discovery §11: small-to-mid headcount).

### 6.12 Filter Bar
`bg-surface`, `rounded-lg`, `border 1px solid border-default`, `padding
16px`, flex row with `12px` gap, `flex-wrap` allowed at narrower widths per
§4.1. Contains Search Input, Select(s), Date Range (two Date inputs with an
en-dash separator label between them), and a right-aligned "Clear filters"
Link (Ghost/Link variant, only rendered when ≥1 non-default filter is set).

### 6.13 Card / Panel
`bg-surface`, `border 1px solid border-default`, `rounded-lg`, `shadow-sm`.
Optional header slot: `padding 16px 24px`, `border-bottom 1px solid
border-default`, contains `text-section-title` + optional right-aligned
action button/link. Body slot: `padding 24px`. Optional footer slot:
`padding 12px 24px`, `border-top 1px solid border-default`.

### 6.14 KPI Card (Dashboard)
Variant of Card, no header/footer dividers, `padding 20px`. Layout: icon
badge (`40px rounded-full`, tinted bg per metric color at 100-level,
icon in the 600-level color) top-left → `text-kpi` figure below → `text-
caption` label below that. Optionally the whole card is a clickable Link
(cursor pointer, hover: `shadow-md` transition) when it deep-links
elsewhere (e.g. "Pending Leave" → `/leave?status=pending`).

### 6.15 Shift Day Grid (custom, `/shift-schedules/new|:id/edit` only)
7 fixed rows (Mon–Sun), each row a horizontal flex band, `padding 12px 0`,
`border-bottom 1px solid neutral-200` (last row no border). Row anatomy:
`[Day label, 100px fixed, font-medium]` `[Working Day Toggle]` `[conditional:
Start Time input] [en-dash] [conditional: End Time input] [conditional:
Break Windows list]`. Break window sub-row (indented `16px`): `[Start Time]
[–] [End Time] [Paid Toggle + "Paid"/"E paguar" label] [× remove icon-
button]`, plus a trailing `+ Add break` Link-button. When Working Day is
toggled off, all conditional elements unmount and a single `text-caption`
neutral-400 "Not a working day" fills the row instead.
Mobile (`<768px`): each day row becomes its own bordered card stacked
vertically (not a horizontal band) — day label as the card header, toggle
top-right of that header, times/breaks stacked below.

### 6.16 Tabs
Underline style. Tab list: `border-bottom 1px solid border-default`, tabs
laid horizontally, each `padding 10px 4px`, `margin-right 24px`, `text-sm
font-medium`.
| State | Text color | Underline |
|---|---|---|
| Inactive | neutral-500 | none |
| Hover (inactive) | neutral-800 | none |
| Active | primary-600 | 2px primary-600, full tab width |
| Disabled | neutral-300 | none, `cursor: not-allowed` (not used in Phase 1 — all tabs are always available to whichever role can see the page at all) |

### 6.17 Modal / Dialog
Sizes: sm (`400px`), md (`560px`, default), lg (`720px`, used for the Shift
Day Grid if ever needed in a modal — not currently, that one's a full page).
Backdrop `rgba(15,23,42,0.5)`, panel `bg-surface`, `rounded-lg`, `shadow-lg`,
`padding 0` (header/body/footer each own their padding per §6.13's Card
slots). Header includes an `×` close icon-button (top-right, Ghost).
Immediately to the left of the `×` button, an `Esc` keycap hint renders per
§1.9. Closes on: `×` click, backdrop click, `Esc` key — **except**
Confirmation Dialogs for destructive actions (§6.18), which only close via
explicit button click (no backdrop/Esc dismiss, to prevent accidental
cancellation of an intended confirm... actually inverted: prevents
accidental *dismissal that the user might mistake for cancellation being
final* — practically, backdrop/Esc on a confirm dialog is treated
identically to clicking "Cancel", so this is a minor implementation note,
not a hard blocker, but Esc/backdrop must map to Cancel, never to silently
doing nothing).

### 6.18 Confirmation Dialog
Specialized Modal, sm size. Icon at top (danger-100 circle bg + danger-600
warning-triangle icon for destructive actions; warning-100/warning-600 for
non-destructive-but-consequential actions like Finalize). Title
(`text-section-title`), description (`text-body-muted`), footer `[Cancel]
[Confirm]` — Confirm button uses Danger variant for delete/irreversible
actions, Primary variant for consequential-but-not-destructive ones (e.g.
Approve leave uses a success-outline Confirm button instead, matching the
action's semantic color). Like every Modal (§6.17), the panel still shows
the `×` close icon-button plus the `Esc` keycap hint in its top-right
corner, even though the Icon+Title block below serves as the visual
header.

### 6.19 Toast / Notification
Fixed top-right stack, `16px` from viewport edges, `12px` gap between
stacked toasts, each `min-width 320px, max-width 420px`, `rounded-md`,
`shadow-md`, `padding 12px 16px`, left `4px` colored accent bar + icon:
success (success-600 bar/icon), error (danger-600), warning (warning-600),
info (primary-600). Auto-dismiss after `4000ms` for success/info; error and
warning toasts persist until manually dismissed (`×` icon-button,
top-right of the toast).

### 6.20 Breadcrumb
Used on nested detail/edit pages (e.g. `Employees / John Doe / Edit`).
`text-caption`, neutral-500, `/` separator in neutral-300, last (current)
segment in neutral-800 font-medium and non-clickable; all prior segments are
Links (hover: primary-600, underline).

### 6.21 Language Switcher
Two-option pill toggle, `bg-neutral-100`, `rounded-full`, `padding 2px`,
each option `padding 4px 12px`, `rounded-full`, `text-xs font-medium`.
Active option: `bg-white`, `shadow-sm`, `text-neutral-900`. Inactive:
transparent, `text-neutral-500`, hover `text-neutral-700`. Labels: "SQ" /
"EN" in the compact topbar placement (§2.1); full "Shqip" / "English" in the
large-form placement on `/settings/profile` (§5.24).

### 6.22 Avatar
`rounded-full`, sizes `32px` (topbar user menu) / `24px` (compact contexts,
not heavily used given this is a text-table-dense app, not a social one).
Shows initials (first letter of first + last name, uppercase, `text-xs
font-semibold`, white text) on a background color deterministically derived
from the user's name (hash the name to pick from a fixed 6-color set:
primary-500, violet-500, success-600, warning-600, `#0EA5E9` [sky-500,
additional accent added solely for avatar variety], `#EC4899` [pink-500,
same reason]) — no photo upload exists in Phase 1.

### 6.23 Empty State (standalone, larger than the inline table empty-state
in §6.10 — used for whole-page-empty scenarios, e.g. no leave types
configured yet)
Centered block, `padding 64px 24px`, `48px` icon (neutral-300), `text-
section-title` message, `text-body-muted` sub-message, optional primary
Button CTA below.

### 6.24 File Download Button
Secondary Button variant with a `download` icon (16px) leading the label.
While the file is being fetched/streamed, shows the Loading state per
§6.1. If the request fails (e.g. PDF not yet generated), a toast (danger
variant) reports the error rather than a silent failure.

### 6.25 Form Section
Wrapper used inside T3 forms: `text-group-label` heading, `8px` gap, then
fields, `32px` bottom margin before the next section, `border-top 1px solid
border-default` + `24px` top padding on every section after the first
(first section has no top border).

### 6.26 Inline Field Error / Form-level Error Banner
Field-level: `text-error` (12px, danger-600) directly under the offending
input, `4px` gap, paired with the input's border turning danger-500.
Form-level (e.g. a 409 conflict or non-field-specific 400 from the API):
banner at the top of the form Card, `bg-danger-50`, `border 1px solid
danger-200`, `rounded-md`, `padding 12px 16px`, `text-sm text-danger-700`,
dismissible `×`.

### 6.27 Skeleton Loader
`bg-neutral-100`, `rounded-sm`, `animate-pulse`. Used for: table body rows
(initial load, §6.10), KPI card figures (dashboard initial load — icon +
label render immediately, only the number area shows a skeleton block sized
to match `text-kpi`'s line-height), detail page key:value grids (each value
cell shows a skeleton block matching its expected text width class).

### 6.28 Drawer (mobile off-canvas: nav and filters)
`bg-surface`, `shadow-lg`. Nav drawer: slides from left, `280px` wide, full
height, backdrop `rgba(15,23,42,0.5)`. Filter drawer: slides from bottom,
`rounded-t-lg`, `max-height 80vh` (scrollable if content exceeds), backdrop
same. Both dismiss on backdrop click, `×` icon-button (top-right of the
drawer's own header), or (nav drawer only) on route navigation.

---

## 7. Done-Condition Checklist (self-verification, not part of the spec output)

- Design system: palette (concrete hex), type scale (concrete px/weight),
  spacing (concrete px), radii (concrete px), shadows (concrete box-shadow
  values) — **all present, Section 1.**
- Visual hierarchy per page/route from `BLUEPRINT.md` §9 — **all 26 routes
  covered explicitly, Section 5** (`/locations/new` and `/locations/:id`
  intentionally folded into the `/locations` list-page Modal pattern per the
  note in §5.11, since BLUEPRINT §9 does not list them as separate routes).
- Component map: every reusable component, variants, states — **Section 6,
  28 components.**
- Mobile rules: breakpoints + per-breakpoint behavior for every page —
  **Section 4 (global rules) + per-route mobile notes embedded in Section 5
  and the table inventory in §6.10.**
- Manager scoping wording — **Revision 3:** every Manager-scoping
  description in Sections 2 and 5 reflects location-based access
  (`users.location_id`) per `BLUEPRINT.md` §6.2, not the superseded
  team/direct-report rule; the new Users-form Location field is fully
  specified in §5.23 (label, type, data source, conditional rendering,
  required/optional behavior, validation/warning copy).
