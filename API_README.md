# InsideLabel — API v0.1

> Status, full setup and next steps: [`STATE.md`](STATE.md).

Wraps the engine (`src/insidelabel/core/`). Every change to engine logic or to
`data/*.json` is recorded in `DECISIONS.md` (e.g. D-085 scoring, D-086 FSSAI basis).

## Run

```bash
pip install -r requirements.txt
pip install -e . && uvicorn insidelabel.api.main:app --reload
```

## Endpoints

| Route | Status | What it does |
|---|---|---|
| `GET /health` | live | table load counts |
| `POST /analyze` | live | `{raw_ingredients}` → engine verdict, verbatim |
| `POST /claim-check` | live | text + `front_claims[]` → verdict + contradiction pairs |
| `POST /scan` | live | images → vision → engine → claim check. Optional `avoid=milk,gluten` puts an `allergens` block first (D-060) |

> **D-051:** `/scan` stores the claim check but returns `claim_check.reason = "claims_not_released"` to users until `INSIDELABEL_CLAIMS_TO_USERS=on`. `/claim-check` is a developer tool and always returns the full result.
| `GET /allergens` | live | allergen codes a profile can avoid |
| `POST /allergen-check` | live | ingredients + statement + `avoid[]` → five-state result (D-071), text-only |
| `POST /compare` | live | 2–4 scanned packs + age + `avoid[]` → best pick of these, with reasons (D-057) |
| `GET /regulators`, `GET /regulators/{ins}` | live | India vs EU vs US status per additive, information only (D-086) |
| `GET /updates` | live (needs DB) | `?device_id=` → this install's packs that review has decided (D-070) |
| `GET /review` | live (needs DB + token) | reviewer screen, HTTP Basic |
| `POST /report` | live (needs DB) | "Report a mistake": `{scan_id, field, proposed_value?, note?}` → correction + review queue (D-076) |
| `GET /app/` | live | the PWA (`web/`, D-090); `/` redirects here |
| `POST /send-to-us` | live (needs DB) | "Send it to us" after two refused scans: `{device_id, scan_ids[]}` (this install's own, all refused, ≥ 2) → one `send_to_us` review item with every attempt's photos, held past retention; `/updates` reports back (D-070, D-096) |
| `POST /problem` | live (needs DB) | "Report a problem" / app crash: `{kind, comment?, request_id?, scan_id?, client, events[]}` → problem report (D-092) |

## The result screen and profiles (D-060–D-066, D-074, D-091)

`/scan` returns a `screen` block next to `allergens` (which stays the first key).
It is what the app renders, in order, and every sentence in it passes the wording
lint:

| Key | What |
|---|---|
| `state` | `result`, or `retake` on a refused (422) scan |
| `people` | one line per profile with an avoid list or a child's age band: `{ref, status, line, allergens[], child_facts[]}` |
| `headline` | one finding `{text, source}`; `source` names the row it came from (D-061) |
| `band` | `{code, label, note}` with the D-063 names; `note` explains NOVA on `ultra-processed` |
| `checked`, `scope` | what was checked (D-062) |
| `claims` | released claim-check rows only (D-051); `[]` in shadow |
| `worth_knowing` | moderate/high additives, industrial ingredients, sugar under ≥ 2 names |
| `ordinary` | `{count, text, additives[]}`: none/low items grouped (D-065) |
| `retake` | a prompt naming the problem (D-036), or `null` |
| `last_verified`, `recheck` | catalogue hits only (D-073) |

There is no score in `screen` (D-064); `verdict.score` stays for admin use.

Send profiles as the form field `profiles`, JSON:
`[{"ref": "me", "age": "adult", "avoid": ["peanut"]}, {"ref": "p1", "age": "toddler", "avoid": ["milk"]}]`.
At most 3; `age` is `adult`, `toddler`, `kid` or `young`; any other key (a name,
say) is refused with 422 `bad_profiles`. Profile text uses the placeholder
`{name}`, which the device replaces with the nickname it keeps; `ref: "me"`
reads "you/your". With `profiles` and no `avoid`, the top-level `allergens`
block covers every profile's avoid list.

## The PWA (D-010, D-090)

Static files in `web/`, served at `/app/` by the API (override with
`INSIDELABEL_WEB`). No build step. Flow: barcode (camera `BarcodeDetector`, or
type the digits) → catalogue hit, or 404 `not_in_catalogue` → back photo (resized
to 1600 px on the phone) → result. Also: household profiles with parental consent
(nicknames in `localStorage` only), compare via `/compare`, "Report a mistake" via
`/report`, and `/updates` checked on open. The service worker caches only `/app/`
files, never API answers.

## Reproducing problems (D-092)

Every response carries `X-Request-ID` (the client's own if it sent a plain id,
else a new UUID); error bodies repeat it as `request_id`; `/health` reports
`build` (git commit, or `INSIDELABEL_BUILD` at deploy) and `data_version`
(hash of `data/*.json`). Each scan row keeps the model's raw answer, the request
options, versions and timings (migration 006) and the Cloud Vision text of the
back photo (`ocr`, migration 007), so `tools/repro.py show <id>` can replay it
exactly, without calling Google, even after the photo is gone:

```bash
INSIDELABEL_DB=… python tools/repro.py list          # open reports
INSIDELABEL_DB=… python tools/repro.py show 12       # trail + versions + replay + diff
INSIDELABEL_DB=… python tools/repro.py show 12 --save name   # → tests/regression/problems/
INSIDELABEL_DB=… python tools/repro.py close 12 fixed --note "…"
```

An exception no handler caught returns `500 {error: "server_error", request_id}`
and is stored as a `server` report with its traceback.

**Setup alarms.** When Gemini refuses for a reason only we can fix (no key, key
rejected 401/403, prepaid credit used up 402, model not available 404),
`/scan` answers `503 {error: "vision_not_configured", retryable: false}` with a plain
message, logs `SETUP ALARM vision_config:<status>`, and files a `server` report at
most once an hour. A busy model (429/5xx) is still retried and answers
`503 vision_unavailable`. Cloud Vision setup failures don't fail the scan (it falls
back to Tesseract) but file `ocr_config:<status>` the same way.

## Rate limits (D-095)

`/scan` and `/problem` are limited per install (`device_id`) **and** per IP, checked
before any photo is read or model called. Over a limit: `429 {error:
"rate_limited", detail, retryable: true, retry_after_s, request_id}` plus a
`Retry-After` header; the PWA shows `detail`. Starting values (`ratelimit.RULES`):

| Bucket | Per install | Per IP |
|---|---|---|
| `scan` (photos, a model call) | 20 / 10 min, 100 / day | 60 / 10 min, 400 / day |
| `lookup` (barcode only) | 120 / 10 min | 600 / 10 min |
| `problem` | 10 / hour | 60 / hour |

Counters are in memory, per process: right for one server process, wrong for
several (move them to Postgres/Redis first). Behind a reverse proxy set
`INSIDELABEL_PROXY_HOPS=<n>` so the client address is read from `X-Forwarded-For`;
otherwise the header is ignored. A refused request is not stored as a scan.

## Scans and the catalogue (D-024, D-028)

Set `INSIDELABEL_DB` to store scans; without it the API stores nothing and
behaves as before.

```bash
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" uvicorn insidelabel.api.main:app --reload
```

`/scan` takes two optional form fields: `barcode` (EAN/UPC digits) and
`device_id` (anonymous install UUID).

| Client sends | What happens |
|---|---|
| barcode only | Catalogue lookup, no vision call. Reviewed pack → result with `catalogue.last_verified`; otherwise **404 `not_in_catalogue`** (ask for a photo). |
| photo (± barcode) | Always read. Stored as a version **waiting for review** and queued (`new_product`); an identical waiting version is reused. Same barcode, different ingredient list from the published one → queued as `reformulation`; the old version keeps serving until review. |
| refused / vision error | Recorded as a scan with its outcome, for the retention numbers. |

Every stored finding has evidence pointing at the label's own words (D-043);
front claims are stored only when the claim check ran on a trusted pairing
(D-035). A database error is logged but never costs the user their result.
Reviewers publish with `SELECT publish_version(<id>, '<name>')` and pull work
with `SELECT * FROM claim_next_review('<name>')`.

## Database (D-020)

Postgres is the app's source of truth; DuckDB + dbt read nightly Parquet
exports for analytics (D-021) and never sit in the request path.

```bash
sudo PG19_PORT=5432 bash tools/install_pg19.sh      # once (D-087); pg_trgm included
python -m insidelabel.db.migrate postgresql://USER:PASS@localhost/insidelabel
```

Migrations are plain SQL in `migrations/`, applied once each. Rules the
database enforces: one current version per product and only after review
(D-026, D-028), no finding without evidence from the same version (D-043),
citations must be verified (D-045), at most 3 nameless profiles (D-074).
Only a version read from a physical label can be published, and a marketplace
lead (`product_leads`) can only be closed by such a version (D-089, migration 005;
run leads with `tools/leads.py`).
`tests/test_db.py` runs them on an embedded Postgres (`pip install -e .[dev]`);
set `INSIDELABEL_TEST_PG` to a full server's URI to include `pg_trgm`.

Local setup (WSL, done 2026-09-25, D-087): PostgreSQL 19 (beta until GA) on
port 5432 as the default; PostgreSQL 18 on 5433 as a fallback. Role
`insightstack` with CREATEDB on both, peer auth over the socket (no password).
Installed with `sudo PG19_PORT=5432 bash tools/install_pg19.sh`. Until 19 GA,
treat the 19 databases as disposable: if a new beta/RC won't start the
cluster, recreate it and re-run the migrations.

```bash
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"
INSIDELABEL_TEST_PG="postgresql:///insidelabel_test?host=/var/run/postgresql" pytest tests/test_db.py
```

The test fixture drops and recreates the schema of the test database on each
run, and refuses any database whose name does not end in `_test`.

## Reviewer screen (D-028)

The only path from a scan to the public catalogue. Open `/review` in a browser.

```bash
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \
INSIDELABEL_REVIEW_TOKEN="choose-a-long-secret" \
uvicorn insidelabel.api.main:app --reload
# browser: http://127.0.0.1:8000/review — username = your name, password = the token
```

- **Take the next item** claims the oldest open item; nobody else can decide it
  until you publish, reject or put it back.
- Left: the stored pack photos. Right: what was read, pre-filled and editable —
  fix it to match the pixels, then **Publish to catalogue**. Findings are rebuilt
  from your corrected list.
- A new product or reformulation publishes the waiting version; a reported
  mistake on a published pack publishes a *new* version (history kept, D-026);
  an unreadable "send it to us" scan is published from your transcription (D-070).
- Reformulations show a line diff against the published version.
- Reject needs a reason; it is kept with the decision.
- **Food category is required** to publish: the FSSAI Appendix A code (e.g. `7.2.1`
  for sweet biscuits, `15.1` for chips/namkeen, `14.1.4.1` for sodas). A shortlist
  sits above the full list of 271. Categories come from `data/food_categories.json`
  and are synced by `python -m insidelabel.db.migrate`.
- The page says whether the version was read from the physical label or a listing,
  and lists any marketplace leads behind it (D-089). Listing-read versions can't publish.

Photos are stored under `INSIDELABEL_MEDIA` (default `./media`, git-ignored).
`GET /updates?device_id=…` tells the app which of its packs are ready (D-070).
`python tools/queue_predictions.py` queues the recorded scans in `predictions/`
with their photos, for free.

## India vs EU vs US (D-086)

Verdicts and scores use FSSAI rules only. Pass `compare_regulators: true` to
`/analyze` (JSON) or `compare_regulators=true` to `/scan` (form) to add a
`regulators` block: for each additive found, how India, the EU and the US treat
it, with sources. It is information only and never changes `verdict`.
`GET /regulators` lists every compared additive; `GET /regulators/{ins}` returns
one (404 if not compared yet). Data: `data/regulatory_status.json`.

## Allergen gate (D-072)

`/scan` interprets allergens only when the scan is reliable
(`verdict_safe_to_display`), the ingredient list is complete, and
`confidence.ingredients` ≥ 0.95. Otherwise every requested allergen is
`cannot_confirm`, including on a refused (422) scan, so the client always has
an answer for the first line of the result.

## Wording lint (D-042)

`tests/test_wording.py` fails the build if consumer text contains forbidden
words (misleading, illegal, toxic, safe, free from, …). It checks the
consumer fields of `data/*.json` and the live output of every endpoint.

## The empty-input guard

`engine.analyze("")` returns **score 100, grade A, binary "clean"** — correct for
the engine (no flags, no penalties), and the most dangerous thing this API could
emit. It makes *"we could not read the label"* indistinguishable from *"this
product is clean"*.

Every path into the engine calls `guard_ingredients()` first and returns **422**
rather than a verdict when no ingredient tokens parse. The engine is not
modified; the refusal happens above it.

## Files

| File | What it is |
|---|---|
| `src/insidelabel/core/` | engine: tokenize (the only INS parser), classify, score |
| `data/*.json` | the knowledge tables: additives, allergens, NOVA, claim rules, regulator comparison |
| `src/insidelabel/extraction/providers/` | Gemini vision prompt + call, independent OCR cross-check |
| `src/insidelabel/reliability/gates.py` | decides whether a verdict may be shown |
| `src/insidelabel/claims/checker.py` | front-of-pack claim checker |
| `src/insidelabel/lenses/` | allergens, shelf comparison, India vs EU vs US |
| `src/insidelabel/api/main.py` | routes + guards |
| `src/insidelabel/db/migrate.py`, `migrations/` | Postgres schema and runner |

## Two things to decide before this ships publicly

Both are recorded in `data/claim_rules.json` under `_meta`:

1. **maltodextrin vs "no added sugar."** It is in `normalization.json`'s
   `added_sugar` list because that list drives the *hidden-sugar heuristic*,
   which is deliberately broader than the legal definition. Maltodextrin is a
   polysaccharide, not a sugar under Codex/FSSAI added-sugar definitions, so
   contradicting a legal claim with it is weak ground. It is parked in
   `added_sugar_adjacent` and reported as a separate `adjacent_facts` row, never
   as a contradiction. Confirm against FSSAI's definition.
2. **fruit juice concentrate.** A free sugar under WHO, disputed by
   manufacturers. Currently treated as a direct contradiction.
