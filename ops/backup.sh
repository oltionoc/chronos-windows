#!/bin/sh
# Nightly Postgres backup for an on-premise chronos install.
#
# Why a long-running container rather than cron or Windows Task Scheduler:
# the target machines are the client's own PCs, often Windows, sometimes
# switched off at night. A compose service with `restart: unless-stopped`
# comes back with the machine, needs no host-side scheduler to be configured
# per site, and can notice on startup that it missed a run.
#
# What it produces, in /backups (a HOST folder, deliberately not the
# Postgres volume — a backup living inside the thing it protects is not a
# backup):
#   chronos-YYYYmmdd-HHMMSS.dump   pg_dump custom format, compressed
#   LAST_BACKUP                    one line: <iso timestamp> <ok|failed> <file>
#
# LAST_BACKUP is what `GET /reports/alerts` reads to raise `backup_stale`,
# so a silently failing backup shows up in the app instead of being
# discovered on the day it is needed.
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
BACKUP_HOUR=${BACKUP_HOUR:-2}
BACKUP_MINUTE=${BACKUP_MINUTE:-30}

log() { echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

mark() {
    # status file is written last and atomically, so a half-written backup
    # can never look like a good one.
    printf '%s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${2:--}" > "$BACKUP_DIR/LAST_BACKUP.tmp"
    mv "$BACKUP_DIR/LAST_BACKUP.tmp" "$BACKUP_DIR/LAST_BACKUP"
}

run_backup() {
    stamp=$(date -u +%Y%m%d-%H%M%S)
    target="$BACKUP_DIR/chronos-$stamp.dump"

    log "starting dump of $POSTGRES_DB"
    if ! pg_dump --format=custom --compress=6 --file="$target.part" \
        --host="$POSTGRES_HOST" --username="$POSTGRES_USER" "$POSTGRES_DB"; then
        log "ERROR pg_dump failed"
        rm -f "$target.part"
        mark failed
        return 1
    fi

    # Verify before trusting it: a dump that cannot be listed cannot be
    # restored either, and finding that out during an actual restore is the
    # worst possible time.
    if ! pg_restore --list "$target.part" > /dev/null 2>&1; then
        log "ERROR dump failed verification, keeping it as .INVALID for inspection"
        mv "$target.part" "$target.INVALID"
        mark failed
        return 1
    fi

    mv "$target.part" "$target"
    size=$(du -h "$target" | cut -f1)
    log "wrote $target ($size)"
    mark ok "$(basename "$target")"

    # Prune old dumps. Failed/invalid files are deliberately NOT pruned on
    # age: they are evidence.
    find "$BACKUP_DIR" -name 'chronos-*.dump' -type f -mtime "+$RETENTION_DAYS" -print -delete \
        | while read -r old; do log "pruned $old"; done
    return 0
}

seconds_until_next_run() {
    now_h=$(date +%H); now_m=$(date +%M); now_s=$(date +%S)
    # strip leading zeros so `sh` does not read them as octal
    now=$(( ${now_h#0} * 3600 + ${now_m#0} * 60 + ${now_s#0} ))
    target=$(( BACKUP_HOUR * 3600 + BACKUP_MINUTE * 60 ))
    delta=$(( target - now ))
    [ "$delta" -le 0 ] && delta=$(( delta + 86400 ))
    echo "$delta"
}

mkdir -p "$BACKUP_DIR"
log "backup service started; schedule ${BACKUP_HOUR}:${BACKUP_MINUTE} local, keeping ${RETENTION_DAYS} days in $BACKUP_DIR"

# Catch-up: if there is no backup from the last 24h (fresh install, or the
# machine was off at the scheduled time), take one now rather than waiting a
# whole day for the next window.
if [ -z "$(find "$BACKUP_DIR" -name 'chronos-*.dump' -type f -mtime -1 2>/dev/null)" ]; then
    log "no backup in the last 24h, taking one now"
    run_backup || true
fi

while true; do
    sleep "$(seconds_until_next_run)"
    run_backup || true
    # Guard against a same-second re-entry when a run finishes instantly.
    sleep 60
done
