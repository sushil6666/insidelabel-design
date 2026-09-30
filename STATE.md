# STATE.md - where InsideLabel is, and how to pick it up

**Last updated:** 2026-09-30 (**https://insidelabel.ai is live**, `main` = `8045c0f`, PR #56 (phase 3, D-134), deployed and checked from outside) · **Owner:** Sushil · **Tests:** 755 passing, 8 skipped, 1 expected failure · **Release gate:** `python tools/release_check.py` - NOT READY (2 failing; 4 with `INSIDELABEL_DB` set) · **Latest real scan:** 5.7 s on the live server (2026-09-27), Gemini + Cloud Vision, `verdict`

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
| Rate limits on `/scan`, `/problem`, `/send-to-us` per install and per IP (D-095) | ✅ overnight; in memory, one process | `ratelimit.py` |
| "Send it to us" after two refused scans (D-070, D-096) | ✅ overnight; walked in headless Chromium against a faked API, not on a phone | `POST /send-to-us`, migration 008, `web/app.js` |
| One login per reviewer (D-097); shared token only until the first account | ✅ overnight | migration 009, `review/accounts.py`, `tools/reviewers.py` |
| Photo retention job, 30 days, holds respected (D-080, D-098) | ✅ overnight; runs nowhere yet (cron at deploy) | migration 010, `retention.py`, `tools/retention.py` |
| Web app / PWA: barcode → back photo on 404 → result; household profiles + consent; compare; report a mistake; `/updates` on open; offline shell | ✅ built; **first real-phone scan on the live site 2026-09-27** (invite link, "Before you start", barcode, back photo, result); profiles, compare and report not yet walked on a phone; stack is D-090 | `web/`, served at `/app/` |
| Hosting (D-114): Google Cloud VM `insidelabel-1`, Mumbai, `e2-medium`, Ubuntu 24.04; Caddy HTTPS, one uvicorn, PostgreSQL 18; nightly backup + photo cleanup; daily disk snapshot | ✅ **live 2026-09-27** at https://insidelabel.ai (IP `8.234.95.74`); restore test PASS 2026-09-27 | `DEPLOY.md`, `deploy/` |

**Accuracy on the gold set (6 real labels, `tools/eval_vision.py`):** 0 verdict
flips, INS F1 1.000 (0 missed, 0 hallucinated), ingredient F1 0.945, front-claim
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
| `INSIDELABEL_INVITE_ONLY` | the invite-only web beta (D-102) | `on` at deploy: only phones that joined with a code can scan; default off |
| `INSIDELABEL_PUBLIC_URL` | join links printed by `tools/beta.py invite` | e.g. `https://yourdomain.in`; or pass `--base` |
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

## 8. Next steps - the road to the closed beta (in order)

Run `python tools/release_check.py` (add `INSIDELABEL_DB=…` for catalogue gates)
to see where each gate stands. §11 has the full list. Done today: D-051/52/55 decided,
food categories, PWA built, D-092 reproduction, D-093 Cloud Vision, scan speed,
setup alarms.

**NEXT SESSION STARTS HERE (2026-09-30).** Where things stand, newest first:

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
11. **Fallback-model comparison** (`gemini-3.5-flash` on the gold set, ~₹3) when Google is
    quieter, if the retry data shows "busy" is common.

**Then, towards week 10:**

12. **Trust pages** (D-076): privacy policy (DPDP, parental consent; name Gemini **and**
    Cloud Vision as processors), COI policy, methodology, who is behind it.
13. **Deploy**: host with PostgreSQL 19, HTTPS, R2 for photos, a daily cron running
    `tools/retention.py --apply` (D-098 - not an R2 lifecycle rule, which can't see holds),
    backups tested by a restore; `GEMINI_API_KEY`, `GOOGLE_VISION_KEY`, `INSIDELABEL_BUILD` as
    secrets (without the Vision key the server quietly falls back to slow Tesseract).
14. **Play closed testing** (D-011): PNG icons 192/512 ✅ (D-112, `web/icon-192.png`, `icon-512.png`),
    check the current tester requirement in Play Console.

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
- [ ] Play Console: account verified, closed-testing requirement met, audience = adults
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

