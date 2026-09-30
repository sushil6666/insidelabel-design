# Baby food: infant formula and complementary foods (D-140, phase 0)

Written 2026-09-30 from primary documents read that day (D-046). **Accepted by Sushil 2026-09-30 (D-140
LOCKED, with his choices recorded there); built in phase 3, in shadow.** Lines
marked "User text" are what the app would show; each quotes its source. The kind-of-pack rule and
`data/pack_kinds.json` are in `docs/SUPPLEMENTS.md` section 2 and 5.1; this file adds the infant words.

**The IMS Act** (the Infant Milk Substitutes, Feeding Bottles and Infant Foods (Regulation of
Production, Supply and Distribution) Act, 1992, Act 41 of 1992) is quoted **only** from
`sources/legal/ims-act-1992/ims-act-1992-en-as-on-2025-12-15.pdf`, India Code's text "As on the 15th
December, 2025" (amended by Act 38 of 2003 and the FSS Act 2006), downloaded by Sushil from
https://www.indiacode.nic.in/handle/123456789/1958 on 2026-09-30 (India Code doesn't answer scripts
from this machine; see the folder's README). Read 2026-09-30; page numbers are the PDF's own.

## 0. Legal status (FSSAI's own pages and documents, 2026-09-30)

- **FSS (Foods for Infant Nutrition) Regulations, 2020**: gazetted 4 December 2020 (F. No.
  Stds/03/Notification (IFR)/FSSAI-2017), amended 30 August 2022 (F. No. Std/SP-05/T(IFR-01)); the
  compendium **Version II (04.01.2024)** carries both (its closing note, PDF p. 53).
- **In force from 1 October 2022**: FSSAI's order of 29 March 2022 ("the regulations shall be enforced
  from 1st October 2022") and direction of 18 October 2022 ("have been enforced w.e.f. 1st October
  2022"), both from FSSAI's advisories list.
- **Selenium, manganese, iron and biotin**: the limits in force are the "revised limits" of the 18
  October 2022 direction's Annexure-1 ("operational with effect from 1st October 2022"), **not** the
  compendium's. A draft amendment of 29 March 2023 proposes the same kind of change; it is a draft.
- **FSS (Labelling and Display) First Amendment Regulations, 2026**, in force **1 July 2027**: "per
  serve percentage (%) contribution to Recommended dietary allowances (RDA) and number of servings per
  pack may not be given for Infant Nutrition products". Not in force yet; noted so the app doesn't
  later expect a % RDA column on these packs.

## 1. Sources read first-hand (2026-09-30)

| Source | Where | Used for |
|---|---|---|
| FSS (Foods for Infant Nutrition) Regulations 2020, compendium Version II (04.01.2024) | https://fssai.gov.in/docs/food-law/regulations/Comp_IFR_VERSION-II_04_01_2024.pdf (PDF pages) | definitions 2 pp. 1 to 2; general 3 pp. 2 to 4; labelling 4 pp. 4 to 6; additives 5 p. 6; infant formula 7 pp. 7 to 12; milk cereal based complementary food 8 pp. 12 to 18; processed cereal based complementary food 9 pp. 18 to 24; follow-up formula 10 pp. 24 to 29; traditional food ingredients 11 pp. 29 to 30; FSMP for infants 12 to 16 pp. 30 to 38; Schedule I pp. 38 to 53 |
| FSSAI order, 29 March 2022, implementation of the regulations | https://fssai.gov.in/docs/food-law/advisory/62441ac13c737Order_Infant_Nutrition_30_03_2022.pdf | in force 1 October 2022 |
| FSSAI direction, 18 October 2022, revised limits, with Annexure-1 | https://fssai.gov.in/docs/food-law/advisory/63849fc9b42f2Direction_Infant_Nutrition_28_11_2022.pdf (pp. 3 to 4) | selenium, manganese, iron, biotin |
| Draft FSS (Foods for Infant Nutrition) Amendment Regulations, 2023 | https://fssai.gov.in/docs/food-law/notice-comment/Notification1.pdf | a draft only |
| FSS (Labelling and Display) Regulations 2020, compendium I, 2(j) | https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Display_23_09_2021.pdf | "Infant" means "a person not more than twelve months of age" (L&D), while the infant regulations cover up to 24 months |
| L&D First Amendment Regulations, 2026 | https://fssai.gov.in/docs/food-law/notice-comment/69cca2b3f3ce9Notification%20dt%2024.03.2026_NRC.pdf | % RDA optional from 1 July 2027 |
| IMS Act 1992, as on 15 December 2025 | `sources/legal/ims-act-1992/ims-act-1992-en-as-on-2025-12-15.pdf` (India Code) | 2(a), 2(f), 2(g), 2(j) p. 4; 3 p. 5; 6 pp. 5 to 6; 7 p. 6 |
| FSS Act 2006, 3(1)(x) and section 100 | https://fssai.gov.in/upload/uploadfiles/files/FOOD-ACT.pdf (PDF pp. 4, 66) | "infant food" and "infant milk substitute" take the IMS Act's meanings (its section 2(f) and 2(g)); section 100 amends the IMS Act's references |
| WHO Guideline for complementary feeding of infants and young children 6 to 23 months of age, 2023 | https://iris.who.int/server/api/core/bitstreams/5abca011-4db2-4cf1-b959-45b756f7b600/content (printed page, PDF page) | recommendations 1 to 7 pp. x to xiii (PDF 12 to 15); 3.5 unhealthy foods and beverages pp. 32 to 33 (PDF 48 to 49) |
| ICMR-NIN, Dietary Guidelines for Indians 2024 | https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf (printed = PDF minus 17) | guideline 3 p. 21; points to register p. 25; complementary feeding pp. 26 to 29; p. 36 |

## 2. The kind of pack: `infant`, and its product type

The Act's definitions, which the FSS Act 3(1)(x) adopts for "infant food" and "infant milk substitute"
(IMS Act 2, p. 4):
- 2(f): ""infant food" means any food (by whatever name called) being marketed or otherwise represented
  as a complement to mother's milk to meet the growing nutritional needs of the infant after the age of
  six months and up to the age of two years;"
- 2(g): ""infant milk substitute" means any food being marketed or otherwise represented as a partial or
  total replacement for mother's milk for infant up to the age of two years;"

Both turn on how a food is "marketed or otherwise represented", which is what the printed words below
show; so the rule reads the pack's own words, never the product's recipe.

**Infant** (checked before `supplement`, `docs/SUPPLEMENTS.md` 2.1 step 2) when any of:
- "MOTHER'S MILK IS BEST FOR YOUR BABY" (4(1)(a): "in capital letters ... on the front of the pack of
  every container of food for infant nutrition"), with or without "IMPORTANT NOTICE" (4(1));
- "Infant food shall be introduced only after the age of six months and up to the age of two years"
  (4(1)(a), for infant food);
- "Traditional Food for Infants" (11(3), "on the front of the pack label");
- a product name from the regulation (below);
- the catalogue category 13.1 or 13.2 (`data/food_categories.json`).
An **age statement alone** ("for 6 to 24 months", "from 6 months") is supporting evidence: every
product type in the regulation is defined by age ("after six months up to twenty-four months", 2(1)),
but a biscuit saying "for 1 year and up" is not therefore a regulated infant food. Alone, it sends the
pack to a reviewer, and the result stays `food` with the baby lines of section 6 (question 3).

**Special medical** (`special_medical`, out of scope: allergens and the pack's own statement only):
"FOR THE PRETERM BABY (BORN BEFORE 37 WEEKS)" (13(2)(a)), "LACTOSE-FREE" with "RECOMMENDED TO BE USED
UNDER MEDICAL ADVICE ONLY" (14(2), 14(3)), "HYPOALLERGENIC FORMULA" (15(3)), "FOOD FOR SPECIAL MEDICAL
PURPOSE" (16(3)(a)), "mono grain based complementary foods for use in specific conditions under medical
guidance only" (9(3)). Category 13.1.3.

**Product type** (decides the additive table and the composition table), from the printed name:

| type | Printed words (from the regulation) | Regulation |
|---|---|---|
| infant_formula | "infant formula", "infant milk substitute", "Infant Milk Food" (7(3): powder made without vegetable oil and the listed extras "may be named as 'Infant Milk Food'") | 7, pp. 7 to 12 |
| follow_up_formula | "follow-up formula", "follow up formula" | 10, pp. 24 to 29 |
| milk_cereal | "milk cereal based complementary food" | 8, pp. 12 to 18 |
| processed_cereal | "processed cereal based complementary food" | 9, pp. 18 to 24 |
| traditional | "Traditional Food for Infants" | 11, pp. 29 to 30 |

No type found: the checks that need a type (additives table, composition, hydrogenated fat) are off,
and the pack goes to a reviewer, who sets the type (catalogue, phase 1). Most Indian packs print the
regulation's name in small type near the brand name; the gold set will show how often it is read.

## 3. Which parts of today's result apply

| Part | food | infant | Why |
|---|---|---|---|
| Allergen lines, first key | on | **on, first** | D-060 for every kind; 4(5) also asks for "A warning relating to allergen if any ingredients with known allergenicity are present" |
| Headline | on | from the infant checks, or the allergen line | |
| Tiles | on | the infant checks (section 4) | |
| Sugar, How it's made, Additives answers | on | **off**: replaced by the regulation's own checks | the product types are defined by the regulation, not by NOVA |
| D-132 notes, D-133 Table 15.1 | on | **off** | ICMR-NIN's Table 15.1 is for foods in general; the regulation has its own composition tables |
| Score, band, grade | admin only | **none** | the IMS Act question (section 5) |
| Compare, "better pick" | on | **refused on the server**, with a test per route | section 5 |
| Shop list | screens | **never offered** (`shop_list` never set) | section 5 |
| Tallies on "Your scans" (D-123) | on | **none** | counting and grouping packs is close to ranking |
| Share card | none exists | none | |

## 4. Checks from the regulation (complete read of both faces, D-111's care for anything strong)

### 4.1 Label statements, regulation 4 (pp. 4 to 6)

Found or not found on the photos, quoting the regulation: **User text** pattern: "FSSAI's rules for
infant foods ask for "MOTHER'S MILK IS BEST FOR YOUR BABY" on the front. We didn't find it on the photo
of the front." Only when the front and back were both read completely.

| id | The regulation's words | Where |
|---|---|---|
| important_notice | "IMPORTANT NOTICE" | 4(1) |
| mothers_milk | "MOTHER'S MILK IS BEST FOR YOUR BABY" in capital letters, "not less than five millimetres", front (size not judged from a photo) | 4(1)(a) |
| six_months | "Infant food shall be introduced only after the age of six months and up to the age of two years" (infant food, not formula) | 4(1)(a) |
| health_worker | "a statement that infant milk substitute or infant food shall be used only on the advice of a health worker as to the need for its use and the proper method of its use" | 4(1)(b) |
| not_sole | "a warning that Infant milk substitute or infant food is not the sole source of nourishment of an infant" | 4(1)(c) |
| preparation | "Warning/Caution-Careful and hygienic preparation of infant foods or infant milk substitute is most essential for health. ..." | 4(1)(d) |
| storage | "Store in a cool and dry place in an air tight container" "or the like" | 4(1)(f) |
| additive_names | "the specific name of the food additives and appropriate class titles" | 4(1)(k) |
| no_milk | "Contains no milk or milk products or milk derivatives", only where the product "contains neither milk nor any milk derivatives" | 4(3) |
| boiled_water | "Warning: Boiled and cooled water shall be used to prepare this product and any leftover product must be discarded to reduce the risk of infection" | 4(6) |

The statements are matched on their key words (the rule lists accepted forms), not letter for letter.

The Act asks for the same notice, IMS Act 6(1), pp. 5 to 6: "no person shall produce, supply or
distribute any infant milk substitute or infant food unless every container thereof or any label affixed
thereto indicates in a clear, conspicuous and in an easily readable and understandable manner, the words
"important notice" in capital letters ... and indicating thereunder the following particulars": "(a) a
statement "mother's milk is best for your baby" in capital letters; (b) a statement that infant milk
substitute or infant food should be used only on the advice of a health worker as to the need for its use
and the proper method of its use; (c) a warning that infant milk substitute or infant food is not the sole
source of nourishment of an infant; (d) the instructions for its appropriate preparation and a warning
against the health hazards of its inappropriate preparation; (e) the ingredients used; (f) the composition
or analysis; (g) the storage conditions required; (h) the batch number, date of its manufacture and the
date before which it is to be consumed ...; (i) such other particulars as may be prescribed." A "not found"
line cites the regulation (4(1)) and may add the Act's clause; it never says the Act is broken (D-042).

### 4.2 Words the regulation says not to use, 4(2) (p. 6)

"The terms "Humanised" or "Maternalised" or any other similar words shall not be used. The package
and/or any other label of infant milk substitute or infant food shall not exhibit the words, "Full
Protein Food", "Energy Food", "Completer Food" or "Health Food" or any other similar expression."
(The compendium prints "Completer Food".) A match on the pack's printed words: **User text:** "The pack
says "Energy Food". FSSAI's rules for infant foods say the label "shall not exhibit" the words "Full
Protein Food", "Energy Food", "Completer Food" or "Health Food"." Exact words only ("or any other
similar expression" is a judgement: not made).

"No containers or label of food for infant nutrition shall have a picture of infant or women or both":
**not checked by the app.** Seeing a picture is a judgement of the image (D-004); it goes on the
reviewer's checklist instead.

The Act, 6(2), p. 6: "No container or label referred to in sub-section (1) relating to infant milk
substitute or infant food shall (a) have pictures of an infant or a woman or both; or (b) have pictures or
other graphic material or phrases designed to increase the saleability of infant milk substitute or infant
food; or (c) use on it the word "humanised" or "maternalised" or any other similar word; or (d) bear on it
such other particulars as may be prescribed." The words check (humanised, maternalised) can cite both;
(a) and (b) stay reviewer checks.

### 4.3 Additives, regulation 5 (p. 6) and the tables per type

- 5(1): "Food for infant nutrition shall be free from preservatives, added colours and flavours." A
  preservative or colour (by the additive's class in `additives.json`, D-046) or a flavour on the list:
  **User text:** "FSSAI's rules for infant foods say they "shall be free from preservatives, added
  colours and flavours". The list on this pack includes "Added flavour (vanilla)"." A tile, with the
  D-111 care (complete read, confidence 0.95, quote, "check the pack", reviewer).
- 5(2): "Only the food additives listed under these regulations shall be used". With a known product
  type, an INS number not in that type's table (and not in Schedule I(d), the nutrient carriers):
  **User text:** "We didn't find INS 471 in the additives FSSAI's infant rules list for this kind of
  food." Worded as not found, because carry-over additives are allowed (5(2)) and the type may be
  misread; a reviewer confirms. Without a type, nothing.

### 4.4 Hydrogenated fat, by type (the build prompt's "not permitted" finding)

| type | The regulation's words | page |
|---|---|---|
| infant_formula | "Hydrogenated vegetable oils and fats shall not be used in infant formula." | 7(1)(c), p. 7 |
| milk_cereal | "It shall not contain hydrogenated vegetable fats and oils." | 8(1)(c), p. 13 |
| processed_cereal | "It shall not contain hydrogenated vegetable oils and fats." | 9(1)(d), p. 19 |
| follow_up_formula | "Partially hydrogenated oils and fats shall not be used in follow-up formula." | 10(1)(d), p. 25 |
| traditional | no such sentence | 11 |

Matched with the names D-132 and D-135 use (hydrogenated vegetable fat, vanaspati, shortening; "non-hydrogenated" never
counts). A tile with D-111's care. Traditional foods get nothing (no source says it).

### 4.5 Composition, where the pack prints the same nutrient (the D-133 reader)

Each type has a table "per 100 g" and "per 100 kcal" (3(14): the maker complies "in either per 100 gm
or per 100 kcal basis"). Where the pack's nutrition table prints the same nutrient on the same basis
and the number passes the second reading (D-133): **User text** pattern: "The pack prints 8 mg iron per
100 g. FSSAI's rules for milk cereal based complementary food set 3 to 7 mg per 100 g." Facts side by
side, never "fails" or "outside the law" (D-042). Only for a known type, and only nutrients whose limit
in force is certain: **selenium, manganese, iron and biotin use the 18 October 2022 direction's limits.**
3(3) allows "a variation of minus 10.0 per cent from the declared value" (declared against analysed,
not against the limits), so it doesn't change this comparison. Moisture, ash, protein quality and fatty
acid ratios are not on labels: not compared.

### 4.6 Sugar and honey

- 3(6): "Sucrose and/or fructose shall not be added, unless needed as a carbohydrate source, and
  provided the sum of these does not exceed 20 per cent of total carbohydrate." Labels rarely print
  sucrose apart from total sugars: **checked only when the table prints sucrose**, otherwise nothing.
- 9(1)(d): honey or maple syrup "shall be processed in such a way as to destroy spores of Clostridium
  botulimum" (sic). A label can't show processing: **not checked.**
- For a baby profile (section 6) the ICMR-NIN sugar line shows as on any food.

### 4.7 Breastfeeding line (on every infant result)

**User text:** "ICMR-NIN's dietary guidelines say: "Ensure exclusive breastfeeding for the first six
months and continue breastfeeding till two years and beyond"." (DGI 2024, guideline 3, p. 21.) WHO's
2023 guideline says the same for 6 to 23 months ("Breastfeeding should continue up to 2 years or
beyond", recommendation 1, p. x) and can sit in the sources.

**Not one line, if the result is "material" under the Act.** IMS Act 7(1) (p. 6) asks every "educational
or other material ... dealing with pre-natal or post-natal care or with the feeding of an infant and
intended to reach pregnant women or mothers of infants" to include clear information on **six
particulars, (a) to (f)**, and two more clauses, (fa) and (g) (quoted in section 5). A single
breastfeeding line covers part of (a) and (b) at most. **Sushil, 2026-09-30 (D-140): the line is removed
until the lawyer answers** (questions 1b and 1c). An infant result shows nothing about feeding.

## 5. The IMS Act and what the app refuses

What the Act says (IMS Act as on 15 December 2025):
- **2(j), p. 4:** ""promotion" means to employ directly or indirectly any method of encouraging any person
  to purchase or use infant milk substitute, feeding bottle or infant food."
- **2(a), p. 4** (outside the build prompt's list, read because it bears on an app): ""advertisement"
  includes any notice, circular, label, wrapper or any other document or visible representation or
  announcement made by means of any light, sound, smoke or gas or by means of electronic transmission or
  by audio or visual transmission;"
- **3, p. 5:** "No person shall (a) advertise, or take part in the publication of any advertisement, for
  the distribution, sale or supply of infant milk substitutes, feeding bottles or infant foods; or (b) give
  an impression or create a belief in any manner that feeding of infant milk substitutes and infant foods
  are equivalent to, or better than, mother's milk; or (c) take part in the promotion of infant milk
  substitutes, feeding bottles or infant foods."
- **7(1), p. 6:** "Every educational or other material including advertisements or material relating to
  promotion of infant milk substitutes, feeding bottles and infant foods, whether audio or visual, dealing
  with pre-natal or post-natal care or with the feeding of an infant and intended to reach pregnant women
  or mothers of infants shall include clear information relating to (a) the benefits and superiority of
  breast-feeding; (b) the preparation for, and the continuance of, breast-feeding; (c) the harmful effects
  on breast-feeding due to the partial adoption of bottle feeding; (d) the difficulties in reverting to
  breast-feeding of infants after a period of feeding by infant milk substitute; (e) the financial and
  social implications in making use of infant milk substitutes and feeding bottles; (f) the health hazards
  of improper use of infant milk substitutes and feeding bottles; (fa) the date of printing and publication
  of such material and the name of the printer and publisher; (g) such other matters as may be
  prescribed."
- **7(2), p. 6:** "No material referred to in sub-section (1) shall be utilised to promote the use or sale
  of infant milk substitutes or feeding bottles or infant foods."
- The infant regulations, 3(8) (p. 3), ask food for infant nutrition to comply with the Act "including
  aspect related to advertisement, marketing and promotion ... in accordance with the section 3, 4, 5, 7,
  8, 9 and 10 of the said Act".

Unlike the regulations, section 3 speaks to "No person", not only to makers. Whether InsideLabel showing
an infant food's facts is "promotion" (2(j)), an "advertisement" by "electronic transmission" (2(a)), an
"impression ... equivalent to, or better than, mother's milk" (3(b)), or "educational or other material"
under 7(1) is a lawyer's question (section 9). Until it is answered, the proposal stays on the careful
side:
- **No grade, score, band, ranking, "better pick", Compare, shop list, tallies or share card** for an
  infant pack: each would be a "method of encouraging any person to purchase or use" one pack over
  another (2(j)). On the server: `/compare` returns 422 with `reason: "infant_food"` when any pack in the
  request is infant; `screen` never carries `shop_list`, `tallies` or `summary` for one; the score is
  null. A test per route, not only a hidden button.
- **Nothing that sets an infant food beside mother's milk** (3(b)): no composition line worded against
  breast milk, no "closer to" or "like".
- **Released in shadow, like the claim check (D-051):** the whole infant result is computed and stored
  for reviewers; **users get the allergen lines, the kind in the pack's own words, the ingredient list and
  one sentence** (Sushil, D-140), **User text:** "Results for infant foods aren't shown yet. We show the
  allergens on the list and the ingredient list." The server sends no score, grade, band, claim, nutrition
  or EU/US result for an infant pack (`withheld`), and `/compare` refuses one. Switch:
  `INSIDELABEL_INFANT_TO_USERS`, off by default, on only after Sushil's decision on a lawyer's reading.

## 6. Profiles: a "baby" band (D-074: a value, not a field)

Today: `toddler` "1 to 3 years", `kid` "4 to 11 years", `young` "12 and up" (web/lib.js,
lenses/compare.py). Proposal: **`baby` "Under 2 years"**, and `toddler` becomes "2 to 3 years"
(question 4 on existing toddler profiles). What changes for a baby profile **on an ordinary food**, only
where a source says it:

| On the pack | Line (User text) | Source |
|---|---|---|
| any added sugar name (kids.sugar_positions) | "ICMR-NIN's dietary guidelines say "Added sugar must be totally avoided for children below 2 years"." | DGI 2024 p. 29 (under its diet charts for infants); also p. 26 "Avoid feeding foods and beverages with added sugar" |
| a non-sugar sweetener (the D-132 sweetener row's names) | "WHO's 2023 guideline for children 6 to 23 months says "Non-sugar sweeteners should not be consumed"." | WHO 2023 recommendation 5c, p. xii |
| honey | "ICMR-NIN's dietary guidelines say "Avoid feeding honey, glucose, water, or dilute milk formula before initiation of breastfeeding and anytime during the first 6 months"." | DGI 2024 p. 21 |
| salt | "ICMR-NIN's dietary guidelines say "Limit use of salt in complementary food preparations"." | DGI 2024 p. 26 |
| a nutrition table over ICMR-NIN's Table 15.1 (D-133) | "ICMR-NIN's dietary guidelines say "Processed foods and foods that are high in fats, salt and sugar (HFSS) must be avoided (example: biscuits, chips)" for children being fed complementary foods." | DGI 2024 p. 28; the thresholds are its Table 15.1, p. 96 |
| a supplement | "FSSAI's rules for supplements cover people above 2 years of age." | Nutra Regulations 2(1), `docs/SUPPLEMENTS.md` 4.5 |

Not said, because no source read gives a threshold: WHO 5a's "Foods high in sugar, salt and trans fats
should not be consumed" (the guideline defines no "high"; its section 3.5 cites only the adult
free-sugars guideline). The toddler lens's existing facts (compare.py) apply to a baby too.

## 7. Data tables (row shapes and first rows)

### 7.1 `data/infant_rules.json`

```json
{
  "_meta": {"source": {"title": "FSS (Foods for Infant Nutrition) Regulations, 2020, compendium Version II (04.01.2024)", "url": "https://fssai.gov.in/docs/food-law/regulations/Comp_IFR_VERSION-II_04_01_2024.pdf", "status": "in force from 1 October 2022 (FSSAI order 29.03.2022, direction 18.10.2022)"}},
  "statements": [
    {"id": "mothers_milk", "text": "MOTHER'S MILK IS BEST FOR YOUR BABY", "match": ["mother's milk is best for your baby", "mothers milk is best for your baby"], "face": "front", "types": "all_except_special_medical", "fssai_basis": "4(1)(a), PDF p. 4", "verified_on": "2026-09-30"},
    {"id": "not_sole", "text": "a warning that Infant milk substitute or infant food is not the sole source of nourishment of an infant", "match": ["not the sole source of nourishment"], "face": "any", "types": "all", "fssai_basis": "4(1)(c), PDF p. 5", "verified_on": "2026-09-30"},
    {"id": "boiled_water", "text": "Warning: Boiled and cooled water shall be used to prepare this product and any leftover product must be discarded to reduce the risk of infection", "match": ["boiled and cooled water"], "face": "any", "types": "all", "fssai_basis": "4(6), PDF p. 6", "verified_on": "2026-09-30"}
  ],
  "words_not_to_use": {"words": ["Humanised", "Maternalised", "Full Protein Food", "Energy Food", "Completer Food", "Health Food"], "fssai_basis": "4(2), PDF p. 6", "verified_on": "2026-09-30"},
  "free_from": {"text": "Food for infant nutrition shall be free from preservatives, added colours and flavours.", "classes": ["preservative", "colour", "flavour"], "fssai_basis": "5(1), PDF p. 6", "verified_on": "2026-09-30"},
  "no_hydrogenated": [
    {"type": "infant_formula", "text": "Hydrogenated vegetable oils and fats shall not be used in infant formula.", "fssai_basis": "7(1)(c), PDF p. 7", "verified_on": "2026-09-30"},
    {"type": "milk_cereal", "text": "It shall not contain hydrogenated vegetable fats and oils.", "fssai_basis": "8(1)(c), PDF p. 13", "verified_on": "2026-09-30"},
    {"type": "processed_cereal", "text": "It shall not contain hydrogenated vegetable oils and fats.", "fssai_basis": "9(1)(d), PDF p. 19", "verified_on": "2026-09-30"},
    {"type": "follow_up_formula", "text": "Partially hydrogenated oils and fats shall not be used in follow-up formula.", "partial_only": true, "fssai_basis": "10(1)(d), PDF p. 25", "verified_on": "2026-09-30"}
  ],
  "composition": [
    {"type": "milk_cereal", "nutrient": "iron", "unit": "mg", "per_100_g": [3.0, 7.0], "per_100_kcal": [0.6, 1.5], "fssai_basis": "8(1)(d) item 15, PDF p. 14", "verified_on": "2026-09-30"},
    {"type": "processed_cereal", "nutrient": "iron", "unit": "mg", "per_100_g": [2.0, 5.65], "per_100_kcal": [0.42, 1.2], "fssai_basis": "9(1)(f) item 15 as revised by FSSAI's direction of 18.10.2022, Annexure-1 p. 3 (the compendium's 3.00 to 5.65 is superseded)", "verified_on": "2026-09-30"},
    {"type": "infant_formula", "nutrient": "sodium", "unit": "mg", "per_100_g": [90.0, 300.0], "per_100_kcal": [19.15, 63.8], "fssai_basis": "7(1)(g) item 22, PDF p. 9", "verified_on": "2026-09-30"},
    {"type": "processed_cereal", "nutrient": "sodium", "unit": "mg", "per_100_kcal": [null, 100.0], "fssai_basis": "9(1)(c): \"shall not exceed 100 mg per 100 kcals of the ready to eat product\", PDF p. 18", "verified_on": "2026-09-30"}
  ]
}
```

### 7.2 `data/infant_additives.json` (one list per type; INS read through core/tokenize.py)

```json
{"types": {
  "infant_formula": {"basis": "7(2)(a), PDF pp. 10 to 12, per 100 ml ready for consumption", "rows": [
    {"ins": "322", "name": "Lecithin", "max": "0.5 g in all types of infant formula", "verified_on": "2026-09-30"},
    {"ins": "471", "name": "Mono- and diglycerides", "max": "0.4 g in all types of infant formula", "verified_on": "2026-09-30"},
    {"ins": "412", "name": "Guar gum", "max": "0.1 g in liquid formulas containing hydrolysed protein", "verified_on": "2026-09-30"}]},
  "milk_cereal": {"basis": "8(2)(a), PDF pp. 15 to 18, per 100 g ready for consumption", "rows": [
    {"ins": "322", "name": "Lecithins", "max": "1500 mg", "verified_on": "2026-09-30"},
    {"ins": "551", "name": "Silicon dioxide", "max": "GMP", "verified_on": "2026-09-30"}]},
  "carriers": {"basis": "Schedule I(d), PDF p. 52, all types", "rows": [
    {"ins": "414", "name": "Gum Arabic (gum acacia)", "max": "10 mg/kg", "verified_on": "2026-09-30"},
    {"ins": "1450", "name": "Starch sodium octenyl succinate", "max": "100 mg/kg", "verified_on": "2026-09-30"}]}
}}
```

The build copies every row of each table from the compendium pages by hand (the text layer merges
table cells; the traditional type uses the milk cereal table, 11(2)).

## 8. What no source says, so the app won't

- **Nothing that ranks, recommends or prefers one infant food** (section 5).
- **No "high in sugar/salt" for a baby from WHO** (no threshold given); ICMR-NIN's HFSS sentence only
  where its Table 15.1 says high.
- **No judgement of pictures** on the pack (4(2)); a reviewer's check.
- **No honey-processing, protein-quality, moisture or fatty-acid checks**: not on labels.
- **No reading of the IMS Act of our own:** the app quotes its words where a label check cites them
  (4.1, 4.2), and never says a pack or maker breaks it (D-042).
- **No feeding advice on an infant result at all**, the breastfeeding line included (Sushil, D-140), until
  the lawyer answers whether the result is 7(1) material.
- **Nothing for special medical infant foods** beyond allergens and their own statement.

## 9. Questions for Sushil (and who else)

1. **The IMS Act (a lawyer), with section 5's quotes:**
   a. Could showing an infant food's facts (allergens, label statements found or not found, additives,
      composition), even without ranking, be "promotion" under 2(j) ("any method of encouraging any
      person to purchase or use") or taking part in an "advertisement" "by means of electronic
      transmission" (2(a), 3(a))?
   b. **Does an infant-food result on the app count as "educational or other material ... dealing with
      ... the feeding of an infant and intended to reach pregnant women or mothers of infants" under
      7(1)?** If yes, it must "include clear information relating to" all six particulars (a) to (f), and
      (fa) "the date of printing and publication of such material and the name of the printer and
      publisher", not one breastfeeding line; and 7(2) says such material shall not "be utilised to
      promote the use or sale" of infant foods. If no, may the app add ICMR-NIN's breastfeeding line
      (4.7) on its own?
   c. Does the baby profile's advice on ordinary foods (section 6), or the supplement line for a baby, make
      the app 7(1) material for every result shown to a parent of an infant?
   Recommended meanwhile: section 5 as written (shadow; allergens and one sentence only).
2. **Release:** infant checks, and the breastfeeding line, to users only after 1 is answered?
   Recommended: yes.
3. **Age statement alone** ("from 6 months" on a biscuit): `food` with the baby lines and a reviewer
   check (recommended), or `infant`?
4. **The baby band:** `baby` "Under 2 years" with `toddler` "2 to 3 years" (recommended). Existing
   toddler profiles: ask once on the phone "Is {name} under 2?" or leave them as toddler?
5. **Composition lines (4.5):** show them to users once released, or keep them reviewer-only because a
   number near a legal range reads like a compliance finding? Recommended: reviewer-only in the beta.
6. **Gold labels:** at least 3 baby foods photographed (one in poor light): an infant formula, a
   processed cereal based complementary food, a traditional-ingredient mix. Paid reads asked first.
</content>
</invoke>
