# DEPLOY.md - putting InsideLabel on insidelabel.ai

The server is set up by hand, once, following these steps in order (D-114). After
that, one command puts a new commit live (§ Day to day). Every file the server
uses is in `deploy/`; nothing on the server is edited except the two settings
files in `/etc/insidelabel/`.

```
phone ──HTTPS──> Caddy :443 ──> uvicorn 127.0.0.1:8000 (one process) ──> PostgreSQL 18 (local socket)
                 (certificates)       │                                   photos: /var/lib/insidelabel/media
                                      └──> Gemini, Cloud Vision (Google)
Cloudflare: DNS only (grey cloud). insidelabel.in, www.* ──301──> https://insidelabel.ai
```

| What | Where on the server |
|---|---|
| Code (git checkout of `main`) | `/opt/insidelabel/app` (root) |
| Python environment | `/opt/insidelabel/venv` (root) |
| Photos (D-080: 30 days) | `/var/lib/insidelabel/media` (insidelabel) |
| Database dumps (14 days) | `/var/lib/insidelabel/backups` (insidelabel) |
| Settings, no secrets | `/etc/insidelabel/settings.env` (root:insidelabel 0640) |
| API keys | `/etc/insidelabel/secrets.env` (root 0600) |
| Deployed commit | `/etc/insidelabel/build.env` (written by `update.sh`) |
| Service and daily jobs | `insidelabel.service`, `insidelabel-backup.timer`, `insidelabel-retention.timer` |

**Never paste an API key into a chat, a commit or an issue.** Keys are typed into
`secrets.env` on the server and nowhere else.

---

## 1. Google Cloud account and project (console, about 10 minutes)

1. **Billing:** upgrade the free-trial account to a **paid account with automatic
   card payment**. The credit is kept and spent first. Without the upgrade, the server
   stops when the trial ends and its disk is marked for deletion (D-114).
2. **Project:** the server lives in the **`insidelabel`** project (created 2026-09-27),
   not the old "Default Gemini Project" (`gen-lang-client-0397832999`).
3. **Budget alert:** Billing, then Budgets and alerts: about ₹1,500 a month, emails at
   50 %, 90 % and 100 %.
4. **Compute Engine API:** `gcloud services enable compute.googleapis.com` (step 2).

The commands below run in **Cloud Shell** (the `>_` button in the console), which
already has `gcloud` and your login.

## 2. Static IP, server, firewall, snapshots (Cloud Shell)

```bash
gcloud config set project insidelabel
gcloud config set compute/region asia-south1
gcloud config set compute/zone asia-south1-a
gcloud services enable compute.googleapis.com

# A fixed public address, so DNS never has to change.
gcloud compute addresses create insidelabel-ip --region=asia-south1
gcloud compute addresses describe insidelabel-ip --format='value(address)'    # note this IP

# The server: Mumbai, Ubuntu 24.04, e2-medium (2 vCPU, 4 GB), 30 GB balanced disk.
gcloud compute instances create insidelabel-1 \
  --machine-type=e2-medium \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-balanced \
  --address=insidelabel-ip --tags=insidelabel-web \
  --shielded-secure-boot --deletion-protection

# Only 80 and 443 from the internet (SSH stays on the default rule, keys only).
gcloud compute firewall-rules create insidelabel-web \
  --network=default --allow=tcp:80,tcp:443 --target-tags=insidelabel-web
# Windows remote desktop isn't needed.
gcloud compute firewall-rules delete default-allow-rdp --quiet

# Daily disk snapshot at 22:00 UTC (03:30 India time), kept 7 days, stored in
# Mumbai: the off-machine copy of the database dumps and the photos (D-114).
gcloud compute resource-policies create snapshot-schedule insidelabel-daily \
  --region=asia-south1 --start-time=22:00 --daily-schedule \
  --max-retention-days=7 --storage-location=asia-south1 \
  --on-source-disk-delete=keep-auto-snapshots
gcloud compute disks add-resource-policies insidelabel-1 \
  --resource-policies=insidelabel-daily
```

## 3. DNS on Cloudflare (dashboard)

Every record below is **DNS only (grey cloud)**; the proxy comes later, as its own
step (D-114).

1. **insidelabel.ai** (already on Cloudflare): delete any parked A/AAAA/CNAME records
   for `@` and `www`, then add:
   - `A  @    <server IP>`  DNS only
   - `A  www  <server IP>`  DNS only
2. **insidelabel.in**: in Cloudflare, "Add a site", `insidelabel.in`, Free plan. It
   shows two nameservers. At **GoDaddy**, Domain settings, Nameservers, "I'll use my
   own nameservers", enter those two. Cloudflare emails when the site is active (often
   within an hour, up to 24). Then add:
   - `A  @    <server IP>`  DNS only
   - `A  www  <server IP>`  DNS only
3. Both domains on **auto-renew** (Cloudflare for `.ai`, GoDaddy for `.in`).

The redirects themselves are done by Caddy on the server (step 8), so the proxy can
stay off.

Check from any computer (answers must be the server IP):

```bash
dig +short insidelabel.ai; dig +short www.insidelabel.ai
dig +short insidelabel.in; dig +short www.insidelabel.in
```

## 4. Server packages (SSH)

```bash
gcloud compute ssh insidelabel-1          # from Cloud Shell
```

On the server:

```bash
df -h /                                     # about 29G: the image grew to fill the 30 GB disk

# NEEDRESTART_MODE=a: answer Ubuntu's "restart which services?" dialog automatically.
export NEEDRESTART_MODE=a DEBIAN_FRONTEND=noninteractive
sudo -E apt update && sudo -E apt -y upgrade
sudo -E apt install -y git curl python3.12-venv tesseract-ocr

# PostgreSQL 18 from the PostgreSQL project's repository (postgresql.org/download/linux/ubuntu)
sudo -E apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo -E apt install -y postgresql-18
pg_lsclusters                               # 18 main 5432 online

# Caddy from its official repository (caddyserver.com/docs/install)
sudo -E apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
sudo -E apt update && sudo -E apt install -y caddy
```

Ubuntu installs security updates by itself (`unattended-upgrades`); leave it on.

## 5. The service user and the database

```bash
sudo adduser --system --group --home /var/lib/insidelabel insidelabel
sudo install -d -m 0750 -o insidelabel -g insidelabel /var/lib/insidelabel/media /var/lib/insidelabel/backups

# A role with the same name as the user: peer auth over the socket, no password.
# CREATEDB is for the restore test's scratch database.
sudo -u postgres createuser --createdb insidelabel
sudo -u postgres createdb --owner=insidelabel insidelabel
sudo -u postgres psql -Atc "SHOW listen_addresses"      # must be: localhost
```

## 6. The code

The repository is private, so the server gets a **read-only deploy key**.

```bash
sudo ssh-keygen -t ed25519 -N "" -C insidelabel-server -f /root/.ssh/insidelabel_deploy
sudo cat /root/.ssh/insidelabel_deploy.pub
```

GitHub, `sushil6666/InsideLabel`, Settings, Deploy keys, Add: title `insidelabel-1`,
paste the key, **leave "Allow write access" off**.

```bash
printf 'Host github.com\n  IdentityFile /root/.ssh/insidelabel_deploy\n  IdentitiesOnly yes\n' | sudo tee -a /root/.ssh/config
sudo ssh -T git@github.com
# The first time it prints GitHub's host key fingerprint: compare it with
# https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
# and answer yes only if it matches. Expected reply: "...successfully authenticated..."

sudo install -d -m 0755 /opt/insidelabel
sudo git clone git@github.com:sushil6666/InsideLabel.git /opt/insidelabel/app
sudo python3 -m venv /opt/insidelabel/venv
sudo ln -s /opt/insidelabel/app/deploy/il /usr/local/bin/il
```

## 7. Settings and keys

```bash
sudo install -d -m 0750 -o root -g insidelabel /etc/insidelabel
sudo install -m 0640 -o root -g insidelabel /opt/insidelabel/app/deploy/settings.env.example /etc/insidelabel/settings.env
sudo install -m 0600 -o root -g root /opt/insidelabel/app/deploy/secrets.env.example /etc/insidelabel/secrets.env
sudoedit /etc/insidelabel/secrets.env          # type the two keys after the = signs
```

`settings.env` needs no edits: invite-only on (D-102), one proxy hop (D-095), the
public address; replay, the claim check and the review token stay unset (D-101,
D-051, D-097). `tests/test_deploy.py` keeps the template that way.

**Keys for the server**: a **new pair** used only by the server, so a key on a laptop
can be revoked without taking the site down. Both live in the `insidelabel` project, so
Gemini and Cloud Vision are billed with the server. Create them in **Cloud Shell** (as
yourself), not on the server: the VM's own account is rightly not allowed to manage keys.

```bash
gcloud services enable vision.googleapis.com apikeys.googleapis.com
# Cloud Vision: this API only, from the server's IP only.
gcloud services api-keys create --display-name="server-vision" \
  --allowed-ips=<server IP> --api-target=service=vision.googleapis.com
#   -> keyString: copy it straight into secrets.env on the server
# Gemini: create the key in AI Studio (in the insidelabel project), then restrict it:
gcloud services api-keys list --format="table(uid,displayName)"
gcloud services api-keys update <uid> \
  --allowed-ips=<server IP> --api-target=service=generativelanguage.googleapis.com
```

Copy keys from Cloud Shell or AI Studio **straight into the server file**: not into a
chat, a screenshot or a note. Check without showing them:

```bash
sudo awk -F= '/^[A-Z]/{print $1, (length($2)>20 ? "set" : "EMPTY")}' /etc/insidelabel/secrets.env
```

Without `GOOGLE_VISION_KEY` scans still work but fall back to Tesseract, about 20 s
slower (D-093).

## 8. Services, first start, HTTPS

```bash
sudo cp /opt/insidelabel/app/deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable insidelabel insidelabel-backup.timer insidelabel-retention.timer
sudo systemctl start insidelabel-backup.timer insidelabel-retention.timer

# Install dependencies, migrate, record the build, start the app, check /health:
sudo /opt/insidelabel/app/deploy/update.sh
# ends with: update: OK, running <commit>

# HTTPS: only once step 3's DNS answers with the server IP.
sudo cp /opt/insidelabel/app/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
# Until a name resolves (insidelabel.in was on GoDaddy "client hold" on 2026-09-27),
# leave it out, or Caddy retries its certificate all day:
#   sed 's/^www\.insidelabel\.ai, insidelabel\.in, www\.insidelabel\.in {$/www.insidelabel.ai {/' \
#     /opt/insidelabel/app/deploy/Caddyfile | sudo tee /etc/caddy/Caddyfile > /dev/null
journalctl -u caddy -n 30 --no-pager      # "certificate obtained successfully" for all four names
```

Checks from your computer:

```bash
curl -s https://insidelabel.ai/health                    # "status":"ok", "build": the commit
curl -sI https://insidelabel.in | grep -i location        # https://insidelabel.ai/
curl -sI https://www.insidelabel.ai | grep -i location    # https://insidelabel.ai/
# A scan without an invite is refused before anything is read (D-102):
curl -s -X POST https://insidelabel.ai/scan -F device_id=check -F barcode=8901063010208
#   -> "invite_required"
# replay is off (D-101); it is refused even before the invite check:
curl -s -X POST https://insidelabel.ai/scan -F device_id=check -F replay='{"x":1}'
#   -> "replay_disabled"
```

Open `https://insidelabel.ai/` and `https://insidelabel.ai/app/` in a browser.

## 9. Reviewer login, backup, restore test

```bash
il tools/reviewers.py add sushil          # prints a generated password once: keep it in a password manager
```

Log in at `https://insidelabel.ai/review`.

```bash
sudo systemctl start insidelabel-backup   # take the first dump now
journalctl -u insidelabel-backup -n 5 --no-pager
sudo -u insidelabel /opt/insidelabel/app/deploy/restore_test.sh
#   -> PASS: ... restores; 14 migrations, all tables present
systemctl list-timers 'insidelabel*'      # next backup 02:30, retention 04:00 India time
```

The next morning, in Cloud Shell: `gcloud compute snapshots list` shows the first
`insidelabel-daily` snapshot. **Write the date of the restore test in STATE.md** (§11
manual gate "backups tested by restoring one").

## 10. One real scan

This is a **paid** Gemini and Cloud Vision call, made by Sushil from the phone.

```bash
il tools/beta.py invite 1 --label sushil  # prints https://insidelabel.ai/app/#/join/CODE
```

On the phone: open the link, agree to "Before you start" (D-105), scan a real pack
(barcode, then the back photo). Then on the server:

```bash
il tools/beta.py list                     # the code: 1 device, 1 scan, agreed today
sudo -u insidelabel psql -d insidelabel -c "SELECT created_at, outcome, latency_ms, build,
  ocr->'back'->>'reader' AS reader, length(ocr->'back'->>'text') AS ocr_chars
  FROM scans ORDER BY created_at DESC LIMIT 3"
#   outcome verdict (or unlisted without a barcode), reader cloud_vision (tesseract
#   means the Vision key was refused), build = the deployed commit
journalctl -u insidelabel -n 50 --no-pager | grep -iE "SETUP ALARM|error" || echo "no setup alarms or errors"
```

(`il tools/repro.py list` shows problem reports, not scans.)

The site is live. Invites to testers wait for the privacy page and the DPDP review
(STATE.md §8).

---

## Day to day

| Task | Command (on the server) |
|---|---|
| Put the latest `main` live | `sudo /opt/insidelabel/app/deploy/update.sh` |
| Roll back to a commit | `sudo /opt/insidelabel/app/deploy/update.sh <commit>` |
| Follow the app's log | `journalctl -u insidelabel -f` |
| Is it up? | `curl -s https://insidelabel.ai/health` |
| Invite a tester | `il tools/beta.py invite 1 --label T07` |
| Testers, scans, days active | `il tools/beta.py list` |
| A reported problem | `il tools/repro.py show <id>` (D-092) |
| Add a reviewer | `il tools/reviewers.py add <name>` |
| What retention would delete | `il tools/retention.py` |

`update.sh` runs migrations before the restart, so a migration must work with the
code it ships with. If a file in `deploy/systemd/` or the `Caddyfile` changes, copy it
again (step 8) and `sudo systemctl daemon-reload` / `sudo systemctl reload caddy`.

## Restoring for real

Database, from a dump on the server:

```bash
sudo systemctl stop insidelabel
sudo -u insidelabel dropdb insidelabel
sudo -u insidelabel createdb insidelabel
sudo -u insidelabel pg_restore --exit-on-error --no-owner -d insidelabel /var/lib/insidelabel/backups/<file>.dump
il migrate
sudo systemctl start insidelabel
```

Whole machine (disk lost, or a bad upgrade): in the console, Compute Engine,
Snapshots, pick the latest `insidelabel-daily`, "Create instance", same zone, type and
network tag, then attach the static IP `insidelabel-ip` to it. DNS doesn't change.

## Later (each its own decision, D-114)

- **PostgreSQL 19** once released: dump from 18, restore into 19, the same way as the
  restore test.
- **Photos and backups to R2**; retention stays our job (D-098).
- **Cloudflare proxy on:** Caddy then needs `trusted_proxies` for Cloudflare's ranges
  and `INSIDELABEL_PROXY_HOPS` changes; `tests/test_deploy.py` changes with it.
