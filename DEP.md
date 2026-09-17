> Note: for the beta release line, the step-by-step runbook (device install,
> client PC setup, registry, code protection) now lives in README.md. This
> file keeps the ongoing-operations detail.

Deployment is Docker Compose on the client's own machine (per BLUEPRINT.md, LAN-only, no reverse proxy needed for Phase 1). Once it's actually running there, here's the runbook:

Before go-live
- Real secrets in .env: JWT_SECRET, INTERNAL_API_KEY, POSTGRES_PASSWORD — random, not the dev defaults. COOKIE_SECURE=true if you ever put TLS in front of it.
- CORS_ORIGINS set to wherever the frontend is actually reached from (LAN IP or domain, not localhost).
- Remove device-simulator service from docker-compose.yml — it's marked temporary dev tooling, no reason to ship it to the client's machine.
- Confirm DEVICE_TIMEZONE=Europe/Tirane and worker's NIGHTLY_HOUR/NIGHTLY_MINUTE are sane for local time.
- Log into the bootstrap admin, change the password immediately (must_change_password already forces this on first login).

Go-live setup (in order)
1. Locations — create each real location.
2. Devices — register each K40's real IP/port, run Test Connection, confirm reachable.
3. Employees — real headcount (bulk import via Excel if it's a lot).
4. Device enrollments — map each employee to their device_user_id (the fingerprint ID on the actual unit).
5. Shift schedules — real work hours per location, assign to employees.
6. Penalty/Overtime/Absence config — real policy numbers, not the placeholders from testing.
7. Manager accounts — one per location, assign location_id, decide who (if anyone) gets the payroll-access flag.
8. Wipe any remaining test/demo data (should already be clean from earlier in this session, but double-check).

Ongoing / ops
- Backups: the `backup` service (ops/backup.sh) dumps the database nightly at 02:30 local into ./backups on the host, verifies each dump with pg_restore --list, keeps 14 days, and writes ./backups/LAST_BACKUP. It runs in Docker with restart: unless-stopped, so it survives a reboot and takes a catch-up dump at startup if the machine was off at the scheduled time. Tune with BACKUP_HOUR / BACKUP_MINUTE / BACKUP_RETENTION_DAYS / BACKUP_TIMEZONE in .env.
  - The app watches itself: Alerts raises backup_missing / backup_failed / backup_stale (admin-only) if the dump stops working, so a silently broken backup is visible in the product instead of on the day it is needed.
  - STILL MANUAL, and still the biggest risk: getting those files OFF that machine. ./backups sits on the same disk as everything else, so a dead disk takes the backups with it. Copy the folder to a network share, a USB drive or cloud storage on a schedule the client will actually keep.
  - Restore: ./ops/restore.sh backups/chronos-YYYYmmdd-HHMMSS.dump — verifies the dump, stops api and worker, restores, restarts them. It asks for typed confirmation because it replaces the live payroll history. Rehearse this once before go-live; an untested restore is not a backup.
- Disk space: watch the Postgres volume — attendance logs accumulate daily, forever, with no retention/purge policy currently.
- Device health: the "device stale" alert (24h no sync) is your early warning if a device goes offline or loses network — check Alerts periodically, don't wait for someone to notice they can't badge in.
- Device clocks: worker reads each device's own clock every sync and stores the difference; Alerts raises device_clock_drift past 2 minutes, and the device page shows it. This matters because every punch is timestamped by the DEVICE, so a drifted clock silently corrupts lateness and overtime (seen for real on a terminal left on factory UTC+8: an on-time arrival recorded as 61 minutes late). If it fires, fix the device clock, then recompute the affected dates from Daily Status.
- Overtime badging: the terminal's "start overtime" / "end overtime" keys are now recorded as their own punch kinds, and those minutes are paid WITHOUT the daily overtime threshold (the threshold only filters overtime inferred from staying late). Tell the client's staff this: if overtime is meant to be paid in full, badge it; if they just stay late, the threshold applies. Pre-approval, where configured, still gates payment either way.
- Holidays: Configuration > Holidays must be filled in for each year, or every public holiday reads as an unexcused absence and deducts a day's pay. Fixed-date ones can be entered once with "repeats every year"; moving ones (Eid, Easter) need entering per year. Work on a holiday is paid at overtime_config.holiday_rate_per_hour_eur.
- Container health: docker compose ps — all should stay "healthy"; restart: unless-stopped handles crashes/reboots but not silent failures.
- Nightly job only processes "yesterday" as a batch reconciliation — the live dashboard doesn't depend on it anymore (recompute is instant on punch now), so this is just a safety net, not critical-path.
