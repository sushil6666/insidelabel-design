# InsideLabel

Reads the front and back of an Indian packaged-food label and tells you what is
in it — and where the front of the pack disagrees with the ingredient list.

**AI reads the label; deterministic rules over our data tables judge it**
(D-004). Every judgement uses FSSAI rules (D-086) and is traceable to a table
row and to the label's own words. The data tables and the reviewed catalogue are
the moat; the code is thin.

> **New here, or starting a new session? Read [`STATE.md`](STATE.md) first** —
> what works, how to set up, what failed, what's next.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                  # 135 tests, no database or API key needed
python tools/release_check.py              # how far from the closed beta

# try the engine on any ingredient list
python -m insidelabel.core.engine "Refined wheat flour, Sugar, Palm oil, INS 471, INS 621, Added flavours"

# run the API (docs at http://127.0.0.1:8000/docs)
uvicorn insidelabel.api.main:app --reload
```

Full setup — PostgreSQL 19, Tesseract, environment variables, the reviewer
screen — is in [`STATE.md` §3](STATE.md#3-set-up-from-scratch-wsl-ubuntu-2404).

## Documents

| Document | Read it for |
|---|---|
| [`STATE.md`](STATE.md) | current status, setup, daily commands, lessons learned, next steps |
| [`DECISIONS.md`](DECISIONS.md) | every product/engineering decision and its reason (append-only) |
| [`insidelabel-blueprint.md`](insidelabel-blueprint.md) | the product and engineering blueprint (v1.1) |
| [`API_README.md`](API_README.md) | endpoints, database, reviewer screen, regulator comparison |
| [`RUNBOOK.md`](RUNBOOK.md) | how to photograph, transcribe and score a batch of real labels |
| [`CLAUDE.md`](CLAUDE.md) | working rules for AI coding sessions |

## How a result is built

```
photo(s) ──► Gemini reads the label ──► Tesseract cross-checks INS numbers
                      │
                      ▼
      reliability gate (refuses bad reads; never "clean" on a partial read)
                      │
                      ▼
 engine: tokenize → classify (additives.json, nova_markers.json) → verdict
                      │
      ┌───────────────┼──────────────────┬───────────────────┐
      ▼               ▼                  ▼                   ▼
  allergens      claim check       shelf comparison    India/EU/US (optional,
  (first line)   (front vs back)   (2–4 packs)          information only)
```

With a database configured, each scan becomes a version **waiting for review**;
a person checks it against the photo on `/review` before it enters the
catalogue, after which a barcode alone returns the result instantly.

## The data tables

| File | What it is | Who owns correctness |
|---|---|---|
| `data/additives.json` | INS additives: class, concern, why, FSSAI status and basis | **Verify every status against FSSAI Appendix A** |
| `data/nova_markers.json` | NOVA Group-4 ultra-processing markers | academic, stable |
| `data/normalization.json` | synonyms, sugar aliases, additive class words | extend from real labels |
| `data/allergens.json` | FSSAI reg. 5(14) allergen categories + Indian aliases | verify category list before launch |
| `data/claim_rules.json` | front-of-pack claim → contradicting ingredient fact | two open questions in its `_meta` |
| `data/regulatory_status.json` | India vs EU vs US status, per document | only verified rows go in |

## ⚠ Before any public "permitted / not permitted" statement

A status is only as good as its source. Check it against the current FSSAI Food
Additives Regulations (Appendix A — the GMP table or a numeric limit) and record
`fssai_basis` and `verified_on` on the row. A number that appears only in the
regulation's INS reference list is **not** permitted. A wrong "not permitted in
India" statement is a legal liability, not just a bug.

## Known limits (honest)

- 66 additives in the table; anything else on a label is seen but not flagged
  (and the result says an absence of flags is not proof of absence).
- Ingredient list only: the nutrition panel (sugar/salt/fat amounts) is not read yet.
- The accuracy set is 6 real labels; the target before trusting it is 20–30.
- The score is an internal ranking aid only; users see findings, not a number (D-064).
