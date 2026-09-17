# chronos — beta

Bilingual (Albanian/English) attendance and payroll system for multi-location
businesses in Kosovo. Punches come off fingerprint/face terminals, the system
turns them into lateness, overtime, absence and leave, and produces a monthly
payroll run.

This README is the operator's runbook: what YOU do, in order, from the day the
device is installed. The client's own manual is a separate, non-technical
Albanian document: [`client/MANUALI.md`](client/MANUALI.md).

---

## What's in this repository

```
backend/    FastAPI + SQLAlchemy + Alembic (the API and all payroll logic)
worker/     Polls the terminals, pushes punches into the API
frontend/   React + Vite + Tailwind (the web app, Albanian + English)
ops/        backup.sh, restore.sh, release.sh
client/     Everything that goes on the CLIENT's machine (no source code)
docker-compose.yml   Development stack, builds from source
```

Internal build documents (`BLUEPRINT.md`, `SECURITY_REPORT.md`,
`BACKEND_NOTES.md`, …) stay in this repo and are never shipped to a client.

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
