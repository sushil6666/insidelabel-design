# InsideLabel - Product & Engineering Blueprint

**Status:** v1.1 blueprint (2026-09-24), written against the 43-section spec. Sections
where I've overruled the spec are marked **[CHANGED]** with the reasoning. Changes from
the 2026-09-24 user-perspective review are marked **[v1.1]** and point to their
decision in `DECISIONS.md`.

**v1.1 changelog.** Parents become a first-class audience (kids lens, shelf comparison,
household profiles - §1, §7, §15). Allergen safety is the first line of every result,
with a five-state check that never says "free from" (§3.3, §4.2, §7). The headline
states the finding; "nothing wrong" is a designed state; band names are plain words;
the quick signal is per person (§2.3, §6, §7). Comparison, alternatives, browse,
search and safety alerts are free (§8). Online shopping, WhatsApp sharing and Hindi
explanations enter the plan (§7, §9, §13). §15-16 now match `STATE.md`'s 15-week beta.
Also fixed: a false statement about FSSAI sweetener warnings (§7, D-056).

---

## 0. The single most important finding

I modelled the unit economics before writing anything else, because they invalidate
part of the spec.

**Consumer subscriptions at ₹49-99/month will never pay for the AI pipeline as
specified.** At 100K scans/month with realistic Indian conversion (1.5-2%), premium
revenue is roughly ₹10-15K/month against ₹1.2-1.4L/month in cost. At 1M scans/month
the gap widens in absolute terms. This means B2B is not "long-term upside" - it is
*required for viability*, which collides directly with the trust principle in §24.

There is one way out, and it reframes the whole company:

> **InsideLabel is a catalogue company, not an AI company.**

If a product has already been resolved, a scan costs ~₹0.05 (barcode lookup + DB
read). If it hasn't, it costs ~₹2.30 (dual-image OCR + vision verification + LLM
extraction). Indian packaged food is extremely concentrated - Parle, Britannia, ITC,
Nestlé, Mondelez, Amul, Haldiram, PepsiCo/Frito-Lay, Hindustan Unilever and Dabur
cover the large majority of what a middle-class urban shopper actually puts in a
trolley. **Manually seeding the top ~2,000 SKUs before launch converts the dominant
cost line from per-scan AI into one-time labour**, and takes blended cost per scan
from ~₹2.30 to ~₹0.20-0.35.

Everything downstream improves: the free tier is genuinely free, latency drops from
8-15s to under 1s for most scans, verdicts become *consistent* (same product always
gives the same answer - something no LLM-per-scan design can promise), and B2B
becomes optional rather than load-bearing.

**Consequence for the roadmap:** the first two months are not engineering. They are
data entry, with tooling.

---

## 1. Positioning & value proposition

**One line:**
> InsideLabel reads the front and the back of an Indian food package and tells you
> where they disagree.

Not "understand your food." Not "health score." The wedge is the *gap between the
marketing and the ingredient declaration*, because that is the one thing a shopper
cannot do in the aisle in ten seconds and cannot get from a generic AI.

**Ten-second value prop:** "It says No Added Sugar. Here's the sugar."

**[CHANGED] Launch segment.** The spec implies a broad "health-conscious Indian
consumer" audience. That audience scans twice and churns - see §12 on retention.
Launch instead to two segments where label-reading is *non-optional*:

1. **Allergen households** - parents of children with nut/milk/soy allergy, coeliac
   families. They must read every label of every new product, every time.
2. **Diabetic / prediabetic households** - India has the volume, and your existing
   prototype already carries the strongest finding in this category (maltodextrin
   with GI ~85-105 inside a biscuit marketed "Diabetic Friendly").

These users have a *forcing function* to open the app. General wellness users do not.
Broaden later from a retained base, not before.

**[v1.1] Parents of young children** (D-056, D-057). Indian children are exposed to a
lot of packaged food, and parents choose between packs daily. Allergy parents stay the
core; general parents are the wider audience the kids lens and shelf comparison open
up. Their question is not "is this bad?" but **"which one should I pick?"** - so a
warning without an alternative is half a product for them.

**[v1.1] Each segment has a different everyday job.** The claim gap is the hook, not
the daily use:

| Segment | Opens the app to ask | First thing they must see |
|---|---|---|
| Allergy household | "Does this contain milk / nuts / gluten?" | The allergen result for that person |
| Diabetic household | "How much sugar is really in this?" | Sugar position and names; hidden sugars |
| Parent | "Which of these should I buy for my child?" | A named best pick with reasons |
| Casual shopper | "Is the front telling the truth?" | The claim check |

**[v1.1] Most scans will find no contradiction.** The product must still be useful then
(D-062): say what was checked and what matters for this person. If the only value is the
surprise, most scans feel empty.

---

## 2. Architecture corrections to the spec

### [CHANGED] 2.1 Product identity comes from the barcode, not from OCR

The spec's flow places "Identify product" after OCR and before claim extraction. In
practice:

- Barcode is the only reliable product key. It's free to read (on-device, ZXing/MLKit),
  instant, and unambiguous.
- Ingredient/nutrition/image fingerprints are *fallback* matchers for the barcode-less
  or unreadable case, and for detecting reformulation of a known barcode.
- §18 lists the matching signals with fingerprints ahead of barcode. Reverse that
  order: barcode → brand+name+netqty exact → nutrition fingerprint → ingredient
  fingerprint → image embedding. Stop at first confident match.

```
                 ┌── barcode scan (on-device, instant, free)
                 │        └── HIT → serve cached analysis. Done. ~₹0.05, <1s.
  CAMERA ────────┤
                 └── MISS / no barcode
                          ↓
              front image ──→ OCR ──→ claims ─────────┐
              back image  ──→ OCR ──→ ingredients ────┤
                                  └──→ nutrition ─────┤
                                  └──→ regulatory ────┤
                                                      ↓
                                        normalization + confidence gate
                                                      ↓
                                   ┌──────────────────┴──────────────────┐
                                   │  CLAIM ↔ LABEL RULE ENGINE          │
                                   │  (versioned, citation-pinned)       │
                                   └──────────────────┬──────────────────┘
                                                      ↓
                                          findings + evidence rows
                                                      ↓
                                     write to catalogue (new product_version)
                                                      ↓
                              interpretation layer (deterministic, segment lenses)
```

### [CHANGED] 2.2 Front and back are parallel, not sequential

The spec's §1 flow chains claims → ingredients. They're independent extractions from
different images that *meet* at the rule engine. The distinction matters
operationally: a scan with a good back image and a blurry front image should still
return full ingredient intelligence with claims marked unavailable. Never block the
whole result on one image.

### [CHANGED] 2.3 Kill the numeric score from the consumer UI

§12 says don't create a single health score. Your prototype currently shows a 0-100
score, an A-E grade, *and* a "Risk Index 7.2/10". All three are the same arbitrary
weight table rendered three ways, and the risk index is the worst offender - one
decimal place of implied precision on a number derived from `{none:0, low:4,
moderate:12, high:25}`. That is exactly the false precision §12 warns against, and
it's the single easiest thing for a brand's lawyer or a journalist to dismantle.

Keep:
- **The three-band verdict** (Clean / Worth checking / Ultra-processed). Defensible
  because the ultra-processed band is *definitional* - NOVA Group-4 marker present or
  not - not a weighted opinion.
- **Flag counts by severity**, shown as "2 things worth knowing, 1 claim to check."

Move the 0-100 score to internal/admin use for ranking alternatives and for
regression-testing rule changes. Never show it. Never expose it in the B2B product.

**[v1.1] Band display names** (D-063). Most biscuits and namkeen land in the
ultra-processed band, so the band alone stops telling users anything, and "Clean"
sounds like "safe to eat freely". Logic unchanged; labels become: **"No concerns found
in the ingredients"** · **"A few things worth knowing"** · **"Made with industrial
ingredients"** (the NOVA term and definition one tap away).

**[v1.1] The quick signal is per person** (D-064, resolves D-050). With the score gone,
the glanceable answer is a status per household profile: "Contains milk - on Aarav's
avoid list", "Fewer concerns for kids".

### [CHANGED] 2.4 Flat "flagged ingredient count" is invalid for comparison

§20/§21 propose "Brand A - 3 flagged attributes vs Brand B - 1". Three low-concern
emulsifiers is a cleaner product than one sodium nitrite. Your own concern weights
exist precisely so you never do a flat count. Comparisons must use the weighted
internal score plus the band, and must show the per-ingredient receipts alongside.

**[v1.1]** Shelf comparison (`compare.py`, D-057) ranks by **concern tiers**, compared
in order: strong-tier facts, then moderate, then how early sugar appears, then
ultra-processing markers. Low/none-concern additives don't count at all, so one
nitrite always outranks three emulsifiers, and no weighted number is involved. Allergen
conflicts remove a pack from ranking entirely.

### 2.5 Separate the two layers physically, not just logically

§24 asks for safeguards. Make them structural:

| | Consumer Truth Layer | B2B Analytics Layer |
|---|---|---|
| Database | Postgres primary (`products`, `findings`, `rules`) | Separate warehouse, read-only ETL |
| Write path | Internal reviewers + rule engine only | No write path to truth layer. Ever. |
| Access | - | Brands never see their own score, never see pre-publication findings, never have a contest/appeal channel into a verdict |
| Audit | Every rule change is a signed, versioned row with author and reviewer | Every B2B query logged |

This maps well onto your existing stack instincts: Postgres for the transactional
truth layer, and dbt/Snowflake for the analytics layer - which is genuinely your
strongest technical edge here, and it's on the *right* side of the wall.

---

## 3. The claim ↔ label rule engine (the actual differentiator)

This is the part worth building carefully, because it is the part Gemini cannot do
consistently.

### 3.1 Many Indian claims are legally defined - use that

The **Food Safety and Standards (Advertising and Claims) Regulations, 2018** govern
nutrition claims, health claims and "non-addition" claims in India, and <cite index="13-1">FSSAI published a final amendment on 13 December 2022 (notification No. Std/EC/T(NSF-01)) revising the general principles for claims, nutrition claims, non-addition claims, and Schedules I (nutrient content claims), II (synonyms used for claims) and III (reduction of disease risk claims)</cite>. <cite index="8-1">A "high protein" or "no added sugar" claim on an Indian label is a legal statement backed by verifiable data requirements under those regulations together with the Food Safety and Standards (Labelling and Display) Regulations, 2020</cite>.

This means your contradiction engine does **not** have to hedge everything into
"potential inconsistency." Where Schedule I sets a numeric threshold, you can state a
verifiable comparison: *the label claims X; Schedule I defines X as ≥N per 100g; the
declared panel says M*. That is a fact with a citation, not an AI opinion.

**Hard requirement:** retrieve the current Schedule I and Schedule II text (2022
amendment, plus any later amendment) and populate `claim_criteria` from it directly.
Do not hardcode remembered thresholds - mine or anyone's. Schedule II is especially
valuable: it enumerates *permitted synonyms* for claims, which is exactly the alias
table your claim extractor needs, written by the regulator.

### 3.2 Rule tiers

| Tier | Basis | Wording | Example |
|---|---|---|---|
| **R1 - Regulatory, numeric** | Schedule I threshold + declared nutrition panel | "The label claims *High Protein*. FSSAI Schedule I defines this as ≥N g/100g. The panel declares M g/100g." | High protein with 2g/serving |
| **R2 - Regulatory, non-addition** | Non-addition claim + ingredient declaration | "The label claims *No Added Sugar*. The ingredient list declares *glucose syrup*." | The killer case |
| **R3 - Definitional** | NOVA Group-4 marker present | "Contains an ultra-processing marker." | Already built |
| **R4 - Unregulated marketing** | Claim with no legal definition | "*Healthy* is not a defined claim under Indian regulation. Here's what the label actually declares." | "Healthy", "Immunity", "Goodness of…" |
| **R5 - Consumer preference** | User's stated avoid-list | "Contains palm oil, which you asked to avoid." | Personalization |

R1/R2 are strong, citable, and legally safe when worded as a comparison rather than a
verdict. R4 is *rhetorically* your best material - telling a shopper that "Healthy" is
not a regulated word in India is genuinely useful and completely unfalsifiable.

### 3.3 Wording discipline (non-negotiable)

Allowed: "The label claims X. The declaration says Y." / "Worth checking before
buying." / "X is not a defined claim under Indian regulation."

Forbidden: "misleading", "false", "illegal", "non-compliant", "violation", "lying",
"toxic", "dangerous", "poison", and any statement about the *brand* rather than the
*label*. Product disparagement is live litigation territory in India; comparative
brand tables are what gets sued over. Enforce this as a lint rule over the content
tables in CI, not as a style guide humans are asked to remember.

**[v1.1] Allergen wording** (D-071). Also forbidden in allergen output: "free from",
"allergen-free", "safe". The strongest negative is *"Milk isn't listed in the
ingredients or the allergen line."* Ambiguous sources get *"We can't tell whether
'lecithin' comes from soy."*

**[v1.1] "What the rule says"** (D-066). Where an R2 finding has a verified citation,
add one neutral line on what the regulation defines, so the user isn't left asking "is
that allowed?". R4 shows in full the first time a user meets that claim type, and
compact after that - interesting once, preachy by the tenth time.

**[v1.1] No legal claim without a verified citation - including in lens text.** The
first kids-lens draft said Indian rules require sweetened packs to carry "Not
recommended for children". FSSAI's labelling FAQ (June 2022) says sucralose no longer
needs a warning statement. The line is gone; sweeteners are stated as facts (D-056).

### 3.4 Every finding is a row, not a sentence

```
finding = {
  id, product_version_id, rule_id, rule_version,
  kind: fact | inference | potential_concern | regulatory_context | preference | uncertainty,
  severity: info | worth_knowing | check_before_buying,
  confidence: 0.0-1.0,
  evidence: [evidence_id, ...],          # ≥1 required, enforced by FK + check
  citation_ids: [...],                   # ≥1 required for R1/R2/R3
  generated_at, generator: rule_engine | reviewer
}
```

A finding with zero evidence rows cannot be inserted. A finding with an unpinned
citation cannot be rendered to a consumer - which is the formalisation of the
verified/unverified chip distinction you already built into `SrcChip`. That mechanism
is one of the best things in the prototype; make it a database constraint instead of a
rendering nicety.

---

## 4. AI / vision pipeline

### 4.1 Four-stage cost ladder

| Stage | Runs on | What | Cost/scan | Purpose |
|---|---|---|---|---|
| **0. On-device** | Phone | Barcode decode, blur/glare/exposure check, perspective correction, crop, compress to ~250KB | ₹0 | Reject bad images *before upload*. Critical on Indian mobile data. |
| **1. Cheap OCR** | Cloud OCR (document text detection) | Raw text + per-block confidence + bounding boxes | ~₹0.27 (2 images) | 80% of extraction |
| **2. Deterministic parse** | Your Python | INS/E numbers, sugar aliases, nutrition table regex, claim synonym match (Schedule II), FSSAI licence number, net qty, MRP | ₹0 | Everything with a known shape |
| **3. VLM fallback** | Vision-language model | Only when: OCR block confidence < threshold, nutrition table unparsed, ingredient list truncated, or unknown token density > threshold | ~₹1.20-1.80 | The hard 20% |

Cache key is `(barcode)` or `(brand, name, net_qty)`, versioned. Stages 1-3 run **once
per product version**, not once per scan. Personalization (lenses) is deterministic
and runs per user at read time for free.

### 4.2 Confidence gate and retry

```
per-field confidence = min(ocr_block_confidence, parser_confidence, vlm_agreement)

if ingredient_list.confidence < 0.85:
    → do not interpret. Return retake prompt with the SPECIFIC problem:
      "The ingredient list is cut off on the right - try landscape."
      "Too much glare on the panel - tilt away from the light."
if nutrition_table.confidence < 0.85:
    → return ingredient analysis, mark nutrition unavailable, suppress all R1 rules
if front_image missing/low:
    → return ingredient analysis, mark claims unavailable, suppress R1/R2/R4
```

**[v1.1] Allergen gate** (D-072). Allergen output needs ingredient confidence ≥ 0.95
and a reliable scan; below that the state is *cannot_confirm* and the user gets a
retake prompt. A missed "milk solids" is a hospital visit, not a wrong verdict. Starting
value, to calibrate once allergen fields are in the gold set.

**Retry strategy:** maximum two automatic retries with different preprocessing
(contrast stretch, then 2× upscale). After that, prompt the human - and offer
**[v1.1] "Send it to us - we'll check this pack and tell you when it's ready"** (D-070;
nobody types a 20-item list on a phone) plus "this product is already in our
catalogue, is this it?" with candidates. Never silently degrade confidence into a confident answer. A bad OCR that
becomes a health statement is the one failure mode that ends the company's
credibility permanently.

### 4.3 Model strategy

Wrap every model behind one interface so swapping is config, not code:

```python
class OCRProvider(Protocol):
    def extract(self, image: bytes) -> OCRResult: ...
class VisionProvider(Protocol):
    def extract_structured(self, images: list[bytes], schema: dict) -> StructuredResult: ...
```

Pin a model version per `product_version` row, so you can tell later whether a wrong
verdict came from a model change. Use deterministic code wherever the shape is known -
INS numbers, nutrition tables, FSSAI licence formats are all regex problems, not AI
problems. **No vector database at launch.** Ingredient alias matching is a
`pg_trgm` + alias-table problem; embeddings only earn their place later for free-text
consumer questions, and even then pgvector inside Postgres is enough.

---

## 5. Database schema

Postgres primary. Object storage (S3/R2) for images. Redis for hot product cache and
rate limits. No warehouse until B2B is real.

```sql
-- ============ CATALOGUE ============
CREATE TABLE brands (
  id            bigserial PRIMARY KEY,
  name          text NOT NULL,
  parent_company text,
  country       text DEFAULT 'IN',
  UNIQUE (name, country)
);

CREATE TABLE products (
  id            bigserial PRIMARY KEY,
  barcode       text UNIQUE,                 -- nullable; the only reliable key
  brand_id      bigint REFERENCES brands(id),
  name          text NOT NULL,
  variant       text,
  category_id   bigint REFERENCES categories(id),
  net_qty_value numeric, net_qty_unit text,
  country       text DEFAULT 'IN',
  current_version_id bigint,                 -- FK set after version insert
  scan_count    bigint DEFAULT 0,
  created_at    timestamptz DEFAULT now()
);
CREATE INDEX ON products (brand_id, category_id);
CREATE INDEX products_name_trgm ON products USING gin (name gin_trgm_ops);

-- Labels change. Formulations change silently. Versioning is not optional.
CREATE TABLE product_versions (
  id               bigserial PRIMARY KEY,
  product_id       bigint NOT NULL REFERENCES products(id),
  version_no       int NOT NULL,
  ingredients_raw  text,
  ingredients_hash text,           -- fingerprint: detects reformulation
  nutrition_hash   text,
  claims_hash      text,
  front_image_key  text, back_image_key text,
  data_confidence  numeric,
  source           text,           -- 'seed' | 'scan' | 'reviewer' | 'brand_submitted'
  verified_by      bigint REFERENCES reviewers(id),
  verified_at      timestamptz,
  superseded_at    timestamptz,
  created_at       timestamptz DEFAULT now(),
  UNIQUE (product_id, version_no)
);
CREATE INDEX ON product_versions (ingredients_hash);

CREATE TABLE product_ingredients (       -- ordered, as declared
  product_version_id bigint REFERENCES product_versions(id),
  position           int NOT NULL,
  raw_text           text NOT NULL,      -- always keep the label's own spelling
  ingredient_id      bigint REFERENCES ingredient_master(id),
  match_method       text,               -- 'ins' | 'alias' | 'trgm' | 'vlm' | 'unmatched'
  match_confidence   numeric,
  PRIMARY KEY (product_version_id, position)
);

CREATE TABLE product_nutrition (
  product_version_id bigint PRIMARY KEY REFERENCES product_versions(id),
  basis              text NOT NULL,      -- 'per_100g' | 'per_100ml' | 'per_serve'
  serving_size_g     numeric,
  energy_kcal numeric, protein_g numeric, carb_g numeric,
  total_sugar_g numeric, added_sugar_g numeric, fibre_g numeric,
  total_fat_g numeric, sat_fat_g numeric, trans_fat_g numeric,
  sodium_mg numeric,
  confidence numeric
);

-- Regulatory/label info kept SEPARATE from product intelligence (spec §5)
CREATE TABLE product_label_meta (
  product_version_id bigint PRIMARY KEY REFERENCES product_versions(id),
  manufacturer text, packer text, country_of_origin text,
  fssai_licence_no text, mrp_inr numeric, batch_no text,
  mfg_date date, best_before text, veg_nonveg text
);

-- ============ INGREDIENT KNOWLEDGE (the moat) ============
CREATE TABLE ingredient_master (
  id            bigserial PRIMARY KEY,
  canonical_name text NOT NULL UNIQUE,
  ins_number    text,
  e_number      text,
  functional_class text,          -- colour | preservative | emulsifier | sweetener | ...
  nova_marker_id bigint REFERENCES nova_markers(id),
  is_additive   boolean DEFAULT false
);
CREATE INDEX ON ingredient_master (ins_number);

CREATE TABLE ingredient_aliases (
  id bigserial PRIMARY KEY,
  ingredient_id bigint NOT NULL REFERENCES ingredient_master(id),
  alias text NOT NULL,
  locale text DEFAULT 'en-IN',
  alias_type text,   -- 'ins' | 'trade' | 'common' | 'misspelling' | 'regional'
  UNIQUE (alias, locale)
);
CREATE INDEX ingredient_aliases_trgm ON ingredient_aliases USING gin (alias gin_trgm_ops);
-- Seed note: your prototype already found that Indian labels write "soya"
-- almost universally. Every such discovery becomes a row here, permanently.

CREATE TABLE ingredient_explanations (
  ingredient_id bigint REFERENCES ingredient_master(id),
  locale        text DEFAULT 'en-IN',
  what_it_is    text NOT NULL,
  why_used      text NOT NULL,
  worth_knowing text,
  evidence_strength text,      -- 'strong' | 'moderate' | 'limited' | 'contested'
  version int NOT NULL, reviewed_by bigint, reviewed_at timestamptz,
  PRIMARY KEY (ingredient_id, locale, version)
);

CREATE TABLE ingredient_regulatory_status (
  id bigserial PRIMARY KEY,
  ingredient_id bigint REFERENCES ingredient_master(id),
  jurisdiction  text NOT NULL,           -- 'IN' | 'EU' | 'US' | 'WHO'
  status        text NOT NULL,           -- 'permitted' | 'permitted_with_limits' | 'banned' | 'unverified'
  limit_note    text,
  citation_id   bigint REFERENCES citations(id),   -- NOT NULL for any public claim
  verified_at   date,
  UNIQUE (ingredient_id, jurisdiction)
);
-- CHECK: no row may be surfaced to a consumer with status IN ('banned')
-- unless citation_id IS NOT NULL AND verified_at > now() - interval '18 months'

CREATE TABLE citations (
  id bigserial PRIMARY KEY,
  label text NOT NULL,         -- 'FSSAI' | 'WHO' | 'INASL' | ...
  title text NOT NULL,
  url   text NOT NULL,
  document_date date,
  verified_at date NOT NULL,
  verified_by bigint REFERENCES reviewers(id)
);
-- Per-document, never per-institution. WHO has multiple documents with
-- different numbers; they get different rows. (Already correct in the prototype.)

-- ============ CLAIMS & RULES ============
CREATE TABLE claim_types (
  id bigserial PRIMARY KEY,
  code text UNIQUE,                     -- 'HIGH_PROTEIN' | 'NO_ADDED_SUGAR' | 'HEALTHY'
  display_name text,
  claim_class text NOT NULL,            -- marketing | nutrition | health | ingredient
                                        -- | comparative | non_addition | unknown
  is_regulated boolean NOT NULL
);

CREATE TABLE claim_synonyms (           -- seed from FSSAI Schedule II + observed labels
  claim_type_id bigint REFERENCES claim_types(id),
  phrase text NOT NULL, locale text DEFAULT 'en-IN',
  PRIMARY KEY (phrase, locale)
);

CREATE TABLE claim_criteria (           -- seed from FSSAI Schedule I. Do not hardcode.
  id bigserial PRIMARY KEY,
  claim_type_id bigint REFERENCES claim_types(id),
  jurisdiction text DEFAULT 'IN',
  nutrient text, comparator text, threshold numeric, unit text, basis text,
  citation_id bigint NOT NULL REFERENCES citations(id),
  effective_from date, version int NOT NULL
);

CREATE TABLE rules (
  id bigserial PRIMARY KEY,
  code text NOT NULL,                   -- 'RULE-CLAIM-001'
  version text NOT NULL,                -- '1.3'
  tier text NOT NULL,                   -- R1..R5
  logic jsonb NOT NULL,
  wording_template text NOT NULL,
  severity text NOT NULL,
  citation_id bigint REFERENCES citations(id),
  author bigint, reviewed_by bigint, last_reviewed date,
  active boolean DEFAULT true,
  UNIQUE (code, version)
);

CREATE TABLE product_claims (
  id bigserial PRIMARY KEY,
  product_version_id bigint REFERENCES product_versions(id),
  claim_type_id bigint REFERENCES claim_types(id),
  raw_text text NOT NULL,               -- exactly as printed
  source text NOT NULL,                 -- 'front_image' | 'back_image'
  bbox jsonb, confidence numeric
);

-- ============ FINDINGS & EVIDENCE ============
CREATE TABLE evidence (
  id bigserial PRIMARY KEY,
  product_version_id bigint REFERENCES product_versions(id),
  kind text NOT NULL,                   -- 'ingredient' | 'nutrition' | 'claim' | 'citation'
  pointer jsonb NOT NULL,               -- {ingredient_position: 7} / {field:'sodium_mg'}
  quoted_text text,                     -- the label's own words
  image_key text, bbox jsonb            -- lets the UI show the actual pixels
);

CREATE TABLE findings (
  id bigserial PRIMARY KEY,
  product_version_id bigint NOT NULL REFERENCES product_versions(id),
  rule_id bigint NOT NULL REFERENCES rules(id),
  kind text NOT NULL,        -- fact|inference|potential_concern|regulatory_context
                             -- |preference|uncertainty
  severity text NOT NULL, confidence numeric NOT NULL,
  rendered_text text NOT NULL,
  created_at timestamptz DEFAULT now()
);
CREATE TABLE finding_evidence (
  finding_id bigint REFERENCES findings(id) ON DELETE CASCADE,
  evidence_id bigint REFERENCES evidence(id),
  PRIMARY KEY (finding_id, evidence_id)
);
-- Enforce ≥1 evidence row per finding via deferred constraint trigger.
-- A finding without receipts must be impossible, not merely discouraged.

-- ============ USERS & SCANS ============
CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz DEFAULT now(),
  auth_provider text, tier text DEFAULT 'free'
  -- No name, no email until they ask for sync. PII minimisation from day one.
);

CREATE TABLE user_preferences (
  user_id uuid PRIMARY KEY REFERENCES users(id),
  avoid_ingredient_ids bigint[],
  allergen_codes text[],
  diet text[],                    -- veg | vegan | jain | eggetarian
  lens_age text, lens_repro text, lens_metabolic text, lens_goal text
);

-- [v1.1] Household profiles (D-074). Up to 3 in the beta. No names: the nickname
-- ("Riya") lives on the device only. Children's data under the DPDP Act, so the
-- server holds an age band, never a date of birth.
CREATE TABLE user_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id),
  age_band text,                  -- toddler | kid | young | adult | older
  allergen_codes text[],          -- allergens.json codes
  strict_may_contain boolean DEFAULT true,
  lens_repro text, lens_metabolic text, lens_goal text,
  consent_at timestamptz NOT NULL -- parental consent recorded at creation
);

CREATE TABLE scans (
  id uuid PRIMARY KEY,
  user_id uuid REFERENCES users(id),
  product_version_id bigint REFERENCES product_versions(id),
  resolved_via text,              -- 'barcode' | 'fingerprint' | 'new_product' | 'failed'
  cache_hit boolean,
  front_image_key text, back_image_key text,
  latency_ms int, ai_cost_paise int,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON scans (user_id, created_at DESC);
CREATE INDEX ON scans (product_version_id, created_at DESC);
-- Images: delete originals after 30 days unless flagged for review.
-- [v1.1] (D-080) Keep the label-region crops used as evidence; seed/reviewer photos
-- are kept in full (D-028). Implement as an R2 lifecycle rule on the originals prefix.

CREATE TABLE corrections (
  id bigserial PRIMARY KEY,
  scan_id uuid REFERENCES scans(id),
  user_id uuid REFERENCES users(id),
  field text NOT NULL, proposed_value text NOT NULL,
  status text DEFAULT 'pending',  -- pending|accepted|rejected|duplicate
  reviewed_by bigint, reviewed_at timestamptz
);
```

**Reformulation detection**, which is a genuinely unique feature: a scan whose
`ingredients_hash` differs from the current `product_versions` row for that barcode
creates a new version and fires an alert to everyone who saved that product. Brands
reformulate silently and constantly. Nobody tells the consumer. You can.

---

## 6. API contracts

```http
POST /v1/scan
Content-Type: application/json
{
  "barcode": "8901063012345",          // optional
  "front_image_key": "up/a1b2.jpg",    // optional; presigned-uploaded
  "back_image_key": "up/c3d4.jpg",
  "client": {"app_version":"1.2.0","net":"3g"}
}

202 Accepted    (cache miss - async)
{ "scan_id":"...", "status":"processing", "poll_after_ms":1200,
  "partial": {"product":{"name":"...","brand":"..."},"resolved_via":"barcode"} }

200 OK          (cache hit - the common case)
{
  "scan_id": "...",
  "status": "complete",
  "resolved_via": "barcode",
  "product": { "id": 4471, "version": 3, "name":"Cream Biscuit 150g",
               "brand":"...", "last_verified":"2026-08-14",
               "data_confidence": 0.94 },
  "verdict": { "band":"worth_checking",
               "band_label":"A few things worth knowing",          // [v1.1] D-063
               "headline":"Says 'No Artificial Flavours', but lists artificial flavours",
               "summary":"1 claim to check, 3 things worth knowing" },  // [v1.1] D-061
  "profiles": [{                       // [v1.1] D-060, D-064: rendered FIRST
      "profile_id":"...", "status":"blocked",
      "allergens":[{"code":"milk","state":"contains",
                    "evidence":"Milk solids (4%)"}],
      "text":"Contains milk. It's on Riya's avoid list." }],
  "last_verified": "2026-08-14",       // [v1.1] D-073
  "recheck_suggested": true,           // [v1.1] cache hit + avoid-list profile
  "claim_checks": [{
      "claim": {"raw_text":"No Artificial Flavours","class":"non_addition",
                "is_regulated": true},
      "status": "potential_inconsistency",
      "rule": {"code":"RULE-CLAIM-002","version":"1.1","tier":"R2"},
      "text": "The label claims No Artificial Flavours. The ingredient list declares Added flavours (natural and artificial).",
      "confidence": 0.93,
      "evidence": [
        {"kind":"claim","quoted_text":"No Artificial Flavours","source":"front_image",
         "bbox":[...]},
        {"kind":"ingredient","quoted_text":"Added flavours (natural and artificial)",
         "position":9,"source":"back_image","bbox":[...]}
      ],
      "citations":[{"label":"FSSAI","title":"Advertising and Claims Regulations 2018 (as amended 2022)","url":"..."}]
  }],
  "findings": [{
      "kind":"fact", "severity":"worth_knowing",
      "text":"Sugar appears under 2 names: sugar, invert syrup.",
      "evidence":[...], "citations":[]
  }],
  "ingredients": [{
      "position":1,"raw_text":"Refined wheat flour (maida)",
      "ingredient_id":88,"matched":true,"flagged":false
  }],
  "nutrition": { "basis":"per_100g","available":true, "...":"..." },
  "unavailable": [],                  // e.g. ["nutrition"] when OCR failed that block
  "personalized": null,               // populated only if user has preferences
  "ordinary_count": 12                // [v1.1] D-065: "12 other ingredients look ordinary"
}

200 OK          (low confidence - never guess)
{ "scan_id":"...","status":"needs_retake",
  "reason":"ingredient_list_truncated",
  "message":"The ingredient list looks cut off on the right side. Try holding the pack landscape.",
  "partial": {"product": {...}, "claims":[...]},
  "alternatives":[{"action":"confirm_product","candidates":[{"id":4471,"name":"..."}]},
                  {"action":"send_for_review"}]   // [v1.1] D-070, replaces type_ingredients
}
```

Other endpoints, thin by design:

| Endpoint | Notes |
|---|---|
| `POST /v1/products/match` | fingerprint/dedup resolution; internal + client fallback |
| `GET /v1/products/{id}/analysis?version=` | cached, CDN-able, 24h TTL |
| `GET /v1/products/{id}/evidence/{finding_id}` | the "why did you flag this?" tap |
| `GET /v1/ingredients/{id}` | explanation + regulatory status + citations |
| `POST /v1/feedback` | corrections → review queue |
| `POST /v1/compare` | **[v1.1] free** (D-059); body: `{scan_ids or product_ids:[2-4], profile_id}` - shelf comparison (D-057) |
| `GET /v1/alternatives?product_id=` | **[v1.1] free**; **requires populated category** (≥80%) |
| `GET /v1/search?q=` | **[v1.1] free** name search over the catalogue (D-059) |
| `POST /v1/recheck` | **[v1.1]** one back photo vs cached version (D-073) |
| `GET/PUT /v1/user/profiles` | **[v1.1]** household profiles (D-074) |
| `GET /v1/user/history`, `GET/PUT /v1/user/preferences` | |

Versioned from `/v1` because the B2B API is the same surface later. Rate limit free
tier by device+IP, not by user, because abuse comes from unauthenticated scan spam.

---

## 7. Consumer screens

Progressive disclosure, four depths. Target: **first useful pixel under 1.5s on a
cache hit**; never a blank spinner.

0. **[v1.1] First run** (D-069) - "Scan 3 packs from your kitchen." Then offer a
   household profile: nickname (device only), age band, avoid list.

1. **Camera** - single screen, barcode reader always live. Copy: "Point at the
   barcode, or photograph the back of the pack." **[v1.1]** Show a sample photo of
   "the side that says Ingredients", and while a cache miss processes, show real
   progress and "First time we've seen this pack. Next time it's instant, for
   everyone." (D-068) Live quality feedback (glare/blur
   warnings) *before* the shutter, not after upload. Two-shot guided flow (back first -
   it's the valuable one), front optional and skippable.

2. **Verdict** - **[v1.1] order: per-person safety line → headline finding → claim
   checks → things worth knowing → ingredient list** (D-060). No score. No ring gauge.
   The headline states the finding in plain words (D-061). Ordinary additives collapse
   to "12 other ingredients look ordinary" (D-065). Band labels per D-063. For a
   casual shopper the claim check card is still the surprise that drives the share;
   for an allergy parent the safety line is the whole point.

   **[v1.1] "Nothing wrong" state** (D-062): "We checked the ingredients. For Riya:
   sugar is the 2nd ingredient; no colours or sweeteners." Say "the front matches the
   back" only when the claim checker actually ran on a paired front image.

3. **Why** - tap any row: plain-language explanation, the exact quoted label text, and
   **a crop of the actual photo with the phrase boxed**. Showing the pixels is worth
   more for trust than any amount of confidence scoring.

4. **Ingredient detail** - what it is / why it's used / worth knowing / regulatory
   status, with linked citations. Verified citations link out; unverified ones render
   as plain text, exactly as your prototype already does.

5. **Personalization** (free for safety-relevant lenses) - allergens, diet, age,
   pregnancy, metabolic. Framed as "based on your preferences", never "this product is
   unhealthy." **[v1.1]** Diabetic and pregnancy lenses say "ask your doctor about
   quantity" once, clearly, on the lens intro - not on every screen (D-067).

6. **[v1.1] Shelf comparison** (D-057) - "Not sure? Scan 2 or 3 other packs on this
   shelf." Returns a named best pick with reasons, packs that are "not for Riya",
   packs to check before buying, and packs we couldn't compare ("we won't guess").
   Works with zero catalogue, because the parent brings the candidates.

7. **[v1.1] Allergy re-check** (D-073) - on a cache hit for an avoid-list profile:
   "Label last verified on 14 Aug. Recipes change - snap the back to re-check."

8. **[v1.1] Trust pages** (D-076) - conflict-of-interest policy, methodology, who is
   behind the app, and "Report a mistake" on every result. Live from the first beta
   user.

9. **[v1.1] Share card** (D-078, after the beta) - built for WhatsApp family groups:
   vertical, readable on a small phone, Hindi option, "check your own" link, wording
   linted like everything else.

10. **[v1.1] Online orders** (D-077, after the beta) - share a Blinkit / Zepto /
    BigBasket product screenshot into the app via the Android share target; plus free
    name search.

**[CHANGED] Low-bandwidth design.** §25 mentions it but nothing in the spec addresses
it. Uploading two photos over congested 3G in a supermarket basement is the actual UX
killer. Mitigations: barcode-first (zero upload for cache hits), on-device compression
to ≤250KB, WebP, resumable upload, optimistic local render of the cached product
while nutrition loads, and a full offline queue - scan now, results when you have
signal. Build the PWA first; native Android only after retention is proven.

---

## 8. Free vs Premium

**[CHANGED] Principle: paywall convenience, never facts or safety.**

**[v1.1] Table updated** (D-059, D-075, D-074). Premium's final shape is open (D-082).

| Free | Premium (₹399-499/**year**, scope per D-082) |
|---|---|
| Unlimited scans | Full scan history & export |
| All ingredient facts and explanations | Saved products + shopping lists |
| All claim checks | Formulation-change alerts on saved products that *don't* touch an avoid list |
| All allergen and diet filters | Households beyond 3 profiles |
| Age / pregnancy / metabolic / kids lenses | |
| Evidence and citations | |
| Shelf comparison and "Find a better alternative" | |
| Category browse and name search | |
| Household profiles (up to 3) | |
| **Safety alerts:** any reformulation touching an avoid list or allergen | |

**Two corrections to §14/§15.** First, "unlimited scans" as a premium feature
contradicts "don't paywall the core scan" - and throttling scans starves the catalogue,
which is your actual asset. Scans stay uncapped and free forever. Second, ₹49-99/month
converts badly in India; annual pricing is how Indian consumer utilities actually
convert, and it matches a product people use a few times a month rather than daily.

**Never monetizable in any form:** "Find a better alternative", alternative ranking,
and category browse. These are the first things paid placement would corrupt, and
they're the features users would most trust you for. Say so publicly.

---

## 9. Retention - the question the spec doesn't answer

§40 asks why someone scans the *second* product. It's the right question and the spec
doesn't answer it. Honest arithmetic: a household buys maybe 25-40 distinct packaged
SKUs, mostly repeats. Scan each once and the app has nothing left to do. Natural
frequency settles around 2-4 scans/month. That is a churn machine.

Four mechanisms that actually generate return visits, in order of strength:

1. **Allergen/medical necessity** (launch wedge) - a forcing function, not a habit to
   be built. Every new product, every time, non-negotiable.
2. **Formulation-change alerts** - the one thing genuinely impossible for the user to
   do themselves. Requires the versioned catalogue you're building anyway. Turns a
   one-off scan into a standing subscription to that product.
3. **Category browse without scanning** - "show me the biscuit aisle sorted by claim
   consistency." Shifts value from *scan-utility* to *shelf-utility*, and works at home
   before shopping, not just in the aisle.
4. **Household profiles** - one scan answers four different questions (toddler, diabetic
   parent, pregnant sister, self). Multiplies the value per scan. **[v1.1]** Minimal
   version in the beta (D-074).

**[v1.1] Parent moments that bring people back:** a child asking for a new snack, school
tiffin planning, festival gift boxes around Diwali, and the shelf comparison itself
(D-057). Use them in beta recruitment messaging; no features built for them during the
beta (D-083).

**[v1.1] The aisle is shrinking.** Urban parents increasingly buy on quick-commerce apps
and never hold the pack before ordering. Checking before ordering needs the share-target
path and name search (D-077, D-059) - otherwise the app only works after the purchase.

**[v1.1] Safety alerts are free** (D-075). Formulation alerts are mechanism #2 above;
paywalling them would hide the very thing the beta is testing.

**[CHANGED] Cut the reward/streak system in §35 entirely.** "Scan your first product →
unlock ₹10 credit" is exactly the manipulative gamification the same section warns
against, and worse: it incentivises garbage scans, which poison the catalogue you're
paying to build. Reward *corrections* instead - accepted correction → free premium
month. That pays for data quality rather than noise.

---

## 10. B2B - narrower than the spec, and firewalled

Only build after 500K+ scans/month with meaningful per-SKU density. Before that there
is nothing to sell: an FMCG category manager needs roughly 20K+ scans on *their own
SKU* before the data beats their existing panel research.

**[CHANGED] What brands may buy:** aggregate category intelligence only.
- Category scan volume and trend
- Which ingredients consumers most often tap "why is this flagged" on, by category
- Which claim types get questioned most, by category
- Anonymised, k-anonymity ≥ 50 per cell, differential noise on small cells

**What brands may never buy or see:** their own product's verdict, findings ahead of
publication, any appeal channel into a rule, any influence on alternatives or ranking,
any individual user data.

**Better buyers with no conflict at all** - and worth pursuing *first*:
- Health/fitness and diabetes-management apps → **engine API licence**
- Retailers and quick-commerce (shelf/PLP enrichment)
- Hospital dietetics and corporate wellness
- Market research firms buying category trend reports

Publish the conflict-of-interest policy on the site before taking the first rupee.
**[v1.1]** Earlier still: at beta launch (D-076), because for users "no brand can pay
us" is the reason to trust a new app.
Yuka's public refusal of brand money is a marketing asset, not a sacrifice. The
policy's value is entirely in having committed to it *early*.

---

## 11. Unit economics

**Assumptions, stated plainly:** cloud OCR ~₹0.135/image; VLM fallback ~₹1.50/call;
small-LLM structured extraction ~₹0.20/call; 2 images/scan; ₹88/USD. Cache-hit scans
cost only a DB read + CDN. Reviewer cost ₹35K/month FTE. Premium conversion 1.5% of
MAU at 10K/100K scale, 2.0% at 1M. MAU ≈ scans/month ÷ 4. Annual plan ₹449.

| | 10K scans/mo | 100K scans/mo | 1M scans/mo |
|---|---|---|---|
| Cache-hit rate | 35% | 70% | 88% |
| Full-pipeline scans | 6,500 | 30,000 | 120,000 |
| AI cost | ₹15,000 | ₹69,000 | ₹2,76,000 |
| Storage + CDN + egress | ₹1,200 | ₹9,000 | ₹70,000 |
| Infra (Postgres, Redis, app) | ₹4,000 | ₹18,000 | ₹90,000 |
| Human review | ₹0 (you) | ₹35,000 | ₹1,40,000 (4 FTE) |
| **Total cost/month** | **₹20,200** | **₹1,31,000** | **₹5,76,000** |
| Cost per scan | ₹2.02 | ₹1.31 | ₹0.58 |
| MAU | 2,500 | 25,000 | 250,000 |
| Premium subs | 38 | 375 | 5,000 |
| Premium revenue/month | ₹1,400 | ₹14,000 | ₹1,87,000 |
| **Gross margin** | **−1,340%** | **−836%** | **−208%** |

**With the catalogue-first strategy** (top 2,000 SKUs seeded; cache-hit rises to
75% / 92% / 97%):

| | 10K | 100K | 1M |
|---|---|---|---|
| Total cost/month | ₹11,300 | ₹73,000 | ₹3,20,000 |
| Cost per scan | ₹1.13 | ₹0.73 | ₹0.32 |
| Premium revenue | ₹1,400 | ₹14,000 | ₹1,87,000 |
| Gap to breakeven | ₹9,900 | ₹59,000 | ₹1,33,000 |
| Gross margin | −707% | −421% | −71% |

**Read this honestly:** consumer subscriptions alone don't reach breakeven even at 1M
scans/month. Closing the last gap needs either (a) 2-3 API licences at ₹15-25L/year
each, or (b) ~3M scans/month, or (c) higher conversion than 2%, which the allergen/
diabetic wedge might actually deliver since those users have real willingness to pay.
Seeding the catalogue and licensing the engine are the two highest-leverage moves.
Neither is AI work.

**[v1.1]** Shelf comparison multiplies scans per session (2-4 packs), mostly uncached in
the beta. At ~₹0.53 per uncached scan (D-030) that is noise at beta scale, and every one
of those scans adds a product to the catalogue.

---

## 12. Security, observability, human review

**Security:** presigned direct-to-object-storage upload (images never transit the app
server); strip EXIF including GPS on ingest; delete originals at 30 days unless
flagged; no name/email until sync is requested; device-scoped JWT for anonymous users;
rate limit per device + IP; signed URLs with short TTL for evidence crops; immutable
audit log on `rules`, `ingredient_regulatory_status`, `citations`; RLS on user tables.

**[v1.1] Children's data** (D-074): profile nicknames stay on the device; the server
holds an age band only; parental consent recorded at profile creation; Play target
audience declared as adults. **Photos** (D-080): keep evidence crops, delete full user
originals at 30 days.

**Observability - the metrics that matter more than latency:**

| Metric | Target | Why |
|---|---|---|
| Ingredient match rate | >95% | Unmatched tokens *are* your database backlog |
| Claim extraction recall | >90% | Measured against a hand-labelled golden set |
| False-positive contradiction rate | **<1%** | The metric that protects you legally |
| Product match precision | >99% | A wrong match shows the wrong product's allergens |
| **[v1.1]** Allergen miss rate (golden set) | **0** | An allergen in the gold file reported as *not_listed* |
| **[v1.1]** Allergen *cannot_confirm* rate | <10% | Above that, allergy parents give up |
| Needs-retake rate | <12% | Above that the camera UX is broken |
| User correction rate | <3% | Rising = extraction quality regressing |
| Cache-hit rate | trending to 90%+ | Directly = gross margin |
| p50 / p95 latency | <1.5s / <6s | Aisle patience |
| AI cost per scan | falling | The only cost that scales with usage |

Build a **golden set of 300 hand-labelled Indian labels** before writing the rule
engine, and gate every rule and model change on it in CI. A regression that flips one
verdict on a popular biscuit is a public-trust event.

**Human review queue**, priority-ordered: (1) new product versions on high-scan SKUs,
(2) any R1/R2 contradiction on a product above a scan threshold - *no contradiction
ships on a high-traffic product unreviewed*, (3) low-confidence extractions,
(4) user corrections, (5) unmatched ingredient tokens.

**[CHANGED] Don't build the admin platform (§33).** Django admin or Retool over the
same Postgres gets you 90% of it in days. The only custom screen worth building is the
side-by-side label-image/extracted-data reviewer, because that's where reviewer
throughput lives.

---

## 13. What NOT to build

Ruthless list. Every item here is in the spec.

- **Any numeric health score in the UI** - false precision, legally fragile (§2.3)
- **Streaks, rewards, ₹10 credits** - generates junk scans that poison the catalogue
- **Social sharing infrastructure** - a share sheet with a PNG is enough; no feeds, no
  profiles, no comments
- **Vector database** - `pg_trgm` + alias tables solve ingredient matching; pgvector
  later if ever
- **Microservices** - one Python service, one Postgres, one worker queue
- **Search engine (ES/Typesense)** - Postgres FTS is fine to ~1M products
- **B2B dashboard, in any form, before 500K scans/month** - nothing to sell
- **Custom admin platform** - use Django admin/Retool
- **Native app for v1** - PWA; native Android after retention is proven
- **Multi-language UI at launch** - Indian packaged-food labels are in English by law;
  translate the *explanations* later, and only after the English ones are reviewed.
  **[v1.1]** "Later" = public launch: Hindi explanations and parent text then (D-079);
  UI chrome can stay English
- **Named alternatives at launch** - require a populated category (≥80%). **[v1.1]**
  Shelf comparison ships in the beta instead (D-057)
- **Nutrition-panel OCR at launch** - tabular OCR is materially harder than list OCR;
  ingredient-list intelligence alone is a complete product. **[v1.1]** One exception
  after the beta: the added-sugar row, for "teaspoons in this pack" (D-081)
- **Shopping lists** - Phase 3. **[v1.1]** Minimal household profiles move into the
  beta (D-074)
- **Brand-submitted data portal** - a trust liability before you have any leverage
- **International architecture work** - keep `jurisdiction`/`locale` columns, build
  nothing else

---

## 14. Tech stack & repo

Chosen to match what you already run, and to keep the surface small.

| Layer | Choice | Why |
|---|---|---|
| App | Python 3.12 + FastAPI | Your language; strong typing for extraction schemas |
| DB | Postgres 16 (Supabase or managed RDS) | Relational truth layer, `pg_trgm`, JSONB, RLS |
| Cache | Redis | Hot product cache, rate limits |
| Queue | Celery or RQ on Redis | **Not Airflow.** Airflow is for batch, not per-scan |
| Object store | Cloudflare R2 | Zero egress fees - matters when serving evidence crops |
| Client | PWA: React + Vite, MLKit/ZXing barcode, on-device canvas preprocessing | One codebase; installable on Android |
| OCR | Cloud OCR behind a provider interface | Swappable |
| VLM | Vision-language model behind the same interface | Swappable; pinned per version |
| B2B analytics (later) | dbt + Snowflake, separate account | Your actual edge; correct side of the firewall |
| Admin | Django admin or Retool | Don't build it |
| Observability | OpenTelemetry → Grafana Cloud; Sentry | |

```
insidelabel/
├── core/                 # segment-blind engine - the existing engine.py, hardened
│   ├── tokenize.py  normalize.py  classify.py  rules/  findings.py
├── data/                 # THE MOAT - versioned JSON → migrated into Postgres
│   ├── ingredients/  nova_markers.json  claims/  citations.json
│   ├── allergens.json    # [v1.1] FSSAI reg. 5(14) categories + Indian aliases
├── extraction/
│   ├── providers/        # ocr_*.py  vision_*.py  (interface-compatible)
│   ├── preprocess.py  parse_nutrition.py  parse_ingredients.py  confidence.py
├── catalogue/            # product resolution, dedup, versioning, fingerprints
├── lenses/               # age / repro / metabolic / goal / allergen - read-only
│   ├── compare.py        # [v1.1] shelf comparison + kids lens (D-056, D-057)
│   ├── allergens.py      # [v1.1] five-state allergen check (D-071)
├── api/                  # FastAPI routers, schemas, auth, rate limits
├── workers/              # async scan pipeline, alerts, review-queue fanout
├── review/               # reviewer tooling (the one custom screen)
├── eval/                 # golden set + CI gates  ← build this EARLY
│   ├── golden/  test_rules.py  test_extraction.py  report.py
├── migrations/
├── web/                  # PWA
└── analytics/            # dbt project (Phase 4, separate deploy)
```

Note the shape: `core/` and `data/` are the company. Everything else is plumbing you
could rewrite in a month. Keep it that way.

---

## 15. The MVP - be ruthless

**Hypothesis to test:** *people will photograph a food label to find out whether the
front of the pack is telling the truth, and will come back to do it again.*

**[v1.1]** For allergy households and parents the question is *"is this right for my
child - and which one should I pick?"* The beta tests whether they come back to ask it
again.

Nothing else is being tested. Cut anything that doesn't test it.

**[v1.1] In scope - the 15-week plan in `STATE.md`** (D-007 early launch, D-084). This
replaces the original "300 SKUs before any user" scope:
1. Catalogue of **50 SKUs**, 15 kids' biscuits first (D-058). Hand-checked.
2. Barcode scan → cached result, with "last verified" and the allergy re-check (D-073).
3. Photo path for cache misses (`gemini-3.6-flash`, D-030), honest progress (D-068),
   "send it to us" after failed retries (D-070).
4. Allergen check first on every result (D-060, D-071, D-072).
5. Result screen per §7: headline finding, "nothing wrong" state, plain band names,
   per-person status, ordinary additives grouped (D-061 to D-066).
6. Household profiles, up to 3, device-local nicknames (D-074); kids lens (D-056).
7. Shelf comparison (D-057).
8. Verdict → Why → Evidence screens, with photo crops.
9. Trust pages and "Report a mistake" (D-076). Corrections → review queue.
10. Claim checker: per D-051, still undecided.

**Out of scope for the beta:** nutrition-panel OCR (including the added-sugar row,
D-081), R1 rules, named alternatives, premium tier, accounts (device-local storage
only), history sync, B2B anything, native app, share target and WhatsApp card (D-077,
D-078 - after the W4 number, D-083), Hindi (D-079 - public launch).

**Beta gate** (from `STATE.md`):
- 50-100 users, **≥30% return in week 4** with ≥1 scan
- ≥2.5 scans per returning user per month
- ≥95% ingredient match rate on the seeded categories
- **<1% false-positive contradiction rate** on the golden set
- **[v1.1] Allergen miss rate 0** on the golden set
- Qualitative: users say a claim check or a shelf comparison changed a purchase
- **[v1.1] Tracked, not gating:** shelf comparisons per returning user; share of parents
  whose next scan in that category is the pack we picked; weekly return rate of
  avoid-list profiles

If week-4 retention lands under 15%, the product is a novelty and no amount of
engineering fixes it. Stop and rethink the wedge rather than building Phase 2.
(D-055: write the exact stop number before week 12.)

---

## 16. Roadmap

**[v1.1] Re-based on the 15-week beta.** Months 1-3 no longer run without users; the
beta itself is the first phase.

| When | Focus | Deliverable | Metric |
|---|---|---|---|
| Weeks 1-15 (Sep-Dec 2026) | Build + 4-week closed beta - see `STATE.md` | Beta on Play closed testing | **W4 retention ≥30%** |
| Jan 2027 | Wave 2: share target, WhatsApp card (D-077, D-078); catalogue to 300 SKUs | Online-order path live | Share-target scans per week |
| Feb 2027 | Wave 3: Hindi explanations (D-079); added-sugar row with its own eval (D-081) | **Public launch** to allergen, diabetic and parent communities | 500 users |
| Mar 2027 | Corrections pipeline at scale; catalogue to 800 SKUs; FSSAI Schedule I/II retrieval | - | W4 retention holds at public scale |
| Apr 2027 | Nutrition-panel OCR → R1 regulatory rules | "High protein" checks live | Nutrition confidence >90% |
| May 2027 | Formulation-change alerts; safety alerts free (D-075) | Alert system | Alert → open rate |
| Jun 2027 | Named alternatives once 3 categories are ≥80% covered; category browse (free, D-059) | Alternatives live | Alternative tap-through |
| Jul 2027 | Premium launch, scope per D-082 | Premium tier | Conversion ≥1.5% |
| Aug-Sep 2027 | Engine API pilot with one health app | First B2B revenue | 1 signed pilot |

---

## 17. Defensibility - honest version

**What is not defensible:** ingredient explanation. A photo into Gemini today already
yields a reasonable explanation of INS 322. Any moat built on "we explain ingredients
with AI" is already gone. Do not position there.

**What is defensible, in ascending order:**

1. **Consistency.** An LLM gives a different answer to the same label on Tuesday. A
   rule engine over a versioned database gives the same verdict every time, and can
   show why. For a parent checking an allergen, non-determinism is disqualifying. This
   is a genuine architectural advantage and it compounds with nothing.
2. **Speed in the aisle.** Barcode → verdict in under a second beats
   photograph → upload → reason → read by roughly 15 seconds. Only a pre-resolved
   catalogue can do it.
3. **The verified Indian SKU catalogue.** Not scrapeable - it comes from photographs
   of physical packages. Every SKU is a unit of labour a competitor must repeat.
4. **Claim criteria pinned to FSSAI Schedule I/II, versioned.** Boring, tedious,
   regulator-sourced, and it takes a competitor the same months it takes you.
5. **Formulation history.** Uniquely non-replicable: it can only be accumulated in
   real time. A competitor launching in 2028 cannot reconstruct what a biscuit's
   ingredient list said in 2026. This is the moat that genuinely deepens with age -
   and it's also the most saleable B2B asset, because brands themselves don't track
   competitor reformulation systematically.
6. **Observed alias corpus.** Your "soya" → "soy" discovery is one row. Ten thousand
   such rows, harvested from real Indian labels, is an extraction accuracy gap a new
   entrant closes only by processing the same volume.

**The flywheel, stated precisely:** scans → unmatched tokens and new SKUs → catalogue
and alias growth → higher cache-hit rate → lower cost *and* lower latency → better
free product → more scans. Note that the loop's output is **margin**, not just data.
That's what makes it a business rather than a dataset.

---

## 18. Brutal assessment

### Five reasons this fails

1. **The economics don't close on consumer revenue, and the fix is the thing you said
   you'd be careful about.** B2B is mandatory for viability at Indian price points, and
   B2B for a label-judging product is a permanent conflict. The catalogue strategy and
   API licensing help, but this tension never fully resolves and one bad story about
   brand money ends the trust proposition in a week.

2. **Retention is probably too low.** 2-4 scans/month is a notification-permission
   business, not a habit business. If W4 retention comes in at 12%, the flywheel never
   spins, the catalogue never fills, cost per scan stays at ₹2, and the whole thing is
   a very well-engineered demo. This is the single most likely failure mode, and the
   spec doesn't currently have an answer for it.

3. **One wrong verdict on a big brand - or one missed allergen.** A false "No Added
   Sugar contradiction" on a Britannia SKU, screenshotted and shared, is simultaneously
   a legal letter and the end of your credibility. **[v1.1]** A missed allergen is worse:
   it's a child's health. Hence the five-state check, the stricter gate and a zero
   allergen-miss target (D-071, D-072). Your architecture is the right defence, but it means the
   `verify: true` rows and bare institution-name citations in the current data files
   stop being TODOs and become launch blockers.

4. **Capacity.** **[v1.1]** ArthaIQ is paused (D-006), which removes the worst of the
   split attention. What remains: a training business, SEBI RA registration, and
   ~2 hours a day. The 2026-09-24 review adds ~38 hours to the beta build (D-084).
   Originally: you're running a training business with a cohort in flight, building
   ArthaIQ Labs, and pursuing SEBI RA registration. This blueprint's months 1-3 are
   full-time, unglamorous catalogue labour with zero user-facing output. Split
   attention is how this becomes a half-built prototype in a repo, which is a more
   likely outcome than either success or failure.

5. **A large player ships 80% of it.** Google Lens, Zepto, Blinkit or BigBasket adding
   an "ingredients explained" panel captures the casual majority and leaves you the
   allergen/diabetic niche. **[v1.1]** Quick-commerce is also where parents now shop,
   which is why the share-target path matters (D-077). That niche can be a good ₹2-5 crore business; it is
   probably not a large one.

### Five reasons this becomes large

1. **The claim-vs-label gap is a real, unserved, emotionally charged wedge.** Nobody in
   India is doing regulation-grounded claim contradiction. "Healthy is not a regulated
   word" is a genuinely new thing to tell a shopper, and it's unfalsifiable.

2. **India's packaged-food market is growing while diabetes prevalence is rising, and
   FSSAI is actively tightening claims regulation.** Product, market and regulatory
   timing are aligned, which is rare.

3. **The catalogue plus formulation history is a compounding asset that a
   better-funded competitor cannot buy.** It's built from physical packages over
   elapsed time. Money doesn't shorten elapsed time.

4. **The architecture you've already built is unusually disciplined for a prototype.**
   Segment-blind core, definitional NOVA override, per-document citation pinning,
   honest rendering of unverified sources, an explicit note about why gender doesn't
   change ingredient guidance. That discipline is the product, and most teams cannot
   fake it retroactively.

5. **The engine is licensable.** Every Indian health app, diabetes app, insurer,
   corporate wellness platform and quick-commerce retailer needs exactly this
   capability and none will build it. That's a conflict-free B2B line with better
   margins than consumer subscriptions and no trust cost - and it's reachable in
   12 months.

### The one thing to decide before writing any more code

Not the architecture. This:

> **Who is the person who opens this app in week six, and what makes them open it?**

Answer that with a named, specific person and a specific trigger. If the answer is
"health-conscious urban Indians who care about what they eat," you don't have one yet,
and everything in this document is premature.

**[v1.1] Working answer:** a mother in Bhubaneswar whose 6-year-old has a milk allergy.
Her son's friend brought a new biscuit to school, he wants it too, and she is standing
at the kirana counter with two packs. She opens the app to ask "can he have this - and
if not, which one here can he have?" That trigger repeats every time a new snack enters
his world.
