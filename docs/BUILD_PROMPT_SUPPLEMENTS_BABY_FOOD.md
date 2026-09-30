# Build prompt: health supplements and baby food (beta)

Written 2026-09-30 for a fresh Claude Code session in this repo. Paste the block below as the
first message. Sushil's words that set it: "Supplements and Baby food will go once claude code
done" (2026-09-29) and "give the claude code part to implement supplements and baby food part,
part of beta" (2026-09-30). Order agreed in chat on 2026-09-29: supplements first, then baby food;
skincare and baby care (lotions, wipes) later as their own line (CDSCO and BIS, INCI names).

Before pasting, note for Sushil:
- **Timing (D-083, D-084).** "Do not build features during the beta" still stands, so this must
  land before the first cohort starts, or wait for the W4 number. It moves the beta date.
- **Phase 0 is research only.** It ends with proposals (RECOMMENDED D-entries). Nothing is built
  until you say "accepted", the same way D-132 went through its review first.
- **Baby food has a legal question only a person can settle.** The Infant Milk Substitutes Act
  1992 forbids "promotion" of infant foods, defined as "to employ directly or indirectly any
  method of encouraging any person to purchase or use" them. Ranking, "better choice", Compare
  and the shop list could all count. The prompt keeps them off for infant foods; releasing
  infant-food results at all needs your decision, ideally after a lawyer reads it.
- **Paid reads.** Each new gold label is one Gemini read (about 50 paise) plus a Cloud Vision
  read. The prompt asks before any.

```text
You are working in the InsideLabel repo (/home/insightstack/insidelabel). Start by reading
CLAUDE.md, STATE.md section 8 ("NEXT SESSION STARTS HERE"), docs/BUILD_PROMPT_SUPPLEMENTS_BABY_FOOD.md
(this file) and DECISIONS.md D-002, D-004, D-042, D-046, D-052, D-058, D-060, D-071, D-074, D-083,
D-086, D-091, D-092, D-111, D-116, D-123, D-125, D-132 to D-134, D-137. Run
`source .venv/bin/activate && pytest -q` and check the count against STATE.md's header before
changing anything.

GOAL
Two new kinds of pack in the beta, both FSSAI-regulated food, so most of the engine carries over:
- Health supplements and nutraceuticals (FSSAI category 13.6 and the Nutra Regulations 2022).
- Baby food: infant formula and complementary foods for infants (categories 13.1 and 13.2, the
  Foods for Infant Nutrition Regulations 2020).
Each gets: a rule that decides the kind of pack from what is printed, the parts of the result
that apply to it (and the parts that don't), checks from its own regulation, data tables with
fssai_basis and verified_on, review and catalogue support, and gold labels to measure it.
Food for special medical purposes (13.1.3, 13.3) is out of scope: say "used under medical
supervision", show allergens, nothing else.

RULES YOU MUST NOT BREAK (CLAUDE.md; tests enforce most of them)
- AI reads, rules judge (D-004). Gemini only transcribes, now also the pack's statements (below).
  The kind of pack, every check and every sentence are rules in Python over data/*.json.
- Every sentence a user reads comes from a primary source read first-hand this session (D-046):
  title, URL, page, read_on. If no source says it, the app doesn't. Report gaps to Sushil.
- Wording (D-042, D-071): never unhealthy, healthy, safe, harmful, toxic, dangerous, free from,
  misleading, illegal, violation; never judge the brand. When a pack lacks a statement its
  regulation asks for, quote the regulation and say what we did or didn't find on the photos;
  say it only on a complete read of both faces. tests/test_wording.py covers every new string.
- No em dash or en dash in any file (tests/test_no_dashes.py); in Python write "\u2013".
- FSSAI decides permitted or not (D-086). Allergens stay the first key and first on screen (D-060),
  for every kind of pack. All result text is built in lenses/screen.py (D-091); web/ only renders.
- Scans stay replayable (D-092): a changed prompt gets a new PROMPT_VERSION; older recorded answers
  (no statements, no kind) must parse and replay unchanged, as ordinary food.
- D-116 extends, it isn't replaced: a pack with no FSSAI licence and only a drug licence (AYUSH or
  any other) is not food under the FSS Act 3(1)(j) and stays out of the catalogue. Many vitamin
  and calcium tablets in India are sold as drugs: check the licence, never the shape.
- Data in data/*.json; schema changes in a new migrations/NNN_*.sql. One INS parser: core/tokenize.py.
- Don't copy SafeLabel, TruthIn or any other app; competitors are context only.
- Ask Sushil before any paid Gemini or Cloud Vision call and say the cost. Tests use `replay`.
  Never touch the uvicorn on port 8000. Never overwrite reports/ or predictions/. Use the session
  scratchpad; PDFs go there, extracted with pypdf in a scratch venv, not the project's.
- Branch per phase; `git branch --show-current` before every commit; push and give
  https://github.com/sushil6666/InsideLabel/pull/new/<branch>. Every new decision is RECOMMENDED
  until Sushil says "accepted". Keep STATE.md section 8 current.

SOURCES (found and opened 2026-09-30; re-open each and quote exactly; pages as noted)
- FSS (Health Supplements, Nutraceuticals, Food for Special Dietary Use, Food for Special Medical
  Purpose, and Prebiotic and Probiotic Food) Regulations 2022, as Annexure 1 of FSSAI's direction:
  https://fssai.gov.in/docs/food-law/regulations/Direction_New_compressed.pdf
  (pages are the annexure's own "Page N of 76"). Seen: p1 scope, "intended for population above the
  age of 2 years"; p4 vitamin and mineral levels "shall not exceed RDA specified by ICMR" where FSSAI
  sets none, and additives from Annexure 3 plus the Appendix A GMP table; p5 products for children
  of 2 to 5 years "only under medical advice"; p5 to p6 regulation 12, label statements: the
  category words on the front, "NOT FOR MEDICINAL USE", recommended usage level, duration of usage,
  "Not to exceed the recommended daily usage", "stored out of reach of children", nutrients as % of
  RDA; p7 and p9 a nutrient claim needs 30% of RDA and no more than one RDA; p10 and p12 statements
  about pregnant and lactating women, children under 5 and the elderly (find which category each
  belongs to); from about p24 the schedule of plants with part, usage range and notes such as
  "Not recommended during pregnancy". FIRST: confirm the regulations' current legal status (a
  direction first; later gazette notification and amendments) from FSSAI's own pages. fssai.gov.in
  is a JavaScript site: if a page won't load by script, ask Sushil for the link or a download.
- FSS (Foods for Infant Nutrition) Regulations 2020, compendium Version II (04.01.2024):
  https://fssai.gov.in/docs/food-law/regulations/Comp_IFR_VERSION-II_04_01_2024.pdf
  (PDF pages). Seen: p2 definitions and general requirements; p3 3(6) sucrose and fructose not added
  unless needed, together at most 20% of total carbohydrate; p3 3(8) compliance with the IMS Act
  1992 "including aspect related to advertisement, marketing and promotion"; p4 "MOTHER'S MILK IS
  BEST FOR YOUR BABY" on the front in letters of at least 5 mm; p5 additives declared by name and
  class; p6 no picture of an infant or woman, and the words "Humanised", "Maternalised", "Full
  Protein Food", "Energy Food", "Completer Food" (sic, as printed), "Health Food" not used; p7 hydrogenated oils and fats
  not used in infant formula; p11 infant formula additive table; p13 and p19 no hydrogenated fats in
  cereal-based complementary foods, and honey or maple syrup processed to destroy Clostridium
  botulinum spores; p16 and p21 further additive tables; p25 follow-up formula: no partially
  hydrogenated fats, trans fatty acids at most 3% of total fatty acids; p30 foods based on
  traditional ingredients. Read the whole compendium: each product type has its own composition
  table.
- Infant Milk Substitutes, Feeding Bottles and Infant Foods (Regulation of Production, Supply and
  Distribution) Act 1992, as amended 2003: India Code, https://www.indiacode.nic.in/handle/123456789/1958
  (it timed out from this machine on 2026-09-30; ask Sushil to download the PDF by hand). Read
  section 2 (definitions of infant, infant food, advertisement, promotion) and sections 3 to 10.
  Seen in a secondary copy only (BPNI), so quote nothing until India Code's text is read:
  "promotion" means "to employ directly or indirectly any method of encouraging any person to
  purchase or use infant milk substitute, feeding bottle or infant food"; educational material on
  infant feeding meant to reach mothers "shall include clear information relating to the benefits
  and superiority of breastfeeding".
- WHO Guideline for complementary feeding of infants and young children 6 to 23 months of age
  (2023): https://iris.who.int/server/api/core/bitstreams/5abca011-4db2-4cf1-b959-45b756f7b600/content
  (recommendations also at https://www.ncbi.nlm.nih.gov/books/NBK596423/). Not yet read first-hand.
- ICMR-NIN, Nutrient Requirements for Indians 2020 (RDA, EAR and tolerable upper levels): the
  RDA the Nutra Regulations point to. Find it on nin.res.in; not yet read.
- ICMR-NIN, Dietary Guidelines for Indians 2024 (already in data/ingredient_notes.json): find its
  pages on infant and young child feeding and on supplements.
- FSS Act 2006 section 3(1)(j), already read for D-116 (drugs and medicinal products are not food).

PHASE 0: read and propose (branch categories-research). No app code.
Write docs/SUPPLEMENTS.md and docs/BABY_FOOD.md from the sources above, each with:
1. The kind-of-pack rule: which printed words decide it (the category words on a supplement's
   front; "MOTHER'S MILK IS BEST FOR YOUR BABY"; an age such as "from 6 months"; a declared FSSAI
   category; the catalogue's 13.1, 13.2 or 13.6), in what order, and what happens when they
   disagree. Plus the licence rule (D-116 extended).
2. Which parts of today's result apply. Recommended starting point, to check against the sources:
   - Supplements: allergens (first), the ingredient list, additives against the Nutra Regulations'
     own additive list, the plant schedule's notes, amounts per daily usage against ICMR-NIN's RDA
     and FSSAI's one-RDA level, the label statements of regulation 12. No A to E grade and no NOVA
     count (fillers such as INS 460, 470, 551 would read as "industrial" in a capsule), no sugar
     answer unless the pack is a food format (gummies, powders). Compare only between supplements.
   - Baby food: allergens (first), the ingredient list, additives against the infant regulation's
     tables for that product type, hydrogenated fat as a "not permitted" finding with D-111's care
     (complete read, confidence 0.95, quote, ask to check, goes to a reviewer), the label
     statements of p4 to p6, the nutrition table (D-133) against the regulation's composition table
     where the pack prints the same nutrient. **No grade, no ranking, no "better choice", no
     Compare, no shop list, no share card** for any infant food, because of the IMS Act. Propose
     the line about breastfeeding the Act asks of material on infant feeding, from the Act and WHO.
3. Every data table the build needs, row shape and first rows, each with fssai_basis (or source)
   and verified_on: data/pack_kinds.json (what applies per kind), data/nutra_rules.json (statements,
   RDA levels), data/nutra_botanicals.json (the schedule, only rows whose notes a user would read),
   data/infant_rules.json (statements, forbidden words, product types, composition limits the
   label can show), data/infant_additives.json (per product type).
4. Profiles: a "baby" age band for under 2 (D-074 keeps profiles to ref, age, avoid; a new band is
   a value, not a field). What changes for a baby profile on an ordinary food, only where WHO 2023
   or ICMR-NIN says it (for example added sugar and salt for 6 to 23 months).
5. What no source says, so the app won't. What needs a person (lawyer, doctor, Sushil).
Record the proposals as D-139 (supplements) and D-140 (baby food), RECOMMENDED, each with the
questions for Sushil. PR, then STOP until he says "accepted" (or edits).

PHASE 1: kind of pack (branch pack-kind), after D-139 and D-140 are accepted
- Prompt: a new `pack_statements` list, copied verbatim with the face it is on (the category words,
  NOT FOR MEDICINAL USE, usage level and duration, age statements, warnings, MOTHER'S MILK IS BEST
  FOR YOUR BABY), and the licences as printed (FSSAI, drug). Transcription only. New PROMPT_VERSION.
- A rule module (e.g. src/insidelabel/core/pack_kind.py) over data/pack_kinds.json decides
  `food | supplement | infant | special_medical | not_food`, with the evidence it used. /scan
  returns it; screen.py switches parts on and off from pack_kinds.json, never with if-chains in JS.
- An ordinary food must come out exactly as today: the six gold labels unchanged, as a test.
- Catalogue: the version records the kind; /review shows it with its evidence; the review checker
  flags a pack whose printed kind and chosen category disagree. A not_food pack is rejected with
  D-116's reason.

PHASE 2: supplements (branch supplements)
Build D-139 as accepted: its tables, checks and screen words; tiles for plant notes (D-134 shape,
kind `supplement`); amounts per daily usage beside ICMR-NIN's RDA with the source; regulation 12
statements found or not found. Nothing changes for other kinds.

PHASE 3: baby food (branch baby-food)
Build D-140 as accepted. Compare, the shop list and any ranking refuse an infant food on the
server, with a test for each route, not only a hidden button. Allergens first, as always.

EACH BUILD PHASE ALSO
- Invented labels as tests (a multivitamin tablet, a protein powder, a gummy, an infant formula, a
  cereal-based complementary food, a traditional ingredient mix), before and after, and the six gold
  labels unchanged.
- Gold: ask Sushil to photograph at least 3 supplements and 3 baby foods (one of each in poor light),
  transcribe blind with tools/new_gold.py (docs/GOLD_SET_PLAN.md), and ask before the paid reads.
- Walk it in headless Chromium, light and dark, at 390 x 844, from answers made by the real server
  code with replay (Playwright in a scratch venv; libnss3, libnspr4, libasound2t64 via apt-get
  download + dpkg -x and LD_LIBRARY_PATH; a scratch uvicorn on a port other than 8000, stopped by
  PID). Bump APP_VERSION (web/lib.js) and VERSION (web/sw.js) together when web/ changes.
- Ends with: full pytest green; wording and dash tests green; DECISIONS.md and STATE.md updated; the
  PR link; the list of anything you couldn't source. Then stop and wait for Sushil's merge and
  phone check before the next phase.
```
