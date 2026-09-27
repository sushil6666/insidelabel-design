#!/bin/bash
# Put a commit of main on the server (D-114). Run as root (sudo):
#
#   sudo /opt/insidelabel/app/deploy/update.sh            # latest origin/main
#   sudo /opt/insidelabel/app/deploy/update.sh <commit>   # a given commit (or roll back)
#
# Fetches, checks out, installs dependencies, applies migrations, records the
# commit as INSIDELABEL_BUILD (D-092: every scan row names the code that made
# it), restarts the one process and checks /health reports that commit.
set -euo pipefail
APP=/opt/insidelabel/app
VENV=/opt/insidelabel/venv
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

cd "$APP"
git fetch --quiet origin
ref=${1:-origin/main}
git checkout --quiet --detach "$ref"
build=$(git rev-parse --short=12 HEAD)
echo "update: $build $(git log -1 --format=%s)"

"$VENV/bin/pip" install --quiet -r requirements.txt -e .
/usr/local/bin/il migrate

install -m 0644 /dev/null /etc/insidelabel/build.env
echo "INSIDELABEL_BUILD=$build" > /etc/insidelabel/build.env

systemctl restart insidelabel
for _ in $(seq 1 30); do
    if got=$(curl -fsS http://127.0.0.1:8000/health 2>/dev/null); then
        echo "health: $got"
        case "$got" in *"\"build\":\"$build\""*) echo "update: OK, running $build"; exit 0;; esac
        echo "update: /health answers but reports another build" >&2; exit 1
    fi
    sleep 1
done
echo "update: no answer from /health after 30 s; see: journalctl -u insidelabel -n 50" >&2
exit 1
