# STATE.md — where InsideLabel is, and how to pick it up

**Last updated:** 2026-09-25 (PWA + D-092) · **Owner:** Sushil · **Tests:** 193 passing, 1 skipped · **Release gate:** `python tools/release_check.py` — NOT READY (2 failing; 4 with `INSIDELABEL_DB` set)

This is the living status document. Read it first in any new session, then
`DECISIONS.md` for the *why*. Update the "Last updated" line, the numbers and
the "Next" list whenever something changes.

> The blueprint (`insidelabel-blueprint.md` §15–16) says the 15-week beta plan
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
| INS parsing — 3–4 digit numbers, `()[]{}` brackets, `&` separators, unit guard | ✅ reads every printed INS on all 6 gold labels | `core/tokenize.py` (the only INS parser) |
| Additive table — 66 additives, 35 verified against FSSAI + Codex on 2026-09-25, none left `verify:true` | ✅ | `data/additives.json` |
| Vision read (Gemini `gemini-3.6-flash`) + independent OCR cross-check: Google Cloud Vision when `GOOGLE_VISION_KEY` is set, Tesseract otherwise (D-093: 3.6 s vs 22.7 s, recall 50/52 vs 27/52, 0 wrong additions) | ✅ | `extraction/providers/` (`cloud_vision.py`, `ocr_check.py`) |
| Reliability gate (never shows "clean" on a partial read) | ✅ | `reliability/gates.py` |
| Claim checker (no added sugar / no preservatives / made with real X) | ✅ built; **in shadow for the beta (D-051)**: stored for reviewers, shown to users only with `INSIDELABEL_CLAIMS_TO_USERS=on` | `claims/checker.py` |
| Allergen check, five states, stricter 0.95 gate, first key in every result | ✅ | `lenses/allergens.py` |
| Shelf comparison (2–4 packs, best pick for a child) | ✅ `/compare` | `lenses/compare.py` |
| India vs EU vs US comparison — optional, information only | ✅ 12 additives | `lenses/regulators.py`, `data/regulatory_status.json` |
| Wording lint (no "misleading/illegal/toxic/safe/free from…") on tables **and** live output | ✅ in the test suite | `tests/test_wording.py` |
| Postgres schema with rules enforced by the DB | ✅ 5 migrations | `migrations/` |
| Marketplace leads → physical label → record (D-089); only `physical_label` versions can publish | ✅ | `db/leads.py`, `tools/leads.py`, migration 005 |
| Scan persistence: barcode lookup, review queue, findings + evidence, photos | ✅ when `INSIDELABEL_DB` is set | `db/store.py`, `media.py` |
| Reviewer screen (`/review`) — the only path into the catalogue; FSSAI food category required on approve | ✅ | `review/` |
| FSSAI food categories (Appendix A Food Category System, 271 codes) | ✅ loaded by `migrate` | `data/food_categories.json`, `db/categories.py` |
| "Report a mistake" `/report`, "ready?" `/updates` | ✅ | `api/main.py` |
| Result-screen block (`screen` in `/scan`): people first, headline from a finding, D-063 names, grouped ordinary items, no score; `profiles` with names kept on the device | ✅ D-091 | `lenses/screen.py` |
| Reproducing problems (D-092): request ids, a replayable trace on every scan row, "Report a problem" + automatic crash and server-error reports, `tools/repro.py` | ✅ proved end to end (app → server → report → replay "same as what the user saw") | `trace.py`, `repro.py`, migration 006, `tools/repro.py` |
| Web app / PWA: barcode → back photo on 404 → result; household profiles + consent; compare; report a mistake; `/updates` on open; offline shell | ✅ built, **not yet tried on a real phone**; stack is D-090 | `web/`, served at `/app/` |

**Accuracy on the gold set (6 real labels, `tools/eval_vision.py`):** 0 verdict
flips, INS F1 1.000 (0 missed, 0 hallucinated), ingredient F1 0.945, front-claim
F1 0.883. Gold scores: Britannia 48, Limca 80 (×2), Maliban 56, Patanjali 48,
Ziggy 28. **The set is 6 labels; the RUNBOOK target is 20–30** — the accuracy
question the README asks is not answered yet.

**Catalogue:** 0 published products. 6 real packs (the gold labels) are waiting
in the review queue on the local database.

---

## 3. Set up from scratch (WSL Ubuntu 24.04)

```bash
cd ~/insidelabel
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                      # fastapi, psycopg, jinja2, google-genai, pgserver, pytest…
sudo apt install -y tesseract-ocr            # independent OCR cross-check (5.3.4 here)

# PostgreSQL 19 (beta until GA ~end Oct 2026) on 5432 — D-087
sudo PG19_PORT=5432 bash tools/install_pg19.sh   # adds apt.postgresql.org, creates cluster + role
createdb insidelabel && createdb insidelabel_test
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"

pytest -q                                    # 193 pass, 1 skipped; DB tests use embedded Postgres
```

**Environment variables**

| Variable | Needed for | Notes |
|---|---|---|
| `GEMINI_API_KEY` | real `/scan` vision calls | tests replay recorded JSON, no key needed |
| `INSIDELABEL_DB` | storing scans, catalogue, `/review`, `/report`, `/updates` | unset → API stores nothing, behaves as before |
| `INSIDELABEL_MEDIA` | where scan photos go | default `./media` (git-ignored) |
| `INSIDELABEL_REVIEW_TOKEN` | reviewer login password | username = reviewer's name |
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
(migrations 001–006, 6 items queued, no leads yet) and `insidelabel_test` (only used to
create/drop per-module test databases). PostgreSQL 16 was removed.

---

## 4. Daily commands

```bash
# API, with storage and the reviewer screen
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \
INSIDELABEL_REVIEW_TOKEN="…" uvicorn insidelabel.api.main:app --reload
#   http://127.0.0.1:8000/docs     API
#   http://127.0.0.1:8000/review   reviewer screen (name + token)
#   http://127.0.0.1:8000/app/     the PWA (camera needs HTTPS or localhost; see §8 item 6)

pytest -q                                                    # everything, embedded Postgres
INSIDELABEL_TEST_PG="postgresql:///insidelabel_test?host=/var/run/postgresql" pytest -q   # on PG19
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"   # new migrations

python tools/eval_vision.py --gold gold/ --pred predictions/ --csv /tmp/eval.csv   # accuracy
INSIDELABEL_DB=… python tools/queue_predictions.py           # queue recorded scans for review, free
INSIDELABEL_DB=… python tools/leads.py list                  # products seen online, waiting for a real pack (D-089)
INSIDELABEL_DB=… python tools/repro.py list                  # problem reports (D-092); `show <id>` replays one
python tools/compare_ocr.py --csv /tmp/ocr.csv                 # Tesseract vs Cloud Vision on the gold photos (D-093)
```

---

## 5. Session log — 2026-09-25 (one long session)

What was done, in order, with the result. Decisions D-085 → D-089 were added; D-051, D-052, D-055 decided.

1. **Allergen check wired into `/scan`** (D-060/71/72) + `/allergen-check`, `/allergens`. ✅
2. **Wording lint** (D-042) over tables and live output of every endpoint. ✅ Nothing in the current text violated it.
3. **`/compare`** endpoint for shelf comparison (D-057). ✅
4. **INS parser fixed** — the big one. Found: 4-digit INS dropped (1422 → 142), `e`/`ins` matched inside words (*"Tomato paste 250 g"* was flagged **sodium nitrite**), units read as suffixes, `[]`/`{}` brackets and `&` ignored, class words missing, three copies of the logic. On real labels the engine had seen **3 of 12** INS on Britannia and **12 of 20** on Ziggy. Now 100 % on all 6, one parser. ✅
5. **26 additive rows added** (5 more in step 7, 33 verified in all), each checked against the Codex INS list and the FSSAI compendium (Version XXVI, 20.12.2022) and the 2025 amendment. ✅
6. **D-085 scoring:** a `low` additive only costs points with a concern flag. ✅
7. **D-086 FSSAI basis + India/EU/US comparison** (information only, opt-in). Titanium dioxide re-based `high`→`moderate`; foreign-ban wording removed from scores. ✅
8. **Postgres schema** (D-020) with DB-enforced rules; embedded test server. ✅
9. **PostgreSQL 19** installed side by side (D-087) — see failures below. ✅ in the end.
10. **`/scan` persistence**: barcode lookup, review queue, reformulation detection, findings + evidence, `/report`. ✅
11. **Reviewer screen** `/review`, photo storage, `/updates`, 6 real packs queued. ✅
12. **Docs for handover**: `STATE.md` (this), `CLAUDE.md`, README rewrite, RUNBOOK/API_README fixes, memory. ✅
13. **Release gate** `tools/release_check.py` + §11 release plan; last two `verify:true` rows (124, 129) verified. Retailer-scraping idea checked against Amazon/Flipkart terms and FSSAI's 2024 e-commerce advisory → D-088 recommended instead. ✅
14. **Swiggy / Instamart terms read first-hand** (same no-copy clause, manual copying included); Zepto / Blinkit only via search excerpts (pages block scripts). **D-088 accepted; D-089 added** (Sushil's flow: a listing screenshot is a lead, the physical label is the record): migration 005 (`product_leads`, `production_source` on every version, DB refuses to publish a non-label version), `tools/leads.py`, review screen shows provenance and refuses listing-read versions. 8 tests. Applied to the local DB. ✅
15. **D-051 / D-052 / D-055 decided** (delegated by Sushil): claim check ships in shadow behind `INSIDELABEL_CLAIMS_TO_USERS` (1 test); wedge = allergy households + parents; stop rule 30 % / 20 % at W4 on ≥ 50 activated users. ✅
16. **Food categories + picker**: parsed Appendix A Part I (compendium XXVI) into `data/food_categories.json` (271 codes; 16 "Prepared foods" from Part II; PDF spacing fixed; "articulated" → "particulated" per Part II). `migrate` syncs them; `/review` requires a category, with a shortlist whose hints quote each category's Part II description. Release gate counts 7.2.1 / 7.2.2 (not 7.2.3 mixes). 3 tests. ✅
17. **PWA (§8 item 6)** — see the entry below the list. ✅ built; phone test pending.

---

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
  (item 7 — after two failed retakes the app gives tips instead of a promise it can't
  keep); live "found 14" progress (D-068) — the API has no progress events, so the
  app shows elapsed time and "8–15 seconds".

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
1600 px photo (Ziggy), almost the whole scan, against the "8–15 s" the app promises
(D-068). Measured on WSL; check on the deploy host before changing anything.

### Cloud Vision (later on 2026-09-25) — D-093 locked

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
  `async` endpoint, so one 10–15 s scan froze every other request (two parents
  scanning at once would have queued). They now run on worker threads. Both
  properties have tests that fail on the old code.

**Now the only slow step is Gemini, and it varies a lot:** 10.4 s, ~16 s and 28.4 s
on three real calls of the same pack today; app-sized photos (1600 px) didn't help.
Every scan now records `timings.vision_retries` (attempt, wait, error), so the beta
data will show whether that's the model being busy (retries) or slow (none). Don't
tune anything until there are numbers from real scans.

### Gemini keys and setup alarms (later on 2026-09-25)

Three Gemini keys tried in one afternoon (`~/.bashrc` lines 126–128; only the last
counts): the first two worked but `gemini-3.6-flash` and `gemini-3.5-flash` both
answered **503 "high demand"** to our label request (text-only pings got through);
the third answers **402 "prepayment credits are depleted"** — its AI Studio project
needs a top-up. The `gemini-3.5-flash` fallback comparison couldn't run (every call
refused); retry it when Google is quieter.

New: `VisionConfigError` for setup failures (no key, 401/402/403/404, "API key not
valid"). `/scan` answers `503 vision_not_configured` ("isn't available right now"),
logs `SETUP ALARM`, and files a `server` problem report (`vision_config:402`) at most
once an hour. Cloud Vision setup failures (billing, key restriction) raise
`ocr_config:http_403` the same way, since they silently cost ~20 s per scan.
`tools/repro.py list` shows both. Checked against the real 402.

## 6. What went wrong, and what we learned

Keep this list — it is the cheapest way to not repeat a mistake.

| What happened | Lesson |
|---|---|
| `eval_vision.py` reported INS F1 = 1.0 while the parser missed a third of the additives | Gold and prediction go through the **same parser**, so they agree on its blind spots. `tests/test_ins_parsing.py` now checks the parser against the numbers actually printed on each gold label. |
| The FSSAI PDF lists INS numbers (e.g. potassium bromate, azodicarbonamide) in a reference list copied from Codex | Being in that list ≠ permitted. **Permitted means an Appendix A provision** (GMP table or a numeric limit). Always check which part of the document a hit comes from. |
| EUR-Lex and legislation.gov.uk return empty pages to scripts; eCFR's API needs `--compressed`; ecfr.gov web pages redirect | Use the FSAI (Ireland) consolidated PDF for EU text; use `https://www.ecfr.gov/api/versioner/v1/full/<date>/title-21.xml?part=…&section=…` with compression for US. The EU copy we have is consolidated to **2018** — replace it with a current EUR-Lex download (manual, in a browser). |
| `pgserver` (embedded Postgres for tests) lacks `pg_trgm` | Migration files that need an extension start with `-- requires-extension: <name>`; the runner skips them only on the embedded server. |
| `install_pg19.sh` v1 assumed Ubuntu would create the 19 cluster; it doesn't when a cluster already exists | Script now runs `pg_createcluster` itself. |
| Installing `postgresql-19` from apt.postgresql.org **also pulled in `postgresql-18`**, and 16 was then upgraded to 18 (`pg_upgradecluster`, source unconfirmed) | Check `pg_lsclusters` before and after any Postgres apt operation. Data survived (pg_upgrade). |
| Early checks said Postgres wasn't installed, then it was | Re-check the system state before acting on an earlier observation. |
| `pkill -f "<pattern>"` killed its own shell (the command line contained the pattern) | Kill by PID, or use a pattern that can't match the pkill command itself. |
| A PL/pgSQL trigger read `NEW.id` on a table without an `id` column | Separate trigger functions per table; test the trigger on every table it's attached to. |
| Starlette's `TestClient` here has no `auth=` | Send `Authorization: Basic …` as a header. |
| The first release-check run showed "false contradictions 0 of 0 — PASS" | A gate with no data is **unmeasured**, not passed. `release_check.py` reports it as TODO. |
| Several test expectations were wrong the first time (e.g. `322 and 471`) | When a new test fails, decide whether the code or the expectation is wrong before changing either. |
| The first result screen said "39 other ingredients look ordinary" above "All 20 ingredients" (parsed items vs label lines) | Only a rendered screen showed it. Look at the real page, not just the JSON; keep every count on one screen in one unit. |
| `node.append(cond && el(...))` printed the word "false" on the retake screen | The DOM's `append()` stringifies `false`; `el()` skips it. The browser walk-through now fails on stray `false/undefined/null`. |
| A bulk find-and-replace (`view.append(` → `put(`) also rewrote `put`'s own body → infinite recursion | After a scripted replace, read the helper it touched. |
| "Stopped test server" wasn't: `$!` after `( … & )` or `env … &` is a wrapper's PID, and the real uvicorn kept running on 8765 | After starting anything in the background, read the real PID from `ps` (not `pgrep -f`, which matches its own shell) and confirm it's gone after `kill`. |
| An e2e step "failed" because the test's barcode had a wrong check digit — the app was right to refuse it | When a test fails, read the screen before touching code. |
| The trail's photo events showed as `image/jpeg` — `record("photo", {type: …})` overwrote the event type | Spread the caller's data first, then the fixed keys: `{...data, t, type}`. |
| Cloud Vision "missed" 5 Ziggy additives it had read perfectly — a newline sat between "Acidity Regulators" and "(330, 270)" | When a reader misses something, look at its raw text before blaming the reader. |
| A test for "the server stays responsive during a scan" passed on the old, blocking code: a blocked event loop also froze the test's own `sleep`, so it timed the wrong thing | Run every new test against the old code once. A test that can't fail proves nothing. |
| `/docs` answered 422: Swagger's Try it out fills every text box with "string" (avoid=string → unknown allergen) | Give form fields empty examples; treat "" as absent. Check the real `/docs` page, not just the JSON schema. |
| Headless Chromium on this box lacks `libnss3`/`libnspr4`/`libasound2` | `apt-get download` + `dpkg -x` into a scratch dir + `LD_LIBRARY_PATH` — no sudo needed. |

---

## 7. Open decisions (need Sushil)

- **D-053** premium pricing — ₹399–499/year recommended.
- **D-054** the "100% ATTA" ruling on Patanjali — decide before any rule fires.
- **D-082** what Premium is for — interviews only.
- Concern levels on the 35 verified rows are judgement calls (e.g. sorbitol `low`) — review before launch.

---

## 8. Next steps — the road to the closed beta (in order)

Run `python tools/release_check.py` (add `INSIDELABEL_DB=…` for catalogue gates)
to see where each gate stands. §11 has the full list.

1. ~~Decide D-051, D-052, D-055~~ — done 2026-09-25 (shadow claims; allergy + parents; 30 % / 20 % stop rule).
2. **Grow the gold set to ≥ 20 labels** (RUNBOOK) — a third in bad conditions, and
   include packs whose front says "no added sugar" / "no preservatives" / "made with
   real X", or the false-contradiction gate stays unmeasured. Only Sushil can do this.
3. **Lift ingredient match from 0.945 to ≥ 0.95** — look at the per-label misses in
   `eval_vision.py` once the gold set is bigger (Britannia is the weakest at 0.80).
4. ~~Product category in the reviewer screen~~ — done: 271 FSSAI categories
   (`data/food_categories.json`) loaded on every migrate; `/review` requires one.
5. **Seed and review 50 SKUs**, 15 kids' biscuits first (D-058); start with the 6 queued.
   Use the D-089 flow: `tools/leads.py add` for each product spotted online →
   buy the pack → `obtained` → scan front + back with its barcode → `link --barcode` →
   publish on `/review` (the lead closes itself).
6. **PWA front end** — built (`web/`, `/app/`). D-090 (stack) and D-091 (server-built screen)
   accepted 2026-09-25. Left: **test on a low-end Android phone** — the camera
   needs HTTPS (or `localhost` via `adb reverse tcp:8000 tcp:8000`); PNG icons (192/512) for
   the Play build — Bubblewrap can generate them from `web/icon.svg`. Share target stays
   after W4 (D-077/D-083; when built, a shared listing becomes a lead, never a record — D-089).
7. **"Send it to us" endpoint** (D-070) — the queue kind exists; nothing creates it yet.
8. **Individual reviewer logins**; **D-080 photo retention** (must skip `scans.evidence_hold`, D-092);
   rate limit on `/scan` and `/problem`; Sentry optional now that D-092 covers reproduction;
   ~~28 s OCR cross-check~~ — fixed by D-093 (4 s). **Deploy needs `GOOGLE_VISION_KEY` as a secret**
   (without it the server quietly falls back to Tesseract); **store Cloud Vision's text on the
   scan row** so D-092 replays don't call Google again; name Cloud Vision in the privacy policy.
9. **Trust pages** (D-076): privacy policy (DPDP, parental consent), COI policy, methodology,
   who is behind it.
10. **Deploy** (week 10): host with PostgreSQL 19, HTTPS, R2 with a 30-day lifecycle rule, backups.
11. **Play closed testing** (D-011) — check the current tester requirement in Play Console.

Later / not blocking the beta: D-073 cheap Tesseract re-check; refresh EU rows from a
current EUR-Lex text and check cyclamate's US status; drop PG18 after PG19 GA.

---

## 9. Timeline anchors

- Beta: 15-week plan, Sep–Dec 2026 (blueprint §16). Wave 1 accepted with a ~3-week slip → **W4 retention answer late December 2026** (D-084).
- Beta gate: ≥30 % W4 retention with ≥2.5 scans per returning user; ≥95 % ingredient match on seeded categories; <1 % false-positive contradictions; **0 allergen misses** on the gold set.
- Deploy (R2 lifecycle, host) — week 10.
- Wave 2 (share target, WhatsApp card) only after the W4 number (D-083).

---

## 10. Where things are

| Path | What |
|---|---|
| `STATE.md` | this file — status, setup, next |
| `DECISIONS.md` | every decision with its reason (append-only) |
| `insidelabel-blueprint.md` | product & engineering blueprint v1.1 |
| `API_README.md` | endpoints, database, reviewer screen, regulator comparison |
| `RUNBOOK.md` | how to photograph, transcribe and score a gold batch |
| `CLAUDE.md` | working rules for AI coding sessions |
| `src/insidelabel/` | the package (core, extraction, reliability, claims, lenses, db, review, api) |
| `data/` | the knowledge tables — the moat |
| `migrations/` | Postgres schema, plain SQL, applied in order |
| `tests/` | 193 tests (+ `regression/problems/`, D-092); `conftest.py` gives each DB test module its own database |
| `tools/` | release gate, leads (D-089), eval, batch scan, gold stubs, queue predictions, PG19 installer |
| `gold/`, `photos/`, `predictions/` | 6 real labels: hand transcription, photos, recorded model output |
| `research/` | private marketplace screenshots behind leads (git-ignored; never published — D-089) |
| `archive/prototype/` | the pre-package prototype, kept for history |
| `web/` | the PWA (D-090): `app.js` views, `lib.js` storage/API, `camera.js` barcodes, `sw.js` |
| `prototype.jsx` | early UI prototype (still shows a numeric score — superseded by D-064) |

---

## 11. Release plan — closed beta with every validation

"Release" here means the **closed beta on Play** (D-007): 50–100 users, a 4-week
retention test. Public launch comes after the W4 number (D-083).

### Computed gates — `tools/release_check.py` (exit 1 until all pass)

| Gate | Threshold (blueprint §15) | 2026-09-25 |
|---|---|---|
| Gold set size | ≥ 20 labels, a third in bad conditions | ❌ 6 |
| Hallucinated INS numbers | 0 | ✅ 0 |
| Verdict flips gold vs model | 0 | ✅ 0 |
| Ingredient match | ≥ 95 % | ❌ 94.5 % |
| Allergen misses | 0 | ✅ 0 (6 labels × 11 allergens) |
| False contradictions | < 1 % | ⏳ unmeasured — no gold claim matches a rule yet |
| Every gold INS has a table row | all | ✅ |
| Additive rows still `verify:true` | 0 | ✅ 0 |
| D-051, D-052, D-055 decided | locked | ✅ locked 2026-09-25 |
| Published catalogue | ≥ 50 SKUs | ❌ 0 (6 waiting) |
| Kids' biscuits published (D-058) | ≥ 15 in 7.2.1 / 7.2.2 | ❌ 0 (category picker ready) |
| Test suite (`--with-tests`) | green | ✅ 193 |

### Manual gates — tick when done

- [ ] PWA built ✅ (`web/`) and tested on a low-end Android phone ⏳ (camera, barcode, result, profiles, compare, report)
- [ ] Share target (if D-088 accepted)
- [ ] "Send it to us" endpoint
- [ ] Individual reviewer logins
- [ ] Photo retention 30 days (D-080)
- [ ] Rate limit on `/scan` and `/problem`; error monitoring ✅ built in (D-092), Sentry optional
- [ ] Privacy policy (DPDP; children's data; parental consent at profile creation)
- [ ] COI policy, methodology, who is behind the app, "last verified" dates (D-076)
- [ ] Deployed: PostgreSQL 19, HTTPS, R2, backups tested by restoring one
- [ ] Play Console: account verified, closed-testing requirement met, audience = adults
- [x] D-055 stop number written down before launch (continue ≥ 30 %, retest 20–30 %, stop < 20 %)

### Where the catalogue comes from (D-088, D-089 — locked)

Not from scraping Flipkart / Amazon / Blinkit / Swiggy / Zepto: their terms forbid
automated *and* manual copying (Amazon, Flipkart, Swiggy and Instamart read
first-hand; Zepto and Blinkit only via search excerpts, since their pages block
scripts — see D-088), and FSSAI's 2024 advisory exists because listings
often don't match the pack. Instead: photograph real packs (D-058); let users share
listing screenshots into the app (D-077, pulled into the beta) so they go through
review; use Open Food Facts only to choose which packs to buy (ODbL — don't ingest);
ask GS1 India about brand-supplied product data.

Screenshots Sushil collects are **leads**, not sources (D-089):

```
screenshot → identify product → obtain the pack → photograph front + back
           → OCR (/scan) → review → InsideLabel product record
```

`tools/leads.py` tracks each lead (`needs_primary_source` → `pack_obtained` →
`label_captured` → `published`, or `abandoned` with a reason) and keeps the
screenshot privately in `research/` by content hash. Keep it to a working list of
products to buy — not a bulk archive of listings, and never copy listing text into a record.

