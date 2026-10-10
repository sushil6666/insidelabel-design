# DECISIONS.md

Architectural and product decisions for InsideLabel, with the reasoning attached.
Append-only. When a decision is reversed, mark it `SUPERSEDED` and add a new entry
rather than editing the old one - the history is the point.

**Last updated:** 2026-09-27 (D-102 to D-113 locked; D-001's chatbot clause superseded; D-114 hosting, D-115 marker wording, D-116 AYUSH packs and D-117 review agents locked)

**Status key:** `LOCKED` decided, don't relitigate · `OPEN` not yet decided ·
`RECOMMENDED` proposed but not accepted · `SUPERSEDED` replaced

---

## Product

### D-001 · Positioning `LOCKED`; its "not a chatbot" clause `SUPERSEDED` by D-113 (2026-09-27)
InsideLabel reads the front and back of an Indian packaged-food label and tells the
consumer where they disagree. Not a health scorer, not a barcode scanner, not a
chatbot.

### D-002 · Trust before monetization `LOCKED`
A brand can never pay to remove, soften, or preview a consumer finding. "Find a
better alternative", alternative ranking, and category browse are never monetizable
in any form. Publish the conflict-of-interest policy before taking the first rupee of
B2B revenue.

### D-003 · India-first `LOCKED`
FSSAI is the primary regulatory authority and leads all citations where it covers the
claim. WHO second (a body India references directly). Single-country foreign health
services (NHS, ACOG, CDC, AAP) are secondary, explicitly-labelled context only.
Schema keeps `jurisdiction` / `locale` columns; no other internationalisation work.

### D-004 · AI reads the label; rules do the judging `LOCKED`
Non-negotiable separation. The vision model transcribes only. Every verdict comes from
a deterministic rule over a database row and is fully traceable. Preserves the "no AI
decided your verdict" promise and makes verdicts reproducible.

### D-005 · Engine is segment-blind `LOCKED`
The core engine states ingredient facts only. Segment lenses (age, goal, pregnancy/
breastfeeding, metabolic) sit above it, re-weight and re-phrase the *same* flags, and
can never change the underlying facts or the score.

### D-006 · ArthaIQ paused; full focus on InsideLabel `LOCKED` (2026-09-12)
Removes the split-attention risk that made the 3-month catalogue phase unsurvivable.

### D-007 · Launch early, via closed beta `LOCKED` (2026-09-12)
The unknown is no longer accuracy - it's whether anyone returns in week six. Ship a
retention test, not a product.

---

## Platform

### D-010 · Android only; PWA wrapped for Play Store `LOCKED` (2026-09-12)
Android is the overwhelming majority of the Indian market and the launch wedge is
value-conscious households. iOS costs ₹8,700/yr plus Mac hardware for the segment
least likely to be a target user. PWA first, Bubblewrap into a Trusted Web Activity.
Revisit iOS only if iOS users are actively asking, month 12+.

### D-011 · Register the Play developer account immediately `LOCKED` (2026-09-12)
₹2,200 one-time. Identity verification and the new-developer closed-testing
requirement consume calendar time that can't be compressed later. Start the clock
during the build.

### D-012 · Play App Signing, not self-managed keys `LOCKED`
Losing a self-managed upload key means never updating the listing again.

---

## Data & infrastructure

### D-020 · Postgres is the transactional truth layer `LOCKED`
Holds `products`, `product_versions`, `findings`, `evidence`, `scans`, `corrections`,
`users`. Indexed point reads, small frequent writes, row-level locking on the review
queue, `pg_trgm` for ingredient alias fuzzy matching. Supabase free tier or a ₹400/mo
VPS.

### D-021 · DuckDB + dbt for analytics, not Snowflake `LOCKED` (2026-09-12)
At this data volume the whole dataset fits in RAM; Snowflake would be a recurring bill
for output DuckDB produces at ₹0. Flow: Postgres → nightly Parquet export on R2 →
DuckDB via `httpfs` → dbt models → aggregates written back to Postgres for the app to
read. Aggregates flow *back* so DuckDB's single-writer limit never touches the request
path.

Revisit at the B2B trigger - Snowflake Secure Data Sharing is genuinely the right
mechanism for selling category intelligence, and enterprise procurement expects it.

### D-022 · dbt models stay dialect-portable `LOCKED`
No `QUALIFY`, `FLATTEN`, `VARIANT` paths, or Snowflake-only functions. Engine-specific
logic lives in macros. `dev` and `ci` targets both on DuckDB from day one - having
`ci` exist is what enforces portability. Makes `dbt-duckdb` → `dbt-snowflake` an
adapter swap, not a rewrite.

### D-023 · No vector database `LOCKED`
`pg_trgm` plus alias tables solve ingredient matching. pgvector inside Postgres later
if free-text consumer questions ever need it.

### D-024 · Barcode is the product key; fingerprints are fallback `LOCKED`
Resolution order: barcode → brand+name+net_qty exact → nutrition fingerprint →
ingredient fingerprint → image embedding. Stop at first confident match. A cached
product costs ~₹0.05/scan and resolves in under a second; an uncached one costs
~₹0.53 and takes 8-15s.

Note the tension with D-025: barcode is the right *key*, but cannot be the primary
*path* at launch because Indian FMCG coverage in existing open databases is thin. The
photo path is primary; the barcode is a cache key built from real usage.

### D-025 · Photo-of-ingredients-panel is the primary path `LOCKED`
Back label first (never blocks the verdict), front of pack second (brand, name,
claims). Single vision call handles both images and returns structured JSON.

### D-026 · Version everything `LOCKED`
Labels change and brands reformulate silently. `product_versions` with
`ingredients_hash` / `nutrition_hash` / `claims_hash`. Model as SCD2
(`valid_from`, `valid_to`, `is_current`) - reformulation alerts and the eventual B2B
reformulation-tracking product both read from it, and it's painful to retrofit.

### D-027 · Always preserve raw OCR alongside resolved values `LOCKED`
Enables re-parsing with a better model later without re-photographing. Displayed
ingredient text always keeps the label's original spelling.

### D-028 · New products route to a review queue, not the public catalogue `LOCKED`
Plus: keep source photos for every catalogue entry as evidentiary protection.

### D-029 · Catalogue is the asset, not the AI `LOCKED`
The models are rented and available to any competitor at the same price. The verified
Indian SKU catalogue, the observed alias corpus, the FSSAI-pinned claim criteria and
the formulation history are owned and compound. Seeding SKUs shifts cost from
per-scan AI to one-time labour and is what makes the free tier genuinely free.

---

## Vision pipeline

### D-030 · `gemini-3.6-flash` in production `LOCKED`
~$6 per 1,000 scans ≈ ₹0.53/scan. Cost is not a constraint at beta scale (5,000
scans/month ≈ ₹2,600). `gemini-2.5-flash` is unavailable to new API keys.

### D-031 · Models sit behind swappable interfaces `LOCKED`
`OCRProvider` / `VisionProvider` protocols. Model version pinned per
`product_version` row so a wrong verdict can be traced to a model change.

### D-032 · Union-based consensus for ingredient recovery `LOCKED`
Not majority vote. Missing an ingredient is worse than listing an uncertain one.

### D-033 · `ingredient_lines` array is the source of truth `LOCKED`
Not `ingredients_raw`.

### D-034 · Independent OCR verification restricted to known additives `LOCKED`
Tesseract cross-check only validates against entries in `additives.json`, preventing
injection of hallucinated facts.

### D-035 · User attestation is the pairing mechanism `LOCKED`
Two still photos cannot prove same-pack. `product_match` distinguishes `match` /
`mismatch` / `indeterminate` / `single_image`, with code-side anchor verification
rather than trusting model-reported evidence.

### D-036 · Confidence gate: never interpret low-confidence text `LOCKED` · *"type it in" SUPERSEDED by D-070*
Below threshold → specific retake prompt naming the actual problem, plus "type it in"
and "is this your product?" candidates. Max two automatic retries with different
preprocessing. A bad OCR that becomes a health statement is the one failure mode that
ends credibility permanently.

### D-037 · Partial results never block on one image `LOCKED`
Bad front image → full ingredient intelligence, claims marked unavailable. Bad
nutrition panel → ingredient analysis, R1 rules suppressed. Unavailable is stated
explicitly; silence reads as approval.

---

## Rule engine

### D-040 · Five rule tiers `LOCKED`
| Tier | Basis |
|---|---|
| R1 | Regulatory numeric - FSSAI Schedule I threshold vs declared nutrition panel |
| R2 | Regulatory non-addition - non-addition claim vs ingredient declaration |
| R3 | Definitional - NOVA Group-4 marker present |
| R4 | Unregulated marketing - claim with no legal definition |
| R5 | Consumer preference - user's stated avoid-list |

### D-041 · NOVA Group-4 is definitional, not scored `LOCKED`
A single marker means ultra-processed regardless of score. The score adds nuance; it
never overturns NOVA.

### D-042 · Wording discipline, enforced in CI `LOCKED`
Allowed: "The label claims X. The declaration says Y." / "Worth checking before
buying." / "X is not a defined claim under Indian regulation."

Forbidden: misleading, false, illegal, non-compliant, violation, lying, toxic,
dangerous, poison - and any statement about the *brand* rather than the *label*.
Lint the content tables in CI; don't rely on humans remembering.

### D-043 · Every finding needs ≥1 evidence row `LOCKED`
Enforced by FK + deferred constraint trigger. A finding without receipts must be
impossible, not merely discouraged.

### D-044 · Citations are per-document, never per-institution `LOCKED`
WHO has multiple documents with different numbers; they get different keys. Verified
citations render as links with a verification date; unverified ones render as plain
text. An unverified citation to the same institution for a *different* claim correctly
still renders plain.

### D-045 · Nothing with an unpinned citation reaches consumer output `LOCKED`
Formalises the existing `SrcChip` verified/unverified distinction as a database
constraint rather than a rendering nicety.

### D-046 · Claim criteria are seeded from FSSAI regulation text, never hardcoded `LOCKED`
Source: Food Safety and Standards (Advertising and Claims) Regulations 2018, as
amended 13 Dec 2022 (notification No. Std/EC/T(NSF-01)), which revised the general
principles, nutrition claims, non-addition claims and Schedules I (nutrient content
claims), II (claim synonyms) and III (disease-risk-reduction claims). Schedule II is
also the regulator-written claim-alias table the extractor needs.

Do not hardcode remembered thresholds from any source, including an AI assistant.

---

## Parents, allergens and the result screen (2026-09-24 user-perspective review)

### D-056 · Parents / kids lens `LOCKED`
Re-weights existing engine facts for the toddler / kid / young age bands. Never adds
facts of its own (D-005). Strong tier for children: Southampton-six colours (EU warning
label, labelled as a foreign rule per D-003), high-concern additives, sugar in the first
two ingredients (first three for toddlers), and MSG and caffeine for toddlers.
Artificial sweeteners are **moderate**, stated as a fact with no legal claim: FSSAI's
labelling FAQ (June 2022) says sucralose no longer needs a warning statement, so
"Indian rules require 'Not recommended for children'" would be false. Raise the tier
only with a verified, child-specific citation.

Parent text uses plain words; INS numbers and citations sit behind a tap. Never says
"healthy".

### D-057 · Shelf comparison ships in the beta `LOCKED`
The parent scans 2-4 packs on the shelf; `compare.py` names the best pick of those with
reasons. Needs no catalogue, and every comparison scan feeds it. Ranked by concern
tiers, never a numeric score. A pack can never be the best pick if it: contains or
may contain something on the child's avoid list, has an allergen status we couldn't
confirm, has an unreliable scan, or has an INS number missing from `additives.json`.
Honest ties are reported as ties. If every pack fails, it says so and asks for another
scan.

### D-058 · Seed kids' biscuits first `LOCKED`
The first 15 of the 50 beta products are the biscuits Indian children eat most, so
named alternatives work in at least one category at launch. Named alternatives turn on
per category only at ≥80% coverage (`coverage_by_category`).

### D-059 · Alternatives, comparison, category browse and name search are free forever `LOCKED`
Resolves the blueprint §8 contradiction (listed as Premium while also "never
monetizable"). A paywall is monetization. Say so in the public COI policy (D-076).

### D-060 · Personal safety comes first on the result screen `LOCKED`
If any profile has an avoid list, the first line is the allergen result for that
profile. Order after that: headline finding → claim check → worth knowing →
ingredients.

### D-061 · The headline states the finding, not a count `LOCKED`
"Says 'No added sugar', but contains jaggery." - not "1 claim to check, 3 things worth
knowing". Counts move below the headline. Headline text comes from the same finding row
(D-043), so it is still rule-generated and traceable.

### D-062 · "Nothing wrong" is a designed state `LOCKED`
Most scans will find no contradiction. That result gets its own useful screen: what was
checked, and the profile-relevant facts. Only say "the front matches the back" when the
claim checker actually ran on a paired front image (D-035); while D-051 is undecided,
the fallback is "We checked the ingredients."

### D-063 · Band display names `LOCKED`
Band logic is unchanged (NOVA stays definitional, D-041). Display labels change:
"Clean" → **"No concerns found in the ingredients"** (never implies "safe to eat
freely"); "Worth checking" → **"A few things worth knowing"**; "Ultra-processed" →
**"Made with industrial ingredients"**, with the NOVA term and its definition one tap
away.

### D-064 · The glanceable signal is per person; no numeric score in the consumer UI `LOCKED`
Resolves D-050 as *remove*. The quick signal is a status per profile: "Contains milk -
on Aarav's avoid list", "Fewer concerns for kids". The 0-100 score stays admin-only for
regression testing.

### D-065 · Ordinary additives are grouped, not listed as concerns `LOCKED`
`none`/`low` concern ingredients collapse to "12 other ingredients look ordinary",
expandable. Reassurance is part of the product; a list of harmless additives reads as a
list of dangers.

### D-066 · R2 gets a "what the rule says" line; R4 is shown in full once `LOCKED`
Where an R2 finding has a **verified** citation, add one neutral line on what the
regulation defines. Still no forbidden words (D-042). R4 ("X is not a defined claim")
shows in full the first time a user meets that claim type, compact after that.

### D-067 · Medical questions: say "ask your doctor" once, clearly `LOCKED`
Diabetic and pregnancy lenses show the facts and one clear line to ask a doctor about
quantity, on the lens intro - not repeated on every screen.

### D-068 · First scans are honest about speed `LOCKED`
Beta scans are mostly cache misses (8-15 s). Show real progress ("Reading ingredients…
found 14") and frame the wait: "First time we've seen this pack. Next time it's instant,
for everyone." The camera screen shows a sample photo of which side to shoot.

### D-069 · Onboarding starts at home `LOCKED`
First run: "Scan 3 packs from your kitchen." Value without a shopping trip, and it seeds
the catalogue with what families actually eat.

### D-070 · "Send it to us" replaces "type it in" `LOCKED`
Amends D-036. After two failed retries: "Send it to us - we'll check this pack and
tell you when it's ready." Routes to the D-028 review queue. In the beta the result
appears in-app on next open; push notifications come later.

### D-071 · Allergen check: five states, never "free from" `LOCKED`
`allergens.py` + `allergens.json`. Reads `ingredients` and `allergen_statement`, which
`prompt.py` already returns, so no prompt change. States: contains > may_contain >
uncertain > not_listed, plus cannot_confirm. Cross-contact wording varies ("may
contain", "traces of", "same facility") and FSSAI accepts any similar wording, so all
forms are matched. Ambiguous sources (lecithin with no source named, "mixed nuts") are
*uncertain*. The strongest negative ever shown is "isn't listed"; "free from",
"allergen-free" and "safe" are forbidden, enforced by a test. Categories follow FSS
(Labelling & Display) Regulations 2020 reg. 5(14), plus opt-in sesame and mustard
flagged as not mandatory to declare.

### D-072 · Stricter confidence gate for allergens `LOCKED`
Allergen output needs ingredient confidence ≥ 0.95 (the general gate is 0.85) and a
reliable scan; below that, *cannot_confirm* and a retake prompt. 0.95 is a starting
value - calibrate once allergen fields are in the gold set.

### D-073 · Allergy profiles re-check cached results `LOCKED`
Barcodes often survive reformulation. On a cache hit for a profile with an avoid list:
show "Label last verified on …" and ask for one back photo. Compare it with Tesseract
(already in the stack, ₹0) against the cached `ingredient_lines`; escalate to the vision
model only on a mismatch. A confirmed change creates a new `product_version` (D-026)
into the review queue. Tesseract is used only to detect change, never as a source of
facts, so D-034 still holds.

### D-074 · Minimal household profiles in the beta `LOCKED`
Up to 3 profiles (the user + 2). Each holds an age band, avoid list and lens choices.
Nicknames stay on the device; the server sees a profile id and an age band only
(DPDP Act, children's data). Parental consent at profile creation. Play Console target
audience is adults - the app is for parents, not directed at children.

### D-075 · Safety alerts are free `LOCKED`
"Your son's usual biscuit now contains milk" is a safety fact. Reformulation alerts that
touch an avoid list or allergen are free forever. (All alerts are free in the beta
anyway; the formulation-alert system itself is still post-beta work.)

### D-076 · Trust is visible from the first beta user `LOCKED`
At beta launch, not "before the first B2B rupee": publish the conflict-of-interest
policy and methodology, show who is behind the app (name and face), show "last
verified" dates, and put "Report a mistake" on every result.

### D-077 · Online-order path via Android share target `LOCKED` · *build after W4 (D-083)*
Urban parents buy on Blinkit / Zepto / BigBasket and never hold the pack. The PWA/TWA
registers as a share target so a product screenshot can be shared into InsideLabel; the
existing photo path reads an ingredient panel from a screenshot. Pairs with free name
search (D-059).

### D-078 · WhatsApp-first share card `LOCKED` · *build after W4 (D-083)*
Still a PNG share sheet, per "Explicitly not building". Vertical, readable on a small
phone, Hindi option, "check your own" link. Card templates pass the D-042 wording lint,
because the card travels without context.

### D-079 · Hindi explanations at public launch `LOCKED`
Findings are templated rows (D-043), so translation is a bounded set of reviewed
strings. Explanations and parent text in Hindi at public launch; UI chrome can stay
English, so "multi-language UI at launch" in *Explicitly not building* still stands.

### D-080 · Photo retention `LOCKED`
Seed and reviewer photos are kept in full (D-028). User scan photos: keep the
label-region crops used as evidence; delete full originals at 30 days unless flagged,
via an R2 lifecycle rule on the originals prefix. Set up at deploy (week 10), because
beta photos turn 30 days old during the beta.

### D-081 · Added sugar in teaspoons `LOCKED` · *after the beta*
Labels must declare added sugars, and FSSAI uses 50 g as the added-sugar RDA, so one
parsed row plus net quantity gives "4 teaspoons in this pack". It needs a new field in
the vision schema, which is a deliberate exception to the `prompt.py` freeze: build it
after the W4 number, with gold files for the new field and a full `eval_vision.py`
re-run to prove ingredients didn't regress.

### D-082 · What Premium is for, after this review `OPEN`
After D-059 and D-075, Premium is roughly: full history and export, saved lists,
non-safety alerts, households beyond 3 profiles. Ask beta parents what they would pay
₹449/year for (interviews only - nothing built during the beta). Feeds D-053.

### D-083 · Wave 2 builds wait for the W4 number `LOCKED`
"Do not build features during the beta" stands: changing the product mid-beta muddies
the retention number. During the beta: premium interviews (D-082) and using tiffin and
festival moments in recruitment messaging. After the W4 result, if the gate passes:
D-077, D-078, then D-079 and D-081 before public launch.

### D-084 · Accept a ~3-week slip for Wave 1 `LOCKED` (2026-09-24)
Wave 1 adds ~38 hours (allergens ~10, household + kids lens + compare UI ~12, result
screen ~4, first use ~5, trust pages ~4, extra additive rows ~3). At 2 hrs/day that
moves the W4 answer from early December to **late December 2026**. Trimming was the
alternative; rejected, because every Wave 1 item is safety, legal, or a screen being
built now. Accepted by Sushil 2026-09-24.

### D-085 · Class-only "low" additives don't lower the score `LOCKED` (2026-09-25)
A `low` additive takes the low penalty only if it carries a concern flag
(`additives.json` `_meta.scoring.low_penalty_flags`: 4mei_trace, phosphate_load,
possible_transfat_source, gut_microbiome_research, polyol, synthetic_colour,
flavour_enhancer, sweetener_natural). Flags that only name the class (emulsifier,
preservative, modified_starch, anticaking, carrier_solvent) score 0. The flag still
appears in the verdict, NOVA markers are scored as before, and the claim checker still
reads the class, so "no preservatives" is still contradicted by INS 282.

Why: after 26 verified rows were added (Codex INS list + FSSAI compendium XXVI + 2025
amendment), long bakery labels were being scored down by ordinary baking additives
(Ziggy 12 → 0). Score is admin-only (D-064) and ordinary additives are grouped in the UI
(D-065); this keeps the admin ranking consistent with that. Gold scores after: Britannia
48, Limca 80, Maliban 56, Patanjali 48, Ziggy 28. No verdict changed. Accepted by
Sushil 2026-09-25.

### D-086 · FSSAI decides; India vs EU vs US is an optional, information-only view `LOCKED` (2026-09-25)
Every verdict, score and concern level uses FSSAI rules only. Another country's legal
status never sets `concern` (the `high` band is now "not permitted in India, or a strong
health signal"). Evidence such as a Southampton-study link or an EFSA safety opinion can
still inform concern; a foreign ban or warning-label rule cannot.

The user can opt in to "check the same with EU and US standards"
(`compare_regulators=true` on `/analyze` and `/scan`, and `GET /regulators/{ins}`).
It shows India first, then EU, then US, per additive found, with regulators-differ
first, the regulator's stated reason where one exists, and a link to the exact document.
Rows live in `data/regulatory_status.json`; only rows checked against the regulation text
go in, and an unchecked jurisdiction reads "Not yet checked". Display text comes from
fixed templates, so it passes the D-042 lint. A test proves the option never changes the
verdict.

Initial rows (verified 2026-09-25): 171, 127, 122, 124, 143, 102, 110, 129, 928 (India
permits; EU and/or US differ) and 927a, 924a, 952 (India does not permit). Consequences
in `additives.json`: 171 re-based `high` → `moderate` and `fssai_status` `check` →
`permitted` (GMP); 952 recorded as not permitted in India; `banned_*` flags and
foreign-ban wording removed from `why`. The kids lens (D-056) still mentions the EU
warning as labelled context. Accepted by Sushil 2026-09-25.

### D-087 · PostgreSQL 19 `LOCKED` (2026-09-25); the server runs 18 until 19 is released, see D-114 (2026-09-27)
Target PostgreSQL 19. Installed locally as 19~beta4 from the official PostgreSQL apt
repository (`tools/install_pg19.sh`), side by side with 16 (which stays on 5432 until
19 is proven). GA is expected by end of October 2026, before the beta users arrive.

Known costs, accepted: a beta cluster may not start on the next beta/RC/GA binaries if
the catalog version changes, so until GA the local 19 database is treated as disposable
and rebuilt from `migrations/` rather than upgraded. The deployment host (D-080, week 10)
must offer 19; if it doesn't by then, the schema stays portable to 16-18 (the DB tests
run on any of them via `INSIDELABEL_TEST_PG`). Chosen by Sushil against the
recommendation to wait for 19.1.

### D-088 · Catalogue sourcing: no scraping of retailer sites; users bring listings in `LOCKED` (2026-09-25)
Proposal (Sushil): fill the catalogue from Flipkart / Amazon / Blinkit / Swiggy
Instamart / Zepto listings, which carry ingredient details.

What was checked:
- **Their terms forbid it.** Amazon.in Conditions of Use prohibit "any use of data
  mining, robots, or similar data gathering and extraction tools" and "any derivative
  use of this website or its contents". Flipkart's Terms of Use prohibit any
  "page-scrape, robot, spider… **or any similar or equivalent manual process**, to
  access, acquire, copy or monitor any portion of the Platform or any Content".
  **Swiggy** (swiggy.com/terms-and-conditions) and **Instamart**
  (instamart.in/instamart-terms-of-use), read directly 2026-09-25, use the same clause:
  no "deep-link", "page-scrape", "robot", "spider"… "or any similar or equivalent manual
  process, to access, acquire, copy or monitor any portion of the Platform or any
  content". Instamart also disclaims listing accuracy ("product information supplied by
  Merchant" may be "incorrectly reflected"; it "accepts no liability for any errors or
  omissions"). **Zepto** (zeptonow.com/terms-of-service) renders only via JavaScript;
  a search-engine excerpt of the page shows the same "deep-link, robot, spider… or any
  similar or equivalent manual process… access, acquire, copy" wording - not read
  first-hand. **Blinkit** returns 403 to scripted requests; a search excerpt (from its
  Bistro terms) says copying or storing platform content "in whole or part is prohibited
  without the express prior written consent of Blinkit" - not read first-hand. Check
  both in a browser before quoting them publicly.
- **The data is required but not reliable.** FSSAI's advisory to e-commerce FBOs
  (3 Dec 2024) requires mandatory label information to be shown pre-sale and matched
  to the physical label - issued because listings often don't match. A listing is a
  claim about a pack, not the pack.
- **Open Food Facts** has 23,156 products tagged India (2026-09-25), under ODbL:
  fine as test input and as a list of *which* products to prioritise; ingesting its
  records into the shipped catalogue likely makes the catalogue share-alike, which
  collides with D-029.

Recommendation:
1. **Don't scrape or copy listings** - terms breach, takedown and account-ban risk,
   and a catalogue built on it is not an asset we own (D-029).
2. **Move D-077 (share target) into the beta.** A user shares a Blinkit/Zepto/Amazon
   product screenshot into InsideLabel; the existing photo path reads it; it goes to
   review like any scan (D-028). Same data, user-initiated, demand-driven. Results
   from a listing are labelled "read from an online listing - check your pack".
3. **Seed by photographing real packs** (D-058: 15 kids' biscuits first), using OFF
   barcodes/names only to choose which packs to buy.
4. **Ask GS1 India about brand-owner product data** (GTIN-keyed, supplied by the
   brand) - terms and cost unknown; worth one email.

Needs Sushil's acceptance; D-077/D-083 ("after W4") change if accepted.

Accepted by Sushil 2026-09-25 ("it's not allowed"); how listings are used is D-089.

### D-089 · A listing is a lead; the physical label is the record `LOCKED` (2026-09-25)
Proposed by Sushil. Marketplace screenshots (Flipkart, Amazon, Blinkit, Zepto, Swiggy
Instamart…) are collected by hand as **research evidence** of which products to add -
never as the source of a catalogue record:

```
screenshot → identify product → obtain the pack → photograph front + back
           → OCR (/scan) → review (D-028) → InsideLabel product record
```

- **Leads** live in `product_leads` (migration 005): product, brand, variant, size,
  barcode, `source_type` (`marketplace_reference`, `user_share`, `store_visit`,
  `open_data_reference`), `source_platform`, URL, `captured_on`, and
  `evidence_status`: `needs_primary_source` → `pack_obtained` → `label_captured`
  (linked to a version) → `published` (set by the database when that version
  publishes); or `abandoned` with a reason. `tools/leads.py` runs it.
- **Every version records `production_source`** (`physical_label` |
  `marketplace_listing`). The database refuses to publish anything but
  `physical_label`, and refuses to close a lead with a listing-read version. The
  review screen refuses it too, and shows the leads behind a pack as research only.
- **Screenshots stay private** in `research/` (git-ignored), keyed by content hash.
  They are not OCR'd into records, not served by the API, not shown to users, and not
  shared. Only the facts needed to buy the right pack are stored.

Why: the canonical record must be something we can show was read from the pack
(D-028, D-043). The listing may be wrong (Instamart's own terms disclaim its product
information; FSSAI's 2024 advisory), and D-088 rules out copying it.

Residual risk (noted, accepted): the terms quoted in D-088 cover "any similar or
equivalent manual process… to access, acquire, copy". Keeping a handful of
screenshots privately to decide what to buy is low risk; building a bulk archive of
them, or copying listing text into records, is not what this decision allows.

### D-090 · PWA stack: no-build ES modules served by the API `LOCKED` (2026-09-25)
Proposed by Claude while building STATE.md §8 item 6; accepted by Sushil 2026-09-25.
The blueprint (§14) names React + Vite with MLKit/ZXing. Built instead: plain ES
modules in `web/` (`app.js`, `lib.js`, `camera.js`, one CSS file, a service worker),
served by FastAPI at `/app` from the same origin as the API. Barcodes use the
browser's own `BarcodeDetector` (Chrome on Android, which is what the TWA runs, D-010),
with "type the number" (GTIN check digit verified) and the photo path as fallbacks.
No third-party JS.

Why: after D-091 the client only lays out server text, so a framework buys little;
no Node toolchain to install or keep patched on this box (none is installed); one
language to maintain for a solo founder; nothing to build before deploy.
Cost: views are hand-written DOM code (~950 lines of JS); if the UI grows past roughly
double that, or a second front-end developer joins, revisit React + Vite. Not built
here: iOS barcode support (no `BarcodeDetector`; iOS is out of scope, D-010) and the
share target (D-077, after W4 per D-083).

### D-091 · The result screen is assembled on the server `LOCKED` (2026-09-25)
Proposed by Claude; accepted by Sushil 2026-09-25. `/scan` returns a `screen` block
(`lenses/screen.py`) holding everything the result screen says, in display order:
people lines (D-060, D-064), a headline taken from one finding row with its `source`
(D-061), the D-063 band names, the "nothing found" state (D-062), worth-knowing vs
grouped ordinary ingredients (D-065), claim rows only when D-051 releases them, the
retake prompt that names the problem (D-036), and last-verified / re-check lines (D-073).
No score or grade appears in it (D-064).

Why: the wording lint (D-042) can only check Python and `data/`; a sentence
assembled in JavaScript could ship unchecked. The PWA's own strings are linted too
(`tests/test_web.py`), but they are chrome, not findings.

Profiles (D-074): `/scan` takes `profiles=[{ref, age, avoid}]` (≤ 3, nothing else
accepted). Text for a profile carries the literal placeholder `{name}`, which the
device replaces with the nickname; the user's own profile (`ref: "me"`) reads
"you/your". The app never sends `who`. Headline order: released claim contradiction
→ high-concern additive → sugar under ≥ 2 names (maltodextrin excluded,
`added_sugar_adjacent`) → moderate additive → industrial ingredients → partial read →
"No concerns found in the ingredients." (only when the display rule says clean).

### D-092 · Every problem can be reproduced: request ids, scan traces, "Report a problem" `LOCKED` (2026-09-25)
Proposed by Sushil ("capture everything from the beginning to the error, with proof
to reproduce it"); design by Claude; accepted by Sushil 2026-09-25.

- **One id per request.** The app sends `X-Request-ID` (its own UUID, so a request
  that never arrived still has one); the server echoes it, prefixes its log lines
  with it, stores it on the scan row and puts it in every error body.
- **Every scan row is replayable** (migration 006): the model's raw answer before any
  correction, the request options (barcode, profiles as ref/age/avoid, pairing…),
  `build` (git commit), `data_version` (hash of `data/*.json`), engine and prompt
  versions, step timings. Refused, failed and unparseable reads included; a read
  with no parseable ingredients is now recorded too (it wasn't).
- **The phone keeps a trail** of the last 60 events (screens, API calls with status,
  time and request id, camera and photo outcomes, errors, and a name-free summary of
  what each scan showed). Nothing leaves the phone until a report is sent.
- **"Report a problem"** on every page and error screen, separate from "Report a
  mistake" (D-076: wrong content → reviewers). It shows what will be sent, then posts
  `/problem`. A user report holds the photos of every scan in its trail past the
  30-day rule (D-080 "unless flagged"). **App crashes** are reported automatically
  (no comment, no photo hold, once per error per session; the server counts repeats
  from one phone within an hour once). **Unhandled server errors** are stored as
  `server` reports with the traceback.
- **`tools/repro.py show <id>`** prints the trail, versions and scans, replays each
  scan on today's code with storage off, and says whether the result still matches
  what the user saw. `--save NAME` freezes it as `tests/regression/problems/NAME.json`
  (no photos: EXIF, git); edit `expected` to the right answer and the test fails
  until the fix lands.

Why our own and not Sentry first: Sentry groups crashes well but can't hold the
photo + model answer that make a scan reproducible, and it would send user data to a
third party (DPDP). Sentry can still be added for crash dashboards (STATE §8 item 8).
Not recorded: nicknames (D-074; the server also drops `name`/`nickname`/`who` keys),
query strings, response text beyond the headline shown. No session recording.

### D-093 · Google Cloud Vision replaces Tesseract as the independent reader `LOCKED` (2026-09-25)
Direction from Sushil ("we will keep Google Cloud Vision API"); Claude recommended
this role for it over replacing Gemini; switched on after it met the rule below.

Gemini stays the reader (D-030): it returns structure Cloud Vision can't (which text
is the ingredient list, the allergen line, the claims, the product). Cloud Vision
takes Tesseract's job in `ocr_check.py`: the independent check that catches an
additive Gemini dropped (D-034), and the brand/name corroboration.

- One `DOCUMENT_TEXT_DETECTION` call per photo (hints `en`, `hi`), cached by content
  hash and shared by every check. Tesseract read the back photo up to 9 times.
- Same guards as before: a number counts only in additive-class context
  (`prefix_bare_ins`), only numbers with a table row can be added, and OCR only ever
  adds, never overwrites. No voting: the same image gives the same text.
- Tesseract remains the fallback (no key, or a failed call). A failure trips a circuit
  breaker (10 min for configuration errors such as billing/key, 1 min for transient
  ones). `INSIDELABEL_OCR=tesseract` forces the old path. The result names the
  `reader` that ran.
- Independence caveat: same vendor as Gemini, different system (dedicated OCR, not a
  generative model). Accepted for the reason D-034 exists - a model can't catch its
  own omission; a separate reader can.
- Cost (Google pricing page, 2026-09-25): first 1,000 units/month free, then $1.50 per
  1,000 (~13 paise a photo). Closed beta fits in the free tier. Billing must be on
  even for the free tier. Photos already go to Google for Gemini; the privacy policy
  must name Cloud Vision too (§8 item 9). Check Google's data-use terms before launch.

**Baseline to beat** (`tools/compare_ocr.py`, 6 gold back photos, WSL): Tesseract
19.7 s per label for the INS check alone (6.5-29.3 s), recall **27/52** printed INS
(Britannia 3/12, Limca 2.25 L 1/5), **0** wrong additions. Switch on if Cloud Vision
is faster with recall ≥ Tesseract on every label and still 0 wrong additions.

**Result** (same photos, same run, after the fix below):

| | Tesseract | Cloud Vision |
|---|---|---|
| INS check, mean per label | 22.7 s | **3.6 s** |
| Printed INS found | 27/52 | **50/52**, ≥ Tesseract on every label |
| Simulated omissions put back (drop each additive from Gemini's read) | - | **49/51** |
| Wrong additions | 0 | **0** |
| Full Ziggy scan (D-092 trace) | 28.6 s | **4.0 s**, same result |

Fix found on the way: OCR line breaks between a class word and its bracket
("Acidity Regulators⏎(330, 270)") hid 5 printed numbers; `ocr_check` now collapses
whitespace before the context rule (Tesseract unchanged at 27/52: its misses are
misreads). The 2 still missed (Ziggy 1100, 1104) are read correctly but land after a
nutrition-table value in reading order; the context rule is right to refuse them.

Open: Cloud Vision's text isn't stored on the scan row yet, so a replay (D-092) calls
it again; store it (like `model_raw`) once it is switched on.

### D-094 · A replay reads the stored OCR text and never calls Google `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 5); accepted by Sushil 2026-09-25.

Closes the "Open" note on D-093. Migration 007 adds `scans.ocr`
(`{"back": {"reader", "text"}}`), written on every vision-path scan that reached
the OCR step, refused ones included. `repro.py` serves that text back through
`cloud_vision.replaying()`, keyed by the hash of the photo it sends, so:

- a replay gets the same text the scan got, even when the photo has been deleted
  (D-080) or left out of a saved regression (1x1 PNG): the cross-check and the
  brand corroboration come out the same;
- **a replay never calls Google**, key or no key: in replay mode a photo without
  stored text falls back to Tesseract (free, local). Scans from before 007 replay
  that way, with a note saying the cross-check may differ;
- a Tesseract read stores only `{"reader": "tesseract"}`: its check votes over six
  passes, so one text wouldn't replay it, and re-running it costs nothing.

Replay mode is a module global, not a context variable, because the reads run on
worker threads; only `repro.py` (CLI, tests) sets it, never the server. Saved
regressions (`--save`) now carry `ocr` too.

Found on the way: a refused read where the OCR finds an additive the model lacks
crashed `/scan` (`KeyError: 'caveats'` → 500) instead of refusing. Fixed.

### D-095 · Rate limits per install and per IP, in memory `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 6); accepted by Sushil 2026-09-25.

`/scan` and `/problem` are limited on two keys at once: `device_id` (exact for
real users, but the client picks it, so an abuser rotates it) and the IP (can't
be chosen, but Indian mobile carriers put many households behind one address,
so its limit is looser). Checked first, before a photo is read or Gemini called.
Starting values, to tune from beta traffic:

- photo scans: 20 per 10 min and 100 a day per install; 60 / 10 min and 400 a day per IP;
- barcode-only lookups (no model call): their own budget, 120 / 10 min per install,
  600 per IP, so checking a shelf by barcode never uses up photo scans;
- problem reports: 10 an hour per install, 60 per IP.

A refused request isn't counted (the wait doesn't grow while a phone retries,
and one phone's refusals don't use up its neighbours' budget on a shared IP).
429 with `Retry-After` and a plain "wait about N minutes" message.

**Not a scan row.** CLAUDE.md asks every new `/scan` outcome to be stored with
its trace. A 429 is refused before anything is read: there's no photo or model
answer to replay, and storing each refusal would let a flood turn into database
writes. It is logged with its request id instead. **Confirmed by Sushil (2026-09-25).**

**In memory, one process.** Sliding windows in a dict, LRU-capped at 100k keys.
Right for the beta's single server process; with several workers the limits
multiply, and a restart forgets them. Move the counters to Postgres (or Redis)
before scaling out. `X-Forwarded-For` is trusted only when
`INSIDELABEL_PROXY_HOPS` says how many proxies sit in front, counting from the
right. `repro.py` replays switch the limits off.

### D-096 · "Send it to us": the server checks the attempts; the photos are kept `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 7); accepted by Sushil 2026-09-25. Builds D-070.

- **After two refused scans** the retake screen offers "Send it to us". The app
  sends the refused scans' ids to `POST /send-to-us`; the server checks them -
  this install's own (anyone else's looks like "not found"), every one refused or
  unreadable (`refused`, `vision_failed`), at least two, and a back photo stored.
  The app's count is a convenience, not the rule.
- **One review item per pack**, kind `send_to_us`: `scan_id` = the latest attempt,
  `attempt_scan_ids` = the earlier ones (migration 008), so the reviewer sees every
  photo (one may show what another lost to glare). Sending the same attempts again
  returns the same item. The barcode the app read, if any, is pre-filled.
- **Nothing is read automatically**: the reviewer types the label from the photos
  and publishes through the usual `/review` path, or rejects with a reason. Either
  way `/updates` tells the app ("ready" / "couldn't add it yet").
- **The photos are held** (`evidence_hold`), outside the 30-day rule (D-080): the
  user asked us to read them and they are the only copy of the label. The app says
  so before sending ("We keep the photos you took until our team has read them").
- Rate limit (D-095): 10 a day per install, 50 per IP.

Not built: a free-text note with the photos (it could carry names, D-074), push
notifications (D-070 says later).

### D-097 · One login per reviewer; the shared token only bootstraps `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 8); accepted by Sushil 2026-09-25.

The shared `INSIDELABEL_REVIEW_TOKEN` let anyone with it publish under any name.
Now: a `reviewers` table (migration 009), passwords as salted scrypt hashes from
Python's standard library (no new dependency), managed with `tools/reviewers.py`
(`add` prints a generated password once; `reset`, `disable`, `list`).

- **The shared token works only while no account exists**, so switching over
  can't lock Sushil out: migrate, `add sushil`, and from then on it is refused.
  **Confirmed by Sushil (2026-09-25)**, over dropping the token outright; once the first
  account works, the token is also removed from the environment.
- **Form tokens (CSRF) are keyed by the reviewer's password hash**, so a password
  reset also invalidates forms opened before it.
- **Guessing is throttled**: 10 failures per name or 30 per address in 15 minutes
  lock that name/address (429), even for the right password. An unknown name costs
  the same time as a wrong password, so names don't leak.
- HTTP Basic sends the password with every request (each photo too): a verified
  login is cached in memory for 5 minutes, keyed by the stored hash, so a reset or
  disable applies at the next request.

Still HTTP Basic, so HTTPS is required at deploy (it is, §8 item 13). No
roles yet: every reviewer can publish.

### D-098 · Photo retention is a daily job, not a storage lifecycle rule `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 8); accepted by Sushil 2026-09-25. Implements
D-080 and changes its mechanism.

D-080 planned an R2 lifecycle rule on an originals prefix. A lifecycle rule
only sees age; it can't see a problem report's hold (D-092), a pack sent to us
(D-096), an open review item, or that the same photo (keys are content hashes)
was sent again yesterday. So `tools/retention.py` decides, daily from cron:

- a user's scan photo goes 30 days after its **newest** scan;
- kept whatever its age: held scans (`evidence_hold`), photos on any product
  version that isn't rejected (the record's evidence, D-028), scans that an open
  or claimed review item points at (including earlier attempts);
- each key is re-checked just before its file is deleted, in case it was sent
  again after the list was made;
- the row keeps its key (what was there) and gets `photos_deleted_at` (migration
  010); `repro.py` says "photo not available", and with D-094 still replays the
  OCR exactly.

Dry run unless `--apply`; `--days` can't go below 30. D-080's "keep the label-region
crops used as evidence" has nothing to act on yet: no crops are made today, and
evidence rows quote text, not pixels. When R2 comes, give its media class the
same `delete(key)`; no lifecycle rule on user photos.

### D-099 · One INS parser, enforced by a test `LOCKED` (2026-09-26)
Proposed by Claude (overnight session, STATE §8 item 9); accepted by Sushil 2026-09-25.

STATE §8 item 9 named `lenses/compare.py`. A search found four more private INS
patterns: `claims/checker.py`, `tools/eval_vision.py`, `tools/stability_check.py`,
`tools/coverage_report.py`. Most read 3 digits only. All now go through
`core/tokenize.py`, which gains `ins_numbers(text or entries)` ("which INS numbers
would the engine read here?").

What the private copies got wrong, found by tests that fail on the old code:
- `/compare` missed Maliban's printed "160 a(ii)" (annatto) and so called that
  pack "not fully checked", while `/scan` read it fine; it read "Raisins (150gm)"
  as an unknown additive, which also blocks a pack from being the pick.
- `eval_vision.py` counted 1422 as 142 and "160 a(ii)" as 160, on gold and
  prediction alike, so nothing showed. Re-run on the 6 gold labels: the
  report is unchanged (INS F1 1.000), now measured with the engine's parser.
- The claim checker parsed "INS 1105 (…)" as 110. No preservative in the table has
  4 digits today, so no claim result changed.

`tests/test_ins_parsing.py` now fails on any `\d{3…}` pattern in `src/` or `tools/`
outside `core/tokenize.py` (migration file names in `db/migrate.py` excepted).

### D-100 · The front photo: asked for once per pack, read by a reviewer `LOCKED` (2026-09-25)
Proposed by Claude from Sushil's direction ("front photo is for company claims, and we
keep the database of which brand claims what"); accepted by Sushil 2026-09-25.

The front carries the brand's claims and the product's name as sold. The catalogue
wants one per version: it is the claims database, and the claim check (D-051) needs
it once released. But a user shouldn't be asked on every scan, and before this the
front was lost whenever a pack was already in the catalogue (a re-read that found
the same ingredients queued nothing).

- `/scan`'s catalogue block says `front_wanted`: the current version has no front
  photo and none is waiting for review.
- Barcode **+ front only**, for a catalogue product: the reviewed result as usual, the
  photo stored, a `front_photo` review item (migration 011). **No model call** (₹0):
  a front alone can't change a verdict, and a reviewer reads the claims against the
  back photo already on file. Unknown barcode → 422 `back_required`.
- A re-check with back + front and a trusted pairing (D-035) queues the same item; a
  waiting version gets the front attached for its reviewer.
- One waiting item per version; approving it publishes a new version with the photo
  **even when the front makes no claims**, so the app stops asking.
- The app: on a first scan the front is a visible, skippable card (it was folded
  away); on a catalogue hit with `front_wanted`, one "Add the front of the pack?"
  card below the result; a thank-you on `/updates` once reviewed.

Photo retention needs nothing new: open review items already hold their scans (D-098).

### D-101 · `replay` is off on a server unless switched on `LOCKED` (2026-09-25)
Proposed by Claude (noticed overnight, STATE §6 item 4); accepted by Sushil 2026-09-25.

`/scan`'s `replay` field takes a recorded model answer instead of calling the model.
It is how the tests, `tools/repro.py` (D-092) and `tools/queue_predictions.py` work,
but on a public server anyone could send an invented reading: it skips the paid model
step and lands in the review queue as a pending version. Review stops it reaching
the catalogue; it still fills the queue with junk at no cost to the sender.

- The server refuses a non-empty `replay` with **403 `replay_disabled`** unless
  `INSIDELABEL_ALLOW_REPLAY=on`, before anything is read, stored or counted (like a
  429, D-095: nothing to replay, logged with the request id). An empty box is not a
  replay, so `/docs` keeps working.
- In-process tools set `main.REPLAY_ALLOWED = True` (`repro.no_storage()`,
  `queue_predictions.py`); the suite sets the variable in `tests/conftest.py`.
- The public deploy never sets it. A local dev server that wants `replay` in `/docs`
  sets it explicitly.

### D-102 · The beta launches on the web first, invite-only, one code per tester `LOCKED` (2026-09-26)
Its "on the web first" part superseded by D-148 (2026-10-01): the beta runs in the Play Store app; invite codes stay.
Its invite-code part `SUPERSEDED by D-162` (2026-10-06): no codes; the gate stays in the code, off.
`SUPERSEDED by D-184` (2026-10-08): no more beta; the invite gate, `/join` and the join screen are removed from the code.
Direction from Sushil ("launch the website first, then the Android app"; "I will ask
50 people to test and ask feedback"); design by Claude; accepted by Sushil 2026-09-26.

Consistent with D-010 (PWA first, then wrap it): the website *is* the app, and the
Play Store build later wraps the same site, which must be live on the domain anyway.
D-007's closed beta (50-100 testers, W4 retention) now starts on the web.

- **Invite codes** (migration 012, `tools/beta.py`): one per **person**, 8 characters
  without look-alikes (no 0/O, 1/I/L), sent as a link `…/app/#/join/CODE` that fills
  it in. A code serves up to 3 devices (phone + laptop); `reset` clears them for a new
  phone, `revoke` locks the tester out. Wrong codes are throttled.
- **The gate**: with `INSIDELABEL_INVITE_ONLY=on`, `/scan`, `/send-to-us` and `/feedback`
  refuse a phone that hasn't joined (403 `invite_required`), before anything is read
  or stored - logged, not a scan row, like D-095/D-101. Without the database nobody
  gets in. Off by default, so local work and tests are unchanged; **on at deploy**.
  Landing, privacy, about, `/access` and "Report a problem" stay open.
- **Retention per person**: `tools/beta.py list` shows each code's devices, scans, days
  active, first/last scan and feedback: the D-055 W4 number counted per tester.
- **Feedback** ("Send feedback" in the footer): comment + optional 1-5 rating + the
  screen it came from, stored against the code. Separate from "Report a mistake"
  (content, D-076) and "Report a problem" (app broke, D-092).
- **Uploads**: every photo can be taken *or* uploaded (a phone's camera-only input
  hid the gallery); on a computer, choose or drag-and-drop. A barcode can be read from
  a photo where the browser can (Chrome on Android/Mac); otherwise it is typed -
  never read by the AI, since a wrong barcode shows the wrong product.
- **Public pages** at `/`, `/privacy`, `/about` (`web/site/`), wording-linted. Privacy
  and about are **drafts** describing what the app does today; the bracketed parts
  (who is behind it, retention of other data, contact, COI policy) are Sushil's to
  write, and the privacy text needs a DPDP review before the beta opens.

The tester label in `tools/beta.py` is for Sushil only (a first name or "T07"); no
phone numbers or emails are stored.

### D-103 · Only real packs get in: barcode, photo file and photo content are checked `LOCKED` (2026-09-26)
**Amended by D-130 (2026-09-29):** a photo of a screen is now read and marked "from a screen", not
refused; it still never reaches the catalogue. Everything else here stands.
Direction from Sushil ("barcode, back and front photo should be valid, not any random
pic"), after a test scan on 2026-09-26: barcode `12222333333333` + two screenshots of
database software cost a Gemini read, came back as a generic "retake", counted
towards "Send it to us", and was then reported as a mistake. Design by Claude;
accepted by Sushil 2026-09-26.

1. **Barcode, on the server** (the app checked only the check digit; the server
   checked only the length): check digit, then GS1's prefix tables
   (`data/barcode_rules.json`, from the GS1 General Specifications Release 26.0,
   Tables 1-4, 1-5, 1-6 and 2-17, read 2026-09-26). Refused with a plain reason: a
   GTIN-14 with indicator 1-9 (a carton or case; that test code), a shop's in-store
   code (02, 04, 20-29, RCN-8), a book/magazine (977-979), a coupon or refund receipt,
   a demo or reserved number. A GTIN-14 with indicator 0 is looked up as the GTIN-13
   inside it. GS1 Prefix 05 is allowed on purpose (the tables disagree; refusing a real
   pack is worse). The reviewer's barcode field uses the same check.
2. **Photo file, before any paid call** (`photo_check.py`): it must decode as an image,
   be at least 480 px on the long edge and 240 on the short (below the smallest gold
   photo Gemini read correctly, 528×572), and not be blank or black (grey-level
   spread ≥ 8; the 12 gold photos measure 33-68). HEIC passes to the model undecoded.
   Skipped for recorded answers (`replay`), which were read from photos checked then.
3. **What the photo shows - the model reads, rules decide (D-004).** The prompt gains
   rule 7a and a required `image_content` {back, front}: `food_pack`, `screen`
   (a screenshot or a photo of a display, *even when an ingredient list is legible
   on it*: D-089, a listing is a lead, never the record), `not_food`, `not_provided`.
   - Back = screen → refused `back_is_a_screen`; back = not food → `not_a_food_pack`.
     Each has its own headline and retake text, and **can't go to "Send it to us"**
     (`screen.can_send` false; the server refuses them too).
   - Front not a pack → the front is set aside (no claims, no pairing, not attached to
     the version) with a caveat; the scan goes on from the back.
   - Answers recorded before this (tests, regressions, `predictions/`) have no
     `image_content`: they parse as before and no image rule fires. An out-of-vocabulary
     value becomes `unknown`, which no rule acts on.

The prompt changed, so `PROMPT_VERSION` changed.

**Measured on the live model, 2026-09-26** (9 Gemini calls, approved by Sushil; 5-8 s each):

| Input | `image_content` | Outcome |
|---|---|---|
| 5 gold packs (Britannia, Limca 2.25 L, Maliban, Patanjali, Ziggy), back + front | food_pack / food_pack | result; 0 INS missed, 0 invented |
| Limca 1 L gold "photo" | screen / screen | refused `back_is_a_screen` |
| Sushil's dbt screenshot, alone | not_food | refused `not_a_food_pack` |
| Shop-listing screenshot with a legible ingredient list | screen | refused `back_is_a_screen` |
| Document screenshot, alone | not_food | refused `not_a_food_pack` |

- The Limca 1 L gold image is flat brand artwork ("images for representation purposes
  only"), not a photograph of a pack: the model is right, and D-089 agrees. The
  published Limca record uses the real 2.25 L photos, so the catalogue is unaffected;
  replace the 1 L gold image with a photo of a real bottle when the gold set grows.
- Found and fixed: with a single photo the model isn't told its role, and described it
  under `front` ({"back": "not_provided", "front": "not_food"}), which the first version
  turned into `unknown` and let through. With one image, its description counts
  whichever key the model used. The 9 recorded answers were replayed through the fix.
The D-100 front-only path (barcode + front, no model call) gets the file check only;
its reviewer rejects a front that isn't a pack.

### D-104 · Barcodes come from the camera or a photo, never typed; every photo gets a tick or a cross `LOCKED` (2026-09-26)
Direction from Sushil ("no manual barcode entry: it should come from an uploaded photo or
the scanner, because a wrong entry will cost us… after uploading any picture, show a
green tick or a red cross, and why"); details by Claude; accepted by Sushil 2026-09-26.

- **No typed barcode.** The app offers the live scanner (Chrome's detector, where the
  browser has one) and "take or upload a photo of the barcode". "No barcode? Photograph
  the ingredients" stays. A photo's barcode is read on the **server** with zxing-cpp, a
  classical decoder (not a model: it reads the bars or reports nothing), so it works in
  every browser, iPhone and desktop included. New dependency: `zxing-cpp` (a
  self-contained wheel, no system library).
- **`POST /check-photo`** (role barcode / back / front): the photo checks of D-103
  (decodes, size, not blank; a barcode close-up has no size floor) plus any barcode on
  it. No model call, nothing stored, rate-limited, invite-gated. A barcode photo is ✓
  only with exactly one retail barcode that passes the GS1 rules; several different
  ones, none, or a non-retail one (book, carton, in-store) is ✗ with the reason. A back
  or front photo is ✓ when it is a readable picture ("we'll read the ingredient list
  when you tap Check this pack": the tick is about the photo, not a promise about the
  label, which only the model's read decides, D-103); a barcode found on it is used.
- **In the app**, each photo shows the tick or cross with the server's reason under it.
  A ✗ back keeps "Check this pack" off; a ✗ front is not sent. When the check can't run
  (offline, server error) the photo is marked "couldn't check" and still allowed:
  `/scan` checks it again.
- **One key per pack**: a 12-digit UPC-A is stored as its 13-digit form (leading 0),
  since the camera and zxing report it differently; UPC-E is expanded. No barcode was
  on file yet, so nothing existing changes.
- `/scan` takes `barcode_source` (`camera` or `photo`) and records it on the scan row;
  anything else is refused. It can't prove where the number came from (an API client
  could still send one); it records what the app says, for audits.

On the 12 gold photos zxing found the one barcode that is in frame (Patanjali back,
8906032018810) and nothing on the others; label photos rarely show the barcode, so
the dedicated barcode photo is the main route and a barcode on the back is a bonus.

### D-105 · "Before you start": every tester agrees to real-pack rules before a first scan `LOCKED` (2026-09-26)
Direction from Sushil ("correct data is important; in the beta there will be wrong data or
AI feeding; an 'I agree' and conditions on the first or home screen"); wording and
mechanism by Claude; accepted by Sushil 2026-09-26.

- **The screen** comes right after joining (D-102) and before the welcome, and again
  whenever the text changes. Five points, one "I agree to these rules" box, "Continue"
  stays off until it is ticked:
  1. I am a real person using InsideLabel myself, not an automated program.
  2. I will only photograph real packs that I am holding or that are in front of me.
  3. I will not upload pictures made or changed by AI, edited photos, or screenshots.
  4. What I send may be checked by a person; made-up or altered pictures are removed
     and can close my invite.
  5. InsideLabel shows ingredient facts from the label, not medical advice.
- **The text is data** (`data/terms.json`, versioned, wording-linted): change it, bump
  `version`, and every tester is asked again.
- **Recorded and enforced on the server** (migration 013 `agreements`: install, version,
  time). With `INSIDELABEL_INVITE_ONLY=on`, `/scan`, `/check-photo`, `/send-to-us` and
  `/feedback` refuse a phone that hasn't agreed to the current version (403
  `terms_required`, before anything is read). `tools/beta.py list` shows who agreed.
- **What it is and isn't.** A tick doesn't stop a determined person or a program; it is
  the rule we point to when removing made-up data or closing an invite
  (`tools/beta.py revoke`). The checks that catch bad data are D-103/D-104 (barcode,
  file, screen/not-food) and the reviewer. Not built, worth considering: marking photos
  uploaded from the gallery (vs taken with the camera) for reviewers, since an AI-made
  picture can only arrive as an upload.

### D-106 · Uploaded photos are marked for reviewers `LOCKED` (2026-09-26)
Proposed by Claude under D-105; Sushil asked for it to be built ("yes"). Details by Claude;
accepted by Sushil 2026-09-26.

An AI-made or edited picture, or a photo of a screen, can only reach us as an upload,
never from the live camera. The app already knows which button produced each photo.

- `/scan` takes `back_source` and `front_source`: `camera` (taken in the app) or `upload`
  (the gallery, a computer, dragged in). Anything else is refused; a source for a photo
  that wasn't sent is ignored. Stored as `request.photo_sources` on the scan row.
- **The reviewer** sees, under each photo: "Uploaded, not taken with the camera. Before
  publishing, look closely for signs of editing, an AI-made picture or a photo of a
  screen", or a quiet "Taken with the app's camera". Earlier attempts of a pack sent to
  us are marked the same way. The queue shows an "uploaded" chip on those items.
- Recorded, not proved: a modified client could say `camera`. It points a reviewer's
  attention; the D-103 checks and the reviewer decide. Older scans say nothing.
- Not built: reading the camera details (EXIF) of an upload before the app re-encodes
  it. A real phone photo carries the phone model and the time taken; a screenshot or a
  generated picture usually carries none. Worth adding if uploads turn out common.

### D-107 · No barcode: the user gets a result, the catalogue gets nothing `LOCKED` (2026-09-26)
Direction from Sushil ("keep 'No barcode? Photograph the ingredients'; if there's no
barcode, only ingredients, allow the user to scan but no entry in the database");
details by Claude; accepted by Sushil 2026-09-26 (scan row kept for replay).

The catalogue is filed by barcode (D-024): a record without one can't be found again by a
scan, and two different packs couldn't be told apart.

- **The button stays**, and moves up: "No barcode? Photograph the ingredients" is now a
  full button right under the camera, above the barcode-photo option. It had been a small
  link at the bottom of the screen, easy to miss on a phone.
- **A scan without a barcode** is read and judged as before, and the user sees the result
  with a note: "This pack has no barcode, so it isn't added to our catalogue. The result
  above is from your photo, just for you." It creates **no product, no version and no
  review item** (`catalogue.status: "not_saved"`).
- **The scan row is kept** (outcome `unlisted`, migration 014), so a reported problem can
  still be replayed (D-092); its photos are deleted at 30 days (D-098), since no version
  holds them. *If "no entry" should mean no row at all, that is a one-line change, at the
  cost of replaying those scans.*
- **Nothing gets in another way**: "Send it to us" needs a barcode (the app doesn't offer
  it; the server refuses `no_barcode`), and a reviewer can't create a new product without
  a barcode (a "Report a mistake" on an unlisted scan can only be rejected).
- `tools/queue_predictions.py` now reads each gold pack's barcode from its photos (or
  `--barcode ID=DIGITS`) and skips a pack without one.

### D-108 · A front of one pack with the back of another is refused `LOCKED` (2026-09-26)
Reported by Sushil ("front image of one product and back image of another, it's
allowing"); cause and fix by Claude; accepted by Sushil 2026-09-26. Amends D-035 (the user's "same pack"
tick resolves "can't tell", never "different packs").

**Reproduced** on the live server: Patanjali Doodh Biscuits front + Maliban wafer back,
"same pack" ticked. Gemini said `mismatch` (front Patanjali; back a wafer by Reliance
Consumer Products). The code required a *matching* anchor before keeping any
match/mismatch verdict, which a mismatch can never have, so it became `indeterminate`;
the tick then trusted the pairing and Patanjali's claims ("100% ATTA", "MORE FIBRE"…)
were attached to the wafer. With a barcode they would have reached the review queue.

- **A mismatch is kept** when nothing checkable matches across the two faces (no shared
  brand, name or manufacturer) **and** the model's own evidence names a difference
  ("different", "vs", "not the same"…). A Limca bottle was once called `mismatch` on
  evidence describing what matched ("printed on both", "matching design"): that stays
  `indeterminate`. A code-only brand comparison was ruled out: a real Limca 2.25 L back
  reads its brand as "The Coca-Cola Company", and a real Maliban back never prints
  "Maliban".
- **A kept mismatch refuses the scan** (`product_mismatch`, as `gates.py` always
  intended): "These two photos look like different packs. Photograph the front and back
  of the same pack, or just the back." The tick can't override it; it can't go to "Send
  it to us"; "Retake" clears both photos. Refused rather than using the back alone: a
  user holding pack A's front would read pack B's result as A's.
- **"Can't tell" without the tick** still gives the back's result, and now says so on
  screen: the front photo wasn't used (it used to be a small-print disclosure).
- **Measured:** 12 reads of the 6 genuine gold pairs (recorded + live today) all keep
  their result; the wrong pair is refused. 12 genuine reads is a small sample: watch
  `product_mismatch` refusals in the beta.

### D-109 · "Report a mistake" needs a note or what the pack says `LOCKED` (2026-09-26)
Proposed by Sushil ("empty reports give reviewers nothing to act on"); details by
Claude; accepted by Sushil 2026-09-26.

Both reports on the local queue so far came in empty: #8 (D-103's screenshot test) and
#9 (field "other", no note). Today the form sends a field from a drop-down plus two
optional boxes, "What does the pack say?" (`proposed_value`) and "Anything else?"
(`note`), and `ReportRequest` accepts both as `null`. A reviewer holding "Something
else" and nothing more can only reject it, and the tester who sent it hears nothing
useful back (D-076's "ready?" on `/updates`).

- **The rule:** a report needs **at least one of** "What does the pack say?" or
  "Anything else?" with real text (after trimming, at least 3 characters, so a single
  "." or "ok" doesn't count). The field choice alone is not enough, whichever it is.
- **In the app:** both boxes lose "(optional)"; a line above them says "Tell us what
  the pack says, or what looks wrong. One of the two is enough." "Send to our team"
  stays on, and tapping it with both empty shows that same line as the error, next
  to the boxes, rather than a disabled button nobody can explain.
- **On the server, too** (a client can skip the app's check): `/report` answers
  **422 `empty_report`** with the same plain sentence, before anything is stored.
  The check runs after `no_subject` and before the scan lookup.
- **Nothing else changes:** no minimum length beyond the 3 characters, no per-field
  wording, and the wording lint covers the new text. Existing tests that post a note
  keep passing; the 404/422 cases in `test_scan_db.py` gain a note so they still test
  what they name, and new tests cover empty, whitespace-only and one-box-filled.
- **Not proposed:** requiring a photo with the report (it slows the only feedback path
  on the result screen), or making the field more specific (the drop-down already says
  where to look; the text says what's wrong).

### D-110 · The website takes the Lovable look, not the Lovable app `LOCKED` (2026-09-26); its type and its colour shades `SUPERSEDED by D-185` (2026-10-08)
Direction from Sushil ("implement the look and feel [of `insidelabel_lovable`] in our
website"); review and details by Claude; accepted by Sushil 2026-09-26.

`insidelabel_lovable/` is a second, complete app (TanStack Start, React, Tailwind,
Supabase, 40+ UI components), not a theme. It carries its own TypeScript copy of the
engine and of six `data/*.json` tables (identical to ours today) and reads photos with
`openai/gpt-6-astra` through the Lovable AI Gateway. Only its **look** is taken.

**What is ported** (CSS in `web/app.css` and `web/site/site.css`; no JS logic changes):
- The "Fresh Air" palette: cream background, deep-blue text (no black), leafy green
  for actions, aqua and pastel surfaces, red and orange kept for findings that must
  catch the eye. Our status colours map onto it: `--stop` → Lovable `alert`,
  `--unsure` → `warn`, `--calm` → `secondary` (aqua).
- Type: **Bricolage Grotesque** for headings, **DM Sans** for text.
- Shape: 16 px radius, soft shadows, the hero gradient on the landing page and home,
  pill chips, cards that lift slightly on hover, buttons that press down, the "IL" mark
  in the header, the segmented switch style.
- Dark mode keeps following the phone's setting (`prefers-color-scheme`), with
  Lovable's dark values.

**Changed from Lovable, measured** (WCAG AA needs 4.5:1 for normal text):

| Pair | Lovable | Proposed |
|---|---|---|
| White on the green button | 2.65 | 4.82 (green `#048149`, oklch 0.53) |
| Red allergen text on its pink card | 3.95 | 4.68 (red `#c92324`, oklch 0.54) |
| Muted text on the cream background | 4.36 | 4.5 (oklch 0.55) |

Every other pair checked passes (deep-blue text on cream 8.6; dark mode 5.1 to 11.8).
The original lighter green stays for large decorative areas that carry no text.

**Fonts: self-hosted, not Google Fonts.** Lovable loads them from `fonts.googleapis.com`,
which sends every visitor's IP address to Google on each page, a processor the privacy
page doesn't name, and fails offline. Proposed: the two fonts (SIL Open Font License) as
`woff2` files in `web/fonts/`, only the weights used (about 100 KB in all), cached by
`sw.js`, `font-display: swap` so text shows at once in the system font on a slow phone.
The "system fonts, no web fonts" note in `app.css` is replaced.

**Not taken, and why:**
- **The app itself**: its engine, Supabase, auth and AI Gateway. D-090 (no build step, no
  third-party JS), D-091 (result text built in `lenses/screen.py`) and D-093/D-103 (our
  reader and its checks) stand. Its copies of `data/` would drift from the reviewed
  tables, and its scans skip the catalogue, the review queue, replay (D-092), the photo
  checks (D-103/D-104), the barcode rule (D-107) and the rate limits.
- **A coloured verdict banner** ("Clean" / "Mixed" / "Ultra-processed" as the biggest
  thing on screen) and uppercase `HIGH` / `MODERATE` badges: D-060/D-091 put people and
  allergens first, with the headline taken from a finding.
- **Its wording**: "See what's really inside", "read what the pack doesn't say",
  "hidden sugars" (suggest the brand hides something, D-042/D-071), "labelling breach"
  (a word from the D-042 list's family), the ⚠️ emoji on the claims heading.
- **"Paste ingredients"**: typed text isn't a physical label (D-089), and has no barcode
  or photo for a reviewer.
- **AI-drafted claim rules** (Lovable's admin): legal facts come from primary documents
  (D-046), and the claim check is in shadow (D-051).

**The folder stays until the port is done** (Sushil, 2026-09-26: "keep it till we are
done, then will remove"; he is adding to it by hand). Claude reads it as a reference and
doesn't edit or delete it; Sushil removes it when the look is in `web/`.

**Checks when built:** `tests/test_web.py` and the wording lint pass; a headless-Chromium
walk of every screen at phone width in light and dark, with screenshots for Sushil
before merge; `APP_VERSION` and the `sw.js` cache version bumped.

### D-111 · Additive cards with a badge, in FSSAI's terms `LOCKED` (2026-09-26)
Direction from Sushil ("I liked their UI, banned / caution / safe kind of thing"), after
screenshots of the SafeLabel Play Store listing; wording and conditions by Claude; mockup
liked by Sushil 2026-09-26; accepted by Sushil 2026-09-26.

SafeLabel shows each additive on its own card with a coloured stripe and a badge
("Banned", "Caution", "Safe"), a "Risk level", and a banner ("All Clear - No Harmful
Additives Detected. Enjoy your product with peace of mind!"). The layout is taken; the
words are not. Its "Banned" sits on tartrazine, which our verified status table
(`data/regulatory_status.json`, 2026-09-25) has as permitted with limits in India,
permitted with a warning in the EU and permitted in the US; and "safe" is on the D-042
list.

- **Every additive on the result gets a card** (INS number, name, "On the label: ..."
  quoting what was read, the row's `why` line, a badge). Plain ingredients (flour, salt,
  oil) stay in the one grouped "look ordinary" line, so the screen doesn't grow by forty
  cards.
- **Three badges, each a fact with a source:**

  | Badge | Colour | Shown when |
  |---|---|---|
  | Not permitted in India | red stripe, ✕ | the row's FSSAI basis says Appendix A gives it no use in any food (today 924a, 927a, 952) |
  | Worth knowing | orange stripe, ! | concern `high` or `moderate`, FSSAI permits it |
  | Permitted in India | green stripe, plain dot | concern `low` or `none` **and** `fssai_basis` is recorded on the row |

  No tick mark (it reads as approval), no "risk level" (D-064), no "all clear" banner: the
  existing "N other ingredients look ordinary" line stays. A row with no recorded FSSAI
  basis gets no "Permitted" badge.
- **"Not permitted" is the most serious thing the app says about a pack.** It shows only
  on a complete read at confidence ≥ 0.95 (the allergen gate, D-060), quotes the label,
  asks the user to check the pack ("if we misread it, tap Report a mistake"), and opens a
  red banner above the cards: "An additive on this label isn't in FSSAI's permitted list".
  It never names or judges the brand (D-042). With a barcode, the scan also goes to a
  reviewer, like a pending version. A partial or low-confidence read shows the card as
  "Worth knowing" with a note that the number needs checking.
- **Built on the server** (D-091): `lenses/screen.py` adds `badge: {kind, text}` to each
  additive item and the banner to the screen block; the PWA only lays it out. The wording
  lint covers the new text. D-086 holds: EU/US status never picks a badge.
- **First, the data.** 32 of 67 rows in `data/additives.json` (102 and 110 among them)
  carry no `fssai_basis` / `verified_on`. They are verified against the FSSAI compendium
  Appendix A (D-046) before the badges ship, or "Permitted" would be missing on most
  common additives. No paid call is needed.

Order when accepted: verify the 32 rows (its own commit, each row with `fssai_basis` and
`verified_on`), then the badges with tests, then phone-width screenshots before merge.

### D-112 · The logo: barcode and a gold magnifier on deep green `LOCKED` (2026-09-26)
Direction from Sushil: a logo image in the Drive `InsideLabel` folder (a Gemini-made picture of
two phones: a green circle, a barcode, a white tick, "INSIDE LABEL / YOUR FOOD GUARDIAN");
then "B" of three redraws, "blending green with yellow or golden shades", then "B1".
Drawing by Claude; accepted by Sushil 2026-09-26 ("yes pls B1").

- **The mark (B1):** a rounded deep-green tile (#07924f to #035c34) with white barcode bars
  on the left and a magnifier on the right: gold rim and handle (#ffd166 to #e9a91c), gold
  lines inside the lens. It says what the app does, reads the label. Gold on the deep green
  is 4.6:1 or more, so it stays clear at 16 px.
- **Why not the image as it was:** the white tick reads as "approved", the message D-042 keeps
  out and D-111 took off the "Permitted" badge; "Your food guardian" promises protection,
  close to "safe", for an app that can misread a label; the picture carries Gemini's
  watermark and a real brand's pack (Aashirvaad Atta, ITC). The tagline stays "See what's
  inside the pack".
- **Where it goes:** one SVG source; `web/icon.svg` and `icon-maskable.svg` (the mark inside
  the maskable safe zone), the header "IL" mark in the app and the site pages, the favicon,
  and PNGs at 192 and 512 px for Play (D-011, STATE §8 item 14). `manifest.webmanifest`
  theme colour unchanged.
- **Checks when built:** the mark at 16, 32, 48, 192 and 512 px on light and dark; screenshots
  of the header before merge; `APP_VERSION` and the `sw.js` cache bumped.

### D-113 · A Pro chatbot, "ask about this pack", personalised `LOCKED` (2026-09-27)
Direction from Sushil ("[not a chatbot] was the initial one; now the plan is to give this to a
Pro user as per their plan and personalization"; the reason `insidelabel.ai` is the main
address). Conditions by Claude; accepted by Sushil 2026-09-27 ("need to change now, as in this
way people will buy subscriptions"). D-001's "not a chatbot" clause is superseded by this entry;
the rest of D-001 stands. Not built yet.

- **Pro only, after the W4 retention answer** (D-083: Wave 2 waits for the W4 number). It is a
  candidate answer to D-082 (what Premium is for) and part of D-053 (pricing), both still open.
  The free product stays as it is: scans stay free and uncapped (D-053).
- **It explains; it never judges (D-004).** It answers only from what InsideLabel already holds:
  the scan's `screen` block and evidence, the data tables and their FSSAI basis (D-046, D-086).
  It may explain why a finding is there and quote the label; it never makes a new verdict,
  concern level or allergen state, and never says "safe" (D-042).
- **Personalised with what the app already keeps:** a profile's age band and avoid list, never a
  nickname (D-074). Allergen answers keep the 0.95 gate and "can't confirm" (D-060); below it,
  the answer says the label couldn't be read well enough.
- **Every answer passes the wording lint before it is shown** (`tests/test_wording.py` rules at
  run time); a failing answer is not shown. Not medical advice: health questions get the same
  line the landing page uses.
- **Replayable like a scan** (D-092): question, context and the model's raw answer are stored.
- **A second DPDP check before launch**: it uses children's data (age band, avoid list) in a new
  way.

### D-114 · Hosting: one Google Cloud server in Mumbai, DNS on Cloudflare `LOCKED` (2026-09-27)
Direction from Sushil ("host the web beta on insidelabel.ai"; asked whether Cloudflare could
host it; first chose AWS Lightsail, then Google Cloud: "go with google cloud for now, will change
in future if any issue", 2026-09-27). Details by Claude. Checked on the providers' own pages
2026-09-27. **Accepted by Sushil 2026-09-27** ("accepted").

**Why not Cloudflare for the app.** Python Workers run pure-Python or Pyodide-built packages
only; we need `psycopg`, `zxing-cpp`, Pillow and Tesseract. Cloudflare Containers run any image,
but "All disk is ephemeral. When a Container instance goes to sleep, the next time it is
started, it will have a fresh disk": the database, the photos and the in-memory rate limits
(D-095) would be lost. Hyperdrive only speeds up a database hosted elsewhere. Cloudflare is used
for what it fits: DNS now, R2 for photos later.

**Why Google Cloud.** Sushil already has the account (the Gemini and Cloud Vision keys) and
free-trial credit on it. Google Cloud India bills an Indian address in INR with 18 % GST.
The runner-up was AWS Lightsail, Mumbai: $12/mo for 2 GB, 2 vCPU, 60 GB and 1.5 TB transfer in
one fixed price (compared with Vultr, Akamai/Linode and DigitalOcean the same day). Google
charges the VM, disk, static IP and outbound traffic separately; the monthly total is read from
Google's pricing calculator, not recorded here. Moving to Lightsail later is a restore.

**Conditions, because of the billing (from Google's free-trial page):** at the end of a trial
"All resources you created during the trial are stopped" and Compute Engine data "is marked
for deletion" (30 days' grace), and a suspended billing account stops every linked project. So:
- The billing account is **upgraded to a paid account with automatic card payment (post-paid)
  before invites go out**. Upgrading keeps the unused credit until it expires; the credit is
  spent first. Not the prepaid kind the Gemini key's project uses (it ran out on 2026-09-25).
- The server lives in **its own project** (`insidelabel-prod`), apart from the key project.
- A **budget alert** on the billing account (about ₹1,500 a month to start).

**The beta setup (step 1):**
- **One Compute Engine VM**, Mumbai (`asia-south1`), Ubuntu 24.04 LTS, **`e2-medium`** (2 vCPU
  sharing one full core, bursting; 4 GB), 30 GB balanced disk, a static external IP. Two vCPUs
  because Gemini and Cloud Vision run on worker threads per scan, PostgreSQL shares the box, and
  the Tesseract fallback is CPU-heavy (D-093). `e2-small` (2 GB, half a core) is the cheaper
  step down if the credit ends and the load allows; resizing is stop, change type, start.
  The Always Free `e2-micro` is only offered in three US regions, so it doesn't apply.
- **Firewall:** 22 (SSH, keys only), 80 and 443; nothing else. PostgreSQL listens on localhost.
- **Caddy** in front for HTTPS (automatic certificates), then **one uvicorn process** under
  systemd (one process because the rate limits live in memory, D-095).
  `INSIDELABEL_PROXY_HOPS=1` (Caddy is the only proxy).
- **PostgreSQL 18 on the server** (18.6 in the PGDG apt repository for noble, checked
  2026-09-27), not 19: 19 is still a beta, and D-087 itself keeps the schema portable to 16-18 for
  a host without 19. Move to 19 by dump and restore once it is released (expected end October),
  in its own step. D-087's heading now points here; local work stays on 19.
- **Photos on the server disk** (`INSIDELABEL_MEDIA`) until R2 is built.
- **Settings in one root-only file** read by systemd, never in the repo: `GEMINI_API_KEY`,
  `GOOGLE_VISION_KEY` (D-093), `INSIDELABEL_DB`, `INSIDELABEL_MEDIA`, `INSIDELABEL_BUILD`,
  `INSIDELABEL_INVITE_ONLY=on` (D-102), `INSIDELABEL_PROXY_HOPS=1`,
  `INSIDELABEL_PUBLIC_URL=https://insidelabel.ai` (invite links, `tools/beta.py`).
  `INSIDELABEL_ALLOW_REPLAY` and `INSIDELABEL_CLAIMS_TO_USERS` are never set (D-101, D-051), and
  `INSIDELABEL_REVIEW_TOKEN` is not set: reviewers log in with accounts (D-097).
- **Daily jobs** (systemd timers): `tools/retention.py --apply` (D-098), and a `pg_dump` kept 14
  days on the server. A daily **disk snapshot schedule** (Compute Engine) holds the off-server
  copy until backups go to R2. One restore of a dump into a scratch database is done before
  invites go out, and written down in `DEPLOY.md`.
- **Domains:** `insidelabel.ai` (registered at Cloudflare) is the main address. `insidelabel.in`
  stays registered at GoDaddy with its nameservers moved to Cloudflare, so DNS and redirects live
  in one place. `insidelabel.in`, `www.insidelabel.in` and `www.insidelabel.ai` redirect
  permanently (301) to `https://insidelabel.ai`. Cloudflare proxy **off** (DNS only) at first.
  Both domains on auto-renew.

**Later, each its own decision when its signal shows up:**
1. **Weeks after launch:** PostgreSQL 19 once released; photos and backups to R2 (retention
   still runs our job, D-098); Cloudflare proxy on, with Caddy trusting Cloudflare's ranges and
   the proxy hops changed, so testers don't share one IP's rate limit.
2. **After the W4 answer (D-055):** below 20 %, stop and spend nothing more on hosting. At 30 %
   or more, and only when slow scans, memory, CPU or disk say so: a bigger machine type first;
   then rate-limit counters in PostgreSQL (D-095) and a second app process; then the database
   on its own server or Cloud SQL in Mumbai with point-in-time recovery.
3. **Pro and the chatbot (D-113):** more app servers behind Cloudflare, and a job queue (RQ on
   Redis) for the slow model calls.

Nothing ties us to Google: plain Ubuntu, PostgreSQL and S3-compatible storage, so moving
(to Lightsail or anywhere) is a restore.

### D-115 · Processing markers are shown in the pack's words, not our table's `LOCKED` (2026-09-27)
Found by Claude on the first real scan on the live site (Sushil's phone, an Organic India
Tulsi Mulethi pack, 2026-09-27); Sushil asked for it to be fixed before invites ("yes please").
**Accepted by Sushil 2026-09-27** ("accepted").

The headline read "Made with industrial ingredients, such as added flavour
(natural/artificial/nature-identical)", and the "Worth knowing" card showed
`On the label: "added flavour (natural/artificial/nature-identical)"` **in quotation marks**.
Neither came from the pack: both are the name of the matching row in
`data/nova_markers.json`. `lenses/screen.py` used table names on purpose (an ingredient as read
can be a fragment like "flavours (natural"), but the side effect breaks D-042/D-071 ("quote the
label; don't characterise it"): whatever the pack says, even only "natural flavour", the screen
put "artificial" next to a named brand's product, and presented it as a quote. Six of the 17 row
names carry words a pack may not say:

| Row name | A pack may print | Words the screen added |
|---|---|---|
| Added flavour (natural/artificial/nature-identical) | "natural flavour" | artificial, nature-identical |
| Artificial / non-sugar sweetener | a sweetener's name | artificial |
| Hydrogenated / interesterified oil | "hydrogenated vegetable oil" | interesterified |
| Stabiliser / thickener / humectant (cosmetic use) | "thickener" | cosmetic use, our label |
| Whey protein isolate (as additive) | "whey protein isolate" | as additive, our label |
| Bulking / anti-caking / glazing agents | "anti-caking agent" | bulking, glazing |

- **The fix:** each marker finding carries `label_term`, the words to show. It is the ingredient
  **as read** when that is a whole term (no bracket characters); when it is a fragment, the
  longest of **that row's own known names** found inside it (for "flavours (natural", "flavour").
  Both are words on the pack. The headline and the card's `On the label: "..."` use it.
- **Nothing that judges changes:** which row matches, the band, the verdict, the concern and the
  score are computed exactly as before (D-004). Only the words shown change.
- **The table name stays where it is a reference, not a quote:** the card's technical line
  ("NOVA group 4 markers: ...", our table row), the reviewer's finding text and rule code
  (`db/store.py`), and the compare screen (which shows only "N ultra-processed ingredients").
- **Tests:** for every known name of every row, a label printing it gives a headline and a quote
  made only of words from that label; the six rows above never show their added words unless
  the label prints them; the Tulsi Mulethi case shows "natural flavour".
- **Checked on the six gold labels** (recorded readings replayed, no model call): every headline
  and verdict unchanged; only the quotes changed, and on every label, not just rows with a slash:
  Britannia "glucose syrup, ..., added flavour (natural/artificial/nature-identical)" became
  "liquid glucose, emulsifiers, anticaking agent, humectant, flavouring"; Patanjali's became
  "liquid glucose, invert syrup, artificial flavour, emulsifier"; both Limca labels "flavour".
- **Not proposed:** renaming the table rows (the names are right as categories for reviewers
  and the technical line), or changing what the rows match (a separate question: today "stevia",
  "sucralose" and "interesterified vegetable fat" match no marker row).

### D-116 · A pack licensed only as an AYUSH medicine is not food: it stays out of the catalogue `LOCKED` (2026-09-27)
Found by Sushil and Claude reviewing the first live item (review item 2 on the server,
ORGANIC INDIA Tulsi Mulethi, barcode 0801541605019, 2026-09-27). Its back prints "Ayurvedic
Medicine Mfg. Lic. No. A-2755" and "Certified Organic as per NPOP"; Sushil checked the whole
pack: **no FSSAI logo or licence number anywhere**. **Accepted by Sushil 2026-09-27** by rejecting
item 2 on this ground ("done. rejected").

**The law, read from the primary text** (Food Safety and Standards Act 2006, section 3(1)(j),
FSSAI's own copy, fssai.gov.in/upload/uploadfiles/files/FOOD-ACT.pdf, read 2026-09-27): "food"
means any substance intended for human consumption ... "but does not include any animal feed,
live animals ..., plants, prior to harvesting, **drugs and medicinal products**, cosmetics,
narcotic or psychotropic substances". A product made under an Ayurvedic medicine manufacturing
licence and carrying no FSSAI licence is sold as a medicinal product. Every InsideLabel
judgement uses FSSAI rules only (D-086), and those rules don't cover it.

- **The rule:** a pack whose only licence is an **AYUSH drug licence** (an Ayurvedic, Siddha or
  Unani medicine manufacturing licence) **and no FSSAI licence** doesn't enter the catalogue.
  The reviewer **rejects** it with the reason "Not food under the FSS Act: AYUSH medicine
  licence, no FSSAI licence (D-116)", and the licence as printed in the note.
- **A pack with an FSSAI licence is food**, whatever else it prints (an organic mark, Ayurvedic
  wording, herbs): it is reviewed and published as usual. When a pack prints both licences, the
  FSSAI one decides.
- **The reviewer checks the whole pack** for the FSSAI logo and 14-digit licence number before
  rejecting, as Sushil did here. The review screen shows only the photos taken; if the licence
  can't be seen in them, "Put back in the queue" and look at the pack.
- **Nothing changes for the user yet.** Today a scan of such a pack still gets a result built
  with food rules. Proposed separately, not part of this decision: the reader notes a drug
  licence on the back (it already reads `fssai_licence`), and the result then says plainly that
  the pack is licensed as an Ayurvedic medicine and our checks follow FSSAI food rules, showing
  the ingredients as read without a food verdict. Needs its own wording check (D-042) and tests.
- **No judgement of the brand or the product** (D-042): the reason states the licence, as
  printed, and the Act's definition; nothing about the product's quality.

### D-117 · Review agents: Gemini drafts, a checker confirms, a person sees only the doubtful items `LOCKED` (2026-09-27)
Direction from Sushil, after reviewing the first run by hand ("one agent will draft and another
agent will confirm; if any ambiguity then human will review"; drafter: Gemini). Details and
safeguards by Claude. **Accepted by Sushil 2026-09-27** ("accepted"), with point 7 added at his request.

**Why.** On 2026-09-27 every item of the first supermarket run needed the same mechanical work:
rejoin compound ingredients the reader split at a bracket, split two ingredients the pack ran
together, read the category the pack declares, otherwise pick it from the Codex descriptors,
clear taglines and pack sizes out of the claims, write a note. A person can't keep doing that for
the 50-SKU seed (D-058) and beyond. What a person must keep doing is catch the doubtful cases:
the Ayurvedic-medicine pack (D-116), a garbled line that dropped words (Bisk Farm TOP GOLD), a
"Sugar Free" claim.

**This changes a standing rule.** Until now only a person on `/review` publishes (CLAUDE.md, "the
catalogue is reviewed data"; D-029: the verified catalogue is the asset). Under D-117 a record can
also be published when two independent checks agree. The door stays the same:
`ReviewService.approve()` then `publish_version()`, with every database rule still in force
(`physical_label` only, D-089; category required). Agent-published versions carry
`verified_by = 'agent'`, so they are always distinguishable from a person's.

**1. The drafter (Gemini, a new prompt `review_draft`, versioned like the reading prompt).** For
each new-product or reformulation item it gets the pack photos, the scan's reading, the Cloud
Vision text already stored on the scan (D-094), the Appendix A category list, the four claim rules
and the review conventions written down on 2026-09-27. It returns, as JSON: brand, name, variant,
category code and **where it came from** (`pack_declared` or `descriptor`), ingredient lines,
allergen line, front claims, a note, whether an AYUSH licence is visible, and a list of its own
doubts. It reads and drafts; it never decides (D-004).

**2. The checker confirms, and is deliberately not a second call to the same model** (which would
repeat Gemini's blind spots). It is rules plus the one independent reader we already have,
Cloud Vision. An item is **confirmed** only if every check passes:
- every word of the drafted ingredient lines appears in the Cloud Vision text of the back photo,
  and every line's brackets balance;
- the category exists; when the pack text declares one ("Proprietary Food - 4.2.2.5"), the draft
  equals it; otherwise the draft equals the category a fixed word table gives, and the table gives
  one;
- barcode valid (D-103), photo checks passed, front and back not flagged as different packs
  (D-108);
- the reading passed the 0.95 confidence gate on a complete read (D-060);
- the allergen line appears in the Cloud Vision text;
- no AYUSH licence seen (D-116);
- no front claim matches a claim rule (sugar free, no added sugar, no preservatives, made with
  real X): claim-bearing packs are the D-051 measurement set and go to a person;
- the drafter listed no doubts.

**3. Anything else goes to a person**, with the draft already filled in and the failed checks
listed at the top, so the review is a correction, not a blank form. Reported mistakes, "send it
to us" and front-photo items stay with people for now.

**4. Shadow first, then publish.** The agents start in **shadow**: they draft and check every new
item and publish nothing, and `/review` shows the draft beside the item. Publishing switches on
(`INSIDELABEL_REVIEW_AGENT=publish`) only when, on **at least 30 items Sushil has reviewed**, the
drafts match his decision on category and ingredient lines for at least 95 % of items, and **no
item the checker would have confirmed** needed a material correction from him. The items already
reviewed on 2026-09-27 are the start of that set.

**5. After switching on:** `/review` lists agent-published items; Sushil spot-checks one in ten for
the first month, and "put back in the queue" undoes an agent publish in one click. Users' "Report
a mistake" still goes to people. Every draft, check result and Gemini's raw answer is stored with
the item (D-092).

**6. Cost and running.** One paid Gemini call per new item (about 50 paise, like a scan). A
systemd timer on the server drafts new items every few minutes, one at a time, outside the web
process (D-095 stays one web process). No new processor of personal data: label photos already go
to Google for Gemini and Cloud Vision, as the privacy page says.

**7. Every published version records who drafted it and who published it** (Sushil, 2026-09-27:
"who published ... keep, Claude or Gemini or Sushil"). A new migration adds to `product_versions`:
- `drafted_by`: `sushil`, `claude` or `gemini`: who wrote the category, ingredient lines, claims
  and note. On `/review` it is a required choice next to the category, defaulting to `gemini`
  when the agent's draft is used, else to the reviewer; the reviewer sets `claude` when pasting a
  draft from a Claude session.
- `category_source`: `pack_declared`, `codex_descriptor` or `reviewer`.
- `verified_by` (exists) keeps who published: a reviewer's name, or `agent`.
The items Sushil published on 2026-09-27 from Claude's drafts are marked `drafted_by = claude`
by their review numbers, with a one-off command, so the history is honest from the first day.
The shadow measurement (point 4) is then reported per drafter.

**Not proposed:** a second AI as the checker (same blind spots, or a new processor to name in the
privacy page); letting the agents handle reports or send-to-us; publishing without the shadow
measurement.

### D-118 · A new pack whose ingredient list Cloud Vision can't confirm: ask for a clearer photo before the result `LOCKED` (2026-09-27)
Direction from Sushil after the first shadow run ("14 needs a new photo; should come while photo
taken"); choice of "ask before the result" by Sushil; details by Claude. **Accepted by Sushil
2026-09-27** ("accepted").

**Why.** Review item 14 reached the review agents with an ingredient list only Gemini had read:
Cloud Vision's text of the same photo held no ingredient list, so nothing independent could check
it, and the item needed a person and a new photo. By then the pack was back on the shelf. The
person scanning is the only one holding the pack, so ask them, then.

- **When:** a scan that would add to the catalogue (it creates a new-product or reformulation
  version), where Cloud Vision read the back photo and the review checker's independent-read test
  fails: its text holds no ingredient list, or words of Gemini's list aren't in it (the same logic
  as `ingredients_in_ocr` and `nothing_lost`, shared, not copied). Packs already in the catalogue
  are never asked. When Cloud Vision didn't run (the Tesseract fallback, D-093), nothing is asked:
  there is no independent read to fail.
- **What the person sees, before the result:** "We need one clearer photo of the ingredient list to
  add this pack. Hold it flat and close, without glare." with **Retake the photo** and **Use this
  one anyway**. Nobody is kept from a result: "Use this one anyway" shows it as today, and the review
  item is marked that the independent read failed.
- **Traced like any refusal** (D-092): the first attempt is stored as a scan row with its reason;
  two failed attempts offer "Send it to us" as today (D-070).
- **Cost:** none. Cloud Vision already reads every back photo; no extra Gemini call.
- **Watch it:** how often it fires, and how often people choose "Use this one anyway". If testers
  meet it often, revisit before the beta's W4 measurement (D-055).

### D-119 · A long ingredient list can be photographed in two or three parts, joined on the server `LOCKED` (2026-09-27)
Direction from Sushil in the shop ("BRITANNIA 50 50 Cheeze DIPPED: the ingredients written on the
packet are lengthier as the packet is bigger; taking everything in a single photo is difficult;
any other way, like 2 photos for ingredients?"). Design by Claude. **Accepted by Sushil 2026-09-27**
("will go with A. Join them on the server ... accepted").

**Why.** On a big pack the list either doesn't fit one photo, or fits only from so far away that
the letters are too small for either reader. Today the app takes exactly one back photo.

- **In the app:** after the back photo, "The list continues? Add the next part" offers up to two
  more photos (three parts in all), with the hint "Start where the last photo ended; a little
  overlap is fine." One part stays the normal case and looks exactly as today.
- **On the server:** each part passes the photo checks (D-103) on its own; then the parts are
  joined, one above the other in the order taken, into one tall image. From there nothing changes:
  that image is the back photo for Gemini, for Cloud Vision (one read), for storage, the review
  screen, replay (D-092) and the 30-day cleanup (D-098). The reading prompt stays frozen (D-081),
  and a scan with one part is byte-for-byte the scan of today.
- **Why not send the parts to Gemini separately:** it needs a change to the frozen reading prompt,
  a full gold-set re-run, and a second back photo through storage, replay and retention: more work
  and risk for no gain in what is read.
- **The risk, measured before release:** words photographed twice where the parts overlap. Before
  it ships, a few gold labels are cut into two overlapping halves and rejoined; the reading must
  match the hand transcription as the single photo does (`eval_vision.py`, written to a scratch
  path). That is a paid Gemini call per label, about 50 paise, asked for first. The review checker
  and D-118 compare against Cloud Vision's text of the same joined image, so an overlap that
  confuses the reading is caught there too.
- **Limits:** three parts; each part the size the app already sends; the joined image is shrunk if
  it exceeds what Gemini and Cloud Vision accept. Costs nothing extra beyond a slightly larger image.
- **Amended 2026-09-27 by Sushil** ("not for all. give the option, do u like to part it or single
  image is ok"): the app asks first. After the back photo, "Is the whole ingredient list in this
  photo?" with "Yes, one photo is enough" and "No, add part 2"; the part camera appears only on
  "No". After part 2, "Is that the end of the list?" the same way. Not answering means one photo,
  so the common case costs no extra tap.
- **Measured 2026-09-27:** 3 gold labels cut into two overlapping parts and joined: every reading
  identical to the single photo's, no word read twice, verdict-changing rate 0%, INS F1 1.000.

### D-120 · "Candy sugar syrup" and "sugar syrup" count as added sugar; bare "malt" does not `LOCKED` (2026-09-27)
Found by Sushil in the shop (Lotus Biscoff, 2026-09-27). Recommended by Claude. **Accepted by Sushil
2026-09-27** ("D-120 accepted").

**The basis (primary source, read 2026-09-27).** FSS (Labelling and Display) Regulations 2020,
compendium version I (23.09.2021), page 9: "'sugars' means all monosaccharides (glucose, fructose,
etc.) and disaccharides (maltose, sucrose, lactose, etc.)" and "'added sugars' means
monosaccharides and disaccharides added to foods and beverages".

- **Add "candy sugar syrup" and "sugar syrup"** to `normalization.json` `sugar_aliases.added_sugar`.
  Both are sucrose, or sucrose split into glucose and fructose, in water: added sugars under the
  definition above.
- **Don't add bare "malt".** On the sugar-free masala cracker it is malted grain, used for flavour
  and for the dough: an ingredient of flour, not a mono- or disaccharide added as such. "Malt
  extract" and "barley malt", the syrups, are already on the list. Counting bare "malt" would put
  "Sugar under 2 names" on a pack that says "Sugar Free" with no sugar on its list.

**What it changes, measured (engine and `/scan`, no paid call).** Biscoff today: "No concerns found
in the ingredients.", score 100. With the names: the headline becomes "Sugar appears under 2
names: candy sugar syrup, sugar.", score 92, still grade A. No gold-set or test label contains
either name, so nothing else moves.

**What it doesn't fix, said plainly.** The engine counts sugar *names*, not sugar *amounts*: a pack
with one sugar name and 36 g per 100 g still reads clean. Amounts need the nutrition panel, read
after the beta (D-081). And the band under that headline still says "No concerns found in the
ingredients", which reads as contradicting it; that wording belongs to the result-screen
discussion Sushil asked for, not to this entry.

### D-121 · The tokenizer splits only outside brackets, at any depth, all three kinds `LOCKED` (2026-09-28)
Found on the first supermarket run (Bisk Farm TOP GOLD, Sundrop POPZ, 2026-09-27). Recommended by
Claude. **Accepted by Sushil 2026-09-28** ("accepted"), with the score moves below (Limca 80 to 76,
Ziggy 28 to 4). Merged in PR #37.

**The defect.** `core/tokenize.py` split at every comma whatever the bracket depth, then read one
level of `( )` and `[ ]`; braces not at all. "Spices (Chilli, Turmeric)" gave `spices (chilli` and
`turmeric)`; real packs gave `emulsifier ]`, `antioxidant }`, `ins 472(e`. Since D-115 the result
screen quotes these tokens, so a user could read "such as emulsifier ]".

**The fix.** Separators (comma, semicolon, new line, full stop, spaced "&") split only outside
brackets. Each entry gives its own words, then each bracket group is tokenized the same way, at
any depth. `( )`, `[ ]` and `{ }` count alike, so an OCR "(322]" still closes (`prefix_bare_ins`
follows the same rule). A group left open runs to the end of the entry and a stray closer is
dropped, so a compound the reader split at its bracket still reads cleanly. A sub-form right
after an INS number, "(ii)", stays on it: `ins 500(ii)`, not `ins 500` plus a token `ii`.

**What it changes, measured (engine only, no paid call; 26 labels: gold, predictions, the
laptop's recorded scans and catalogue versions).** INS numbers read: identical on all 26.
`eval_vision.py`: verdict-changing error rate and every F1 identical. Binary and grade: identical
on all 26. **Scores move on two products**, because a class word with brackets after it was glued
to them ("stabilizers (ins 414") and never matched its NOVA row. Now it does, under the scoring
already in force (cosmetic-additive marker = low = 4):

| Label | Score | Grade | Marker(s) now found |
|---|---|---|---|
| Limca (both sizes) | 80 to 76 | B, unchanged | Stabiliser / thickener / humectant |
| Ziggy donut cake | 28 to 4 | E, unchanged | Added colour, Emulsifier, Modified starch, Stabiliser |
| Britannia Treat, Maliban, Patanjali | unchanged | unchanged | none |

Three pinned test scores move with it (Limca 80 to 76 twice; the engine's demo cream biscuit 60
to 56, grade C unchanged). **A pack scoring just above 70 or 50 could cross a grade line**, since
the markers were hidden only when a class word had brackets after it; the server's catalogue was
not checked (not reachable from the laptop).

**The alternative, not recommended:** keep the old scores by leaving class words glued to their
brackets. That keeps the fragments on the result screen, and it keeps two identical ingredients
scoring differently depending on whether the pack prints their numbers.

### D-122 · Rows for INS 319, 472e and 296; "472(e)" reads as 472e; sub-forms keep their parent's row `LOCKED` (2026-09-28)
Found on the first supermarket run (2026-09-27). Recommended by Claude. **Accepted by Sushil
2026-09-28** ("accepted"), as recommended: TBHQ concern **low**. Built on top of D-121; merged in PR #38.

**The basis (primary source, read 2026-09-28).** FSS (Food Products Standards and Food Additives)
Regulations 2011, compendium Version XXVI (20.12.2022), FSSAI's PDF, 883 pages:

| INS | Name and class (compendium INS list) | Appendix A | Row |
|---|---|---|---|
| 296 | Malic acid (DL-): acidity regulator, flavouring agent (p. 828) | **GMP table** (p. 739, "Malic acid, DL-") | `permitted`, concern none |
| 319 | Tertiary butylhydroquinone: antioxidant (p. 829) | **numeric limits only**: e.g. 200 mg/kg fats and oils (p. 568), 100 mg/kg category 1.3 (p. 549); note 195, singly or with BHA and BHT (p. 731). Not in the GMP table | `permitted_with_limits`, concern **low** |
| 472e | Diacetyltartaric and fatty acid esters of glycerol: emulsifier, stabilizer, sequestrant (p. 859) | **numeric limits only**: 49 category-table pages, e.g. 5,000 mg/kg (p. 540), 20,000 mg/kg (p. 642). Not in the GMP table (472a, b, c are) | `permitted_with_limits`, concern low |

Codex CAC/GL 36 itself could not be fetched (FAO's site answers scripts with a Cloudflare
challenge); names match the compendium's INS list, as in D-111. **Sushil: download CXG 36 in a
browser if the Codex text should be read first-hand.**

**TBHQ's concern level is a values choice, not a legal fact.** Recommended: **low**, flag
`antioxidant` only, so it scores 0 like other class-only lows (2026-09-25 rule) and shows its
card, "Permitted with limits". The alternative is **moderate** (12 points), which the concern
scale reserves for evidence such as an ADI or a regulator's published safety opinion; that would
need the opinion read first-hand (D-046) before the row changes.

**Parsing.** `INS_NUMBER` accepts a single letter a to f in brackets as the suffix: "472(e)" and
"472 (e)" read as 472e (Bisk Farm, Anmol). Before, the reading stopped at 472, a number with no
row. Roman sub-forms "(i)", "(ii)" are not letters a to f and are unaffected. Name synonyms in
`normalization.json`: "tbhq", "tertiary butylhydroquinone", "datem" and variants.

**Sub-forms: keep matching the parent row.** Every sub-form seen on a pack so far has the same
Appendix A basis as its parent: 500(i)(ii)(iii), 503(i)(ii), 1101(i)(ii)(iii), 322(i)(ii),
331(i)(iii), 170(i), 1100(i) to (vi), 420(i)(ii) in the GMP table like their parents; 450(i),
341(i), 160a(ii), 481(i) with numeric limits like theirs. **Known gap, not built:** 331(ii) and
170(ii) appear only in the INS reference lists (pp. 826 to 879), never in Appendix A, so under
D-046 they are not permitted, yet they would match their parent's "Permitted" row. Neither has
been seen on a pack; a sub-form-aware row can wait until one is.

**What it changes, measured.** On the 26 local labels: nothing (none contains these three). On
the packs that carry them, a card appears; no score moves (class-only low and none score 0).
5 tests.

### D-123 · Three answers on every result; "Your scans"; the next scan is a comparison `LOCKED` (2026-09-28)
Why: Sushil gave the app to 5 testers (T01 to T05) and "none of them seems to be happy with
output"; he asked for a result that is more useful and makes people want to scan more. Option B of
the result-screen mockups (https://claude.ai/artifact/2Rh7RTBhRz4D5ibsY9hbNF). Recommended by
Claude; built on Sushil's "let's build". **Accepted by Sushil 2026-09-28** ("accepted and merged"). Result-screen work under
Wave 1 (D-084), before invites, so D-083 (no features during the beta) is not crossed.

- **`screen.summary`**, right under the headline: the same three answers on every pack, in the
  same order. *Sugar*: its place in the list ("2nd of 8") and every other name with its place
  (`compare.sugar_positions()`, now the one place that finds it). *How it's made*: the NOVA
  markers in the pack's words (D-115), sugar syrups listed last since the sugar row names them.
  *Additives*: how many, which are worth knowing ("Allura Red AC (colour 129)"), the rest
  "permitted in India". Each row has a chip and a tone (`worth` or `calm`); no score (D-064). A
  partial read says "Not sure", never "None found" (D-062). Wording when nothing matches: "None of
  the 17 industrial ingredients we look for", the accurate form.
- **Headlines say what they mean.** Sugar: "Sugar is the 2nd ingredient, and appears again as
  candy sugar syrup." (was "Sugar appears under 2 names: ..."). A named additive: "Has Sodium
  benzoate, a preservative." The order of findings is unchanged (D-061).
- **"No concerns found" never sits under a finding.** A clean band with anything worth knowing is
  shown as "A few things worth knowing" (Biscoff). The engine's band is unchanged.
- **PWA (web-19):** the answers replace the band box (its "what does industrial mean" note moves
  under them); "N other ingredients look ordinary" and "checked against 69 additives" move to the
  bottom. After a result: "Holding another pack? Scan the one next to it" (D-057 compare), or
  "Compare them" once packs are waiting. Home: **"Your scans"**, the count of this phone's results
  per finding ("Sugar in the first 3 ingredients: 6 of 6" on the six gold packs), worded on the server (`screen.tallies`,
  D-091), counted on the phone, sent nowhere (D-074). No streaks or points (not building).
- Older results kept on phones have no summary and render as before.

Not in this entry: plain-language reasons for the 69 additive rows (Claude drafts, Sushil
reviews); named catalogue alternatives (mockups at https://claude.ai/artifact/HV9MoviE2ipcVyvGwYjwyd,
gated by D-058 and the `compare.py` tie-break question).

### D-124 · A more forgiving barcode scanner; a wait screen that never looks hung `LOCKED` (2026-09-28)
Why: testers, and Sushil, found the live barcode scanner slow, and some scans took about 30 s.
Recommended by Claude. **Accepted by Sushil 2026-09-28** ("accepted and merged"). App only (web-20); no server or cost change.

- **Scanner (`web/camera.js`):** a code is accepted once it is read twice within 1.5 s, not twice
  in a row (one blurred frame used to start over); frames every 150 ms (was 200); the camera is
  asked for continuous focus and up to 2x zoom where it offers them, so the phone can sit a hand's
  width back, where it focuses; a light button where the phone has a torch; a short vibration on
  a read. After 8 s with no read, a hint on distance and light, pointing at the barcode photo.
  Still no third-party scanner; the server still checks every code (D-103, D-104).
- **Wait screen:** after 20 s, "Taking longer than usual: the reader is busy right now. It is
  still working." It also says a catalogued pack's barcode gives the result at once.
- **Where the time goes, known so far:** Gemini takes 5 to 18 s for a new pack (laptop records);
  the 30 s seen on the laptop was the Tesseract fallback, which runs only without Cloud Vision.
  The server's own timings decide the next step (OPERATIONS.md query in STATE.md).

### D-125 · "Worth a look" rows for additives worth knowing; research lines only from sources read first-hand `LOCKED` (2026-09-28)
Why: testers said the result didn't show what to look at first, and asked for "this is here and a
study says ... here is the research paper". Mockup: https://claude.ai/artifact/K7R9s8EFw35MZCA8vfpiEg.
**Accepted by Sushil 2026-09-28** ("yes, pls proceed. looks good"), including the tapped-open row
with an arrow that keeps nudging until tapped.

- **`screen.alerts`:** one row per additive whose badge is "Worth knowing" (moderate or high concern
  and permitted; "Not permitted" keeps its own alert, D-111). Title "Worth a look: Allura Red AC
  (colour 129)". Closed until tapped; the arrow nudges; phones set to reduce motion get a still
  arrow. Opened: what research found, the pack's line as printed, the sources as links.
- **Research lines** live in `data/additive_research.json`, keyed by INS: one to three plain
  sentences, each source with title, link and the date it was read, and who reviewed it.
  `tests/test_additive_research.py` refuses a row without them, and the wording lint runs on
  every sentence. Until a row is researched and reviewed, the body is the row's own reason and the
  prompt says "Tap to see why", never "research".
- **What research lines may say:** what the source found, in its own terms, with its limits when it
  states them. Never "wrong", "harmful", "dangerous" (D-042, D-071). EU and US rules are information
  only (D-086). Sources: the study, or the regulator's own opinion (EFSA, JECFA, IARC, FSSAI).
- **App (web-21):** the rows sit right under the headline, before the three answers (D-123), so
  the household's allergen line stays first (D-060).

### D-126 · The all-clear allergen line names what was checked `LOCKED` (2026-09-28)
Sushil asked why "Nothing on your avoid list is listed in the ingredients" was shown: it didn't say
what the avoid list was. **Accepted by Sushil 2026-09-28** ("yes").

- Now: "Peanut, sesame: not listed in the ingredients or the allergen line." When the photo showed
  no allergen line: "Peanut, sesame: not in the ingredients. We didn't see a "may contain" line in
  the photo, so check the pack." Names are allergens.json `short`, in the profile's order.
- Unchanged: the line appears only for a profile with an avoid list, first on the screen (D-060);
  it reports what is printed, never "free from" or "safe" (D-042); below 0.95 confidence or on a
  partial read it says we can't confirm.

### D-127 · Ask the allergy question plainly; "At a glance"; what the words mean, linked to "How we check" `LOCKED` (2026-09-28)
Sushil: "are we asking the right question to user to add the allergic part", and the words
(Industrial, Additive, Other) should be explained at the end with a link. Recommended by Claude.
**Accepted by Sushil 2026-09-28** ("accepted and merged"). App web-22.

- **Setup asks what people can answer.** Welcome: "Does anyone you shop for avoid a food, like
  peanut, milk or gluten?" [Yes] [No]. Yes: "Who avoids it?" Me / A child I shop for (D-074 keeps
  other adults out). The list screen: "What do you avoid?" / "Foods this child avoids", with what we
  do with it and that we only report what the label prints, linked to "How we check". Before, the
  question was never asked: "Set up your household" led to "Add a child", and your own list sat
  behind a row called "Your avoid list".
- **"At a glance"** (the mockup Sushil approved, D-125): `screen.glance` gives each list entry one
  type, the most telling first: worth knowing, sugar, industrial, additive, other; a ring of the
  counts and a strip of the list in printed order. The caption says counts, not weight. Colours
  from the validated categorical slots and the status red, in both themes.
- **"What these words mean"** at the end of every result: only the terms that result used, each
  with a plain definition (`screen.GLOSSARY`, under the wording lint) and a "More" link to its
  section of the new public page `/how` ("How we check a label", `web/site/how.html`). A test
  checks every term has its section.
- "By law, ingredients are listed from most to least" was left out of `/how` until the FSSAI
  labelling regulation is read first-hand (D-046).

### D-128 · Keep what the label said; unlink who scanned it after 30 days `LOCKED` (2026-09-28)
Sushil: "data is gold we will keep may be in cheaper storage format". Claude recommended keeping
the label data for good but not the link to the person: the DPDP Act s.8(7) requires erasing
personal data "as soon as it is reasonable to assume that the specified purpose is no longer being
served", and applies only to data about an identifiable individual (s.2(t)). **Accepted by Sushil
2026-09-28** ("agree with you"). Data map: `docs/DPDP_DATA_MAP.md`.

- **Built (migration 016, `retention.unlink`, run daily by `tools/retention.py --apply`):**
  - After 30 days a scan loses `user_id` and the `profiles` and `avoid` in its request; the
    reading, barcode, timings and result stay. `unlinked_at` records when.
  - A held scan (problem report, "send it to us") keeps its link, so a replay has the profiles
    it ran with (D-092), until no report names it, and never past 12 months. A review item
    doesn't hold the link: the review needs the photo, which D-098's rules keep.
  - `device_days` keeps each install's scans per day, so D-055's W4 retention survives
    (`beta_testers()` reads it).
  - Feedback and problem reports are deleted after 12 months. An install id, its invite link,
    agreement and day counts are deleted 12 months after the device was last seen.
  - Resolved review items drop `notify_user_id` after 30 days.
  - Invite labels are codes (T01), no names (`tools/beta.py` help changed).
  - Privacy page "How long we keep it" updated to match.
- **Not built yet:** keeping scan photos in cheaper archive storage instead of deleting them at
  30 days. Photos are still deleted at 30 days (D-080, D-098), the promise on the live privacy
  page, and photos taken under that notice keep it. Before changing it: the DPDP reviewer says
  whether an unlinked pack photo that shows a hand or a face is still personal data (crop to
  the label if so); the storage class and its price are read from Google's pricing page; the
  privacy page changes first. That change will supersede the photo part of D-080 and D-098.

### D-129 · "Delete my data" in the app; Gemini on paid quota `LOCKED` (2026-09-28)
The DPDP Act gives a right to erasure (s.12(3)) and to a readily available grievance route (s.13);
the app had no way to do either. Recommended by Claude in the data map (`docs/DPDP_DATA_MAP.md`
section 4, point 6). **Accepted by Sushil 2026-09-28** ("Delete my data" option in the app. yes).
Sushil also confirmed the Gemini project is on **paid quota** (under the Gemini terms, Google doesn't
use paid-tier prompts or responses to improve its products). App web-23.

- **App:** "Your data" in the footer of every screen (`#/data`), open before joining or agreeing
  so a revoked tester can still erase. It says what the server keeps and for how long, shows the
  install id to quote in an email to `connect@insidelabel.ai`, and has "Delete my data" behind a
  confirm step. On success it clears everything the app keeps on the phone (`store.clear()`).
- **Server:** `POST /forget {device_id}`, rate limited (5 an hour per install). No invite needed.
  Deletes feedback, problem reports, invite link, agreement, day counts and the install id;
  unlinks every scan and strips its household profiles; ends holds; closes open "send it to us"
  requests as rejected; deletes the install's photos except a photo that is a non-rejected
  catalogue version's evidence or that another install's scan also sent. The database goes
  first; a photo file that can't be deleted then is picked up by the 30-day job. Logs counts only.
- **Privacy page:** "Who reads your photos" says paid Gemini and asks for pack-only photos; "Your
  choices" describes the button, the email address, the 90-day answer and the Data Protection Board.

### D-130 · A photo of a screen is read, marked "from a screen"; a shop list closes the gap in the shop `LOCKED` (2026-09-29)
Amends D-103 (only its refusal of a screen; "not a food pack" is still refused). Problem report #1
on the live server ("Why photo not allowed?"): a tester photographed a listing on a screen and was
refused twice. Sushil: "if a user want to compare on his laptop or with other screen, which product
will good before going next time to any supermarket, we should allow to check with upload option,
don't stop user". On the allergen line Sushil asked to give the result as read, with the caution in
it, rather than always "can't confirm". **Accepted by Sushil 2026-09-29** ("understood and accepted,
please proceed"), after the three cases below were set out.

The risk, on record: a listing can be older than the pack in the shop. If a recipe adds milk and the
listing photo isn't updated, a correct read of the screen says "not listed", and a parent could buy a
pack their child reacts to. Nothing in the photo shows its age, so the design answers it three ways:
the caution is inside the allergen line, our own catalogue is checked, and the shop list sends the
person back to the pack.

- **Read, marked.** `image_content.back == "screen"` no longer refuses (`gates.assess` marks
  `from_screen` and adds the `read_from_screen` caveat; every other check still runs). The result
  opens with "Read from a screen, not the pack." and "Listings can be out of date or show another
  size or flavour. Check the pack in the shop before you buy." An unreadable screen gets its own
  retake text and can't go to "Send it to us".
- **Allergen lines say "on this screen" (D-060, D-071).** Found: "Contains milk, as listed on this
  screen." Not found: "Milk, soy: not listed in the ingredients on this screen. Listings can differ
  from the pack in the shop. Check the pack before buying for {name}." (your own list: "before you
  buy"). Below 0.95 confidence or on a partial read: can't confirm, as for any scan.
- **Our catalogue beside the screen.** When the barcode has a published version (read from a real
  pack, D-089): case A, the pack lists what the screen doesn't: "Milk: listed on the pack we checked
  on 12 Aug 2026. This screen doesn't show it, so the listing may be old." (the pack's state wins);
  case B, both not listed: "...not listed, on this screen and on the pack we checked on ... Check the
  pack when you buy."; case C, no pack: the screen line above.
- **Never the record (D-088, D-089).** A screen scan creates no product, version or review item,
  whatever barcode came with it: only a scan row, outcome `screen_read` (migration 017), kept for
  replay (D-092); its photos go at 30 days (D-098). No D-118 clearer-photo request.
- **Shop list (app, web-24).** "Add to my shop list" under a screen result; the list is kept on the
  phone only (cleared by "Delete my data"). "Scan it now" sends the screenshot's ingredient list and
  allergen line (`screen_pack`, no names, D-074) with the pack's scan or barcode lookup; the server
  words what differs ("Milk is listed on this pack. The screenshot didn't list it.", D-091), and the
  item leaves the list.
- **Later:** matching a screen to the catalogue by brand and name when no barcode is shown (risk of
  the wrong variant); to be proposed separately.

### D-131 · Concern levels for three sweeteners and carrageenan after reading the sources `LOCKED` (2026-09-29)
Sushil approved the 15 research rows (2026-09-29, "approved"; now in `data/additive_research.json`)
and asked for a call on whether saccharin (954), acesulfame K (950), sucralose (955) and carrageenan
(407) stay `moderate`. EFSA's latest opinions on all four found no concern at current intakes
(saccharin 2024, acesulfame K 2025, sucralose 2026: intakes below the limit; carrageenan 2018: no
concern on cancer or DNA, no adverse effects in long-term rat studies). Recommended by Claude.

- **954, 950, 955 stay `moderate`.** EFSA answers "is intake within the limit"; the WHO guideline of
  15 May 2023 (read first-hand) answers a different question and names all three (with aspartame
  and stevia): it advises against non-sugar sweeteners to control weight, citing no long-term benefit
  for body fat and possible links in adults to type 2 diabetes, cardiovascular disease and death,
  rated conditional because the studies may be confounded. That is a published opinion of a health
  body, the `moderate` definition in `additives.json`. Sucralose also has EFSA's 2026 uncertainty on
  heating. Drafts in `docs/research_drafts.json` add the WHO sentence to each row, for Sushil's
  "approved". **Approved by Sushil 2026-09-29** ("approved"): the three rows stay `moderate` and
  their research rows carry the WHO sentence and source. The rest of D-131 (407, stevia) still waits.
- **407 carrageenan to `low`, its "why" rewritten.** EFSA's temporary limit is about gaps in the data,
  not an effect it found; the row's "why" ("Some studies suggest gut inflammation (contested)") has no
  source read first-hand (D-046). Proposed "why": "Seaweed thickener. EFSA (2018) found no adverse
  effects in long-term studies and set a temporary daily limit until better data came in." Effect: 407
  leaves "Worth a look" (its research row goes back to the drafts file), its penalty goes from 12 to 0
  (its flag isn't a low-penalty flag), and it still counts as an industrial ingredient (NOVA marker,
  scored separately). None of the 6 gold labels contain 407. **Not applied until Sushil says
  "accepted".**
- **Open, not proposed:** stevia (960) is `low` though the WHO guideline names it too. Consistency
  with the reason above would make it `moderate`; that moves scores on stevia packs and is Sushil's
  call.
- **Accepted by Sushil 2026-09-29** ("accepted, Stevia go with WHO"). Applied:
  - 407 carrageenan `low`, "why" as proposed, flag `efsa_temporary_adi` (was
    `gut_inflammation_contested`), sources EFSA. Its research row moved back to
    `docs/research_drafts.json`, kept in case it returns to `moderate`.
  - 960 stevia `moderate`: "Plant-derived sweetener. WHO 2023 advises against non-sugar sweeteners,
    stevia among them, for weight control. NOVA cosmetic marker." Flags `sweetener_natural`,
    `who_nss_advisory`. A research row (the WHO sentence) waits in the drafts for "approved"; until
    then its "Worth a look" row shows the "why". Approved by Sushil 2026-09-29 ("approved").
  - Scores: the 6 gold labels are unchanged (none has 407 or 960). Invented examples: a cocoa drink
    with carrageenan 84 to 96; a drink sweetened with stevia 88 to 80; both together 76 to 80.

### D-132 · "Ingredients worth knowing": notes on maida, fats, oils, salt, caffeine, from sources read first-hand `LOCKED` (2026-09-29)
The ingredient-notes review in chat (15 rows, from ICMR-NIN 2024 and WHO). **Accepted by Sushil
2026-09-29** ("keep all 15 rows now ... implement all"). Built in phase 1 (branch `ingredient-notes`).

- **`data/ingredient_notes.json`**, one row per group: names (whole words in a list entry), a
  1 to 3 sentence summary, sources with title, url, page and `read_on`, a position rule, and
  `reviewed_by`. **A row shows only once Sushil has reviewed it** (as D-125's research rows); every
  row ships `reviewed_by: null`. Matching is `engine.ingredient_notes()` on the list as printed,
  INS numbers by `tokenize.ins_numbers` (D-099). `tests/test_ingredient_notes.py`.
- **Tiles** ("Worth a look", closed): hydrogenated fat, vanaspati, shortening (first: the strongest);
  palm oil and palmolein; coconut oil; maida and other refined flours or starch **when in the first 3**.
  **Lines** under one closed "More about the ingredients": the same flours further down, sooji,
  ghee or butter, margarine, an oil or a fat whose type the pack doesn't name, salt, caffeine, and
  for a phone with a child's profile only, sweeteners (sugar alcohols only when printed as a
  sweetener, so "Humectant (420)" doesn't count). The sugar answer gets ICMR-NIN's and WHO's lines
  one tap away; no new flag.
- **Information only.** Score, grade, band, NOVA and allergen lines are unchanged; the one wording
  change: a pack that reads clean but has a tile says "A few things worth knowing." instead of
  "No concerns found" (D-123's rule). Tested before and after on the 6 gold labels.
- **Sugar names (row 11):** khandsari, bura and misri added to `sugar_aliases`: FSSAI FPS&FA 2011
  2.8.1(3), 2.8.1(4), 2.8.2 define them as sugar of at least 93%, 90% and 98% sucrose, so added
  sugar under L&D 2020 5(3)(a)(ii). Gold set unchanged; an invented "Bura sugar, Misri" pack goes
  100 to 92 (two names, as D-120). **Coconut sugar not added:** no FSSAI standard defines it.
- **Sources read first-hand 2026-09-29:** ICMR-NIN Dietary Guidelines for Indians 2024 pp. 17 to 18,
  51 to 56, 66, 91, 93 to 98, 107 to 109; WHO fats and carbohydrates (2023), sugars (2015), salt
  fact sheet; FSS (Labelling and Display) Regulations 2020, compendium I, pp. 5 to 13; FSS (Food
  Products Standards and Food Additives) Regulations 2011, compendium XXVI, pp. 104, 119 to 124,
  204 to 206, 226, 341 to 342, 439, 625.
- **What no source said, so the app doesn't:** no source calls sooji refined (it gets FSSAI's
  definition only, no tile); no children's caffeine figure (ICMR-NIN speaks only of pregnancy);
  "bakery fat" has no FSSAI definition (it is treated as a fat whose type isn't named).
- **Rows approved by Sushil 2026-09-29** ("approved, keep the oil line"): all 14 rows now carry
  `reviewed_by: "sushil"` and show. The unnamed-oil row keeps its second sentence ("FSSAI's
  labelling rules ask for the name of the specific edible oil...").

### D-133 · Read the nutrition table and judge it against ICMR-NIN's own thresholds `LOCKED` (2026-09-29)
**Accepted by Sushil 2026-09-29** ("keep all 15 rows now ... implement all", row 15 of the review).
Gemini transcribes the table; rules in Python check it (numbers must appear in Cloud Vision's text,
per serving x servings, sugars within carbohydrates, saturated within total fat, salt = sodium x 2.5)
and compare it with ICMR-NIN Table 15.1 (p. 96: per 100 g 250 kcal, 625 mg salt, 3 g added sugar;
per 100 ml 70 kcal, 175 mg, 2.0 g) and the daily 25 g sugar and 5 g salt. Information only. To be
built in phase 2 (branch `nutrition-panel`).

**Built (2026-09-29, branch `nutrition-panel`, web-26).** Full account: `docs/NUTRITION_PANEL.md`.
- **Sources read first-hand:** FSS (Labelling and Display) Regulations 2020, 5(3) and 8(1)
  (mandatory values, exemptions, % RDA bases, energy factors); ICMR-NIN 2024 pp. 93, 94, 96, 108;
  WHO fats (2023) and salt fact sheet.
- **Reading:** prompt rule 10 and a `nutrition` object: the model copies status, headings, serving
  size, servings and each row's cells as printed (paragraph tables too). New PROMPT_VERSION (a hash of
  the prompt). Answers from before D-133 have no table, parse and replay unchanged.
- **Judging (`lenses/nutrition.py`, `data/nutrition_panel.json`):** every number must be in the second
  reading of the same photo; then the table's own arithmetic. **Added beyond the build prompt:** the
  printed % RDA per serve is checked against FSSAI's bases (2000 kcal, 67 g fat, 22 g saturated, 2 g
  trans, 50 g added sugar, 2000 mg sodium, 5(3)(b)): it catches a number read into the wrong row,
  which "is it in the text" can't. When most rows disagree the serving size is dropped instead. The
  build prompt's "per serving x servings ~ per 100" is done as: a printed per serving amount fits
  per 100 x serving size, and servings x serving size fits the net quantity. All four readable gold
  tables pass every check with nothing dropped.
- **Screen (`data/nutrition_thresholds.json`, `screen.nutrition`):** energy, added sugar (total sugars
  when added isn't printed alone), salt from sodium x 2.5, saturated fat with its share of the food's
  energy against WHO's 10%, trans fat against WHO's 1%; per serving, added sugar and salt against the
  25 g and 5 g a day, "for adults"; the rest in one line. Added fat not applied (packs print total
  fat). Trans fat above zero (including "not more than 0.09 g") is a "Worth a look" tile; with it,
  "No concerns found" becomes "A few things worth knowing." (D-123's rule). No score change.
- **No table in the photo:** "If the pack has one, add a photo of it": the photo joins the back photos
  as the next D-119 part and the pack is read again, **one more paid read (about 50 paise, plus a
  Cloud Vision read)**. Not offered after three parts or for a catalogue pack. FSSAI exempts many
  packs (single ingredient, spices, tea, water, packs up to 100 cm2), so it is an offer, never a refusal.
- **Catalogue (migration 018):** `product_versions.nutrition`; `/review` shows the rows beside the
  photo with "Every number shown to users matches the photo"; unticked, published without the table;
  publishing records `confirmed_by`. A pack published before D-133 gets its table through a new
  version queued as kind `nutrition` (can't be published unticked). Review checker: `nutrition_in_ocr`.
- **Measuring:** gold tables added (transcribed by Claude from Sushil's photos: Maliban, Patanjali,
  Ziggy, Limca 2.25 L read; Britannia cut off, "unreadable"; Limca 1 L a render, "not_found").
  `eval_vision.py` reports numbers read right; `release_check.py` gate "Nutrition numbers read
  correctly >= 98%", TODO until the gold set is read with the new prompt (6 paid reads, about Rs 3).
- **Not done:** a published table that changes while the ingredients don't isn't noticed; tables not
  per 100 g or 100 ml aren't used.

### D-136 · Should the nutrition table change the score? `RECOMMENDED` (2026-09-29)
The D-133 build prompt: "Information only; propose any score rule separately as RECOMMENDED." The
score today counts ingredients, not amounts (D-120 said so plainly). Measured on the gold set, with
one penalty per ICMR-NIN per 100 threshold exceeded (added sugar, energy, salt; Table 15.1):

| Label | Over | Now | -4 each | -12 each |
|---|---|---|---|---|
| Limca 2.25 L | added sugar | 76 B | 72 B | 64 C |
| Maliban wafer | added sugar, energy, salt | 56 C | 44 D | 20 E |
| Patanjali Doodh | added sugar, energy, salt | 48 D | 36 D | 12 E |
| Ziggy donut cake | added sugar, energy, salt | 4 E | 0 E | 0 E |

**Recommended by Claude: no score rule yet.** A misread number would then move a grade, and the
reader's accuracy on tables is unmeasured (the D-133 gate is TODO). Revisit when that gate passes on
at least 20 gold tables; the -4 column (the `low` weight) is the gentler starting point. Not applied
until Sushil decides.

### D-134 · One-screen result: warning tiles, each opening its own page `LOCKED` (2026-09-29)
**Accepted by Sushil 2026-09-29** ("keep all 15 rows now ... implement all"). Compact tiles under the
allergen line and headline, each opening a detail page; nothing else open by default; the first
screen fits a 390 x 844 phone for a pack with 2 warnings. To be built in phase 3 (branch
`result-tiles`).

**Built (2026-09-30, branch `result-tiles`, web-27).** Started after Sushil confirmed the phase 2 phone
check ("Checked, start phase 3").
- **Server (`lenses/screen.py`):** `screen.tiles`, each `{id, kind, title, chip, tone, source}`, kind
  `not_permitted | additive | ingredient | nutrition`, in that order (hydrogenated fat first among the
  notes, D-132), and `screen.details[tile id]`: `what_it_is`, `what_research_found[]`,
  `who_it_concerns`, `on_the_label`, `where`, `note`, `sources[]`. **The tiles regroup what the
  result already said; no new judgement and no new sentence about a pack.** Tiles are exactly the
  D-111 additives badged "Not permitted in India" or "Worth knowing" (an unsure "not permitted" read
  is `additive` with the chip "Check the number" and D-111's note), the D-132 ingredient tiles and
  the D-133 trans fat row. Pages use the reviewed words: the D-125 research row (or the additive's
  `why`), the ingredient note's sentences, the trans fat summary. `what_it_is` is the additive's
  class from its row ("Potassium bromate is a flour treatment, INS 924a."), or for a note the sentence
  that data/ingredient_notes.json marks with the new optional `what_it_is` index (maida only: palm
  oil's FSSAI sentence defines palmolein, so it stays with the rest). `who_it_concerns` is always
  null: no reviewed row says it apart from its research. `more_title` "More about this pack";
  `glance.caption_short` (the caption's first sentence; the strip's ends say the second). Every older
  field stays for app versions before web-27. `tests/test_result_tiles.py` (17 tests).
- **App (`web/app.js`, web-27):** first screen = allergen lines, headline, tiles, the three answers as
  chips (a tap opens one sentence under them; the sugar sources one tap further), then only what asks
  for something now (a partial read's retake, "Add a photo of the nutrition table", the D-073
  re-check), At a glance (smaller ring, one-sentence caption), Compare and Scan another (and "Add to
  my shop list" on a screen result), Report a mistake; everything else in one closed "More about
  this pack", in the old order. A tile opens `#/result/<id>/look/<tile id>` with a back link; the
  trail records it as `sub`. "Compare" adds this pack and opens Compare (the D-123 "Holding another
  pack?" card is gone; Compare's page offers the scan). Results kept on the phone from before web-27
  show their old "Worth a look" rows in place of tiles.
- **Measured** in headless Chromium at 390 x 844 from real `/scan` answers (replay), light and dark:
  Britannia (2 tiles, one profile) ends at 787 px including Report a mistake; Maliban (3 tiles, two
  profiles) at 984. No console errors. Found on the way: every `row wrap` also took the page's `.wrap`
  padding (16px sides, 48px below), the "empty space under Remove" on the shop-list card seen in the
  D-130 walk; fixed in app.css for all four rows.
- **Choices for Sushil to confirm:** the front-photo ask (D-100) now sits inside "More"; over-threshold
  nutrition rows (sugar, salt, energy) are not tiles (D-133 made only trans fat a tile); the shop list
  stays for screen results only (its comparison says "your screenshot").

### D-135 · Hydrogenated and interesterified fats under the names Indian packs print them count as NOVA markers `LOCKED` (2026-09-29)
Found while building D-132: the NOVA row "Hydrogenated / interesterified oil" misses the words Indian
packs use. A rusk listing "Hydrogenated vegetable fat" scores 100, grade A, clean; Britannia's gold
label lists "INTERESTERIFIED VEGETABLE FAT" and the marker doesn't see it. Sushil asked for the
write-up ("write up the NOVA proposal", 2026-09-29). Recommended by Claude. **Accepted by Sushil
2026-09-29** ("D-135 accepted"); built on branch `ingredient-notes` (see "Built" below).

**The basis (primary sources, read 2026-09-29).**
- Monteiro et al., "Ultra-processed foods: what they are and how to identify them", Public Health
  Nutrition 22(5), 2019, pp. 937 to 938 (https://doi.org/10.1017/S1368980018003762, the paper
  `nova_markers.json` cites): food substances used only in ultra-processed foods include "modified
  oils (hydrogenated or interesterified oils)", and "The presence in the list of ingredients of one
  or more of these food substances identifies a product as ultra-processed."
- ICMR-NIN Dietary Guidelines for Indians 2024, p. 55: hydrogenated fat is "often referred to as
  'vegetable shortening'".
- FSS (FPS&FA) Regulations 2011, 2.2.6 (compendium XXVI, PDF pp. 122 to 123): vanaspati is refined
  vegetable oil "subjected to a process of hydrogenation in any form or chemical or enzymatic
  interesterification"; "Bakery shortening means vanaspati meant for use as a shortening".
- FSS (Labelling and Display) Regulations 2020, 5(2)(d) (compendium I, PDF p. 6): the class title
  for edible vegetable fat names "interesterified vegetable fat" and "hydrogenated oils", so these
  are the words a pack is told to print.

**The change (data only).** Add to `nova_markers.json` `nova_hydrogenated_oil` aliases:
"hydrogenated vegetable fat", "partially hydrogenated fat", "interesterified vegetable fat",
"interesterified vegetable oil", "shortening". Aliases match inside a longer entry, so "vegetable
shortening" and "bakery shortening" are covered by "shortening". Not bare "hydrogenated": it would
also match "non-hydrogenated". Not margarine: the paper lists margarines among ultra-processed
*products*, not among the marker substances.

**What it changes, measured** (engine and `/scan` with replay, no paid call; the NOVA marker costs
12 points, the `moderate` penalty):

| Label | Now | With D-135 |
|---|---|---|
| Britannia Treat Croissant (gold) | 48 D, ultra-processed | 36 D, ultra-processed; "How it's made" leads with "Interesterified vegetable fat"; headline unchanged (sugar) |
| Limca x2, Maliban, Patanjali, Ziggy (gold) | unchanged | unchanged |
| Invented: maida, sugar, hydrogenated vegetable fat, salt, yeast | 100 A, clean, "A few things worth knowing." | 88 A, ultra-processed, "Made with industrial ingredients, such as hydrogenated vegetable fat." |
| Invented: with "Bakery shortening" / "Vegetable shortening" | 100 A, clean | 88 A, ultra-processed |
| Invented: with "Interesterified vegetable fat" | 100 A, clean | 88 A, ultra-processed |

The laptop database (18 scans) has only the Britannia wording. The server has more; Sushil can count
them read-only: `sudo -u insidelabel psql -d insidelabel -c "SELECT count(*) FROM scans WHERE
model_raw::text ~* 'hydrogenated vegetable fat|partially hydrogenated fat|interesterified vegetable|shortening'"`.

**If accepted:** the five aliases, a test per wording (and one that "non-hydrogenated" stays out),
and the gold label's expected score updated. `compare.py`'s NOVA count reads the same file, so it
follows without a code change.

**Built (2026-09-29).** The five aliases in `nova_markers.json`; `tests/test_nova_label_terms.py`
checks each printed form (7 wordings), that "Non-hydrogenated vegetable fat/oil" and "Non
hydrogenated fat" are not the marker, and pins the six gold scores (Britannia 36 D, the rest as
before). **Found while building, fixed with it:** aliases match inside a longer entry, so the
existing "hydrogenated fat" already matched "non-hydrogenated fat", and so would the new names. A
match directly after "non-" or "non " no longer counts (`classify._inside`; the kids lens's NOVA
count, `compare._marker_in`, the same), and D-132's hydrogenated-fat tile excludes
"non-hydrogenated" (its approved wording is unchanged). An alias that itself starts with "non-"
("non-nutritive sweetener") still matches. No gold label contains "non-".

### D-137 · Gold ingredient arrays split where the prompt says to split `LOCKED` (2026-09-30)
The ingredient match gate reads 94.5% (needs 95%). Diagnosed on the 6 gold labels against the saved
predictions (read 2026-09-25) and the photos: **no ingredient word is misread.** Four labels match
exactly; every difference on the other two is where the list was cut into entries:

| Label | Gold | Model | Pack (photo) | Prompt rule 4 ("split on top-level commas only") |
|---|---|---|---|---|
| Britannia | bakery improver mix as one entry | split into 3 inside its `{ }` | one bracketed group | model is wrong |
| Britannia | "... FLAVOURING SUBSTANCES" and "RAISING AGENTS [...]" as two | one entry | "SUBSTANCES AND RAISING AGENTS": no comma | gold departs from the rule |
| Patanjali | "Natural, Nature identical & Artificial Flavours (...)" as one | "Natural" + the rest | a top-level comma after "Natural" | gold departs from the rule |
| Patanjali | "Emulsifier INS 322(i)" | "Emulsifier [INS 322(i)]" | no brackets | model added brackets (the gate cannot see it: `norm()` drops brackets) |

The gold was split by meaning; the model is told to split by commas. The gate then counts obeying the
prompt as a miss. **Recommended by Claude:**
1. The gold follows prompt rule 4, the one written convention: Britannia's last two gold entries
   become one ("... FLAVOURING SUBSTANCES AND RAISING AGENTS [450(i) & 338]"), Patanjali's flavours
   entry becomes two ("Natural", "Nature identical & Artificial Flavours (Milk & Vanilla)"). Nothing
   else changes; the gate stays whole-entry F1 at 95%. Measured on the saved predictions: **98.0%**
   (Britannia 0.882, the other five 1.0). The bakery-mix split stays counted, as it should.
   For comparison, F1 over the tokens the engine actually scores (`engine.tokenize`, D-121) is 98.3%.
2. With the paid gold run (only when Sushil says "run the gold set"), not before: add a `{ }` and
   `[ ]` example to rule 4 and a line "do not add brackets that are not printed". A prompt change
   moves PROMPT_VERSION and invalidates every saved prediction, so it goes in with that run.

Why this isn't fitting gold to output (RUNBOOK: "don't fix gold after seeing a mismatch"): no word
changes, and both gold splits were the error `tools/new_gold.py` names, writing what the pack means
rather than what it prints (it prints "SUBSTANCES AND RAISING", and a comma after "Natural"). The
model's two real mistakes stay counted or noted. Why not change the measure instead: the gate is a
blueprint number, and passing it by redefining it is the wrong habit. Why it matters little either way: 6 labels is far too few for 94.5 against 95 to
mean anything; the gold set size gate (20) is the real work. Nothing applied until Sushil decides; the
gold files are not edited.
- **Accepted by Sushil 2026-10-01:** "D-137 accepted now with above suggestions". **Point 1 applied** (branch
  `beta-limit`): Britannia's last two gold entries are one, "NATURE IDENTICAL & ARTIFICIAL (CHOCOLATE & VANILLA)
  FLAVOURING SUBSTANCES AND RAISING AGENTS [450(i) & 338]", as printed; Patanjali's flavours entry is two,
  "Natural" and "Nature identical & Artificial Flavours (Milk & Vanilla)". No word changed. Each file's
  `ingredient_count` follows its list (Britannia 17 to 16, Patanjali 11 to 12), since prompt rule 4 defines it as
  the number of entries. The gate is unchanged: whole-entry F1 at 95%. The re-score (expected 98.0%: Britannia
  0.882, the other five 1.0) runs on Sushil's laptop, where `predictions/` is, before the merge. **Point 2** (a
  `{ }` and `[ ]` example in rule 4, "do not add brackets that are not printed") waits for the one gold run
  Sushil approved (D-147), since it moves PROMPT_VERSION.
  On the gold input, Britannia now reads as 18 entries, not 19, as a scan already does when the model follows rule 4:
  score 36 D, band, headline and allergen lines unchanged; the strip, the "of 19" chips and the NOVA flavour
  marker's label ("artificial flavouring substances and raising agents") follow the joined entry. Its capture in
  `tests/fixtures/pack_kind_gold_before.json` is refreshed to match; the other five labels are untouched.

### D-138 · The conflict-of-interest policy, in the words already decided `LOCKED` (2026-09-30)
**Approved by Sushil 2026-10-02 ("D-138 approved", with the photo and the contact address connect@insidelabel.ai).**
D-076 asks for the policy at beta launch; `web/site/about.html` still has a bracket where it goes.
Draft in `docs/COI_POLICY_DRAFT.md`: page-ready text, and for every line the decision it comes from
(D-002; blueprint §2.5 and §10; "Explicitly not building"; D-053's "scans free forever" and nothing
on price, which is still open). One new line, recommended so the promise can be checked: a change is
dated on the page before it takes effect. **Only Sushil can fill:** who pays today, ties to the food
industry ("none" is an answer), and "who is behind it" (name, photo, a few sentences). Not on the
site until Sushil says "approved".

Built with it (no decision needed, the pages only describe what is already built): `/how` explains
"Not permitted in India" (D-111), ingredients worth knowing (D-132), the nutrition table (D-133) and
tiles (D-134); `/about` lists where the facts come from. `tests/test_wording.py` now lints the site
pages and the app shell too (all were already clean).
- **Sushil's answers, 2026-10-01** (in `docs/COI_POLICY_DRAFT.md`): who pays, "my own money"; ties to the food
  industry, "none"; who is behind it, "Sushil Behera, a photo and a few sentences" (the sentences are Claude's draft
  for him to edit). The page follows D-148: "Looking up a pack stays free. Photo scans have a daily limit." and "No
  ads." Still RECOMMENDED: nothing goes on `web/site/about.html` until Sushil says "D-138 approved" and sends the
  photo and the contact address to show.
- **Approved 2026-10-02.** On `web/site/about.html`: "Money and brands" is the draft's page text unchanged; "Who is
  behind it" is Sushil's own note (D-153) in place of Claude's draft sentences, his photo and connect@insidelabel.ai.
  The page's "DRAFT" banner goes, since no bracket is left. The photo, at Sushil's request ("do some edit for clarity"),
  only had its warm cast halved, light and contrast raised a little and a mild sharpen, then a 4:5 crop: nothing about
  the face changed. `web/people/sushil-behera-240.webp` and `-480.webp`.

### D-139 · Health supplements and nutraceuticals: a kind of pack with its own checks `LOCKED` (2026-09-30)
Sushil: "implement supplements and baby food part, part of beta" (2026-09-30), phase 0 of
`docs/BUILD_PROMPT_SUPPLEMENTS_BABY_FOOD.md`. Full proposal with sources and first data rows:
`docs/SUPPLEMENTS.md`. **Nothing built until Sushil says "accepted".**

- **Legal basis, read from FSSAI's pages 2026-09-30:** the FSS (Nutra) Regulations 2022 are **not
  notified**; FSSAI runs them by directions under section 16(5), the latest of 18 October 2022 "with
  effect from 1st October 2022" (only the draft of 29 June 2022 is in the notifications list). Every
  citation says "as operationalised by FSSAI's direction of 18 October 2022".
- **Kind of pack** (`core/pack_kind.py` over `data/pack_kinds.json`, shared with D-140): licence first
  (D-116 extended: no FSSAI licence on a complete read plus a non-FSSAI manufacturing licence gives
  `not_food`; shape never decides), then infant words, then medical words (`special_medical`: FSMP,
  FSDU, "RECOMMENDED TO BE USED UNDER MEDICAL ADVICE ONLY"), then the category words of 5(12)(a)(i)(A)
  ("HEALTH SUPPLEMENT", "NUTRACEUTICAL", and 6(1)(f)(ii)'s "Dietary supplements", "Food supplements"),
  then the catalogue's 13.6; otherwise `food`, exactly as today. Disagreements go to a reviewer.
- **What applies:** allergens first; the 5(12) label statements found or not found (complete read of
  both faces); additives against Annexure 3 (tablets, capsules, syrups, by name) or the 13.6 list;
  tiles for Schedule II plant notes (about 54 notes on 48 rows, quoted exactly with the plant part,
  each row copied from the page image); amounts per daily usage beside ICMR-NIN's RDA (men and women)
  and upper limit (Short Summary 2020, revised 2024, pp. 30 and 32), a tile only above the upper limit;
  the 5(10) line for children of 2 to 5. **Off:** NOVA count, D-132 notes (hydrogenated vegetable oil
  is a listed tablet lubricant, Annexure 3 item 30), Table 15.1, the score; the sugar answer only for
  food formats; Compare only between supplements.
- **Corrections to the build prompt:** the statements are 5(12), not "regulation 12"; the pregnant,
  under-5 and elderly statement belongs to FSDU (6(3)(f)(ii)(A)) and sportsperson food, not to health
  supplements; the one-RDA limit sits inside the nutrient-claim sentence of 6(1)(c)(i).
- **Questions for Sushil** (`docs/SUPPLEMENTS.md` section 8): the unnotified regulations' status and
  the one-RDA sentence (a lawyer); which RDA (men, women, activity); the `kid` band against "2 to 5
  years"; prebiotic/probiotic foods; English plant names (no source yet); the ICMR-NIN protein-powder
  line; 3 supplement gold labels (paid reads asked first); timing (D-083).
- **Accepted by Sushil 2026-09-30**, with his choices (the same message for D-140): "D-139 and D-140 accepted, with these choices: 1. Lawyer: I will send all three questions ... Until the answer, quote the supplement rules "as operationalised by FSSAI's direction of 18 October 2022", and show amounts beside the RDA without calling one RDA a limit. 2. Baby food ships in shadow, like the claim check (D-051): computed and stored; users see only the allergens and the breastfeeding line until the lawyer answers. 3. New band "baby, under 2"; "toddler" becomes 2 to 3 years. Ask existing toddler profiles once, on their next result, whether the child is under 2. Never relabel silently. 4. Show the ICMR-NIN RDA for men and for women side by side. 5. Protein-powder note: approved only if every sentence is quoted from ICMR-NIN with its page; otherwise drop it. 6. Gold labels: I will photograph 3 supplements and 3 baby foods myself, one of each in poor light. Ask me before the paid reads. 7. Timing: build phase 1 (kind of pack) and phase 2 (supplements) before the first cohort; baby food (phase 3) in shadow."
  For D-139 that means: (1) every citation reads "as operationalised by FSSAI's direction of 18
  October 2022"; amounts per daily usage are shown beside ICMR-NIN's RDA and upper limit, and **the
  RDA is never called a limit** (no "exceeds one RDA" finding); the lawyer gets the status and one-RDA
  questions. (4) Men's and women's RDA side by side. (5) The protein-powder note ships as proposed:
  both sentences are ICMR-NIN's own words on DGI 2024 printed p. 60 (PDF p. 77), cited with the page.
  (6) Sushil photographs 3 supplements (one in poor light); paid reads asked first. (7) Built before
  the first cohort: phase 1 (kind of pack, branch `pack-kind`), then phase 2 (branch `supplements`).
  Questions not answered in the message take the recommendation in `docs/SUPPLEMENTS.md` section 8:
  the 2-to-5 line for `toddler` and `kid`; prebiotic and probiotic foods stay ordinary food; plants
  matched on the schedule's Latin and Indian names only, no English names until a source gives them.
- **Phase 1 built (2026-09-30, branch `pack-kind`, web-28, migration 019, 794 tests).** Prompt rule 11
  copies `pack_statements` and `licences` word for word with their face (new PROMPT_VERSION
  `b26cc0ca9c24`, was `9593e129ab49`); rule 7a no longer tells the model to call "medicines" not food, so
  tablets and capsules are read and the licences decide. `core/pack_kind.py` over `data/pack_kinds.json`
  (every phrase with its regulation and page): licence first (not_food only on a complete read of both
  faces; a back-only drug licence goes to a reviewer), then medical words (so preterm, hypoallergenic and
  other special medical infant foods are special_medical, the outcome both docs give), infant words,
  supplement words, the catalogue's 13.x category, else food. A company's name never decides ("... Pvt
  Ltd", "Marketed by"). `/scan` returns `pack_kind`; the screen for any other kind shows the allergen
  lines first, the kind's lines and printed evidence (the infant breastfeeding line was removed before
  merge, see D-140), the ingredient list, Scan another, Report a mistake; no summary, tiles, additives, glance,
  nutrition, band, Compare or shop list (the app keeps no compare data for them). **Food is unchanged:**
  the six gold labels' output equals the baseline captured before any change
  (`tests/fixtures/pack_kind_gold_before.json`). Catalogue: `product_versions.pack_kind` and evidence;
  /review shows them, and for not_food pre-fills "Not food under the FSS Act: a drug licence, no FSSAI
  licence (D-116, D-139)" after the whole-pack check; the review checker's `pack_kind` check sends every
  kind but food, and any printed-kind and category disagreement, to a person. Walked in headless
  Chromium, light and dark, 390 x 844: no errors. **Found on the way:** the test suite sent its fake
  photos to Cloud Vision whenever the shell had `GOOGLE_VISION_KEY` set (conftest cleared the database
  URI, not the keys); `conftest.py` now clears both keys (suite with the key in the shell: 0 Google
  calls; it runs slower, about 8.5 minutes, on the Tesseract fallback).

- **Phase 2 built (2026-09-30, branch `supplements`, web-29, PROMPT_VERSION `4efbe2214842`).** Prompt rule 12
  copies the composition table ("Each tablet contains...") as printed. `lenses/nutra.py` over three tables,
  each row from its page: `data/nutra_botanicals.json` (53 notes on 48 Schedule II rows, every one of the 33
  schedule pages read from the image; names printed on two rows left out: "Sage", "Saral"; six notes the
  schedule doesn't box to one part carry `placement`), `data/nutra_additives.json` (Annexure 3: 86 tablet,
  capsule and syrup additives, 40 for supplements; the 10 May 2022 order's 7), `data/nutra_rules.json`
  (5(12) statements, ICMR-NIN's RDA for men and women and upper limits from the Short Summary pp. 30 to 32,
  the 5(10) line, the protein-powder sentences). A supplement's result: allergen lines first; tiles for a
  plant note (the note quoted, only for the part it belongs to), a day's amount above ICMR-NIN's upper limit,
  an additive not found in the lists; sections: "For children" (5(10), with a toddler or child profile), a
  day's amounts beside the RDA for men and for women ("RDA" never called a limit, Sushil's choice), the 5(12)
  statements found or not found (only on a complete read of both faces; the second reading counts too),
  additives against the list for the format (Appendix A's GMP table applies to every format, 5(4)(a) and the
  10 May order; tablet-list names mark additives only in tablets; a colour in a tablet isn't checked, the D&C
  Rules' list isn't read), ICMR-NIN's protein-powder sentences (DGI p. 60) for a protein powder; the sugar
  chip only for a food format. No score, grade, band or NOVA count in the /scan answer (`withheld`,
  `supplement_not_scored`); flags stay for reviewers. Every amount must be in the second reading of the photo
  (D-133), else none is shown. Not compared: folate (packs print folic acid), vitamin A (form), vitamin D in
  micrograms (ICMR-NIN's table is in IU), biotin and pantothenic acid. From the catalogue (no photos): plants
  and additives only. `tests/test_supplements.py` (29); phase 1 tests updated. Walked in headless Chromium,
  light and dark: no errors. **Not built, for Sushil:** "Compare only between supplements": today's Compare
  names "the better pick for a child", and FSSAI's 5(10) says supplements for children of 2 to 5 years
  "shall only be given under medical advice", so supplements stay out of Compare until Sushil says what a
  supplement comparison should say.
- **Compare, decided by Sushil 2026-09-30** ("keep supplements out of Compare for the beta, as you built it"):
  supplements stay out of Compare for the beta. Compare's ranking rules are for food, no source we read ranks
  one supplement above another, and a "better choice" between supplements is close to medical advice.
  Revisit after the week-4 result (D-083). `/compare` already refuses them (`data/pack_kinds.json`
  "comparable": food only), with a test.

### D-140 · Baby food: infant formula and complementary foods, released in shadow `LOCKED` (2026-09-30)
Same request as D-139. Full proposal: `docs/BABY_FOOD.md`. **Nothing built until Sushil says "accepted".**

- **Legal basis:** FSS (Foods for Infant Nutrition) Regulations 2020 (gazetted 4 December 2020,
  amended 30 August 2022, compendium Version II), **in force from 1 October 2022**; selenium,
  manganese, iron and biotin limits from FSSAI's direction of 18 October 2022, Annexure-1 (a 2023
  amendment is a draft). The L&D First Amendment 2026 (from 1 July 2027) makes % RDA optional on
  these packs. **IMS Act 1992** quoted only from India Code's text "As on the 15th December, 2025",
  `sources/legal/ims-act-1992/ims-act-1992-en-as-on-2025-12-15.pdf` (downloaded by Sushil 2026-09-30):
  2(f) ""infant food" means any food (by whatever name called) being marketed or otherwise represented
  as a complement to mother's milk to meet the growing nutritional needs of the infant after the age of
  six months and up to the age of two years"; 2(g) ""infant milk substitute" means any food being
  marketed or otherwise represented as a partial or total replacement for mother's milk for infant up to
  the age of two years" (p. 4).
- **Kind `infant`** from "MOTHER'S MILK IS BEST FOR YOUR BABY" (4(1)(a)), the six-months statement,
  "Traditional Food for Infants" (11(3)), the regulation's product names, or category 13.1/13.2; an
  age statement alone goes to a reviewer. Preterm, lactose-free, hypoallergenic, IEM and mono-grain
  foods are `special_medical` (allergens and their own statement only). Product type (formula,
  follow-up, milk cereal, processed cereal, traditional) from the printed name; without it, the
  type-dependent checks are off.
- **Checks:** allergens first (4(5) asks for an allergen warning too); regulation 4's statements found
  or not found; 4(2)'s words "Humanised", "Maternalised", "Full Protein Food", "Energy Food",
  "Completer Food", "Health Food" (exact words only; pictures of an infant or woman are a reviewer
  check, never the app's); 5(1) "free from preservatives, added colours and flavours" and 5(2) additives
  per type; hydrogenated fat by type (7(1)(c), 8(1)(c), 9(1)(d); follow-up formula "partially"; nothing
  for traditional foods), all with D-111's care; composition beside the type's table where the pack
  prints the same nutrient (recommended reviewer-only in the beta); ICMR-NIN's breastfeeding line
  (guideline 3, p. 21) on every infant result.
- **IMS Act caution, until a lawyer reads it.** 2(j) (p. 4): ""promotion" means to employ directly or
  indirectly any method of encouraging any person to purchase or use infant milk substitute, feeding
  bottle or infant food." 3 (p. 5): "No person shall (a) advertise, or take part in the publication of
  any advertisement, for the distribution, sale or supply of infant milk substitutes, feeding bottles or
  infant foods; or (b) give an impression or create a belief in any manner that feeding of infant milk
  substitutes and infant foods are equivalent to, or better than, mother's milk; or (c) take part in the
  promotion of infant milk substitutes, feeding bottles or infant foods." 2(a) counts "electronic
  transmission" as a means of advertisement. 6 (pp. 5 to 6) is the label notice regulation 4 repeats
  ("important notice", "mother's milk is best for your baby", and (b) to (i)); 6(2) forbids "pictures
  of an infant or a woman or both" and "the word "humanised" or "maternalised"". So: no grade, score,
  band, ranking, "better pick", Compare, shop list, tallies or share card for an infant pack, refused on
  the server with a test per route; nothing that sets an infant food beside mother's milk; **released in
  shadow** (like D-051): users get allergens and one sentence; `INSIDELABEL_INFANT_TO_USERS` off by
  default.
- **Section 7(1) asks for six particulars, not one breastfeeding line.** 7(1) (p. 6): "Every educational
  or other material including advertisements or material relating to promotion of infant milk
  substitutes, feeding bottles and infant foods, whether audio or visual, dealing with pre-natal or
  post-natal care or with the feeding of an infant and intended to reach pregnant women or mothers of
  infants shall include clear information relating to (a) the benefits and superiority of
  breast-feeding; (b) the preparation for, and the continuance of, breast-feeding; (c) the harmful effects
  on breast-feeding due to the partial adoption of bottle feeding; (d) the difficulties in reverting to
  breast-feeding of infants after a period of feeding by infant milk substitute; (e) the financial and
  social implications in making use of infant milk substitutes and feeding bottles; (f) the health
  hazards of improper use of infant milk substitutes and feeding bottles;" plus (fa) "the date of
  printing and publication of such material and the name of the printer and publisher" and (g) matters
  prescribed; 7(2): such material shall not "be utilised to promote the use or sale" of them. The
  ICMR-NIN breastfeeding line (guideline 3, p. 21) is therefore **held** until the lawyer says whether an
  infant-food result is such material; one line would cover part of (a) and (b) at most.
- **Baby profile band** (D-074, a value): `baby` "Under 2 years", `toddler` "2 to 3 years". On an
  ordinary food a baby profile gets only sourced lines: added sugar (ICMR-NIN p. 29 "Added sugar must
  be totally avoided for children below 2 years"), non-sugar sweeteners (WHO 2023 recommendation 5c),
  honey (ICMR-NIN p. 21), salt (p. 26), HFSS by Table 15.1 (p. 28). WHO's "foods high in sugar, salt
  and trans fats" is not applied: it gives no threshold.
- **Questions for Sushil** (`docs/BABY_FOOD.md` section 9): for a lawyer, (a) whether showing an infant
  food's facts is "promotion" (2(j)) or an "advertisement" by "electronic transmission" (2(a), 3(a)),
  (b) **whether an infant-food result counts as "educational or other material" under 7(1)**, which
  would need (a) to (f) and (fa), not one line, and (c) whether the baby profile's lines on ordinary
  foods make every result 7(1) material; release; age statements alone; the baby band and existing
  toddler profiles; composition lines reviewer-only; 3 baby-food gold labels.
- **Updated 2026-09-30** (Sushil: "The IMS Act is now in sources/legal/ims-act-1992/ ... Section 7(1)
  asks for six particulars (a) to (f), not one breastfeeding line"): the Act's quotes above replace
  "Not read"; the breastfeeding line moved from "shown in shadow" to "held".
- **Accepted by Sushil 2026-09-30** with the choices quoted under D-139. For D-140: (1) the lawyer gets
  all three IMS questions (2(j), 3, 7). (2) **Shadow, like D-051:** computed and stored; **users see only
  the allergen lines and the breastfeeding line** (ICMR-NIN guideline 3, p. 21) until the lawyer
  answers. Claude flagged once, on recording it: 7(1) asks "educational or other material" for all six
  particulars (a) to (f) and (fa), and one line covers part of (a) and (b) at most, which is why the
  update above had held it; Sushil's choice stands and the lawyer's question (b) covers it. (3) New
  band `baby` "Under 2 years"; `toddler` becomes "2 to 3 years"; a phone's existing toddler profiles are
  **asked once, on their next result, whether the child is under 2**, never relabelled silently. (6)
  Sushil photographs 3 baby foods (one in poor light); paid reads asked first. (7) Phase 3 (branch
  `baby-food`) ships in shadow. Questions not answered in the message take the recommendation in
  `docs/BABY_FOOD.md` section 9: an age statement alone stays `food` with the baby lines and a reviewer
  check; composition lines are reviewer-only in the beta.
- **Changed by Sushil 2026-09-30, before merging phase 1** ("Remove the breastfeeding line for infant packs
  until the lawyer answers question (c). Infant packs show the allergen lines, the kind in the pack's own
  words, the ingredient list, and one sentence that results for infant foods aren't shown yet. ... Confirm
  the server itself refuses a grade, Compare, the shop list and any ranking for an infant pack, with a test
  for each route"): **the breastfeeding line is removed** until the lawyer answers (the note above, 7(1)'s
  six particulars, stays for the lawyer; question (b) asks whether an infant-food result is 7(1) material,
  (c) whether the baby lines make every result so). The infant result: allergen lines, the headline quoting
  the pack's own kind words ("This pack says "Infant Formula"."), the sentence "Results for infant foods
  aren't shown yet. We show the allergens on the list and the ingredient list.", the ingredient list.
  **The server refuses, not only the app** (audited 2026-09-30): `/scan` sent `verdict` (score, grade,
  band), `display`, `claim_check`, `nutrition` and `regulators` for an infant pack; it now sends them as
  null with `withheld` (vision and catalogue paths). `/compare` knew no kinds; it now refuses (422
  `not_comparable`, reason `infant_food`) a pack whose client-reported kind, printed statements (re-decided
  on the server) or stored scan kind isn't comparable (`data/pack_kinds.json` "comparable": food only, so
  supplements too until phase 2). The shop list has no server route: `screen.shop_list` is never set for
  an infant pack, even read from a screen. `/compare`'s better pick is the product's only ranking. A test
  for each (`tests/test_pack_kind.py`, `tests/test_pack_kind_db.py`). Back-only reads stay as built (both
  faces needed for not_food; back-only goes to a reviewer).
- **Phase 3 started 2026-09-30 (Sushil: "start phase 3 (baby food, in shadow) on its own branch from main"),
  branch `baby-food`, first part:** `data/infant_rules.json` read from the compendium's page images (types
  from 2(1) and the chapters, PDF pp. 1, 2, 7, 12, 18, 24, 30; regulation 4's statements pp. 4 to 6; 4(2)'s words
  and 5(1) p. 6; the four hydrogenated-fat sentences pp. 7, 13, 19, 25). Follow-up formula (10) sits in
  Chapter 3 "Infant Food" with the cereal and traditional foods, so the six-months line of 4(1)(a) ("In case of
  infant food") applies to it and not to infant formula (Chapter 2 "Infant Milk Substitute").
  `lenses/infant.py`: the type from the printed name and the front's own words (never from regulation 4's
  statements, which name "infant milk substitute or infant food" on every pack); statements found or not
  found on a complete read; 4(2)'s words; 5(1) preservatives, colours (by the additive's class) and flavours
  (not flavour enhancers); hydrogenated fat by type (follow-up formula: "partially" only; traditional: none).
  `/scan` computes it for an infant pack and stores it with the reading (`raw_extraction._infant`); nothing
  of it is sent to the user; `/review` shows it with the reviewer's own check (no picture of an infant or a
  woman, 4(2)). **Not yet:** 5(2)'s additive tables per type, 4(3) (no milk), composition (reviewer-only),
  the `baby` band with the one-time toddler question, and `INSIDELABEL_INFANT_TO_USERS` (nothing to switch on
  until the lawyer answers).
- **Phase 3, part 2 (branch `baby-food-additives`, 2026-09-30): 5(2), each type's additive list.**
  `data/infant_additives.json`, every row copied by hand from the page images: infant formula 7(2)(a), 28 rows,
  PDF pp. 10 to 12; milk cereal 8(2)(a), 70 rows, pp. 15 to 18; processed cereal 9(2)(a), the same 70 rows and
  limits, pp. 20 to 24; follow-up formula 10(2)(a), 29 rows, pp. 27 to 29; traditional foods use the milk
  cereal list (11(2), p. 29); Schedule I(d)'s five nutrient carriers (414, 551, 421, 1450, 301), p. 52, which
  each type's (b) allows. **A misprint kept as printed:** 10(2)(a) gives sodium hydroxide INS 525, potassium
  hydroxide's number (7(2)(a) and 8(2)(a) give 524); a follow-up formula's 524 is therefore "not found", for a
  reviewer. `lenses/infant.py additives()`: for a known type, an INS number on the list (core/tokenize) that
  the list doesn't name is "not found in this type's additive list", never "not permitted" (5(2) allows
  carry-over additives, and the type may be misread); compared on the number and any letter suffix, since the
  parser keeps a lone roman "i" ("500i") but drops "ii"; entries under vitamins or minerals (nutrient sources,
  Schedule I) are left out. On /review with the other infant checks; nothing reaches the user.
- **Phase 3, part 3 (branch `baby-food-no-milk`, 2026-09-30): 4(3).** "The product which contains neither milk
  nor any milk derivatives shall be labelled "Contains no milk or milk products or milk derivatives" in
  conspicuous manner." (PDF p. 6.) `lenses/infant.py no_milk()`: found or not found, only when both faces were
  read whole and the allergen check (lenses/allergens.py, D-072's 0.95 gate) says milk is not listed; contains,
  may contain, uncertain or cannot confirm say nothing. "Conspicuous" is not judged. Reviewers only.
- **Phase 3, part 4 (branch `baby-food-composition`, 2026-09-30): composition, reviewers only** (Sushil's
  choice 5). `data/infant_composition.json`, copied by hand from the page images: infant formula 7(1)(g), 30
  rows, PDF pp. 8 to 9; milk cereal 8(1)(d), 11 rows, pp. 13 to 14, and its optional nutrients 8(1)(e), 16
  rows, pp. 14 to 15; processed cereal 9(1)(f), 18 rows, pp. 19 to 20 (its total fat is a maximum, 7.50 g per
  100 g, where milk cereal's is a minimum); follow-up formula 10(1)(h), 25 rows, p. 26. FSSAI's direction of
  18 October 2022, Annexure-1 (direction PDF pp. 3 to 4, in force from 1 October 2022), replaces seven rows:
  selenium 5 to 40 µg per 100 g in all four types, processed cereal iron 2 to 5.65 mg, follow-up biotin 7.50
  to 50 µg and manganese 5 to 500 µg; each keeps the compendium's figures under `compendium`. Left out: rows a
  label can't print (moisture, ash, fibre, ratios, milk fat, amino acids, per 100 ml of prepared feed), and
  folate (the tables are in DFE, labels print folic acid). Traditional foods have no table.
  `lenses/infant.py composition()`: for a known type and a table per 100 g, each nutrient whose per 100 g number
  is also in the second reading of the photo (as D-133) is set beside the type's range, "within", "below" or
  "above" (facts, never "fails"); IU, kJ and unit-less cells aren't compared, nor per 100 kcal columns. The
  D-133 reader is unchanged (it still ignores vitamins and minerals for foods): the infant lens reads those rows
  itself. On /review only.
- **Phase 3, part 5 (branch `baby-food-under-2`, 2026-10-01): the `baby` band and the one-time toddler question,
  the last part of phase 3.** Bands (a value, not a field, D-074): `baby` "Under 2 years", `toddler` "2 to 3 years",
  `kid`, `young`; the toddler lens's stricter tiers (sugar in the first 3, caffeine, additives flagged for infants)
  apply to `baby` too. `data/baby_lines.json`, every quote read first-hand on 2026-10-01 (D-046) with page, basis
  and verified_on: added sugar (ICMR-NIN DGI 2024 p. 29, PDF p. 46, under Figure 4.3), non-sugar sweeteners (WHO
  2023 complementary feeding, recommendation 5c, p. xii, PDF p. 14), honey (DGI p. 21, PDF p. 38), salt (DGI p. 26,
  PDF p. 43), HFSS (DGI p. 28, PDF p. 45) only when the D-133 table's checked salt or added sugar is over Table 15.1,
  and the supplement line (Nutra 2(1), Annexure 1 p. 1, PDF p. 4). Shown as the baby profile's own `child_facts`
  with their source, on an ordinary food (and the one line on a supplement); never on an infant, special medical
  or not_food pack. Nothing else moves (score, band, headline, allergen lines, Compare). **Choices made in the
  build, RECOMMENDED until Sushil says "accepted":** (a) which sweeteners count is WHO's own NSS guideline (2023,
  p. xi, PDF p. 13): "Common NSS include acesulfame K, aspartame, advantame, cyclamates, neotame, saccharin,
  sucralose, stevia and stevia derivatives"; sugar alcohols and low-calorie sugars "are not considered NSS", so
  sorbitol, maltitol, xylitol and erythritol get no WHO line (D-132's sweetener row for children keeps them, as
  before). (b) The supplement line quotes 2(1) ("FSSAI's rules for supplements say "These foods are intended for
  population above the age of 2 years".") in place of `docs/BABY_FOOD.md`'s paraphrase. (c) The question: the
  server sends `band_question` (its words, under the lint, D-091) on a result when a profile is `toddler`; the app
  asks for the first toddler profile saved before this change ("Is {name} under 2?", "Yes, under 2" / "No, 2 or
  older"), keeps `under2_asked` on the phone (never sent, D-074) and never asks that profile again; a profile saved
  from the editor counts as answered. Not sent after D-146's digit check in the same scan (`barcode_answer`), on a
  retake, or on an infant or special medical result. One profile per result. Lawyer's question (c), whether the
  baby lines make every result 7(1) material, stays open (`docs/BABY_FOOD.md` section 9).
- **Sushil, 2026-10-01: show baby lines.** The section 6 baby lines (`docs/BABY_FOOD.md`) and the baby supplement
  line go to users now, before the lawyer answers question 1(c) in `docs/BABY_FOOD.md` section 9. Claude had
  recommended holding them behind a server switch until then; Sushil's choice stands. As merged in #81 they
  already go to users (no switch was built), so nothing in the code changes. The three build choices above,
  (a) to (c), are still RECOMMENDED.


### D-141 · A barcode read from a photo counts only when two reads agree, or the barcode is big enough `SUPERSEDED by D-144` (2026-09-30)
Found by Sushil in the phone check of phase 1 (2026-09-30): a small, blurry barcode photo made zxing-cpp read
**0961676012608** where the pack prints **8901058018608**, and `barcode.check()` accepted it. Six of the 13
digits differ, yet the check digit is right: a check digit catches any single wrong digit, but when several
are wrong about one misread in ten still passes, and every other rule in `check()` (length, case codes, store
codes, books) is about what kind of code it is, not whether the bars were read right. The barcode is the
catalogue key (D-024): this read would have filed the pack under another product. Today `read_from_photo()`
reads once, at up to 2400 px, and takes the code that passes `check()`.

**Recommended by Claude:**
1. A photo barcode counts when **two reads agree**: zxing-cpp on the photo as now (up to 2400 px) and once more
   on one rescale of it (half size), both giving the same code. Two reads that disagree, or a second read that
   finds nothing, are refused with a new message ("We couldn't read that barcode clearly. Hold the phone
   closer, with the barcode flat and in focus, or use the camera scanner."), never a guess.
2. **Or the barcode is big enough** that one read is enough: its width in the photo at or above a threshold
   set from Sushil's barcode photos (the gold photos, D-139 point 6). Starting point to measure, not yet
   sourced: 2 pixels per bar module; an EAN-13's width in modules would be read first-hand in GS1's
   specification before the number is fixed.
3. The live camera scanner is unchanged. A barcode found on a back photo (`barcode_too`) follows the same rule.
4. **The case as a test:** `tests/test_barcode_two_reads.py` stands in for zxing-cpp with Sushil's two codes.
   The refusal is an expected failure (`xfail`, strict) until this is built, so the suite shows the gap
   without failing, and flips to a plain test when it is.
Cost: one more zxing-cpp pass per barcode photo (milliseconds, no paid call). Nothing built until Sushil says
"accepted".
- **What happened (2026-09-30).** Accepted by Sushil with two conditions: build only "two reads agree" (no
  size threshold), and measure it on the server first (stop above 5% of today's accepted reads refused).
  Built with a half-size second read (PR #66, merged and deployed before the measurement came back): the
  server run refused **2 of 6** accepted photo reads (33.3%), both right (they matched the camera read on
  the same scan). Sushil rolled the server back and #66 was reverted (#67, deployed). A three-quarter-size
  second read (branch `barcode-rescale-75`, never merged) refused **1 of 6** (16.7%): f77b1de8...d1.jpg,
  8904089974837 = the camera read, the second read empty. Two reads alone refuse too many right codes.
  Superseded by D-144, which lets the photo's OCR text confirm a code.

### D-142 · A product's barcode is corrected only through a recorded, reviewed change `LOCKED` (2026-09-30)
Found by the D-141 measurement, confirmed on the server by Sushil (2026-09-30): product 42 "Corn Flakes" is
published under **4901196008343**, the camera scanner's read on scan 799e4f9a (2026-09-27, new_product),
while two zxing reads of that scan's back photo (03f8277a...bae974.jpg) agree on **8901499008343**. The two
codes differ in 4 of 95 bar modules and both have a right check digit. **Sushil read the printed digits on
the photo (2026-09-30): the pack prints 8901499008343**, so product 42 is filed under a camera misread. Until now there was no reviewed
way: `approve()` wrote `barcode = COALESCE(<form>, barcode)`, so typing another code on the review form
changed a published product's key and kept nothing of the old one; the other way was SQL.

**Recommended by Claude (built on branch `d142-barcode-correction`, not merged):**
1. **One way to change it:** `ReviewService.correct_barcode()`, run with `tools/barcodes.py fix` (a dry run
   until `--yes`). It records old and new code, who (`--by`, an active reviewer account, D-097), when, why
   (required: where the right code was read) and the photo key as evidence, in `barcode_changes`
   (migration 020). It refuses a code that fails `barcode.check()`, the code the product already has, and a
   code another product has (merging two products is a separate decision, not done here).
2. **The database enforces it:** a trigger refuses any UPDATE of `products.barcode` without a
   `barcode_changes` row for that product, old and new code, written in the same transaction. A direct SQL
   UPDATE fails. Setting a barcode where there was none is not a change and is allowed.
3. **The review form** can no longer change a published product's barcode (it names the correction
   instead). A never-published product may still get its barcode set at review, because the scan's read can
   be wrong (D-143); that is recorded too (`via = 'review'`, the item number and the reviewer's note).
4. **The old code stays findable in the record** (`tools/barcodes.py history <code>`), never by a scan: after
   the change, a scan of the old code finds nothing, as for any pack not yet checked.
5. **Look for others** (branch `d142-barcode-audit`, Sushil's item 2): `tools/barcode_audit.py`, read-only,
   sets every published product's barcode against zxing reads of its own photos (every version's and scan's,
   as `/check-photo` reads them) and the barcodes printed in its scans' stored OCR text
   (`barcode.codes_in_text`: the digits under the bars, in their printed groups). MISMATCH (zxing reads
   another code), unconfirmed (nothing shows the code), confirmed, no photos. A mismatch is fixed with point 1
   only after a person reads the printed digits.
6. **The audit on the server** (Sushil, 2026-09-30): 47 published, 1 MISMATCH (#42, by eye 8901499008343),
   6 confirmed, 40 unconfirmed (no barcode in their photos), 0 no photos. Sushil spotted a likely second
   misread among the unconfirmed: #48 Sugar Free Natura, 4992146143214 from the camera (499, where every
   other camera read is 890 or a known 7622 Mondelez code). So the audit now also lists **SUSPECT**: a camera
   read nothing confirms, whose GS1 prefix (first 3 digits) is not 890 and not the prefix of another published
   product of the same brand (branch `d142-audit-suspects`). A reason to photograph the pack's barcode, not a
   finding; a correction still needs the printed digits read by a person.
Not done: a /review page for it (the tool is enough for one reviewer; a page later if others need it);
telling installs that scanned the product under the old code (their saved results show the old code).
- **Accepted by Sushil 2026-09-30** ("D-142 and D-143 accepted"), merged (#68, #72) and deployed. **#42
  corrected on the server** the same day: `il tools/barcodes.py history 8901499008343` shows record #1,
  2026-09-30 16:41, by sushil (4901196008343 to 8901499008343).

### D-143 · A camera barcode is set against the scan's own photos; one they don't show waits for a reviewer's check `LOCKED` (2026-09-30)
Found by the D-141 measurement: product 42's camera read (4901196008343) and its back photo's two zxing reads
(8901499008343) disagree; the pack prints 8901499008343 (Sushil, by eye). `web/camera.js` takes a code seen twice within 1.5 s (D-124), but two frames of one
view share the blur, so the same wrong code can come twice; the check digit doesn't catch it (4 of 95 bar
modules differ). Sushil (2026-09-30): "Include camera reads in the D-141 rule: when the scan also has a
photo, the camera code must match the photo's read or the digits in its OCR text; otherwise the reviewer is
asked to check the barcode before publishing."

**Recommended by Claude (built on branch `d143-camera-barcode-check`, stacked on `d142-barcode-audit`, not merged):**
1. **At `/scan`**, when a barcode comes with photos: `barcode.confirm()` reads every photo of the scan as
   `/check-photo` does and looks for the code in the Cloud Vision text of the back (`codes_in_text`, the printed
   digit groups). `confirmed` (a photo or the OCR shows it), `mismatch` (a photo reads another code and none
   reads it), `not_shown` (nothing shows it). Kept on the scan row (`scans.barcode_check`, migration 021, with
   the source), and its time in `timings.barcode_check_ms`. **The user's result doesn't change.**
2. **At `/review`**: a camera code that isn't `confirmed` is shown above the form ("... came from the camera
   scanner, but the photos read ...") with a tick box, "I checked the barcode". `approve()` publishes it only
   when ticked (the reviewer is recorded, `review_queue.barcode_checked_by`), or when the reviewer types
   another code (recorded as a D-142 change, `via = 'review'`).
3. **The review agents** (D-117) get a check, `barcode_confirmed`, that fails for such a code, so it never
   publishes without a person.
4. **Only camera reads are held.** A code read from a barcode photo by `/check-photo` has its own rule (D-144, replacing D-141). The app always
   says where a code came from (D-104); a request that doesn't (an API client, a test) is recorded, not held.
Open: `not_shown` may be common, since many back photos don't show the barcode, and then the reviewer has
nothing in the photos to check against. How common is measured by `tools/barcode_audit.py`'s "unconfirmed"
count on the server; if it is most packs, the answer may be to ask the app for a barcode photo with a new
pack instead.
- **Accepted by Sushil 2026-09-30** ("D-142 and D-143 accepted"), merged (#72) and deployed. The open point
  above is answered by the audit (40 of 47 packs show no barcode): D-145, held until after week 4.

### D-144 · A photo barcode counts when two reads agree or its digits are in the photo's OCR text `LOCKED` (2026-09-30)
Replaces D-141. Sushil (2026-09-30): "a barcode from a scan photo counts if two zxing reads agree OR its 13
digits appear in that photo's Cloud Vision/Tesseract text (the D-093 second reading, no extra paid call);
otherwise refused. /check-photo has no OCR: keep two-reads-agree there and point the user to the live camera
scanner on a refusal." Why both: a check digit catches one wrong digit, not several (0961676012608 for
8901058018608, 0921129008343 and 4901196008343 for 8901499008343 all pass it), and two reads alone refused
right codes (D-141's measurement). The digits printed under the bars, read by a different reader, are
independent evidence of the same code.

**Recommended by Claude (built on branch `d144-photo-barcode-ocr`, stacked on `d143-camera-barcode-check`, not
merged):**
1. **The rule**, `barcode.read_from_photo(data, ocr_text=...)`: zxing-cpp reads the photo (up to 2400 px); a
   code counts when a second read at three-quarter size (`SECOND_READ`, the better of the two scales measured)
   finds it too, or when `codes_in_text()` finds it in that photo's OCR text. Otherwise `barcode_unsure`. The
   second read is skipped when the OCR text already shows the code.
2. **`/check-photo`** has no OCR text: two reads decide, for a barcode photo and for "Barcode ... found on it
   too" on a back or front photo. A refused barcode photo gets "We couldn't read that barcode clearly from the
   photo. Scan it with the camera scanner instead, or take the photo again closer, with the barcode flat and
   in focus."
3. **`/scan`** has the OCR text (Cloud Vision, or Tesseract when it falls back), for the back photo only. The
   app takes a back photo's barcode from `/check-photo`, where the OCR text doesn't exist yet, so a code only
   the OCR text confirms would never arrive. So: **a scan sent without a barcode reads its own photos**
   (`barcode.photo_code()`), and one code that counts (the back with its OCR text, the front with two reads)
   becomes the scan's barcode (`barcode_source` "scan_photo", recorded in `scans.barcode_check`). None, or
   more than one: the scan goes on without one (D-107: the result, an unlisted row). A barcode the app sent is
   never replaced (a camera read is D-143's).
4. **D-143's check** reads the back photo with its OCR text too.
5. **Measure before any merge:** `tools/barcode_reads.py`, the old rule (one read) against this one over every
   stored photo, with each back photo's stored OCR text; Tesseract (local, free) only for a back photo with no
   stored text where the text decides the answer. The same 5% line.
Not covered by the measurement: barcode photos taken on their own are never stored, and two reads alone
decide them. If refusals there are frequent, the camera scanner is the answer the message gives.
- **Measured on the server and accepted by Sushil, 2026-09-30:** 107 photos; the old rule accepted 6, the new
  rule 6 (1 of them by the Cloud Vision text only, f77b..., the photo D-141's two reads refused); refused 0 of
  6 (0.0%), within the 5% line; the wrong 0921129008343 on 03f8... is dropped. "D-144 accepted (Sushil)."
  Merged with D-142 and D-143 (PRs #68, #72) and deployed.


### D-145 · The camera frame the scanner accepted goes with the scan as the barcode's evidence photo `RECOMMENDED, held until after week 4 (D-083, D-105)` (2026-09-30)
Answers D-143's open point with the server audit (Sushil, 2026-09-30): **40 of 47 published packs have no
barcode in their photos**, so for most packs nothing on the server can check the camera's code, and a
reviewer asked to "check the barcode" has nothing to check it against. Two camera misreads are already in
the catalogue (#42 certain, #48 likely). Today nothing from the live scanner leaves the phone:
`web/camera.js` decodes on the device (BarcodeDetector) and sends only the digits.
Sushil (2026-09-30): "when the live camera scanner accepts a code, the app sends that camera frame with the
scan as the barcode's evidence photo, checked by zxing and the OCR text on the server like any other photo,
and kept with the version under D-080 retention. Note the privacy side for the DPDP map."

**Recommended by Claude (proposal only, nothing built):**
1. **The frame.** When `camera.js` accepts a code (the second frame agreeing, D-124), it draws that video
   frame to a canvas and keeps it as a JPEG with the code. **Cropped to the barcode:** the detector reports
   each code's `boundingBox`; the app keeps that box widened enough to hold the printed digits under the bars
   (the margin to be set on the phone), not the whole frame. Data minimisation (DPDP s.8(1), purpose), and a
   hand or a room mostly falls outside the crop. Nothing else of the video is kept.
2. **When it is sent.** Only with a scan that sends label photos (a pack the catalogue may add or re-read), as
   a new part, `barcode_photo`, with `barcode_source` "camera". A catalogue lookup (barcode only, D-024) sends
   no frame: nothing would be added, so nothing needs evidence. Kept on the phone only until that scan is sent.
3. **Checked like any other photo.** `/scan` stores it (media, content-hash key) and reads it with the D-144
   rule: two zxing reads agree, or the code's digits are in its OCR text. The OCR text for it: **Tesseract
   (free, on the server) only when the two reads don't agree**, not Cloud Vision, which would be a new paid
   call on every new pack; Sushil's choice if he prefers Cloud Vision. D-143's check then has a photo that
   shows the barcode for almost every camera scan. **A limit to know:** the frame is the one the phone's
   decoder read, so it carries the same blur; zxing is a different decoder and the printed digits are a
   different reading, but the frame's main value is to a person: the reviewer reads the digits in it.
4. **Kept with the version (D-080).** New columns `barcode_image_key` on `scans` and `product_versions`
   (one migration); `retention.py` treats it like the back and front keys: deleted 30 days after the scan
   unless held, kept while it is a published version's record. `/review` shows it beside the barcode field.
5. **The privacy side** (for the DPDP map, row 4 and point 9): this is new data leaving the phone. Today the
   live camera sends nothing but digits; with this, one cropped frame goes to the server with a new-pack scan.
   It may still show a finger, a hand or part of a background; it is never sent to Gemini; with Tesseract as
   its reader it is not sent to Google either. The privacy page and "Before you start" must say so before it
   ships, which changes the terms version (D-105: users agree again). The data map gets the frame in row 4
   (and row 10 if Cloud Vision ever reads it).
Not decided here: whether a user can see and remove the frame before sending (a thumbnail with "Sent with
your scan" is cheap); the crop margin; whether old catalogue entries (the 40) should get a barcode photo from
the review queue instead.
- **Held by Sushil, 2026-09-30:** "D-145 stays held until after week 4": a Wave 2 build waits for the W4 number
  (D-083), and it changes what "Before you start" must say, so every tester would agree again (D-105).
- **For the DPDP data map, when it is built** (proposed point 9a; `docs/DPDP_DATA_MAP.md` is unchanged until then):
  > 9a. **Proposed, not built (D-145): a camera frame with the barcode.** Today the live barcode scanner
  > decodes on the phone and sends only the digits. D-145 proposes sending the one frame it accepted,
  > cropped to the barcode and its printed digits, with a scan that adds a pack to the catalogue, as
  > evidence that the digits are right (two camera misreads were found in the catalogue, 2026-09-30).
  > Stored like a pack photo (row 4: deleted at 30 days unless it becomes the catalogue record), never
  > sent to Gemini, read on the server by zxing and, only if needed, Tesseract (so not sent to Google).
  > The crop keeps most of a hand or a room out, but a finger or background can remain. Before it ships
  > the privacy page and the terms must say so (users agree again, D-105), and row 4 names it. The
  > reviewer should say whether this is enough, or whether the app should show the frame and let the
  > user remove it before sending.


### D-146 · A scanned code for a new pack is checked against the digits on the pack before the photo `LOCKED` (2026-09-30)
Proposed by Sushil (2026-09-30), after two camera misreads were found in the catalogue (#42, #48; D-142 to
D-145): "After the live camera scanner (or a barcode photo) finds a code for a pack NOT in the catalogue, the
next screen ("photograph the ingredients") first shows the code with its first 3 and last 4 digits large:
"Check these match the numbers under the barcode", with "Yes, they match" and "Scan again". "Scan again"
returns to the scanner; nothing is stored for the dropped code. For a catalogue hit, no digit check: the result
shows the product name with "Not this pack? Scan again". Store the answer on the scan (confirmed, rescanned)
and show it on /review next to D-143's check, as supporting evidence only: a reviewer still checks a camera
code the photos don't show. No typing of barcodes (D-104). All text from lenses/screen.py (D-091), wording
test covers it."

**Built by Claude (branch `d146-digit-check`, not merged):**
1. **The check.** `/scan`'s 404 `not_in_catalogue` now carries `barcode_check` from `lenses/screen.py`
   (`barcode_check()`): title "Check the barcode", "Check these match the numbers under the barcode", the code
   split into its first 3, middle and last 4 digits, "Yes, they match", "Scan again". A UPC-A, kept as 13 digits
   with a leading 0 (D-104), is shown as the 12 it prints. The app (`digitCheck()`) shows the first 3 and last 4
   large; every word is the server's. An older server sends no check, and the app goes to the photo as before.
2. **Nothing is stored for a dropped code:** the 404 lookup writes no row, and "Scan again" only returns to the
   scanner.
3. **The answer, on the scan it belongs to** (`scans.request.barcode_answer`, no migration): "confirmed" when
   the user taps "Yes, they match" for the first code they scanned; "rescanned" when the code came after at least
   one "Scan again" (for a new pack, the user then also tapped Yes; for a catalogue hit, it is the code the
   rescan found). `/scan` refuses any other value (422 `bad_barcode_answer`); `repro.py` replays it.
4. **A catalogue hit** carries `screen.rescan` ("Not this pack?", "Scan again"), shown under the product name
   when the result came from the scanner or a barcode photo; it returns to the scanner, and the next code is
   "rescanned".
5. **/review** shows the answer beside D-143's check ("On the phone, the tester said the digits match the
   numbers under the barcode."), marked "Supporting evidence only (D-146): a camera code the photos don't show
   still needs your check." D-143's gate is unchanged.
6. No typing (D-104): the check only confirms or drops a scanned code. `APP_VERSION` web-30 and the service
   worker's `il-shell-30` together.
Walked in headless Chromium (Playwright, 390 x 844, light and dark) against the real server on a scratch
database: a barcode photo of a new pack's code gives the digit check; "Scan again" returns to the scanner; a
catalogue hit after it shows the product's name with "Not this pack? Scan again" and is stored "rescanned";
"Yes, they match" goes to the ingredients photo; the only console errors are the two expected 404 lookups.
Not walked: the live camera (headless Chromium has no BarcodeDetector); it calls the same `lookUp()`.
- **Accepted by Sushil 2026-09-30, as merged in #79:** "the digit-check screen stays exactly as merged in #79
  ... Do not remove or change it." (He had asked the same day to remove the digit check under the principle
  "never make the user do the app's checking"; that message was cancelled before anything was changed. One quick
  check at the right moment is fine; no second prompt is to be added on top of it.)

### D-149 · The Play app's package name is `ai.insidelabel.app.f` `LOCKED` (2026-10-01)
**Sushil, 2026-10-01: "confirmed ai.insidelabel.app.f".** The Android package (application id) of the Play app,
the Trusted Web Activity of https://insidelabel.ai/app/ (D-010, D-148). It is registered in Play Console with the
app (name InsideLabel, default language English (United Kingdom) en-GB, App, Free, Play App Signing, D-012) and
**can never change after the first upload**: a different package is a different app on Play, with no installs,
reviews or testers carried over. It is written in `android/twa-manifest.json`, `android/app/build.gradle` (the
`applicationId` and `namespace`) and `data/assetlinks.json`; `tests/test_android_project.py` and
`tests/test_assetlinks.py` fail if any of them moves.

### D-148 · The beta runs in the Play Store app, free with a daily photo-scan limit; then Pro at Rs 51 a month through Play billing, with Google sign-in `LOCKED` (2026-10-01)
Its limit screen's words amended by D-184 (2026-10-08): no "During the beta"; the 15-a-day limit stays.
Direction from Sushil (2026-10-01): "Beta will go with apps, free, with a daily limit on photo scans. Then: Pro at Rs 51
through Play billing, with Google sign-in that also carries data across." Earlier the same day he proposed ads for
free users; Claude advised against them (below). Plan and numbers by Claude.

1. **The beta in the app.** Closed testing on Google Play, the Trusted Web Activity of insidelabel.ai that D-010 already
   plans (Bubblewrap). This supersedes D-102's "on the web first" only: the invite codes, one per tester, stay. The
   website stays live, as the content of the app and for testing. Play's current closed-testing requirement (number of
   testers and days) is read in Play Console when the account is set up (D-011), not from memory.
2. **Free, no ads, no payments** during the beta.
3. **A daily limit on photo scans per install: 15** (Sushil's choice). It uses D-095's limiter (photo scans 100 a
   day per install today; only the number changes). Barcode lookups keep their own budget and stay unlimited in
   practice: they cost about Rs 0 and never use up photo scans. When the limit is reached, one screen with words from
   lenses/screen.py: today's photo scans are used, barcode lookups still work, more tomorrow. No upsell in the beta.
   Worst-case cost: 50 testers x 15 photo scans x about Rs 0.6 = about Rs 450 a day.
4. **After the beta: Pro at Rs 51 a month** (a Rs 499 a year option to decide then) through Google Play billing (about
   15% to Google on subscriptions; the current rate and India's alternative billing option are checked before
   launch). **Google sign-in** comes with Pro: it restores a subscription on a new phone and carries profiles, shop
   list and Compare across (it also covers moving from another browser). That is new personal data (an email):
   docs/DPDP_DATA_MAP.md is updated before it ships. Free stays: unlimited barcode lookups and 5 photo scans a day;
   Pro: 15 a day. What else Pro includes is D-082's question, answered from beta interviews.
5. **Ads: none in the beta.** For after the beta Claude recommends none at all: a web ad in India earns a few paise
   against a photo scan's 50 to 60 paise; food-brand ads beside food results break D-002's promise in spirit; the IMS
   Act and baby food (docs/BABY_FOOD.md) and the DPDP Act's rules on children's data are risks with an ad network; an
   ad before a scan is the friction Sushil asked to avoid. Ads stay out unless a new decision says otherwise.
6. **D-053 changes:** "scans stay uncapped and free forever" becomes "barcode lookups stay free forever; photo scans
   have a daily limit"; its price question is answered as Rs 51 a month.
7. **The conflict-of-interest page (D-138)** follows: "Looking up a pack stays free. Photo scans have a daily limit."
   in place of "Scanning stays free", and "no ads".

- **Accepted by Sushil 2026-10-01:** "Choose the beta limit: 15 products ... D-148 accepted".

Build order: the beta limit (small, on the `beta-limit` branch with D-137); the Play wrap and closed testing
(Sushil's Play Console steps plus a Bubblewrap build); Pro, Play billing and
Google sign-in only after the beta.

**Built (2026-10-01, branch `beta-limit`, web-32, no migration).** `ratelimit.PHOTO_SCANS_A_DAY = 15` per install, a
rolling 24 hours (the old 20-in-10-minutes rule could never bite under it and is gone); barcode lookups' budget and the
IP rules unchanged (400 a day per address is about 26 installs at their full 15 behind one carrier address, and still
holds someone rotating install ids to about Rs 240 a day). The window stays rolling, so the screen says when the next
photo scan is free ("about N hours") rather than "tomorrow", which a rolling window can't promise. Only a refusal by
the install's daily rule gets the screen (`lenses/screen.py` `photo_limit()`, in the 429's `photo_limit`); an IP
refusal keeps D-095's words. The 429 is logged with its request id and not stored (D-095). The app shows the screen
in place of "That didn't work", with "Scan a barcode" back to the scanner. `tests/test_photo_limit.py`.

### D-150 · The explainer film on the website home and the app home `SUPERSEDED by D-151` (2026-10-01)
**Sushil, 2026-10-01: "website home page and android apps home page".** The 41 s film
(`videos/insidelabel-how-it-reads/`, D-004's "AI reads, rules decide" shown on a phone) is served as static files
from `web/film/`: H.264 and AAC, 1920 x 1080 for the website (2.9 MB) and 1080 x 1920 for the app (3.1 MB), each
with a WebP poster (24 KB, 20 KB). Its words are on screen, so it works muted. The details, Claude's, waiting on
Sushil's "accepted":
- **Website (`/`):** the 16:9 film under the opening lines, before "How it works"; it plays muted once it is
  scrolled into view and the page has loaded, and pauses when it leaves; never by itself with reduced motion,
  with Save-Data, or without IntersectionObserver: then the poster and the player's play button wait for a tap.
- **App (`/app/`):** a "How it works" card with the poster directly under "Scan a pack", which stays first, shown
  to everyone. It never plays by itself; a tap opens the 9:16 film full screen with sound and a close button; the
  phone's Back and Escape close it too. With reduced motion the tap opens it paused, on the poster.
- **Loading:** `preload="none"` everywhere; the service worker never precaches it and leaves any `.mp4` alone
  (fetched in byte ranges, which phones need); the poster may be cached after it is shown.
- **The film's line "The first read of a pack takes about 8 to 15 seconds"** is the app's own waiting text
  (`web/app.js`); if the scan-speed query (OPERATIONS.md section 5) says otherwise, both change together.
`tests/test_film.py`.

### D-151 · The explainer film is on the website home only, as the hero; the app has no film `LOCKED` (2026-10-01); the film as the hero `SUPERSEDED by D-185` (2026-10-08): an animated phone is the hero, the film one tap away lower on the page
**Accepted by Sushil 2026-10-02 ("accepted")**, the details below included, with one change the same day: the
caption under the film is "How InsideLabel checks a label, in 41 seconds." (Sushil: remove "No sound: the words
are on screen.").
**Sushil, 2026-10-01: "not liked it, keep only web page website on desktop and mobile version video".** Supersedes
D-150. The app (`/app/`) has no film: the "How it works" card and its player are gone and home is back to "Scan a
pack" first with nothing added (web-35). The website home (`/`) shows the film as its hero. The details, Claude's,
waiting on Sushil's "accepted":
- **One cut per screen, one download:** phones and portrait screens (`(max-width: 767px), (orientation:
  portrait)`) get the 9:16 cut, landscape screens the 16:9 cut. One rule, written three times that must agree
  (`tests/test_film.py`): the still (`<picture>`), the CSS (the box's aspect ratio) and the inline script, which
  sets the video's src after the page's load event. Rotating afterwards keeps the file already chosen.
- **The files:** silent hero copies (the words are on screen), H.264 High, fast start: `web/film/hero-16x9.mp4`
  1280 x 720 (1.29 MB) and `hero-9x16.mp4` 720 x 1280 (1.44 MB), WebP stills (24 KB, 19 KB). D-150's files with
  sound are deleted. The render and encode steps live in one place, the film's README ("On the homes").
- **Playing:** muted, looped, while at least half of it is in view; it pauses out of view and resumes when back,
  unless the visitor paused it. Never by itself with reduced motion, with Save-Data or without
  IntersectionObserver: the still waits with a play button in the middle.
- **Pausable (WCAG 2.2.2):** a 48 px play/pause button on the film, a real button, labelled "Pause the film" or
  "Play the film", reachable by keyboard.
- **Layout:** the heading, the lead and "Open the app" sit beside the film on landscape screens and above it on
  phones; the film never covers them. The box is sized before anything loads (CLS 0). Light and dark.
- **Service worker:** it never caches an `.mp4` (the website isn't in its scope; the rule stays as a guard).
- **The film's line "The first read of a pack takes about 8 to 15 seconds"** stays tied to the app's waiting text
  (`web/app.js`) and the scan-speed query (OPERATIONS.md section 5), as in D-150.
`tests/test_film.py`.

### D-152 · One centred italic wordmark everywhere; the app's links behind a profile menu; "Scan here" first; the website's desktop layout `LOCKED` (2026-10-02); its app-header and menu parts `SUPERSEDED by D-176` (2026-10-08); its website header part `SUPERSEDED by D-179` (2026-10-08)
**Accepted by Sushil 2026-10-02 ("accepted" for D-152)**, the details below included; built and merged in #91.
**Sushil, 2026-10-02:** "italic name for brand name everywhere and logo and brand name each page in center"; "In
the app's header, right corner we will keep user profile icon, once click that the links (Compare, Household
etc)"; from a marked-up screenshot of another company's app, the logo in the centre and one wide bar on the home
that says "Scan here" (only the pattern taken; its colours, words and layout not); and for the website "lots of
space right, left side of the webpage desktop version please adjust", "mobile version is perfect". The details,
Claude's, waiting on Sushil's "accepted":
- **The wordmark:** the logo and "InsideLabel" in a true italic, centred at the top of every website page and app
  screen. Bricolage Grotesque (the display face) has no italic, so the name is drawn from DM Sans ExtraBold Italic
  (OFL, the app's own text family). It is one inline SVG (4.4 KB, `role="img"`, named "InsideLabel", light and
  dark ink) made by `tools/make_wordmark.py` and written into each page; not a web font (a 1.4 KB subset plus its
  stylesheet, and then an SVG file, each cost the website's mobile LCP an extra request in Lighthouse). In running
  text the name stays plain. Not changed now: the app icon and launcher icons, the Play listing, the explainer
  film, the reviewer screen.
- **The app header** (phone and desktop the same): the wordmark centred; on the left a back button only where a
  screen had one (a result's own page: "Back to the result" moved there from the page); on the right a person icon
  drawn for the app (never a photo, a name or initials: D-074), 48 x 48, labelled "Menu".
- **The menu:** a modal dialog, a sheet from the bottom on phones and a panel under the icon from 600 px: Household,
  Compare (with its count), then Your data, Send feedback, Report a problem, Privacy. Every header and footer link;
  the footer keeps its links too. Focus moves in and back; Escape, a tap outside, a choice or the phone's Back close
  it. No tap is added to the scan flow; D-146's digit check is unchanged.
- **Home:** "Scan here" (no test pinned "Scan a pack") is the first thing under the header and opens what "Scan a
  pack" opened; the "what's new" notes moved from above it to below it; the rest keeps its order.
- **The website on desktop** (1024 px and up, a step at 1440 px): one container, 1200 px (1280 px), on the same
  edges for every section; the hero in two columns (text about 4.5/12, film about 7.5/12, so the film is larger
  than before at every width); "How it works" three equal cards across; "What it is, and isn't" in two columns.
  The rules sit in the home page's own `<style media="(min-width: 1024px)">`, so phones never load them: below
  the header, every website page on a 390 or 360 px phone is pixel-identical to before.
`tests/test_site_desktop.py`.

### D-153 · The redesign: one design system for the website and the app; the website home rebuilt as "Merged"; the app's photo ask and result fixed where a tester got stuck `LOCKED` (2026-10-02); its serif and mono faces `SUPERSEDED by D-185` (2026-10-08)
**Accepted by Sushil 2026-10-02 ("accepted")**, after a five-round interview with Claude and four mockup directions
on one canvas (https://claude.ai/artifact/2rmu9zKpTyATZwibpcK1fF; row D is the one accepted, rows A to C are kept for
reference). Not built yet.

**Why.** Sushil set InsideLabel next to Truthin's website (his screen recording, 2026-10-02) and ours looked
unfinished. What Truthin does that we didn't: it *shows* the product (phone mockups of real screens, short headlines,
numbered steps with a picture each) instead of describing it. Not taken from it: a single rating, "Good to go",
"healthier", stock photos of families, its purple. Its proof section is download counts and press; we have neither
yet, so ours is what we already keep: the source of every finding (D-046, D-086), shown next to the finding.

**What a tester hit** (Sushil, 2026-10-02; seen, not guessed): after the barcode, "photograph the back" didn't say which
panel (nutrition table, ingredients, FSSAI licence), how many photos, or why; a refused photo meant starting again.
The result was too long, too many cards, nothing said what it meant for her child, and with only warnings and nothing
to say "yes" to, she couldn't tell what to buy. The app today can ask for the ingredients, the front and the nutrition
table, and some buttons say "Photograph the back" (`web/app.js`).

- **Scope and order:** one design system (tokens, type, components) for the website and the app, built first; then
  the app's photo ask and result; then the website home. English only. No deadline: right over fast.
- **Look:** today's palette (D-110) kept. Big headlines, the hero, the CTA band and the app's per-person lines in
  Bricolage Grotesque; section headings, the pack name and the founder note in a serif (Source Serif 4); text in
  DM Sans; INS numbers and sources in a monospace (IBM Plex Mono). All OFL, self-hosted, only the weights used
  (D-110); D-152's Lighthouse numbers are the bar. Dark mode keeps following the phone.
- **Website home, top to bottom:** a deep-blue hero ("Read the label for your kids.", the D-151 film inside a phone
  mockup, three cards that rise out of it, each with a citation number); How it works (three numbered steps); one
  real pack from the gold set with the **brand hidden** and a Finding / For / Source table (a named brand's result as
  marketing reads as judging that brand, D-042); Method (four statements, linking to `/how`); In preparation ("Ask
  about this pack", Pro, D-113; other packs without the things on your avoid list, free, D-058/D-059); the founder
  note; the CTA. Designed now, built later: public pages per additive and per product.
- **App, photo ask:** one screen, "Photograph the ingredients list", "1 photo", why it's needed (the barcode isn't in
  our checked list yet), a drawing of a pack's back with the ingredients block marked and the nutrition table and
  licence marked "not needed", and frame and light hints. "Photograph the back" goes from every button. Refusals keep
  `screen.py`'s specific reasons. Where another decision needs a second photo before the first answer, the build
  says so and asks Sushil rather than dropping it.
- **App, result:** the per-person lines first (D-060, D-064) and the only red on the screen; everything else folded
  under "Worth knowing (n)", each line with its source (`fssai_basis` and `verified_on`, or where on the label it was
  read); the screen ends with "Scan the next pack to compare" (D-057), then places kept for alternatives and "Ask
  about this pack". The words stay in `lenses/screen.py` (D-091) and pass the wording lint.
- **Motion:** CSS only, no library (D-090), off under `prefers-reduced-motion`. The motion-graphics toolkit Sushil
  shared was a reference, not a dependency.
- **The founder note**, Sushil's words, as given:
  > I'm Sushil Behera, and I have a young son. When he visits the neighbours, someone always hands him a biscuit, a
  > chocolate or a packet of chips. Kind people, kind gestures. But each time I turned the pack over, I couldn't tell
  > what he was actually eating: the ingredient list was tiny, full of codes like INS 322 and 150d, and nothing on the
  > pack explained them.
  >
  > I've worked with data for years, so I built the tool I wanted: scan the pack and see what's in it, in plain words,
  > starting with anything on your family's avoid list.
  >
  > InsideLabel is paid for from my own money. No food company pays us, and none can change what we show. I read every
  > reported mistake myself.

  It states who pays and that no food company does, which is D-138's ground: it goes on the site together with
  D-138's "approved", not before (approved 2026-10-02; it is on `/about` now, and moves to the home page with the
  rebuild). "I read every reported mistake myself" is a promise: D-117 already keeps users' "Report a mistake" with
  people, never the agents.

**Checks when built:** `tests/test_web.py`, `tests/test_wording.py`, `tests/test_no_dashes.py`,
`tests/test_site_desktop.py`; a headless-Chromium walk at 390, 360 and 1280 px in light and dark with screenshots for
Sushil before merge; Lighthouse against D-152's numbers; `APP_VERSION` and the `sw.js` cache version bumped.
- **Built, step 1 of 3: the design system (2026-10-02, web-38).** Tokens, faces and components in one block shared
  by `web/app.css` and `web/site/site.css`, held together by `tests/test_design_system.py`; reference sheet
  `web/design.html`; written up in `docs/APP_DESIGN.md` 8.9. No screen uses it yet, so nothing a user sees changes.
- **Built, step 2 of 3: the app's photo ask and result (2026-10-02, web-39).** Photo ask: a deep panel with "Photograph
  the ingredients list", "New pack · 1 photo" (or "1 photo" without a barcode) and why; a drawing of a pack's back with
  the ingredients block marked "This one" and the nutrition table and FSSAI licence "Not needed"; frame and light
  hints; D-119's parts, D-104's checks and D-100's front unchanged, the front now headed "Optional". "Photograph the
  back" is gone from every button. Result: a deep panel with the pack's name (now the h1, so focus starts there) and
  the person lines (red only for "contains" and "may contain"); the headline in serif; then, closed, "Worth knowing
  (n)": each tile a numbered note with its first source, opening its page (D-134), then the three answers (D-123) and
  the ring (D-127). **One exception, Claude's call:** a tile for an additive not permitted in India stays open above
  the fold, since D-111 makes it the most serious thing the app says. The result ends on "Holding another pack? Scan
  it to compare" (adds the pack to Compare and opens the scanner, D-057), "Compare (n)" once two are waiting, and two
  "In preparation" lines (alternatives, D-058/D-059; Ask, Pro, D-113). Server text is unchanged (D-091).
- **Built, step 3 of 3: the website home (2026-10-03).** `/` in row D's order: a deep-blue hero ("Read the label for
  your kids.", "Open the app", the invite line), How it works (three ruled steps), one real pack with the brand hidden
  and a Finding / For / Source table, How we check (four statements, "69 additives" tied to `data/additives.json` by a
  test), In preparation (Ask, Pro; alternatives, free), Sushil's note and photo (the same words as `/about`, by test),
  and a deep closing band. **The film, Claude's call:** D-151's rule stays (9:16 on phones and portrait screens, 16:9
  on landscape ones) and so does D-152's larger desktop film, so the film sits in a phone-like frame on phones and a
  screen-like frame on laptops, rather than in a phone at every width as in the mockup (a phone frame would have
  needed the 9:16 cut on desktops, a smaller film and D-151 reversed). The three example cards rise over the frame's
  bottom edge on desktops and sit under it on phones; they never cover the film's own words. Below the first screen,
  sections use `content-visibility: auto`. **Measured** (Lighthouse mobile, median of 5, behind gzip as Caddy serves
  it): real throttling LCP 1619 to 1614 ms, CLS 0.039 to 0.011; simulated throttling LCP 1368 to 1532 ms (the
  simulation charges the bigger page's style and layout; a real slowed browser shows no difference). `tests/test_site_home.py`.
- **The photo ask, changed by Sushil 2026-10-03:** "everywhere ingredients and Nutrition label we need for food
  items". Step 2's ask had marked the nutrition table "Not needed"; D-133 reads it from the same back photos. The app
  now asks "Photograph the ingredients and the nutrition table" ("1 or 2 photos": one if both fit, the table as a
  second photo if not, through D-119's parts); the drawing marks both, only the licence "Not needed"; the food
  result's re-check button, the photo check's tick (server) and the website's step 2 say the same. D-133's offer to
  add the table afterwards stays, for when it was missed. web-41.
- **The film, redone for the redesign (Sushil 2026-10-03: "what about the video on home page, need to change it as
  well").** Same story, timings and music (D-151); its app screens now follow D-153: the header's wordmark and profile
  icon (D-152), the photo of the ingredients and the nutrition table ("Ingredients and table." in place of "One
  photo."), the deep result panel with the person line, the not-permitted tile, "Worth knowing (2)" and "Holding another
  pack? Scan it to compare", the tile page's back button in the header, the partial read on the deep panel, and the
  close "Read the label for your family.". Both cuts re-rendered (HyperFrames check: 0 errors, contrast 37/37); the
  site's copies get new names, `web/film/hero2-16x9.mp4` (1.34 MB) and `hero2-9x16.mp4` (1.52 MB), so no browser keeps
  the old film; the `hero-*` files are deleted. D-151's one-cut-per-screen rule is unchanged. The word sources are in
  the film's BRIEF.md.
- **The hero's headline, changed by Sushil 2026-10-03:** "Read the label for your family." in place of "...for your
  kids." ("it's not true for your kids part": the profiles are you and the people you shop for, not only children).

### D-154 · The slow-scan line names no cause `LOCKED` (2026-10-02)
**Number:** first recorded as D-153 on `main` (#94). The merge of #95, which used D-153 for the redesign, kept that
entry and dropped this one; restored here word for word under the next free number (2026-10-02). Sushil's "D-153
accepted" below refers to this entry; the code and tests that cited "D-153" for it now cite D-154.
Amends one line of D-124. Recommended by Claude; Sushil asked for the fix (2026-10-02: "Yes, make the step 4 fix"). **Accepted by Sushil 2026-10-02** ("D-153 accepted"). App only (web-37); no server or cost change.
Why: D-124's line after 20 s was "Taking longer than usual: the reader is busy right now. It is still working." When Cloud Vision refuses (code 8, 2026-10-01) the scan uses the fallback reader; nothing is busy, and the app can't see the cause anyway. The scan-speed brief (step 4) asked that the waiting words stay true.
- **After 20 s:** "Taking longer than usual. It is still working." The rest of D-124's wait screen is unchanged, and so is "The first read of a pack takes about 8 to 15 seconds" (D-150).
- A Vision outage reaches Sushil as a `server` problem report (#87), never as words to the user.
- **The 503 words** (same commit as the acceptance's follow-up, 2026-10-02): "The label reader is busy right now. Try again in a minute." became "Something on our side isn't working right now. Try again in a minute." Every 503 the server sends means the database is unavailable (`storage_unavailable`); the reader is never what failed.
`tests/test_web.py::test_slow_scan_words_name_no_cause`.

### D-155 · The site stops promising "No ads": ads may come after the beta `LOCKED` (2026-10-03)
**Direction from Sushil, 2026-10-03:** "under Money and brands remove No ads. as we have plan for it". Supersedes D-148
point 5's "Ads stay out unless a new decision says otherwise" and point 7's "no ads" on the conflict-of-interest page.
D-148 point 2 stands: no ads during the beta (`docs/PLAY_RELEASE.md` still answers Play's ads question "No").
**What "ads" means, Sushil 2026-10-03:** "in app we give different ads to get money if you are not a paid user": ads
from an ad network for free users, none for Pro (D-148 point 4).
- `/about`, "Money and brands": "No ads." is removed. The policy on that page promises that a change "is dated on this
  page before it takes effect", so the page now says so: "Changed 3 October 2026: the line "No ads." is removed,
  because ads may come later. Before any ad appears, this page will say where it goes and who may advertise, dated
  before it takes effect."
- **Not decided yet, needed before any ad ships (Claude):** who may advertise and where ads go. Also, with an ad
  network: D-090 (no third-party JavaScript) and D-110 (no visitor IP sent to Google for a font) would both need a new
  decision, since an ad network's script runs in the app; the privacy page, the DPDP data map and Play's ads and
  Data safety answers change; and ads stay out of the result's people block and its findings (D-060, D-091). The same page still
  says "No brand can pay us, and nothing a brand does changes what InsideLabel shows", the founder note says "No food
  company pays us", and D-002 forbids paid influence on results: an ad from a food company would contradict all three.
  D-148 point 5's other cautions stand as questions for that decision: what a web ad earns against a scan's cost, the
  IMS Act and baby food (docs/BABY_FOOD.md), the DPDP Act's rules on children's data with an ad network, and an ad
  before a scan.


### D-156 · InsideLabel will read more than food labels; the conflict-of-interest "ties" line covers skin care and personal care `LOCKED` (2026-10-03)
**Direction from Sushil, 2026-10-03:** "we are not focusing only food packet, will expand to other sector like skin
care and personal care where is label we will reach." The product's scope will grow beyond packaged food. Nothing is
built for it yet: the engine, the tables and every check stay food-only (FSSAI basis, D-086) until a decision on
each new sector's primary documents (D-046).
- `/about`, "Money and brands": "Ties to the food industry: none ... in the food industry." becomes "Ties to the
  industries whose labels we read: none. No job, shares, advisory role or family business in food, skin care or
  personal care." The page's own rule dates the change: a "Changes to this policy" list now holds this and D-155's.
- **To confirm (Claude):** the "none" for skin care and personal care is Sushil's to state; the line was written from
  this direction, and is to be corrected if any tie exists.
- **Confirmed by Sushil, 2026-10-03:** "no ties in skin care or personal care".
- **Left as Sushil wrote it:** his note says "No food company pays us" (D-153, on `/` and `/about`). It stays true; a
  wider "No company whose labels we read pays us" is his choice to make.
- **Changed by Sushil, 2026-10-03:** "change note to No company whose labels we read pays us". His note on `/` and
  `/about` now says "No company whose labels we read pays us, and none can change what we show." (D-153 quotes the
  first wording.)

### D-157 · The D-118 check ignores date stamps and words cut at an overlap `LOCKED` (2026-10-04)
Refines D-118 (and the D-117 review checker, which shares `review/checker.py`'s `independent_read`).
Recommended by Sushil and the advisor from problem report #5; built by Claude. **Accepted by Sushil 2026-10-04.**
Why: a new pack (8901058009439, Nestle Choco Coated Wafer) was refused twice with "One clearer photo, please."
(`independent_read_failed`) though Gemini read the list right both times; the tester spent about 9 minutes before
"Use this one anyway". Cloud Vision was working. MISSING was empty; LOST held words that aren't ingredients:
- scan 8c46004c: `apr`, `aug`, from the date stamp "AUG/26-APR" printed across the ingredient panel;
- scan 8bd1c116 (the back in 3 parts): `augt` (the same stamp misread), `frac`, `leci`, `ing`, `dient` (words cut
  where the parts overlap, read twice by Cloud Vision), `choce` (a cut, misread "Choco") and `water` (wrapper text in
  the overlap).

What changes, in LOST only (MISSING is as before), on every scan:
- **Stamps:** a month (jan to dec, "sept") or a stamp word (mfd, mfg, exp, best, before, batch, lot) never counts,
  as a whole word only ("marjoram", "mayonnaise" and "sausage" are untouched). A close misread of a month ("augt")
  counts as a stamp only next to a digit or "/" or alone on its line, so a word like "mayo" in running text still
  counts. The list lives in `checker.py` beside `_NOT_INGREDIENTS` (a parser rule); past a handful it moves to
  `data/`.
- **Cut words:** a word that is the start (3 letters or more) of a word in the given list, or a start or end piece of
  "ingredients", doesn't count. A cut word that starts no word of the list still counts.
- **Strict otherwise:** a whole ingredient word Cloud Vision read that Gemini's list lacks still refuses (D-118's
  purpose); `tests/test_checker_stamps_and_cuts.py` holds a dropped "salt".

Result on report #5: scan 8c46004c is confirmed; scan 8bd1c116 still asks, on `choce` and `water`.
- **Open question for Sushil:** a single stray whole word (here "water", wrapper text caught in an overlap) can still
  trip the gate, and so can a cut word that is also misread ("choce": not the start of any listed word, since the
  list has no "choco"). Widening either (for example, letting one stray word through on a multi-part back, or
  matching a cut word against the whole of Cloud Vision's text outside the list) is his call, not done here.
`tests/test_checker_stamps_and_cuts.py`.

### D-158 · A cut word only at a line's start or end, and never an allergen or an ingredient name `LOCKED` (2026-10-04)
Refines D-157. Found in the advisor's review after #106 merged; built by Claude. **Accepted by Sushil 2026-10-04.**
Why: D-157 took any lost word that starts a word of Gemini's list as a cut word, so a dropped ingredient beside a
longer one went through the D-118 gate. Measured on `main` 14c2fc6 with `independent_read()`: "Sugar, Nutmeg, Nut,
Salt" lost nothing (was `nut`); "Eggless mix, Egg" lost nothing (was `egg`); "Cornflour, Corn" lost nothing (was
`corn`). The gate exists to catch Gemini dropping an ingredient, and allergens come first (D-060).

What changes, in `review/checker.py` `_cut()` only:
- **Where:** a word counts as cut only when it is the first or last word of a line of Cloud Vision's text, where an
  overlap of the back's parts or the photo's edge cuts it. In report #5 every cut word sits there ("...vegetable fats,
  Frac", "...(Soya leci", "ING" alone, "Choce DIENT'S"), so both scans keep their D-157 result: 8c46004c confirmed,
  8bd1c116 lost `choce` and `water`.
- **Never cut:** every word of an allergen's aliases and statement words in `data/allergens.json` (read from the table:
  "egg", "wheat", "milk", "soy", "peanut", and "nut" from "pine nut" and "brazil nut", since the table has no "nut"
  alias of its own); and the one-word names in `normalization.json` `synonyms` ("salt", "msg", "vanaspati" and the
  like). The synonyms were added because the engine itself reads them as ingredients, and none of report #5's cut
  words is one of them; multi-word synonym entries were left out, since their words ("yellow", "colour") are too
  general.
- **Open question for Sushil:** a plain word at a line's start or end that starts a longer listed word, and is neither
  an allergen word nor a synonym, is still taken as cut ("Cornflour, Salt, Corn" at a line's end loses nothing). A
  test pins it. Narrowing further (for example, only on a back sent in parts) is his call.
`tests/test_checker_stamps_and_cuts.py`.

### D-159 · /scan asks for a clearer photo only when a lost word could change the result `LOCKED` (2026-10-04)
Refines D-118, D-157 and D-158. Proposed by the advisor in review; **accepted by Sushil 2026-10-04**; built by Claude.
Sushil's rule: at most one quick check per scan, and only when it matters.
Why: problem report #5 (Nestle Choco Coated Wafer, 8901058009439, the back in 3 parts). After D-157 and D-158,
`independent_read()` still lost `choce` and `water` on scan 8bd1c116, so the tester was asked "One clearer photo,
please." for two words that change nothing they would see ("water" is wrapper text from an overlap, "choce" a cut,
misread "Choco"), and spent about 9 minutes before "Use this one anyway". The gate protects the user's result now;
the catalogue is protected separately: every new pack goes to review, and the D-117 checker's `nothing_lost` sends a
person "in Cloud Vision's ingredient list but not in the draft: choce, water".

What changes, in `api/main.py`'s D-118 gate only:
- No list in Cloud Vision's text, or words of Gemini's list it never saw (MISSING): still asks, as before.
- Words only Cloud Vision read (LOST): asks only when `lost_words_matter()` says they change the result. It runs the
  scan's own rules (D-004) on Gemini's list, and on the list with the lost words added as one more ingredient, and
  compares: every allergen code's state (`allergens.json`), the engine's verdict (additives, sugar names,
  sweeteners, NOVA markers, band), the ingredient notes, the household lines for each age band and the baby lines.
  No word list in code. It sits beside the gate, not in `review/checker.py`: it is /scan's question, and the D-117
  checker stays word-for-word strict. About 150 ms, only on a scan whose LOST isn't empty.
- Recorded with the back's Cloud Vision read (`scans.ocr`, `back.independent_read`: section found, missing, lost,
  asked), so `tools/repro.py show` prints it (D-092). No migration; the user's screen doesn't change.
- `independent_read()`, `independent_read_confirmed()` and the D-117 `nothing_lost` check are unchanged.

| Lost word, on report #5's list | Changes | Asks |
|---|---|---|
| `choce`, `water` (scan 8bd1c116) | nothing | no |
| `milk` (on the list without "Milk solids" and its statement) | the milk allergen | yes |
| `sucralose` | an additive finding | yes |
| `glucose` | the sugar names | yes |
| `rice`, `water` | nothing | no |

Report #5's own list already has "Milk solids" and says milk in its statement, so a lost "milk" there changes nothing
and doesn't ask: the rules decide, not the word. `tests/test_lost_words_gate.py`.

### D-160 · The lost-words check reads lost INS numbers, each lost word on its own, and asks on its own failure `LOCKED` (2026-10-05)
Refines D-159. Proposed by the advisor in review of D-159; **accepted by Sushil 2026-10-05**; built by Claude.
Why: D-159's `lost_words_matter()` could let a dropped additive or allergen through the D-118 gate.

**Bug 1, lost INS numbers.** LOST holds words only, so an additive Gemini dropped shows only as its class word, which
alone changes nothing. Measured on `lost_words_matter()` with the list "Wheat flour, Sugar, Edible vegetable oil
(palm), Cocoa solids, Salt" and Cloud Vision's "INGREDIENTS: ..., Cocoa solids, <X>, Salt.":

| <X> (dropped by Gemini) | LOST | D-159 asked | D-160 asks |
|---|---|---|---|
| Preservative (211) | preservative | no | yes |
| Antioxidant (319) | antioxidant | no | yes |
| Acidity regulator (INS 330) | acidity, ins, regulator | no | yes |
| Raising agents (500(ii), 503(ii)) | agents, raising | no | yes |
| Colour (150d) | colour | yes | yes |

**Bug 2, a joined phrase.** The sorted lost words joined can form an `exclude` phrase of `allergens.json`. With the same
list and "..., Sugar, Coconut, Milk solids, ...", LOST is `coconut`, `milk`; joined, "coconut milk" is in milk's
exclude list, so milk wasn't flagged and the gate didn't ask. "egg free" forms the same way.

| Lost words | Joined | D-159 asked | D-160 asks |
|---|---|---|---|
| coconut, milk | coconut milk (milk's exclude) | no | yes |
| egg, free | egg free (egg's exclude) | no | yes |
| choce, water (report #5, scan 8bd1c116) | choce water | no | no |

**Bug 3.** No error handling: an exception in the rules would have cost the user their result.

What changes (`api/main.py`'s `lost_words_matter()` and its call at the gate; `review/checker.py` gains
`lost_ins_numbers()`; `independent_read()`, `independent_read_confirmed()` and the D-117 checker are unchanged):
- **Numbers:** `lost_ins_numbers()` gives the INS numbers in Cloud Vision's ingredient section (the one
  `independent_read()` reads) that the list doesn't have, read with `core/tokenize.ins_numbers` only (D-099). It sits
  in the checker because the section is defined there, and it leaves `independent_read()` as it is. The numbers go to
  the rules as "INS n" entries, so the rules decide: a misread that is no additive ("INS 987") changes nothing and
  doesn't ask (pinned by a test); a bare "(987)" isn't read as a number at all.
- **Words:** one run of the rules on the list with each lost word as its own entry, the words joined as one more
  entry ("corn syrup" still reads as one name), and the numbers. One run holds them all: the allergen check strips
  `exclude` phrases entry by entry, and the engine's findings only add up. Two runs in all (the list, and the list
  with what was lost); about 170 ms on report #5, only on a scan where something was lost.
- **Errors:** any exception logs (`log.exception`) and asks, as before D-159; the record says `"error": true`.
- **Record:** `scans.ocr` `back.independent_read` adds `lost_ins` (and `error`); `tools/repro.py show` prints it.
- **At the gate, the list after D-093's recovery.** Measured in a scan, D-093's cross-check reads the same Cloud Vision
  text first and puts an omitted additive back in the list, so rows 1, 2, 3 and 5 of the first table are recovered
  and the result shows the additive: those scans go through, complete, as they should. Row 4 is the one that reached
  a user: the cross-check recovers "Raising agents (500(ii)" and "(503)", which the engine can't read, so 500 and 503
  were missing from the result while its caveat said "Recovered and included in the verdict", and the recovered words
  confirmed the read. D-160 counts a number as lost when the list as it stands doesn't yield it to the parser, and
  checks lost numbers even when no word is lost, so this scan now asks.
- **Open, for Sushil:** D-093's recovery itself (`ocr_check.recover_from()`) cuts an entry at a nested bracket; a fix
  there would put 500 and 503 in the result instead of asking. Not changed here.
`tests/test_lost_words_gate.py`.

### D-161 · The reviewer screen and the Play feature graphic take the wordmark `LOCKED` (2026-10-05)
Refines D-152, which listed the reviewer screen and the Play listing under "Not changed now". **Decided by Sushil
2026-10-05:** "Add the wordmark" (the reviewer screen) and "Play feature graphic yes". Built by Claude.
- **The header** (`review/templates/base.html`; the queue and item pages extend it, and no other reviewer page renders
  HTML: sign-in is the browser's own dialog, errors are JSON): the D-152 wordmark, then the plain word "review" (muted,
  normal weight), one link to `/review` named "InsideLabel review". The row stays as it was, left-aligned for a work
  tool, "Signed in as" on the right; the wordmark is drawn 22 px high, the text line's height, so the header goes from
  42.75 to 43 px (no layout jump).
- **One definition:** `tools/make_wordmark.py` writes the block into `base.html` between the markers, as it does for
  the app and the website; regenerating left the other five pages byte for byte the same. The template wraps the block
  in `{% raw %}` ... `{% endraw %}`, outside the markers, so Jinja never reads the SVG's braces. No font and no image
  request.
- **Colours:** the wordmark's own light and dark ink follow `prefers-color-scheme`, as the reviewer page does: 9.2:1 on
  the light panel (#244b6b on #ffffff) and 14.6:1 on the dark one (#e0f2f6 on #1a1d23). No change needed.
- **The Play feature graphic** (`android/feature_graphic.png`): 1024 x 500, the wordmark in its light ink centred on
  the app's cream (#FBF9EE), 676 x 135 px (66% of the width, readable when Play shows it small); nothing else. A
  24-bit PNG with no alpha (Play's rule), flattened onto the cream. Drawn by `python tools/make_wordmark.py
  --feature-graphic` from the same definition (rasterised with cairosvg, dev only), so it changes when the wordmark
  does. Sushil uploads it in Play Console (Grow > Store presence > Main store listing > Graphics); a listing change
  goes to Google's review again (`docs/PLAY_RELEASE.md`, section 6).
- **Unchanged:** the app icon (no name on it); the explainer film already shows the wordmark (D-153).
`tests/test_site_desktop.py` (the same copy on every page, GET /review shows it, and the graphic's size, mode and
cream corners).
- **Corrected by Sushil, 2026-10-05 (after #111 merged):** drop the feature graphic part. The feature graphic live on
  Play already carries the italic wordmark: the logo and italic "InsideLabel" on cream, with "Read the label for your
  family." under it (Sushil checked the Console). It already matches D-152 and needs no change. So
  `android/feature_graphic.png`, `make_wordmark.py --feature-graphic` and its test are removed; the graphic is kept in
  Play Console, not in the repo (`docs/PLAY_RELEASE.md`, section 6). The reviewer screen's wordmark stands as built.

### D-162 · No invite code: the Play closed test decides who installs, the limits cap the cost `LOCKED` (2026-10-06)
Supersedes D-102's invite-code part (and D-148's "invite codes stay"). **Decided by Sushil 2026-10-06:** "it should
redirect to android app not asking any beta", then, of three options, "No codes anywhere". Built by Claude.
Why: testers already opt in through Play's closed test (the Google Group, the opt-in link), so a second code is
friction for nothing (Sushil's rule: at most one quick check, D-146). The cost stays capped by what exists: 15 photo
scans per install per rolling 24 h (D-148) and per IP 60 per 10 minutes and 400 a day (D-095, about Rs 240 a day for
someone rotating install ids).

Not chosen: "the Play app skips the code, the website keeps it" (the app is the website in Chrome, so the server can
only take the app's word for it; fakeable for the same capped cost) and "keep codes for everyone" (strongest control,
one tap with the join link).

What changes:
- **The server:** `INSIDELABEL_INVITE_ONLY=off` (`deploy/settings.env.example`; Sushil sets it in
  `/etc/insidelabel/settings.env`, OPERATIONS.md "Testers"). `/access` then says `invite_only: false` and the app
  treats every phone as joined, so the join screen never shows. "Before you start" (D-105) stays: it is consent.
- **No code removed:** the gate, `tools/beta.py`, the invites tables and `#/join/CODE` keep working, so `on` brings
  D-102 back with one setting. Codes made before D-162 stay with their install until their retention ends.
- **Words:** the website home says "In an early beta. On Android, testers get it through Google Play." instead of
  the invite line; the privacy page says "only if you joined with one" for the invite code; "Delete my data" no
  longer says you'll need your invite link (web-42).
- **Play Console (Sushil):** App access becomes "All functionality is available without special access"; Data
  safety drops Personal info > User IDs (the invite code). Both go to Google's review. `docs/PLAY_RELEASE.md`.
- `tools/release_check.py`'s manual item and `tests/test_deploy.py` expect `off`.

### D-163 · The photo screen asks to keep the barcode in the photo when it's on the same side `LOCKED` (2026-10-06)
Refines D-143. Proposed by the advisor in review; **accepted by Sushil 2026-10-06** ("agree"). Built by Claude.
Why: review item for Saffola Soya Chunks (8901088072236, 2026-10-06). The tester scanned the barcode, confirmed its
digits (D-146) and photographed the ingredients and the front; no photo showed the barcode, so D-143 asked the
reviewer to check it by hand. A machine check isn't available: GS1's "Verified by GS1" site refuses scripted
lookups (403), its API needs a GS1 licence, and it often names only the company.
What changes: on the photo screen (`web/app.js`), when the scan has a barcode, the hints add "Barcode: If it's on
the same side, keep it in the photo too. We check the number against it." D-143 already reads every photo of the
scan (back, parts, front) with zxing-cpp, so a code in any photo is confirmed and the reviewer's box doesn't show.
A hint only: no extra photo, step or screen (Sushil's low-friction rule). web-43. `tests/test_web.py`.

### D-164 · D-093's recovery takes the omitted additive's whole bracket group `LOCKED` (2026-10-07)
Closes D-160's open item. Proposed by the advisor; **accepted by Sushil 2026-10-07** ("yes"). Built by Claude.
Why: `ocr_check.recover_from()` cut an omitted entry at the first ")", so "Raising agents (500(ii), 503(ii))" came
back as "Raising agents (500(ii)" and a bare "(503)". The engine can't read either, so 500 and 503 were missing from
the result while its caveat said "Recovered and included in the verdict"; since D-160 the gate asked for a clearer
photo instead, a request the user needn't have had.
What changes (`extraction/providers/ocr_check.py` only): the entry is the innermost bracket group holding the number,
closed by bracket matching (`core/tokenize._balanced_span`: round, square and curly alike), with the class name before
it. Two missing numbers of one group give one entry. A compound ingredient still gives only the inner group
("emulsifier (322)", not the whole "Compound chocolate (...)" the model kept). A number with no name before it keeps
the bare "(n)" fallback, as before; the D-160 gate still catches it.
| Printed, omitted by the model | Recovered before | Recovered now |
|---|---|---|
| Raising agents (500(ii), 503(ii)) | Raising agents (500(ii), (503) | Raising agents (500(ii), 503(ii)) |
| Humectant [420(ii)] | (420) | Humectant [420(ii)] |
| Mix {Emulsifiers [481(i) & 471]} | (481), (471) | Emulsifiers [481(i) & 471] |
| Preservative (211), Colour (150d) | unchanged | unchanged |
`tests/test_recovery_brackets.py`; `tests/test_lost_words_gate.py` now expects the raising agents scan to go through.


### D-165 · /how says there is no score `LOCKED` (2026-10-07)
Refines D-064's wording on the public page. **Decided by Sushil 2026-10-07.** Built by Claude.
Why: testers, and a future help bot, will ask "what's this pack's score?". D-064 keeps the 0-100 score admin-only, but
the "How we check" page (`web/site/how.html`, `/how`) never said so, and twice said a note or the nutrition table
"doesn't change the score", as if there were one.
- **A new section,** right after the intro, "No score": "InsideLabel doesn't give a pack a score, a grade or stars. One
  number can't say what matters in your family: the same biscuit can be on one person's avoid list and not another's.
  So we show what the label says, person by person, with the source for each line, and you decide."
- **"Ingredients worth knowing"** now ends: "A note is information only: it never changes what we say about your
  avoid list or an additive. Its tile means the headline says "A few things worth knowing" rather than "No concerns
  found"."
- **"Nutrition table"** now ends: "The table is information only, the same way: its tiles can change "No concerns
  found" to "A few things worth knowing". It adds a line only for a child under 2 in your household, when salt or added
  sugar is over that threshold."
- **Checked against the code first:** notes (D-132) and the table (D-133) move no score, band, allergen answer or
  additive finding; `screen._hfss()` only feeds `baby_lines()` (D-140). But under D-123 a note's or the table's tile
  turns a "No concerns found" headline into "A few things worth knowing", so the brief's "doesn't change the headline"
  would have been untrue; Sushil chose (2026-10-07) wording that says what the code does.
`tests/test_web.py` (the word "score" only inside the "No score" section).


### D-166 · A recipe's list is refused as "no ingredient list found" `LOCKED` (2026-10-07)
Proposed by the advisor; **accepted by Sushil 2026-10-07**, including new retake words for this case. Built by Claude.
Why: Saffola Soya Chunks (8901088072236), reviewed 2026-10-06. The tester's back photo was the cooking side, whose "SOYA
MASALA GRAVY RECIPE" box has its own "INGREDIENTS:" heading ("2 cups cooked Saffola Soya Chunks, 3 tsp Oil, ..., 1/4 cup
Curd, fresh, ..., 8 Cashews, whole (Optional)"). That scan read the pack right from a second photo (version 62:
"Defatted Soya"), so it **reached no user**; but a scan with the recipe photo alone could have shown a family "Curd"
(milk) and "Cashews" (tree nut) as the pack's contents and missed the real list.
- **The rule (D-004),** in `reliability/gates.py` beside the empty-list refusal, so every caller of the gate has it:
  a list is a recipe's when at least 3 entries, and at least half of all entries, carry a recipe's marker. Then it is
  refused with the existing `no_ingredient_list_found`, `reason: "recipe"`, a detail naming the count and a hint to
  photograph the pack's own list.
- **The markers are data** (`data/recipe_markers.json`, its own file: `normalization.json` is the tokenizer's alias
  table, this one only the gate's): a measure, a number then a unit (cup, tsp, tbsp, teaspoon, tablespoon, inch,
  clove, pinch: "2 cups", "1/2 tsp", "1-inch", "3 cloves"), or a cooking word at an entry's end ("finely chopped",
  "thinly sliced", "crushed", "to taste", "(optional)", "fresh"). Narrow on purpose: "Cup cake mix", "8 Cashews",
  "Chopped nuts (Cashew 5%)", "Fresh cream", "Tomato paste (28%)" and INS numbers carry none; no g or ml.
- **Measured:** the Saffola recipe, split as the model returns it, has 21 of 26 entries marked (the other 5 are counts
  of whole items, "1 Bay leaf", "8 Cashews"). Every list we hold (6 in `gold/`, 8 in `predictions_archive/`, 13 in
  `tests/fixtures`) has none marked, so the 3-and-half threshold has a wide margin, and one stray measure never
  refuses. The laptop's `predictions/` is checked by the same test where it exists.
- **Retake words** (Sushil chose them; the existing ones point to "the part that starts with "Ingredients"", which the
  recipe box also does): "This looks like a recipe printed on the pack, not its own ingredient list. Look for the
  list that starts with "Ingredients" near the nutrition table, usually on the back or a side, and photograph that."
  (`screen.RETAKE_RECIPE`). The headline and "Send it to us" are as for any `no_ingredient_list_found`.
- **The prompt:** rule 4's "These are NOT ingredients" now names a recipe printed on the pack (its ingredients, method
  or serving suggestion), and says that if the only "Ingredients" heading belongs to a recipe, `ingredients_status`
  is "not_found" with an empty list. **`PROMPT_VERSION` changes** (4efbe2214842 to 01696584efa3): the next paid gold run reads with it (only when
  Sushil says "run the gold set").
- **Trace (D-092):** the refusal goes through `record_failed_scan(..., trace=tr)` with the model's raw answer, like
  every gate refusal, and `tools/repro.py` replays it to the same refusal.
- With it, `/how` quotes the headlines in the app's own words ("No concerns found in the ingredients").
`tests/test_recipe_gate.py`.
- **Added 2026-10-07 (the advisor's queue):** Unicode fractions count as the number of a measure: "½ tsp", "¼ cup",
  "1 ½ cups", "1½ cups" (`gates._MEASURE`). Percentages and INS numbers still never do.


### D-167 · "We haven't checked this pack yet" on the result; a "Light" hint for pouches `LOCKED` (2026-10-07)
**Decided by Sushil 2026-10-07** (the words and when they show; the hint: "yes pls"). Built by Claude.
- **Why the line:** review item 66: a tester used "Report a mistake" to ask why the review screen came up after
  scanning a pack we hadn't seen. Nothing on the result said it was read from their photo and goes to our team.
- **The line** (`screen.UNCHECKED_NOTE`, in the result's catalogue note card): "We haven't checked this pack yet, so
  this result is read from your photo. Our team checks it next, and then the next scan of this barcode is instant,
  for everyone." Shown on every result for a barcode with no checked (published) version yet: the scan that adds it
  and any scan of it before review (`save_scan()` now returns `checked`). Never without a barcode (D-107, its own
  note), from a screen (D-130, its own note), for a pack that isn't food (a supplement, infant food or medicine), for a
  refusal, or for a pack with a checked version (a catalogue hit, a re-read, or a reformulation waiting for review).
- **The hint** (the photo screen, "Light"; Sushil accepted 2026-10-07, "yes pls"), after a tester's glossy, curved
  Kissan Chef Solutions Ketchup pouch with tiny text: "Hold the phone close and steady. On a pouch or a shiny pack, lay
  it on a table, smooth it flat and tilt it away from the light." A hint only, no new step (web-44).
`tests/test_unchecked_note.py`, `tests/test_web.py`.


### D-168 · A published pack without a nutrition table offers one photo of it `LOCKED` (2026-10-07)
Proposed by the advisor; **accepted by Sushil 2026-10-07, with two changes** (below). Built by Claude. Replaces the
D-147 draft ("nutrition-capture"), which was never recorded here: its core, asking for the table before the one read,
is live since D-153 (2026-10-03: the photo screen asks for "the ingredients and the nutrition table, 1 or 2 photos").
Why: label data is gold (D-128), and the D-133 numbers are what D-136 needs. Sushil's server numbers: new versions with
a table were 2 of 6 on 1 to 2 October, 3 of 5 on 4 to 7 October, 2 of 2 on 6 to 7 October. The gap: a pack already
published without a table never got one (a catalogue hit never asked; a table-only photo couldn't go through /scan).
- **The offer:** on a catalogue hit for a food pack with no nutrition table on file and none on its way (no
  `nutrition` item waiting, no pending version carrying one: `store.find_current()` `table_wanted`), the result ends
  with a card (`screen.TABLE_OFFER`): "Add the nutrition table?" / "We have this pack's ingredients but not its
  nutrition table. One photo of the table lets our team add it, so everyone who scans this pack sees its sugar, salt
  and fat beside ICMR-NIN's guide." / "Photograph the nutrition table". Never from a screen (D-130), without a barcode
  (D-107), or for another kind (D-140). An offer, never a gate (D-146's one check stays the only one).
- **The photo** (`/scan` with `table_only`, a barcode and one back photo): the same single read as a scan (about 50 to
  60 paise a photo), counted in D-095's limits and D-148's daily photo limit. Only the table is used, through
  `nutrition.check()` (D-133's second reader and arithmetic); the ingredient list isn't gated, read into the record or
  changed. A checked table makes one pending version, the published content copied plus the table, queued as
  `nutrition` (`store.add_table()`, sharing `save_scan()`'s D-133 insert). Answers (`screen.TABLE_ANSWER`): "Thanks.
  Our team checks the table, then it shows for everyone who scans this pack." / "We couldn't find a nutrition table in
  that photo, so nothing was added." / "We couldn't read every number on that table clearly, so nothing was added." /
  "That photo shows a different barcode, so nothing was added." Every read is stored with its trace (D-092; `repro`
  replays it) and its photo follows D-098.
- **Sushil's changes (2026-10-07):**
  1. "The table photo might be another pack's." The photo view adds "If the barcode is on the same side, keep it in the
     photo." (as D-163). A barcode in the photo must match (D-143's `barcode.confirm()`); another code stores nothing,
     with the "different barcode" line. /review shows the published version's pack photos beside the table photo.
  2. "The card goes at the end of the result, after everything else, never above the allergen lines (D-060), and isn't
     offered again on this phone once it sent a table for this pack." (The server also stops offering once one waits.)
- **/review:** the `nutrition` item labels the table photo and shows the published pack's back and front beside it;
  the "Every number shown to users matches the photo" tick (D-133) and `ReviewService.approve()` are unchanged.
- **Out of scope:** a 4th photo for the table when a list takes 3 parts (rare, Sushil 2026-10-01); the layout and
  accuracy measurement, which waits for the one gold run Sushil approved (about Rs 10 to 15, once the gold set has 20
  labels; asked before any paid call).
`tests/test_table_photo.py`, `tests/test_web.py`.

### D-169 · One symbol and one colour per kind of message `LOCKED` (2026-10-07); its shades, not its meanings, `SUPERSEDED by D-185` (2026-10-08)
A tester's feedback via Sushil, 2026-10-07 ("all", colours and symbols first): a blurry photo was drawn in the same red
as the strongest findings about the food, the retake card in the same amber as "worth knowing", and some messages
leaned on colour alone. A red photo problem makes the pack look bad when only the photo was. **Accepted by Sushil
2026-10-07: "Accept as shown"** (the table below, with light and dark screenshots of each kind). Built by Claude.
Style and markup only: no finding or word changes (D-004, D-091).

| Kind | Symbol (`web/icons.js` `KINDS`) | Colour | For |
|---|---|---|---|
| Photo or app problem | retake arrow (new) | `--problem` (new), grey-blue, never red | blurry, dark, wrong side, no list, network, limits, form errors |
| On your avoid list | cross in a circle | `--stop` | the allergen "contains" / "may contain" lines only |
| Not permitted in India | warning triangle (new) | `--stop` | the `not_permitted` badge, tile, chip and alert |
| Worth a look | ! in a circle | amber, `--unsure` | notes, sugar, worth knowing, couldn't confirm |
| Information | i in a circle (new) | blue, `--calm` | where a result came from, catalogue notes |
| Done | check | green, `--brand` on `--mint` | photo accepted, saved, sent |

- **Names:** each symbol has an accessible name ("Photo problem", "On your avoid list", "Not permitted in India",
  "Worth a look", "Information", "Done"), or is decoration beside words that say the same (the badges and the look
  page's chip). Never colour alone.
- **Contrast (WCAG):** `--problem` text is light #3e5a6e on #e6edf2, 6.88:1 on `--bg`, 7.26:1 on `--surface`, 6.14:1
  on its tint; dark #c6d6e2 on #2e4a60, 9.14:1, 7.26:1 and 6.23:1. Symbols on `--bg` / `--surface`: `--stop` light
  5.3 / 5.6, dark 8.5 / 6.8; `--unsure` light 9.0 / 9.5, dark 10.0 / 7.9; `--calm` light 9.3 / 9.8, dark 11.5 / 9.1;
  `--brand` light 4.69 / 4.95, dark 6.2 / 4.9 (4.1 / 4.0 on `--mint`). `--unsure-line` is only 2.0:1 on the light
  `--bg`, so the worth symbol draws in `--unsure`; `--unsure-line` stays a border colour.
- **The kind comes from the server's fields:** `screen.state`/`retake`, `badge.kind`, the tile's and look page's
  `kind`, the chip's `tone`, `people[].status`, `catalogue_note`, `front_note`, `from_screen`, `since_screen.differs`,
  the photo check's `ok`. One field was added: D-168's table answer carries `kind` ("done" or "problem",
  `screen.TABLE_ANSWER_KIND`). The JS never reads `score` or the words to pick a kind.
- **D-060 unchanged:** the allergen-state tokens and the person lines' classes keep their meanings; the lines gain the
  avoid-list or worth symbol. The legacy D-125 "Worth a look" rows (results kept from before web-27) turn amber.
- **Kept as they are** (Sushil's answer to the open choice): the `permitted` badge's green dot and the calm "not
  listed" person lines take no new symbol.
`tests/test_web.py` (every kind's symbol, name, class and light and dark tokens; no error or refusal uses `--stop`;
the avoid list and `not_permitted` still do), `tests/test_table_photo.py`.

### D-170 · A refused photo is shown back with its problem named `LOCKED` (2026-10-07)
A tester's feedback via Sushil, 2026-10-07: "if ingredients are not clear user should get information what went
wrong". A refusal gave one sentence and never showed the user their own photo, so the tester didn't know what to
change. **Accepted by Sushil 2026-10-07: "Accept, no hint line"** (the words below and light and dark samples).
Built by Claude.
- **The refusal screen** shows the user's own photo (still on the phone; nothing is uploaded again), the problem's
  short label with the D-169 photo-problem symbol and colour, the fix line, and Retake. For "different packs" the
  front sits beside the back. After a reload or on an older result, the label and fix line show without the photo.
  The partial read's retake card does the same. "Report a mistake" is dropped from the refusal screen (nothing was
  read, so there is nothing to correct); "Something not working? Report a problem" stays.
- **The photo check** (`/check-photo`, before the read) shows the label over its sentence, with a Retake button
  that opens the same camera or file picker. `/scan`'s own photo-check refusals carry the label too.
- **Words** (`lenses/screen.py` `PROBLEM_LABEL`, D-091; the fix lines are the existing sentences, unchanged), each
  from what the server already knows:

| Source | Label |
|---|---|
| `photo_too_small` / `photo_blank` / `not_an_image` (photo_check.py) | Too small / Too dark or blank / Not a photo we can read |
| `ingredient_list_unreadable` | Too blurred or dark to read |
| partial read (`ingredients_complete` false) | Part of the list is cut off |
| `no_ingredient_list_found`, `back_not_read`, `no_ingredients_extracted` | No ingredient list in this photo |
| `reason: "recipe"` (D-166) | This is a recipe, not the pack's list |
| `back_is_a_screen` (D-103) / a screen we couldn't read (D-130) | This is a screen, not a pack / No list we can read on this screen |
| `not_a_food_pack` | Not a food pack |
| `product_mismatch` | Front and back look like different packs |
| `independent_read_failed` (D-118) | One clearer photo, please |
| any other code | We couldn't read this label |
| barcode photo: `no_barcode`, `several_barcodes`, `case_code`, `store_code`, `not_a_product`, `barcode_unsure` (and a misread `length` / `check_digit`) | No barcode found, More than one barcode, A carton's barcode, A shop's own label, Not a food pack's barcode, Barcode not clear |

- **Not built** (Sushil's answer): a line naming glare, a cut edge or blur from the model's `extraction_notes`.
- No new step, check, screen, model call or prompt change. The `screen` block gains `problem` ({code, label, fix});
  `retake` is unchanged, so older app versions and replays (D-092) read as before.
`tests/test_photo_problems.py` (every refusal code has a label: the codes are gathered from gates.py, photo_check,
`CHECK_MESSAGES` and barcode.MESSAGES), `tests/test_web.py`.

### D-171 · The label photos in steps, one job per screen; the app's own shutter behind a switch `LOCKED` (2026-10-07); where a step's action sits on a phone `SUPERSEDED by D-185` (2026-10-08)
A tester's feedback via Sushil, 2026-10-07: he liked the barcode scan; the ingredients and the nutrition table should
come next the same way, step by step; the photo page carried too much at once. **Accepted by Sushil 2026-10-07:
"accepted"** (mockups of every screen, light and dark, 390 x 844), **with one change to the order:** "the in-app shutter
can't be tested before it exists. Build it with a setting that keeps today's camera-app button as the default unless
the shutter is switched on." Built by Claude.
- **The steps** (`web/app.js`), each with "Step n of 3": 1, the barcode (as before; "No barcode?" unchanged, D-107; the
  D-146 digit check still follows and is not a step). 2, the ingredient list, one line under the camera: "Fit the list,
  from "Ingredients" to the last word". After the shot, the photo and the D-104 check, then "Is the nutrition table in
  this photo too?" [Yes, check this pack] [No, photograph the table], and "The list continues" (D-119's next part).
  Not answering is Yes: a pack whose list and table fit one photo costs the shutter and one tap. 3 (only on No), the
  nutrition table: "Fit the whole table, from its title to the last row", and "This pack has no table". Then the one
  read and the result.
- **Limits unchanged:** 3 photos in all. The table travels as the next part (back2 or back3), so `/scan`'s roles, the
  join (D-119), one Gemini and one Cloud Vision read, replay (D-092) and the daily limit (D-148) are as before. A list
  in 3 parts has no table step (as D-168).
- **Tips:** D-163's Barcode line (only with a barcode), D-167's Light line, the Frame line and the D-153 drawing move to
  a "Tips" sheet. D-153's opener ("1 or 2 photos", why we read the pack) goes; D-167's result line says it.
- **The front photo** (D-100) is not a step. **Sushil, 2026-10-07, before merging:** "a new pack must not lose its front
  photo (the reviewer reads brand, name and claims from it). /scan already takes the front together with the back, so
  no server work": the answer screens (step 2's question and step 3's) carry a link, "Add the front of the pack too
  (optional)", which takes one front photo ("Optional", "Photograph the front", "Not now") and returns to the same
  screen, showing the front beside the label photos with D-035's "Both photos are of the same pack" box and "Retake
  the front". A link, not a step: skipping it costs no tap. The front goes up with the back in the one `/scan`, as
  before. Shown while `frontWanted` (D-100: not for a re-check of a pack whose front is on file). The result's offer
  ("Add the front of the pack?") stays for a catalogue pack without a front. (The mockup's front offer on a new
  pack's first result isn't built: `/scan` takes a front alone only for a published pack.)
- **D-133's and D-168's table photos** use the step 3 screen (D-168 with its server words, `screen.TABLE_OFFER`).
- **The camera.** With the switch off (the default), each step takes its photo with the phone's camera app
  (`capture="environment"`) or an upload, as before. With `INSIDELABEL_LIVE_SHUTTER=on` (read on `/access` as
  `live_shutter`), a phone that has `ImageCapture.takePhoto()` (Chrome on Android) gets a live view with a frame and a
  round shutter; the shot is the camera's full-resolution still, then the app's resize (1600 px) and `/check-photo` as
  before. "Too dark" (mean brightness) and "Hold still" (frame difference) are worked out on the phone from a 64 x 48
  copy of the view; nothing is sent before the shutter, and a hint never blocks it. A refused camera permission, or a
  browser without ImageCapture, falls back to the camera app with one line saying why. Photos from the shutter are sent
  as `back_source` "live" (D-106 gains a third value; the review screen says "Taken with the app's own shutter"), so
  the stored scans tell the two apart.
- **The comparison (to record here):** Sushil switches the shutter on, scans 3 packs (tiny text, a glossy pouch, a
  curved bottle) both ways, about 6 normal paid reads (about Rs 4, accepted), and compares the stored scans
  (OPERATIONS.md "The label shutter"). Then the shutter goes on for everyone or stays off. **Result: pending.**
- Walked in headless Chromium (Playwright, 390 x 844, light and dark, a fake camera stream, `/scan` answered from a
  replayed reading, `/check-photo` the real server): one photo with the table; list then table; no table; a 2-part list
  then the table (3 photos); upload instead of the camera; the switch off; camera permission refused; D-168's table
  photo; the "Too dark" hint; the front link on step 2's answer (live, with "Not now" and the pairing box) and on
  step 3's (switch off). No console errors. Not walked: a real phone's camera.
web-48. `tests/test_web.py`, `tests/test_photo_source.py`, `tests/test_deploy.py`.

### D-172 · A label Gemini blocks is retried, then sent to a person; every model failure keeps its text `LOCKED` (2026-10-07)
Found 2026-10-07, proposed by the advisor. **Accepted by Sushil 2026-10-07: "accepted"**, with his plan answers ("Send
it to us" at once, the words of Set A, photos held only when sent) and one addition: "anything else that reads
scans.model_raw (the review agent, health_report, eval or batch tools) must skip the {"_blocked": ...} marker, not
try to parse it as a model answer; add a test." Built by Claude.
- **What happened.** Problem report #7 (Sushil, 2026-10-07 18:04 UTC): Britannia 8901063367456, 2 list photos and the
  front, every photo check passed; `/scan` answered 502 `vision_failed` after about 10 s, twice (scans 8ef0f68f... and
  96337b79...). `model_raw` was empty and nothing was logged. Re-reading the stored photos on the server with
  `gemini.analyze_images` gave `Empty response. Finish reason: RECITATION` (6062 input tokens, no output): Gemini's
  recitation guard blocked the whole answer, since a word-for-word transcription of a widely published label looks
  like recitation. Reproducible for this pack. `call_gemini_json()` raised a plain VisionError, and `/scan` turned it
  into "Something went wrong on our side".
- **The model call** (`gemini.py`): an empty answer whose finish reason is RECITATION, SAFETY, BLOCKLIST,
  PROHIBITED_CONTENT or SPII raises `VisionBlocked` (a VisionError) with the reason, on the SDK and REST paths.
  RECITATION is retried up to 2 more times at once, each recorded in `timings.vision_retries`; the others aren't. No
  seed or temperature change: Gemini 3.x ignores temperature (prompt.py) and a seed isn't documented for 3.6; the
  default sampling already varies the answer. The prompt and `PROMPT_VERSION` are unchanged (D-081).
- **The answer** (`/scan`): a block that survives the retries is a refusal (422), never a 502: stored `refused`,
  `error_code` `vision_blocked:<reason>`, allergens "couldn't confirm" (D-037). With a barcode, `can_send` and the new
  `send_now` are true: the app shows "Send it to us" as the first button on the first refusal, and `/send-to-us` takes
  that one scan (D-070's two attempts stay for every other refusal). Without a barcode, nothing can be sent (D-107).
  Photos are kept as every refusal's (30 days, D-098) and held only when sent (D-080).
- **The words** (`lenses/screen.py`, Sushil's Set A): headline "We couldn't read this pack automatically."; problem
  label (D-170) "Our reader couldn't read this label"; fix "Your photos look fine. Send them to us and our team will read
  the label and add this pack."; without a barcode "Your photos look fine, but our reader couldn't read this label. Try
  one more photo, a little closer to the list."
- **Every model failure keeps its text:** VisionError, VisionUnavailable, VisionConfigError and VisionBlocked store
  `"<class>: <text>"` (first 1000 characters) in the new `scans.model_error` (migration 022) and log it with the request
  id. Status codes for the others are unchanged (502, 503).
- **Replay** (D-092): a blocked answer is stored as `model_raw` `{"_blocked": "RECITATION"}` and replays to the same
  refusal. `gemini.blocked_reason()` is the one place that recognises it. Readers of `scans.model_raw`: `repro`
  passes it back to `/scan` (a note says the model blocked its answer); `tools/repro.py show` prints `model error`, and
  `--save` skips a blocked scan (no reading to keep). The review agent's `model_raw` is its own drafts table;
  `health_report`, the barcode tools and retention don't read it. A test lists every file that mentions `model_raw` and
  fails on a new one until it is checked. Report #7's two scans predate the marker: they stay "nothing to replay".
- Walked in headless Chromium, 390 x 844, light and dark: the refusal with its label and fix line, "Send it to us"
  first and "Retake the photo" second, the send screen with one scan, "Thank you". No console errors.
web-49. Migration 022. `tests/test_vision_blocked.py`, `tests/test_web.py`.

### D-173 · A retake keeps the table photo `LOCKED` (2026-10-07)
**Sushil, 2026-10-07:** "i scanned barcode, then ingredients then table, then it asked to scan again ingredients; when i
added it asks again table, it should reuse as it reads properly in previous photo". Plan shown and accepted the same
day. Built by Claude. App only.
- **Why it was so:** "Retake the photo" cleared the back photo and every part, so D-171's table photo went with the
  list and the steps started again (the list, the table question, step 3).
- **Now** (`retakeList()` in `web/app.js`): the refusal's "Retake the photo" (also D-118's "One clearer photo") and the
  partial read's "Retake the ingredients photo" drop the list's photos only. The table photo and the front stay; the
  front still goes after "two packs" (D-108); "use this one anyway" resets as before. A refusal is about the list
  (the gates, D-118, D-166; D-172's block is about the read); a table that can't be read never refuses a scan (D-133).
- **Not kept, as before:** `back_is_a_screen`, `not_a_food_pack` and `screen_unread` (D-103, D-130): the photos aren't
  of a pack, so the table photo goes too (the front stays, as before). On a result whose photos this phone no longer
  holds (another scan's, or after a reload), nothing is kept.
- **After the retake:** step 2 only. The answer screen shows the new list photo with the kept table (and front), "Both
  photos are in", "Check this pack", "Retake" (the list photo), "Retake the table too" (drops it, step 3) and "The list
  continues" while under 3 photos. No table question, no step 3.
- **Server unchanged:** the same roles in the same order (back, back2, back3, front); the table is always the last
  part. One read per scan; D-070, "Send it to us" and D-172's `send_now` unchanged.
- Walked in headless Chromium, 390 x 844, light and dark, live shutter on: list and table, refused, Retake, step 2,
  the kept table sent as back2 (the same bytes as before the retake); "Retake the table too" goes to step 3; a not-a-pack
  refusal asks for the table again; a partial read's retake keeps the table. No console errors.
- **Follow-up to D-165, on this branch (Sushil, 2026-10-07: "find all scores and remove"):** a user saw "Sugar, salt
  and fat quantities on the nutrition panel are not part of the score." under "What this check covers"
  (`reliability/gates.py` `ALWAYS_DISCLOSE[0]`). It broke D-064/D-165 and was out of date since D-133. Now: "The
  headline and findings come from the ingredient list. When we can read the nutrition table, its numbers are shown
  beside ICMR-NIN's guide, as information." The partial-list caveat now says "finding nothing here doesn't mean there
  is nothing to find"; the single-read caveat no longer says "grade band"; the empty-list hints no longer say "scores
  100/100". `tests/test_no_score_words.py`: no shown text (every /scan screen, disclosures, caveat details, the
  screen's word tables, the data tables' shown fields, the app's strings) says "score" or "grade". /how's "No score"
  section (D-165) is the one place the word belongs.
- **Follow-up to D-111, on this branch (Sushil, 2026-10-07: "yes"):** the scope line said "20 ingredients checked" for
  50 50 Maska Chaska, which prints 11 entries: the count was the engine's parsed parts (palm, palmolein, 503, 341 ...
  each on its own). Every count of ingredients on a result is now the list's printed entries:
  - the scope line (`screen.py` "scope"): "We checked the 11 ingredients on the list against 69 additives and 17
    processing markers in our tables." (", and the claims on the front." when claims are shown, D-051). It replaces the
    separate "We checked the ingredients." line (`checked` is now empty), which would have said it twice;
  - "N other ingredients look ordinary": now the glance ring's "other" count, the printed entries nothing else on the
    screen names (was parsed parts minus the named ones);
  - already printed entries, unchanged: the glance ring (D-127) and the sugar chip ("2nd of 11");
  - not counts of ingredients, so they stay: the additives' count ("Additives on this pack (5)", "The other 4 are
    permitted"), which counts additives (one entry "Raising agents [503(ii), 500(ii), 341(i)]" holds three); the
    processing row's "N more", which counts industrial ingredient names; the tallies (D-123), which are sentences with
    no count. `tests/test_screen.py` with a list shaped like Maska Chaska's (11 entries, 23 parsed parts; the exact
    printed list isn't in the repo).
web-50. `tests/test_web.py`, `tests/test_screen.py`, `tests/test_no_score_words.py`.
- **Wording follow-up (the advisor, Sushil agreeing, 2026-10-08), on its own branch:**
  - **The scope line on a partly read list** no longer says "on the list", which suggested the whole list was
    checked. It now reads: "We checked the 11 ingredients we could read against 69 additives and 17 processing markers
    in our tables." The counts are still printed entries (D-111), ", and the claims on the front." is still added when
    claims are shown, and one entry reads "1 ingredient we could read". A complete read keeps "on the list".
  - **The partial-list caveat** ends "What we did find still stands." (was "Findings that were found are still real.").
  `tests/test_screen.py`.

### D-174 · A pack sent to us publishes with its nutrition table `LOCKED` (2026-10-07)
**Sushil, 2026-10-07:** "yes", after review items #71 and #72. The plan was shown with options (a), (b) and (c), and
he approved it the same day. Built by Claude.
- **What happened:** Britannia 50 50 Maska Chaska (8901063367456).
  - The scan took the ingredients and the table (D-171 steps), and Gemini blocked the read (RECITATION, D-172).
  - Sushil sent it to us (item #71). A send_to_us item has no version, so `approve()` had no table to publish. The
    pack went out without one, though the table photo was in the item.
  - The next scan found "published, no table", and D-168 asked for the table (item #72). The user was asked for a
    photo we already had.
- **What the server knew:**
  - `/scan` joins the back parts into one stored photo (D-119) and recorded only how many there were, not which was
    the table.
  - A refused scan stores the model's answer and Cloud Vision's text (D-092), so a table it copied can be checked
    again for free.
  - A blocked scan stored neither. Its Cloud Vision reading had been paid for, but not kept.
- **Option (a), chosen:** a table-only read, with an earlier answer used first. Typing the table (b) is slow and
  error-prone, and it would still need a second reader. When the read fails, the pack publishes without the table, as
  before, and D-168's one-photo offer remains. (b) can follow if failures show up.
- **Now:**
  - **The app names each back part:** `back_kinds` = "list,table", stored with the request. web-51. A scan from before
    this counts as having a table when its list came in two or more parts.
  - **A blocked scan keeps Cloud Vision's text** of its photo when the text has been read by then. It isn't waited
    for.
  - **When a pack is sent to us**, after the reply (the sender never waits), `review/table_read.py` runs once:
    1. **Free:** an earlier answer of the item's scans that copied the table is checked again by
       `nutrition.check()`, using its stored Cloud Vision text.
    2. **Paid**, only when the photos include the table: one read with the table-only prompt
       (`extraction/providers/table_prompt.py`).
       - The prompt is rule 10 of the label prompt, copied word for word, plus the net quantity. The answer is that
         prompt's `nutrition` object.
       - It has its own version, `table-<sha>`. The label prompt is unchanged (D-081).
       - Cost: about Rs 0.6, plus 13 paise for Cloud Vision when no text was stored. One read per item, never per
         page view.
  - **Every attempt is stored** in `review_table_reads` (migration 023): its answer, its error (D-172's marker for a
    block), the second reading and the checked table. None raises out.
  - **On /review:**
    - A sent item shows the checked numbers beside the photos, with D-133's tick.
    - Ticked, `approve()` publishes the table. Unticked, the pack publishes without it, as before.
    - A failed read shows its error in one line, plus a button ("Read the nutrition table from these photos", one paid
      read). The button doesn't read again once a usable table is on file.
  - **Published with its table**, the pack never gets D-168's offer.
- **The D-133 rules hold:** a number is shown only where Cloud Vision's text of the same photo has it and the table
  adds up. Publishing goes only through `ReviewService.approve()`.
- **Measuring on item #71:** `tools/table_read.py 71`, on the server (one paid read). It stores the read and prints
  what was kept. It never changes the catalogue.
`tests/test_sent_table.py`.

### D-175 · A published pack is checked again against the real pack every 15 days `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "what if everytime we ask for barcode and photos then validate with database if ingredient
changes or not once we will check per day if any column is there only updated_scan time field and don't need to
change any and that day within 24 hrs it reads barcode only and give result instantly". After the advisor's reply
(the result first, the photo optional, the free comparison first): "15 days will keep". The plan was accepted on
2026-10-08, with the advisor's two changes (Sushil agreeing), and Sushil said to build it the same day: "Start
D-175 on d175-recheck from current main, as approved, with the advisor's two changes." Built by Claude.
- **Why:** brands change recipes under the same barcode. A barcode hit returned the published version (D-024) and a
  change was noticed only when someone happened to send photos of the new pack. D-073's free comparison was never
  built: its re-check button ran a normal paid scan.
- **The result first, always.** A barcode hit answers at once, as before. A food pack whose last check is more than
  `RECHECK_AFTER_DAYS` (15, `lenses/screen.py`) days old shows one optional card after the three answers: "Help keep
  this pack up to date: one photo of the ingredient list.", button "Photograph the ingredient list". One tap opens
  step 2 (the list) with the barcode kept; no table question, no front link.
  - **One ask per scan:** while the card shows, and on the result of its photo, D-168's table offer and D-100's front
    ask wait for a later scan. D-073's avoid-list ask, when it shows, does the same job, so the card doesn't.
- **"Last check"** is the newer of the version's `verified_at` (publish, a person) and a new `last_verified_at` that a
  matching photo sets (migration 024). Nothing else on the version changes when a photo matches.
- **The photo is compared free first** (`review/checker.unchanged`), on its Cloud Vision text (Tesseract when Vision
  is off, D-093). "Unchanged" only when all of these hold:
  1. the list is there, and where it ends was found;
  2. every word of every stored entry is in the text (D-118's MISSING);
  3. no word of the text's list that the stored list and statement lack (LOST, with D-157 and D-158's stamp, panel
     and cut words left out);
  4. no new INS number (`lost_ins_numbers`, D-099);
  5. no allergen word anywhere in the text, the "Contains" line too, whose allergen the stored list and statement
     don't name (`lenses/allergens.mentioned`);
  6. **the same number of entries** (the advisor's change): the text's list split at commas outside brackets has as
     many entries as the stored list;
  7. the same order: entry i of the text holds the words of stored entry i (the order feeds "2nd of 11").
- **Unchanged:** `last_verified_at = now()`; the scan row is `resolved_via 'recheck'`, `cache_hit`, cost 0; no model
  call, no review item, no new version. The catalogue result says "Pack checked again on 8 Oct 2026."
- **Not clearly unchanged:** one paid read (about Rs 0.6), exactly the normal photo path. The same ingredients hash as
  the published version sets `last_verified_at` (any photo scan of the same label does now); a different one is a
  reformulation item, as before. Only `ReviewService.approve()` publishes.
- **The free check only decides "same, skip the paid read"** (D-004, D-034). It never becomes a fact, a verdict or a
  finding. A failure in it counts as "not clear".
- **D-073 uses the same path:** its re-check photo is sent with `recheck=true` and compared free first. Its ask and
  words are unchanged and not limited to 15 days.
- **Two dates, never merged** (the advisor's change, Sushil agreeing, replacing rule 7 of the brief): a photo match
  is a machine check, not our team's. When it is newer: "Our team checked this label on 20 Sep 2026; a photo of the
  pack matched it on 8 Oct 2026." Otherwise as before. The catalogue block's `last_verified` is the newer date and
  the 15 days count from it.
- **Measured** on the four real Cloud Vision texts the repo keeps (the gold photos aren't in it): a pack that gained
  one entry was caught 44 of 44 times ("Sugar" added beside "Invert sugar" is caught by the count); two neighbouring
  entries swapped, 40 of 40; an added INS 211 and an added peanut, caught. 2 of the 4 real packs pass as unchanged:
  the D-157 stamped pack prints some entries without commas (8 against 11) and the two-part read has overlap words.
  Both only cost the paid read. `tools/recheck_measure.py` replays the rule on the server's published packs and
  their stored texts, with no model or Google call.
- **Cost per check:** about 13 paise with Cloud Vision, Rs 0 with Tesseract; about Rs 0.6 more only when not clear.
  Only the person who sent the photo waits for the free check (Cloud Vision, usually 1 to 3 s), and never more than
  `RECHECK_WAIT_S` (10 s, `api/main.py`): a read not done by then is "not clear" and the paid read goes on.
- **Replayable (D-092):** `request.recheck`, and `ocr.back.recheck` = the decision, what each check found, its reader
  and text. `repro.replay_scan` replays a free re-check from that text with no model.
- The app: web-52. `tests/test_recheck.py`.
- **Count follow-up (Sushil, 2026-10-08, "Build it" on the decision card), on its own branch:** on the server,
  `tools/recheck_measure.py` passed 20 of 57 published packs; 28 failed on the entry count (missing 9, lost 9,
  lost_ins 1, new_allergens 8). Three of them showed the count was ours, not the pack's: a stored list that splits a
  compound entry inside its brackets (Oats & Chocolate Cookies, 18 stored against 13 printed), and Cloud Vision
  dropping a closing bracket (Oreo, "(500(ii), 503 (ii), STARCH"), which merged the rest of the list into one entry.
  - **Now:** both sides are cut at every comma, brackets or not, the stored list after joining it, so like is
    compared with like; "Sugar" beside "Invert sugar" is still one more piece.
  - **The list end, for the count only:** the latest of the last entry's final three words, as a misread last word
    can also sit earlier in the list ("SOYBEAN" in the chips, "SOYABEAN" at the end). The D-117 and D-118 checks
    keep the last word.
  - **Measured** on the repo's 4 texts and those 3: Oats and Oreo now count equal; Eat Fit, where Cloud Vision lost
    commas, still goes to the paid read; 90 of 90 added entries and 83 of 83 swaps still caught. The server number
    comes from re-running the tool after deploy.
  - **Re-measured after deploy:** 23 of 57 pass (was 20); entry count still 25, most likely Cloud Vision losing
    commas, which no count rule can recover safely. Left there: the cost is at most about Rs 0.6 per re-check photo.
- **Allergen-number follow-up (Sushil, 2026-10-08, "yes"):** the "no new allergen" test ignores bare numbers.
  Sulphite's aliases include INS 220 to 228, and Junior Horlicks, Mother's Plus and Women's Plus read as "new
  sulphite" from nutrition-panel values; their records match their labels. A new INS number in the list is still
  caught by `lost_ins_numbers`. The allergen check itself (`lenses/allergens.check`) is unchanged.

### D-176 · The app gets a real frame: a header with the screen's name and a back arrow, and a bottom bar `LOCKED` (2026-10-08); its screen-name-in-the-header part `SUPERSEDED by D-180` (2026-10-08); its home footer, and the bar on computers, `SUPERSEDED by D-185` (2026-10-08)
**Sushil, 2026-10-08:** "we will make the best ui i am not happy with ui part take some reference attached, and
suggest, plan only first, no proper header and footer etc till now", with two screen recordings of another food-label
app; then "think about animation etc more focus on visually something describe and ey catching"; then, on the plan
(https://claude.ai/artifact/YaSSPSNBUgbVgfHYDBbA9w, five choices each with a recommendation), "please proceed on UI
design plan". **Accepted by Sushil 2026-10-08**, taken as yes to every recommendation. This entry is step 1 of the
plan's four (the frame); the result screen, the other screens and the website follow as their own entries.

From the recordings, only patterns were taken: a fixed top bar with back and actions, and a bottom bar. Not taken:
their rating out of 5 (D-064), "Generally Safe" (D-071), the "concern" and "like" sections (D-042), the red-to-green
bars (D-169), "Buy on Amazon" and "better rated options" (D-088, D-138), and their purple.

- **The header** (supersedes D-152's "wordmark on every app screen"): home and the first-run screens (welcome, who,
  invite, Before you start) keep the centred wordmark. Every other screen shows its name in the centre ("Result",
  "Household", "Your scans"...) and a back arrow on the left. Back on a tile's page goes to its result (D-134), on a
  result goes home (the photo steps behind it are done), and on any other screen goes where the phone's Back goes,
  or home when the screen was the first one opened. The profile icon stays on the right on every screen.
- **The bottom bar** (supersedes D-152's Household and Compare in the menu): Home, Your scans, a raised Scan
  button in the middle (it opens what "Scan here" opens), Compare (with its count as a badge), Household. Fixed, so
  showing or hiding it moves nothing (CLS). Hidden on the first-run screens and on the camera and photo steps,
  where it would cover the shutter. Every target is 48 px or more; the screen in view is marked `aria-current`.
- **"Your scans"** (`#/scans`): new. D-123's counts, then every result kept on this phone, newest first. Nothing is
  sent anywhere (D-074).
- **The menu:** Your data, Send feedback, Report a problem, How we check, Privacy. **The text footer** shows on home
  only, with the same links.
- Unchanged: every word about a pack (D-091), D-146's digit check, the scan flow's steps, the result's layout.
`tests/test_site_desktop.py`, `tests/test_web.py`.

### D-177 · The result screen: a pack card with the user's photo, three tabs, nutrition bars, Share `LOCKED` (2026-10-08); its person lines, Worth knowing list, nutrition rows, "In preparation" block and desktop layout `SUPERSEDED by D-185` (2026-10-08)
Step 2 of the plan accepted in D-176 (**accepted by Sushil 2026-10-08**, "please proceed on UI design plan", taken as
yes to every recommendation). Built by Claude. Layout and motion only: every word about the pack still comes from
`lenses/screen.py` (D-091), and nothing new judges it (D-004, D-064).

- **The pack card:** the product name sits next to a small, tilted copy of the user's own front photo (the back one
  when there is no front). The photo is shrunk on the phone (360 px, JPEG) and kept only in that phone's history,
  on the newest 10 results; older entries lose it. It is never sent anywhere (D-074). No stock or retailer images
  (D-088).
- **The people block stays first** (D-060), inside the card, shown at once with no motion. The headline follows.
- **Three tabs under them:** "For you" (not-permitted tiles, Worth knowing, the three answers, the asks for a
  better photo), "What's inside" (nutrition, ingredients, additives) and "On the pack" (the user's photo and the
  label text as read). Buttons in a tablist; arrow keys move between them; the chosen tab is kept for that result
  while the app is open. "Worth knowing" is now an open list, not folded.
- **Nutrition bars:** energy, added sugar and salt get a bar under their line, from the server's own numbers
  (`screen.nutrition.rows[].bar`: value, the ICMR-NIN line, unit). The line is marked on the track with its value.
  Amber when the server's tone is "worth" (D-169), grey otherwise; never red to green, no bar when the label gives
  only a bound ("less than"). Saturated and trans fat get none. The text line stays the finding; the bar is
  `aria-hidden`.
- **Share:** a button on the card shares the product name, the people lines, the headline and the site link,
  through the phone's share sheet or the clipboard. The lines are filled with no profile, so no nickname ever
  leaves the phone (D-074).
- **Motion** (transform and opacity only, off under reduced motion): the photo tilts in, the tab pill slides, a
  panel fades in, a bar fills from zero when it scrolls into view.
- Not built in this step: a per 100 g / per serving switch (servings stay as text lines).
`tests/test_web.py`, `tests/test_pack_kind.py`.

### D-178 · Home, Your scans, Household and Compare as cards `LOCKED` (2026-10-08); its scan-card chips and its Start at home card `SUPERSEDED by D-185` (2026-10-08)
Step 3 of the plan accepted in D-176 (**accepted by Sushil 2026-10-08**, "please proceed on UI design plan", taken as
yes to every recommendation). Built by Claude. Layout and motion only: the words on each card are the ones these
screens already showed (D-091), and nothing is sent anywhere new (D-074).

- **Home:** after "Scan here", a "Checking for" card: each person in the household as a chip (their initial, their
  nickname, their avoid list in the server's allergen labels), with Edit opening Household. "Recent scans" shows
  the newest 5 as cards, with "See all" opening Your scans.
- **Scan cards** (home and Your scans): the user's own photo of the pack where the phone kept one (D-177), else a
  drawn pack; the name; the server's chips or first person line, as before; and when it was scanned (Today,
  Yesterday, or the date). An empty Your scans gets a drawing.
- **Household:** a card per person: a coloured initial, the age band, and the avoid list as chips. "Add a child"
  is a dashed card.
- **Compare:** the chosen packs side by side, with a dashed "Scan a pack" slot until there are two. The answer
  shows the packs side by side too, each with what compare.py said about it, "Better pick" marked on the one
  named; the page scrolls to the answer.
- **Motion** (transform and opacity only, off under reduced motion): cards rise in one after another
  (`--stagger`, at most 6); a pressed card dips.
`tests/test_web.py`.

**Follow-up (2026-10-08, web-62), Sushil with a phone screenshot:** "Don't show everything here in checking for.
Don't show directly all avoid list, keep one click option to see". Home's "Checking for" card shows one row per
person: avatar, nickname and a count ("You · 9 to avoid", or "· no avoid list"). A person with a list is a
`<details>` row, closed on every visit: a tap opens their full list underneath (the same `avoidNames()` labels),
another closes it; the chevron is the app's own. "Edit" still goes to Household. Fixed in the same card: the
name wrapped one letter per line beside a long list (`overflow-wrap: anywhere` let it shrink); it now never
breaks or shrinks, and the list wraps under the line. Nicknames stay on the phone (D-074).

### D-179 · The website gets a header nav and a real footer `LOCKED` (2026-10-08); its wordmark-on-the-left part `SUPERSEDED by D-180` (2026-10-08)
Step 4, the last, of the plan accepted in D-176 (**accepted by Sushil 2026-10-08**, "please proceed on UI design
plan", taken as yes to every recommendation). Built by Claude. Supersedes D-152's centred wordmark on the website
only; the app keeps D-176's header.

- **Header** (every page, 65 px as before, so nothing below it moves): the wordmark on the left. From 768 px, How
  it works, How we check, About, Privacy and an "Open the app" pill on the right, the page in view marked
  `aria-current`. On phones one menu button (48 px) opens the same links in a panel; it is a `<details>`, so it
  needs no script.
- **Footer** (every page, the same): a deep band with one line on what InsideLabel is ("Each finding names the
  FSSAI rule or primary document it comes from"), three short columns (Product: Open the app, How it works,
  Compare packs; Trust: How we check, Report a problem, Privacy; Company: About, Contact), and D-138's "No company
  whose labels we read pays us, and none can change what we show." The old one-line footers go.
- Not added: a Google Play badge (the listing is not public yet).
- Motion: the phone menu panel fades and drops in (transform and opacity, off under reduced motion).
`tests/test_site_desktop.py`.

### D-180 · The wordmark stays in the centre of the header, on every app screen and website page `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "web browser or all logo should be always in center, don't change the position". D-176 had
replaced the wordmark with the screen's name on the app's inner screens, and D-179 had moved it to the left on
the website; both are undone. Built by Claude.

- **App:** the wordmark is centred on every screen, as D-152 set it. Inner screens keep D-176's back arrow on
  the left and the profile icon on the right; their name is the page's own heading, not in the header.
- **Website:** the wordmark is centred on every page. From 1024 px the site's links (How it works, How we check,
  About, Privacy) sit to its left and "Open the app" to its right; below that, one menu button on the right holds
  them (D-179's menu). Every page's header now uses the wide container, so the wordmark sits in the same place.
- Measured in Chromium at 360, 390, 800 and 1280 px: the wordmark's centre is the window's centre on the website
  home, About and Privacy and on the app's home, Your scans, a result and Household.
- Unchanged: D-179's footer, D-176's bottom bar and back arrow, the header heights (65 px on the website).
`tests/test_site_desktop.py`.

### D-181 · The front photo is required while the catalogue wants it `LOCKED` (2026-10-08); where its "Check this pack" sits on a phone `SUPERSEDED by D-185` (2026-10-08)
**Sushil, 2026-10-08:** "make the front photo mandatory". Supersedes the front's "link, not a step" in D-171
(Sushil, 2026-10-07). Built by Claude.

- **A step, not a link.** While `frontWanted` is on (D-100: a new pack, a pack scanned without a barcode, or a
  catalogue pack whose front isn't on file), the front is "Step 4 of 4". The answer to "Is the nutrition table in
  this photo too?" becomes "Yes, now the front of the pack" (or "Next: the front of the pack" once the table is
  in), and leads to the front's camera. "Not now" and "(optional)" are gone; "Back" returns to the photos in hand.
- **The check waits for it.** With the front in, the screen says "Both photos are in" (or three, or four), shows
  D-035's "same pack" box above "Check this pack", and the button stays off until the box is ticked: an unticked
  front would not reach the reviewer (the server keeps a front only with a trusted pairing).
- **Not asked:** a re-check of a pack whose front is on file, D-175's list-only re-check, and a catalogue hit by
  barcode alone (no photos are taken, so the result's "Add the front of the pack?" offer stays optional).
- **App only.** `/scan` still accepts a back without a front (repro, tools, tests, an older app); the app is the
  only client that sends new packs.
- **No loose links on the camera pages (Sushil, 2026-10-08: "this tips and back in every page does not look good").**
  Tips is a small pill with an info icon beside each camera step's title, not a link under the picker (in the live
  shutter row its place is left empty). The header's back arrow does what the "Back" and "Not now" links did: on
  the table, front and later list steps it returns to the photos in hand (a screen shown in place sets `backTo`),
  elsewhere it goes back as before. "This pack has no table" is a full-width answer button, and leads to the front
  when it is still to take.
`tests/test_web.py`.

### D-182 · The pack picture: a reviewed front photo taken by the team, shown for that barcode `RECOMMENDED` (2026-10-08); `ACCEPTED and widened by D-183` (2026-10-08)
Sushil asked where the app can get real product images ("the UI looks great with a real image"). Options Claude
checked on 2026-10-08:
- **Verified by GS1** (gs1.org): the public search allows 30 lookups a day (GS1 UK's page) and shows the brand's
  own name, image and net content where the brand entered them. Fine for a person checking a barcode by hand or
  adding a lead (D-089); not for the server. Its terms PDF could not be read from the cloud session (gs1.org is
  blocked there), so "no automated use" is an inference until someone reads it in a browser.
- **GS1 India DataKart:** brand-supplied data and images (GS1 India claims 20M+ SKUs). Paid registration plus company
  papers; its terms treat product data as confidential (cl. 3.1) and forbid passing access on (cl. 8.2), so showing
  its images to users needs GS1 India's written OK. Still D-088's "one email".
- **Open Food Facts images:** CC BY-SA (credit and share-alike; brand trademark rights still apply). Thin for India
  and collides with D-029. **Retailer images:** no (D-088).

**Sushil chose "Own photos" (2026-10-08).** Proposed by Claude, not built until accepted:
- **Whose photos:** only fronts taken by the team (Sushil and reviewers), from installs joined with an invite marked
  `team` (new column on `invites`). A user's photo is never shown to anyone else (D-074; D-128 leaves open whether a
  pack photo showing a hand or a face is personal data).
- **Reviewed by a person:** a team front on a catalogue product with no picture yet queues a `pack_picture` item.
  A person (never the review agent, D-117) approves it only when it shows the pack alone (no hand, face or room),
  is this product, and is sharp. Approved pictures go in a new `product_pictures` table (product, image key, taken
  on, scan, approved by, approved at); the newest one is shown, and its photo is kept like any catalogue photo
  (D-098).
- **Served small:** `/pack-picture/<product>` returns a 480 px JPEG with its metadata stripped, cached; `/scan`'s
  catalogue block carries its URL and date, and `lenses/screen.py` words the caption ("Photo of the pack taken by
  InsideLabel on 8 Oct 2026", D-091).
- **Where it shows:** D-177's pack card shows the user's own photo first and the pack picture when there is none (a
  catalogue hit by barcode alone). Your scans and Compare cards can use it later.
- **Never a source:** the picture is not read for findings; they still come from the reviewed version (D-004). No
  brand can supply or replace it.
- **Cost:** storage only, no model call.

Needs Sushil's acceptance.

### D-183 · Pack pictures from reviewers and shoppers, and example photos as a suggestion `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "yes" to D-182, "we will keep user informed as well in initial terms of first page and will
show good example of front and back ingredient and nutrition table visually so user will follow same ... only
suggestion we will give to take this way photo not restrict"; then, on the card "Show shoppers' front photos to
everyone, once a reviewer approves them?", **"Shoppers too"**. Widens D-182's "team only". Built by Claude.

- **What it is:** `pack_pictures` (migration 025): a small copy of a pack's front (`pictures.shrink`: long edge
  480 px, JPEG, turned upright, saved with no metadata), its source (`reviewer_upload` or `shopper_photo`), the scan
  it came from, when it was taken, who approved it and, once removed, who removed it. The newest one not removed is
  shown. The copy has its own key: the shopper's photo still goes at 30 days (D-080, D-098) and stays private.
- **Only a person makes one, on /review.** On a review item with a front photo, two boxes: "Show this front photo
  to everyone who scans this barcode" and "It shows the pack alone (no hand, face, person or room) and it is
  sharp"; the first without the second is refused. The picture is made after the publish, by the route, so the
  review agent (D-117), which calls `ReviewService.approve()` itself, never makes one. `/review/pictures` lists the
  pictures shown (with Remove) and takes a reviewer's own upload (barcode of a catalogue product, the photo, and
  two boxes: the pack alone, this product).
- **Whose photo:** a shopper's only from an install that agreed to terms `2026-10-08` or later
  (`pictures.TERMS_FROM`); older photos say why they can't be shown. The terms gain one rule: "I agree that a clear
  photo I take of the front of a pack may be shown to other InsideLabel users as that product's picture, after a
  person checks that it shows only the pack." A new version, so everyone sees "Before you start" once more (D-105).
- **Privacy page:** a paragraph under "Who reads your photos" (a small copy, no hidden details, never a name or
  install id, never read for a result), and a line under "How long we keep it": kept while the product is in the
  catalogue, with no link to the person, also after "Delete my data" (like a version's photos, D-129); ask and
  we take it down.
- **Served:** `GET /pack-picture/{key}` returns only a key being shown (404 otherwise, every other photo stays
  private), cached as immutable (keys are content hashes). A catalogue result's `screen.pack_picture` has its URL,
  alt text and caption ("Photo of the pack, checked by our team on 8 Oct 2026"), worded in `lenses/screen.py`
  (D-091); absent when the product has none. A replay (`version_hit`) carries none.
- **The app:** D-177's pack card, the "On the pack" tab and Your scans' thumbnail use the shopper's own photo, else
  the pack picture with its caption. It is never read for findings (D-004).
- **Example photos, a suggestion only:** a drawn pack (a made-up "Sample Co. Oat Biscuits", no real brand) in three
  "good photos": front, ingredient list, nutrition table, each with a tick. "Before you start" shows all three
  under "Photos that read best" with "This is a suggestion: any clear photo of the pack works" (`terms.json`
  `examples`); each camera step shows its own above the picker, "Like this: flat, sharp, the whole panel" (the list
  step's pack-back drawing stays in Tips). Nothing checks a photo against them.
`tests/test_pack_pictures.py`, `tests/test_web.py`.

### D-184 · No more beta: the invite-only beta removed, and no "beta" or "tester" in anything a user sees `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "before that remove all beta options anywhere in app and web, we are no more beta now".
Plan by Claude, accepted by Sushil the same day with his choices below. Supersedes D-102 (the invite-only beta,
already off by D-162); amends D-148's wording only (the daily photo limit stays, for cost).

- **Removed:** the join screen ("Welcome to the InsideLabel beta", "Join the beta"), the `join` route and
  FIRST_RUN step, `joinRequest` (`web/`); the server's invite gate (`_require_invite`, 403 `invite_required`),
  `POST /join`, `INSIDELABEL_INVITE_ONLY`, `JoinRequest`, the `join_fail` rate limit; the Store's invite methods
  and `beta_testers`; `tools/beta.py` (its feedback listing moves to `tools/feedback.py`); `tests/test_beta.py`
  (its feedback tests move to `tests/test_feedback.py`). `/access` now returns `{agreed, terms_version,
  live_shutter}`.
- **No migration.** `invites`, `invite_devices` and `feedback.invite_code` stay in place, unused: codes made before
  D-162 may still be on the server, and retention (D-128) and "Delete my data" (D-129) keep deleting them, so the
  privacy page's "any invite code" and "any invite link" lines stay. Its "what we collect" line now says codes
  stopped on 6 October 2026 and no new ones are given (it said "which tester sent a scan").
- **"Before you start" (D-105) stays:** it is the terms of use every install agrees to, asked by the app. The
  server only refused un-agreed scans when invite-only was on, so with the gate gone its check (and its "rules
  for the beta" message) goes too; the live site already worked this way. A server-side check would be a new
  decision. Rule 4 loses "and can close my invite" (there is none); the text changed, so the version is
  `2026-10-08-2` and every phone sees it once more (Sushil's choice). `pictures.TERMS_FROM` stays `2026-10-08`,
  which the new version still meets.
- **The photo limit (D-148):** "During the beta, each phone can photograph {limit} packs in any 24 hours."
  becomes "Each phone can photograph {limit} packs in any 24 hours." (`lenses/screen.py`, D-091).
- **Website:** the meta description drops "In an early beta."; both "In an early beta. On Android, testers get it
  through Google Play." lines become **"On Android: coming soon on Google Play."** (Sushil chose the public
  version, as "coming soon" until the Play app is live; then the Play link); the footer "InsideLabel, in beta"
  becomes **"© 2026 InsideLabel"** on every page (Sushil's choice).
- **Privacy page:** "Beta version, last updated 6 October 2026. A lawyer will review it before the public
  launch." becomes **"Last updated 8 October 2026. A lawyer will review this policy, and we will update it
  here."** (Sushil chose the reworded line). Nothing else in substance changes.
- **Kept:** DECISIONS.md history; comments naming testers as where an idea came from; migration and table names.
  `tools/release_check.py` drops "beta" from its header and its access line.
- **Everyone on the full plan, free** (Sushil, 2026-10-08: "by default everone now pro user"): until paid plans
  and Play billing exist, every user gets what D-148 gives the paid plan, at no cost: 15 photo scans a day,
  unlimited barcode lookups, every feature. D-148's lower free limit (5 photo scans a day) does not start now; it
  waits for a later decision that ships billing. No plan name, price or upgrade appears anywhere in the app or
  website now. (The live limit is already 15 a day, `ratelimit.PHOTO_SCANS_A_DAY`, so no code changes.)
- **Plan names, for later** (Sushil, 2026-10-08, chosen from the advisor's list: first "Label  Label Plus", then
  the same day "The plan names Label / Label master"): the free plan will be called **"Label"** and the paid plan
  **"Label Master"**, replacing "Basic" and "Pro" for the future. Shown nowhere until billing ships.
- **Sign-up and sign-in ON HOLD** (Sushil, 2026-10-08: "stop that signin and login part now. once it is available
  and testing done will implement"): no Google, email or phone sign-in is built now, including D-148's Google
  sign-in. It comes back with its own decision.
- **No plan name shows now** (Sushil, 2026-10-08: "pro = Label Master and Free = Label, Yes"): the "Ask about this
  pack" tag "Pro · in preparation" (app result screen, `web/design.html`) and "Pro · not yet available" (website
  home) become plain **"In preparation"** (web-61). "Free · shelf by shelf" stays: it says the shelf feature
  will cost nothing, not which plan. `tests/test_no_beta.py` also fails on "Pro" as a word, "Label Master",
  "Label Plus", a price (Rs or the rupee sign with a number, "a month") or "upgrade" in any app string, screen.py
  table, website page or the design page.
- **Checked by** `tests/test_no_beta.py`: no app string, screen.py table, website page or meta description,
  "Before you start" text or server message says "beta" or "tester" ("beta-carotene" is a pigment and passes).
- **Sushil's own steps:** the Play Store listing text and the Play Console track.

### D-185 · The redesign: two fonts, quieter colours, motion with a job; built in three phases `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "redesign all app and website top5 best ui app or website available in world ... review
till u get more than 96% score. more animation, motion gif style focused for insidelabel." And later the same day:
"redesign with a top 1 percentage reviewer, think all font option to change if required not much information on
top to be exposed etc". Plan and mockups by Claude (https://claude.ai/code/artifact/5f38a778-9606-4254-80c2-1745fbd84216).
**Accepted by Sushil 2026-10-08:** "Accept (Sushil, 2026-10-08), with these choices: 1. Fonts: Figtree + Bricolage
Grotesque. [...] 2. New words: accept all three [...] 3. Phases: three PRs, (1) design system and app screens, (2)
scan flow and result, (3) website. Each its own branch from main after the previous one is merged. 4. The changes to
D-176, D-177, D-178 and D-151 (including the website's hero film becoming an animated phone): accepted as listed in
your plan. Record each in D-185 as superseding that part only, with one line per change. 5. Keep the rules:
allergen lines and "cannot confirm" never behind a tap; D-169 colour meanings; no score feel; nothing slower on a
mid-range Android phone. Each phase's PR shows the reviewer's table with every screen in that phase above 96 and the
Lighthouse numbers." Built by Claude.

**The five benchmarks, for principles only** (no layout, icon, wording, colour or asset taken from them, or from any
food-label app):
- **Apple** (iOS Health, Wallet, apple.com): the clearest type hierarchy; motion that shows where a thing came from.
- **Linear:** restraint and density; one accent; every state of a small control finished.
- **Stripe** (stripe.com, Docs): complex, sourced information made calm; numbers that line up; the product shown.
- **Airbnb:** one task per screen on a phone; cards that lead with the picture.
- **Headspace:** warmth without noise; slow, calm loops that explain instead of decorate.

**The design system (every phase):**
- **Type:** two families instead of four, each one variable file, Latin plus the rupee sign, SIL OFL, self-hosted
  in `web/fonts/` (no visitor IP goes to Google, D-110): **Figtree** 400 to 700 for text (16 KB) and **Bricolage
  Grotesque** 600 to 800 for headings (31 KB), 47 KB in all (about 100 KB was the budget). Sizes: 13 caption (the
  smallest), 14 label, 16 body, 17 lead, 18 card title, 21 section and result headline, 28 screen title, 38
  display. Tabular figures wherever numbers line up. Each face has a local fallback scaled to its metrics
  (`size-adjust`, `ascent-override`), so the swap moves no line.
- **Not preloaded (the plan said preloaded; changed on measurement):** Lighthouse mobile on the app's first screen,
  gzip on as the live server: both files preloaded LCP 1874 ms (Performance 99), Figtree only 1725 ms, none 1667 ms
  (main today 1677 ms). On slow 4G a preload competes with the shell's own CSS and JS; with `font-display: swap`
  and the scaled fallbacks nothing flashes or shifts either way. The service worker precaches both files, so every
  later visit has them. The website keeps its two preloads until Phase 3 measures it.
- **Colour:** D-110's cream, ink and green, quieter: the cream less yellow, the mint glow behind pages gone, softer
  shadows. D-169's meanings unchanged; shades (text on tint, light / dark, contrast): avoid list and "Not permitted
  in India" #b42318 on #fdebe8 / #ffb4a8 on #4a1f1c (5.71 / 8.21); worth a look, cannot confirm #7a4a06 on #fff3d6 /
  #ffd58a on #443214 (6.78 / 8.84); information #1f5a85 on #e5f1fa / #a8d4f5 on #17344d (6.40 / 8.20); photo or
  app problem, never red, #3e5a6e on #e8eef3 / #c6d6e2 on #233a4f (6.21 / 7.89); done #047a45 on #f9f7ef / #5fcb8c
  on #0f2133 (5.05 / 8.10). The logo's gold (#f2b632) is the colour of reading only: never a finding, never text.
  "Start at home" fills green, not gold: it counts packs done (D-169's green), and gold on white is 1.8:1, under
  the 3:1 a bar needs.
- **Shape:** 4 px grid, 16 px side gutter; radii 10, 14 (buttons, fields), 20 (cards), 28 ("Scan here", sheets).
- **Motion rules:** CSS, SVG and the Web Animations API only; no library, no GIF or video in the app. Only
  `transform` and `opacity` animate (plus an SVG stroke); `tests/test_design_system.py` fails on a keyframe that
  moves anything else. UI moves in 150 to 400 ms; a loop is calm (2.6 to 9 s); nothing blinks. A scan never waits
  on motion, and the people block appears at once (D-060). Under reduced motion every duration is 0 and each loop
  shows its finished still. Tokens: `--d-enter` 220 ms and `--d-reveal` 320 ms (were 200 and 250), `--d-draw` 400
  ms (new), `--ease-spring` (new, a `linear()` spring with about 4 percent overshoot, for a small control
  arriving, never for text about a pack). docs/APP_DESIGN.md 8.1 to 8.6 carry the tables.

**The three new word lines (accepted; final text):**
1. Website hero lead (Phase 3): "Scan the barcode and photograph the label. See what matters for each person in your
   family, and where every line comes from."
2. Website "How it works", step 2 (Phase 3; the front is required while the catalogue wants it, D-181): "The list
   that starts with "Ingredients:" and the table of values, then the front of the pack."
3. App header from 1024 px (Phase 1): "Scan a pack".

**What this supersedes, that part only (one line each):**
- D-110 and D-153, type: four families become two; DM Sans becomes Figtree; Source Serif 4 and IBM Plex Mono go
  (`--serif` now names Bricolage Grotesque, `--mono` Figtree with tabular figures). Phase 1.
- D-110 and D-169, colour: the shades above; meanings unchanged; the mint glow removed; the logo's gold added for
  reading only. Phase 1.
- D-176, frame: from 1024 px the bottom bar's places (Home, Your scans, Compare with its count, Household) move
  into the header left of the centred wordmark (D-180 kept), "Scan a pack" on its right, and the bar hides; home's
  text footer goes, its links stay in the profile menu. Phase 1.
- D-177, result: each person line shows the person's initial; Worth knowing items become rows with a kind icon and
  a one-line source; nutrition rows lead with the label and the value; on desktop the pack card and people stay
  on the left; "In preparation" items become one quiet line. Phase 2.
- D-178, cards: scan cards show at most 2 chips (the "worth a look" ones first); "Start at home" becomes one
  compact card; home no longer repeats Your scans' counts. Phase 1.
- D-171 and D-181, camera steps: the step's action docks at the bottom of the screen on phones; the drop zone
  shows only with a mouse. Phase 2.
- D-151, film: the website hero becomes an inline animated phone (scan, photo, result); the film stays one tap
  away lower on the page. Phase 3.
The old entries' headers are marked when their phase is built: D-110, D-153, D-169, D-176 and D-178 now.

**Unchanged:** every word about a pack (D-091); allergens first and "cannot confirm" as visible as a match
(D-060); no score, grade, stars or traffic light (D-064, D-165); D-169's one symbol and one colour per kind; the
wordmark and logo (D-152), centred everywhere (D-180); the flows (D-168, D-170 to D-175, D-181); at most one
optional ask per scan; nothing new leaves the phone (D-074); no tracking or analytics; /review untouched.

**Phase 1, design system and app screens** (branch `claude/project-thread-n9uqxj`, web-63, `il-shell-63`):
- **Header:** 60 px (68 from 1024), the wordmark centred; its hairline shows only once the page scrolls. From 1024
  px the places and "Scan a pack" as above; the back arrow hides on the places' own screens.
- **Bottom bar:** translucent over the page; the place in view gets a soft green pill that springs in; the labels
  are 13 px; the Scan button sits raised in a ring of the page colour.
- **Home:** "Scan here" is one green card with a drawing of what it does: a gold line reads a pack's barcode, its
  list lights up line by line, a result card arrives with a tick (7.2 s, three passes, then still; each pass starts
  on the finished drawing, which is also the reduced-motion still). Then "Checking for", "Start at home" as one
  compact card with three segments (a `progressbar` for screen readers), and Recent scans. From 1024 px two
  columns (Scan here, Checking for and Start at home; Recent scans, 6 instead of 5). Blocks rise in order.
- **Your scans:** the repeated heading goes; two columns from 1024 px. **Household and the person editor:** each
  question is a card with its title inside and a hairline between choices; Save docks above the bar on phones
  while the list scrolls. **Compare, Your data, Send feedback, Report a problem, the menu:** the new type, cards
  and buttons; the menu sheet gets a handle on phones.
- **The quiet action a screen ends on** (Done, Cancel, Home, "Scan a pack to add") sits centred under the main
  one, the whole row its target.
- **First run:** the welcome shows the same drawing on a green panel; "Before you start" and "Who avoids it?" take
  the new type and cards. **States** (no connection, server error, the photo limit, offline): centred under their
  kind's disc, which springs in.
- `web/design.html` shows the new swatches and type. Measured on the branch:
  - **Lighthouse mobile, app first screen, gzip as live**, the final build run in turn with main, median of 3:
    Performance 100, Accessibility 100, Best Practices 100, SEO 100; LCP 1689 ms (main 1818, Performance 99, in
    the same runs), FCP 1220 ms (main 1290), CLS 0. An earlier, quieter run: LCP 1667 ms against main's 1677.
  - **Returning user's home, slow 4G and 4x CPU** (median of 5): LCP 1256 ms (main 1244, within noise), CLS 0,
    longest task 111 ms (main 125).
  - **Headless walk** (first run, two photo scans to a result, every Phase 1 screen, the menu, no connection, a
    server error, the photo limit, the offline shell) at 390 light and dark, 360 dark, 1280 light and dark, and
    390 with reduced motion: no console errors.
  - **Reviewer's final scores** (rubric: hierarchy 15, type 10, colour 10, motion 15, brand 10, one-hand 10, trust
    10, consistency 10, performance 10), every point lost named on the evidence page
    (https://claude.ai/artifact/BYWK3DZSWgg7Z8LCUBZuT9): Home 98 (computer 97), Your scans 98 (computer 98),
    Household 98, the person editor 97, Compare 97, the menu 98, Your data 97, Send feedback 98, Report a problem
    98, Welcome 98, Who avoids it? 97, Before you start 98, no connection 98, server error 98, the photo limit 98,
    offline home 98, the other screens on a computer 97. Kept on purpose: "Delete my data" stays red (a
    destructive action behind a confirmation; D-169 governs messages about a pack).
`tests/test_design_system.py`, `tests/test_web.py`, `tests/test_site_desktop.py`.

**Phase 2, the scan flow and the result** (branch `claude/project-thread-n9uqxj` again, from `main` after #141,
web-64, `il-shell-64`). **Sushil, 2026-10-08** (relayed in the project): "Start Phase 2. Also, Sushil
(2026-10-08): the motion is too quiet; he couldn't see it. Make it more visible: 1. Home's "Scan here" loop keeps
playing slowly while home is on screen (not 3 times then still); it pauses when the app is in the background, and
is still with reduced motion. 2. The loop is bigger and easier to notice on a phone (it can take more of the
button), without making the button taller than today. 3. In Phase 2, every screen in the scan flow and the result
has motion a first-time user notices within 2 seconds (the scanner line, the label being read while waiting,
result cards arriving, the tick drawing itself), still purposeful and calm, never blinking. Record it in D-185 with
Sushil's words." So Phase 1's "three passes, then still" is replaced: the drawing plays an 8 s pass for as long as
home is on screen, pauses while the app is in the background or the card is scrolled away, and is the finished
still under reduced motion; it is laid out in `em` and sized to the card's width (container units), so at 390 px
it is 165 by 155 px (was 132 by 124) in the same 168 px tall card.
- **Barcode:** a torch glyph on the camera; corners in the logo's rounded shape that settle and breathe (2.6 s); a
  gold line sweeping the frame (2.6 s each way); the camera's line on the camera; "No barcode? Photograph the
  ingredients" and "Take a photo of the barcode" as two quiet buttons under it. Without a live reader, a drawn
  barcode takes the camera's place in the same square frame, still and with no line. The steps as dots, the current one a pill that slides over from the
  step before.
- **Label steps:** the example in a card under the title, settling in, its tick (32 px) drawing itself and a gold
  band reading it once; the step's action docks at the bottom of the screen on phones (D-171, D-181), with the
  table question directly above its two answers; the drop zone shows only with a mouse. A photo being checked has
  a gold band passing over it (1.3 s each way) in the example's place. "Both photos are in" (and the others) draw
  their tick; the photos in hand arrive one after another in one frame style. The digit check (D-146) and Send it to us
  also dock in thumb reach; on a refusal only Retake docks, and the second refusal's "Send it to us" sits under
  its hint. A photo being checked shows a turning ring in place of the camera icon; the digits get a gold line
  drawing under them.
- **Waiting:** a sheet whose lines light up one by one under a moving lens that never crosses "INGREDIENTS:" (4.8
  s), or a gold line over a barcode while a pack is looked up; the explanation smaller and narrower; the seconds
  show from 3 s.
- **Result:** the pack name 21 px; each person line with the person's initial; Worth knowing as rows with a kind
  icon and a one-line source; "In preparation" as one quiet line; "Not this pack? Scan again" smaller; on a
  computer the pack card and people stay on the left (sticky) and the tabs on the right. The cards after the
  people block rise in order (70 ms apart; the people block is there at once, D-060), and again each time a tab
  opens; the tab pill springs; the nutrition bars and the ring fill (600 ms). Nutrition rows: the server now sends
  each row's `amount` and `why`, cut from the row's own sentence (no new words, `text` unchanged), so a row reads
  "Energy 473.8 kcal", its bar, then the rest; amber only on the fill and the icon.
- **Thank you** screens (Send it to us, a reported mistake, a problem) open on a filled green disc whose check draws itself. A
  problem's retake arrow turns once.
- A screen sliding in from the right could leave the page wider than the phone (the bottom bar ran past the edge on
  a finding's page; on `main` too): the main column now clips it. On a computer the
  reading screen already has the result's width, so the result arriving does not move the page (a 0.14 layout
  shift before).
Measured on the branch:
- **Lighthouse mobile, app first screen, gzip as live**, the final build run in turn with main, 3 each: Performance
  99, 99, 99 (main 100, 100, 100), Accessibility, Best Practices and SEO 100 in every run; LCP 1712 to 1829 ms
  (main 1679 to 1737), CLS 0. The extra Phase 2 CSS costs about 30 ms of LCP on a cold first load.
- **Headless walk** (barcode live and drawn, the lookup, the digit check, all four photo steps with their reviews,
  the read, the result and both other tabs, a finding's page, two refusals, Send it to us, Thank you) at 390 light
  and dark, 360 dark, 1280 light and 390 with reduced motion: no console errors; layout shift from "Check this
  pack" to the settled result 0 in all five; no page wider than the window.
- **Review:** eight rounds; every Phase 2 screen ends at 97 to 99 (scan 97 and 98, lookup 98, digit check 98, the
  photo steps 97, their reviews 97 to 99, reading 98, result 99, the full result 98, What's inside 98, On the pack
  97, a finding's page 98, refusal 97, Send 97, Thank you 99, desktop result 97).
Superseded, that part only: D-171's and D-181's action placement on a phone (now docked); D-177's person lines,
Worth knowing list, nutrition rows, "In preparation" block and desktop layout (as above). Headers marked.

**Phase 3, the website** (branch `claude/project-thread-n9uqxj` again, from `main` after #143, web-65,
`il-shell-65`). **Sushil, 2026-10-08:** "Start Phase 3".
- **Home:** the header sits on the hero's deep blue, so the first screen is one panel. The hero takes the accepted lead
  (line 1 above) and, in the film's place (D-151, superseded as above), a phone drawn in HTML and CSS: the app's own
  header (the wordmark centred, D-180), then three screens that slide in like pages, 9 s a loop: a gold line reads a
  barcode, an ingredient list lights up under a lens, the result's cards settle in (the example's own lines with their
  [1] to [3]). It pauses out of view, and under reduced motion shows the result alone, still. Decoration only
  (`aria-hidden`): the example table below has every line in words. On a phone under 420 px it is drawn at 88 percent
  so its screen starts in the first view.
- **The film:** one tap away, its own section after How it works, under the heading "How InsideLabel checks a label, in
  41 seconds" (D-151's caption). The still and a large play button; it never starts by itself, and pauses out of view.
- **How it works** step 2 takes the accepted line 2; the steps are numbered discs (three cards on a computer). The
  example table becomes a card per row on a phone, so no column is cut off.
- **How we check, About, Privacy:** calm reading pages: a large title, the lead in ink, sections ruled by a hairline,
  text at most 68 characters wide. Each page lists its own headings: a sticky row of chips on a phone, and from 1024 px
  a column beside the text that stays in view; the section in view is marked (a small script per page, after the
  footer). About's "Write to me at" moves into the founder block; Privacy's dated notice is a quiet outlined line.
  Words unchanged.
- **Header, menu and footer:** on a computer every page's header and footer use the home page's edges. The menu opens
  over a scrim that closes it when tapped, and its button turns into a cross; still no script for the menu (D-179). On
  the home page the menu no longer repeats "Open the app" (the hero's button is under it). Footer links are 48 px tall.
- **Motion:** headings, cards and the film rise in as they scroll into view (`animation-timeline: view()`, where the
  browser has it); the hero's words move in 320 ms without fading, so the first paint already shows them (a fade left
  Lighthouse with no LCP at all on an earlier build). The phone's screens slide rather than fade, so no frame shows
  text at part opacity (Lighthouse's contrast check failed on a caption caught mid-fade).
- **Font preloads, measured as Phase 1 asked** (Lighthouse mobile, gzip as live, 3 runs each, in turn): with the two
  preloads LCP 1287 to 1443 ms and CLS 0; without them LCP 770 to 1380 ms but CLS 0.004 in every run (the headline's
  font swap moves the lines below it). The website keeps its two preloads; the app keeps none.
Measured on the branch:
- **Lighthouse mobile, website home, gzip as live,** run in turn with main, 3 each: Performance, Accessibility, Best
  Practices and SEO 100 in every run (main: Accessibility 96, an About link under 4.5:1); LCP 1435 to 1448 ms (main 1517
  to 1532), CLS 0.
- **Headless walk** (home, How we check, About, Privacy, each first view and whole page, and the open menu) at 390 light
  and dark, 360 dark, 1280 light and dark, and 390 with reduced motion: no console errors, layout shift 0 on every page.
- **Review:** four rounds (81 to 88, then 91 to 95, 96 to 99, 97 to 99); final: home on a phone 97 (light, dark and
  reduced motion), home on a computer 98, How we check 98 (phone) and 99 (computer), About 98, Privacy 97, the menu 97.
  Kept on purpose: the menu does not close on Escape or on a link tap (that needs a script, D-179).
Superseded, that part only: D-151's film as the hero (now one tap away lower on the page). Header marked.

**Evidence** (Sushil, 2026-10-08: saved in the repo): [docs/design/d185/](docs/design/d185/README.md) holds the three phases'
before and after screenshots (WebP) and motion GIFs, each listed with its screen, theme, width and the reviewer's score.
Not served by the app or the website.

### D-186 · Crop a pack picture to the pack on /review `LOCKED` (2026-10-08)
**Sushil, 2026-10-08:** "can we trim this and show", then "yes". His brief, the same day: a shopper's front photo
(D-182, D-183) showed a DMart Premia Jeera 100 g pack held in a hand over a floor. The reviewer's ticks say "It shows
the pack alone (no hand, face, person or room) and it is sharp", so it can't be ticked, although the pack itself is
clear. Today /review can only tick a photo as it is. Built by Claude; no change to D-182 or D-183.

- **Where:** only on /review (reviewers, D-097): the pack picture block on a review item (a shopper's front), and the
  upload form on /review/pictures (a reviewer's own photo). Nothing changes in the app or the website.
- **The control:** "Crop to the pack" over the photo. The reviewer drags a box (mouse or touch; corners resize, the
  middle moves it; arrow keys move it, Shift and arrow keys change its size), sees "What will be shown" beside it,
  and can go back with "Use the whole photo". A small inline script in the review page (`review/templates/_crop.html`);
  no library. Without JavaScript the photo is used whole, as before.
- **What travels:** four numbers, left, top, width and height, as fractions 0 to 1 of the photo as shown (after its
  EXIF rotation; browsers apply it too). Empty means no crop.
- **What the server checks** (`pictures.crop_from_form`, `pictures.shrink`): numbers, finite, inside the photo, at
  least 20 percent of each side, the shape between 1:3 and 3:1 in pixels. A bad box is refused with a line for the
  reviewer and nothing is saved; on a review item nothing is published either.
- **The order in `pictures.shrink()`:** rotate by EXIF, crop, resize to 480 px, save without metadata. No crop
  behaves exactly as before.
- **The ticks** keep their words and mean the cropped result: "It shows the pack alone ... and it is sharp" is about
  what will be shown. The preview is what the reviewer ticks against.
- **Record:** `pack_pictures.crop` (migration 026, nullable jsonb `{"left", "top", "width", "height"}`; NULL is the
  whole photo). `source` stays `shopper_photo`, or `reviewer_upload` for a reviewer's own; `approved_by` as before.
- **The shopper's original** is not changed and not kept longer: it still goes at 30 days (D-080, D-098). Only the
  small cropped copy is the pack's.
- **Never read for findings (D-004).** The review agent (D-117) never crops or ticks a picture: it publishes through
  `ReviewService.approve()`, which never makes one.

### D-187 · A plain "Lic No." never makes a food pack not food `LOCKED` (2026-10-08)
**Sushil, 2026-10-08,** on review item #82: "but fssai present". His brief, the same day: "Indian food packs print their
FSSAI licence as "Lic. No." beside the logo all the time, so "Lic No." alone says nothing about a non-food
licence." **Accepted by Sushil 2026-10-08** in that brief (the rule below is his). Built by Claude; narrows the licence rule of D-116 as extended by D-139 and D-140, nothing else of them.

**What happened.** Item #82, Bambino Vermicelli POPULAR 850 g (8904287001052), taken with the app's own shutter. The
back shows the FSSAI logo with "Lic No. 10014047000..." (the last digits under the shopper's thumb) and a second
"Lic No. 11423999000016" on the manufacturer block. The model read the first as "Lic No. 100140470002" (12 digits) and
had no "fssai" word to copy (the logo is artwork). `core/pack_kind.py` filed it as a non-FSSAI licence ("lic no" was a
licence word), both faces counted as read, and `decide()` gave `not_food`: /review told the reviewer to reject a
vermicelli pack with a nutrition table and category 6.4.2. The review agent had already flagged the clash.

- **Only words that name a non-food licence count** (`data/pack_kinds.json` `licences.non_food_licence_words`): "Drug
  Lic", "Mfg Lic", "DL No" (and their spellings), and D-116's own case, "Ayurvedic" or "AYUSH" on a line that also
  names a licence ("Ayurvedic Medicine Mfg. Lic. No. A-2755"). "Lic", "Lic No", "Licence", "License", "Licence No",
  "License No" and "Reg No" alone no longer make a licence non-FSSAI.
- **A probable FSSAI licence:** a licence line with a number of 10 to 13 digits starting 1 or 2 (FSSAI licence and
  registration numbers are 14 digits starting 1 or 2; a thumb or a fold can hide the end). It never gives `not_food`;
  the pack stays food and /review says "probable FSSAI licence, last digits not read: check the pack". The review
  checker sends it to a person. A full 14-digit number counts as FSSAI's, as before.
- **not_food also needs no ordinary food signal:** when the pack prints a nutrition table (read or partial) or its
  category is an ordinary food category (not 13.x), `decide()` never returns `not_food` on the licence rule alone; it
  stays food and goes to a reviewer with the reason (the agent's clash check, made a rule).
- **Unchanged:** an FSSAI licence decides food (D-116); a partial read never gives `not_food` (D-139); a pack licensed
  only as an AYUSH medicine, with nothing that says ordinary food, is still `not_food` on a complete read.
- **Replay (D-092):** stored answers replay with the new rule. `tools/pack_kind_replay.py` (read-only) lists every
  stored version whose kind or reviewer notes change, with its review item.
- **Tests:** `tests/test_pack_kind.py` (item #82's lines, the Chyawanprash-style licence, the food signals, the
  checker, the replay tool) and `tests/test_pack_kind_db.py` (the /review note).
- **Follow-up (2026-10-08): version 74.** The replay found version 74 (Bambino Vermicelli, 8904287001052, item #82)
  published as `not_food`; users saw the not-food screen. Sushil fixed it by hand on the server the same day:
  `UPDATE product_versions SET pack_kind = 'food', pack_kind_evidence = jsonb_build_object('evidence', '[]'::jsonb,
  'corrected', 'D-187: was not_food from a plain Lic No. (thumb hid the last digits); pack_kind_replay gives food.
  Sushil, 2026-10-08') WHERE id = 74`. D-188 adds `--apply` to the replay tool so the next one is not by hand.

### D-188 · Allergen lines show only when they matter; a front tick; "on the pack we checked"; replay --apply `LOCKED` (2026-10-08)
**Sushil, 2026-10-08,** after a Bambino Vermicelli result whose top card said "JOO: Milk, soy, fish: not in the
ingredients. We didn't see a "may contain" line in the photo, so check the pack.": "if any list matches then we should
see JOO's allergen line first; with warning, unnecessary it's not required", then "will show only Match ... unnecessary
panic don't do. if Cannot confirm ... suggest", then "yes" to the advisor's table (match: a calm red card; cannot
confirm: an amber card with Retake on a photo scan; no match: nothing at the top). On the plan's screenshots, the same
day: "i thought it won't show anything, but it says not listed"; he chose **option B**: on no match, nothing for that
person anywhere on the result. **Accepted by Sushil 2026-10-08** (his option B message names the plan's matches,
cannot-confirm and age lines "as accepted"). Built by Claude. Changes how D-060 shows on the result screen only.

**1. The people block on the result screen (`lenses/screen.py`, D-091).**

| Situation | At the top | Colour |
|---|---|---|
| Listed in the ingredients | `Milk is listed: "Milk solids".` (the label quoted) | red (D-169) |
| Listed in the allergen line | `Milk is listed in the allergen line: "Contains wheat, milk".` | red |
| The pack says "may contain" | `The pack says it may contain soy: "May contain traces of soy".` | red |
| A source we can't tell (`uncertain`) | unchanged: `We can't tell whether "lecithin" comes from soy. Check with the brand ...` | amber |
| Cannot confirm, partial read | `Part of the list couldn't be read, so we can't confirm milk, soy, fish. Check the pack.` | amber |
| Cannot confirm, otherwise (below 0.95, unclear) | `The list wasn't clear enough to confirm milk, soy, fish. Check the pack.` | amber |
| A child's age line (honey under 1, HFSS under 2, sugar 2nd) | `1 thing worth knowing for {name}.`, its facts under More | amber |
| No match | nothing, here or in "For you" (sesame: see below) | none |

- One card per person; the person's name is on the card above the line. A second match for the same person shows under
  the first line, not folded. No "warning", no exclamation mark.
- **"May contain" is red:** today's states rank it with "contains" and D-169 gives both the avoid cross; the pack
  itself names the allergen. Amber stays for what is about our read ("can't tell", "can't confirm").
- **Retake** on an amber cannot-confirm card of a photo scan (D-170, D-173's retake flow); none on a barcode-only hit.
- **"For you"** opens with "Nothing extra for {name}'s age came up." (never a card), then, for a person whose avoid
  list has sesame and only when sesame isn't listed, the note's existing words: `Brands don't have to declare sesame,
  so this check is weaker.` (`data/allergens.json`: `fssai_mandatory: false`, its `note`; mustard, the other such
  row, gets the same line), then one reminder when something on an avoid list isn't listed and no allergen line was
  read: `We didn't see a "may contain" line in the photo, so check the pack for one.` on a photo
  scan, `We didn't see a "may contain" line on the pack we checked, so check the pack for one.` on a barcode-only hit.
  No "Not listed for ..." line (option B); never "safe", "free from" or "no milk" (D-042/D-071).
- **Your scans, Compare, Share** follow the same rule: a scan card names a match in its colour; Compare's allergen
  lines leave out "not listed"; Share sends `For your child, milk is listed: "Milk solids".` (no nickname, D-074,
  D-177) and nothing for a person with no match.
- **The /scan answer is unchanged:** `allergens` stays the first key with every state (D-060). `screen.people` now
  holds only the cards; `screen.for_you` holds "nothing extra" and the sesame line, `screen.for_you_note` the reminder. A result kept on a
  phone from before web-66 still lists everyone; the app hides its "not listed" lines.

**2. "In the photo" on a barcode scan.** On a catalogue hit no photo was taken; the words come from the reviewed
record. `allergens.py` and the reminder say "on the pack we checked" there and keep "in the photo" for a photo scan.

**3. /review pack picture: a front tick.** A published pack picture (TATA Sampann LUXE DRY FRUIT & NUT MIX,
8904043906393) was the back of the pack. The item's pack picture block and /review/pictures have a third required
tick, "It is the front of the pack"; a picture is not saved without it. The ticks are about the cropped copy (D-186).

**4. `tools/pack_kind_replay.py --apply --by <name>`.** Off by default; the default run stays read-only. With it, each
changed version gets today's `pack_kind` and `pack_kind_evidence` (evidence and review notes, plus a `corrected` note:
the rule's decision number, old and new kind, who ran it, the date); each written row is printed; nothing else on the
version changes. D-187's follow-up line records version 74, fixed by hand before this existed.

- **Follow-up, before merge (Sushil, 2026-10-08):** age lines stay at the top, as accepted (the advisor's reply he
  pasted: "Age lines stay at the top: a child's age line (today's amber "1 thing worth knowing for Mira", e.g. honey
  under 1, HFSS under 2) keeps its amber card for that child, only when there is one."). And, agreeing with the
  advisor, the sesame note comes back in "For you", only for a sesame avoider and only when sesame isn't listed. Both
  are in the table and the "For you" line above.
- **Tests:** `tests/test_screen.py` (match, cannot-confirm, no match, a household of three with one match, the
  reminder's two wordings, an age line's amber card, a sesame avoider's line, a milk avoider sees nothing), `tests/test_web.py` (cards, For you, scan cards, Share, Retake), `tests/test_pack_kind.py`
  (the gold labels' cards), `tests/test_pack_kind_db.py` (a barcode hit says "on the pack we checked"; `--apply`
  writes only the two columns, the default run writes nothing), `tests/test_pack_pictures.py` (the front tick).

### D-189 · Privacy: "Your data" is in the profile menu; the mustard note stays `LOCKED` (2026-10-09)
**Sushil, 2026-10-09,** "you are right continue", answering two questions in the project chat with the recommended
option each. Built by Claude.

1. **Privacy page.** Since D-185 Phase 1, Your data is in the menu behind the person icon at the top right, not at the
   bottom of the screen. `web/site/privacy.html`, "Your choices": `<b>Your data</b> (at the bottom of every screen)`
   becomes `<b>Your data</b> (in the profile menu, top right)`; "Last updated 8 October 2026." becomes "Last updated
   9 October 2026." Nothing else in the policy changes; the terms version does not change, so no one sees "Before
   you start" again.
2. **The sesame note for mustard stays** (D-188 already shows it): mustard, like sesame, is marked
   `fssai_mandatory: false` in `data/allergens.json`, so a mustard avoider sees the same weaker-check line when
   mustard isn't listed. No code change.

### D-190 · An Ayurvedic medicine gets the not-food screen, not "no ingredient list" `LOCKED` (2026-10-09)
**Sushil, 2026-10-09,** "yes", to the advisor's proposal. Built by Claude.

**What happened** (review item #85, scan c8193e8a-3045-4f8f-9eaa-08e96d54847a, 2026-10-09). A Baidyanath
CHYAWANPRASH "Special Pack". Both faces read (`front_status` and `back_status` "read"), `ingredients_status`
"not_found" (an Ayurvedic pack prints a formula, not an "Ingredients:" list), `licences` [] (no licence line read),
`pack_statements`: "AYURVEDIC MEDICINE", "(Ayurveda Sara Samgraha)", "Mfd. in India in a GMP Certified Plant".
- `/scan` refused it as `no_ingredient_list_found` in the reliability gate, before `pack_kind.decide()` ran. The
  shopper got "couldn't find the ingredient list", tapped "Send it to us", and a send_to_us item (#85) landed on
  /review for a pack that can never be published as food.
- Even had it reached `decide()`, the answer was `food`: "Ayurvedic"/"AYUSH" counted only on a line that also names
  a licence (D-116 as narrowed by D-187), and no licence line was read.

1. **"Ayurvedic medicine" printed is a non-food sign on its own.** The phrases "Ayurvedic medicine", "Ayurvedic
   proprietary medicine" and "AYUSH medicine" (any case, any spacing), in a pack statement, the product's name or
   variant, a front claim or a licence line, count without a licence line (`data/pack_kinds.json`
   `licences.medicine_label_words`). "Ayurvedic" alone, "Ayurvedic recipe", "Ayurvedic tea", "with Ayurvedic herbs"
   stay food: "medicine" must follow. Everything that beats the licence rule beats this too: an FSSAI licence (or a
   probable one, D-187) decides food; a nutrition table or an ordinary food category (not 13.x) stops not_food and
   a reviewer looks (D-187); a partial read never gives not_food (D-139). The evidence quotes the pack's own words
   (`AYURVEDIC MEDICINE`, face back), so /review and the not-food screen show what was read; /review names it
   ("not food: "Ayurvedic medicine" printed and no FSSAI licence on the photos") and offers a matching reason.
2. **A refused "no ingredient list" is checked for not-food first.** When the reliability gate would refuse with
   `no_ingredient_list_found`, both faces were read and the read is not from a screen, `/scan` runs
   `pack_kind.decide()` first. On `not_food` it answers with the not-food result (the same screen and words a not_food
   pack gets; the "We checked the ingredients against your avoid lists" line is left out, since no list was read),
   with every avoided allergen "couldn't confirm" (D-072). No "Send it to us", no review item, no product or version,
   barcode or not: only the scan row (outcome `unlisted`, `resolved_via` "barcode" when one came with it), with
   its trace for replay (D-092). Every other refusal, and `no_ingredient_list_found` on a partial read or with a
   food kind, is unchanged.
3. **`tools/pack_kind_replay.py --apply` keeps every correction note.** On 2026-10-08 its single `corrected` string
   replaced Sushil's manual note on version 74 (D-187). Now `pack_kind_evidence.corrections` is a list, oldest first:
   --apply appends its note and carries over the existing list and any old single `corrected` string (as the first
   entry). /review shows every note under the kind of pack. The default run stays read-only.

**Open:** the rule matches the pack's printed words as printed. We record only what the pack prints and make no
claim about which law makes it a medicine; the label term "Ayurvedic Proprietary Medicine" has not been checked
against a primary document (D-046).

---

### D-191 · Fewer retakes: table-only words, a table hint (off), same photo same answer, the cross-check asks when it matters `LOCKED` (2026-10-10)
**Sushil, 2026-10-10,** "yes D-191", then "accept" to the plan (/mnt/project-files/fewer-retakes/plan.md, with
390x844 light and dark screenshots). The advisor reviews before merge. Built by Claude.

**Why** (Sushil): "many complain i am getting like performance issue while checking the photo as it asks multiple
time to take a new pic". The server, 2026-10-03 to 10-10: 86 photo scans, 39 refused (45%): 18
`independent_read_failed`, 15 `no_ingredient_list_found`, 6 others; each read takes about 9 s.
- `no_ingredient_list_found`: 2 were the Ayurvedic pack (D-190). In 10 of the other 13 the nutrition table was read
  but no list: the shopper photographed the table.
- The same pack refused 2 or 3 times in a row: 8901063371101, 8904422708501, 8908017658295. Identical photos sent
  again: 8901063371101 (14:24:18 and 14:33:12 on 10-07), 8901058022216 (13:45:51 and 13:46:29 on 10-08),
  8904422700826 (14:52:42 and 14:56:22 on 10-09).
- `independent_read_failed` since D-159: 15. Maggi 8901058022216 asked 4 times, the last two on `missing:
  ["ginger"]` only; 8901058022223 on `missing: ["nut"]`; 8901928222401 on `missing: ["contaadded"]`; 4 with
  `section_found: false`. One ask was right and must stay: 8901725121228, a may-contain oats and soy line.

1. **Table-only words, and the table photo kept.** A `no_ingredient_list_found` refusal of a one-photo back whose
   nutrition table was read (or partly read) says so: "We read the nutrition table, but not the ingredient list.",
   then 'The ingredient list is a separate block that starts with "Ingredients", usually beside the table or on
   another side of the pack. Photograph that one; we'll keep this photo for the table.' (the "keep" half only when
   the table was read in full), and the button "Photograph the ingredient list". The kept photo goes into the
   table step (D-173), so the retake is one photo. Words in `lenses/screen.py` (D-091). Every other refusal is
   unchanged.
2. **A free table hint, OFF.** `INSIDELABEL_TABLE_HINT=on` lets `/check-photo` run one local Tesseract read (at most
   3 s) of the first list photo of a scan; when it finds table words and no "Ingredients", the app asks "This looks
   like the nutrition table. Is the ingredient list in it?" with "Retake" and "Use this photo". It never refuses or
   stores anything. Word lists in `data/table_hint.json`. It stays off until `tools/table_hint_measure.py` (false
   alarms, catches, misses, time, on stored scans; read-only) gives numbers Sushil accepts.
3. **Same photo, same answer.** A phone that sends the same photos with the same choices as its own refusal in the
   last 24 hours gets that answer again from the stored read: no Gemini or Cloud Vision call, the limiter hit given
   back (D-095), and a scan row with `request.repeat_of` and its trace (D-092), so it replays. The screen adds "This
   is the same photo as last time, so the answer is the same. Take a new photo of the ingredient list." A
   `vision_blocked` refusal (D-172) is read again. In the app, the phone's Back after a refusal resent the same
   photos; it now opens that result instead.
4. **The cross-check asks only when it matters, once.** D-159's test for what only Cloud Vision read (LOST) now also
   covers the words of Gemini's list Cloud Vision never saw (MISSING): a clearer photo is asked for only if a word
   would change the result. A word Cloud Vision read glued to a neighbour ("groundnut" for "nut", "contaadded") counts
   as seen. No list found in Cloud Vision's text no longer asks on its own; MISSING is checked against the whole
   text. At most one ask per pack per phone in 24 hours; a second goes to the result, as "Use this one anyway" does.
   The D-117 checker still sends every such word to a person. Before and after (`tests/test_fewer_retakes.py`, 8
   cases from the week, each asked before): 3 still ask, among them 8901725121228's may-contain line. The exact
   count for the 15 comes from `tools/cross_check_replay.py` on the server (read-only).

---

### D-192 · A second reader: Claude Haiku 5.5 behind a switch `PLANNED` (2026-10-10)
**Sushil, 2026-10-10,** "keep it in plan only d-192 not now". Not built.

The plan: `claude-haiku-5-5` ($0.10 input and $0.50 output per million tokens, for prompts up to 100,000 tokens)
as a second label reader behind `INSIDELABEL_READER=gemini|claude`, default `gemini`. The gold set first: it is
built only after a gold-set run shows it reads as well as Gemini. AI reads, rules judge (D-004) either way.

---

### D-193 · A faster read: tokens recorded, three read switches, all off `LOCKED` (2026-10-10)
**Sushil, 2026-10-10,** "yes D-193", then "accept" to the plan. The advisor reviews before merge. Built by Claude.

**Why:** photo scan median 8.9 s, slowest tenth 12.0 s. Gemini's call (`vision_ms`) median 8.6 s, 97% of the scan.
Cloud Vision takes 1.1 s and the wait for it after Gemini is 0. 64 of 86 photo scans sent the front in the same
call; only 1 Gemini retry. The time is Gemini's own read, so that is what the switches try.

1. **Tokens per call, stored.** Every Gemini call records its usage (prompt, output, thinking and total tokens,
   model, thinking level, media resolution, ms): a scan in `scans.timings->'gemini'` (and `gemini_front` for a split
   read; no migration for scans), the review agent in `review_drafts.usage`, the table read in
   `review_table_reads.usage` (migration 027). `tools/repro.py show` prints it.
2. **Three switches, each one line in /etc/insidelabel/settings.env, all off:**
   - `INSIDELABEL_READ_SPLIT_FRONT=on`: the back and the front in two Gemini calls at once; the front's answer is
     joined to the back's before the rules run. A front that hasn't answered when the back has is saved on the row
     later (`model_raw_front`, migration 027); the result doesn't wait for it.
   - `INSIDELABEL_THINKING_LEVEL=minimal|low|medium|high` (unset: today's `low`).
   - `INSIDELABEL_MEDIA_RESOLUTION=low|medium|high` (unset: the API's default). A value the API doesn't take is
     ignored.
   Each scan records the settings it ran with (`timings.read`), so a replay uses the same.
3. **`tools/batch_scan.py --split-front --thinking-level --media-resolution`** prints seconds and tokens per photo;
   it refuses an `--out` under reports/.
4. **PROMPT_VERSION unchanged.** A switch goes on only after the advisor's gold-set run (about Rs 15 to 20) shows it
   is faster with no loss in reading.

---

## Open and pending

### D-050 · Numeric score in the consumer UI `SUPERSEDED by D-064` (removed)
The prototype currently shows a 0-100 score, an A-E grade, *and* "Risk Index 7.2/10" -
three renderings of the same `{none:0, low:4, moderate:12, high:25}` table. One decimal
of implied precision on arbitrary weights is the easiest thing for a lawyer or
journalist to dismantle, and it contradicts the stated "no single health score"
principle.

Proposal: keep the three-band verdict (defensible because the ultra-processed band is
definitional), show flag counts by severity, move the score to admin-only for ranking
alternatives and regression-testing rule changes. **Not yet decided.**

### D-051 · Claim checker in the beta `LOCKED` (2026-09-25): ship in shadow, switch on when measured
The claim checker has never fired on a real front-of-pack claim. Shipping it requires
pairing attestation + a rebuilt rule set + FSSAI Schedule I retrieval - roughly 3
extra weeks. Deferring means the beta tests the commodity half (ingredient
explanation) and the resulting retention number is a **floor, not a forecast**.
~~**Not yet decided.**~~

**Decided 2026-09-25** (Sushil delegated: "go with your best decision"): neither defer
nor ship blind - **ship in shadow**. The checker is built, pairing attestation (D-035)
exists, and it has tests; what it lacks is evidence on real claim-bearing packs.
- Every `/scan` still runs the claim check and stores its findings with evidence, so
  reviewers see them on `/review` and the gold set measures them.
- Users see `claim_check.status = "not_checked"`, `reason = "claims_not_released"`
  until `INSIDELABEL_CLAIMS_TO_USERS=on`.
- **Switch it on** when the gold set holds **≥ 5 packs whose front claims match a
  rule** and `tools/release_check.py` shows **0 false contradictions** on them.
  It can happen mid-beta; record the date here when it does.
Why: a wrong "the front contradicts the back" on a real brand is the costliest error
the app can make, while the upside (the differentiator) is kept one flag away.

### D-052 · Launch wedge `LOCKED` (2026-09-25): allergy households + parents of young children
General wellness users scan twice and churn; household packaged-food variety caps
natural frequency at 2-4 scans/month. Allergen and diabetic households have a forcing
function to open the app. ~~**Not yet decided.**~~

**Decided 2026-09-25** (Sushil delegated): **allergy households + parents of young
children**, not diabetic households for now.
- The allergen check (D-060/71/72) is the most complete, most tested part, and it
  serves both groups; the D-058 seed (15 kids' biscuits first) already targets parents.
- Diabetic households need sugar *amounts* from the nutrition panel, which is not read
  yet (D-081 is after the beta). Revisit when it is.
- Play listing, onboarding and the first screen talk to these two groups; the target
  audience in Play Console stays **adults** (parents), never children (D-074).

### D-053 · Premium pricing `SUPERSEDED by D-148` (its "uncapped" line and its open price)
Original thinking was ₹49-99/month. Recommendation is ₹399-499/**year** - Indian
consumer utilities convert far better on annual, and matches a product used a few
times a month rather than daily. Also: scans stay uncapped and free forever
(throttling scans starves the catalogue, which is the asset). **Not yet decided.**

### D-054 · The "100% ATTA" ruling `LOCKED` (2026-09-25): the claim is about the flour; no finding
Patanjali Doodh Biscuits declares `Wheat flour (Atta) 58.3%` while the front says
`100% ATTA`. Likely manufacturer intent is "the flour is atta, not maida" rather than
"the product is 100% atta". Must be decided deliberately before any rule fires,
because it names a brand with active advertising-claim litigation history.
~~**Not yet decided.**~~

**Decided 2026-09-25 by Sushil** (reviewing the pack): atta is the only flour on the
label, so "100% ATTA" describes the flour and is true. InsideLabel says nothing about it.
- `100% <flour>` is stored as printed (the claims database) and produces **no finding**:
  not a contradiction, not an R4 note, not a side-by-side quote.
- A rule may speak only if the ingredient list shows **another flour** besides the named
  one (e.g. maida next to "100% atta"), and then only by quoting both (D-042).
- `tests/test_claim_rulings.py` holds this: the Doodh label gives no claim finding.

### D-055 · Stop rule for the beta `LOCKED` (2026-09-25)
Gate is W4 retention ≥30% with ≥2.5 scans per returning user. The failure mode is
reaching December with 18% retention and building Phase 2 anyway because the time is
already sunk. **Write the number that makes you stop, now, before the data exists.**

**Decided 2026-09-25** (Sushil delegated), measured on the beta cohort at week 4:

| W4 retention (and scans per returning user) | What happens |
|---|---|
| **≥ 30 %** and **≥ 2.5** | Continue: Phase 2 planning starts |
| **20 - 30 %**, or ≥ 30 % with < 2.5 scans | **One** fix-and-retest cycle, max 4 weeks: fixes to what users report only, no new features; re-measure W4 on a fresh cohort |
| **< 20 %**, or the retest misses 30 % | **Stop.** No Phase 2 build. Rethink the product or the audience from interviews before writing more code |

Measured on at least 50 activated users (one completed scan); fewer than that and the
number is not read as a pass or a fail - recruit more first. Not renegotiable after
the data arrives; a change needs a new D- entry written *before* the next measurement.

---

## Explicitly not building

Airflow (batch tool, wrong for per-scan - use Celery/RQ on Redis) · Snowflake (see
D-021) · vector DB · Elasticsearch · microservices · Kubernetes · native app ·
custom admin platform (use Django admin or Retool; the one custom screen worth
building is the label-image/extracted-data reviewer) · streaks, rewards or scan
credits (incentivise junk scans that poison the catalogue - reward accepted
*corrections* instead) · social sharing infrastructure beyond a PNG share sheet ·
multi-language UI at launch · B2B dashboard in any form before ~500K scans/month ·
brand-submitted data portal · affiliate revenue until a public methodology exists.
