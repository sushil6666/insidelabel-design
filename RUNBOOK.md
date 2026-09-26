# Runbook - your first real batch

Goal: 20-30 photographed products, hand-transcribed, scored. At the end you
have one number that means something and a ranked list of what to fix.

Budget roughly 6-8 hours of your time, most of it transcription. There is no
shortcut around that part; see step 4.

---

## Step 0 - Check the setup (5 min)

The one-time tidy (stale root tables, strays, old predictions →
`predictions_archive/`) was done in September 2026; `cleanup.sh` is kept only
as a record. Keep `predictions_archive/` out of the eval path - those files came
from older prompt versions and carry no `_model` stamp.

Confirm everything still passes before you shoot anything:

```bash
source .venv/bin/activate
pytest -q                     # 135 passing as of 2026-09-25
python tools/release_check.py # where the beta release gates stand
```

---

## Step 1 - Decide the product list (30 min)

Aim for 20-30. Pick for COVERAGE, not convenience. Each row below tests
something the others do not:

| What you need | Why |
|---|---|
| 3-4 with front-of-pack claims ("no added sugar", "no preservatives", "made with real X") | The claim checker has NEVER run on a real label. Highest-value gap. |
| 3-4 foil packets (namkeen, chips, wafers) | Reflective, crumpled. Hardest surface. Untested. |
| 2-3 pouches (curved, flexible) | Text curving away from the lens. |
| 3-4 biscuits / bakery | Long ingredient lists, many additives. |
| 2-3 instant noodles / ready-to-eat | Multi-component lists ("Noodles:" / "Tastemaker:"). |
| 2-3 dairy / beverages | Short lists; tests false CLEAN. |
| 2-3 "health" positioned products | Where claims and reality diverge most. |
| 2-3 genuinely simple (roasted nuts, plain atta) | If these don't come out CLEAN, the engine is over-flagging. |

Deliberately include products whose additives you expect to be missing from
`additives.json` - 472e, 965, 450, 503, 508 are known gaps. You want to see how
a miss presents to a user.

---

## Step 2 - Shoot (60-90 min)

Two images per product. Name them exactly:

```
photos/<id>-back.jpg
photos/<id>-front.jpg
```

`<id>` is lowercase, hyphenated, and stable - `britannia-nutrichoice-sugarfree`,
not `IMG_2043`. It is the key linking photo, gold and prediction.

**Back = the ingredient list.** Fill the frame with the panel. This is the only
required image.

**Front = the marketing face.** Whatever a shopper sees first.

Deliberately shoot **a third of the set in bad conditions**: shop lighting,
angled, glare on foil, a pack you have not flattened. A set of thirty clean
photos will report high accuracy and tell you nothing about a user standing in
a kirana store. The bad third is the informative third.

Do NOT retake a photo because the model read it badly. That is the measurement.

---

## Step 3 - Create empty gold stubs (5 min)

```bash
for id in $(ls photos/*-back.* | sed 's|photos/||; s|-back\..*||'); do
  python3 tools/new_gold.py --id "$id"
done
```

Empty on purpose. Read the checklist it prints.

---

## Step 4 - Transcribe by hand (3-5 hours - the actual work)

Fill each `gold/<id>.json` **from the photo, before running any scan.**

The rule: **for every field, be able to point at the pixels.**

Three gold errors were made on the first two labels of this project, all the
same shape - recording what the pack MEANS rather than what it PRINTS:

- `net_quantity: "2000 ml"` - derived by multiplying 200 ml × 10 servings. The
  pack prints no total.
- `back_identity.brand: "Limca"` - inferred because it is a Limca bottle. The
  back label carries no Limca wordmark at all.
- `product.name: "Limca Lime 'N' Lemoni"` - assembled from a wordmark and a
  separate descriptor. That string appears nowhere on the pack.

Each is a reasonable description and none is a transcription. If you cannot
point at it, the value is `null` and the reason goes in `extraction_notes`.

**Do not look at the model's prediction first.** Once you have seen
`LEMON ADDED` you cannot unsee it, and your transcription drifts toward it.
Gold built by correcting model output agrees with the model by construction and
measures nothing.

Two people transcribing the same 5 labels independently, then comparing, is the
cheapest way to find out how reliable your own gold is. Worth doing for a
subset if anyone can help.

---

## Step 5 - Scan (10 min of waiting)

```bash
python3 tools/batch_scan.py --photos photos/ --out predictions/
```

Skips ids already scanned. The summary table has a `gold` column - anything
reading `NO` is unmeasured.

---

## Step 6 - Score

```bash
python3 tools/eval_vision.py --gold gold/ --pred predictions/ --csv reports/eval.csv
```

Read the output in this order. The first three are correctness; the rest is
diagnosis.

1. **HALLUCINATED INS NUMBERS** - must be zero. Any entry is a fact with no
   source on a real pack. Stop and fix the prompt before anything else.
2. **MOST-DROPPED INS NUMBERS** - which additives get lost, and on which packs.
3. **FLAG SET CHANGED** - the receipts shown to a user being wrong, even when
   the headline verdict survives.
4. **SCORE DRIFT ≥ 10** - errors large enough to move a grade band.
5. **VERDICT-CHANGING ERROR RATE** - coarse; moves last.
6. **PRODUCT IDENTITY / FRONT CLAIM F1** - a mismatch is as likely to be your
   gold as the model. Check the pack before assuming.

---

## Step 7 - Find the table gaps

```bash
python3 tools/coverage_report.py <(for f in predictions/*.json; do \
  python3 -c "import json,sys;d=json.load(open('$f'));print(json.dumps({'code':'$f','product_name':d.get('product',{}).get('name'),'ingredients_text':', '.join(d.get('ingredients',[])),'off_additives_tags':[],'off_nova_group':None}))"; done)
```

The unmatched-token list is your demand-driven to-do for `additives.json` -
ranked by how often real labels actually contain them, rather than guessed.

---

## Step 8 - Decide, don't drift

Write down, in one page:

- the hallucination count (must be 0)
- the drop rate for INS numbers, split by **photo quality** (your bad third vs
  the clean two-thirds)
- how many verdicts you personally disagree with, reading the label yourself
- the additives that came up and are not in the tables

That last one is the honest test the README set: *are the verdicts accurate and
consistent on real products?* If you would not show a stranger the verdicts on
these 30, the answer is not yet, and the next move is table work rather than an
app.

---

## Step 9 - Send the batch to review (the catalogue)

Once gold is final and the eval is recorded, queue the batch so the packs become
real catalogue entries. It replays the recorded predictions with their photos -
no vision calls, no cost:

```bash
INSIDELABEL_DB="postgresql:///insidelabel?host=/var/run/postgresql" \
  python tools/queue_predictions.py --ids <id> <id> ...
```

Then review them on `/review` (see `API_README.md`). Your gold transcription is
the reference: correct the pre-filled list to match the pack, and publish.

---

## What NOT to do during this batch

- **Don't tune the prompt mid-batch.** Half your results become incomparable.
  Collect all 30, then change one thing, then re-run all 30.
- **Don't fix gold after seeing a mismatch** unless you have re-read the pack
  and the pack agrees with the model. Otherwise you are fitting gold to output.
- **Don't average renders with photos.** `limca-pet-1l` is a vector render;
  either drop it or report the two populations separately.
- **Don't build the frontend yet.** The number that changes the UI most -
  nutrition - is not in the score.
