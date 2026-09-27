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

### D-110 · The website takes the Lovable look, not the Lovable app `LOCKED` (2026-09-26)
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

### D-053 · Premium pricing `OPEN`
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
