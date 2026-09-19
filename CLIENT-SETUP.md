# Chronos — setting up at a client (Windows)

Step-by-step for installing Chronos on a client's PC with the Windows
installer. Written for the person doing the install (you), not the client.
For how the app is used day to day, see the Albanian manual at
[`client/MANUALI.md`](client/MANUALI.md) (also served in-app at
`http://<pc-ip>:8080/manuali.html`).

There is no Docker and no separate database to install — the one
`ChronosSetup.exe` sets up everything: the app, the worker, PostgreSQL, the
nightly backup, and a firewall rule.

---

## Before you go

- [ ] **Build the installer.** Push the repo, then GitHub → Actions →
      *Windows installer* → Run workflow. Download the
      `ChronosSetup-<version>.exe` artifact from the finished run. Keep your
      own copy — GitHub deletes artifacts after 90 days.
- [ ] **Have the licence in mind.** The beta build stops working on
      **10 November 2026**. To run past that, mint a key on your machine with
      `python sign_license.py --to "Client" --expires <date>` (see
      `packaging/license/README.md`) and paste it in after install.
- [ ] **Know the network.** The client PC needs a fixed LAN IP, and the
      attendance terminal must be on the same network.

---

## 1. The attendance terminal

Do this before, or alongside, the PC install.

1. Power it, connect it to the network, note its IP (set a DHCP reservation
   so it never changes).
2. If it is new, **activate it** and set an admin password. **Write the
   password down** — after ~5 wrong tries it locks for ~30 minutes, and each
   further try restarts the timer.
3. **Set its clock and timezone** before anyone badges. A wrong clock makes
   every lateness and overtime figure wrong by that much.
4. Turn on **attendance mode** so staff can pick check-in / check-out /
   break / overtime.
5. **Enrol the staff** (finger/face/card). You do not need to write down each
   ID — Chronos can read the enrolled users off the device later.

---

## 2. Install Chronos on the PC

Windows 10 or 11. You need to be an **administrator** on the PC.

1. Copy `ChronosSetup-<version>.exe` onto the PC.
2. Right-click it → **Run as administrator**. Click through; it sets up the
   database and services itself (about a minute). A desktop shortcut,
   **Chronos**, is created.
3. It is done when the shortcut opens `http://localhost:8080` and you see the
   login page.

If setup reports a problem, the log is at
`C:\ProgramData\Chronos\logs\install.log`.

---

## 3. First run

1. Open **Chronos** (desktop shortcut). Sign in:
   - user `admin`, password `ChangeMe123!`
   - it forces you to set a new password immediately. Choose a real one.
2. **If you have a licence key** (to run past the beta expiry): Settings →
   **Licence** → paste it → Install. Otherwise skip; it runs until
   10 November 2026.

### Company logo (optional)

To show the client's own logo across the app (login screen and sidebar) instead
of the Chronos mark:

1. Save their logo as `logo.png` (a square-ish PNG or SVG works best).
2. Copy it to `C:\ProgramData\Chronos\branding\logo.png` (the installer creates
   that folder).
3. Restart the **ChronosServer** service, or just reload the browser.

If the file is absent the app falls back to the Chronos mark. The Solis Labs
attribution stays either way.

### Back up the secrets — off this PC

Copy `C:\ProgramData\Chronos\chronos.env` to a USB stick or somewhere safe.
Its secrets **cannot** be recovered from a database backup, and you need them
if the PC ever has to be rebuilt.

---

## 4. Set it up for the client, in this order

Each step needs the one before it.

1. **Locations** — create each real location.
2. **Devices** — add the terminal (IP, and for Hikvision the username and
   password). Press **Test Connection**: it confirms the device answers and
   checks its clock. Fix the clock now if it complains.
3. **Employees** — add the staff, with real base salaries.
4. **Link staff to the device** — open the device → **Users on device** →
   **Read users from device**. For each one, **Link** it to an employee, or
   **Create employee**. This replaces typing device IDs by hand.
5. **Shift schedules** — real hours, breaks, grace minutes; split shifts where
   they exist. Assign them to employees.
6. **Holidays** — Configuration → Holidays. **Do not skip this**, or every
   public holiday counts as an unexcused absence and is deducted from wages.
7. **Penalty / Overtime / Absence rules** — the client's real numbers, agreed
   with them in writing. Not the testing placeholders.
8. **Manager accounts** — one per location, each with its location set.
9. **Badge a full test day yourself** — check in, break out, break in, check
   out — then look at Daily Status and confirm the numbers are what you expect.

---

## 5. Show the client

- Open the app from **another PC or a phone** on the office network at
  `http://<this-pc-ip>:8080`, to prove it works across the network. The PC's
  network must be set to **Private** in Windows, or the firewall blocks it.
- Point them at the manual: sidebar → **Manuali** (it opens with no internet).
- Show them the **Alerts** page and tell them to open it daily.

---

## 6. Backups — the one thing you must arrange

Chronos backs itself up nightly to `C:\ProgramData\Chronos\backups` and warns
in the app if that stops working. But that folder is on the **same disk** as
everything else — if the disk dies, the backups die with it.

**Set up a copy of that folder to somewhere else** — a USB drive, a network
share, or cloud sync — and check it actually runs. A backup on the same disk
is not a backup.

To restore one (as administrator):

```
& "C:\Program Files\Chronos\scripts\restore.ps1" -DumpFile "C:\ProgramData\Chronos\backups\<file>.dump"
```

Rehearse a restore once before you rely on it.

---

## 7. Later: upgrades and removal

- **Upgrade** — run a newer `ChronosSetup.exe` over the old one. It keeps the
  database, the config and the secrets, and restarts the services.
- **Uninstall** — Settings → Apps → Chronos. Services and the firewall rule
  are removed; the database and backups are **kept** in
  `C:\ProgramData\Chronos`. Delete that folder by hand only if you mean it.

---

## If something is wrong

| Symptom | Look at |
|---|---|
| Install did not finish | `C:\ProgramData\Chronos\logs\install.log` |
| App will not open | Services (`services.msc`): ChronosPostgres, ChronosServer, ChronosWorker should all be **Running** |
| A service keeps stopping | `C:\ProgramData\Chronos\logs\ChronosServer.out.log` (or ...Worker...) |
| Device says 401 | See the "401" section in [`README.md`](README.md); **stop retrying**, it locks the device |
| "Licence expired" screen | Paste a new key; mint one with `sign_license.py` |
