# Health supplements and nutraceuticals: what the app would do (D-139, phase 0)

Written 2026-09-30 from primary documents read that day (D-046). **Accepted by Sushil 2026-09-30 (D-139
LOCKED, with his choices recorded there: amounts beside the RDA, never "one RDA" as a limit; men and women
side by side; the protein-powder note as quoted).**
Every sentence here that the app would show is marked "User text" and quotes a source; everything
else is working notes for the build. The companion file is `docs/BABY_FOOD.md` (D-140); the
kind-of-pack rule and `data/pack_kinds.json` are shared and written out once, here.

## 0. The legal status, first (read from FSSAI's own pages, 2026-09-30)

- FSSAI's regulations page (https://fssai.gov.in/food-law/regulations, rendered in a browser,
  2026-09-30) lists, as item 6, the **FSS (Health Supplements, Nutraceuticals, Food for Special
  Dietary Use, Food for Special Medical Purpose, Functional Food and Novel Food) Regulations, 2016**
  with its regulation, compendium, one amendment (6 September 2021) and a "Direction (18 Oct 2022)".
- That direction (https://fssai.gov.in/docs/food-law/regulations/Direction_New_compressed.pdf, the
  file the build prompt names) bundles three documents, then the text as Annexure 1:
  - **29 March 2022**, direction under section 16(5): the 2022 regulations "are in the process of
    draft publication and its final notifications are likely to take more time. Therefore, it has
    been decided to operationalize the provisions of these regulations as enclosed at Annexure 1
    with effect from 1st April 2022", and they "shall supersede" the 2016 regulations.
  - **10 May 2022**, order: some additives (ammonium acetate, cross carmellose sodium, sodium starch
    glycolate and others) allowed at GMP; Schedule III enzymes and proteins allowed in health
    supplements.
  - **18 October 2022**, direction under 18(2)(d) with 16(5): "As the finalization of these draft
    regulations, 2022 is likely to take some more time before being notified, it has been decided
    to re-operationalize the provisions of these regulations ... with effect from 1st October 2022."
- FSSAI's notifications list (1,355 entries, searched for "Nutra" and "Health Supplement",
  2026-09-30) has the **draft** 2022 regulations of 29 June 2022 and nothing later: **no final
  gazette notification of the 2022 regulations.** The advisories list has no direction newer than
  the 18 October 2022 one (published 28 November 2022).

So the text the app would quote is **the FSS (Nutra) Regulations, 2022 as operationalised by
FSSAI's direction of 18 October 2022**, and every citation says so. Whether a 2022 direction under
16(5) still binds in 2026 is a legal question the documents don't answer; it is in section 8.

## 1. Sources read first-hand (2026-09-30)

| Source | Where | Used for |
|---|---|---|
| FSS (Nutra) Regulations 2022, Annexure 1 of the direction above | pages are the annexure's "Page N of 76" (PDF page = N + 3) | scope 2(1) to 2(7) p. 1 to 2; definitions 3 p. 2; general requirements 5 p. 3 to 7; labelling 5(12) p. 5 to 6; claims 5(13) p. 6; health supplements 6(1) p. 7 to 8; nutraceuticals 6(2) p. 8 to 9; FSDU 6(3) p. 9 to 12; FSMP 6(4) p. 12 to 15; pre/probiotic 6(5) p. 15 to 16; Schedule I p. 17 to 22; Schedule II (plants) p. 23 to 55; Schedule III p. 56 to 65; Schedule IV p. 66 to 67; Annexure 3 additives p. 68 to 75 |
| The three covering documents (29 Mar, 10 May, 18 Oct 2022) | same PDF, pages 1 to 3 (scanned; read from the images) | legal status |
| ICMR-NIN, Short Summary Report, Nutrient Requirements for Indians: RDA and EAR (2020, revised 2024) | https://www.nin.res.in/RDA_short_Report_2024.html (ICMR-NIN's page embeds it as a Google Drive file; read in the viewer, downloads are off) | A2 RDA p. 30; A5 other minerals p. 31; A6 tolerable upper limits p. 32 (printed page numbers) |
| ICMR-NIN, Dietary Guidelines for Indians 2024 | https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf (printed = PDF minus 17) | protein powders pp. 59 to 61 |
| FSS (Labelling and Display) Regulations 2020, compendium I | https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Display_23_09_2021.pdf | 5(3)(c)(xiii), PDF p. 12: FSDU and FSMP exempt from the nutrition table |
| FSS (Labelling and Display) First Amendment Regulations, 2026 (Gazette) | https://fssai.gov.in/docs/food-law/notice-comment/69cca2b3f3ce9Notification%20dt%2024.03.2026_NRC.pdf | comes into force 1 July 2027; replaces (xiii) with "Health supplements, Nutraceuticals and Foods for Special Dietary Uses (FSDU) in tablet, pills and capsule format, with respect to macronutrients, when sources of energy are insignificant" |
| FSS Act 2006, 3(1)(j) | https://fssai.gov.in/upload/uploadfiles/files/FOOD-ACT.pdf | "food" excludes "drugs and medicinal products" (D-116) |
| FSS (FPS&FA) Regulations 2011, Appendix A food categories | already in `data/food_categories.json` (13.5 dietetic foods, 13.6 food supplements) | catalogue categories |

**Corrections to the build prompt, from the text:** the label statements are regulation **5(12)**,
not "regulation 12". The statement that a product "is not to be used by pregnant, nursing and
lactating women or children under 5 years, adolescents and elderly, except when medically advised"
belongs to **Food for Special Dietary Use** (6(3)(f)(ii)(A)) and a similar one to **Food for
Sportsperson** (3.1.2(b)(ii)(A)); health supplements and nutraceuticals have no such line. And the
"one RDA" limit sits inside the nutrient-claim sentence of 6(1)(c)(i) (section 4.4).

## 2. The kind of pack

### 2.1 The words that decide it (read by the model, judged by `core/pack_kind.py`)

The model only copies what is printed (`pack_statements`, each with its face; `licences` as printed,
section 6). The rule then looks, in this order:

1. **Licence (D-116, extended).** No FSSAI licence number on a complete read of both faces **and**
   a non-FSSAI manufacturing licence printed (for example "Mfg. Lic. No.", "Drug Lic. No.",
   "Ayurvedic Medicine") gives `not_food`. An FSSAI licence decides "food" whatever else is
   printed (D-116: "When a pack prints both licences, the FSSAI one decides"). A partial read never
   gives `not_food`: the kind stays `unknown` and the result says what it can (allergens).
   Why it matters here: the Nutra Regulations 2(4) say these products "shall not include a drug as
   defined in clauses (a), (b) and (h) of section 3 of the Drugs and Cosmetics Act, 1940", and
   many vitamin, calcium and iron tablets in India are sold as drugs. The shape of the product
   (tablet, capsule) never decides.
2. **Infant words** (docs/BABY_FOOD.md section 2) win over everything below: a pack with "MOTHER'S
   MILK IS BEST FOR YOUR BABY" is `infant` even if it also says "supplement" (Nutra Regulations 2(1)
   note 1: "Foods intended for infants up to the age of 2 years shall comply with FSS (Food for
   Infant Nutrition) Regulations, 2020").
3. **Medical words** give `special_medical`: "FOOD FOR SPECIAL MEDICAL PURPOSE", "RECOMMENDED TO BE
   USED UNDER MEDICAL ADVICE ONLY" (6(4)(f)(i)(A)), "For the dietary management of" (6(4)(f)(i)(B)),
   and "FOOD FOR SPECIAL DIETARY USE" (6(3)(f)(i)(A); see 2.3).
4. **Supplement words** give `supplement`: the category words of 5(12)(a)(i)(A), "HEALTH SUPPLEMENT"
   or "NUTRACEUTICAL", "in capital and bold letters in the immediate proximity of the name or brand
   name", and the alternatives 6(1)(f)(ii) allows, "Dietary supplements or Food supplements".
   "NOT FOR MEDICINAL USE" (5(12)(a)(ii)(A)) is supporting evidence only: alone, it doesn't decide.
5. **The catalogue's category** for a published pack: 13.6 gives `supplement`, 13.3 or 13.4 or 13.5
   `special_medical`. A printed kind and a chosen category that disagree go to a reviewer (phase 1).
6. Otherwise `food`: today's result, unchanged.

"PREBIOTIC FOOD" and "PROBIOTIC FOOD" (5(12)(a)(i)(A)) stay `food` in this proposal: they are
usually ordinary formats (a curd, a drink) and the food result fits them. Question 5 in section 8.

When the words disagree (a pack prints "HEALTH SUPPLEMENT" and the catalogue says 7.2.1 biscuits),
the printed words decide the result and the disagreement goes to a reviewer; the result carries the
evidence it used (`kind.evidence`: the statement, its face, the rule).

### 2.2 Delivery format

5(1)(a) lists "powders, granules, tablets, capsules, liquids, semi solids, drops, pills, gummies,
jelly, chewable and mouth dissolving strips, bars, biscuits, candies". The format is read from the
pack's words (the name, "Each tablet contains", "per capsule", "per scoop") and decides only two
things: whether the additive list is Annexure 3's tablet/capsule/syrup list or the 13.6 list
(6(1)(e)), and whether the sugar answer shows (a gummy, a powder, a bar: yes; a tablet: no).

### 2.3 Food for special dietary use and special medical purpose

Out of scope (build prompt). `special_medical` shows the allergen lines, the pack's own medical
statement quoted as printed, and one line: **User text:** "This pack says it is to be used under
medical advice. We show the allergens on the list and nothing else." Nothing is scored, compared or
catalogued beyond the usual review.

## 3. Which parts of today's result apply

| Part (lenses/screen.py) | food | supplement | Why, for a supplement |
|---|---|---|---|
| Allergen lines (`people`), first key | on | **on, first** | D-060, every kind |
| Headline | on | on, from the supplement checks (4.x) | |
| Tiles (D-134) | on | on: additive not in the Nutra lists, plant notes, amounts above ICMR-NIN's upper limit | |
| Sugar answer | on | **only for gummies, powders, bars, candies, biscuits** (5(1)(a) formats) | a tablet's sucrose coating is an excipient (Annexure 3 item 66) |
| "How it's made" (NOVA count) | on | **off** | excipients such as microcrystalline cellulose, maltodextrin and hydrogenated vegetable oil are listed by the regulation itself (Annexure 3 items 48, 44, 30) and would read as "industrial" |
| Additives answer and cards | against FSSAI Appendix A | **against the Nutra lists**: Annexure 3 for tablets, capsules, syrups; the 13.6 list plus Appendix A GMP otherwise (6(1)(e)) | the regulation names its own list |
| D-132 ingredient notes | on | **off** except the sweetener line for a child's profile | hydrogenated vegetable oil is a listed tablet lubricant (Annexure 3 item 30, 1%); maida, palm oil lines were written for foods |
| Nutrition table (D-133) and ICMR-NIN Table 15.1 | on | **replaced** by amounts per daily usage beside ICMR-NIN's RDA and upper limit (4.4) | Table 15.1 is per 100 g of food |
| A to E score, band | admin only | **none** (score null) | the score weighs ingredients of a food |
| At a glance | on | on, ingredient types only; no "industrial" slot | |
| Compare | on | **only between supplements** | a tablet beside a biscuit means nothing |
| Shop list (D-130) | screens | screens | unchanged |
| Kids lens (child's profile) | on | replaced by the Nutra rules for children (4.5) | |

## 4. Checks from the regulation (each quotes the regulation; complete read of both faces)

### 4.1 Label statements, 5(12) (Annexure 1 pp. 5 to 6)

Found or not found, never "missing": **User text** pattern: "FSSAI's rules for health supplements
ask the label to say "NOT FOR MEDICINAL USE". We didn't find it on the photos of this pack." Only
on a complete read of both faces (front and back photos, both `read`); otherwise nothing is said.

| id | The regulation's words | Where | Checked how |
|---|---|---|---|
| category_words | "HEALTH SUPPLEMENT/ NUTRACEUTICAL/ ..." "in capital and bold letters in the immediate proximity of the name or brand name" | front, 5(12)(a)(i)(A) | the words on the front (letter size and boldness are not judged) |
| target_group | "A prominent statement indicating the target consumer group and/or age group if the product has been formulated for a specific age group" | front, (i)(B) | not checked ("if": the label decides) |
| not_medicinal | "NOT FOR MEDICINAL USE" | front or back, (ii)(A) | text match |
| usage_level | "Recommended usage level" | (ii)(B) | a usage statement present (e.g. "Take 1 tablet daily") |
| duration | "Duration of usage, where applicable" | (ii)(C) | not checked ("where applicable") |
| not_exceed | "Not to exceed the recommended daily usage" | (ii)(D) | text match |
| varied_diet | "product is not to be used as a substitute for a varied diet" | (ii)(G) | text match; not for FSDU/FSMP |
| out_of_reach | "product is required to be stored out of reach of children" | (ii)(H) | text match (wording varies: "Keep out of reach of children" counts; the rule lists accepted forms) |
| pct_rda | "The quantity of nutrients, expressed in terms of percentage of the relevant recommended daily allowances" | (ii)(I) | a % RDA column read |

### 4.2 Additives

6(1)(e): tablets, capsules, pills, liquids: "Only additives as specified by the FA from time to
time", which the direction's footnote points to Annexure 3 ("FBO shall refer to Annexure 3 for
additives/excipients intended specifically for tablet/capsule/syrup/pills format"). Other formats:
"Only additives within the limits specified as permitted for category 13.6 and GMP table of
Appendix 'A'". Annexure 3's tablet list names most excipients **by name, without INS** ("Magnesium
stearate", "Microcrystalline cellulose", "Colors permitted under Rule 127 of Drugs & Cosmetics Rules
including lake colours"), so matching is by name through `normalization.json` plus INS through
`core/tokenize.py` (D-099). A name in neither list is **not** "not permitted" (the list is long and
names vary); it gets the D-111 "Worth knowing" badge with **User text:** "We didn't find this
additive in the lists FSSAI's supplement rules give." A reviewer confirms before anything stronger.

### 4.3 Plants (Schedule II, pp. 23 to 55)

The schedule gives, per plant and part, a "Permitted range of usage for adults per day" and about
**54 notes on 48 rows** (a note belongs to a part, so a row can carry two). Counted from the text
layer, which is unreliable (below); the build counts from the page images:
20 "Not recommended for children below 5 years", 10 "Not recommended during pregnancy", 5 "children
below 5 years and pregnant women", 3 "children below 16 years", 2 "males and females planning to
conceive", 2 "diabetics", and one each of "prolonged use", "usage beyond 30 days", "skin ailments",
"Caution: excessive use may cause giddiness", "hypertension and bleeding disorders", "not indicated in
children and lactating mothers", "females planning to conceive". Notes 4 and 5 (p. 55): children 5
to 16 years get half the adult range, 2 to 5 years a quarter.

A **tile** (D-134 shape, kind `supplement`) when a listed plant is on the pack **and** its row has a
note: **User text** pattern: "Garlic (Allium sativum), bulb: FSSAI's schedule for supplements says
"Not recommended during pregnancy"." Quote the note exactly, name the part, and say nothing when
the pack doesn't say which part (the note may belong to another part: row 427 Vitex's note is for
the leaf only). The **usage range** is shown beside the pack's own amount per day only when the pack
prints the amount of that plant as raw herb or powder; extracts ("Extract equivalent to") are not
compared (the schedule's "extractive ratios" aren't on the label).

The text layer is unreliable at page breaks (row 359 reads "Not recommended for Root diabetics": the
note is "(Not recommended for diabetics)" and "Root" is the next part; row 437's note runs across
pp. 54 to 55), so **every row goes into the table from the page image**, by hand, with its page.

### 4.4 Amounts per daily usage (Schedule I has no levels of its own)

Schedule I lists the permitted forms of each vitamin and mineral and the overages (Table C) but no
amounts. The amounts come from:
- 6(1)(c)(i), health supplements: "Usage levels shall not be more than the level specified by the
  Food Authority. In case, the levels are not specified by the food Authority, usage level shall be
  minimum 15 % of RDA as specified by ICMR, where a nutrient content claim is being made, provided
  that, if claim of higher nutrient content is made, the nutrient content shall not be less than
  thirty per cent of the recommended daily allowance and shall not exceed one RDA in any case."
- 5(4)(e): esters and salts of vitamins used as additives: "In case, levels are not specified by
  Food Authority the total level shall not exceed RDA specified by ICMR."
- ICMR-NIN's RDA (A2, p. 30) and tolerable upper limit (A6, p. 32; "the maximum level of habitual
  intake from all sources ... judged to be unlikely to lead to adverse health effects in humans").

Whether "shall not exceed one RDA in any case" applies to every health supplement or only to one
making a higher-content claim is not clear from the sentence (question 2). So the proposal shows
**facts only, no finding on the RDA**: **User text** pattern: "One day's usage (2 tablets) gives
15 mg iron. ICMR-NIN's RDA is 19 mg a day for adult men and 29 mg for adult women, and its upper
limit is 45 mg a day." A **tile** only above ICMR-NIN's upper limit for adults, which is the source's
own line. Magnesium's upper limit (350 mg) is below its RDA (440 mg for men) because, as A6's note
says, "For Magnesium the TUL values are only for non-dietary pharmacological doses": the line quotes
that note.

Reading: the amount per tablet, capsule or scoop comes from the pack's composition table (the D-133
reader, extended to "per serving" tables, section 6); the daily usage from the usage statement
(4.1 usage_level) as printed ("1 tablet twice a day" gives 2). Any number that fails the second
reading (D-133) is not shown.

### 4.5 Children

- 5(10), p. 5: "The products covered under these regulations intended for children of 2 to 5 years of
  age, shall only be given under medical advice by a recognized medical doctor or dietician or
  nutritionist." For a phone with a child's profile of 2 to 5 years (the `toddler` band 1 to 3 is
  under it; `kid` 4 to 11 straddles it), **User text:** "FSSAI's rules for supplements say products
  for children of 2 to 5 years "shall only be given under medical advice by a recognized medical
  doctor or dietician or nutritionist"."
- Under 2 years: 2(1) note 1 sends foods for infants to the infant regulations; a supplement isn't
  one. For a baby profile, **User text:** "FSSAI's rules for supplements cover people above 2 years
  of age." (2(1): "These foods are intended for population above the age of 2 years".)
- Plant notes about children (4.3) show for the matching profile first.

### 4.6 Claims

5(13)(a): no claim "to treat, cure, mitigate or prevent any specific disease, disorder or condition
... unless specifically permitted by Food Authority". The claim checker is in shadow (D-051); a
supplement's front claims are **stored, not shown**, like every other claim. No new claim rule in
this proposal.

### 4.7 Protein powders (ICMR-NIN, a note, not a check)

A protein powder (the pack's own words "protein" with a powder format) gets a line in "More about
this pack", for Sushil to approve as D-132 rows were: **User text:** "ICMR-NIN's dietary guidelines
say "Consuming high level of protein, especially in the form of protein supplement powders, is
therefore not advisable" and "Most athletes can get the recommended amount of protein through food
alone, without the use of supplements."" (DGI 2024 pp. 60 to 61.)

## 5. Data tables (row shapes and first rows; every row carries its basis and `verified_on`)

### 5.1 `data/pack_kinds.json` (shared with baby food)

```json
{
  "_meta": {"why": "D-139, D-140: which parts of the result apply to each kind of pack, and the printed words that decide the kind. core/pack_kind.py reads it; screen.py switches parts from it."},
  "kinds": {
    "food":            {"parts": ["allergens", "headline", "tiles", "sugar", "processing", "additives", "ingredient_notes", "nutrition", "glance", "compare", "score"]},
    "supplement":      {"parts": ["allergens", "headline", "tiles", "sugar_if_food_format", "nutra_additives", "nutra_statements", "nutra_amounts", "botanicals", "glance_types", "compare_same_kind"]},
    "infant":          {"parts": ["allergens", "headline", "tiles", "infant_additives", "infant_statements", "infant_composition", "breastfeeding_line"]},
    "special_medical": {"parts": ["allergens", "medical_statement"]},
    "not_food":        {"parts": ["allergens", "licence_note"]}
  },
  "evidence": [
    {"id": "infant_notice", "kind": "infant", "words": ["MOTHER'S MILK IS BEST FOR YOUR BABY", "MOTHERS' MILK IS BEST FOR YOUR BABY"], "face": "any", "basis": "FSS (Foods for Infant Nutrition) Regulations 2020, 4(1)(a), compendium Version II PDF p. 4", "verified_on": "2026-09-30"},
    {"id": "hs_words", "kind": "supplement", "words": ["HEALTH SUPPLEMENT", "NUTRACEUTICAL", "DIETARY SUPPLEMENT", "FOOD SUPPLEMENT"], "face": "any", "basis": "FSS (Nutra) Regulations 2022 as operationalised by direction of 18.10.2022, 5(12)(a)(i)(A) Annexure 1 p. 5 and 6(1)(f)(ii) p. 8", "verified_on": "2026-09-30"},
    {"id": "fsmp_words", "kind": "special_medical", "words": ["FOOD FOR SPECIAL MEDICAL PURPOSE", "RECOMMENDED TO BE USED UNDER MEDICAL ADVICE ONLY", "FOOD FOR SPECIAL DIETARY USE"], "face": "any", "basis": "same, 6(4)(f)(i)(A) p. 14 and 6(3)(f)(i)(A) p. 10", "verified_on": "2026-09-30"}
  ],
  "catalogue_categories": {"13.1": "infant", "13.2": "infant", "13.3": "special_medical", "13.4": "special_medical", "13.5": "special_medical", "13.6": "supplement"}
}
```

### 5.2 `data/nutra_rules.json`

```json
{
  "_meta": {"source": {"title": "FSS (Health Supplements, Nutraceuticals, Food for Special Dietary Use, Food for Special Medical Purpose and Prebiotic and Probiotic Food) Regulations, 2022, Annexure 1 to FSSAI's direction of 18 October 2022 under sections 18(2)(d) and 16(5)", "url": "https://fssai.gov.in/docs/food-law/regulations/Direction_New_compressed.pdf", "status": "operationalised by direction; the final regulations are not notified (FSSAI notifications list, searched 2026-09-30)"}},
  "statements": [
    {"id": "not_medicinal", "text": "NOT FOR MEDICINAL USE", "match": ["not for medicinal use"], "face": "front_or_back", "fssai_basis": "5(12)(a)(ii)(A), Annexure 1 p. 6", "verified_on": "2026-09-30"},
    {"id": "not_exceed", "text": "Not to exceed the recommended daily usage", "match": ["not to exceed the recommended daily usage", "do not exceed the recommended daily"], "face": "front_or_back", "fssai_basis": "5(12)(a)(ii)(D), Annexure 1 p. 6", "verified_on": "2026-09-30"},
    {"id": "out_of_reach", "text": "product is required to be stored out of reach of children", "match": ["out of reach of children"], "face": "front_or_back", "fssai_basis": "5(12)(a)(ii)(H), Annexure 1 p. 6", "verified_on": "2026-09-30"}
  ],
  "rda": {
    "_source": {"title": "ICMR-NIN, Short Summary Report: Nutrient Requirements for Indians, RDA and EAR (2020, revised 2024), Tables A2 and A6", "url": "https://www.nin.res.in/RDA_short_Report_2024.html", "page": "pp. 30, 32", "read_on": "2026-09-30"},
    "rows": [
      {"nutrient": "iron", "unit": "mg", "rda_men": 19, "rda_women": 29, "tul_adult": 45, "verified_on": "2026-09-30"},
      {"nutrient": "zinc", "unit": "mg", "rda_men": 17, "rda_women": 13.2, "tul_adult": 40, "verified_on": "2026-09-30"},
      {"nutrient": "calcium", "unit": "mg", "rda_men": 1000, "rda_women": 1000, "tul_adult": 2500, "verified_on": "2026-09-30"},
      {"nutrient": "vitamin_d", "unit": "IU", "rda_men": 600, "rda_women": 600, "tul_adult": 4000, "verified_on": "2026-09-30"},
      {"nutrient": "vitamin_b12", "unit": "ug", "rda_men": 2.2, "rda_women": 2.2, "tul_adult": null, "verified_on": "2026-09-30"},
      {"nutrient": "magnesium", "unit": "mg", "rda_men": 440, "rda_women": 370, "tul_adult": 350, "tul_note": "For Magnesium the TUL values are only for non-dietary pharmacological doses.", "verified_on": "2026-09-30"}
    ]
  },
  "children_2_to_5": {"text": "The products covered under these regulations intended for children of 2 to 5 years of age, shall only be given under medical advice by a recognized medical doctor or dietician or nutritionist.", "fssai_basis": "5(10), Annexure 1 p. 5", "verified_on": "2026-09-30"}
}
```

The rest of A2 (vitamin A 1000/840 µg, vitamin C 80/65 mg, folate 300/220 µg, iodine 140 µg, B6 1.9 mg
sedentary, thiamine, riboflavin and niacin by activity level) and A5 (sodium 2000 mg, potassium
3500 mg, copper 1.7 mg, manganese 4 mg, chromium 50 µg, selenium 40 µg) go in the same shape, each
checked against the page image. Thiamine, riboflavin, niacin and B6 vary with activity: the
sedentary figure, stated as such (question 3). Biotin and pantothenic acid have "adequate intake"
in the text, not in A2: not compared.

### 5.3 `data/nutra_botanicals.json` (only rows whose note a user would read)

```json
{"rows": [
  {"id": "allium_sativum_bulb", "botanical": "Allium sativum L.", "part": "Bulb", "names": ["garlic", "lahsun", "rason"], "usage_adult_per_day": "1-3 g", "note": "Not recommended during pregnancy", "who": "pregnancy", "fssai_basis": "Schedule II row 19, Annexure 1 p. 24", "verified_on": "2026-09-30"},
  {"id": "cinnamomum_bark", "botanical": "Cinnamomum zeylanicum Blume / C. cassia / C. aromaticum", "part": "Bark", "names": ["cinnamon", "dalchini", "twak"], "usage_adult_per_day": "1-2 g", "note": "Not recommended during pregnancy", "who": "pregnancy", "fssai_basis": "Schedule II row 101, p. 30", "verified_on": "2026-09-30"},
  {"id": "coffea_seed", "botanical": "Coffea arabica / C. robusta", "part": "Seed (Dry/Green)", "names": ["coffee", "green coffee", "kaaphi"], "usage_adult_per_day": "3-5 g", "note": "Not recommended for children below 5 years", "who": "under_5", "fssai_basis": "Schedule II row 121, p. 31", "verified_on": "2026-09-30"},
  {"id": "crocus_stigma", "botanical": "Crocus sativus L.", "part": "Style/ Stigma", "names": ["saffron", "kesar", "kumkum"], "usage_adult_per_day": "25-50 mg", "note": "Not recommended for children below 16 years", "who": "under_16", "fssai_basis": "Schedule II row 138, p. 32", "verified_on": "2026-09-30"},
  {"id": "nigella_seed", "botanical": "Nigella sativa L.", "part": "Seed", "names": ["kalonji", "kalaunji", "black cumin"], "usage_adult_per_day": "1-3 g", "note": "Not recommended during pregnancy", "who": "pregnancy", "fssai_basis": "Schedule II row 271, p. 42", "verified_on": "2026-09-30"},
  {"id": "zingiber_extract", "botanical": "Zingiber officinale Rosc.", "part": "Rhizome, extract", "names": ["ginger extract"], "usage_adult_per_day": "0.1-1 g", "note": "Not recommended during hypertension and bleeding disorders", "who": "condition", "fssai_basis": "Schedule II row 437, pp. 54 to 55 (checked on the page images)", "verified_on": "2026-09-30"}
]}
```

"names" in English (garlic, cinnamon, saffron) are **not in the schedule**, which gives Latin and
Indian names only: each English name needs a source before it matches (question 6). Rows with no
note (ashwagandha, row 432, p. 54) are not in the table: the schedule says nothing a user would read
about them beyond the usage range. The pregnancy rows show only as information (the app has no
pregnancy profile, D-074).

## 6. Reading (phase 1 and 2, transcription only; D-004)

- `pack_statements`: every statement from section 4.1 and 2.1 copied verbatim with its face.
- `licences`: each licence as printed with its kind as printed ("FSSAI Lic. No. 1001...", "Mfg. Lic.
  No. ..."): no judgement of what it is.
- `composition`: the pack's table of nutrients and ingredients per unit ("Each tablet contains",
  "per 2 capsules", "per scoop (30 g)"), with the unit and the % RDA column as printed; the D-133
  second-reading check applies to every number.
- New PROMPT_VERSION; an older answer without these parses as `food` and replays unchanged (D-092).

## 7. What no source says, so the app won't

- **Nothing about whether a supplement is needed**, works, or is worth taking: no primary source read
  says it for a given pack, and 5(13) is about what the maker may claim, not what the app may say.
- **No finding that an amount breaks the one-RDA rule**, until question 2 is answered.
- **No English plant names** until a source gives them (question 6).
- **No "industrial" or ultra-processed wording** for a supplement: NOVA (Monteiro 2019) classifies
  foods; no source read applies it to tablets.
- **No verdict on a drug-licensed pack:** it is not food under the FSS Act, and our rules are food
  rules (D-116, D-086).
- **Letter size, boldness and "prominently"** in 5(12) are not judged from a photo.

## 8. Questions for Sushil (and who else)

1. **Legal status (a lawyer):** the 2022 Nutra Regulations run on a direction of 18 October 2022 and
   were never notified. Can the app quote them as FSSAI's rules for supplements, saying "as
   operationalised by FSSAI's direction of 18 October 2022"? Recommended: yes, with that phrase in
   every source line, and revisit if FSSAI notifies them.
2. **The one-RDA sentence (a lawyer):** does 6(1)(c)(i)'s "shall not exceed one RDA in any case"
   apply to every health supplement or only to a higher-content claim? Recommended until answered:
   show amounts beside RDA and upper limit, no finding on the RDA.
3. **Which RDA:** men's or women's, and which activity level? Recommended: show men and women side by
   side, sedentary where the table splits by activity, and name both.
4. **Kid band:** 5(10) speaks of 2 to 5 years; our `kid` band is 4 to 11. Recommended: the 2-to-5 line
   for `toddler` and `kid` both, worded "for children of 2 to 5 years".
5. **Prebiotic and probiotic foods:** keep them as ordinary food (recommended) or add 6(5)'s label
   checks (strain names, viable numbers)?
6. **English plant names** (garlic, cinnamon, saffron): from which source? The schedule gives Latin and
   Indian names only. Recommended: match on the schedule's own names and the Latin name until a
   source (for example the Ayurvedic Pharmacopoeia of India) is read.
7. **The protein-powder line** (4.7): approve, edit or drop.
8. **Gold labels:** at least 3 supplements photographed (one in poor light): a multivitamin tablet, a
   protein powder, a gummy or a herbal capsule with a noted plant. Each paid read about 50 paise plus
   a Cloud Vision read; asked before any.
9. **Timing (D-083):** this lands before the first cohort or waits for W4.
</content>
</invoke>
