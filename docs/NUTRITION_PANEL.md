# The nutrition table (D-133)

What an Indian pack must print, how InsideLabel reads it, and what it sets beside the numbers.
Written 2026-09-29 from the primary documents, read first-hand that day (D-046):

- **FSSAI L&D 2020:** FSS (Labelling and Display) Regulations 2020, compendium version I
  (23.09.2021), https://www.fssai.gov.in/upload/uploadfiles/files/Compendium_Labelling_Display_23_09_2021.pdf,
  regulation 5(3) (PDF pp. 9 to 13) and regulation 8 (PDF p. 23).
- **ICMR-NIN 2024:** Dietary Guidelines for Indians 2024,
  https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf, pp. 93, 94, 96 (Table 15.1), 107 to 108.
  Printed page = PDF page minus 17.
- **WHO:** fats and carbohydrates guidelines (17 July 2023); salt reduction fact sheet.

## 1. What the pack must print (FSSAI L&D 2020, 5(3))

**Mandatory values** "per 100g or 100ml or per single consumption pack of the product and per
serve percentage (%) contribution to Recommended Dietary Allowance" (5(3)(b)):

| Value | Unit | Notes |
|---|---|---|
| Energy | kcal | |
| Protein | g | |
| Carbohydrate | g | |
| Total sugars | g | |
| Added sugars | g | "monosaccharides and disaccharides added to foods and beverages" (5(3)(a)(ii)) |
| Total fat | g | |
| Saturated fat | g | only if total fat is more than 0.5% of the final food; may be declared "not more than" |
| Trans fat (other than naturally occurring) | g | as saturated fat |
| Cholesterol | mg | only for fats of animal origin, when total fat is more than 0.5% |
| Sodium | mg | |
| Vitamins and minerals | metric units | when declared |

- **Serving:** the panel gives the amount of food in g or ml beside the serving measure, and the
  number of servings in the package (5(3)(b)(iv)).
- **% RDA per serve** is calculated on **2000 kcal energy, 67 g total fat, 22 g saturated fat, 2 g
  trans fat, 50 g added sugar and 2000 mg sodium (5 g salt)** "for average adult per day" (5(3)(b)).
  InsideLabel uses these to check a table's arithmetic (below); it never shows them as advice.
- **Tolerance:** declared nutrients may be up to 10% below the declared value within shelf life
  (5(3)(d)).
- **Energy factors** (5(3)(e)): carbohydrate 4, protein 4, fat 9 kcal per gram (polyols 2,
  erythritol 0, alcohol 7, organic acid 3, dietary fibre 2). InsideLabel uses fat's 9 kcal/g to say
  what share of a food's energy is saturated fat.
- **Oils and fats:** every package of edible oils, interesterified fat, hydrogenated oils, margarine
  and fat spreads, and every food using fats or oils as an ingredient, declares trans fat and
  saturated fat (5(3)(c) proviso).

**Exempt from mandatory nutrition labelling** (5(3)(c)): unprocessed single-ingredient products;
products whose only processing is maturing; waters (carbon dioxide the only addition); herbs, spices
and their mixtures (except sprinkler masala); salt and salt substitutes; table-top sweeteners;
coffee and chicory products; tea and herbal or fruit infusions without other added ingredients;
vinegars; flavourings, additives, processing aids, enzymes, gelatine, yeast; chewing and bubble gum;
alcoholic beverages; FSDU and FSMP foods. These still need the table if they make a nutrition or
health claim. **Small packs** (surface area up to 100 cm2) are exempt from nutritional information,
which then goes on the multi-unit package (regulation 8(1)).

So "no nutrition table in the photo" is often the pack's right: the app asks for one more photo only
as an offer ("If the pack has one, add a photo of it"), never as a refusal.

## 2. How it is read (D-004: AI reads, rules judge)

1. **Gemini copies the table** (prompt rule 10, `nutrition` in the schema): status, the per 100
   heading, the % RDA heading, serving size and servings as printed, and one row per nutrient with
   its label and cells exactly as printed. Paragraph tables ("ENERGY 473.8 kcal (2.8%), ...") are
   rows too. It never computes, rounds or converts. Answers recorded before D-133 have no `nutrition`
   and replay unchanged (D-092).
2. **`lenses/nutrition.py` interprets it**, with `data/nutrition_panel.json`: which row is which
   nutrient (in order, most specific first; "Energy from fat", MUFA, PUFA, vitamins are set aside),
   units (kJ is never converted; sodium in g becomes mg).
3. **Every number is checked; a failed check drops every number it involves:**
   - it appears in the second reading of the same photo (Cloud Vision, or Tesseract, D-093);
   - the printed % RDA fits the per 100 value and the serving size, on FSSAI's bases above (when
     most rows disagree, the serving size is the misread number and only it is dropped);
   - a printed per serving amount fits the per 100 value;
   - total sugars within carbohydrate, added within total sugars, saturated and trans fat within
     total fat (and together within it);
   - salt = sodium x 2.5 when both are printed (WHO: 1 g salt is 400 mg sodium);
   - servings x serving size is within 5% of the net quantity, when all three are read.
   On the four readable gold tables every check passes with nothing dropped.
4. **What the user sees** (`lenses/screen.py`, D-091), per 100 g or 100 ml as printed:
   energy, added sugar (or total sugars, when added isn't printed on its own line), salt worked out
   from sodium, saturated fat with its share of the food's energy, trans fat; the rest in one
   "Also on the table" line. Per serving, for added sugar and salt, the share of the daily amount.
   Numbers that were dropped aren't shown: "We couldn't read the nutrition table clearly, so some of
   its numbers aren't shown."

## 3. What it is set beside (`data/nutrition_thresholds.json`)

| | Solids, per 100 g | Liquids, per 100 ml | Source |
|---|---|---|---|
| Energy | 250 kcal | 70 kcal | ICMR-NIN Table 15.1, p. 96 |
| Salt | 625 mg | 175 mg | ICMR-NIN Table 15.1, p. 96 |
| Added sugar | 3 g | 2.0 g | ICMR-NIN Table 15.1, p. 96 |
| Added fat | 4.2 g | 1.5 g | ICMR-NIN Table 15.1, p. 96: **not applied**, packs print total fat |

Daily, adults: added sugar 25 g (ICMR-NIN p. 94), salt 5 g (ICMR-NIN p. 93; WHO). Saturated fat
no more than 10% and trans fat no more than 1% of daily energy (WHO 2023). No source read gives
children's figures (WHO says only to adjust the adult amount down for ages 2 to 15), so the daily
lines are for adults and say so. Trans fat above zero gets a "Worth a look" tile.

Wording: "Added sugar: 18 g per 100 g. ICMR-NIN counts more than 3 g per 100 g as high." and "One
serving (30 g) has 5.4 g added sugar, about a fifth of the 25 g a day ICMR-NIN counts as high."
Never "unhealthy", "healthy" or "safe" (D-042, D-071); the tests lint every sentence.

## 4. Catalogue and review

- The checked table is stored on the version (`product_versions.nutrition`, migration 018). A
  reviewer sees the rows as printed beside the photo on `/review` and ticks "Every number shown to
  users matches the photo"; unticked, the pack is published without its table. Publishing records
  who confirmed it (`confirmed_by`).
- A pack published before D-133 gets its table when a later scan reads one: a new version (same
  content plus the table) waits for review as kind `nutrition`, and can't be published unticked.
- The review checker (D-117) fails `nutrition_in_ocr` when a number isn't in Cloud Vision's text,
  so a person looks.
- Measuring the reader: `tools/eval_vision.py` reports "nutrition numbers read right" against
  `gold/*.json` "nutrition"; `tools/release_check.py` gates it at 98% (TODO until predictions are
  made with the D-133 prompt).

## 5. Not done, said plainly

- A published table that changes without the ingredients changing isn't noticed (only a missing
  table is filled).
- Tables that aren't per 100 g or 100 ml (small single-consumption packs) aren't used.
- The gold tables were transcribed by Claude from Sushil's photos on 2026-09-29; Britannia's table
  is cut off in its photo (status "unreadable"), Limca 1 L's photo is a render with no table.
