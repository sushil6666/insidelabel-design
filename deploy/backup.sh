#!/bin/bash
# Daily database backup (D-114). Run by insidelabel-backup.timer as the
# insidelabel user, which reaches Postgres by peer auth over the local socket.
#
# One custom-format dump a day, kept BACKUP_KEEP_DAYS days. The daily disk
# snapshot copies these files off the machine; restore_test.sh proves one
# restores. PGHOST/PGPORT/PGDATABASE are honoured, so the same script runs
# against a local test cluster.
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/var/lib/insidelabel/backups}
BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
DB=${PGDATABASE:-insidelabel}

umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/$DB-$stamp.dump"

# Write to a temporary name and rename, so a failed dump never looks like a backup.
pg_dump --format=custom --no-owner --file="$out.part" "$DB"
mv "$out.part" "$out"
echo "backup: $out ($(du -h "$out" | cut -f1))"

find "$BACKUP_DIR" -maxdepth 1 -name "$DB-*.dump" -mtime +"$BACKUP_KEEP_DAYS" -print -delete
find "$BACKUP_DIR" -maxdepth 1 -name "$DB-*.dump.part" -mmin +60 -delete
