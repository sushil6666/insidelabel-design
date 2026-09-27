#!/bin/bash
# Restore test (D-114): a backup only counts once it has been restored.
#
# Restores the newest dump (or the one named) into a scratch database, then
# checks every table of the live database is there, the applied migrations
# match, and prints row counts side by side. The scratch database is dropped
# at the end. Nothing touches the live database except reading it.
#
#   deploy/restore_test.sh                     # newest dump in BACKUP_DIR
#   deploy/restore_test.sh /path/to/file.dump
#
# Run as the insidelabel user on the server (DEPLOY.md, step 9).
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/var/lib/insidelabel/backups}
LIVE=${PGDATABASE:-insidelabel}
SCRATCH=${LIVE}_restore_test

dump=${1:-$(ls -1t "$BACKUP_DIR/$LIVE"-*.dump 2>/dev/null | head -n1 || true)}
[ -n "$dump" ] && [ -f "$dump" ] || { echo "restore test: no dump found in $BACKUP_DIR" >&2; exit 1; }
echo "restore test: $dump -> $SCRATCH"

cleanup() { dropdb --if-exists "$SCRATCH"; }
trap cleanup EXIT
dropdb --if-exists "$SCRATCH"
createdb "$SCRATCH"
pg_restore --exit-on-error --no-owner --dbname="$SCRATCH" "$dump"

q() { psql -X -At -d "$1" -c "$2"; }
tables="SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
missing=$(comm -23 <(q "$LIVE" "$tables") <(q "$SCRATCH" "$tables"))
if [ -n "$missing" ]; then
    echo "FAIL: tables missing from the restore:" $missing >&2
    exit 1
fi

migrations="SELECT filename FROM schema_migrations ORDER BY 1"
if [ "$(q "$LIVE" "$migrations")" != "$(q "$SCRATCH" "$migrations")" ]; then
    echo "FAIL: applied migrations differ between live and restored" >&2
    exit 1
fi

# Row counts: the restore can be a little behind live (scans since the dump),
# never ahead, and never empty where live isn't.
printf '%-24s %10s %10s\n' table live restored
bad=0
for t in $(q "$LIVE" "$tables"); do
    l=$(q "$LIVE" "SELECT count(*) FROM \"$t\"")
    r=$(q "$SCRATCH" "SELECT count(*) FROM \"$t\"")
    printf '%-24s %10s %10s\n' "$t" "$l" "$r"
    if [ "$r" -gt "$l" ] || { [ "$l" -gt 0 ] && [ "$r" -eq 0 ]; }; then bad=1; fi
done
[ "$bad" -eq 0 ] || { echo "FAIL: a restored count is empty or ahead of live" >&2; exit 1; }
echo "PASS: $(basename "$dump") restores; $(q "$SCRATCH" "SELECT count(*) FROM schema_migrations") migrations, all tables present"
