# STATE.md - where InsideLabel is, and how to pick it up

**Last updated:** 2026-09-30 (**https://insidelabel.ai is live**, `main` = `11d184e`, PR #74: D-142, D-143, D-144 LOCKED and deployed; D-140 phase 3 part 1 merged) · **Owner:** Sushil · **Tests:** 913 passing, 8 skipped, 1 expected failure (branch `baby-food-composition`) · **Release gate:** `python tools/release_check.py` - NOT READY (2 failing; 4 with `INSIDELABEL_DB` set) · **Latest real scan:** 5.7 s on the live server (2026-09-27), Gemini + Cloud Vision, `verdict`

This is the living status document. Read it first in any new session, then
`DECISIONS.md` for the *why*. Update the "Last updated" line, the numbers and
the "Next" list whenever something changes.

> The blueprint (`insidelabel-blueprint.md` §15-16) says the 15-week beta plan
> lives here. That plan was never committed to the repo. Its known anchors are
> recorded under **Timeline** below; rebuild the week-by-week plan here when you
> next plan.

---

## 1. What InsideLabel is (one paragraph)

An Android app (a PWA wrapped for Play Store, D-010) for Indian packaged food.
You photograph the pack; it tells you what is in it and where the front of the
pack disagrees with the ingredient list. Launch audience: allergy households and
parents of young children (D-052). **AI only reads the label; deterministic rules
over our data tables make every judgement** (D-004), and every judgement uses
**FSSAI rules only** (D-086). The verified catalogue is the asset, not the AI
(D-029).

---

## 2. What works today

| Area | State | Where |
|---|---|---|
| Ingredient engine (INS parsing, NOVA markers, 3-band verdict, admin-only score) | ✅ | `src/insidelabel/core/` |
| INS parsing - 3-4 digit numbers, `()[]{}` brackets, `&` separators, unit guard | ✅ reads every printed INS on all 6 gold labels | `core/tokenize.py` (the only INS parser) |
| Additive table - 66 additives, all with an FSSAI basis (35 checked 2026-09-25, 31 on 2026-09-26, D-111); a test keeps every row that way | ✅ | `data/additives.json` |
| Vision read (Gemini `gemini-3.6-flash`) + independent OCR cross-check: Google Cloud Vision when `GOOGLE_VISION_KEY` is set, Tesseract otherwise (D-093: 3.6 s vs 22.7 s, recall 50/52 vs 27/52, 0 wrong additions) | ✅ | `extraction/providers/` (`cloud_vision.py`, `ocr_check.py`) |
| Scan speed: Cloud Vision reads **alongside** Gemini; `/scan` runs the slow calls on worker threads so one scan never freezes the server | ✅ real scan 6.9 s (was 15.7 s); Gemini itself varies 7-28 s with Google's load | `api/main.py` |
| Setup alarms: out of credit (402), key rejected (401/403), no key, Cloud Vision billing → plain "not available" to the user, `SETUP ALARM` in the log, a `server` problem report once an hour | ✅ checked against a real 402 | `gemini.VisionConfigError`, `cloud_vision.take_alarm` |
| Reliability gate (never shows "clean" on a partial read) | ✅ | `reliability/gates.py` |
| Claim checker (no added sugar / no preservatives / made with real X) | ✅ built; **in shadow for the beta (D-051)**: stored for reviewers, shown to users only with `INSIDELABEL_CLAIMS_TO_USERS=on` | `claims/checker.py` |
| Allergen check, five states, stricter 0.95 gate, first key in every result | ✅ | `lenses/allergens.py` |
| Shelf comparison (2-4 packs, best pick for a child) | ✅ `/compare` | `lenses/compare.py` |
| India vs EU vs US comparison - optional, information only | ✅ 12 additives | `lenses/regulators.py`, `data/regulatory_status.json` |
| Wording lint (no "misleading/illegal/toxic/safe/free from…") on tables **and** live output | ✅ in the test suite | `tests/test_wording.py` |
| Postgres schema with rules enforced by the DB | ✅ 14 migrations, all applied to the local DB (001-014) | `migrations/` |
| Marketplace leads → physical label → record (D-089); only `physical_label` versions can publish | ✅ | `db/leads.py`, `tools/leads.py`, migration 005 |
| Scan persistence: barcode lookup, review queue, findings + evidence, photos | ✅ when `INSIDELABEL_DB` is set | `db/store.py`, `media.py` |
| Reviewer screen (`/review`) - the only path into the catalogue; FSSAI food category required on approve | ✅ | `review/` |
| FSSAI food categories (Appendix A Food Category System, 271 codes) | ✅ loaded by `migrate` | `data/food_categories.json`, `db/categories.py` |
| "Report a mistake" `/report`, "ready?" `/updates` | ✅ | `api/main.py` |
| Result-screen block (`screen` in `/scan`): people first, headline from a finding, D-063 names, grouped ordinary items, no score; `profiles` with names kept on the device | ✅ D-091 | `lenses/screen.py` |
| Reproducing problems (D-092): request ids, a replayable trace on every scan row, "Report a problem" + automatic crash and server-error reports, `tools/repro.py` | ✅ proved end to end (app → server → report → replay "same as what the user saw") | `trace.py`, `repro.py`, migration 006, `tools/repro.py` |
| Exact replays (D-094): Cloud Vision's text stored on every scan row; `repro.py` replays it and never calls Google | ✅ overnight | migration 007, `cloud_vision.replaying()` |
| Rate limits on `/scan`, `/problem`, `/send-to-us` per install and per IP (D-095); the beta's 15 photo scans per install a day with its own screen (D-148) | ✅ overnight; in memory, one process; D-148 on `beta-limit` | `ratelimit.py` |
| "Send it to us" after two refused scans (D-070, D-096) | ✅ overnight; walked in headless Chromium against a faked API, not on a phone | `POST /send-to-us`, migration 008, `web/app.js` |
| One login per reviewer (D-097); shared token only until the first account | ✅ overnight | migration 009, `review/accounts.py`, `tools/reviewers.py` |
| Photo retention job, 30 days, holds respected (D-080, D-098) | ✅ overnight; runs nowhere yet (cron at deploy) | migration 010, `retention.py`, `tools/retention.py` |
| Web app / PWA: barcode → back photo on 404 → result; household profiles + consent; compare; report a mistake; `/updates` on open; offline shell | ✅ built; **first real-phone scan on the live site 2026-09-27** (invite link, "Before you start", barcode, back photo, result); profiles, compare and report not yet walked on a phone; stack is D-090 | `web/`, served at `/app/` |
| Hosting (D-114): Google Cloud VM `insidelabel-1`, Mumbai, `e2-medium`, Ubuntu 24.04; Caddy HTTPS, one uvicorn, PostgreSQL 18; nightly backup + photo cleanup; daily disk snapshot | ✅ **live 2026-09-27** at https://insidelabel.ai (IP `8.234.95.74`); restore test PASS 2026-09-27 | `DEPLOY.md`, `deploy/` |

**Accuracy on the gold set (6 real labels, `tools/eval_vision.py`):** 0 verdict
flips, INS F1 1.000 (0 missed, 0 hallucinated), ingredient F1 0.945 (98.0% expected with D-137's gold, re-score pending), front-claim
F1 0.883. Gold scores: Britannia 48, Limca 80 (×2), Maliban 56, Patanjali 48,
Ziggy 28. **The set is 6 labels; the RUNBOOK target is 20-30** - the accuracy
question the README asks is not answered yet.

**Catalogue:** 5 published products on the local database (review items #1, 3, 4, 5, 6);
#2 and #7 rejected as duplicates, #8 (empty report) rejected. **#9 is open**: Sushil's own
empty "Report a mistake" test, which he will reject on `/review`. **None of the 5 has a
barcode yet** - Sushil will send them; add each to `products.barcode`.

---

## 3. Set up from scratch (WSL Ubuntu 24.04)

```bash
cd ~/insidelabel
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                      # fastapi, psycopg, jinja2, google-genai, pgserver, pytest…
sudo apt install -y tesseract-ocr            # independent OCR cross-check (5.3.4 here)

# PostgreSQL 19 (beta until GA ~end Oct 2026) on 5432 - D-087
sudo PG19_PORT=5432 bash tools/install_pg19.sh   # adds apt.postgresql.org, creates cluster + role
createdb insidelabel && createdb insidelabel_test
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"

pytest -q                                    # 375 pass, 1 skipped; DB tests use embedded Postgres
```

**Environment variables**

| Variable | Needed for | Notes |
|---|---|---|
| `GEMINI_API_KEY` | real `/scan` vision calls | tests replay recorded JSON, no key needed |
| `INSIDELABEL_DB` | storing scans, catalogue, `/review`, `/report`, `/updates` | unset → API stores nothing, behaves as before |
| `INSIDELABEL_MEDIA` | where scan photos go | default `./media` (git-ignored) |
| `INSIDELABEL_REVIEW_TOKEN` | reviewer screen **until the first account exists** (D-097) | then refused; accounts via `tools/reviewers.py` |
| `INSIDELABEL_ALLOW_REPLAY` | the `replay` form field on `/scan` (D-101) | default off (403); `repro.py`, tools and tests switch it on in-process |
| `INSIDELABEL_PROXY_HOPS` | rate limits behind a reverse proxy (D-095) | number of proxies; unset → the socket address, `X-Forwarded-For` ignored |
| `INSIDELABEL_LIVE_SHUTTER` | the app's own shutter for the label photos (D-171) | default `off` (the phone's camera app); **`on` on the server since 2026-10-07** while the comparison runs (§8) |
| `INSIDELABEL_PUBLIC_URL` | the site's address in `settings.env` (D-114) | read by no tool since D-184 (the join links went with the invite codes) |
| `INSIDELABEL_TEST_PG` | run DB tests on a real server | must name a `*_test` database |
| `INSIDELABEL_CLAIMS_TO_USERS` | show the claim check to users (D-051) | default `off`; turn on only after ≥ 5 claim packs with 0 false contradictions |
| `INSIDELABEL_DATA` | alternate `data/` dir | rarely needed |
| `GOOGLE_VISION_KEY` | Cloud Vision as the OCR cross-check (D-093) | API key restricted to the Vision API; project billing must be on. Unset → Tesseract. Never commit it. |
| `INSIDELABEL_OCR` | force a reader | `tesseract` to compare or fall back; default `auto` |
| `INSIDELABEL_BUILD` | the build name on every scan and report (D-092) | set at deploy (no `.git` there); locally the git commit is read |
| `INSIDELABEL_WEB` | alternate `web/` dir for the PWA | rarely needed |

**This machine right now:** PostgreSQL **19beta4 on 5432** (default) and
**18.6 on 5433** (fallback, holds an older copy of the empty schema). Role
`insightstack` with CREATEDB, peer auth (no password). Databases `insidelabel`
(migrations 001-014, 5 products published, review queue empty, reviewer account
`sushil`, no leads yet) and `insidelabel_test` (only used to
create/drop per-module test databases). PostgreSQL 16 was removed.

**Keys (in `~/.bashrc` only - never in the repo):**
- `GOOGLE_VISION_KEY` - restricted to the Cloud Vision API; billing on in Google Cloud
  project **797275767015**.
- `GEMINI_API_KEY` - `~/.bashrc` has **three** lines (126-128); only the last one counts.
  It belongs to an AI Studio project on **prepaid** credit: it ran out once today (402)
  and was topped up. Delete lines 126-127 (`sed -i '126,127d' ~/.bashrc`), restrict the
  key to the Generative Language API, and consider auto top-up or post-paid billing.
- `INSIDELABEL_REVIEW_TOKEN` - removed 2026-09-25; `/review` uses the `sushil` account (D-097).
- The dev server runs with `--reload`, so code changes apply at once, but a **new key
  needs a restart** (Ctrl+C, then start it again from a terminal that has the key).

---

## 4. Daily commands

```bash
# API, with storage and the reviewer screen
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \
  uvicorn insidelabel.api.main:app --reload
#   http://127.0.0.1:8000/docs     API
#   http://127.0.0.1:8000/review   reviewer screen (reviewer login, D-097)
#   http://127.0.0.1:8000/app/     the PWA (camera needs HTTPS or localhost; see §8 item 6)

pytest -q                                                    # everything, embedded Postgres
INSIDELABEL_TEST_PG="postgresql:///insidelabel_test?host=/var/run/postgresql" pytest -q   # on PG19
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"   # new migrations

python tools/eval_vision.py --gold gold/ --pred predictions/ --csv /tmp/eval.csv   # accuracy
INSIDELABEL_DB=… python tools/queue_predictions.py           # queue recorded scans for review, free
INSIDELABEL_DB=… python tools/leads.py list                  # products seen online, waiting for a real pack (D-089)
INSIDELABEL_DB=… python tools/repro.py list                  # problem reports (D-092); `show <id>` replays one
INSIDELABEL_DB=… python tools/reviewers.py add <name>         # reviewer login (D-097); list / reset / disable
INSIDELABEL_DB=… python tools/retention.py                    # photos due for deletion (D-098); --apply deletes
python tools/compare_ocr.py --csv /tmp/ocr.csv                 # Tesseract vs Cloud Vision on the gold photos (D-093)
```

---

## 5. Session log - 2026-09-25 (one long session)

What was done, in order, with the result. Decisions D-085 → D-089 were added; D-051, D-052, D-055 decided.

1. **Allergen check wired into `/scan`** (D-060/71/72) + `/allergen-check`, `/allergens`. ✅
2. **Wording lint** (D-042) over tables and live output of every endpoint. ✅ Nothing in the current text violated it.
3. **`/compare`** endpoint for shelf comparison (D-057). ✅
4. **INS parser fixed** - the big one. Found: 4-digit INS dropped (1422 → 142), `e`/`ins` matched inside words (*"Tomato paste 250 g"* was flagged **sodium nitrite**), units read as suffixes, `[]`/`{}` brackets and `&` ignored, class words missing, three copies of the logic. On real labels the engine had seen **3 of 12** INS on Britannia and **12 of 20** on Ziggy. Now 100 % on all 6, one parser. ✅
5. **26 additive rows added** (5 more in step 7, 33 verified in all), each checked against the Codex INS list and the FSSAI compendium (Version XXVI, 20.12.2022) and the 2025 amendment. ✅
6. **D-085 scoring:** a `low` additive only costs points with a concern flag. ✅
7. **D-086 FSSAI basis + India/EU/US comparison** (information only, opt-in). Titanium dioxide re-based `high`→`moderate`; foreign-ban wording removed from scores. ✅
8. **Postgres schema** (D-020) with DB-enforced rules; embedded test server. ✅
9. **PostgreSQL 19** installed side by side (D-087) - see failures below. ✅ in the end.
10. **`/scan` persistence**: barcode lookup, review queue, reformulation detection, findings + evidence, `/report`. ✅
11. **Reviewer screen** `/review`, photo storage, `/updates`, 6 real packs queued. ✅
12. **Docs for handover**: `STATE.md` (this), `CLAUDE.md`, README rewrite, RUNBOOK/API_README fixes, memory. ✅
13. **Release gate** `tools/release_check.py` + §11 release plan; last two `verify:true` rows (124, 129) verified. Retailer-scraping idea checked against Amazon/Flipkart terms and FSSAI's 2024 e-commerce advisory → D-088 recommended instead. ✅
14. **Swiggy / Instamart terms read first-hand** (same no-copy clause, manual copying included); Zepto / Blinkit only via search excerpts (pages block scripts). **D-088 accepted; D-089 added** (Sushil's flow: a listing screenshot is a lead, the physical label is the record): migration 005 (`product_leads`, `production_source` on every version, DB refuses to publish a non-label version), `tools/leads.py`, review screen shows provenance and refuses listing-read versions. 8 tests. Applied to the local DB. ✅
15. **D-051 / D-052 / D-055 decided** (delegated by Sushil): claim check ships in shadow behind `INSIDELABEL_CLAIMS_TO_USERS` (1 test); wedge = allergy households + parents; stop rule 30 % / 20 % at W4 on ≥ 50 activated users. ✅
16. **Food categories + picker**: parsed Appendix A Part I (compendium XXVI) into `data/food_categories.json` (271 codes; 16 "Prepared foods" from Part II; PDF spacing fixed; "articulated" → "particulated" per Part II). `migrate` syncs them; `/review` requires a category, with a shortlist whose hints quote each category's Part II description. Release gate counts 7.2.1 / 7.2.2 (not 7.2.3 mixes). 3 tests. ✅
17. **PWA (§8 item 6)** - see the entry below the list. ✅ built; phone test pending.

---

### Commits pushed today (github.com/sushil6666/InsideLabel, `main`)

| Commit | What |
|---|---|
| `e46b30e` | Everything up to the PWA: engine, API, review screen, PWA (D-090, D-091) |
| `a0b109b` | D-092: every problem can be reproduced |
| `0b89527` | D-093: Cloud Vision as the independent OCR reader |
| `2839bce` | `/docs` no longer pre-fills "string" into `/scan` fields (the 422 Sushil hit) |
| `dfc91a7` | Cloud Vision alongside Gemini; `/scan` no longer blocks the server |
| `1cc7585` | Setup alarms for credit, key and billing errors |

### PWA session (later on 2026-09-25)

- **`screen` block on `/scan`** (`lenses/screen.py`, D-091): all result-screen
  wording on the server so the lint covers it. Profiles via the `profiles` form field;
  names never sent (the `{name}` placeholder is filled on the device). Allergen text
  learnt `who="you"` ("your avoid list"). 9 tests in `tests/test_screen.py`, one more
  assertion on the catalogue path, the wording lint now covers `screen`.
- **PWA in `web/`** (D-090): no build, served at `/app/`. Walked end to end in headless
  Chromium at phone size (welcome → household + consent → barcode → 404 → photo →
  result → compare → report → refused scan/retake): no page errors, the nickname
  never reached the server, no `{name}` or stray `false` left on any screen.
  7 static tests in `tests/test_web.py` (wording lint over the JS/HTML, no score,
  no `innerHTML` from strings, only ref/age/avoid leave the device).
- **Not built, on purpose:** share target (D-077 → after W4, D-083); "send it to us"
  (item 7 - after two failed retakes the app gives tips instead of a promise it can't
  keep); live "found 14" progress (D-068) - the API has no progress events, so the
  app shows elapsed time and "8-15 seconds".

### D-092 session (later on 2026-09-25): reproducing problems

Sushil's ask: when a user hits an error, capture everything from the start to the
error, with proof to reproduce it. Built in four steps, each tested:

1. **Request ids + versions** (`trace.py`): `X-Request-ID` on every response and log
   line, `build` + `data_version` in `/health`. Migration 006 puts the model's raw
   answer, request options, versions and timings on **every** scan row. Found and
   fixed on the way: the raw answer used to live only on a (shared) product version and
   was lost for refused/failed scans; a read with no parseable ingredients wasn't
   recorded at all.
2. **Report a problem** (`POST /problem`, `problem_reports`): the app's 60-event trail,
   a "what we'll send" preview, photos held for every scan in the trail. Unhandled
   server errors become `server` reports.
3. **`tools/repro.py`**: trail + versions + replay of each scan with storage off, diffed
   against what the user saw; `--save` makes it a regression test.
4. **Automatic crash reports** from the app, deduplicated.

Proof: headless Chromium → real server on a scratch PG19 database → a result, a
refusal, a planted crash, a user report → `repro.py show` rebuilt the 27-event trail
and replayed both scans: **"same as what the user saw"**. `--save` produced a test that
passed, and failed once `expected` was edited. 20 new tests (171 total). Migration 006
applied to the local `insidelabel` database (6 scans and 6 queued items intact).

**Finding from the first trace:** the Tesseract cross-check took **28.4 s** on a
1600 px photo (Ziggy), almost the whole scan, against the "8-15 s" the app promises
(D-068). Measured on WSL; check on the deploy host before changing anything.

### Cloud Vision (later on 2026-09-25) - D-093 locked

Built `cloud_vision.py` (one cached call per photo, circuit breaker, Tesseract
fallback), wired into `ocr_check.py` with the same guards; 8 tests with a faked
Google API; `tools/compare_ocr.py`. Sushil restricted the key to the Vision API and
enabled billing on project 797275767015. On the 6 gold photos: **3.6 s vs 22.7 s per
label, 50/52 vs 27/52 printed INS, 49/51 simulated omissions put back, 0 wrong
additions**; the full Ziggy scan went from 28.6 s to 4.0 s. A line-break bug in the
context rule (5 of Ziggy's numbers) was found and fixed on the way.

### Scan speed (later on 2026-09-25)

Sushil's first real scan through `/docs` (Ziggy, front + back) took 15.7 s: Gemini
10.4 s, then Cloud Vision 5.3 s. Two changes:

- **Cloud Vision starts with Gemini**, not after it; the cross-check finds the text in
  its cache. Measured: the OCR now adds ~0.1 s to a scan.
- **`/scan` no longer blocks the server.** Gemini and OCR ran directly inside an
  `async` endpoint, so one 10-15 s scan froze every other request (two parents
  scanning at once would have queued). They now run on worker threads. Both
  properties have tests that fail on the old code.

**Now the only slow step is Gemini, and it varies a lot:** 10.4 s, ~16 s and 28.4 s
on three real calls of the same pack today; app-sized photos (1600 px) didn't help.
Every scan now records `timings.vision_retries` (attempt, wait, error), so the beta
data will show whether that's the model being busy (retries) or slow (none). Don't
tune anything until there are numbers from real scans.

### Gemini keys and setup alarms (later on 2026-09-25)

Three Gemini keys tried in one afternoon (`~/.bashrc` lines 126-128; only the last
counts): the first two worked but `gemini-3.6-flash` and `gemini-3.5-flash` both
answered **503 "high demand"** to our label request (text-only pings got through);
the third answers **402 "prepayment credits are depleted"** - its AI Studio project
needs a top-up. The `gemini-3.5-flash` fallback comparison couldn't run (every call
refused); retry it when Google is quieter.

New: `VisionConfigError` for setup failures (no key, 401/402/403/404, "API key not
valid"). `/scan` answers `503 vision_not_configured` ("isn't available right now"),
logs `SETUP ALARM`, and files a `server` problem report (`vision_config:402`) at most
once an hour. Cloud Vision setup failures (billing, key restriction) raise
`ocr_config:http_403` the same way, since they silently cost ~20 s per scan.
`tools/repro.py list` shows both. Checked against the real 402.

### Overnight session - 2026-09-26 (Claude, unattended; STATE §8 items 5-9)

Branch `overnight-2026-09-26`, merged to `main` ([PR #3](https://github.com/sushil6666/InsideLabel/pull/3)). Every
new test was run against the old code first and failed; the suite was green before
each commit. No paid calls (Google's HTTP answers faked, model answers replayed); the
local `insidelabel` database, `photos/`, `media/`, `research/`, `predictions/` and
`reports/` untouched; migrations tested on the embedded test Postgres only.

| Commit | Item | What |
|---|---|---|
| `be4348f` | 5 | Cloud Vision's text on the scan row (migration 007); replays use it and never call Google, even without the photo; saved regressions carry it. **Found:** a refused read where OCR found an additive crashed `/scan` with a 500 (`KeyError 'caveats'`) - fixed. D-094. 5 tests |
| `ea3f308` | 6 | Rate limits per install + per IP, before any photo is read; separate budgets for photo scans, barcode lookups, problem reports; 429 + `Retry-After`; PWA shows the server's message. D-095. 11 tests |
| `e2044f4` | 7 | "Send it to us": `POST /send-to-us` (server checks: own scans, all refused, ≥ 2), one review item with every attempt (migration 008), photos held, reviewer page shows all attempts + the barcode; PWA button after the 2nd refusal. D-096. 10 tests |
| `a980caf` | 8 | Reviewer accounts (migration 009, scrypt, `tools/reviewers.py`, per-reviewer CSRF, login throttling) and the retention job (migration 010, `tools/retention.py`). D-097, D-098. 21 tests |
| `10c3eb0` | 9 | One INS parser: `compare.py` **and** four more private patterns (claim checker, eval_vision, stability_check, coverage_report) now use `core/tokenize.py`. **Found:** `/compare` missed Maliban's "160 a(ii)" and read "Raisins (150gm)" as an unknown additive. Test forbids new patterns. D-099. 5 tests |

Tests 193 → 245 (+52), 1 skipped. Release gate unchanged: 2 computed gates failing
(gold set size, ingredient match), both data, not code.

### After the overnight session - 2026-09-25 evening (branch `front-photo-flow`)

Built on top of the overnight branch (rebased onto `91f46c6`), in a separate worktree so
the unattended session wasn't disturbed.

- **D-100, the front photo once per pack.** `/scan` says `front_wanted`; barcode + front
  alone → a `front_photo` review item (migration 011), no model call; a re-check with a
  trusted pairing queues it too; approval records the photo even with no claims. PWA: the
  front is a visible card on first scans, "Add the front of the pack?" on catalogue hits.
  **Found:** a re-check of a published pack silently dropped its front photo; and the
  pairing checkbox showed before any front photo (`[hidden]` lost to `display: flex`).
  4 tests + a headless-Chromium walk against a scratch DB.
- **D-101, `replay` off on servers** unless `INSIDELABEL_ALLOW_REPLAY=on`; repro, tools
  and tests switch it on in-process. 3 tests.
- **D-094 to D-101 accepted by Sushil and locked**, including the two explicit points
  (D-095: a 429 is not a scan row; D-097: the token bootstraps until the first account).
- Tests 245 → 252, 1 skipped.
- **D-054 decided** (`a198535`): "100% ATTA" is about the flour, so no finding. Tests 253.
- **Merged** ([PR #1](https://github.com/sushil6666/InsideLabel/pull/1) `front-photo-flow`,
  [PR #3](https://github.com/sushil6666/InsideLabel/pull/3) overnight); `main` = `a198535`, pushed.
  Sushil then migrated the local DB through 011, created the `sushil` reviewer account,
  removed `INSIDELABEL_REVIEW_TOKEN` from `~/.bashrc`, and cleared the review queue
  (#1, 3, 4, 5, 6 published; #2 and #7 rejected as duplicates).

### First supermarket run on the live site (2026-09-27, Sushil in the shop, Claude reviewing)

Sushil scanned real packs on https://insidelabel.ai and published them through `/review`, sending a
screenshot of each item. Findings, in the order they were found. **Nothing here is fixed yet except
the decimal split.**

**Categories assigned** (keep these for consistency when the same products come back):

| Pack | Category | How it was decided |
|---|---|---|
| ORGANIC INDIA Tulsi Mulethi | none: **rejected** | AYUSH medicine licence, no FSSAI licence (D-116) |
| DiSano Peanut Butter Chocolate Crunchy | 4.2.2.5 | **the pack declares it**: "Proprietary Food - 4.2.2.5 Spread" |
| Maliban Wafer Cheese Flavour | 7.2.1 | Codex descriptor: sweet biscuit. 7.2.2's "wafers" means ice cream wafers/cones |
| Sundrop POPZ Chocolatey Crunch | 6.3 | judgement call: extruded multigrain from flour. 15.1 is savoury snacks only |
| Sunfeast farmlite Oats & Chocolate Cookies | 7.2.1 | Codex descriptor: cookies |
| Lotus Biscoff Caramelized Cookie | 7.2.1 | Codex descriptor: sweet biscuit |
| Anmol dream LITE | 7.2.1 | sugar and liquid glucose 3rd and 4th, so not a 7.1.2 cracker |
| Bisk Farm TOP GOLD | 7.2.1 | sugar 3rd, despite cheese and butter flavour |

**1. Data gaps in `data/additives.json`** (each needs Appendix A verification before it is added, D-046):

- **INS 319 (TBHQ)** has no row. Seen twice: Sundrop POPZ ("Antioxidant (TBHQ)") and Bisk Farm
  TOP GOLD ("ANTIOXIDANT (319)", inside the oil). It passes silently even when numbered.
- **INS 472(e)** has no row. Seen on Anmol dream LITE and Bisk Farm TOP GOLD.
- **Sub-forms have no rows of their own**: 503(ii), 500(ii), 450(i), 1101(i), 322(i). They match the
  parent number today, which is probably right, but it has never been decided.

**2. The biggest one: a missing sugar name changes a verdict.** "Candy Sugar Syrup" is not in
`normalization.json` `sugar_aliases.added_sugar`, so **Lotus Biscoff reads as clean, grade A, score
100** while its own panel declares **36 g added sugars per 100 g** (sugar is the 2nd ingredient,
candy sugar syrup the 4th). Compare Anmol dream LITE the same afternoon: grade D, score 44. Same
category, opposite results. Fixing this changes verdicts on real packs, so: collect the missing
names, re-run the gold set, show Sushil what moves, then his decision.

**3. Tokenizer, two more bracket bugs** (the decimal split was found and fixed the same day):

- **Nested square brackets aren't handled.** `EMULSIFIERS [450(i), 472(e)]` and
  `PLAIN CHOCOLATE CHIPS (6.2%) [SUGAR, ... EMULSIFIER [LECITHIN (FROM SOYBEAN)], ...]` give
  fragments: `emulsifier ]`, `natural flavours and natural flavouring substances]`, `ins 503(ii`,
  `ins 450]`, `ins 472(e`.
- **Braces `{ }` are not treated as brackets at all** (only `( )` and `[ ]`), so Sundrop POPZ gave
  `multigrain flour mix {rice meal`, `oat meal }`, `antioxidant }`.
- **Why it matters now:** D-115 shows the label's own words on the result screen, so a user can see
  "such as emulsifier ]". Fix both together, with a gold-set re-run, like the decimal fix.

**4. Reader (Gemini) mistakes seen, none of them caught by a check:**

- **Compound ingredients split into separate top-level entries** at a bracket or brace: Sundrop POPZ,
  Sunfeast farmlite, ORGANIC INDIA Tulsi. The most common error of the day.
- **Text garbled and dropped**: Bisk Farm TOP GOLD produced `CONTAARTIFICIAL FOOD COLOUR (102)`,
  losing "AND ADDED ARTIFICIAL FLAVOURS (CHEESE, BUTTER)" entirely.
- **Wrong character**: Tulsi pack, `#` where the pack prints `*` (the organic marker).
- **Two ingredients joined on one line**: Tulsi, Sundrop POPZ.

**5. What users see (Sushil, in the shop): "not much useful for a user."** Not a bug report: a
product criticism of the result screen. To discuss with mockups. His examples come from packs where
the screen described the label instead of answering what a shopper wants to know. See also the
DiSano jar, where one ingredient (Stabilizer INS 471) produced two findings, a processing marker and
the additive itself, which may read as the same thing counted twice.

**6. Two useful facts about Indian packs, now proven in the shop:**

- **Proprietary foods often declare their own Appendix A category** (DiSano: "Proprietary Food -
  4.2.2.5 Spread"). Read it from the OCR text before guessing: it is the pack's own statement.
- **The FSSAI licence can be on any of the four sides, or behind a QR code** (Maliban: "scan the QR
  code and enter the first two characters of the batch no."). So **absence of a visible FSSAI number
  is never evidence that a pack is not food**. The D-116 check may only fire on an AYUSH licence
  being *found*.

**7. Assisted review, proposed as D-117** (not written up yet): the licence check, a comparison of
Gemini's list against the Cloud Vision text already stored on every scan (it would have caught the
Bisk Farm garble and the split compounds), the declared category read from the pack with a word
table as fallback, and a quick lane with one "Confirm and publish" button for items where the two
reads agree.

## 6. What went wrong, and what we learned

Keep this list - it is the cheapest way to not repeat a mistake.

| What happened | Lesson |
|---|---|
| `eval_vision.py` reported INS F1 = 1.0 while the parser missed a third of the additives | Gold and prediction go through the **same parser**, so they agree on its blind spots. `tests/test_ins_parsing.py` now checks the parser against the numbers actually printed on each gold label. |
| The FSSAI PDF lists INS numbers (e.g. potassium bromate, azodicarbonamide) in a reference list copied from Codex | Being in that list ≠ permitted. **Permitted means an Appendix A provision** (GMP table or a numeric limit). Always check which part of the document a hit comes from. |
| EUR-Lex and legislation.gov.uk return empty pages to scripts; eCFR's API needs `--compressed`; ecfr.gov web pages redirect | Use the FSAI (Ireland) consolidated PDF for EU text; use `https://www.ecfr.gov/api/versioner/v1/full/<date>/title-21.xml?part=…&section=…` with compression for US. The EU copy we have is consolidated to **2018** - replace it with a current EUR-Lex download (manual, in a browser). |
| `pgserver` (embedded Postgres for tests) lacks `pg_trgm` | Migration files that need an extension start with `-- requires-extension: <name>`; the runner skips them only on the embedded server. |
| `install_pg19.sh` v1 assumed Ubuntu would create the 19 cluster; it doesn't when a cluster already exists | Script now runs `pg_createcluster` itself. |
| Installing `postgresql-19` from apt.postgresql.org **also pulled in `postgresql-18`**, and 16 was then upgraded to 18 (`pg_upgradecluster`, source unconfirmed) | Check `pg_lsclusters` before and after any Postgres apt operation. Data survived (pg_upgrade). |
| Early checks said Postgres wasn't installed, then it was | Re-check the system state before acting on an earlier observation. |
| `pkill -f "<pattern>"` killed its own shell (the command line contained the pattern) | Kill by PID, or use a pattern that can't match the pkill command itself. |
| A PL/pgSQL trigger read `NEW.id` on a table without an `id` column | Separate trigger functions per table; test the trigger on every table it's attached to. |
| Starlette's `TestClient` here has no `auth=` | Send `Authorization: Basic …` as a header. |
| The first release-check run showed "false contradictions 0 of 0 - PASS" | A gate with no data is **unmeasured**, not passed. `release_check.py` reports it as TODO. |
| Several test expectations were wrong the first time (e.g. `322 and 471`) | When a new test fails, decide whether the code or the expectation is wrong before changing either. |
| The first result screen said "39 other ingredients look ordinary" above "All 20 ingredients" (parsed items vs label lines) | Only a rendered screen showed it. Look at the real page, not just the JSON; keep every count on one screen in one unit. |
| `node.append(cond && el(...))` printed the word "false" on the retake screen | The DOM's `append()` stringifies `false`; `el()` skips it. The browser walk-through now fails on stray `false/undefined/null`. |
| A bulk find-and-replace (`view.append(` → `put(`) also rewrote `put`'s own body → infinite recursion | After a scripted replace, read the helper it touched. |
| "Stopped test server" wasn't: `$!` after `( … & )` or `env … &` is a wrapper's PID, and the real uvicorn kept running on 8765 | After starting anything in the background, read the real PID from `ps` (not `pgrep -f`, which matches its own shell) and confirm it's gone after `kill`. |
| An e2e step "failed" because the test's barcode had a wrong check digit - the app was right to refuse it | When a test fails, read the screen before touching code. |
| The trail's photo events showed as `image/jpeg` - `record("photo", {type: …})` overwrote the event type | Spread the caller's data first, then the fixed keys: `{...data, t, type}`. |
| Cloud Vision "missed" 5 Ziggy additives it had read perfectly - a newline sat between "Acidity Regulators" and "(330, 270)" | When a reader misses something, look at its raw text before blaming the reader. |
| A test for "the server stays responsive during a scan" passed on the old, blocking code: a blocked event loop also froze the test's own `sleep`, so it timed the wrong thing | Run every new test against the old code once. A test that can't fail proves nothing. |
| `/docs` answered 422: Swagger's Try it out fills every text box with "string" (avoid=string → unknown allergen) | Give form fields empty examples; treat "" as absent. Check the real `/docs` page, not just the JSON schema. |
| Three failure types from Google in one afternoon: 503 "high demand" (theirs, retried), 402 "prepayment credits are depleted" (ours, billing), text pings fine while image scans failed | Read Google's message before touching code. A "busy" is not a bug; an "out of credit" is a setup alarm, not a retry. |
| Prepaid Gemini credit ran out silently: every scan would have failed with a vague error | Setup failures must alarm the developer, not just fail the user (`vision_config:*`, `ocr_config:*`). |
| Headless Chromium on this box lacks `libnss3`/`libnspr4`/`libasound2` | `apt-get download` + `dpkg -x` into a scratch dir + `LD_LIBRARY_PATH` - no sudo needed. (Scratch dirs don't survive sessions: redo it each time.) |
| Item 9 named one private INS regex; a search found five, most reading 3 digits (1422 → 142) | Search for the *shape* of a thing, not its name. A test now fails on any INS-shaped pattern outside `tokenize.py`. |
| The eval showed INS F1 = 1.0 with a parser that truncated 4-digit numbers | Same lesson as the first row, again: gold and prediction shared the blind spot. |
| A refused scan crashed with a 500 only when OCR also found an additive; no test had combined the two | Found while testing something else (OCR text on refused scans). Combine outcomes in tests, not just features. |
| A retention job run between "list" and "delete" could remove a photo a user had just re-sent (keys are content hashes) | Re-check each key right before deleting it; test the race with the check switched off. |


### 2026-10-01 (Sushil and the advisor)

| What happened | Lesson |
|---|---|
| **Photo scans took 53 s** (scan `ef4186a3`). From 18:02 UTC every Cloud Vision call returned HTTP 200 with a per-image error `{"code": 8, "message": "Resource has been exhausted (e.g. check quota)."}`, so scans fell back to Tesseract. A curl of one 512 px image failed the same way, and so did a brand-new API key restricted to Cloud Vision: the refusal is project-wide, not the key. One call around 19:00 succeeded (a coincidence); code 8 was back at 19:26, after the budget change. Ruled out: the budget (Billing > Budgets & caps, "cloud vision": "Spend cap status: Not applicable", Sushil's screenshot; alerts only, no cap, it never paused anything; now Rs 3,000 a month, alerts at 50, 90 and 100%), the quotas (defaults, 1,800 a minute, 0.04% used, no overrides, no per-day limits) and the key. Not tested: the VM's service account lacks the scope to call Vision (403). **Cause still open.** Likely, not confirmed: an automatic project-level limit after the laptop's `pytest` bursts of 27 to 30 September (next row but one). The support plan is Basic (billing only, no free technical case); Sushil asks on the Google Cloud Community and the Issue Tracker. It may last days. Corrected 2026-10-02: an earlier version blamed the budget's spend cap; the budget has no cap. | On Vision code 8, follow OPERATIONS.md section 6 in order (log, one-call test, quotas, budget, traffic by credential, a new restricted key, then the Community). A Vision outage must alert Sushil (the scan-speed branch), not show up as slow scans. |
| **Why the scans took 50 to 80 s, and the fix (branch `scan-speed`).** With Vision refusing, the cross-check and the two identity checks re-read the back photo with Tesseract **after** Gemini had answered: nine passes one after another (measured in the cloud checkout, Gemini mocked at 8 s: a 1-photo scan 17.0 s, 3 parts 16.1 s; on the server's two slower CPUs, 50 to 80 s: ef4186a3 took 54 s). A per-image code 8 tripped the breaker for only 60 s, so 44e92599 logged two Vision errors 79 s apart in one scan; no alarm was raised (a code 8 wasn't counted as a setup problem), and the app's 20-second line said "the reader is busy". The fix: one independent read of the back photo per scan, started alongside Gemini (Vision, or Tesseract's six passes two at a time); every check uses it; the result never waits for it (a fallback not done when Gemini answers counts the passes finished, or is skipped and recorded "ocr: skipped (deadline)"); a code 8 or HTTP 429 trips the breaker for 10 minutes and files a `server` problem report. Measured after: 1 photo 8.2 s, 3 parts 8.6 s (Gemini's 8 s), Vision called once per scan. | **Cloud Vision code 8 can arrive with HTTP 200 and no visible quota use.** Treat it as an outage, alarm on it, and never let the fallback sit on the critical path. |
| **The Rs 501.75 was not users' scans.** Testers made 65 photo scans from 27 to 30 September: a few hundred Vision calls, inside the 1,000 free a month. The Vision API's Metrics, "Traffic by credential", showed two keys: `server-vision` (the server, tiny) and `insidelabel` (Sushil's laptop, exported in `~/.bashrc`), with bursts up to 0.4 calls a second from 27 to 30 September. Laptop `pytest` runs sent the tests' fake images to Google until `tests/conftest.py` started removing `GOOGLE_VISION_KEY` (commit 5bae400, 2026-09-30 07:13 UTC). Sushil removed the key from `~/.bashrc` on 2026-10-01. | A paid key is never in a shell profile; it is set for one approved command only. |
| **Gemini is billed separately**, in Google AI Studio (Gemini API Billing), on prepay: Rs 394.71 left on 2026-10-01 with auto-reload off. Gemini cost about Rs 85 from 25 September to 2 October. | At Rs 0 every photo scan fails: watch the AI Studio balance as well as the Cloud bill (OPERATIONS.md section 7). |
| **The cloud build session has limits.** No keys and no server. `dl.google.com` is blocked, so the Android SDK and the Gradle plugin can't download and the `.aab` is built on Sushil's laptop. `photos/` and `predictions/` are gitignored, so gold re-scores run on the laptop (the D-137 re-score passed there: ingredient set F1 0.980, gate PASS). The cloud baseline has 1 extra skip (the gold photos test). | Anything that needs a key, the server, the Android SDK or the gold photos is a command for Sushil's laptop or the server, with its cost. |
| **A command with a placeholder like `<id>` fails in bash** ("syntax error near unexpected token `newline'"): bash reads `<` and `>` as redirections. | The advisor gives commands with real values, ready to paste. |

---

## Web beta first (2026-09-26, branch `web-beta`, D-102 recommended)

Sushil: launch the website first (domain ready), Android after; ~50 invited testers,
feedback from each. Built, tested (267 passing), walked in headless Chromium against a
faked API (link → join → welcome → home → scan → feedback → photo drop box):

- **Invite codes + gate** - migration 012, `/access`, `/join`, `INSIDELABEL_INVITE_ONLY`;
  `tools/beta.py invite | list | feedback | reset | revoke`.
- **Send feedback** - footer link, comment + 1-5, stored against the tester's code.
- **Take or upload** every photo; drag-and-drop on a computer; barcode from a photo where
  Chrome supports it, otherwise typed.
- **Landing page** at `/` + draft `/privacy` and `/about` (`web/site/`).
- Found and fixed: `go()` to the page already showing did nothing (stuck on welcome after
  joining).

**Sushil, to launch:** accept D-102 → fill the `[To complete]` parts of `web/site/privacy.html`
and `about.html` (and a DPDP review) → deploy (§8 item 13) with `INSIDELABEL_INVITE_ONLY=on`,
then `migrate`, `tools/reviewers.py add`, `tools/beta.py invite 50 --base https://yourdomain`
(one link per person, labels like "T01 Priya") → send the links → watch `tools/beta.py list`
and `tools/beta.py feedback`. Seed the kids' biscuits first (§8 item 4): every pack not in
the catalogue is a paid 8-15 s read.

### D-112 built: the logo (2026-09-26, branch `additive-badges`)

Sushil picked B1 of three redraws of his Drive logo image ("yes pls B1"): white barcode bars
and a gold magnifier on a deep-green tile, no tick, no "food guardian". `web/icon.svg` and
`icon-maskable.svg` redrawn; PNGs `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`
rendered from them (for Play, §8 item 14) and listed in the manifest; the header "IL" text
mark is now the logo image in the app and on the landing, privacy and about pages.
`APP_VERSION` web-16. Checked in headless Chromium: header on light and dark, the mark at
16 to 192 px, the maskable icon cropped to a circle; the logo loads on every page.

### D-111 built: additive cards with a badge (2026-09-26, branch `additive-badges`)

Accepted by Sushil and locked.

- **Step 1, data:** the 31 additive rows without an FSSAI basis checked against the
  compendium XXVI Appendix A (GMP table pp. 736-741, category tables pp. 540-722,
  Annexure-1 groups p. 723): 14 GMP, 17 numeric limits (6 through a group: SORBATES,
  BENZOATES, SULFITES, NITRITES, PHOSPHATES, SACCHARINS). **Eight statuses were wrong**: MSG
  (621) is in the GMP table; 133, 150d, 200, 202, 339, 476, 960 have only numeric limits.
  Names and classes match the compendium's INS list. `tests/test_additives_data.py` now
  fails on any row without `fssai_status` / `fssai_basis` / `verified_on`.
- **The 2025 First Amendment** (in force 01.02.2026) was checked only through a trade
  summary (ChemLinked): FSSAI's site returns an empty page to scripts. Its Appendix A change
  (a steviol note in 14.1.5) and colour changes (purity, labelling) change none of the 31.
  **Sushil: download the amendment PDF in a browser** so it can be read first-hand (D-046).
- **Step 2, screen:** `lenses/screen.py` gives each additive `ins`, `label_line` and a
  `badge`; `screen.additives` lists them most serious first, "Permitted" ones folded behind
  one row; `screen.additive_alert` only for "not permitted" on a sure read (complete, ≥ 0.95).
  "Other ingredients look ordinary" no longer counts additives that have a card. PWA lays it
  out (`additiveCard`); `APP_VERSION` web-15. 6 new screen tests, all failing on the old code.
- **Walked** in headless Chromium, light and dark: the real Ziggy read (21 additives, all
  permitted, one folded row; the screen was ~10,000 px before folding, ~3,200 after) and a
  made-up pack with 924a / 102 / 503. **Found and fixed:** cards quoted the engine's token
  ("ins 503(ii") instead of the label line; 21 open cards made the screen unusable.
- Not built: the reviewer page doesn't show badges yet (a new barcode's scan already goes
  to review as a pending version).

### D-109 and D-110 built (2026-09-26, branch `report-note-and-look`)

Both accepted by Sushil and locked.

- **D-109:** `/report` refuses a report whose "What does the pack say?" and "What looks wrong?"
  both have fewer than 3 characters (422 `empty_report`, before anything is stored); the app
  shows the same sentence above the boxes and as the error. 3 tests (one checks the app's
  sentence matches the server's); the new refusal test failed on the old code.
- **D-110:** the Lovable look in `web/app.css` and `web/site/site.css` only (no JS logic
  change): cream, deep blue, leafy green, Bricolage Grotesque + DM Sans self-hosted in
  `web/fonts/` (96 KB, OFL licences beside them, cached by `sw.js`), soft shadows, pill nav,
  the "IL" mark, green app icon. Colours in hex (older Chrome has no `oklch()`); every text
  pair 4.5:1 or better in light and dark. `APP_VERSION` web-14, `sw.js` il-shell-14.
- **Walked** in headless Chromium at 390 px, light and dark, 13 screens each (landing,
  privacy, about, home, photo, household, a real result and a refused result from recorded
  reads, report with an empty send, compare, feedback, agree, problem) + welcome: no page
  errors, no stray `false`/`undefined`/`{name}`, no sideways scroll, fonts loaded. Found and
  fixed: the header pills wrapped at 390 px; the gradient repeated under short pages; the
  landing header had no top padding (`.wrap` overrode it, older than this change).
- `insidelabel_lovable/` is still in the repo as the reference (Sushil removes it when done).
- **Sushil, 2026-09-27: "We will not copy anyone, SafeLabel or TruthIn. We will work with the best we
  can give to the consumer."** Competitors are context, never a source of features, wording or data.
- **TruthIn** (truthin.ai, India, 1M+ downloads claimed): barcode or name search, a "TruthIn Rating"
  reviewed by nutritionists, healthier alternatives, TruthIn Plus with the "TIA" assistant; FoodPharmer
  (Revant Himatsingka) on its advisory board. InsideLabel differs on purpose: no score (D-064), any pack
  by photo, front vs back (D-001, D-051), every finding traced to the label and FSSAI (D-043, D-111).
- **SafeLabel** (Play Store, screenshots in Sushil's Drive `InsideLabel` folder, not in the repo):
  per-additive cards with Banned / Caution / Safe badges, E-numbers, a US-style pack. Its
  "Banned" on tartrazine is wrong (permitted in India, EU, US). Its layout became D-111.

### Session start, and D-109 proposed (2026-09-26, branch `report-needs-content`)

- PR #9 (`refusal-labels`, `05ba1fa`) and PR #10 are merged; local `main` = `origin/main` =
  `ca1f661`. `pytest -q`: **363 passed, 1 skipped**. Release gate unchanged: 2 failing
  (gold set size, ingredient match), 4 with the DB (plus catalogue size, kids' biscuits).
- **D-109 recommended, not built:** "Report a mistake" needs text in "What does the pack
  say?" or "Anything else?"; `/report` refuses an empty one (422 `empty_report`). Both
  reports so far (#8, #9) came in empty.
- **Left for Sushil to launch (D-102):** reject #9 on `/review`; on the deployed server,
  `migrate` then `tools/reviewers.py add sushil`; fill `[To complete]` in
  `web/site/privacy.html` and `about.html` and get a DPDP review; deploy with
  `INSIDELABEL_INVITE_ONLY=on` (§8 item 13); `tools/beta.py invite 50 --base https://<domain>`;
  replace the Limca 1 L gold image with a photo of a real bottle; send the barcodes of the
  published packs (none on file yet).

### Refusals name the wrong photo (2026-09-26, branch `refusal-labels`)

Sushil's test (screenshot back + real Ziggy front) was refused correctly, but the history
read "ZIGGY DONUT CAKE Choco Vanilla: This doesn't look like a food pack". Now, with two
photos, the refusal says "The back photo isn't a food pack" (or "is a photo of a screen"),
and a not-a-pack or two-pack refusal carries no product name. His "Report a mistake"
(review item #9: field "other", no note) is still open for review. Server problem #1
(UndefinedTable on /agree at 12:23, before migration 013) closed as fixed. Tests: 363.

### Front of one pack, back of another (2026-09-26, branch `pack-mismatch`, D-108 locked)

Sushil found a Patanjali front + Maliban back went through. Gemini had said "mismatch";
the code discarded it (it demanded a matching anchor), and the "same pack" tick then
attached Patanjali's claims to the wafer. Now a reasoned mismatch refuses the scan, the
tick can't override it, and "can't tell" says on screen that the front wasn't used.
All 12 genuine gold pair reads still pass. Tests: 358 passing.

### No barcode, no catalogue entry (2026-09-26, branch `no-barcode`, D-107 locked)

"No barcode? Photograph the ingredients" moved up to a full button under the camera. A
scan without a barcode shows its result with a note and creates no product, version or
review item (scan row kept for replay, migration 014). "Send it to us" and reviewer
publishing need a barcode. `queue_predictions.py` reads barcodes from the gold photos.
Tests: 351 passing.

### Uploads marked for reviewers (2026-09-26, same branch, D-106 locked)

D-102 and D-105 accepted. Each photo now says where it came from (camera or upload); the
reviewer page warns on uploads ("could be edited, AI-made or a screen") and the queue shows
an "uploaded" chip. Tests: 343 passing.

### "Before you start" (2026-09-26, same branch, D-105 locked)

Sushil: correct data first; expect wrong data and AI-made pictures in the beta. After
joining, every tester ticks "I agree" to five rules (real person, real packs only, no
AI-made/edited pictures or screenshots, a person may check, not medical advice). Text in
`data/terms.json` (versioned); migration 013 records who agreed; invite-only servers refuse
scans until then. Walked in headless Chromium. Tests: 335 passing.

### Barcodes, photo ticks, no dashes (2026-09-26, same branch)

- **D-103 and D-104 locked** (Sushil). D-104: no typed barcode; the camera or a
  photo read on the server (zxing-cpp, new dependency); `POST /check-photo` gives every
  photo a green tick or a red cross with the reason as soon as it is picked; a crossed
  back photo keeps "Check this pack" off. UPC-A stored as 13 digits. Walked in headless
  Chromium against a faked API.
- **No em or en dash anywhere** (Sushil): 731 replaced in 74 tracked files (user-facing
  lines by hand, the rest " - " / "to"); `tests/test_no_dashes.py` keeps it that way.
  Includes SQL *comments* in applied migrations (no schema change; the runner tracks file
  names) and two printed en dashes in the Ziggy gold transcription (eval unchanged:
  INS F1 1.000, ingredient 0.945, claims 0.883, 0 flips). `predictions/` and `reports/`
  are untracked recorded output, left verbatim.
- **Live check of D-103 done** (9 Gemini calls, see D-103): 5 real packs pass with every
  INS number read; all 3 screenshots refused; the Limca 1 L gold image is brand artwork,
  not a pack photo, and is refused too (replace it in the gold set). A single-photo bug
  it found is fixed.
- Tests: 324 passing, 1 skipped.

### Input validation (2026-09-26, same branch, D-103 locked)

Sushil's test scan (barcode `12222333333333` + two dbt/Snowflake screenshots) was paid
for, answered "retake", counted towards "Send it to us" and got an empty mistake report
(review item #8 on the local DB - reject it). Now: the server checks the barcode
against GS1's tables, the photo file before any paid call, and what each photo shows
(new prompt field `image_content`). 38 new tests; 305 passing. Existing tests' made-up
barcodes had wrong check digits (the app always checked, the server never did): fixed.
**Before launch:** run the new prompt on the 6 gold labels and 2-3 real screenshots
(a few paid Gemini calls) to confirm `food_pack` / `screen` come back as expected.

## Waiting for Sushil (from the overnight session, 2026-09-26)

Nothing was blocked; all five items were built. These need you:

1. ~~Accept D-094 to D-099; merge `front-photo-flow` → `main`~~ ✅ accepted 2026-09-25 (with
   D-100, D-101, all locked); PRs #1 and #3 merged, `main` = `a198535`.
2. ~~Migrate the local DB and add the reviewer account~~ ✅ migrated through 011; reviewer
   `sushil` exists.
3. **Try "Send it to us" on the phone** with the PWA test (§8 item 2): two unreadable photos
   → the button → publish it on `/review` → reopen the app. Only a faked API walked it.
4. ~~`replay` accepted from anyone~~ ✅ D-101: off unless `INSIDELABEL_ALLOW_REPLAY=on`.
   Your local server now refuses `replay` in `/docs` (403) unless you add that variable.
5. ~~Delete `INSIDELABEL_REVIEW_TOKEN` from `~/.bashrc`~~ ✅ removed (D-097).
6. **Send the barcodes of the 5 published products** - Claude adds them to
   `products.barcode`. Until then a barcode scan of those packs misses the catalogue.

## 7. Open decisions (need Sushil)

- **D-053** premium pricing - ₹399-499/year recommended.
- ~~**D-054** the "100% ATTA" ruling~~ ✅ decided 2026-09-25: about the flour, no finding.
- **D-082** what Premium is for - interviews only.
- ~~**D-114**~~ LOCKED 2026-09-27 (see §8 item 1). Was: hosting: one Google Cloud VM in Mumbai (`e2-medium`, 4 GB,
  Ubuntu 24.04, own project, billing upgraded to post-paid before invites; free-trial credit spent
  first), Caddy + one uvicorn + PostgreSQL 18, photos on disk until R2; DNS for both domains
  on Cloudflare (proxy off at first; `.in` stays at GoDaddy with Cloudflare nameservers); later
  steps each wait for their own signal.
- **D-113** (LOCKED 2026-09-27) a Pro chatbot, "ask about this pack", personalised with age band and
  avoid list; explains, never judges (D-004). Supersedes D-001's "not a chatbot". Not built. Open:
  when to build it (D-113 says after W4, per D-083; Sushil wants it to sell subscriptions).
- Concern levels on the 35 verified rows are judgement calls (e.g. sorbitol `low`) - review before launch.
- **Gemini billing**: prepaid credit (can run out, as it did today) vs post-paid / auto top-up.
- **A fallback model** for when `gemini-3.6-flash` is busy - only after `gemini-3.5-flash`
  passes the gold set (comparison couldn't run today: it was busy too). Decide from the
  `timings.vision_retries` data real scans now record.

---

## 8. Next steps - the road to release (in order)

Run `python tools/release_check.py` (add `INSIDELABEL_DB=…` for catalogue gates)
to see where each gate stands. §11 has the full list. Done today: D-051/52/55 decided,
food categories, PWA built, D-092 reproduction, D-093 Cloud Vision, scan speed,
setup alarms.

**NEXT SESSION STARTS HERE (2026-10-10).** The redesign (D-185) is complete: Phase 1 (#141), Phase 2 (#142), the evidence folder (#143) and Phase 3, the website (#144), are merged; D-186 to D-188 merged as #145 to #148, D-189 as #149, D-190 as #150. Where things stand, newest first:

- **`claude/fewer-retakes-faster-read-jetoq3` (2026-10-10, migration 027, web-67), from `main` eccca4e (#150).** D-191 (Sushil: "it asks multiple time to take a new pic"; 45% of photo scans refused in a week): a refused table-only photo says so, keeps the table and asks for "the ingredient list"; the same photos sent again get the same answer with no paid call and no limit used; the app's Back after a refusal opens the result instead of resending; the cross-check asks only when a word Cloud Vision missed would change the result, once per pack per phone a day. The free table hint is built but OFF (`INSIDELABEL_TABLE_HINT`). D-193: tokens per Gemini call stored (`scans.timings`, `review_drafts.usage`, `review_table_reads.usage`); three read switches, all OFF (OPERATIONS.md §5). D-192 (Claude Haiku 5.5 as a second reader) is PLANNED only. Tests: 1274 expected locally (1227 + 47); in a cloud container 1273 passed, 9 skipped, 0 failed.
  - **Waiting on Sushil:** the advisor's review; merge; `update.sh` (migration 027). Then, read-only: `il tools/cross_check_replay.py` (the 15 asks, then and now) and `il tools/table_hint_measure.py` (whether the hint may go on). The advisor's gold-set run decides each D-193 switch.

- **`claude/ayurvedic-medicine-not-food-zcly0h` (2026-10-09, data, rule and /scan, no migration, no web change), from `main` 416c485 (#149).** D-190 (Sushil, review item #85): "Ayurvedic medicine", "Ayurvedic proprietary medicine" or "AYUSH medicine" printed on the pack is a non-food sign without a licence line (losing, like the licence rule, to an FSSAI licence, a food signal or a partial read). A complete read refused as `no_ingredient_list_found` is checked for not-food first and, if not food, gets the not-food result: no "Send it to us", no review item, only the scan row. `tools/pack_kind_replay.py --apply` now keeps a `corrections` list (an old `corrected` string first).
  - **Waiting on Sushil:** merge; `update.sh`; then `il tools/pack_kind_replay.py` (read-only). Expected: no published version changes (a version is only made from a read with an ingredient list, and one printing "Ayurvedic medicine" with no licence line, no FSSAI licence and no table would now say not_food: a reviewer should look at any listed). Close item #85 on /review as not food.

- **`claude/project-thread-68trxb` (2026-10-09, website text only, no migration), from `main` a37290e (#148).** D-189 (Sushil): the privacy page says Your data is "in the profile menu, top right" (was "at the bottom of every screen"), last updated 9 October 2026; the sesame note for mustard stays (no change). D-188 merged as #147 and #148.
  - **Waiting on Sushil:** merge; `update.sh`.

- **`claude/allergen-lines-when-they-matter-0w2vts` (2026-10-08, no migration, web-66), from `main` 1ccabc1 (#146).** D-188 (Sushil, option B): the top of a result has an allergen card only for a match (red, the label quoted: `Milk is listed: "Milk solids".`) or a line we can't confirm (amber, Retake on a photo scan); a child's age line keeps its amber card; a no-match shows nothing anywhere, and "For you" keeps one "may contain" reminder ("in the photo" on a photo scan, "on the pack we checked" on a barcode hit), "nothing extra for her age", and the weaker-check line for a sesame avoider when sesame isn't listed. Your scans, Compare and Share follow it; `/scan`'s `allergens` block is unchanged (D-060). /review pack pictures need a third tick, "It is the front of the pack". `tools/pack_kind_replay.py --apply --by <name>` writes only the kind and its evidence with a `corrected` note (OPERATIONS.md). Tests: 1218 expected locally (1206 + 12); in a cloud container 1217 passed, 9 skipped, 0 failed (with pytesseract installed).
  - **Waiting on Sushil:** merge; `update.sh`. Look at the TATA Sampann pack picture (8904043906393) on /review/pictures and replace it with a front.
- **`claude/fssai-lic-no-not-food-age2la` (2026-10-08, data and rule, no migration), from `main` 93a1c8b (#145).** D-187 (Sushil, review item #82): a plain "Lic No." no longer makes a licence non-FSSAI; only drug, manufacturing, DL or AYUSH/Ayurvedic licence words do. A licence number of 10 to 13 digits starting 1 or 2 is a probable FSSAI licence (food, a reviewer checks the pack), and a nutrition table or an ordinary food category stops `not_food` on the licence rule alone. `tools/pack_kind_replay.py` lists stored versions that change kind. Tests: 1206 expected locally (1200 + 6); in a cloud container 1178 passed, 27 failed, the same 27 as `main`.
  - **Waiting on Sushil:** merge; `update.sh`; then `il tools/pack_kind_replay.py` on the server to see which stored versions change (item #82 should), and re-look at item #82.
- **`claude/review-crop-pack-picture-fzdy0k` (2026-10-08, migration 026, server and /review only), from `main` 7d65267 (#144).** D-186 (Sushil): "Crop to the pack" on a review item's pack picture and on `/review/pictures`. The reviewer drags a box, sees "What will be shown", and the ticks are about that copy. The server checks the box (inside, at least 20 percent of each side, 1:3 to 3:1) and crops after the EXIF turn, before the 480 px resize; `pack_pictures.crop` keeps the box. The shopper's original still goes at 30 days.
  - **Waiting on Sushil:** merge; `update.sh` (runs migration 026). Then the DMart Premia Jeera front can be cropped and ticked.
- **`claude/project-thread-n9uqxj` again (2026-10-08, no migration, web-65, `il-shell-65`), from `main` after #143.** D-185 Phase 3, the website: the hero's film becomes a drawn phone (scan, photograph, the result, sliding like pages; the result alone and still with reduced motion), the film one tap away in its own section; the accepted hero lead and How it works step 2; How we check, About and Privacy as reading pages with their own headings (chips on a phone, a sticky column on a computer); the menu's scrim and cross; header and footer on the home page's edges on a computer; scroll reveals. Lighthouse mobile on the home 100/100/100/100 (main's accessibility 96), LCP 1436 ms against main's 1530, CLS 0. The two font preloads stay (without them CLS 0.004). Every screen 97 to 99 in the review. Evidence in `docs/design/d185/phase3/`.
  - **Waiting on Sushil:** merge; `update.sh`. Privacy's "Your data" wording: fixed by D-189.
- **`claude/project-thread-n9uqxj` again (2026-10-08, no migration, web-64, `il-shell-64`), from `main` after #141: merged as #142.** D-185 Phase 2, with Sushil's "the motion is too quiet" (his words in D-185): home's "Scan here" loop plays slowly for as long as home is on screen (pauses in the background, still with reduced motion) and is bigger (165 by 155 px at 390, same card height); the scanner's corners and gold line; step dots; each photo step's example card with its tick drawing itself; a gold band over a photo being checked; the read's sheet whose lines light up under a moving lens; result cards rising after the people block (D-060 unchanged), bars and the ring filling; Thank you's drawn check. Actions dock in thumb reach on phones (D-171, D-181 placement superseded); D-177's result parts restyled; nutrition rows split into amount and reason by the server (`amount`, `why`, no new words). Fixes: a finding's page ran wider than the phone (on `main` too); the desktop result moved the page when it arrived. Lighthouse mobile 99/100/100/100 (main 100), CLS 0. Every Phase 2 screen 97 to 99 in the review.

- **`claude/project-thread-n9uqxj` (2026-10-08, web-63, `il-shell-63`): merged as #141.** D-185 Phase 1 (design system and app screens). `update.sh` not confirmed yet.

- **`claude/project-thread-naq2w8` (2026-10-08, no migration, web-60, terms 2026-10-08-2), from `main` 2c27878 (#138).** D-184 (LOCKED, Sushil): no more beta. The invite-only beta is removed (join screen, `/join`, the invite gate, `INSIDELABEL_INVITE_ONLY`, `tools/beta.py`; feedback is read with `tools/feedback.py`); the old invite tables stay, unused. No "beta" or "tester" in anything a user sees (`tests/test_no_beta.py`): the photo limit reads "Each phone can photograph {limit} packs in any 24 hours."; the site says "On Android: coming soon on Google Play." and "© 2026 InsideLabel"; the privacy page "Last updated 8 October 2026. A lawyer will review this policy, and we will update it here." "Before you start" loses "can close my invite" (new version: everyone sees it once more).
  - **Also in D-184 (Sushil, 2026-10-08):** everyone gets the full plan free (15 photo scans a day, unlimited barcode lookups, every feature) until billing ships; D-148's 5-a-day free limit waits for that later decision. Future plan names: "Label" (free) and "Label Master" (paid), replacing "Basic" and "Pro", shown nowhere until billing. Sign-up and sign-in (Google, email, phone) are ON HOLD until Sushil restarts them.
  - **After #139 (same branch, web-61):** the "Pro" tags on "Ask about this pack" (app, website home, design page) read "In preparation"; a test keeps plan names, prices and "upgrade" out of the app and site. Waiting on Sushil: merge, `update.sh`.
  - **Same branch, web-62 (D-178 follow-up):** Home's "Checking for" shows "You · 9 to avoid" per person; a tap opens the list. The name no longer wraps one letter per line. Waiting on Sushil: merge, `update.sh`.
  - **Waiting on Sushil:** merge; `update.sh`; the `INSIDELABEL_INVITE_ONLY` line in `/etc/insidelabel/settings.env` now does nothing and can be deleted. The Play listing text and track (Play Console). When the Play app is public, the site's line becomes the Play link.

- **`claude/project-thread-viwmj6` again (2026-10-08, migration 025, web-59, terms 2026-10-08), from `main` cee2162 (#137).** D-183: pack pictures (a reviewer's upload on `/review/pictures`, or a shopper's front ticked on a review item), shown on the result card when the shopper has no photo; a new terms rule and privacy paragraph; example photos on "Before you start" and each camera step.
  - **Waiting on Sushil:** merge; `update.sh` (runs migration 025); everyone sees "Before you start" once more. Upload a few pack pictures on `/review/pictures`.
- **`claude/project-thread-viwmj6` (2026-10-08, no migration, web-58), from `main` 20aabd0 (#136).** D-181: the front photo is a required step 4 while the catalogue wants it, and "Check this pack" waits for the "same pack" box. The camera pages lose their loose "Tips" and "Back" links (Tips is a pill by the title; the header arrow goes back). D-182 (pack picture from the team's reviewed front photos) is written as a recommendation, not built.
  - **Waiting on Sushil:** merge; `update.sh`; accept or change D-182.
- **`d175-count` (2026-10-08, no migration, server only), from `main` d720f93 (#129).** D-175 count follow-up: the re-check counts every comma on both sides and finds the list end by the last entry's final three words. The server's first run passed 20 of 57 packs, 28 failing on the count.
  - **Waiting on Sushil:** merge; `update.sh`; `il tools/recheck_measure.py` again.
  - **Merged (#130); re-measured: 23 of 57.** Count tuning stopped there.
- **`d175-allergen-numbers` (2026-10-08, server only), from `main` 4d0721f (#130).** The re-check's "no new allergen" test ignores bare numbers (sulphite's INS 220 to 228 matched nutrition values on three Horlicks packs). **Waiting on Sushil:** merge; `update.sh`.
  - **For a person on /review, from the six allergen flags:** Rolled Oats (8904335601951) has no allergen line and its label has "soy" on a line of its own: check the photo for a "may contain" line. Gold (8901393024500): the line reads "Contains Milk and SoyMay Contains Barley and Wheat"; make it "Contains Milk and Soy. May Contain Barley and Wheat." PEANUT BUTTER (8901030980046): "of cow's milk" on the label, probably a comparison; glance at the photo. The three Horlicks packs are fine.

- **`d175-recheck` (2026-10-08, migration 024, web-52), from `main` 4ded7eb (#128).** D-175: a published pack is checked again every 15 days.
  - A food pack last checked over 15 days ago shows one optional card: "Help keep this pack up to date: one photo of the ingredient list." The photo is compared with the published list for free first (`review/checker.unchanged`); only a "not clear" photo pays for the normal read.
  - A match sets `product_versions.last_verified_at` and stores the scan as `resolved_via 'recheck'`, nothing else. The result shows both dates when a photo matched after our team's check.
  - Measured on the repo's four real texts: 44 of 44 added entries and 40 of 40 swaps caught; 2 of 4 real packs pass.
  - **Waiting on Sushil:** merge; `update.sh` (runs migration 024); then `il tools/recheck_measure.py` on the server to see how many published packs would pass for free.

- **`d173-wording` merged (#128), 2026-10-08.** D-173 wording follow-up: "the 11 ingredients we could read"; "What we did find still stands." `update.sh` not confirmed yet.

- **2026-10-07 evening (hand-off, docs only).**
  - **D-174 is live:** merged (#126) and `update.sh` run (migration 023).
    - Optional: measure the table read on item #71's photos with `il tools/table_read.py 71`. Export `GEMINI_API_KEY` in that shell first; it costs about Rs 0.75.
    - The blocked #71 scan stored no Cloud Vision text (it predates D-174), so this measurement pays for a new Cloud Vision read too.
  - **D-171 shutter comparison, in progress: the shutter is ON for everyone.**
    - `INSIDELABEL_LIVE_SHUTTER=on` was added to `/etc/insidelabel/settings.env`, and `/access` reports `live_shutter: true`.
    - Before that the line was missing, which means off. Every scan earlier on 2026-10-07 was `camera`: the photos carry the OnePlus camera app's "Shot on OnePlus" watermark, which Cloud Vision reads as label text.
    - First shutter scan, 21:01 UTC: 8906112660519, `live`, 2 parts, a result (verdict), list read (1 ingredient, confidence 1.0), table read (12 rows), 889 Cloud Vision characters, 9.4 s.
    - **Waiting on Sushil:**
      - that pack again with "Upload a photo" and the camera app;
      - the other two packs both ways;
      - which pack was the tiny text, the glossy pouch and the curved bottle, and how the shutter felt to use (focus, glare, lining up the frame);
      - then the side-by-side query (OPERATIONS.md "The label shutter").
    - Then keep it on, or set the line to `off` and restart. The result goes in a new DECISIONS.md entry, since D-171 is append-only and says "Result: pending".
  - **Seen in the same query, not shutter-related:**
    - **Doodh Marie Gold (8901063371101):** refused 3 times as "no ingredient list found", correctly. Cloud Vision's text holds the price block, the manufacturer and the nutrition paragraph, but no list, so the list is on a face that wasn't photographed. Not a bug.
    - **8901928222401:** refused twice as `independent_read_failed` with 12 entries read, then a result with 13 entries. Probably Cloud Vision's check catching an entry the model missed. Not investigated.
    - **8901030949678:** fell back to Tesseract once and took 44.6 s.
    - **Maska Chaska:** `vision_failed` before D-172 was deployed, then correctly `vision_blocked:recitation` at 19:04, then its table photo (item #72) at 19:18.

- **`d174-sent-table` (2026-10-07, web-51, migration 023), from `main` 6d2283b (#125).** D-174 (LOCKED, Sushil: "yes", after items #71 and #72):
  - **What changed:** a pack sent to us has its nutrition table read once from the photos we hold:
    - an earlier answer that copied the table is checked again, for free;
    - otherwise one table-only read (its own prompt; the label prompt is unchanged);
    - Cloud Vision is the second reader (D-133).
  - **On /review:** the numbers show with the tick, and `approve()` publishes them. The pack then gets no D-168 table
    offer.
  - **Supporting changes:**
    - the app sends `back_kinds` ("list,table");
    - a blocked scan keeps Cloud Vision's text;
    - every read is stored in `review_table_reads`, failures included.
  - **Waiting on Sushil:**
    - merge;
    - `update.sh` (it runs migration 023);
    - optionally `il tools/table_read.py 71` to measure the read on item #71's photos (about Rs 0.75).

- **`d173-keep-table` (2026-10-07, web-50, no migration, app only), from `main` f57039f (#124).** D-173 (LOCKED, Sushil: "it should reuse as it reads properly in previous photo"): a retake after a refusal, D-118's clearer photo or a partial read drops the list's photos only; the table photo and the front stay (front still dropped after "two packs", D-108; nothing kept for a screen or not-a-pack photo). After the retake, step 2 only, then "Check this pack" with the kept table as the last part, or "Retake the table too". Also on this branch: "What this check covers" no longer says "score" (D-165 follow-up, Sushil: "find all scores and remove"; a test keeps "score" and "grade" out of every shown text), and every ingredient count on a result is the printed entries (D-111 follow-up: "We checked the 11 ingredients on the list ..." for 50 50 Maska Chaska, was "20"). **Waiting on Sushil:** merge; `update.sh`.

- **`d172-recitation` (2026-10-07, web-49, migration 022), from `main` 529cf47 (#123).** D-172 (LOCKED, Sushil: "accepted"): problem report #7's 502s were Gemini's RECITATION guard blocking the answer (Britannia 8901063367456, reproducible). A blocked answer is now `VisionBlocked`; RECITATION is retried twice; one that survives is a refusal (`vision_blocked:<reason>`), never a 502, with "Send it to us" at once when there is a barcode (one scan is enough; photos held only when sent). Words in `screen.py` (Set A). Every model failure stores its text in `scans.model_error` (migration 022) and logs it with the request id; `repro.py show` prints it. A blocked answer replays from the `{"_blocked": ...}` marker, which every other reader of `model_raw` leaves alone (test lists them). **Waiting on Sushil:** merge; `update.sh` (runs migration 022); rescan the Britannia pack: expect the refusal and "Send it to us", or a result if a retry passes.

- **`d171-label-steps` (2026-10-07, web-48, no migration), from `main` f1bc6e0 (#122).** D-171 (LOCKED, Sushil accepted the mockups 2026-10-07): the label photos come in steps, one job per screen ("Step n of 3"): the ingredient list, then "Is the nutrition table in this photo too?" (Yes reads the pack; No asks for the table as the next part; "The list continues" for D-119's parts; "This pack has no table"). Tips hold D-163/D-167's hints and the drawing; the front photo (D-100) is an optional link on the answer screens, "Add the front of the pack too (optional)", sent with the back in the one `/scan` (Sushil, before merging: a new pack must not lose its front). D-133's and D-168's table photos use the step 3 screen. The app's own shutter (live view, `ImageCapture.takePhoto()`, "Too dark"/"Hold still" on the phone) is behind `INSIDELABEL_LIVE_SHUTTER`, **off**: the camera app until Sushil compares the two. Photos taken with it are recorded as `live`. **Merged and deployed; the shutter is on and the comparison is in progress (see the 2026-10-07 evening entry above).** Originally waiting on: merge; `update.sh`; switch the shutter on, scan 3 packs both ways (about 6 paid reads, Rs 4, accepted), compare (OPERATIONS.md "The label shutter"); then on for everyone or off, recorded in D-171.

- **`d170-photo-problems` (2026-10-07, web-47, no migration), from `main` 5c2602d (#121).** D-170 (LOCKED, Sushil: "Accept, no hint line"): a refused photo is shown back to the user (the photo still on the phone) with its problem named in a short label (`screen.PROBLEM_LABEL`), the existing sentence as the fix line, and Retake; the same for the partial read's card and for the photo check before the read (with a Retake button). "Report a mistake" is off the refusal screen. **Waiting on Sushil:** merge; `update.sh`.

- **`d169-message-kinds` (2026-10-07, web-46, no migration), from `main` 5acd5c2 (#120).** D-169 (LOCKED, Sushil: "Accept as shown"): one symbol and one colour per kind of message on every screen. A photo or app problem (retake cards, form errors, the photo check, error screens, D-168's "nothing was added") is grey-blue `--problem` with a retake arrow, never red; red stays for the avoid list (circled cross) and "Not permitted in India" (new triangle); amber circled ! for worth a look; blue circled i for information; green check for done. Words unchanged; the kind comes from server fields (D-168's table answer gained `kind`). **Waiting on Sushil:** merge; `update.sh`.

- **`d168-table-for-published` (2026-10-07, web-45, no migration), from `main` 503bc32 (#119).** D-168 (LOCKED, Sushil with two changes): a catalogue hit for a food pack with no nutrition table offers, at the end of the result, one photo of the table; `/scan` `table_only` reads it once (about 50 to 60 paise, in the daily photo limit), keeps only the checked table and queues a `nutrition` item with the published content unchanged. A photo showing another barcode, or no usable table, adds nothing. Not offered again on that phone. Replaces the D-147 draft (never recorded; its core is live via D-153). **Waiting on Sushil:** merge; `update.sh`.

- **`d167-first-scan-line` (2026-10-07, web-44, no migration), from `main` 001ea48 (#118, merged as #119).** D-167 (LOCKED, Sushil): a result for a barcode we haven't checked yet says "We haven't checked this pack yet, so this result is read from your photo. Our team checks it next, and then the next scan of this barcode is instant, for everyone." (review item 66; first scan and every scan before review; never without a barcode, from a screen, not food, refused, or checked). The photo screen's "Light" hint is for pouches and shiny packs. D-166 follow-up: Unicode fractions ("½ tsp") count as measures. Merged (#119) and deployed (2026-10-07).

- **2026-10-07, all live.** D-162 to D-166 merged (#113 to #117) and deployed: no invite codes, the barcode hint (web-43), whole bracket groups in D-093's recovery, "No score" on `/how`, and the recipe-list refusal (prompt changed: the next paid gold run reads with it). **Next:** a "first time we've seen this pack" line on the result (review item 66: a tester asked why the review screen came up); D-166's measures should also count Unicode fractions ("½ tsp", "1 ½ cups"), one line in `reliability/gates.py` `_MEASURE` plus a test; then the Chyawanprash fix (waiting on its scan rows) and nutrition capture (D-147). **Waiting on Sushil:** Play Console App access (no restriction) and Data safety (drop User IDs); recruit 15 to 20 testers (12 opted in for 14 days).

- **`claude/gifted-faraday-v5s2db` (2026-10-07, no migration), from `main` f9f38e9 (#116).** D-166 (LOCKED): a read list that is a recipe's printed on the pack (at least 3 entries and half of them with a measure or cooking word, `data/recipe_markers.json`) is refused as `no_ingredient_list_found`, with new retake words saying a recipe was read (`screen.RETAKE_RECIPE`). Saffola Soya Chunks' recipe box: 21 of 26 entries; every list we hold: none. **`PROMPT_VERSION` changed** (4efbe2214842 to 01696584efa3; rule 4 names a recipe): the next gold run reads with it, only when Sushil says "run the gold set". `/how` quotes "No concerns found in the ingredients" in full. Merged (#117); live 2026-10-07.

- **`claude/gifted-faraday-v5s2db` (2026-10-07, no migration, no app change), from `main` ab6649e (#115).** D-165 (LOCKED, Sushil): `/how` gains a "No score" section after the intro (no score, grade or stars; the label, person by person, with sources), and its two "doesn't change the score" lines now say what the code does (information only; a tile can turn "No concerns found" into "A few things worth knowing"; the table's only other effect is the HFSS line for a child under 2). Merged (#116); live 2026-10-07.

- **`d164-nested-bracket-recovery` (2026-10-07, no migration, no app change), from `main` 364a2b9 (#114).** D-164 (LOCKED): D-093's recovery takes an omitted additive's whole bracket group, so "Raising agents (500(ii), 503(ii))" comes back whole and 500 and 503 are in the result, with no clearer-photo request (closes D-160's open item). D-163 (#114) is merged and live (web-43). Checked 2026-10-07: the Saffola Soya Chunks scan read "Defatted Soya" right, so its recipe panel reached no result; the recipe-list rule check is next, as a defence. Merged (#115); live 2026-10-07.

- **`d163-barcode-in-photo` (2026-10-06, no migration, web-43), from `main` e7762d9 (#113).** D-163 (LOCKED): the photo screen asks to keep the barcode in the photo when it's on the same side, so D-143 confirms it and the reviewer doesn't check it by hand (Saffola Soya Chunks review item). D-162 (#113) is merged and live; invite-only is off on the server. Merged (#114); live 2026-10-06 (web-43). **Next:** the D-093 nested-bracket fix; the photo check spotting a back photo with no ingredient list (Saffola's recipe panel); a "first time we've seen this pack" line on the result (review item 66).

- **`d162-no-invite-codes` (2026-10-06, no migration, web-42), from `main` 503d0d3 (#112).** D-162 (LOCKED, Sushil): no invite code in the app or on the website; the Play closed test decides who installs, and the daily photo limit (D-148) and per-IP limits (D-095) cap the cost. The gate stays in the code, switched off by `INSIDELABEL_INVITE_ONLY=off`. Home, privacy and "Delete my data" wording updated; OPERATIONS.md, PLAY_RELEASE.md, the data map and the release gate match. Also carries the 2026-10-05 "phone checks done" line that #110 left out. Merged (#113); live 2026-10-06 (web-42); invite-only off on the server; fresh install tested. **Waiting on Sushil:** in Play Console, App access (no restriction) and Data safety (drop User IDs).

- **`claude/gifted-faraday-v5s2db` (2026-10-05, no migration, no app change), from `main` b5f91de (#111).** D-161 corrected (Sushil): the Play feature graphic part is dropped. The live graphic already carries the italic wordmark (logo, italic "InsideLabel" and "Read the label for your family." on cream) and needs no change; `android/feature_graphic.png`, `make_wordmark.py --feature-graphic` and its test are removed, and `docs/PLAY_RELEASE.md` says what is live. The reviewer wordmark stays. **Waiting on Sushil:** merge.

- **`claude/gifted-faraday-v5s2db` (2026-10-05, no migration, no app change), from `main` 5bd877d (#110).** D-161 (LOCKED, Sushil: "Add the wordmark"): the reviewer screen's header shows the D-152 wordmark, then "review", written into `review/templates/base.html` by `tools/make_wordmark.py` (inside `{% raw %}`). Header 43 px (was 42.75); readable in light and dark. Merged (#111).

- **2026-10-05, deployed.** #106 to #109 (D-157 to D-160) merged and `update.sh` run: report #5's pack goes straight to its result, and a dropped additive number or allergen still asks for one clearer photo. **Next:** D-093's recovery (`ocr_check.recover_from()`) cuts an entry at a nested bracket ("Raising agents (500(ii), 503(ii))"); fixing it puts 500 and 503 in the result instead of asking (open in D-160). **Waiting on Sushil:** retest report #5 on the phone.

- **2026-10-05, Sushil: the phone and laptop checks and the scan-speed query asked for in the entries below are done,** and every branch below is merged and live. The older "Waiting on Sushil" lines are history. Still open from them: post the film's 9:16 MP4 (`film-on-home`); whether the app icon, the Play listing, the film and the reviewer screen take the italic wordmark (D-152); what "Compare only between supplements" should say, and 3 supplement photos for gold (`supplements`). D-137's re-score passed (F1 0.980); D-141 and D-150 were superseded; the first-visit footer jump was fixed (web-40).

- **`claude/gifted-faraday-v5s2db` (2026-10-05, no migration, no app change), from `main` 8d06896 (#108).** D-160 (LOCKED), the advisor's review of D-159: `lost_words_matter()` now reads lost INS numbers (`review_checker.lost_ins_numbers()`, via `core/tokenize`), adds each lost word as its own entry as well as joined ("coconut milk" no longer hides milk), and asks on its own failure (`"error": true` in the record). Found while testing: D-093's recovery cuts nested brackets ("Raising agents (500(ii)", "(503)"), so 500 and 503 were missing from the result; the gate now asks there. Open: fix the recovery itself. Merged (#109); live 2026-10-05.

- **`claude/gifted-faraday-v5s2db` (2026-10-04, no migration, no app change), from `main` 064e92c (#107).** D-159 (LOCKED): /scan's D-118 gate asks for a clearer photo on LOST words only when `lost_words_matter()` (beside the gate in `api/main.py`) finds they change the result, by running the scan's own rules with and without them. Report #5's scan 8bd1c116 (lost "choce", "water") now goes straight to the result; the words are kept in `scans.ocr` `back.independent_read` and shown by `tools/repro.py show`. The D-117 checker is unchanged and still sends the pack to a person. Merged (#108); live 2026-10-05, with D-160's fixes.

- **`claude/gifted-faraday-v5s2db` (2026-10-04, no migration, no app change), from `main` 14c2fc6 (#106).** The advisor's review of D-157: its cut-word rule let a dropped ingredient beside a longer one through D-118 ("Nutmeg, Nut", "Eggless mix, Egg", "Cornflour, Corn" all lost nothing). D-158 (LOCKED): a word is cut only at a line's start or end, and never one of `allergens.json`'s alias or statement words or a one-word `normalization.json` synonym. Report #5 keeps its D-157 result. Open: a plain word at a line end ("Corn" after "Cornflour") still reads as cut. Merged (#107); live 2026-10-05.

- **`claude/gifted-faraday-v5s2db` (2026-10-04, no migration, no app change), from `main` c60cb63 (#105).** Problem report #5: a Nestle Choco Coated Wafer (8901058009439) was refused twice by D-118 though Gemini read it right. D-157 (LOCKED): `review/checker.py` `independent_read` no longer counts date or batch stamps ("AUG/26-APR", "AUGT") or words cut where a back's parts overlap ("frac", "leci", "ing", "dient") as lost. Scan 8c46004c is now confirmed; 8bd1c116 still asks, on "choce" and "water" (open question in D-157, answered by D-159). Merged (#106); live 2026-10-05.

- **`claude/gifted-faraday-v5s2db` (2026-10-04, tests only), from `main` 9691ea6 (#101).** Review of #101's screen-text test: (1) all-caps codes are checked only on the Southampton card; a general rule would trip on label words, so left as is. (2) Claim rows are now checked with `CLAIMS_TO_USERS` on, ready for when D-051 releases them. (3) The fields the test skips (id, ref, key, url, kind, status, state, code, type, tone, tier, concern) are now held by `tests/test_web.py`: `web/app.js` may not pass one to `el()` as words. `ins` left the skip list, since additive cards show "INS " + ins. Also a race in `tests/test_scan_speed.py` (failed once in a full run): a scan's result never waits for its read, so the deadline test's slow fake Tesseract passes outlived it and were counted by the next test's fake; the `fresh` fixture now waits for each test's reads (reproduced with a 3 s delay, then fixed). **Waiting on Sushil:** merge.

- **`claude/gifted-faraday-v5s2db` (2026-10-04, no migration, no app change), from `main` 1618c6a (#100).** Sushil's phone bug: the "Sugar under N names" card showed "normalization.json added_sugar aliases matched: ...". Its source line is now `screen.SUGAR_SOURCE` (FSSAI's definition of added sugars, Labelling and Display Regulations 2020; the card already quotes the label's names). Every other card checked: the additive cards' "Sources:" showed table codes ("SOUTHAMPTON, CODEX"), now plain words from `additives.json` `_meta.sources_shown`; the industrial card said "NOVA marker:" twice per name; the household facts' `technical` (sent, not drawn) named files and keys ("normalization.json", "flavour_enhancer, concern: moderate"). `tests/test_screen.py` fails if any screen text outside the machine fields (id, ref, key, url, kind, status, state, code, type, tone, tier, concern, ins) has ".json" or a snake_case key. `tests/fixtures/pack_kind_gold_before.json`: only its `technical` lines changed. **Waiting on Sushil:** merge; `update.sh`.

- **The home page's film redone for the redesign (2026-10-03, no app change), on `claude/trusting-einstein-kddhlb`.**
  Both cuts re-rendered from `videos/insidelabel-how-it-reads/src/` with the redesign's screens, the ingredients and
  nutrition table photo, and "Read the label for your family." at the close; served as `web/film/hero2-*` (old
  `hero-*` deleted). D-153 note; film BRIEF.md and README updated. **Waiting on Sushil:** watch it; merge; `update.sh`.

- **The photo ask wants the nutrition table too (2026-10-03, web-41), on `claude/trusting-einstein-kddhlb`.** Sushil:
  "everywhere ingredients and Nutrition label we need for food items". "Photograph the ingredients and the nutrition
  table", 1 or 2 photos; drawing, hints, the parts question, the food re-check button, the photo check's tick and the
  website's step 2 follow (D-153 note). New test: every app script parses as a module (a stray ")" got past
  `node --check` on .js). **Waiting on Sushil:** merge; `update.sh`.

- **First-visit footer jump fixed; D-156 (2026-10-03, web-40, no migration), on `claude/trusting-einstein-kddhlb`.**
  A screen still loading its words (`aria-busy`, "Before you start") no longer reveals the footer; `settled()` does
  once the terms are in: 0 of 8 fresh visits shifted (was 3 to 5 of 6), Lighthouse CLS 0 in 5 of 5. D-156: InsideLabel
  will read skin care and personal care labels too (not built); `/about`'s "ties" line now covers them and its
  "Changes to this policy" list dates it. "None" for skin care and personal care confirmed by Sushil.
  **Waiting on Sushil:** merge; `update.sh`.

- **Two wording changes from Sushil (2026-10-03, no code), on `claude/trusting-einstein-kddhlb`.** The website hero
  says "Read the label for your family." (was "for your kids": not true of a household's adults). D-155 (LOCKED):
  `/about` no longer says "No ads." because ads may come after the beta; the page dates the change, as its own policy
  requires. Before any ad ships, a decision on who may advertise and where (the same page still says no brand can pay
  us). **Waiting on Sushil:** merge; `update.sh`.

- **D-153 step 3, the website home (2026-10-03, no migration, no app change), on `claude/trusting-einstein-kddhlb`.**
  `/` rebuilt in the accepted order (hero, how it works, one sourced example with the brand hidden, how we check, in
  preparation, Sushil's note, closing band). The D-151 film rule and D-152's desktop size stay; the film sits in a
  device frame, the example cards rise over it on desktops. Walked at 390/360 px and 1280/1440 px, light and dark: no
  page errors, no sideways scroll. Lighthouse (gzip, real throttling): LCP 1619 to 1614 ms, CLS 0.039 to 0.011.
  `tests/test_site_home.py` (6). The redesign's three steps are done. **Waiting on Sushil:** merge; `update.sh`; a
  look on a phone and a laptop. **Still open:** the first-visit footer jump in the app (step 2 entry below).

- **D-153 step 2, the app's photo ask and result (2026-10-02, web-39, no migration), on
  `claude/trusting-einstein-kddhlb`.** The photo ask names the panel, the count and why, with a drawing; the result
  opens on a deep panel with the pack's name and the person lines, folds the rest under "Worth knowing (n)" with
  sources (a not-permitted additive stays open, D-111), and ends on "Holding another pack? Scan it to compare".
  Details in D-153. Walked at 390/360 px light and dark on three gold packs; `tests/test_web.py` (+3). Found, not
  fixed (it predates this): on a first visit the footer can show under "Loading…" and jump when "Before you start"
  appears (Lighthouse CLS 0.16 in about half of fresh loads, with and without this change). **Waiting on Sushil:**
  merge; `update.sh`; try a scan on the phone. **Next:** step 3, the website home.

- **D-153 step 1, the design system (2026-10-02, web-38, no migration), on `claude/trusting-einstein-kddhlb`.**
  One block of tokens and components, identical in `web/app.css` and `web/site/site.css` (deep-blue panel, person
  lines, serif headings, mono sources, numbered notes, ruled lists, the Finding / For / Source table, "in
  preparation" boxes, the 60 px button); Source Serif 4 (400, 600) and IBM Plex Mono (400) self-hosted with their
  OFL files, 56 KB. `tests/test_design_system.py` (7): the two copies identical, every token defined, repeated values
  unchanged, WCAG AA computed in light and dark (it caught the table header at 4.27:1 and the hero stroke in dark
  mode, both fixed). Reference sheet `/app/design.html` (noindex), walked at 390 light and dark and 1280. No screen
  uses it yet. **Next:** step 2, the app's photo ask and result.

- **`claude/trusting-einstein-kddhlb` (2026-10-02, decision only, no code).** D-153 **LOCKED** (Sushil: "accepted"):
  the redesign. One design system for the website and the app; the website home as row D ("Merged") of the canvas
  https://claude.ai/artifact/2rmu9zKpTyATZwibpcK1fF; the app's photo ask ("Photograph the ingredients list", 1
  photo, which panel and why) and result (per-person lines first, the rest under "Worth knowing" with sources,
  ending in "Scan the next pack to compare") fixed where a tester got stuck. Sushil's founder note is in D-153 word
  for word. **D-138 approved** the same day (photo and connect@insidelabel.ai): `/about` now has the policy, the
  note and the photo (`web/people/`), and no DRAFT banner. **Waiting on Sushil:** merge; `update.sh`. **Next:** build the design system, then the photo ask and result,
  then the website home.

- **`d151-accepted` (2026-10-02, no code or migration), from `main` 77d0327 (#92).** Sushil: "accepted" for D-151
  (the film as the website home's hero), now **LOCKED**; and the caption under the film loses "No sound: the words
  are on screen.", leaving "How InsideLabel checks a label, in 41 seconds." (the caption keeps its two-line height,
  so nothing below it moves). **Waiting on Sushil:** merge; `update.sh`.

- **`site-desktop` (2026-10-02, web-36, no migration), from `main` 0dc965b (#90).** Sushil's header, menu, "Scan
  here" and desktop asks; D-152 (RECOMMENDED). One wordmark, the logo and "InsideLabel" in DM Sans ExtraBold Italic
  (Bricolage has no italic), drawn as one inline SVG of 4.4 KB by `tools/make_wordmark.py` and written into the
  app and every website page, centred. App header: wordmark centred, "Back to the result" as the left button on a
  result's own page only, a 48 px person icon on the right ("Menu") opening a modal dialog (a bottom sheet on
  phones, a panel from 600 px) with Household, Compare, Your data, Send feedback, Report a problem, Privacy (the
  footer keeps its links). Home: "Scan here" first, the "what's new" notes below it. Website desktop (1024 px up,
  step at 1440): one 1200/1280 px container, hero 4.5/12 + 7.5/12 (film 570/670/705 px at 1024/1280/1440, was
  555/611/611), three equal cards, two-column points; the rules in the home page's own `<style media>` so phones
  never load them; below the header every website page at 390 and 360 px is pixel-identical to before (16 of 16,
  light and dark). Lighthouse (median of 5, cold): website mobile LCP 1364 to 1368 ms, CLS 0, 84 to 90 KB;
  desktop 332 to 330 ms; app home mobile 2570 to 2448 ms, CLS 0.033 to 0, 201 to 197 KB; desktop 588 to 576 ms.
  Tried and dropped, each measured slower on the website's mobile LCP: the italic as a web font with its own
  stylesheet, the wordmark as a separate SVG file, the desktop rules in their own stylesheet. Walked at 390 x 844,
  360 x 800 and 1280 x 800, light and dark: home, the menu (Escape, outside tap, Back, a choice), a result, a
  result's own page, Household, Compare. `tests/test_site_desktop.py` (8). Merged (#91); D-152 **LOCKED**, accepted
  by Sushil 2026-10-02 ("accepted" for D-152). **Waiting on Sushil:** `update.sh`; a look on a phone and a laptop;
  later, whether the app icon, the Play listing, the film and the reviewer screen take the italic wordmark too.

- **`film-website-only` (2026-10-01, web-35, no migration), from `main` b96b322 (#89).** Sushil: "not liked it,
  keep only web page website on desktop and mobile version video". D-151 (RECOMMENDED) supersedes D-150: the app has
  no film (home is "Scan a pack" first, nothing added; `app.js`, `app.css`, `icons.js` are back to before D-150).
  The website home's hero is the film: text and "Open the app" beside it on landscape screens, above it on phones;
  phones and portrait screens get the 9:16 cut, landscape the 16:9 cut, one rule in the `<picture>` still, the CSS
  and the script, so one file downloads, its src set after the load event; muted, looped, plays while half in view,
  pauses out of view and resumes unless the visitor paused it; never by itself with reduced motion, Save-Data or no
  IntersectionObserver (the still and a play button wait); a labelled 48 px play/pause button (WCAG 2.2.2). Silent
  hero copies: `web/film/hero-16x9.mp4` 1280 x 720 1,292,680 bytes, `hero-9x16.mp4` 720 x 1280 1,440,735 bytes, WebP
  stills 24 KB and 19 KB; D-150's files with sound deleted. The hero's three fonts are preloaded and the hero is
  top-aligned so the font swap moves nothing. Website home on a phone (390 x 844, Fast 4G 9 Mbps / 60 ms, 4x CPU,
  median of 5): LCP 404 ms to 316 ms, CLS 0 to 0, 78 KB to 76 KB by the load event; the film now loads only when
  scrolled into view (1.44 MB) where before the 2.87 MB film started at once. Desktop (1440 x 900): LCP 400 to
  336 ms, CLS 0.015 to 0. Headless Chromium here has no H.264: the requests, states, keyboard and shifts were seen,
  not the picture moving. `tests/test_film.py` (7). Merged (#90); D-151 accepted 2026-10-02 (`d151-accepted`,
  above). **Waiting on Sushil:** the scan-speed query (OPERATIONS.md section 5) for "about 8 to 15 seconds";
  `update.sh`; a look on a phone and a laptop.

- **`film-on-home` (2026-10-01, web-34, no migration), from `main` 507c38e (#88).** Sushil: "website home page and
  android apps home page". D-150 (RECOMMENDED): the explainer film is served from `web/film/` (H.264 + AAC, 16:9
  2.9 MB, 9:16 3.1 MB, WebP posters 24 KB and 20 KB). Website home: the 16:9 film under the opening lines, muted,
  plays once scrolled into view after load, pauses when it leaves; never by itself with reduced motion or
  Save-Data. App home: a "How it works" card with the poster under "Scan a pack" (which stays first); a tap opens
  the 9:16 film full screen with sound and a close button; Back and Escape close it. `preload="none"`; the service
  worker skips every `.mp4` and precaches nothing new; the server registers `video/mp4` and `image/webp` and
  serves byte ranges (206). Found and fixed on the walk: `app.js` has its own `history()` (the scan list), so the
  player uses `window.history`. LCP, median of 7 cold loads at 390 x 844, Slow 4G and 4x CPU: website home 468 ms
  to 608 ms (the poster is now the largest element; preloading it made it 664 ms, so no preload), app home
  1688 ms to 1740 ms. Headless Chromium here has no H.264, so playback itself was not seen: the requests, the
  player, Back, close, focus and the cache were. `tests/test_film.py` (5). **Waiting on Sushil:** before
  deploying, the scan-speed query (OPERATIONS.md section 5) for the film's and the app's "about 8 to 15 seconds"
  (recorded so far: real scans 5.7 s and 6.9 s, Gemini alone 7 to 28 s); merge; `update.sh`; play both on a phone;
  "accepted" for D-150. Merged (#89), then superseded the same day by D-151 (`film-website-only`, above).

- **`explainer-video` (2026-10-01, no code or migration), from `main` 550173e (#87).** Sushil tested the HyperFrames
  video skills ("help me to test this", then "re design ... more we are describing to user", "it will mostly be
  watched on phones", "add a free track"). `videos/insidelabel-how-it-reads/`: a 41 s product film written as code
  and rendered locally (no account, no paid call), two cuts from one project: 9:16 (main) and 16:9. The app plays
  on a phone (screens copied from the real app's screens and words), 2 to 4 words per beat, an original
  soundtrack made by `src/music.py` (free, no licence), -16 LUFS. Every word on screen has a source row in its
  `BRIEF.md`; the look and motion rules are in `MOTION.md` (from `docs/APP_DESIGN.md` section 8); `AUDIT.md`
  checks it against Apple's HIG motion rules; `README.md` says how to build (`./make.sh vertical render`). The MP4s
  are not committed (`renders/` is ignored): publish them. The folder is meant to move to its own repo later.
  Merged (#88). **Waiting on Sushil:** post the 9:16 MP4.

- **`scan-speed` (2026-10-01, no migration), from `main` 21aa069 (#86).** Sushil: "scan-speed first". With Cloud
  Vision refusing (code 8), photo scans took 50 to 80 s and nobody was told (section 6, 2026-10-01). Now: one
  independent read of the back photo per scan, started alongside Gemini (Vision, or Tesseract's six passes two at a
  time with one thread each); the cross-check, the identity check, the nutrition table and the barcode digits all
  use it; the result never waits for it (passes finished in order count; fewer than two: skipped, traced "ocr:
  skipped (deadline)", and the existing gate then shows nothing as checked); a code 8 or HTTP 429 trips the breaker
  for 10 minutes (was 60 s) and files a `server` problem report once per trip; Vision is called at most once per
  scan (a long scan made 5 calls before). Measured in the cloud checkout with Vision answering code 8 and Gemini
  mocked at 8 s: 1 photo 17.0 s to 8.2 s, 3 parts 16.1 s to 8.6 s. `repro.py` replays the same number of passes.
  The scan-speed query is in OPERATIONS.md section 5. `tests/test_scan_speed.py` (13). Merged (#87). **Waiting on
  Sushil:** `update.sh`, then the scan-speed query after a day; whether a skipped cross-check should keep saying "We couldn't
  read the label clearly enough... Please retake" (the gate's existing words; true for a bad photo, not for a
  skip), a short grace, or new words.

- **`app-polish` (2026-10-01, web-33, no migration), from `main` 0893586 (#83, `beta-limit` merged).** Sushil: make
  the app look and feel as good as the best-rated apps. `docs/APP_DESIGN.md`: every screen and state reviewed in
  headless Chromium (390 x 844, light and dark, real server code with recorded readings, no paid scan), 14 findings
  ranked, the design system (tokens for colour, type, spacing, shape, elevation, Material 3 motion, icons), every
  number cited to a page read 2026-10-01; contact sheets before and after in `docs/app-design/`. Built: tokens on
  `:root`; 48 px targets everywhere; text-field borders 3:1 (WCAG 1.4.11); one press state; screens enter with a
  200 ms rise, a result's people block never moves (D-060) and the rest follows 40 ms apart; the app's own SVG
  icons (`web/icons.js`) in place of font glyphs; an honest scan wait ("Sending the photo…" until the upload
  finishes, then "Reading the ingredient list…", both existing sentences); corner guides and a 15 ms tap on the
  live scanner; the photo step leads with its next action; skeletons; 200% text and zoom no longer scroll
  sideways (also broken on main). No word in JS changed; D-146's digit check untouched; reduced motion turns all
  motion off. At 4x CPU: CLS 0.106 and 0.111 to 0.002 (the footer jumped), LCP and INP unchanged (INP 40 ms);
  +6.9 KB gzipped. Walked at 390 x 844 and 360 x 800, light and dark, reduced motion on and off: no step failed.
  **Waiting on Sushil:** merge, `update.sh` (no new Play upload: the app loads the site), a look on the phone.
  The D-137 re-score from `beta-limit` is still recorded as pending above; this branch doesn't touch it.

- **`beta-limit` (2026-10-01, web-32, no migration), from `main` 5b19b2d (#82, `play-wrap` merged).**
  (1) **D-137 LOCKED** (Sushil: "D-137 accepted now with above suggestions"): Britannia's last two gold entries
  joined, Patanjali's flavours entry split, as printed; `ingredient_count` follows each list. **The ingredient
  gate's re-score is pending:** `predictions/` is on the laptop, not in the cloud checkout; expected 98.0%
  (Britannia 0.882, the other five 1.0), gate PASS. Point 2 waits for the D-147 gold run. (2) **D-148 LOCKED and
  built:** 15 photo scans per install in a rolling 24 hours (`ratelimit.PHOTO_SCANS_A_DAY`); barcode lookups and
  the IP rules unchanged; the limit screen from `lenses/screen.py` ("Photo scans used for now", "During the beta,
  each phone can photograph 15 packs in any 24 hours.", "Scanning a barcode still works for packs we already
  know.", "You can photograph another pack in about N hours.", "Scan a barcode"); `tests/test_photo_limit.py`;
  walked in headless Chromium at 390 x 844, light and dark (limit lowered to 1 and a recorded reading on a scratch
  server, no paid call). D-053 and D-102's "web first" marked superseded. (3) **D-138:** Sushil's answers in
  `docs/COI_POLICY_DRAFT.md`; still RECOMMENDED; needs "D-138 approved", the photo and the contact address before
  `about.html`. (4) **Privacy page:** "Beta version, last updated 1 October 2026. A lawyer will review it before
  the public launch."; `docs/PLAY_RELEASE.md` section 8 answers 1, 3, 4, 5 recorded. **Waiting on Sushil:** the
  re-score on the laptop, merge, `update.sh`. **Next:** the Chyawanprash not_food fix when its data arrives, then
  `nutrition-capture` (D-147).

- **D-148 `play-wrap` (2026-10-01, no migration): the Play app.** Branch from `main` d09f13a (#81).
  `android/`: the Bubblewrap TWA of https://insidelabel.ai/app/, generated with `@bubblewrap/core` 1.25.0 from
  the web manifest; package `ai.insidelabel.app.f` (**D-149 LOCKED**, Sushil "confirmed ai.insidelabel.app.f"),
  versionCode 1, targetSdk 36 (Play's rule since 31 August 2026, read 2026-10-01), icons from `icon-512.png`
  and `icon-maskable-512.png`, portrait, custom tabs fallback, no notifications, no permissions. Signing keys
  and build output are git-ignored; `tests/test_android_project.py` (12) fails on a tracked key and pins the
  fixed values. `GET /.well-known/assetlinks.json` from `data/assetlinks.json` (`tests/test_assetlinks.py`,
  16): ships with no fingerprints (404) until Sushil adds the upload key, then Google's app signing key after
  the first upload. `/privacy.html` now served (it was a 404; it is the URL given to Play). `docs/PLAY_RELEASE.md`:
  laptop build commands, the key and its two backups, asset links steps, Play Console steps (internal
  testing first), App content and Data safety answers traced to `docs/DPDP_DATA_MAP.md`, the en-GB listing
  (linted by `tests/test_wording.py`), the phone checklist, 6 questions. **Not proved: the build** (this
  cloud session's network refuses `dl.google.com`). D-140 part 5 now records "Sushil, 2026-10-01: show
  baby lines". **Waiting on Sushil:** merge; upload key and first build on the laptop; the upload key's
  fingerprint into `data/assetlinks.json`; internal testing upload; Google's fingerprint; the questions in
  `docs/PLAY_RELEASE.md` section 8. D-147 and D-148 are not yet written in DECISIONS.md. **Next:**
  `beta-limit`.

- **Phase 3 of D-140, part 5 (the last), on `baby-food-under-2` (2026-10-01, web-31, no migration):** the
  `baby` band "Under 2 years" (`toddler` now "2 to 3 years"), the sourced lines for a baby on ordinary foods
  (`data/baby_lines.json`, every quote read first-hand on 2026-10-01: ICMR-NIN DGI 2024 pp. 21, 26, 28, 29; WHO
  2023 complementary feeding 5c p. xii, with WHO's NSS guideline p. xi for which sweeteners count; Nutra 2(1)
  for a supplement), and the one-time question for a phone's older toddler profiles ("Is {name} under 2?",
  server's words, answer kept on the phone as `under2_asked`, never sent). Not sent after D-146's digit check in
  the same scan, on a retake, or on an infant or special medical result; infant packs stay in shadow, no
  breastfeeding line. `tests/test_baby_band.py` (16; suite 929 passed, 8 skipped, 1 xfailed). Walked in headless Chromium, light and dark, 390 x 844,
  from real `/scan` answers: question, "Yes" (profile becomes `baby`, server still sees ref/age/avoid only), not
  asked again, the baby lines with their sources, the editor's bands; no console errors. **Waiting on Sushil:**
  merge, `update.sh`, phone check; "accepted" for the three build choices recorded under D-140 part 5 (WHO's NSS
  definition leaves sugar alcohols out; the supplement line quotes 2(1); one profile asked per result, catalogue
  hits included). The brief's `docs/LEGAL_QUESTIONS.md` doesn't exist; the lawyer's questions are
  `docs/BABY_FOOD.md` section 9, and (c), whether the baby lines make every result 7(1) material, is still open.
  **Next:** the Chyawanprash not_food fix, once Sushil sends the scan row or id (own branch from `main` after this
  merges).

- **Barcodes: D-142, D-143, D-144 on `main` and deployed (Sushil, 2026-09-30, PRs #68 and #72; #70 and #71
  merged the stack's branches into each other first).** D-144 measured on the server before the merge: 107
  photos, the old rule accepted 6, the new rule 6 (1 by the Cloud Vision text only, f77b...), **refused 0 of 6
  (0.0%)**, and the wrong 0921129008343 on 03f8... is dropped; **D-144 accepted by Sushil.** **D-142 and D-143
  accepted by Sushil** the same day; all three LOCKED. The audit on the server: 47 published, 1 MISMATCH (#42),
  6 confirmed, 40 unconfirmed (no barcode in their photos).
  - **Done: #42 Corn Flakes corrected** on the server (Sushil, 2026-09-30 16:41): 4901196008343, the camera
    misread, to 8901499008343, the digits the pack prints; `il tools/barcodes.py history 8901499008343` shows
    record #1, by sushil.
  - **Open: #48 Sugar Free Natura**, 4992146143214 from the camera scanner on 27 September and again on 30
    September; SUSPECT in the audit; its photos show no barcode. Waits for Sushil to read the digits printed on
    the pack, then `il tools/barcodes.py fix 48 <digits> --by sushil --why "..."` if they differ.
  **D-145** (the scanner's camera frame as the barcode's evidence photo, RECOMMENDED, proposal only) **is held
  until after week 4** (Sushil; D-083, D-105): the full entry, with its proposed DPDP data map point 9a, is
  in DECISIONS.md; nothing is built. `barcode-rescale-75` and the old stack branches
  (`barcode-correction`, `barcode-audit`, `camera-barcode-check`) are not to be merged; they can be deleted.

- **D-146 LOCKED (Sushil, 2026-09-30), merged as #79:** a scanned code for a pack not in the catalogue is shown
  back (first 3 and last 4 digits large) with "Yes, they match" / "Scan again" before the ingredients photo; a
  catalogue hit shows the name with "Not this pack? Scan again"; the answer (confirmed, rescanned) is kept on the
  scan and shown on /review beside D-143's check. web-30. It stays exactly as merged (Sushil); no second prompt
  on top of it. **Waiting on Sushil:** the phone check with the live camera.

- **Phase 3 of D-140 (baby food, in shadow): part 1 merged** (#74, 2026-09-30): an infant food's own checks
  stored for reviewers (see D-140's notes). **Part 2 on `baby-food-additives`:** 5(2), each type's additive
  list (197 rows and 5 carriers from the page images; a follow-up misprint, INS 525 for sodium hydroxide, kept
  as printed), merged (#76). **Part 3 on `baby-food-no-milk`:** 4(3), the no-milk statement where milk isn't
  listed, merged (#78). **Part 4 on `baby-food-composition`:** composition, reviewers only (the type's ranges,
  with FSSAI's 18 October 2022 revisions). Then the `baby` band and the toddler
  question. Branches from now on: one at a time from the current `main`,
  merged by Sushil before the next starts (Sushil, 2026-09-30). Next parts: 5(2)'s additive tables
  per type, 4(3), composition (reviewer-only), the `baby` band and the one-time toddler question.

- **Same branch (`supplements`), after Sushil's review:** Compare stays food-only for the beta, recorded in
  D-139 (Sushil: Compare's ranking rules are for food, no source ranks supplements, a "better choice" between
  them is close to medical advice; revisit after week 4). **Phone check finding (Sushil, phase 1):** a small
  blurry barcode photo made zxing-cpp read 0961676012608 for 8901058018608 and `barcode.check()` accepted it
  (6 digits wrong, check digit right). **D-141 RECOMMENDED:** a photo barcode counts only when two reads agree
  (as sent and one half-size rescale) or the barcode is big enough (threshold from the gold photos); the case
  is `tests/test_barcode_two_reads.py`, two strict xfails until built. **Waiting on Sushil:** "accepted" for
  D-141.

- **Phase 2 of D-139 built: supplements** (branch `supplements`, web-29, 831 tests, PROMPT_VERSION `4efbe2214842`, no
  migration). Phase 1 (`pack-kind`, PRs #62 and #63) merged, deployed, phone check done by Sushil 2026-09-30.
  Prompt rule 12 reads the composition table; `lenses/nutra.py` over `data/nutra_botanicals.json`,
  `nutra_additives.json`, `nutra_rules.json` (every row from its page image). A supplement result: plant-note
  tiles by part, a day's amounts beside ICMR-NIN's RDA for men and women (never called a limit) with a tile
  above the upper limit, 5(12) statements found or not found, additives against the format's list (GMP table
  for all), the 5(10) children line, the protein-powder note, the sugar chip for gummies and powders; no score
  sent. Walked, light and dark, no errors. **Waiting on Sushil:** merge, `update.sh`, phone check; what
  "Compare only between supplements" should say (kept out for now); 3 supplement photos for gold (paid reads
  asked first). **Then phase 3** (`baby-food`, in shadow).

- **Phase 1 of D-139/D-140 built** (branch `pack-kind`, web-28, migration 019, 802 tests; PROMPT_VERSION
  `b26cc0ca9c24`). Kind of pack from printed words and licences (`core/pack_kind.py`,
  `data/pack_kinds.json`); a short result for supplement, infant (allergens, the kind in its words, one sentence),
  special_medical and not_food; food output identical to the baseline for the six gold labels; kind and
  evidence on the catalogue version, on /review, in the review checker. **Fixed:** the suite no longer
  calls Cloud Vision when the shell has `GOOGLE_VISION_KEY` (it did before, on every photo-posting test;
  Google refused the fake images, "Bad image data"). **Before merge (Sushil 2026-09-30):** breastfeeding line removed until the lawyer answers; the server
  itself refuses an infant pack's result (`/scan` withholds verdict, display, claim_check, nutrition,
  regulators) and `/compare` refuses it (client kind, printed statements, stored scan kind), tested per
  route; back-only reads stay as built. **Waiting on Sushil:** merge `categories-research`
  first, then `pack-kind`; `update.sh` (migration 019); phone check. The prompt change means the next paid
  gold run reads with rule 11 (still only when Sushil says "run the gold set"). **Then phase 2**
  (`supplements`).

- **D-139 and D-140 LOCKED** (Sushil 2026-09-30, "D-139 and D-140 accepted, with these choices"): the
  lawyer gets three questions (Nutra status on a direction, the one-RDA sentence, IMS 2(j)/3/7); amounts
  beside ICMR-NIN's RDA for men and women, never "one RDA" as a limit; baby food in shadow, users see
  allergens and the breastfeeding line only (Claude flagged 7(1)'s six particulars once; Sushil's call
  stands); band `baby` "Under 2", `toddler` "2 to 3", existing toddler profiles asked once on their next
  result; protein-powder note ships as quoted (DGI p. 60); Sushil photographs 3 + 3 gold packs, paid
  reads asked first. **Order: phase 1 `pack-kind` and phase 2 `supplements` before the first cohort,
  phase 3 `baby-food` in shadow.** Merge `categories-research` (IMS Act folder, LOCKED entries) before
  `pack-kind`, which is branched from it.

- **Phase 0 of `docs/BUILD_PROMPT_SUPPLEMENTS_BABY_FOOD.md` done** (branch `categories-research`, docs
  only, 755 tests unchanged): `docs/SUPPLEMENTS.md` (**D-139 RECOMMENDED**) and `docs/BABY_FOOD.md`
  (**D-140 RECOMMENDED**), every line from sources read 2026-09-30. Found on the way: the 2022 Nutra
  Regulations are **not notified**, run by FSSAI's direction of 18.10.2022; the infant regulations are
  in force from 1.10.2022 with four nutrient limits from a direction; label statements are Nutra 5(12)
  (the build prompt said "regulation 12"); the under-5/pregnant statement is FSDU's, not supplements';
  hydrogenated vegetable oil is a permitted tablet lubricant; ICMR-NIN's RDA 2020 (revised 2024) was
  read in the Drive viewer ICMR-NIN's page embeds (downloads off). **IMS Act read** (Sushil downloaded
  it: `sources/legal/ims-act-1992/`, quote only the "as on 15 December 2025" PDF): 2(f), 2(g), 2(j), 3,
  6, 7 quoted in `docs/BABY_FOOD.md` and D-140; 7(1) asks educational or other material for six
  particulars (a) to (f) plus (fa), so the breastfeeding line is held for the lawyer. **Waiting on
  Sushil:** "accepted" or edits for D-139 and D-140 and their questions (a lawyer for the Nutra status,
  the one-RDA sentence, IMS "promotion" and whether a result is 7(1) "educational or other material"); photos of 3 supplements and 3 baby foods for gold. **Then phase 1** (`pack-kind`).
  Headless-Chromium tricks that worked for FSSAI's JavaScript site: render the page, type into the
  table's search box and press Enter (`fill` alone doesn't filter).

- **Next build, ready to paste: `docs/BUILD_PROMPT_SUPPLEMENTS_BABY_FOOD.md`** (2026-09-30, Sushil:
  "implement supplements and baby food part, part of beta"). Phase 0 reads the FSSAI Nutra
  Regulations 2022, the Infant Nutrition Regulations 2020 (Version II), the IMS Act 1992, WHO 2023
  complementary feeding and ICMR-NIN's RDA, and proposes D-139 and D-140; nothing is built until
  Sushil accepts. Must land before the first cohort (D-083). **Legal:** the IMS Act forbids
  "promotion" of infant foods, so no grade, ranking, Compare or shop list for them; releasing
  infant-food results needs Sushil's decision (a lawyer ideally). India Code times out from WSL: the
  Act's PDF needs a manual download.

- **Beta gates, work Claude could do alone (2026-09-30, branch `beta-gates`, on top of
  `state-phase3-deployed`).** Nothing live changes except two site pages. (1) **Ingredient match
  94.5%: D-137 RECOMMENDED.** No word is misread; every miss is where the list was cut. Gold follows
  prompt rule 4 in two places = 98.0% on the saved predictions; the prompt line for `{ }` and
  "no added brackets" waits for the paid gold run. Gold files not edited. (2) **D-076 pages:** `/how`
  explains Not permitted, ingredient notes, the nutrition table and tiles; `/about` lists where the
  facts come from; the wording test now covers the site pages. **D-138 RECOMMENDED:** the
  conflict-of-interest policy, `docs/COI_POLICY_DRAFT.md`, every line from D-002 or the blueprint;
  Sushil fills who pays, industry ties, who is behind it. (3) **Gold set to 20:**
  `docs/GOLD_SET_PLAN.md`: photos of published packs (never their records), transcribed blind, one
  paid read of all 20 (about Rs 10). **Waiting on Sushil:** D-137, D-138 and its three blanks, the
  server query in the plan, whether testers' photos may be used.

- **Deployed 2026-09-30: main `8045c0f` (PR #56, phase 3 D-134, 754 tests) on the server.**
  Checked from outside 2026-09-30: `/health` build `8045c0f3a14f`, data `63346c110198`, 69 additives,
  17 NOVA markers; `/app/lib.js` web-27, `/app/sw.js` `il-shell-27`. Local suite on `8045c0f`: 754
  passed, 8 skipped, 1 xfailed. **Waiting on Sushil:** the phone check of the tiles; confirm the
  three choices in D-134 (front-photo ask inside "More", sugar/salt/energy over ICMR-NIN not tiles,
  shop list for screens only). Still open from phase 2: the four gold tables to check, "run the
  gold set" (about Rs 3), D-136. Phases 1 to 3 of `docs/BUILD_PROMPT_D132-D134.md` are all live;
  its beta list (billing is the blocker) is what comes after. **Not sourced:** a tile page's
  "who it concerns" is always empty: no approved row states it apart from its research sentence
  (D-134). A row gets one only when Sushil names the sentence to use from its source.

- **D-134 built, phase 3 of `docs/BUILD_PROMPT_D132-D134.md`** (branch `result-tiles`, web-27,
  754 tests). Sushil confirmed the phase 2 phone check first. `screen.tiles` + `screen.details`
  (lenses/screen.py), one-screen result with chips, tile pages at `#/result/<id>/look/<tile id>`,
  "More about this pack" (web/app.js). Nothing new is judged: tiles are the existing "Worth a look"
  rows. Walked in headless Chromium, light and dark, from real `/scan` answers and the real photo
  flow (Limca 1 L: "Add a photo of the nutrition table" on the first screen): no errors; a 2-tile pack
  ends at 787 of 844 px. Fixed on the way: `row wrap` rows took the page padding (the shop-list gap).
  **Merged (PR #56) and deployed 2026-09-30, see above.** Confirm three choices in D-134 (front-photo
  ask inside "More", sugar/salt/energy over ICMR-NIN not tiles, shop list for screens only).
  Still open from phase 2: the four gold tables to check, "run the gold set" (about Rs 3), D-136.

- **Deployed 2026-09-30: main `ee2e45e` (PRs #54 and #55, 737 tests) on the server**: phase 1
  (D-132 ingredient notes, D-135 NOVA aliases) and phase 2 (D-133 nutrition table); migration 018
  applied. Checked from outside 2026-09-30: `/health` build `ee2e45eb0937`, data `92c1d160ec6d`,
  69 additives, 17 NOVA markers; `/app/lib.js` web-26, `/app/sw.js` `il-shell-26`. **Waiting on
  Sushil:** the phone check (confirmed 2026-09-30: "Checked, start phase 3"); check the four gold tables Claude transcribed (gold/*.json "nutrition"); "run the
  gold set" for the paid run (6 reads, about Rs 3); D-136 stays RECOMMENDED. **Then phase 3** (D-134
  tiles, branch `result-tiles`): built, see above.

- **D-133 built, phase 2 of `docs/BUILD_PROMPT_D132-D134.md`** (branch `nutrition-panel`, web-26,
  migration 018, ~745 tests). The nutrition table: prompt rule 10 + `nutrition` schema (new
  PROMPT_VERSION), `lenses/nutrition.py` (second reading, FSSAI % RDA arithmetic, parts within
  wholes, salt = sodium x 2.5, servings x size = net), `data/nutrition_panel.json`,
  `data/nutrition_thresholds.json` (ICMR-NIN Table 15.1), `screen.nutrition` + trans fat tile,
  "Add a photo of the nutrition table" (a D-119 part; one more paid read), `/review` confirm tick,
  kind `nutrition` for packs published before, checker `nutrition_in_ocr`, eval line + release gate
  (TODO). `docs/NUTRITION_PANEL.md`. Walked in headless Chromium, light and dark, through the real
  photo flow (Gemini and the second reader stood in by Ziggy's gold answer): no errors.
  **Waiting on Sushil:** merge; migration 018 runs with `update.sh`; check the four gold tables
  Claude transcribed (gold/*.json "nutrition"); say yes to the paid gold run (6 reads, about Rs 3)
  to measure the reader; D-136 (score rule) RECOMMENDED: no rule until the gate passes. **Then
  phase 3** (D-134 tiles).

- **D-132 built, phase 1 of `docs/BUILD_PROMPT_D132-D134.md`** (branch `ingredient-notes`, web-25,
  639 tests). `data/ingredient_notes.json` (14 rows: the review's 1 to 14, with "vegetable fat, type
  not named" split from row 9), `engine.ingredient_notes()`, `screen.ingredient_notes` (tiles +
  lines), sugar answer's `more`. **Every row ships `reviewed_by: null`, so nothing shows until
  Sushil says "approved"** (then set `reviewed_by: "sushil"` on each row). Walked in headless
  Chromium, light and dark, with the rows marked reviewed: no errors. Khandsari, bura, misri in
  `sugar_aliases` (live on merge; gold set unchanged). **Rows approved by Sushil 2026-09-29**
  ("approved, keep the oil line"): all 14 carry `reviewed_by: "sushil"` and show on merge.
  **Waiting on Sushil:** merge, `update.sh`, phone check. **D-135 LOCKED and built** (same branch,
  Sushil "D-135 accepted"): "hydrogenated vegetable fat", "partially hydrogenated fat",
  "interesterified vegetable fat/oil", "shortening" are NOVA aliases (Monteiro 2019 read first-hand);
  **scores move on merge:** Britannia 48 to 36 (still D), other gold labels unchanged, a pack whose
  only industrial ingredient is one of these goes 100 A clean to 88 A ultra-processed. A marker
  right after "non-" no longer counts ("non-hydrogenated fat" was already matching "hydrogenated
  fat"). Server count query in the D-135 entry. **Then phase 2** (D-133, branch `nutrition-panel`); FSSAI L&D 2020 is already read
  (nutrition fields pp. 9 to 13). Test isolation fixed on the way: `conftest.py` clears Cloud
  Vision's per-photo text cache before each test (it made `test_no_barcode` depend on test order).

- **Next build, ready to paste: `docs/BUILD_PROMPT_D132-D134.md`** (2026-09-29). Sushil: "keep all 15
  rows now ... implement all". D-132 ingredient notes (maida, palm oil, hydrogenated fat, all 15 rows
  from ICMR-NIN 2024 and WHO, read first-hand), D-133 the nutrition table against ICMR-NIN Table 15.1
  (added sugar 25 g a day, salt 5 g a day), D-134 one-screen result with tiles. Three phases, a branch
  each. The file also lists what is still needed to complete the beta (billing is the blocker).
  Rows 3, 8, 9, 11 and a children's caffeine line have no source yet: the build must find one or say so.

- **Deployed 2026-09-29: main `7d0c1b6` (PRs #44 to #50, 603 tests) on the server** (Sushil ran
  `update.sh`: migration 017 applied, health OK, data `f4ba132bf687`). Checked from outside: `/health`
  build `7d0c1b6d2d54`, app web-24, shell `il-shell-24`, shop list in `app.js`. Includes the repro fix,
  D-130 (screen photos), the research rows and D-131. **Sushil next:** try a screenshot and "Scan it
  now" on the phone; `il tools/repro.py show 1`, then `il tools/repro.py close 1 fixed --note "D-130:
  screens are read"` (report #1's old `back_is_a_screen` scans now replay as screen reads and show
  "DIFFERS": expected). Not deployed yet: stevia's research row (merged, #51).
  **Checked on the server 2026-09-29:** `repro.py show 1` runs to the end; both scans now replay as
  results with `p1:contains` (the child's allergen found on the screen). Its note said "now unknown"
  for the build: `il` read only `settings.env`, not the `build.env` that `update.sh` writes, and git
  refuses the app folder to the `insidelabel` user. Fixed on branch `il-build-id` (`deploy/il` reads
  `build.env`; `il` is a symlink, so the next `update.sh` brings it).
- **D-130 LOCKED:** a photo of a screen is read and marked "Read from a screen, not the pack"; allergen
  lines say "on this screen" with the caution in the line; our catalogue's pack beside it (case A: the
  pack lists milk, the screen doesn't; B: they agree; C: no pack); never catalogued (outcome
  `screen_read`); shop list on the phone with "Scan it now", and the pack's result says what differs.
  DPDP data map row 7a and reviewer point 11. Seen in the walk: empty space under
  "Remove" on the shop-list card (fixed 2026-09-30 with D-134: `row wrap` took the page's padding).
- **Research rows live:** Sushil "approved" all 15 (2026-09-29); `data/additive_research.json`,
  `reviewed_by` sushil. 127 erythrosine needs the EFSA 2011 PDF (EFSA Journal 9(1):1854) by hand:
  Wiley refuses scripted downloads. **D-131:** 954, 950, 955 stay `moderate` on the WHO 2023
  sweetener guideline, and their research rows carry its sentence (approved by Sushil 2026-09-29,
  branch `sweeteners-who`). **D-131 LOCKED** (Sushil: "accepted, Stevia go with WHO"; branch
  `concern-407-960`): 407 carrageenan `low` with a sourced "why"; 960 stevia `moderate` on the WHO
  guideline. Gold labels unchanged. Stevia's research row (the WHO sentence) approved by
  Sushil 2026-09-29 and live in `data/additive_research.json` (branch `stevia-research`).
- **Parked by Sushil (2026-09-29, "will check later"):** billing, `insidelabel.in` client hold, the
  API keys, Candzey hard or chewy (review item 11 on the server; 5.2.1 hard, 5.2.2 chewy) (§8 item 1).

- **Live on the server (main `48172ca`, web-23, 580 tests), deployed and checked 2026-09-28:**
  D-121 to D-129 on top of D-115 to D-120. Result screen: three answers, "Worth a look" rows, the
  all-clear line names the allergens, "At a glance" ring and strip, "What these words mean" with `/how`
  (D-123, D-125 to D-127); scanner and wait screen (D-124). Privacy: data map `docs/DPDP_DATA_MAP.md`;
  scans unlinked after 30 days, 12-month lifetimes, `device_days` (D-128, migration 016 applied on the
  server, retention dry run clean); "Your data" / "Delete my data" and `POST /forget` (live probe
  answered `nothing_stored`); privacy page has no `[To complete]` left, DRAFT banner stays until the
  DPDP review; Gemini confirmed on paid quota (D-129). **The review-agent timer is ON** (shadow only).
- **Waiting on Sushil:** check the server's invite labels for real names (`il tools/beta.py stats`);
  a DPDP reviewer (send the data map and https://insidelabel.ai/privacy); "approved" or edits for the
  6 research drafts (`docs/research_drafts.json`, not read by the app);
  the server's scan timings query and `il tools/beta.py feedback`; which loose end next (billing,
  `insidelabel.in` client hold, Gemini key restriction and the two older keys, Candzey category).
- **Not built, decided direction:** scan photos to archive storage instead of deleting at 30 days
  (D-128, needs the reviewer's answer on photos showing a hand or face, a price read from Google, and
  the privacy page changed first); `compare.py` tie-break rule before any catalogue recommendation.
- **D-117 measurement:** 3 of 30 agreements (items 12, 13, 15). Phase B (agents publish) only after
  30 items at 95%. Items 22 to 31 went to a person; see §8 item 5 notes and the checker-fixes branch.
- **Sushil is scanning packs** (aim: 50). For each review screenshot he posts, answer in the fixed
  format (memory: review item format): Category as the exact dropdown line, ingredient fixes, front
  claims, a paste-ready Note, pack checks. Never ask him to hunt for the FSSAI licence.
- **Tokenizer brackets: D-121 LOCKED, merged** (PR #37): splits only
  outside brackets, any depth, `( ) [ ] { }` alike; no more `emulsifier ]`. INS numbers, binary and
  grade identical on 26 local labels; **scores move**: Limca 80 to 76, Ziggy 28 to 4 (class words now
  reach their NOVA rows). Accepted 2026-09-28; `update.sh` on the server if not yet run.
- **Additive rows: D-122 LOCKED, merged** (PR #38, 551 tests): INS 319 TBHQ, 472e DATEM, 296 malic acid from compendium XXVI Appendix A; "472(e)" now
  reads as 472e; sub-forms keep the parent row (gap: 331(ii), 170(ii) not in Appendix A, never seen).
  TBHQ concern low (accepted, scores 0).
- **Result screen: options ready for Sushil** (2026-09-28): today's real `/scan` output for Biscoff,
  Maliban and Limca beside option A (tidy up) and B (three answers: sugar's place in the list, how
  it's made, additives; recommended) and C (compare with the shelf, later). Page:
  https://claude.ai/artifact/2Rh7RTBhRz4D5ibsY9hbNF. Waiting: A or B, the "none found" wording, and
  whether Claude drafts shopper-facing reasons for the 69 additive rows.
- **Health report page** (2026-09-28, Sushil: "output like the Elementary report"):
  https://claude.ai/artifact/2uS8hxSpVxkLoBCh8zSoHB (tests, release gates, catalogue, scans; a summary
  written by Claude and an Ask box). Data from `tools/health_report.py` (counts only, no personal data).
  Refresh: run it (on the server: `il tools/health_report.py --no-tests --source server --out /tmp/health.json`),
  paste the JSON, Claude rewrites the summary and republishes `data.json`. The laptop DB is behind on
  migrations (no `review_drafts`), so the review-agent section is empty there.
  **Incident, fixed:** a test run with `INSIDELABEL_DB` set wrote 386 scans, 52 users and 5 problem
  reports into the laptop DB; deleted with Sushil's OK. `conftest.py` now drops `INSIDELABEL_DB`, and
  both tools strip it before running pytest.
- **Your scans + alternatives: mockups for Sushil** (2026-09-28): https://claude.ai/artifact/HV9MoviE2ipcVyvGwYjwyd
  (on-phone scan summary from the PWA's own history; alternatives as a side-by-side table + up to 3
  named packs, no named "worse" list). Found: `compare.py` ties Lotus Biscoff (1 additive) with Ziggy
  Donut Cake (21 additives, 8 industrial) because its tie test uses only concern tiers and sugar's
  place; a tie-break rule is needed before any catalogue recommendation. Waiting: his three calls.
- **Result screen rebuilt: D-123 RECOMMENDED** (branch `result-answers`, web-19): Sushil's 5 testers were
  unhappy with the output. Three answers under every headline (sugar's place and names, how it's
  made, additives worth knowing), clearer headlines, no "No concerns found" under a finding, a
  compare prompt after each result, "Your scans" on home. Sushil: merge, `update.sh`, try it on the
  phone, then "accepted". Next: plain-language additive reasons (69 rows, Sushil reviews); ask the
  testers what they wanted to know that the screen didn't say.
- **Tester feedback round 2 (2026-09-28):** scanner slow, scans up to 30 s, warnings don't stand out,
  "study says" wanted, a report-style chart over animation. Built: D-124 (branch `scanner-speed`, on
  top of `result-answers`, web-20). Mockup of the warning-first result with research lines and a
  counts donut + list-order strip: https://claude.ai/artifact/K7R9s8EFw35MZCA8vfpiEg (research lines
  are drafts until read first-hand, D-046). Waiting: the server's scan timings and the testers' own
  words (`il tools/beta.py feedback`); Sushil's call on the layout and the 19-row research table.
- **"Worth a look" rows: D-125 LOCKED, built** (branch `scanner-speed`, web-21, 563 tests). Research
  table `data/additive_research.json` is empty: 19 worth-knowing rows to research from primary
  sources, each reviewed by Sushil before it is added.
- **D-126 LOCKED, D-127 RECOMMENDED** (branch `scanner-speed`, web-22, 567 tests): the all-clear line
  names the allergens; setup asks "Does anyone you shop for avoid a food...?"; "At a glance" ring and
  strip; "What these words mean" with links to the new `/how` page.
- **D-123, D-124, D-127 accepted and merged (2026-09-28).** Deploy: `sudo /opt/insidelabel/app/deploy/update.sh`.
- **DPDP data map written: `docs/DPDP_DATA_MAP.md`** (branch `privacy-dpdp`), from the code and the Act and the
  Gemini terms read first-hand; the DPDP Rules 2025 only via the PIB summary.
- **D-128 LOCKED and built (575 tests, migration 016):** keep what the label said, unlink who scanned it after
  30 days (install id and household profiles), `device_days` keeps the W4 count; feedback and reports 12 months;
  installs 12 months after last seen. Runs inside the daily retention job. Privacy page "How long we keep it"
  filled. Not built: photos to archive storage (needs the reviewer's answer on photos showing a hand or face,
  and a price read from Google). Waiting on Sushil: is Gemini on paid quota; check the server's invite labels
  for names; a DPDP reviewer.
- **D-129 LOCKED and built (580 tests, web-23):** Gemini confirmed on paid quota; "Your data" in the app footer
  with "Delete my data" (`POST /forget`); privacy page "Your choices" filled. The privacy page has no
  `[To complete]` left; its DRAFT banner stays until the DPDP review.
- **Next work, in order (before invites):** (1) and (2) done; (3) built as D-123, see above. (3) The result-screen
  discussion Sushil asked for ("not much useful for a user"; Biscoff's band says "No concerns found"
  under a sugar headline): mockups, his decision. (4) Privacy page (contact `connect@insidelabel.ai`),
  DPDP review, DPDP data map. (5) Loose ends below: billing off the free trial, `insidelabel.in`
  client hold, Gemini key restriction and the two older keys, Candzey category check (5.2.1 or 5.2.2).
- **Working rules this project has learned:** every new decision is RECOMMENDED until Sushil says
  "accepted"; work on a branch and give the link `https://github.com/sushil6666/InsideLabel/pull/new/<branch>`
  (`gh` is not installed); ask before any paid Gemini or Cloud Vision call and say the cost; Sushil
  runs server commands (give them exactly, with `--zone=asia-south1-a` for `gcloud compute ssh`);
  never touch the uvicorn on port 8000 on the laptop.

The older notes below are kept for their detail.


**Done 2026-09-27: https://insidelabel.ai is live** (D-114, DEPLOY.md steps 1 to 10, with Sushil).
**For anything on the server or Google Cloud, start with `OPERATIONS.md`** (the day's full log is its §9).
Project `insidelabel`, VM `insidelabel-1` in
`asia-south1-a`, `e2-medium`, static IP `8.234.95.74`; SSH with `gcloud compute ssh insidelabel-1 --zone=asia-south1-a`
from Cloud Shell. Cloudflare DNS for `insidelabel.ai` and `www` (DNS only). Checked from outside:
Let's Encrypt certificate (to 2026-12-26, Caddy renews), http to https, `www` 301 to the main
address, security headers, no `Server` header, `/review` asks for a login, a scan without an invite
gets `invite_required`, `replay` gets `replay_disabled`. On the server: 14 migrations on
PostgreSQL 18, build `45f9feb078dc`, reviewer `sushil` (logged in), first backup and **restore test
PASS**, timers (backup 02:30, photo cleanup about 04:00 India time; disk snapshot 03:30, kept 7 days),
one invite (Sushil's own), and **one real scan from the phone**: `verdict`, 5.7 s, Cloud Vision read
1,717 characters in parallel with Gemini, no retries, no setup alarms.
**Reboot test, 2026-09-27 09:13 UTC** (the kernel from the morning's upgrade): the site was down under
a minute and every service came back by itself (app, Caddy, PostgreSQL, both timers). Five tester
invites made on the server, labelled T01 to T05 (codes not recorded here).
**Uptime check** (2026-09-27): Cloud Monitoring checks `https://insidelabel.ai/health` every 5 minutes
from all regions and emails Sushil after 60 s of failure (OPERATIONS.md §5). Free at this size.

1. **Loose ends from the deploy (Sushil):**
   - **Billing:** confirm the account is upgraded from the free trial to paid with automatic payment
     (Billing, Overview: no "Activate" button). **Must be done before invites**, or the VM stops and
     its disk is deleted when the trial ends. Budget alert about ₹1,500 a month.
   - **`insidelabel.in` is on GoDaddy `client hold`** since 2026-09-12 (the `.in` registry's record:
     registered 2026-09-07, paid to 2029-09-07), so it resolves nowhere. Usually the registrant email
     verification: GoDaddy, Domain settings, Contact information, resend and click. Then move its
     nameservers to Cloudflare, add `A @` and `A www` to `8.234.95.74` (DNS only), and put the full
     `deploy/Caddyfile` back on the server (the server's copy leaves the `.in` names out for now).
   - **Keys:** the server has its own pair in the `insidelabel` project: `server-vision` (Cloud Vision
     only, IP `8.234.95.74` only) and `gcp_website` (Gemini, AI Studio). Confirm the Gemini key's
     restriction went through (`gcloud services api-keys list` in Cloud Shell), and check the two older
     keys in the project, `testing` and `insidelabel`: restrict or delete whichever the laptop doesn't
     use. The Vision key's value appeared in the chat; it only works from the server, so keeping it is
     acceptable; rotate it if preferred.
   - Walk the rest of the app on the phone (profiles, compare, report a mistake, report a problem):
     the manual gate in §11.
2. **D-115 LOCKED 2026-09-27, built** (branch `nova-label-words`): the first live scan's headline and
   "On the label" quote showed our table's row name ("added flavour (natural/artificial/
   nature-identical)"), not the pack's words. Now both use the words as read; which row matches,
   and every verdict, is unchanged. 103 new tests (82 fail on the old code); the six gold labels'
   headlines unchanged, their quotes now the pack's words. **Sushil: merge, then
   `sudo /opt/insidelabel/app/deploy/update.sh` on the server.** Before invites.
3. **D-116 LOCKED 2026-09-27**: review item 2 on the live server (ORGANIC INDIA
   Tulsi Mulethi) carries only an Ayurvedic medicine licence, no FSSAI licence. The FSS Act 2006
   s.3(1)(j) (read from FSSAI's copy) excludes "drugs and medicinal products" from "food", so such
   packs stay out of the catalogue; the reviewer rejects them with the D-116 reason. Item 2 was
   **rejected** on the live server with the D-116 reason. The user-facing note for such packs is a
   separate proposal, not built.
4. **Decimal-point split: FIXED** (branch `decimal-split`, not yet merged): `core/tokenize.py` split at
   every ".", so "Natural Mint Flavour 0.010g" became "natural mint flavour 0" and "58.3%" became
   "58" + a fragment. A full stop now splits only when it isn't between two digits. Gold set and
   recorded readings: every band, score, verdict and flag identical; `eval_vision.py` identical
   (ingredient F1 0.945, INS F1 1.000, 0 flips). **Sushil: merge, then `update.sh` on the server,
   ideally before today's 50 scans are reviewed.**
   **Known, older, not fixed:** an amount after a name *without* brackets ("Sugar 25.5%") stops the
   exact match, so that sugar isn't counted (score 88 instead of 80). Fixing it changes judgements on
   real packs, so it needs its own check against the gold set and Sushil's decision; pinned as an
   expected failure in `tests/test_tokenize_decimals.py`. Today's scans will show how common it is.
   **Also:** the server's catalogue starts fresh; the 5 products on the laptop's database are not
   moved (Sushil re-scans, which also gets their barcodes).
5. **From the first supermarket run (2026-09-27), in priority order** (full detail in the session
   log, "First supermarket run on the live site"):
   a. **A missing sugar name changed a verdict**: Lotus Biscoff reads clean, grade A, score 100 with
      36 g added sugars per 100 g, because "candy sugar syrup" is not in `sugar_aliases`. Collect the
      missing names, re-run the gold set, show Sushil what moves, then his decision. **Before invites.**
      **D-120 LOCKED and built** (Sushil, 2026-09-27): "candy sugar syrup" and "sugar syrup" added
      (FSSAI L&D 2020 definition of added sugars); bare "malt" deliberately not. Biscoff's headline is
      now "Sugar appears under 2 names"; its band still says "No concerns found" (for the result-screen
      discussion). Gold set re-scored from stored predictions: per-label results identical. 3 tests.
   b. **Tokenizer: nested square brackets and braces** give fragments like `emulsifier ]` and
      `antioxidant }`, which D-115 can now show to a user. Fix with a gold-set re-run. **Before invites.**
   c. **Additive rows missing**: INS 319 (TBHQ, seen on two packs) and INS 472(e); and a decision on
      sub-forms (503(ii), 450(i), 1101(i), 322(i)) that today match only their parent number.
      Each new row needs its Appendix A basis (D-046).
   d. **The result screen** ("not much useful for a user", Sushil): options and mockups to discuss.
   e. **D-117 LOCKED 2026-09-27: review agents** (Sushil: "one agent will draft and another agent will
      confirm; if any ambiguity then human will review"; drafter Gemini). Gemini drafts every new
      item; a rules checker confirms against Cloud Vision's text; anything doubtful goes to Sushil
      with the draft filled in. Shadow first; publishing switches on after 30 of Sushil's reviews
      agree at 95 %. Remaining queue items (about 38) wait for it. **Phase A built** (branch
      `review-agents`): migration 015 (`drafted_by`, `category_source`, `review_drafts`); the
      drafter (`review/agent.py`, prompt `review/draft_prompt.py`); the checker (`review/checker.py`,
      15 checks, word table `data/category_words.json`); the item page shows the draft and fills
      the form; "Drafted by" and "Category came from" on every publish; `tools/review_agent.py`
      (run, show, measure, mark-drafted); a shadow timer, **not enabled** (paid). 21 tests; no paid
      call made. **Next (Sushil):** merge, `update.sh`, copy the new units, mark the 2026-09-27
      items `--by claude`, then agree to the first paid drafting run (OPERATIONS.md §5).
      **Timer switched on by Sushil 2026-09-27** ("Automatic", for the 50-pack day): drafts up to
      5 new items every 10 minutes, about 50 paise each, shadow only. Each item is drafted once per
      prompt version (a failed draft is stored as `error`, never retried). Item 13 confirmed after the
      panel-word fix (PR #31); 12, 13 and 15 are the first agreements toward the 30-item gate.
      **First timer runs (items 22 to 31):** all 10 went to a person. Fixed from `show` output: the
      drafter's category "14.1.5 Coffee, ..." is cut to its code (item 24's empty category box);
      a code-first declaration "(1.1.2) PROPRIETARY FOOD" is read (items 27, 28, where it was on the
      front: still a person until front text is read); "soft candy" gives 5.2.2 (Codex 05.2.2, item
      22); the user's "same pack" tick settles an indeterminate front/back match (D-035; 7 of 10).
      Categories with no printed code or word rule (13.5 supplements, drinks) stay with a person.
      **Phase B, before publishing:** the agent publishing through `approve()`, one-click undo, the
      agent-published list for spot checks.
      **First shadow run, 2026-09-27 16:57 (paid, 5 items, 12 to 16): all five "needs a person".**
      One was right for the right reason (item 14: Cloud Vision hadn't read the ingredient list, so
      nothing could check Gemini). The other four exposed checker rules, fixed on branch
      `review-agent-tuning`: a recipe on the pack that also says "ingredients" (12); a nutrition
      panel Cloud Vision read in among the list (13); an accent, CRÈME vs creme, and "Net Weight"
      after the list (15); and a **wrong word rule** (16): "sugar boiled confectionery" is not hard
      candy, since **FSSAI 2.7.1** (Food Products Standards, read from FSSAI's PDF) defines it to
      include "toffee or milk toffee"; Gemini's 5.2.2 for a butter toffee was right. **Claude's
      earlier advice for item 11 (Candzey, 5.2.1) used that same wrong reasoning:** check whether
      it is a hard or a chewy sweet; if chewy, 5.2.2. After deploying: `recheck 12 13 14 15 16`
      (free) shows what the tuned checker makes of the same answers.
      **Recheck after tuning (free):** 12 and 15 confirmed, and Sushil published both unchanged (the
      first two agreements for the D-117 gate); 14 and 16 rightly still need a person; 13 still
      failed `nothing_lost` on "added" and "sodium": the server's text showed them as nutrition-panel
      rows read in among the list, so both joined the panel-word list (a dropped "sodium bicarbonate"
      is still caught by "bicarbonate"; 2 tests). After deploy, `il tools/review_agent.py recheck 13`. **D-118 RECOMMENDED:** ask for a clearer photo
      at scan time when Cloud Vision can't confirm a new pack's list (Sushil: before the result).
      **D-118 LOCKED and built** (branch `retake-at-scan`): the review checker's independent-read test
      is shared (`checker.independent_read`); `/scan` asks only for a pack that would add a catalogue
      version, only when Cloud Vision read the photo; "Use this one anyway" (`accept_unconfirmed`) is
      recorded on the scan. 5 tests; walked in headless Chromium at phone width (retake screen, both
      buttons, the flag sent on the second request). App `web-17`.
      **D-119 LOCKED and built** (branch `multi-photo-list`, Sushil in the shop: the Britannia 50-50
      Cheeze Dipped list doesn't fit one photo): up to three photos of the list, joined on the
      server into one back photo (`photo_join.py`), so the frozen reading prompt, storage, replay and
      retention are unchanged; one photo is today's scan byte for byte. 8 tests; walked in headless
      Chromium (part 2 sent as `back2`). Amended the same day: the app asks "Is the whole ingredient
      list in this photo?" and shows the part camera only on "No". App `web-18`. **Overlap check PASSED** (2026-09-27, Sushil's
      go-ahead, 3 Gemini calls): Britannia Treat, Ziggy donut and Maliban wafer backs cut into two
      overlapping parts (one printed line in both), app-sized, joined by `photo_join`; each reading was
      identical, word for word, to the single-photo reading, with no duplicated ingredient. Against gold:
      verdict-changing rate 0%, INS F1 1.000, score drift 0 (Britannia's ingredient F1 0.8 is the
      known brace-nesting split, the same on the single photo). Tesseract cross-check only, no Cloud
      Vision call. Output in a scratch path, not `reports/`.
6. Then the DPDP data map, and the other items below (invites only after the privacy page and the
   DPDP review).

**Earlier list (2026-09-27), still valid:**

- **Claude: a one-page DPDP data map** from the code: every piece of personal data
  (label photos, device id, invite code and tester label, feedback and problem-report text,
  household profiles: a child's age band and avoid list, D-074), where it is stored, who sees
  it (Google as processor for Gemini and Cloud Vision), and when it is deleted (D-098). Sushil
  hands it to the DPDP reviewer with `web/site/privacy.html`. About 30 minutes.
- **Domains bought (2026-09-26): `insidelabel.ai` and `insidelabel.in`. Sushil: `.ai` is the main
  address** ("we are claiming for chatbot and all in future plan"). `insidelabel.in` and `www.` of
  both redirect to it permanently; `INSIDELABEL_PUBLIC_URL=https://insidelabel.ai`. **Contact address
  (Sushil, 2026-09-28): `connect@insidelabel.ai`**, on Zoho Mail (MX `mx.zoho.in`, SPF `include:zoho.in`,
  DMARC `p=none` reporting to the same address; checked by DNS lookup 2026-09-28). The privacy
  page's "who to write to" line waits for the privacy page and DPDP review. Goes into D-114 with the host. The chatbot plan (Pro) is D-113,
  LOCKED; it supersedes D-001's "not a chatbot". Auto-renew both domains.
- **Sushil: pick the host** (suggested: one small Ubuntu VPS in Mumbai, 2 GB). Then Claude
  records **D-114** (hosting; PostgreSQL 18 on the server until 19 is released, which changes
  D-087; photos on the server disk until R2 is built) and writes `deploy/`: Caddy (HTTPS),
  a systemd service (one process, D-095), a settings template (`INSIDELABEL_INVITE_ONLY=on`,
  replay off, `INSIDELABEL_PROXY_HOPS=1`), daily retention and backup jobs, a restore test,
  and `DEPLOY.md`. About 1 to 2 hours; the first deploy with Sushil another 1 to 2.
- **Sushil:** the FSSAI 2025 amendment PDF (browser download); privacy/about `[To complete]`
  and a DPDP reviewer; Gemini auto top-up and a budget alert; review item #9 (still `open`
  on the local DB).

Estimate given: live on the domain in one working day; invites in 2 to 4 days, mostly
waiting on the DPDP review.

**This week - only Sushil can do these (they unblock the most):**

1. **Housekeeping (10 minutes):** delete the two old Gemini key lines in `~/.bashrc`
   (three are still there; only the last counts); restrict the Gemini key to the
   Generative Language API; set a budget alert and decide prepaid vs post-paid (§7);
   ~~reject review item #7 on `/review`~~ ✅ rejected (duplicate), with #2.
2. **Try the PWA on a low-end Android phone** - the one manual gate that only a real
   phone answers (camera, barcode, photo, result, profiles, compare, report). Easiest:
   USB debugging + `adb reverse tcp:8000 tcp:8000`, then open `http://localhost:8000/app/`
   in Chrome on the phone. Use "Report a problem" for anything odd - it's traced (D-092).
3. **Grow the gold set to ≥ 20 labels** (RUNBOOK) - a third in bad conditions, and packs
   whose front says "no added sugar" / "no preservatives" / "made with real X" (otherwise
   the false-contradiction gate stays unmeasured). Unblocks 2 failing gates.
4. ~~Publish the queued packs on `/review`~~ ✅ 5 published (#2 and #7 were duplicates);
   barcodes still to add (Waiting for Sushil, 6). **Next:** start the 50-SKU seed, 15 kids'
   biscuits first (D-058), via the D-089 flow (`tools/leads.py add` → buy → scan front +
   back with barcode → `link --barcode` → publish). Unblocks the 2 catalogue gates.

**Code - Claude can build these next (in this order):**

5. ~~Store Cloud Vision's text on the scan row~~ ✅ overnight 2026-09-26 (D-094).
6. ~~Rate limits on `/scan` and `/problem`~~ ✅ overnight (D-095). Move the counters to
   Postgres/Redis before running more than one server process.
7. ~~"Send it to us"~~ ✅ overnight (D-096); phone test pending (Waiting for Sushil, 3).
8. ~~Individual reviewer logins and D-080 photo retention~~ ✅ overnight (D-097, D-098);
   retention needs a daily cron at deploy (item 13).
9. ~~One INS parser, for real~~ ✅ overnight (D-099), five private patterns removed.
9a. ~~Gate the `replay` form field~~ ✅ D-101.
10. **Lift ingredient match 0.945 → ≥ 0.95** once the gold set is bigger (Britannia is the
    weakest at 0.80).
    D-137 LOCKED (2026-10-01): the gold now follows prompt rule 4; expected 98.0%, gate PASS, once
    re-scored on the laptop against the saved predictions (pending).
11. **Fallback-model comparison** (`gemini-3.5-flash` on the gold set, ~₹3) when Google is
    quieter, if the retry data shows "busy" is common.

**Then, towards week 10:**

12. **Trust pages** (D-076): privacy policy (DPDP, parental consent; name Gemini **and**
    Cloud Vision as processors), COI policy, methodology, who is behind it.
13. **Deploy**: host with PostgreSQL 19, HTTPS, R2 for photos, a daily cron running
    `tools/retention.py --apply` (D-098 - not an R2 lifecycle rule, which can't see holds),
    backups tested by a restore; `GEMINI_API_KEY`, `GOOGLE_VISION_KEY`, `INSIDELABEL_BUILD` as
    secrets (without the Vision key the server quietly falls back to slow Tesseract).
14. **Play closed testing** (D-011, D-148): PNG icons 192/512 ✅ (D-112, `web/icon-192.png`, `icon-512.png`);
    developer account verified ✅ (Sushil, 2026-10-01); app created with package `ai.insidelabel.app.f`
    (D-149) ✅; TWA project, asset links route and the release guide on `play-wrap`
    (`docs/PLAY_RELEASE.md`); the tester requirement is read in Play Console (that file, section 4).

Later / not blocking the beta: share target (D-077, after W4); D-073 cheap Tesseract
re-check; refresh EU rows from a current EUR-Lex text and check cyclamate's US status;
drop PG18 after PG19 GA.

---

## 9. Timeline anchors

- Beta: 15-week plan, Sep-Dec 2026 (blueprint §16). Wave 1 accepted with a ~3-week slip → **W4 retention answer late December 2026** (D-084).
- Beta gate: ≥30 % W4 retention with ≥2.5 scans per returning user; ≥95 % ingredient match on seeded categories; <1 % false-positive contradictions; **0 allergen misses** on the gold set.
- Deploy (host, R2, retention cron per D-098) - week 10.
- Wave 2 (share target, WhatsApp card) only after the W4 number (D-083).

---

## 10. Where things are

| Path | What |
|---|---|
| `STATE.md` | this file - status, setup, next |
| `DECISIONS.md` | every decision with its reason (append-only) |
| `insidelabel-blueprint.md` | product & engineering blueprint v1.1 |
| `API_README.md` | endpoints, database, reviewer screen, regulator comparison |
| `RUNBOOK.md` | how to photograph, transcribe and score a gold batch |
| `CLAUDE.md` | working rules for AI coding sessions |
| `src/insidelabel/review/agent.py`, `checker.py`, `draft_prompt.py`, `tools/review_agent.py` | the review agents (D-117): Gemini drafts, the rules checker confirms or sends to a person; shadow mode |
| `OPERATIONS.md` | **running the live site**: what exists on Google Cloud and where, GCP words in plain language, everyday commands, what to do when something breaks, money, security rules, the log of 2026-09-27 |
| `DEPLOY.md`, `deploy/` | the server (D-114): step-by-step setup, Caddy, systemd units, backup/restore/update scripts, settings templates |
| `src/insidelabel/` | the package (core, extraction, reliability, claims, lenses, db, review, api) + `trace.py` / `repro.py` (D-092); OCR readers in `extraction/providers/` (`cloud_vision.py`, `ocr_check.py`) |
| `data/` | the knowledge tables - the moat |
| `migrations/` | Postgres schema, plain SQL, applied in order |
| `tests/` | 379 tests (+ `regression/problems/`, D-092); `conftest.py` gives each DB test module its own database and resets the rate limits (D-095) |
| `tools/` | release gate, leads (D-089), `repro.py` (D-092), `compare_ocr.py` (D-093), `reviewers.py` (D-097), `retention.py` (D-098), eval, batch scan, gold stubs, queue predictions, PG19 installer |
| `gold/`, `photos/`, `predictions/` | 6 real labels: hand transcription, photos, recorded model output |
| `research/` | private marketplace screenshots behind leads (git-ignored; never published - D-089) |
| `archive/prototype/` | the pre-package prototype, kept for history |
| `web/` | the PWA (D-090): `app.js` views, `lib.js` storage/API, `camera.js` barcodes, `sw.js` |
| `prototype.jsx` | early UI prototype (still shows a numeric score - superseded by D-064) |

---

## 11. Release plan - closed beta with every validation

"Release" here means the **closed beta on Play** (D-007): 50-100 users, a 4-week
retention test. Public launch comes after the W4 number (D-083).

### Computed gates - `tools/release_check.py` (exit 1 until all pass)

| Gate | Threshold (blueprint §15) | 2026-09-25 |
|---|---|---|
| Gold set size | ≥ 20 labels, a third in bad conditions | ❌ 6 |
| Hallucinated INS numbers | 0 | ✅ 0 |
| Verdict flips gold vs model | 0 | ✅ 0 |
| Ingredient match | ≥ 95 % | ❌ 94.5 % |
| Allergen misses | 0 | ✅ 0 (6 labels × 11 allergens) |
| False contradictions | < 1 % | ⏳ unmeasured - no gold claim matches a rule yet |
| Every gold INS has a table row | all | ✅ |
| Additive rows still `verify:true` | 0 | ✅ 0 |
| D-051, D-052, D-055 decided | locked | ✅ locked 2026-09-25 |
| Published catalogue | ≥ 50 SKUs | ❌ 5 (queue empty; no barcodes yet) |
| Kids' biscuits published (D-058) | ≥ 15 in 7.2.1 / 7.2.2 | ❌ 0 (category picker ready) |
| Test suite (`--with-tests`) | green | ✅ 379, 1 skipped (`hosting`, 2026-09-27) |

### Manual gates - tick when done

- [ ] PWA built ✅ (`web/`) and tested on a low-end Android phone ⏳ (camera, barcode, result, profiles, compare, report)
- [ ] Share target (if D-088 accepted)
- [ ] "Send it to us" - built ✅ (D-096); tried on a phone ⏳
- [x] Individual reviewer logins - built ✅ (D-097); `sushil` created on the live server 2026-09-27 ✅
- [x] Photo retention 30 days (D-080) - job built ✅ (D-098); daily systemd timer on the live server 2026-09-27 ✅
- [ ] Rate limit on `/scan` and `/problem` - built ✅ (D-095); proxy hops 1 and one process on the live server 2026-09-27 ✅; error monitoring ✅ built in (D-092 reports + setup alarms), Sentry optional
- [ ] Privacy policy (DPDP; children's data; parental consent at profile creation)
- [ ] COI policy, methodology, who is behind the app, "last verified" dates (D-076)
- [ ] Deployed: HTTPS ✅ and backups tested by restoring one ✅ (2026-09-27); PostgreSQL **18** until 19 is released (D-114); R2 ⏳
- [ ] Play Console: account verified (done 2026-10-01, Sushil), closed-testing requirement met, audience = adults
- [x] D-055 stop number written down before launch (continue ≥ 30 %, retest 20-30 %, stop < 20 %)

### Where the catalogue comes from (D-088, D-089 - locked)

Not from scraping Flipkart / Amazon / Blinkit / Swiggy / Zepto: their terms forbid
automated *and* manual copying (Amazon, Flipkart, Swiggy and Instamart read
first-hand; Zepto and Blinkit only via search excerpts, since their pages block
scripts - see D-088), and FSSAI's 2024 advisory exists because listings
often don't match the pack. Instead: photograph real packs (D-058); let users share
listing screenshots into the app (D-077, pulled into the beta) so they go through
review; use Open Food Facts only to choose which packs to buy (ODbL - don't ingest);
ask GS1 India about brand-supplied product data.

Screenshots Sushil collects are **leads**, not sources (D-089):

```
screenshot → identify product → obtain the pack → photograph front + back
           → OCR (/scan) → review → InsideLabel product record
```

`tools/leads.py` tracks each lead (`needs_primary_source` → `pack_obtained` →
`label_captured` → `published`, or `abandoned` with a reason) and keeps the
screenshot privately in `research/` by content hash. Keep it to a working list of
products to buy - not a bulk archive of listings, and never copy listing text into a record.

