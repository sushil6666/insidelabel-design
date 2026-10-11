# CLAUDE.md

InsideLabel: an Indian packaged-food label checker. Python 3.12 + FastAPI +
PostgreSQL 19. Solo founder: Sushil.

## Start here

1. Read `STATE.md` (status, setup, open items, lessons) and skim `DECISIONS.md`.
2. `source .venv/bin/activate && pytest -q` - expect 1325 passing (8 skipped, 1 xfailed) before you change anything
   (a cloud session: 1324 and 9 skipped, no gold photos; Tesseract and pytesseract must be installed).
   `python tools/release_check.py` shows how far the beta is from release.
3. The "Next" list in `STATE.md` §8 is the default work queue.
4. The live site (https://insidelabel.ai, Google Cloud, D-114): `OPERATIONS.md` to run it,
   `DEPLOY.md` to build it. Code reaches it only through `main` and `deploy/update.sh`.

## Rules that are easy to break

- **AI reads, rules judge (D-004).** Never let a model output become a verdict,
  score or concern level directly.
- **FSSAI basis only (D-086).** EU/US status is information-only
  (`data/regulatory_status.json`); it must never change a score, verdict or
  `concern`. A test enforces this.
- **Wording (D-042/D-071).** User-facing text never says misleading, false,
  illegal, violation, toxic, dangerous, poison, safe, free from, healthy - and
  never judges the brand. `tests/test_wording.py` checks tables and live output.
  Quote the label; don't characterise it.
- **Legal facts come from primary documents, never memory (D-046).** For an
  additive: Codex CAC/GL 36 for name/class; FSSAI compendium **Appendix A** for
  permission (GMP table or a numeric limit). A number that appears only in the
  FSSAI INS *reference list* is **not permitted**. Record `fssai_basis` and
  `verified_on` on the row.
- **OCR cross-check = Cloud Vision, Tesseract fallback (D-093).** `GOOGLE_VISION_KEY` lives in
  the environment only - never in a file in this repo. It only ever *adds* a known additive.
- **One INS parser:** `core/tokenize.py` (`INS_RE`, `prefix_bare_ins`,
  `extract_ins`, `ins_numbers`). Don't write another regex for INS numbers anywhere;
  `tests/test_ins_parsing.py` fails on any 3-4 digit pattern outside it (D-099).
- **Claim check is in shadow (D-051).** `/scan` computes and stores it; users get
  `reason: "claims_not_released"` unless `INSIDELABEL_CLAIMS_TO_USERS=on`. Don't route
  around `_user_claim_check()` in `api/main.py`.
- **Allergens are the first key** of every `/scan` response (D-060); never output
  "free from"/"safe"; below confidence 0.95 or on a partial read → `cannot_confirm`.
- **The catalogue is reviewed data.** Scans create `pending_review` versions; only
  `ReviewService.approve()` (→ `publish_version()`) publishes: a person on `/review`, or, under
  D-117, the review agents when every check passes and publishing is switched on. Don't add
  another path. Every published version records `drafted_by` and `verified_by`.
- **Result-screen text is built in `lenses/screen.py` (D-091).** The PWA (`web/`)
  renders `/scan`'s `screen` block; don't compose findings in JS, never read `score`
  there, and never send a profile nickname (`profiles` = ref/age/avoid only, D-074).
- **Scans must stay replayable (D-092).** Any new `/scan` outcome passes `trace=tr` to the
  store; never drop the model's raw answer. Debug a report with `tools/repro.py show <id>`
  before touching code, and `--save` it so it becomes a regression test. The one
  exception: a request refused *before anything is read* (429 rate limit, D-095; 403
  `replay_disabled`, D-101) is logged with its request id, not stored.
- **`replay` is off on servers (D-101).** Only `INSIDELABEL_ALLOW_REPLAY=on` or in-process
  `main.REPLAY_ALLOWED = True` (repro, tools, tests via `conftest.py`) accept it. Never
  set it on the public deploy.
- **`DECISIONS.md` is append-only.** New decision = new `D-0xx` entry; reversal =
  mark `SUPERSEDED` and add a new one. Record who accepted it.
- **No scraping or copying retailer listings** (Amazon, Flipkart, Blinkit, Zepto, Swiggy) -
  their terms forbid it (D-088). A listing screenshot is a **lead** (`product_leads`,
  `tools/leads.py`), never a source: the record is read from the physical pack (D-089),
  and the DB refuses to publish a version whose `production_source` isn't `physical_label`. Open Food Facts is ODbL: test input and prioritisation only, not catalogue rows.
- **No em dash or en dash anywhere** (Sushil, 2026-09-26): use `-`, `:` or "to".
  `tests/test_no_dashes.py` checks every tracked file. To match one in label text,
  write the escape (`"\u2013"`).
- **No barcode, no catalogue entry (D-107).** A scan without one gets its result and an
  `unlisted` scan row only; never create a product, version or review item for it.
- **Barcodes are never typed (D-104).** Camera scanner or a photo read by `/check-photo`
  (zxing-cpp on the server); every barcode passes `barcode.check()` (GS1 rules, D-103).
- **A gate with no data is TODO, never PASS** (`tools/release_check.py`).
- **Don't overwrite `reports/`** when re-running eval - write to a scratch path unless asked.

## Commands

```bash
pytest -q                                   # all tests, embedded Postgres (pgserver)
INSIDELABEL_TEST_PG="postgresql:///insidelabel_test?host=/var/run/postgresql" pytest -q
python -m insidelabel.db.migrate "postgresql:///insidelabel?host=/var/run/postgresql"
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \
  uvicorn insidelabel.api.main:app --reload     # /review logins: tools/reviewers.py (D-097)
python tools/eval_vision.py --gold gold/ --pred predictions/ --csv <scratch>/eval.csv
INSIDELABEL_DB=… python tools/release_check.py --with-tests     # beta release gate
INSIDELABEL_DB=… python tools/health_report.py --out <scratch>/health.json   # snapshot for the health report page
```

## Code conventions

- Match the surrounding style: explanatory module docstrings that say *why*,
  comments citing decision numbers (`# D-043: …`).
- Data changes go in `data/*.json`, not code. New additive rows copy the existing
  row shape and include `fssai_basis` + `verified_on`.
- Schema changes are a new `migrations/NNN_*.sql` file - never edit an applied one.
  A file needing an extension starts with `-- requires-extension: <name>`.
- DB tests use the `fresh_db` fixture (`tests/conftest.py`); they refuse to run on
  any database not named `*_test`.
- Storage is optional: code paths that touch the DB go through `_persist()` in
  `api/main.py` so a DB failure never costs the user their result.

## Environment gotchas (this WSL box)

- Postgres: 19beta4 on **5432** (default), 18 on 5433 (fallback). Peer auth as
  `insightstack`; no password. Check `pg_lsclusters` before/after any apt Postgres work.
- Admin commands need `sudo` - ask Sushil to run them (suggest the `!` prefix).
- EUR-Lex blocks scripted downloads; use the FSAI consolidated PDF or ask for a
  manual download. eCFR API needs `curl --compressed`.
- `pkill -f` can match its own shell - kill by PID.
- Another `uvicorn --reload` may already be running (Sushil's); don't kill it.
