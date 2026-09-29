# Build prompt: D-132, D-133, D-134

Written 2026-09-29 for a fresh Claude Code session in this repo. Paste the block below as the
first message. Sushil's words that decided it: "keep all 15 rows now ... implement all"
(2026-09-29). Context: the ingredient-notes review in chat that day; STATE.md section 8.

```text
You are working in the InsideLabel repo (/home/insightstack/insidelabel). Start by reading CLAUDE.md,
STATE.md section 8 ("NEXT SESSION STARTS HERE") and DECISIONS.md D-004, D-042, D-046, D-060, D-071,
D-086, D-091, D-092, D-120, D-123, D-125, D-130, D-131. Run `source .venv/bin/activate && pytest -q`
(expect 603 passed, 8 skipped, 1 xfailed) before changing anything.

GOAL
Three accepted decisions (Sushil, 2026-09-29, "keep all 15 rows now ... implement all"). Record each
in DECISIONS.md as LOCKED with that quote, then build them in the phases below:
- D-132 "Ingredients worth knowing": all 15 rows of the ingredient-notes review (table below).
- D-133 Read the nutrition table on the back and judge it against ICMR-NIN's own thresholds.
- D-134 One-screen result: compact warning tiles; each tile opens a detail page. Nothing else is
  open by default.

RULES YOU MUST NOT BREAK (from CLAUDE.md; tests enforce most of them)
- AI reads, rules judge (D-004). Gemini only transcribes: ingredients, and now the nutrition table.
  Every judgement is a rule in Python over data/*.json.
- Every sentence a user reads comes from a primary source read first-hand this session (D-046):
  the document itself, with title, URL, page, read_on date. Never from memory or a summary. If no
  primary source says something, the app does not say it. Report the gap to Sushil.
- Wording (D-042, D-071): never "unhealthy", "safe", "healthy", "toxic", "dangerous", "free from";
  never judge the brand. Say what the ingredient is, where it sits in the list, what the source
  says. tests/test_wording.py must stay green and must cover every new string.
- No em dash or en dash in any file (tests/test_no_dashes.py).
- FSSAI decides permitted or not permitted; EU and US status never changes a verdict (D-086).
- Allergens stay the first key of /scan and the first thing on screen (D-060).
- All result-screen text is built in src/insidelabel/lenses/screen.py (D-091). web/ only renders
  the `screen` block. Never compose findings in JS.
- Scans stay replayable (D-092): new request fields go into the trace and into repro.form_for.
  A changed Gemini prompt gets a new PROMPT_VERSION.
- Data changes go in data/*.json, never hard-coded. Schema changes are a new migrations/NNN_*.sql.
- One INS parser: core/tokenize.py.
- Ask Sushil before any paid Gemini or Cloud Vision call, and say the cost. Tests use `replay`.
- Never touch the uvicorn on port 8000. Never overwrite reports/. Use the session scratchpad.
- Work on a branch per phase; push and give https://github.com/sushil6666/InsideLabel/pull/new/<branch>.
  Check with `git branch --show-current` before every commit (a detached HEAD lost a commit before).
  Keep STATE.md section 8 current at the end of each phase.

SOURCES ALREADY READ (use them, re-open to quote exactly; printed page = PDF page minus 17)
- ICMR-NIN, Dietary Guidelines for Indians 2024: https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf
  p.51 trans fats; p.55 hydrogenated fat, "vegetable shortening"; p.56 limit ghee/butter, avoid
  vanaspati; p.66 refined carbohydrates, glycemic index; p.91 caffeine 300 mg/day; p.93 HFSS,
  saturated fats incl. palm and coconut oil, salt >5 g/day high; p.94 sugar >25 g/day high, added
  sugars list, "children should avoid sugar substitutes", foods high in salt; p.96 Table 15.1
  thresholds; p.97-98 Table 15.2 (maida in Group B, refined flours in Group C); p.108-109 labels,
  partially hydrogenated oils "should not be acceptable", hidden sugars in "sugar free" foods.
- WHO fats and carbohydrates 2023: https://www.who.int/news/item/17-07-2023-who-updates-guidelines-on-fats-and-carbohydrates
- WHO sugars 2015: https://www.who.int/news/item/04-03-2015-who-calls-on-countries-to-reduce-sugars-intake-among-adults-and-children
- WHO sodium fact sheet: https://www.who.int/news-room/fact-sheets/detail/salt-reduction
- WHO non-sugar sweeteners 2023 (already in data/additive_research.json).
STILL TO READ FIRST-HAND: FSSAI Labelling and Display Regulations 2020 (which nutrition values are
mandatory, exemptions, added sugars, sodium), FSSAI standards for khandsari/bura/mishri and
margarine/bakery fat, and any FSSAI rule on naming the oil. Download PDFs with curl into the
scratchpad and extract text with pypdf (install it in a scratch venv, not the project).

PHASE 1: D-132 ingredient notes (branch ingredient-notes)
Create data/ingredient_notes.json, one row per group, same discipline as data/additive_research.json:
{id, title, names[], kind, summary[] (1-3 plain sentences), sources[{title,url,page,read_on}],
position_rule, children_only, reviewed_by}. Add tests/test_ingredient_notes.py: every row has
sources and passes the wording lint; names don't collide with sugar_aliases or allergens. The 15 rows:
 1 maida / refined wheat flour: tile when in the first 3 ingredients, else a details line.
 2 other refined flours, corn flour, starch: same rule as 1.
 3 sooji / rava / semolina: NO source found yet calls it refined. Find one; if none, ship a neutral
   fact only ("Sooji is milled wheat") with no tile, and tell Sushil.
 4 palm oil / palmolein: saturated fat tile (ICMR p.93, WHO 2023).
 5 hydrogenated fat / vanaspati / shortening: its own tile, strongest of the list (ICMR p.51, p.55,
   p.109; WHO trans fat 1%). Add "vegetable shortening", "bakery shortening", "shortening" to names.
   Keep the NOVA marker too.
 6 coconut oil: saturated fat tile (ICMR p.93, WHO).
 7 ghee / butter: details line quoting ICMR p.56 (Sushil wants it kept; no alarm tone).
 8 margarine / bakery fat: needs a source (FSSAI); report if none.
 9 unnamed "edible vegetable oil": neutral line "The oil isn't named on the pack", once FSSAI's
   naming rule is read.
10 sugar: add ICMR p.94 and WHO 2015 lines to the existing sugar details. No new flag.
11 khandsari, bura, mishri, coconut sugar: add to sugar_aliases only with FSSAI's definition read;
   re-run the gold set and report what moves (like D-120).
12 sweeteners and children: children's view line for any sweetener incl. sugar alcohols (ICMR p.94).
13 salt: details line now (ICMR p.93-94, WHO); the numbers come in phase 2.
14 caffeine: details line with ICMR p.91 for adults; a children's line only with a source.
15 nutrition table: phase 2.
Wire it into core/engine.py (matching via core/tokenize.py and normalization.json) and
lenses/screen.py. Information only: NO score change in this phase. Show before/after on the six
gold labels and invented labels, as tests.

PHASE 2: D-133 nutrition table (branch nutrition-panel)
- Read FSSAI L&D 2020 first; write docs/NUTRITION_PANEL.md: mandatory fields, exemptions, units.
- Gemini prompt: transcribe the nutrition table verbatim (nutrient, value, unit, basis per 100 g/ml
  and per serving, serving size, servings per pack). New PROMPT_VERSION and schema fields; an
  answer without the table still parses (older recorded answers must replay).
- If no table is in the back photo, the app asks for one more photo of it (reuse the D-119 parts flow).
- Rules (new module, e.g. src/insidelabel/lenses/nutrition.py): every number must appear in Cloud
  Vision's text of the same photo; per serving x servings ~ per 100; sugars <= carbohydrates;
  saturated <= total fat; sodium vs salt (salt = sodium x 2.5). Any failure: that number is not
  shown ("We couldn't read the nutrition table clearly").
- Thresholds from ICMR-NIN Table 15.1 in data/nutrition_thresholds.json with page and read_on:
  solids per 100 g 250 kcal, 625 mg salt, 3 g added sugar, 4.2 g added fat; liquids per 100 ml
  70 kcal, 175 mg, 2.0 g, 1.5 g. Daily: added sugar 25 g (ICMR p.94), salt 5 g (ICMR p.93, WHO).
  Panels print total fat, not added fat: do not apply the added-fat threshold to total fat; show
  saturated and trans fat against WHO instead. Trans fat > 0 gets a tile.
- Screen: "Added sugar: 18 g per 100 g. ICMR-NIN counts more than 3 g per 100 g as high." and
  "One serving (30 g) has 5.4 g added sugar, about a fifth of the 25 g a day ICMR-NIN counts as
  high." Adults only unless a source gives children's figures.
- Store the numbers on the catalogue version (new migration); /review shows them beside the photo
  for the reviewer to confirm; publish records them. Review checker: a panel number not in Cloud
  Vision's text sends the item to a person.
- Gold set: add the nutrition table to each gold label; tools/eval_vision.py reports panel accuracy;
  tools/release_check.py gets a gate "nutrition numbers read correctly >= 98%" (TODO when no data).
- Information only; propose any score rule separately as RECOMMENDED.

PHASE 3: D-134 one-screen result (branch result-tiles)
- screen.py returns a compact `tiles` list (allergen line stays first, separate): each tile
  {id, kind: not_permitted|additive|ingredient|nutrition, title, chip, tone} and a `details` map
  keyed by tile id: what_it_is, what_research_found[], who_it_concerns (only if the source says),
  on_the_label, sources[].
- First screen fits a 390 x 844 phone without scrolling for a pack with 2 warnings: allergen line,
  headline, tiles, the three answer chips (tap opens the sentence), At a glance, buttons (Compare,
  Add to shop list, Report a mistake). Everything else in one closed "More about this pack".
- Tapping a tile opens #/result/<id>/look/<tile id>, a separate page with a back arrow.
- Keep old fields for older app versions. Bump APP_VERSION (web/lib.js) and VERSION (web/sw.js)
  together. Walk it in headless Chromium (Playwright in a scratch venv; libs via apt-get download
  + dpkg -x, see STATE lessons) against answers generated by the real server code with replay, light
  and dark, and read the screenshots.

EACH PHASE ENDS WITH: full pytest green; wording and dash tests green; DECISIONS.md and STATE.md
updated; PR link to Sushil; a list of rows or numbers you could not source. Then stop and wait for
his merge and phone check before the next phase.
```

## What is still needed to complete the beta (2026-09-29)

Failing or unmeasured release gates (`tools/release_check.py`):
1. Test set: 6 labels, needs 20 (proposal: build from packs a person published on `/review`).
2. Ingredient match 94.5%, needs 95%: diagnose the misses on the 6 labels.
3. False contradictions: unmeasured; needs test packs with "no added sugar" / "no preservatives" claims.
4. Catalogue gates: run the check against the server's database.
5. Nutrition table accuracy (new with D-133).

Manual (STATE.md section 11):
6. Whole app walked on a phone, including the screenshot flow and "Scan it now".
7. "Send it to us" tried on a phone.
8. Privacy page DRAFT banner removed after the DPDP review.
9. Conflict-of-interest and methodology pages, who is behind the app, "last verified" dates (D-076).
10. `INSIDELABEL_PROXY_HOPS` confirmed on the server.
11. Invite-only on; codes T01 to T05 sent.
12. Play Console (D-011), only if the beta goes to the Play Store.

Only Sushil:
13. Billing off the free trial (the one real blocker).
14. A DPDP reviewer.
15. Gemini key restriction and the two older keys.
16. `insidelabel.in` client hold (not needed for the beta).
17. Candzey: hard or chewy.
18. Testers' feedback (`il tools/beta.py feedback`).

Not needed for the beta: D-117's 30 agreements (only before the review agents publish on their own).
