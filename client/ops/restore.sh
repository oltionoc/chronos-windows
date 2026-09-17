#!/bin/sh
# Restore a chronos backup. DESTRUCTIVE: replaces the current database
# contents with the dump's.
#
# Run from the project folder (the one holding docker-compose.yml):
#
#   ./ops/restore.sh backups/chronos-20260917-023000.dump
#
# It refuses to do anything until you type the confirmation, because the
# thing it overwrites is the client's payroll history.
set -eu

DUMP=${1:-}
if [ -z "$DUMP" ]; then
    echo "usage: $0 <path-to-dump-file>"
    echo
    echo "available backups:"
    ls -1t backups/chronos-*.dump 2>/dev/null || echo "  (none found in ./backups)"
    exit 2
fi

if [ ! -f "$DUMP" ]; then
    echo "No such file: $DUMP" >&2
    exit 2
fi

# Read the same .env docker compose reads, so the database name and user
# match this deployment rather than a hard-coded default.
if [ -f .env ]; then
    # shellcheck disable=SC1091
    . ./.env
fi
DB=${POSTGRES_DB:-chronos}
USER=${POSTGRES_USER:-chronos}

echo "About to REPLACE the contents of database '$DB' with:"
echo "  $DUMP"
echo
echo "Everything currently in it — punches, daily status, payroll runs — is lost."
printf "Type RESTORE to continue: "
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Aborted."; exit 1; }

# Verify the dump before touching the live database, so a corrupt file is
# discovered while the current data is still intact.
echo "Verifying dump..."
docker compose exec -T db sh -c 'cat > /tmp/restore.dump' < "$DUMP"
docker compose exec -T db pg_restore --list /tmp/restore.dump > /dev/null

# The API holds open connections and would fight the restore over object
# locks; it also must not serve half-restored data.
echo "Stopping api and worker..."
docker compose stop api worker

echo "Restoring..."
docker compose exec -T db pg_restore --clean --if-exists --no-owner \
    --username="$USER" --dbname="$DB" /tmp/restore.dump
docker compose exec -T db rm -f /tmp/restore.dump

echo "Starting api and worker..."
docker compose up -d api worker

echo
echo "Done. Check the app, then confirm the most recent punches are present."
