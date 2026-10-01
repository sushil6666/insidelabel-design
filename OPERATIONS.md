# OPERATIONS.md - running insidelabel.ai on Google Cloud

Written 2026-09-27, the day the site went live, for Sushil coming back to it later
without that day's context. It says **what exists, where to find it, how to do the
everyday things, and what to do when something breaks**, in plain words.

- Setting a server up from nothing: `DEPLOY.md` (the ten steps, in order).
- Why it is built this way: `DECISIONS.md` D-114 (hosting), D-115 (marker wording).
- What happened on the day, and every snag hit: §9 below.

No secret is written in this file: no API key, no password, no invite code, no
billing account number. They live only where §8 says.

---

## 1. The picture

```
             Cloudflare DNS (insidelabel.ai, www)  "DNS only", grey cloud
                               |
phone / browser ──HTTPS──> 8.234.95.74  (Google Cloud, Mumbai)
                               |
                  VM insidelabel-1 (Ubuntu 24.04)
                  ├─ Caddy          :443, certificates, www -> insidelabel.ai
                  ├─ uvicorn        127.0.0.1:8000, ONE process (the app, /review, /app/)
                  ├─ PostgreSQL 18  local only (the catalogue, scans, invites, reviewers)
                  ├─ photos         /var/lib/insidelabel/media  (deleted after 30 days)
                  └─ backups        /var/lib/insidelabel/backups (14 days)
                               |
                  Gemini (reads the label) + Cloud Vision (checks the reading)
```

Every night: database backup 02:30, disk snapshot 03:30, photo cleanup about 04:00
(India time). The snapshot copies the whole disk, backups included, to Google's
storage in Mumbai and keeps 7 days.

---

## 2. Everything that exists, and where to find it

### Google Cloud (console.cloud.google.com, project **insidelabel**)

Pick the project in the top bar ("Insidelabel") before looking for anything.

| Thing | Name / value | Console location |
|---|---|---|
| Project | `insidelabel` (number 797275767015) | top bar project picker |
| The other project | `gen-lang-client-0397832999` "Default Gemini Project": the old AI Studio project (the laptop's Gemini key, prepaid credit). **The server doesn't use it.** | top bar project picker |
| Virtual machine | `insidelabel-1`, zone `asia-south1-a` (Mumbai), type `e2-medium` (2 vCPU sharing one core, 4 GB), Ubuntu 24.04, 30 GB disk, deletion protection on | Compute Engine, VM instances |
| Static IP | `insidelabel-ip` = **8.234.95.74** | VPC network, IP addresses |
| Firewall | `insidelabel-web` (80, 443 to VMs tagged `insidelabel-web`); `default-allow-ssh` (22) kept; `default-allow-rdp` deleted | VPC network, Firewall |
| Snapshot schedule | `insidelabel-daily`: 22:00 UTC (03:30 India), kept 7 days, stored in `asia-south1` | Compute Engine, Snapshots, "Snapshot schedules" tab |
| APIs switched on | Compute Engine, Cloud Vision, API Keys | APIs and services, Enabled APIs |
| Server keys | `server-vision` (Cloud Vision only, from 8.234.95.74 only); `gcp_website` (Gemini, made in AI Studio, in this project) | APIs and services, Credentials |
| Older keys to review | `testing`, `insidelabel` (made before today; restrict or delete) | APIs and services, Credentials |
| Billing | the account linked to this project; free-trial credit until upgraded | Billing |
| Uptime check | `insidelabel health`: `https://insidelabel.ai/health` every 5 minutes from all regions, HTTPS certificate validated, must contain `"status":"ok"` | Monitoring, Uptime checks |
| Alert | `insidelabel health uptime failure`: emails isushilb@gmail.com after 60 s of failed checks, and again when it recovers | Monitoring, Alerting |

### Outside Google

| Thing | Where | State on 2026-09-27 |
|---|---|---|
| `insidelabel.ai` | registered **and** DNS at Cloudflare (dash.cloudflare.com); nameservers `brady` and `stephane.ns.cloudflare.com` | `A @` and `A www` to 8.234.95.74, **DNS only** |
| `insidelabel.in` | registered at **GoDaddy** (nameservers `ns27`/`ns28.domaincontrol.com`), paid to 2029-09-07 | **on "client hold"** since 2026-09-12: resolves nowhere (§6, "insidelabel.in") |
| Code | github.com/sushil6666/InsideLabel (private), branch `main` | the server pulls it with a **read-only deploy key** `insidelabel-1` (repo Settings, Deploy keys) |
| Certificates | Let's Encrypt, got and renewed by Caddy | first one valid to 2026-12-26; renewal is automatic |

### On the server

| What | Where |
|---|---|
| The code (a git checkout of `main`) | `/opt/insidelabel/app` |
| Python and its packages | `/opt/insidelabel/venv` |
| Settings, no secrets | `/etc/insidelabel/settings.env` |
| The two API keys | `/etc/insidelabel/secrets.env` (only root can read it) |
| Which commit is running | `/etc/insidelabel/build.env`, and `https://insidelabel.ai/health` ("build") |
| Photos | `/var/lib/insidelabel/media` |
| Database backups | `/var/lib/insidelabel/backups` |
| Web server config | `/etc/caddy/Caddyfile` (for now without the `.in` names, §6) |
| Services | `insidelabel` (the app), `caddy`, `postgresql`, timers `insidelabel-backup`, `insidelabel-retention` |
| The tool runner | `il` (runs `tools/*.py` as the service user with the server's settings) |

---

## 3. Google Cloud words, in plain language

| Word | What it means here |
|---|---|
| **Project** | A folder that holds everything for one purpose, with its own bill and permissions. Ours is `insidelabel`. |
| **Billing account** | The card that pays. One billing account can pay for several projects. **If it is suspended (trial ended, card failed), every project on it stops.** |
| **Free trial** | Welcome credit that runs out after a set time or amount. Google's page (checked 2026-09-27) says $300 for 90 days; your console, Billing, Credits shows your exact amount and date. When the trial ends without an upgrade, VMs **stop** and their disks are **marked for deletion** (30 days' grace). |
| **Upgrade / Activate** | Turns the trial into a paid account. Keeps the unused credit and spends it first; nothing restarts. |
| **Compute Engine** | Google's virtual machines. |
| **VM / instance** | Our server, `insidelabel-1`. A computer in Google's data centre we rent by the second. |
| **Region / zone** | Where it runs. `asia-south1` is Mumbai; `asia-south1-a` is one building in it. |
| **Machine type** | Its size. `e2-medium` = 2 vCPU sharing one full core (can burst), 4 GB memory. Can be changed: stop, change, start. |
| **Boot disk** | The server's hard disk, 30 GB, "balanced" SSD. |
| **Static IP** | A public address reserved for us that never changes, so DNS never has to. Ours: 8.234.95.74. |
| **Firewall rule / network tag** | Which ports the internet may reach. Our rule opens 80 and 443 to VMs carrying the tag `insidelabel-web`. |
| **Snapshot / schedule** | A copy of the whole disk. The schedule takes one daily and deletes those older than 7 days. A new VM can be made from any snapshot. |
| **API** | A Google service (Cloud Vision, Gemini). Each must be **enabled** in the project before use. |
| **API key** | A password-like string that lets our code call an API, billed to the project. **Restrictions** limit which API it opens and from which IP. |
| **Service account / scopes** | The VM's own Google identity. It has narrow "scopes" on purpose, so `gcloud` commands that change the project **fail on the VM** ("insufficient authentication scopes"). That is correct; run them in Cloud Shell. |
| **Cloud Shell** | A terminal in the browser (the `>_` button, top right), logged in as you, with `gcloud` ready. Free. |
| **gcloud** | Google Cloud's command line. Everything clicked in the console can be typed with it. |
| **AI Studio** | aistudio.google.com: where Gemini keys are made. A key belongs to a project, and that project pays for it. |

---

## 4. Getting in

**The console:** console.cloud.google.com, project `insidelabel`.

**The server:** open Cloud Shell, then

```bash
gcloud compute ssh insidelabel-1 --zone=asia-south1-a
```

- **Always give the zone.** A new Cloud Shell tab can forget the default and guess another zone:
  on 2026-09-27 it offered `asia-southeast1-b` (Singapore) and found nothing. Ours is
  **`asia-south1-a` (Mumbai)**. To save it again: `gcloud config set compute/zone asia-south1-a`.
- The first time on a new Cloud Shell it makes an SSH key and asks for a passphrase: **press
  Enter twice**. Nothing shows on screen while you type at that prompt; it is waiting, not frozen.
- **Look at the prompt to know where you are:**
  - `isushilb@cloudshell:~ (insidelabel)$` = Cloud Shell, you. Use it for `gcloud` (keys, APIs,
    snapshots, the VM itself).
  - `isushilb@insidelabel-1:~$` = the server. Use it for `sudo`, `il`, logs, updates.
- Keep two tabs: the `+` next to the Cloud Shell tab opens a second one. One tab on the server,
  one for `gcloud`.
- `exit` leaves the server and returns to Cloud Shell.

---

## 5. Everyday tasks (on the server unless it says Cloud Shell)

### How you hear that the site is down

Google checks `https://insidelabel.ai/health` every 5 minutes from several countries (the uptime
check `insidelabel health`, created 2026-09-27). If it fails for a minute, an email arrives from
Google Cloud Monitoring; a second one when it's back. It also fails if the HTTPS certificate
breaks or `/health` stops saying `"status":"ok"`. The Google Cloud app on the phone can show the
same alerts as notifications. On the email: start at §6, "The site doesn't open".

Cost (Google's pricing page, 2026-09-27): uptime checks free up to 1 million runs a month per
project (this one is about 52,000); alerting free until at least 1 September 2027, then $0.35 a
month per condition.

A losing SSH session is different: the prompt goes back to `isushilb@cloudshell`; reconnect (§4).

### Is it up? Which version?

```bash
curl -s https://insidelabel.ai/health          # from anywhere: "status":"ok", "build": the commit
systemctl status insidelabel --no-pager         # "active (running)"
```

### Put new code live, or roll back

After a PR is merged into `main` on GitHub:

```bash
sudo /opt/insidelabel/app/deploy/update.sh              # latest main
sudo /opt/insidelabel/app/deploy/update.sh <commit>     # a given commit, to roll back
```

It fetches, installs, applies database migrations, restarts the app and checks `/health`.
It must end with `update: OK, running <commit>`. **The server only ever runs `main`**: a
change on a branch isn't live until its PR is merged.

### Logs

```bash
journalctl -u insidelabel -f                    # the app, live (Ctrl+C to stop)
journalctl -u insidelabel -n 100 --no-pager     # the last 100 lines
journalctl -u insidelabel --since "1 hour ago" --no-pager | grep -iE "SETUP ALARM|error"
journalctl -u caddy -n 50 --no-pager            # web server, certificates
```

`SETUP ALARM` means a key, credit or billing problem with Google: §6.

### Testers

```bash
il tools/beta.py invite 1 --label T07       # one code; prints the link to send
il tools/beta.py list                       # each code: devices, scans, days active (the W4 number)
il tools/beta.py feedback                   # newest feedback first
il tools/beta.py reset <CODE>               # tester has a new phone
il tools/beta.py revoke <CODE>              # lock a tester out
```

Invite codes are personal: send each privately, never post them anywhere public.

**The daily photo-scan limit (D-148):** 15 per phone in any 24 hours. To change it, change
`PHOTO_SCANS_A_DAY` in `src/insidelabel/ratelimit.py` on a branch, merge, then `update.sh`
(the screen's words follow the number; a restart also forgets today's counts).

### Reviewers and the queue

```bash
il tools/reviewers.py add <name>            # prints a password ONCE: give it privately
il tools/reviewers.py reset <name>          # a new password, printed ONCE
il tools/reviewers.py list
il tools/reviewers.py disable <name>
```

The queue: https://insidelabel.ai/review (log in with the reviewer name and password).

**A wrong barcode on a product (D-142).** Read the digits printed under the bars on the product's own
photo first (`/review/media/<key>`). Never change `products.barcode` with SQL: the database refuses it.

```bash
il tools/barcode_audit.py                                  # every published barcode against its own photos (read-only)
il tools/barcodes.py history <product id or barcode>       # the barcode and every recorded change
il tools/barcodes.py fix <product id> <right code> --by <your reviewer name> \
    --why "printed under the bars on the back photo: ..." --photo <key>    # dry run
il tools/barcodes.py fix ... --yes                          # the change, recorded with the old code
```

### Scans and problems

```bash
# The latest scans: outcome, speed, which reader checked the label
sudo -u insidelabel psql -d insidelabel -c "SELECT created_at, outcome, latency_ms, build,
  ocr->'back'->>'reader' AS reader FROM scans ORDER BY created_at DESC LIMIT 10"
il tools/repro.py list                      # problem reports from testers (not scans)
il tools/repro.py show <id>                 # a report's timeline and a replay (no Google call)
```

`reader` should say `cloud_vision`. `tesseract` means the Vision key was refused (§6).

**D-118, "One clearer photo, please":** a new pack whose list Cloud Vision can't confirm is asked
for one clearer photo before the result. How often, and how often people chose "Use this one
anyway" (watch it: if testers meet it often, revisit):

```bash
sudo -u insidelabel psql -d insidelabel -c "SELECT created_at::date AS day,
  count(*) FILTER (WHERE error_code = 'independent_read_failed') AS asked,
  count(*) FILTER (WHERE (request->>'accept_unconfirmed')::boolean) AS used_anyway,
  count(*) AS scans FROM scans GROUP BY 1 ORDER BY 1 DESC LIMIT 14"
```

### The review agents (D-117), in shadow

Gemini drafts each new queue item (category, ingredients, claims, note); a rules checker confirms
it against Cloud Vision's text or sends it to a person. **Shadow mode: nothing is published.** The
draft fills in the form on `/review`, with the failed checks listed above it. The form also asks
**who drafted** the record (you, Claude or Gemini) and **where the category came from**.

**Once, after the build with migration 015 is live** (`update.sh` applies the migration):

```bash
sudo cp /opt/insidelabel/app/deploy/systemd/insidelabel-review-agent.* /etc/systemd/system/
sudo systemctl daemon-reload
```

**Record who drafted items published before the column existed** (the 2026-09-27 run was
drafted by Claude). List them, then mark by item number:

```bash
sudo -u insidelabel psql -d insidelabel -c "SELECT q.id, p.name, q.resolved_at::date
  FROM review_queue q JOIN product_versions v ON v.id = q.resolved_product_version_id
  JOIN products p ON p.id = v.product_id WHERE q.status = 'done' ORDER BY q.id"
il tools/review_agent.py mark-drafted --by claude 3 4 5      # the item numbers
```

**Drafting costs one paid Gemini call per item** (about as much as a scan):

```bash
sudo systemctl start insidelabel-review-agent                  # draft up to 5 open items now
journalctl -u insidelabel-review-agent -n 20 --no-pager        # item N: confirmed / needs_person (checks)
sudo systemctl enable --now insidelabel-review-agent.timer     # every 10 minutes from now on
sudo systemctl disable --now insidelabel-review-agent.timer    # stop
```

The timer is **on** since 2026-09-27 (Sushil). Each item is drafted once per prompt version,
failed drafts included, so it never pays twice for one item; the most it spends is 5 drafts
every 10 minutes, and only while new packs are waiting. `systemctl list-timers
insidelabel-review-agent.timer` shows the next run.

Draft items you already decided, for the measurement (paid; the agent needs the Gemini key,
which only systemd can read, hence `systemd-run`):

```bash
sudo systemd-run --wait --pipe --quiet -p User=insidelabel -p WorkingDirectory=/opt/insidelabel/app \
  -p EnvironmentFile=/etc/insidelabel/settings.env -p EnvironmentFile=/etc/insidelabel/secrets.env \
  /opt/insidelabel/venv/bin/python tools/review_agent.py run --include-decided --limit 20
```

**Look and measure** (free):

```bash
il tools/review_agent.py show 12        # an item's newest draft and every check
il tools/review_agent.py recheck 12 13  # stored answers through the current checker (after a fix; no Gemini call)
il tools/review_agent.py measure        # drafts against your decisions: the D-117 gate
```

Publishing switches on only when `measure` says **PASSES** (at least 30 of your reviews, 95 %
agreement on category and ingredients, none confirmed-but-corrected), and after the publish step
is built (undo, and a list of agent-published items).

### Backups

```bash
ls -lh /var/lib/insidelabel/backups                       # one .dump per night, 14 kept
sudo systemctl start insidelabel-backup                   # take one now
sudo -u insidelabel /opt/insidelabel/app/deploy/restore_test.sh   # prove the newest restores
systemctl list-timers 'insidelabel*' --no-pager           # when the next ones run (UTC)
```

In Cloud Shell: `gcloud compute snapshots list` shows the daily disk snapshots.

Run the restore test after any big change, and at least once a month.

### Reboot (for example when the login says "System restart required")

```bash
sudo reboot            # the session drops; wait a minute, reconnect from Cloud Shell
uptime; systemctl is-active insidelabel caddy postgresql insidelabel-backup.timer insidelabel-retention.timer
```

Everything starts by itself: tested 2026-09-27, the site was back in under a minute. Reboot when
no one is likely to be scanning.

### Disk space, memory

```bash
df -h /                  # disk: act before it passes about 80 %
free -h                  # memory
```

### Restart things

```bash
sudo systemctl restart insidelabel      # the app (also needed after editing either settings file)
sudo systemctl reload caddy             # after editing /etc/caddy/Caddyfile
```

### Change a setting or a key

```bash
sudoedit /etc/insidelabel/settings.env          # e.g. never needed day to day
sudoedit /etc/insidelabel/secrets.env           # paste the new key after its "="
sudo systemctl restart insidelabel              # the app reads both files only when it starts
sudo awk -F= '/^[A-Z]/{print $1, (length($2)>20 ? "set" : "EMPTY")}' /etc/insidelabel/secrets.env
```

In nano: Ctrl+O, Enter saves; Ctrl+X exits. Never set `INSIDELABEL_ALLOW_REPLAY`,
`INSIDELABEL_CLAIMS_TO_USERS` or `INSIDELABEL_REVIEW_TOKEN` on this server
(`tests/test_deploy.py` guards the template).

---

## 6. When something is wrong

Work down the list; each line says what to look at first.

**The site doesn't open.**
1. From anywhere: `curl -sI https://insidelabel.ai` . No answer at all: is the VM running?
   Console, Compute Engine, VM instances: `insidelabel-1` should show a green tick. If it's
   stopped, check Billing first (a trial that ended or a failed card stops it), then start it.
2. On the server: `systemctl status insidelabel caddy postgresql --no-pager`. Restart whichever
   isn't running and read its log (§5).
3. `/health` answers but pages don't: `journalctl -u insidelabel -n 100 --no-pager`.

**Scans say "The label reader isn't available right now" (503 `vision_not_configured`).**
The log shows `SETUP ALARM` with the reason: `401`/`403` = the key is wrong or restricted
from this IP; `402` = out of credit (a prepaid AI Studio project); `404` = model name. Fix the
key or billing, then `sudo systemctl restart insidelabel`.

**Scans work but take 20 seconds or more.** Probably Cloud Vision refused the key and the
server fell back to Tesseract: check the `reader` column (§5) and the log for `ocr_config`.
Usually the key's IP restriction doesn't match 8.234.95.74, or the Vision API is off.

**A certificate error in the browser.** `journalctl -u caddy -n 50 --no-pager`. Caddy needs
ports 80 and 443 open and the DNS pointing at 8.234.95.74 (Cloudflare record **grey cloud**;
an orange cloud breaks it until the proxy step, D-114).

**The disk is filling up.** `sudo du -sh /var/lib/insidelabel/* /var/log/journal`. Photos
are cleaned after 30 days and backups after 14; if it still fills, make the disk bigger
(console, Compute Engine, Disks, `insidelabel-1`, Edit, size), then on the server
`sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1` (check the device name with `lsblk` first).

**I lost access over SSH.** Cloud Shell: `gcloud compute ssh insidelabel-1 --zone=asia-south1-a` again (it re-sends
your key). Still failing: console, VM instances, the SSH button in the row.

**A key has leaked** (pasted in a chat, a screenshot, a commit). In Cloud Shell:

```bash
gcloud services api-keys list --format="table(uid,displayName)"
gcloud services api-keys delete <uid>
gcloud services api-keys create --display-name="server-vision" \
  --allowed-ips=8.234.95.74 --api-target=service=vision.googleapis.com
```

(for Gemini: a new key in AI Studio, then restrict it, DEPLOY.md step 7). Paste the new key
into `secrets.env` on the server and restart the app. A key restricted to our IP is much less
urgent than an open one, but replace it anyway when convenient.

**Bring the database back from a backup.** DEPLOY.md, "Restoring for real". Stop the app
first; photos are not in the dump (they come back from a disk snapshot).

**The whole server is lost or a bad upgrade broke it.** Console, Compute Engine, Snapshots:
pick the latest `insidelabel-daily`, "Create instance" in `asia-south1-a`, type `e2-medium`,
network tag `insidelabel-web`, then attach the static IP `insidelabel-ip` to it (VPC network,
IP addresses, "Change"). DNS needs no change because the IP stays ours.

**`insidelabel.in` doesn't work.** On 2026-09-27 it was on GoDaddy **client hold**, set by
GoDaddy itself on 2026-09-12 (usually the registrant email was never verified). Fix: GoDaddy,
My Products, `insidelabel.in`, Domain settings, Contact information, resend the verification
and click it. Then: Cloudflare, Add a site, `insidelabel.in`, Free plan; put its two
nameservers at GoDaddy; add `A @` and `A www` to 8.234.95.74 (DNS only); and on the server
put the full Caddyfile back:

```bash
sudo cp /opt/insidelabel/app/deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

Check the registry's own view any time: https://rdap.nixiregistry.in/rdap/domain/insidelabel.in
("status" should not contain "client hold").

---

## 7. Money

- **What costs money, all on the `insidelabel` project's bill:** the VM (runs all day), its
  disk, the static IP, outbound traffic, snapshot storage, and every scan's Gemini and Cloud
  Vision call. Scans are the part that grows with testers.
- **Where to look:** console, Billing, Reports (filter project `insidelabel`, group by service).
  Billing, Credits shows what is left of the trial and when it ends.
- **Budget alert:** Billing, Budgets and alerts: about ₹1,500 a month, emails at 50, 90 and 100 %.
  An alert only emails; it doesn't stop anything.
- **Before any tester is invited, the account must be upgraded to paid with automatic payment.**
  Otherwise the trial's end stops the server and marks its disk for deletion. Upgrading keeps
  the remaining credit and spends it first.
- Indian banks may decline automatic card charges above ₹15,000 (RBI rule); this server is far
  below that.
- For comparison when deciding later (D-114, prices checked 2026-09-27): AWS Lightsail Mumbai
  was $12 a month for 2 GB, 2 vCPU, 60 GB, 1.5 TB transfer, all in one price. Moving there is a
  restore of the backup onto a new machine.

---

## 8. Security rules (each learned or confirmed on 2026-09-27)

- **API keys live in one place: `/etc/insidelabel/secrets.env` on the server.** Copy a new key
  from Cloud Shell or AI Studio straight into that file. Never into a chat, a screenshot, a
  note or a commit. (On the day, one key appeared whole and one mostly in the chat; both were
  restricted to the server's IP, which makes them useless elsewhere.)
- **Every key is restricted:** to its one API, and to the server's IP 8.234.95.74.
- **Keys for the laptop and keys for the server are different**, so one can be replaced without
  touching the other.
- **Invite codes and reviewer passwords are personal:** sent privately, kept in a password
  manager, never in the repo.
- **The deploy key is read-only:** the server can pull the code, never change it.
- **Only 22, 80 and 443 are open**; PostgreSQL and the app listen on the machine only.
- **`replay` is refused** on the server, and so is any scan from a phone without an invite.
- **Cloudflare stays "DNS only"** until the proxy step, which needs Caddy and a setting changed
  together (D-114); otherwise every tester would share one rate limit.

---

## 9. What we did on 2026-09-27 (the log)

In order, with the snag at each step and how it was solved.

1. **Checked:** PR #17 (domains) was in `main`; local `main` synced; 375 tests passed.
2. **Host question: can Cloudflare host it?** Checked Cloudflare's docs: no. Python Workers can't
   run our native libraries, Containers lose their disk when they sleep, Hyperdrive only speeds up
   a database hosted elsewhere. Cloudflare is used for DNS now and R2 (photos) later.
3. **AWS Lightsail vs Google Cloud.** Lightsail Mumbai was the recommendation ($12 fixed, 2 vCPU).
   Sushil chose **Google Cloud**: one account with the Gemini and Vision keys, and free-trial
   credit. Conditions: the server in its own project, billing upgraded before invites, a budget
   alert. Recorded as **D-114**, accepted.
4. **Wrote `deploy/` and `DEPLOY.md`**, tested on the WSL machine first: backup and restore on
   PostgreSQL 18 (and a cut backup fails the test), Caddy's config validated, a faked address
   header dropped by Caddy, the systemd units verified, the app run with the server's settings.
   Merged as **PR #18**.
5. **Project:** `insidelabel` turned out to be separate from the old "Default Gemini Project",
   so it was used as is.
6. **Created** (Cloud Shell): the Compute Engine API switched on, the static IP 8.234.95.74, the VM,
   the firewall rule, `default-allow-rdp` removed, the snapshot schedule. *Snag:* a warning that
   the 30 GB disk was bigger than the 10 GB image: harmless, Ubuntu grew to fill it (28 GB usable).
7. **DNS:** `A @` and `A www` at Cloudflare, DNS only; checked from public resolvers.
   *Found:* `insidelabel.in` is on GoDaddy **client hold** (not caused by anything we did).
8. **SSH into the server.** *Snag:* the passphrase prompt looked frozen; it was waiting for Enter.
9. **Packages:** PostgreSQL 18.6, Caddy 2.11.4, Tesseract 5.3.4, Python 3.12.3. *Snag avoided:*
   Ubuntu's "restart which services?" dialog, by running apt non-interactively (now in DEPLOY.md).
10. **Service user and database**; PostgreSQL confirmed listening on localhost only.
11. **Code:** a read-only deploy key added in GitHub; GitHub's fingerprint checked against GitHub's
    own list before answering yes. *Snag:* the server installs from `main`, so PR #18 had to be
    merged first.
12. **Keys.** *Snags:* (a) `gcloud` run on the server was refused ("insufficient authentication
    scopes"): correct, it must run in Cloud Shell; (b) the Agent Platform page greyed out "Create
    API key" until the API Keys service was switched on; created with `gcloud` instead. New pair:
    `server-vision` (restricted to Cloud Vision and the server IP) and `gcp_website` (Gemini).
13. **Services started:** 14 migrations applied, `update.sh` OK. *Choice:* the Caddyfile on the
    server leaves out the `.in` names until the hold is lifted, so Caddy doesn't retry all day.
    Certificates obtained for `insidelabel.ai` and `www`.
14. **Checked from outside:** HTTPS, redirects, headers, `/review` asks for a login, no invite =
    refused, `replay` = refused.
15. **Reviewer `sushil`** created and logged in. **First backup and restore test: PASS.**
16. **First real scan** from Sushil's phone (Organic India Tulsi Mulethi): `verdict` in 5.7 s,
    Cloud Vision read 1,717 characters alongside Gemini, no alarms. *Snags:* `repro.py list` shows
    problem reports, not scans; the OCR reader sits under `ocr->'back'` in the scan row. Both now
    in DEPLOY.md step 10 and §5 above.
17. **The first scan showed a wording problem:** the headline and the "On the label" quote used
    our table's category name ("added flavour (natural/artificial/nature-identical)"), putting
    "artificial" next to a brand. Fixed as **D-115** (accepted): the pack's own words are shown;
    verdicts unchanged; 103 new tests. Merged as PRs #19 and #20, put live with `update.sh`
    (build `866eaadbfbbb`).

**Open after the day** (also in STATE.md §8): upgrade billing before invites; lift the
`insidelabel.in` hold; confirm the Gemini key restriction and review the keys `testing` and
`insidelabel`; walk the rest of the app on a phone; then the DPDP data map.

---

## 10. Where else to look

| Question | File |
|---|---|
| How do I build the server again from zero? | `DEPLOY.md` |
| Why Google Cloud, Mumbai, PostgreSQL 18, Caddy? | `DECISIONS.md` D-114 |
| What's the status, what's next? | `STATE.md` (§8 is the work queue) |
| What does each deploy file do? | the comment at the top of each file in `deploy/` |
| The app's endpoints | `API_README.md` |
