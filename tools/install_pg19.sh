#!/usr/bin/env bash
# Install PostgreSQL 19 (beta until GA, expected end of October 2026) next to
# the existing PostgreSQL 16, from the official PostgreSQL apt repository.
#
#   sudo bash tools/install_pg19.sh
#
# Existing clusters keep their ports; 19 gets PG19_PORT or the next free port.
#   sudo PG19_PORT=5432 bash tools/install_pg19.sh   (once 5432 is free)
# Safe to re-run.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
APP_USER="${SUDO_USER:-insightstack}"
CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"   # noble on Ubuntu 24.04

echo "==> Adding the PostgreSQL apt repository (main + 19 beta channel) for $CODENAME"
install -d /usr/share/postgresql-common/pgdg
curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main 19" \
  > /etc/apt/sources.list.d/pgdg.list

echo "==> Installing postgresql-19 (contrib, incl. pg_trgm, is part of the package)"
apt-get update -q
apt-get install -y postgresql-19

# The package only auto-creates a cluster on a machine with none, so create it
# explicitly. PG19_PORT picks the port (default: the next free one).
if ! pg_lsclusters -h | awk '$1=="19" && $2=="main"' | grep -q .; then
  echo "==> Creating cluster 19/main${PG19_PORT:+ on port $PG19_PORT}"
  pg_createcluster 19 main ${PG19_PORT:+--port "$PG19_PORT"}
fi
PORT="$(pg_lsclusters -h | awk '$1=="19" && $2=="main" {print $3}')"
pg_ctlcluster 19 main start 2>/dev/null || true

echo "==> Creating role $APP_USER on 19/main (port $PORT)"
if ! sudo -u postgres psql -p "$PORT" -tAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1; then
  sudo -u postgres createuser -p "$PORT" --createdb "$APP_USER"
fi

echo
pg_lsclusters
echo
echo "Done. PostgreSQL 19 is on port $PORT."
