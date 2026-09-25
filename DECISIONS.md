# DECISIONS.md

Architectural and product decisions for InsideLabel, with the reasoning attached.
Append-only. When a decision is reversed, mark it `SUPERSEDED` and add a new entry
rather than editing the old one — the history is the point.

**Last updated:** 2026-09-25 (D-094–D-101 accepted by Sushil and locked)

**Status key:** `LOCKED` decided, don't relitigate · `OPEN` not yet decided ·
`RECOMMENDED` proposed but not accepted · `SUPERSEDED` replaced

---

## Product

### D-001 · Positioning `LOCKED`
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
The unknown is no longer accuracy — it's whether anyone returns in week six. Ship a
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

Revisit at the B2B trigger — Snowflake Secure Data Sharing is genuinely the right
mechanism for selling category intelligence, and enterprise procurement expects it.

### D-022 · dbt models stay dialect-portable `LOCKED`
No `QUALIFY`, `FLATTEN`, `VARIANT` paths, or Snowflake-only functions. Engine-specific
logic lives in macros. `dev` and `ci` targets both on DuckDB from day one — having
`ci` exist is what enforces portability. Makes `dbt-duckdb` → `dbt-snowflake` an
adapter swap, not a rewrite.

### D-023 · No vector database `LOCKED`
`pg_trgm` plus alias tables solve ingredient matching. pgvector inside Postgres later
if free-text consumer questions ever need it.

### D-024 · Barcode is the product key; fingerprints are fallback `LOCKED`
Resolution order: barcode → brand+name+net_qty exact → nutrition fingerprint →
ingredient fingerprint → image embedding. Stop at first confident match. A cached
product costs ~₹0.05/scan and resolves in under a second; an uncached one costs
~₹0.53 and takes 8–15s.

Note the tension with D-025: barcode is the right *key*, but cannot be the primary
*path* at launch because Indian FMCG coverage in existing open databases is thin. The
photo path is primary; the barcode is a cache key built from real usage.

### D-025 · Photo-of-ingredients-panel is the primary path `LOCKED`
Back label first (never blocks the verdict), front of pack second (brand, name,
claims). Single vision call handles both images and returns structured JSON.

### D-026 · Version everything `LOCKED`
Labels change and brands reformulate silently. `product_versions` with
`ingredients_hash` / `nutrition_hash` / `claims_hash`. Model as SCD2
(`valid_from`, `valid_to`, `is_current`) — reformulation alerts and the eventual B2B
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
| R1 | Regulatory numeric — FSSAI Schedule I threshold vs declared nutrition panel |
| R2 | Regulatory non-addition — non-addition claim vs ingredient declaration |
| R3 | Definitional — NOVA Group-4 marker present |
| R4 | Unregulated marketing — claim with no legal definition |
| R5 | Consumer preference — user's stated avoid-list |

### D-041 · NOVA Group-4 is definitional, not scored `LOCKED`
A single marker means ultra-processed regardless of score. The score adds nuance; it
never overturns NOVA.

### D-042 · Wording discipline, enforced in CI `LOCKED`
Allowed: "The label claims X. The declaration says Y." / "Worth checking before
buying." / "X is not a defined claim under Indian regulation."

Forbidden: misleading, false, illegal, non-compliant, violation, lying, toxic,
dangerous, poison — and any statement about the *brand* rather than the *label*.
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
The parent scans 2–4 packs on the shelf; `compare.py` names the best pick of those with
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
"Says 'No added sugar', but contains jaggery." — not "1 claim to check, 3 things worth
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
Resolves D-050 as *remove*. The quick signal is a status per profile: "Contains milk —
on Aarav's avoid list", "Fewer concerns for kids". The 0–100 score stays admin-only for
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
quantity, on the lens intro — not repeated on every screen.

### D-068 · First scans are honest about speed `LOCKED`
Beta scans are mostly cache misses (8–15 s). Show real progress ("Reading ingredients…
found 14") and frame the wait: "First time we've seen this pack. Next time it's instant,
for everyone." The camera screen shows a sample photo of which side to shoot.

### D-069 · Onboarding starts at home `LOCKED`
First run: "Scan 3 packs from your kitchen." Value without a shopping trip, and it seeds
the catalogue with what families actually eat.

### D-070 · "Send it to us" replaces "type it in" `LOCKED`
Amends D-036. After two failed retries: "Send it to us — we'll check this pack and
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
value — calibrate once allergen fields are in the gold set.

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
audience is adults — the app is for parents, not directed at children.

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
₹449/year for (interviews only — nothing built during the beta). Feeds D-053.

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

### D-087 · PostgreSQL 19 `LOCKED` (2026-09-25)
Target PostgreSQL 19. Installed locally as 19~beta4 from the official PostgreSQL apt
repository (`tools/install_pg19.sh`), side by side with 16 (which stays on 5432 until
19 is proven). GA is expected by end of October 2026, before the beta users arrive.

Known costs, accepted: a beta cluster may not start on the next beta/RC/GA binaries if
the catalog version changes, so until GA the local 19 database is treated as disposable
and rebuilt from `migrations/` rather than upgraded. The deployment host (D-080, week 10)
must offer 19; if it doesn't by then, the schema stays portable to 16–18 (the DB tests
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
  similar or equivalent manual process… access, acquire, copy" wording — not read
  first-hand. **Blinkit** returns 403 to scripted requests; a search excerpt (from its
  Bistro terms) says copying or storing platform content "in whole or part is prohibited
  without the express prior written consent of Blinkit" — not read first-hand. Check
  both in a browser before quoting them publicly.
- **The data is required but not reliable.** FSSAI's advisory to e-commerce FBOs
  (3 Dec 2024) requires mandatory label information to be shown pre-sale and matched
  to the physical label — issued because listings often don't match. A listing is a
  claim about a pack, not the pack.
- **Open Food Facts** has 23,156 products tagged India (2026-09-25), under ODbL:
  fine as test input and as a list of *which* products to prioritise; ingesting its
  records into the shipped catalogue likely makes the catalogue share-alike, which
  collides with D-029.

Recommendation:
1. **Don't scrape or copy listings** — terms breach, takedown and account-ban risk,
   and a catalogue built on it is not an asset we own (D-029).
2. **Move D-077 (share target) into the beta.** A user shares a Blinkit/Zepto/Amazon
   product screenshot into InsideLabel; the existing photo path reads it; it goes to
   review like any scan (D-028). Same data, user-initiated, demand-driven. Results
   from a listing are labelled "read from an online listing — check your pack".
3. **Seed by photographing real packs** (D-058: 15 kids' biscuits first), using OFF
   barcodes/names only to choose which packs to buy.
4. **Ask GS1 India about brand-owner product data** (GTIN-keyed, supplied by the
   brand) — terms and cost unknown; worth one email.

Needs Sushil's acceptance; D-077/D-083 ("after W4") change if accepted.

Accepted by Sushil 2026-09-25 ("it's not allowed"); how listings are used is D-089.

### D-089 · A listing is a lead; the physical label is the record `LOCKED` (2026-09-25)
Proposed by Sushil. Marketplace screenshots (Flipkart, Amazon, Blinkit, Zepto, Swiggy
Instamart…) are collected by hand as **research evidence** of which products to add —
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
  generative model). Accepted for the reason D-034 exists — a model can't catch its
  own omission; a separate reader can.
- Cost (Google pricing page, 2026-09-25): first 1,000 units/month free, then $1.50 per
  1,000 (~13 paise a photo). Closed beta fits in the free tier. Billing must be on
  even for the free tier. Photos already go to Google for Gemini; the privacy policy
  must name Cloud Vision too (§8 item 9). Check Google's data-use terms before launch.

**Baseline to beat** (`tools/compare_ocr.py`, 6 gold back photos, WSL): Tesseract
19.7 s per label for the INS check alone (6.5–29.3 s), recall **27/52** printed INS
(Britannia 3/12, Limca 2.25 L 1/5), **0** wrong additions. Switch on if Cloud Vision
is faster with recall ≥ Tesseract on every label and still 0 wrong additions.

**Result** (same photos, same run, after the fix below):

| | Tesseract | Cloud Vision |
|---|---|---|
| INS check, mean per label | 22.7 s | **3.6 s** |
| Printed INS found | 27/52 | **50/52**, ≥ Tesseract on every label |
| Simulated omissions put back (drop each additive from Gemini's read) | — | **49/51** |
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
  sends the refused scans' ids to `POST /send-to-us`; the server checks them —
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

---

## Open and pending

### D-050 · Numeric score in the consumer UI `SUPERSEDED by D-064` (removed)
The prototype currently shows a 0–100 score, an A–E grade, *and* "Risk Index 7.2/10" —
three renderings of the same `{none:0, low:4, moderate:12, high:25}` table. One decimal
of implied precision on arbitrary weights is the easiest thing for a lawyer or
journalist to dismantle, and it contradicts the stated "no single health score"
principle.

Proposal: keep the three-band verdict (defensible because the ultra-processed band is
definitional), show flag counts by severity, move the score to admin-only for ranking
alternatives and regression-testing rule changes. **Not yet decided.**

### D-051 · Claim checker in the beta `LOCKED` (2026-09-25): ship in shadow, switch on when measured
The claim checker has never fired on a real front-of-pack claim. Shipping it requires
pairing attestation + a rebuilt rule set + FSSAI Schedule I retrieval — roughly 3
extra weeks. Deferring means the beta tests the commodity half (ingredient
explanation) and the resulting retention number is a **floor, not a forecast**.
~~**Not yet decided.**~~

**Decided 2026-09-25** (Sushil delegated: "go with your best decision"): neither defer
nor ship blind — **ship in shadow**. The checker is built, pairing attestation (D-035)
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
natural frequency at 2–4 scans/month. Allergen and diabetic households have a forcing
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
Original thinking was ₹49–99/month. Recommendation is ₹399–499/**year** — Indian
consumer utilities convert far better on annual, and matches a product used a few
times a month rather than daily. Also: scans stay uncapped and free forever
(throttling scans starves the catalogue, which is the asset). **Not yet decided.**

### D-054 · The "100% ATTA" ruling `OPEN`
Patanjali Doodh Biscuits declares `Wheat flour (Atta) 58.3%` while the front says
`100% ATTA`. Likely manufacturer intent is "the flour is atta, not maida" rather than
"the product is 100% atta". Must be decided deliberately before any rule fires,
because it names a brand with active advertising-claim litigation history.

### D-055 · Stop rule for the beta `LOCKED` (2026-09-25)
Gate is W4 retention ≥30% with ≥2.5 scans per returning user. The failure mode is
reaching December with 18% retention and building Phase 2 anyway because the time is
already sunk. **Write the number that makes you stop, now, before the data exists.**

**Decided 2026-09-25** (Sushil delegated), measured on the beta cohort at week 4:

| W4 retention (and scans per returning user) | What happens |
|---|---|
| **≥ 30 %** and **≥ 2.5** | Continue: Phase 2 planning starts |
| **20 – 30 %**, or ≥ 30 % with < 2.5 scans | **One** fix-and-retest cycle, max 4 weeks: fixes to what users report only, no new features; re-measure W4 on a fresh cohort |
| **< 20 %**, or the retest misses 30 % | **Stop.** No Phase 2 build. Rethink the product or the audience from interviews before writing more code |

Measured on at least 50 activated users (one completed scan); fewer than that and the
number is not read as a pass or a fail — recruit more first. Not renegotiable after
the data arrives; a change needs a new D- entry written *before* the next measurement.

---

## Explicitly not building

Airflow (batch tool, wrong for per-scan — use Celery/RQ on Redis) · Snowflake (see
D-021) · vector DB · Elasticsearch · microservices · Kubernetes · native app ·
custom admin platform (use Django admin or Retool; the one custom screen worth
building is the label-image/extracted-data reviewer) · streaks, rewards or scan
credits (incentivise junk scans that poison the catalogue — reward accepted
*corrections* instead) · social sharing infrastructure beyond a PNG share sheet ·
multi-language UI at launch · B2B dashboard in any form before ~500K scans/month ·
brand-submitted data portal · affiliate revenue until a public methodology exists.
