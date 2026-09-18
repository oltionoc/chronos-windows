# chronos — Windows edition

Bilingual (Albanian/English) attendance and payroll system for multi-location
businesses in Kosovo. Punches come off fingerprint/face terminals, the system
turns them into lateness, overtime, absence and leave, and produces a monthly
payroll run.

**This folder is the Windows edition**: the same application, delivered as a
normal Windows installer (`ChronosSetup.exe`) instead of Docker, with the
server and worker compiled to machine code. See
[Windows installer](#windows-installer) below. The Docker-based line lives
unchanged in `chronos-beta`.

The client's staff get their own non-technical Albanian manual, served by the
app itself at `http://<pc-ip>:8080/manuali.html` and linked from the sidebar
as **Manuali** — it opens with no internet connection. The markdown source is
[`client/MANUALI.md`](client/MANUALI.md); edit it and
`frontend/public/manuali.html` together, they do not track each other.

---

## What's in this repository

```
backend/    FastAPI + SQLAlchemy + Alembic (the API and all payroll logic)
worker/     Polls the terminals, pushes punches into the API
frontend/   React + Vite + Tailwind (the web app, Albanian + English)
ops/        backup.sh, restore.sh, release.sh (Docker deployment)
client/     Docker deployment bundle for a client PC (no source code)
packaging/
  nuitka/     compile flags, shared by the Linux check and the Windows build
  windows/    installer: build.ps1, chronos.iss, install/uninstall/backup/restore
  linux-compile-check.sh
.github/workflows/windows-installer.yml   builds + installs + tests the .exe on Windows
docker-compose.yml               development stack, builds from source
docker-compose.native-test.yml   runs the native (Windows-style) topology for tests
```

Internal build documents (`BLUEPRINT.md`, `SECURITY_REPORT.md`,
`BACKEND_NOTES.md`, …) stay in this repo and are never shipped to a client.

---

## Windows installer

### What the client's PC gets

One `ChronosSetup-<version>.exe`. Running it (as Administrator) installs:

| Where | What |
|---|---|
| `C:\Program Files\Chronos\server\chronos-server.exe` | API + web UI, **compiled** (Nuitka) — Windows service **ChronosServer**, port 8080 |
| `C:\Program Files\Chronos\worker\chronos-worker.exe` | device sync, **compiled** — service **ChronosWorker**, listens on 127.0.0.1 only |
| `C:\Program Files\Chronos\pgsql\` | PostgreSQL 16 — service **ChronosPostgres**, 127.0.0.1:55432 only |
| `C:\ProgramData\Chronos\chronos.env` | config + generated secrets, readable by SYSTEM/Administrators only |
| `C:\ProgramData\Chronos\pgdata\` | the database |
| `C:\ProgramData\Chronos\backups\` | nightly verified dumps (task **Chronos Backup**, 02:30 and at boot) |
| `C:\ProgramData\Chronos\logs\` | install log and service logs |

Plus a firewall rule for TCP 8080 on **private/domain networks only**, and a
desktop shortcut to `http://localhost:8080`. No Docker, no WSL, no Python.

**No readable source ships.** The only Python files on disk are the database
migration scripts, which alembic loads from files by design; they contain
schema definitions only, which the database exposes anyway. The build fails
if any other `.py` file ends up in it. Honest limit: compiled code can still
be reverse-engineered by someone with administrator rights and a lot of time —
pair this with not giving the client admin on that PC, and a signed licence.

### Building it

Nuitka cannot cross-compile, so the Windows executables are built on
Windows. Two ways:

- **GitHub Actions (recommended).** Push this repo to GitHub, then Actions →
  *Windows installer* → *Run workflow* (or push a tag like `v0.1.0`). The
  job builds the installer on a clean Windows machine, **installs it there**,
  checks services, web UI, login, backups, that internal endpoints refuse the
  network and that no source shipped, re-runs it as an upgrade, uninstalls,
  and uploads `ChronosSetup-<version>.exe` as an artifact.
- **On a Windows PC** with Python 3.12, Node 20, Visual Studio Build Tools
  and Inno Setup 6: `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1 -Version 0.1.0`.

Before either, `./packaging/linux-compile-check.sh` compiles both programs on
Linux with the **same Nuitka flags** (`packaging/nuitka/*.args`) and runs
them; most compiled-build failures (modules loaded by name, missing data
files, missing package metadata) show up there first and much faster.

### Installing on site

1. Copy `ChronosSetup-<version>.exe` to the PC, run it as Administrator.
2. When it finishes, open `http://localhost:8080` (desktop shortcut) and sign
   in as `admin` / `ChangeMe123!` — you are forced to change it.
3. **Copy `C:\ProgramData\Chronos\chronos.env` somewhere safe, off that
   PC.** Its secrets cannot be recovered from a backup.
4. Continue with [First-run configuration](#3-first-run-configuration-in-this-order).

Other PCs on the office network reach it at `http://<that-pc-ip>:8080`.

### Upgrading, removing, restoring

- **Upgrade:** run the newer `ChronosSetup` over the old one. It stops the
  services, replaces the programs, keeps `chronos.env` and the database,
  migrates, and starts everything again.
- **Uninstall:** Windows Settings → Apps → Chronos. Services, firewall rule
  and backup task are removed; **the database, backups and config are kept**
  in `C:\ProgramData\Chronos`. Delete that folder by hand only if you mean it.
- **Restore a backup** (Administrator PowerShell):
  `& "C:\Program Files\Chronos\scripts\restore.ps1" -DumpFile "C:\ProgramData\Chronos\backups\<file>.dump"`
- **If setup reports it could not finish:** `C:\ProgramData\Chronos\logs\install.log`.
  Service output is next to it (`ChronosServer.out.log`, `ChronosWorker.out.log`).

---

## 0. One-time setup, before the first client

### GitHub (private)

```bash
cd chronos-beta
git add -A
git commit -m "chronos beta"
git branch -M main
git remote add origin git@github.com:<your-user>/chronos.git   # create it PRIVATE
git push -u origin main
```

`.gitignore` already excludes `.env`, `backups/`, `node_modules/`, `.venv/`.
Verify with `git status` before the first commit that no `.env` is staged.

### Container registry (private)

Docker Hub or GitHub Container Registry, either works. What matters is that
the repositories are **private** — this is what keeps your code off the
client's machine.

```bash
docker login                                   # or: docker login ghcr.io
REGISTRY=docker.io/<your-user> ./ops/release.sh beta
```

That builds and pushes three images: `chronos-api`, `chronos-worker`,
`chronos-frontend`. Check the registry afterwards and confirm the
repositories are marked private.

---

## 1. Device installation day

The terminal (Hikvision DS-K1T804 series, or a ZKTeco K40) is on the same LAN
as the PC that will run chronos.

1. **Power and network.** Plug in, connect Ethernet, note the IP the router
   gives it. Prefer a DHCP reservation so the address never changes.
2. **Activate the device** if it's new (it refuses everything until activated)
   and set an admin password. **Write that password down.** Hikvision locks
   the account for ~30 minutes after about five failed attempts, and each
   further attempt restarts the timer.
3. **Set the device clock and timezone.** Do this before anyone badges. A
   terminal left on its factory timezone stamps every punch with the wrong
   time, and lateness and overtime are then wrong by exactly that much. This
   is not theoretical — it has already happened once during testing.
4. **Turn on attendance mode** so staff can pick check-in, check-out, break
   and overtime rather than just "access granted". Without it every punch
   arrives unlabelled and the system has to infer the meaning from the order
   of punches.
5. **Enrol the staff** on the device (fingerprint/face/card) and write down
   each person's device user ID. You need those IDs in step 3 below.

---

## 2. Install chronos on the client's PC

Windows 10/11 or Linux. Needs Docker Desktop (Windows) or Docker Engine
(Linux). Give the PC a static LAN IP.

Copy **only the `client/` folder** onto that machine:

```
docker-compose.yml
.env.example
ops/backup.sh
ops/restore.sh
MANUALI.md
```

Then:

```bash
cp .env.example .env
# fill in REGISTRY, and generate the three secrets:
openssl rand -hex 32     # JWT_SECRET
openssl rand -hex 32     # INTERNAL_API_KEY
openssl rand -hex 32     # POSTGRES_PASSWORD
# set CORS_ORIGINS to http://<this-pc-lan-ip>:8080

docker login             # your registry account
docker compose pull
docker logout            # do not leave your registry credentials there
docker compose up -d
```

Open `http://<pc-ip>:8080` from another machine on the LAN to confirm it is
reachable, not just from the PC itself.

**Keep a copy of that finished `.env` somewhere safe and off that machine.**
The secrets are not recoverable from a database backup.

---

## 3. First-run configuration, in this order

Order matters — each step depends on the one before.

1. **Log in** as the bootstrap admin and change the password immediately (the
   app forces this).
2. **Locations** — create each real location.
3. **Devices** — add the terminal: IP, port, and for Hikvision the username
   and password. Press **Test Connection**. It confirms reachability *and*
   reports the device clock; fix the clock now if it complains.
4. **Employees** — real headcount, real base salaries.
5. **Device enrolments** — map each employee to their device user ID from
   step 1.5. Get this wrong and their punches arrive as "unresolved".
6. **Shift schedules** — real hours, breaks, grace minutes; split shifts where
   they exist. Then assign them to employees.
7. **Holidays** — `Configuration > Holidays`. **Do not skip this.** An empty
   holiday calendar means every public holiday is recorded as an unexcused
   absence and deducted from wages.
8. **Penalty / Overtime / Absence rules** — the client's real policy numbers,
   not the testing placeholders. Confirm each number with the client in
   writing before go-live.
9. **Manager accounts** — one per location, each with its location assigned.
10. **Badge a full test day yourself** before staff use it: check in, break
    out, break in, check out. Then look at Daily Status and confirm the
    numbers are what you expect.

---

## 3b. When the device refuses: "Device rejected the request: HTTP 401"

This is not a network problem. The terminal answered and rejected the
credentials. The important part first:

> **Stop pressing Test Connection.** Hikvision terminals lock the admin
> account after about five failed attempts, for about thirty minutes, and
> **every further attempt restarts that timer**. Retrying is what turns a
> one-minute fix into a half-hour wait. This has already happened once during
> testing.

### 1. Check what chronos has stored, before touching the device

- The **username** must be the account whose password you set at activation,
  normally `admin` — not your own name.
- chronos never displays a stored device password back to you. If the device
  was added with that field empty, the request goes out with no secret and the
  device answers 401. Re-enter it and save.
- Changing a device's address, port or type also **requires re-entering the
  password in the same save** (otherwise the stored secret would be sent to a
  new target — see `_RETARGETING_FIELDS` in `backend/app/routers/devices.py`).
  A save that was rejected for that reason leaves the row unchanged.

### 2. Ask the device once what it objects to

One request. Not a loop, not a script:

```bash
curl -s -i --digest -u 'admin:<password>' http://<device-ip>/ISAPI/System/deviceInfo
```

The body of the 401 names the cause:

| In the response | Meaning | What to do |
|---|---|---|
| `badPassword` | Wrong password | Fix the stored credentials, then **one** attempt |
| `userLocked`, or `lockStatus: lock` with `unlockTime: <seconds>` | Locked out by earlier attempts | Wait out `unlockTime` and touch nothing. `retryLoginTime` shows how many attempts remain after it unlocks |
| `notActivated` / `<isActivated>false</isActivated>` | Factory-fresh or restored device | Activate it first; no login works until then |
| HTTP 200 with device details | Credentials are fine | The problem is in the stored row, not the device |

### 3. Activation, if that is what it says

A new or restored device refuses everything until activated, and it has no web
UI on the K1T series, so do it over ISAPI:

```bash
curl -s -X PUT --digest -u 'admin:<new-password>' \
  -H 'Content-Type: application/xml' \
  -d '<ActivateInfo><password><new-password></password></ActivateInfo>' \
  http://<device-ip>/ISAPI/System/activate
```

`hasActivated` in the reply means it was already activated — then the issue is
the password, not activation.

### 4. Last resort

A device-side restore to defaults clears the password **and** every enrolled
fingerprint and face, so everyone has to be enrolled again and the device
re-activated. Treat it as the end of the list, not the start.

---

## 4. Ongoing

- **Alerts page, daily.** Everything the system detects goes there: missing
  check-outs, unresolved punches, a terminal that stopped syncing, a drifted
  device clock, overtime awaiting approval, failed backups.
- **Backups.** The `backup` service dumps the database nightly into
  `./backups`, verifies each dump, keeps 14 days, and the app raises an alert
  if it stops working. **Copying those files off that machine is still
  manual** — arrange a USB disk, a network share or cloud sync, and check it
  actually happens. A backup on the same disk as the database is not a backup.
- **Restore drill.** Run `./ops/restore.sh backups/<file>.dump` into a test
  machine once, before go-live. An untested restore is not a backup either.
- **Upgrades.** Build and push a new tag, then on the client machine set `TAG`
  in `.env` and run `docker compose pull && docker compose up -d`. Database
  migrations run automatically on start.

---

## 5. Keeping your source code off the client's machine

Realistic, in order of how much they actually achieve:

**What works:**

1. **Ship images, not source.** The `client/` bundle has no source and no
   build context. There is nothing to copy off that PC except compiled
   artefacts.
2. **Private registry.** Log in, pull, log out. Without your credentials they
   cannot pull the images again elsewhere, and cannot browse your other tags.
3. **Don't give them Docker admin.** On Windows, whoever is in the
   `docker-users` group can run `docker exec` and `docker cp`, which means
   reading anything inside a container. Set the PC up with an ordinary user
   account for daily use, keep the administrator account to yourself, and hand
   over the app through the browser only.
4. **Contract.** A licence clause naming the software as yours, with no right
   to copy, decompile or redistribute. In practice this is the protection that
   matters most, because the technical measures below are all bypassable by
   anyone with administrator rights on the machine.

**Be honest with yourself about the limits:**

- Python code inside an image is recoverable by anyone with admin on that
  machine. Shipping `.pyc` only raises the effort slightly; it is not
  protection.
- The frontend is JavaScript served to a browser. Minified, but readable.
- Full protection would mean not running it on their hardware at all — hosting
  it yourself and selling access. That is the real answer to "they must never
  have the code", and worth considering once there are several clients.

---

## 6. If they insist on on-premise for 14 locations

Two shapes, pick deliberately:

- **One stack per location.** Simple, isolated, no WAN dependency. Fourteen
  machines to maintain, fourteen sets of backups, no cross-location reporting.
- **One central stack, terminals reaching it over the network.** One machine to
  maintain, real multi-location reporting, but every location depends on that
  connection and on that one box staying alive.

For a client this size, central plus a solid backup and a spare machine is
usually right. Either way, `location_id` scoping already isolates managers to
their own location, so the data model does not change between the two.

---

## Development

```bash
cp .env.example .env     # fill in secrets
docker compose up -d --build
# tests (needs the stack running):
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

The test suite runs against the real running stack over HTTP — no mocks. It
creates and deletes its own data, prefixed with a per-run suffix.
