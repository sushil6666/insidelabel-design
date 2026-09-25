import React, { useState, useMemo } from "react";

/*
  Inside Label — Phase 1 scan-result prototype
  =============================================
  The engine logic (engine.py) ported to JS so this runs standalone.
  Same three layers: per-ingredient flags -> score -> binary verdict.
  NOVA markers are definitional (override "clean"). Nothing here is
  monetized; this is the honest core that earns trust and generates
  the scan catalog Phase 2 (Smart Swap) will read from.

  Design note: deliberately NOT the cream/terracotta AI-default palette.
  Ink-and-signal identity — near-black paper, a single confident signal
  colour per verdict band, a monospace data face for the traceable facts
  (because the whole promise is "here are the receipts").
*/

// ---- data (trimmed port of the JSON tables) ----
const NOVA_MARKERS = {
  "invert sugar": { name: "Invert sugar", cat: "industrial sweetener" },
  "invert syrup": { name: "Invert sugar", cat: "industrial sweetener" },
  maltodextrin: { name: "Maltodextrin", cat: "industrial carb" },
  "glucose syrup": { name: "Glucose syrup", cat: "industrial sweetener" },
  "liquid glucose": { name: "Glucose syrup", cat: "industrial sweetener" },
  "hydrolysed vegetable protein": { name: "Hydrolysed protein", cat: "protein isolate" },
  "hydrolysed protein": { name: "Hydrolysed protein", cat: "protein isolate" },
  "soy protein isolate": { name: "Soy protein isolate", cat: "protein isolate" },
  "hydrogenated oil": { name: "Hydrogenated oil", cat: "modified fat" },
  vanaspati: { name: "Hydrogenated oil", cat: "modified fat" },
  "modified starch": { name: "Modified starch", cat: "modified carb" },
  flavour: { name: "Added flavour", cat: "cosmetic additive" },
  flavor: { name: "Added flavour", cat: "cosmetic additive" },
  "artificial flavour": { name: "Added flavour", cat: "cosmetic additive" },
  "natural flavour": { name: "Added flavour", cat: "cosmetic additive" },
  emulsifier: { name: "Emulsifier", cat: "cosmetic additive" },
  colour: { name: "Added colour", cat: "cosmetic additive" },
  color: { name: "Added colour", cat: "cosmetic additive" },
  stabiliser: { name: "Stabiliser", cat: "cosmetic additive" },
  thickener: { name: "Thickener", cat: "cosmetic additive" },
};

const ADDITIVES = {
  "102": { name: "Tartrazine", cls: "colour", concern: "moderate", why: "Synthetic azo dye. Linked to hyperactivity in sensitive children (Southampton). EU requires a warning label.", src: ["Southampton", "EU"], nova: true },
  "110": { name: "Sunset Yellow FCF", cls: "colour", concern: "moderate", why: "Synthetic azo dye. Southampton hyperactivity link. EU warning label required.", src: ["Southampton", "EU"], nova: true },
  "150d": { name: "Sulphite ammonia caramel", cls: "colour", concern: "low", why: "Caramel colour class IV. Contains 4-MEI (IARC 2B) at high exposure. Common in colas.", src: ["WHO"], nova: true },
  "171": { name: "Titanium dioxide", cls: "colour", concern: "high", why: "Whitening colour. Banned as a food additive in the EU since 2022 (genotoxicity not ruled out).", src: ["EU"], nova: true, verify: true },
  "202": { name: "Potassium sorbate", cls: "preservative", concern: "low", why: "Common preservative. Low concern, but invalidates any 'no preservatives' claim.", src: ["FSSAI"] },
  "211": { name: "Sodium benzoate", cls: "preservative", concern: "moderate", why: "Preservative. With vitamin C can form benzene. Southampton study pairing.", src: ["Southampton", "FSSAI"] },
  "250": { name: "Sodium nitrite", cls: "preservative", concern: "high", why: "Curing agent in processed meats. Nitrosamine formation; processed meat is IARC Group 1.", src: ["WHO"] },
  "322": { name: "Lecithin", cls: "emulsifier", concern: "low", why: "Common emulsifier (often soy). Ultra-processing marker but low safety concern.", src: ["FSSAI"], nova: true },
  "471": { name: "Mono- & diglycerides", cls: "emulsifier", concern: "low", why: "Very common emulsifier. Ultra-processing marker. May carry trans fats depending on source.", src: ["FSSAI"], nova: true },
  "621": { name: "Monosodium glutamate (MSG)", cls: "flavour enhancer", concern: "moderate", why: "Flavour enhancer. Permitted; some report sensitivity. Not permitted in infant food. Signals industrial formulation.", src: ["FSSAI", "WHO"], nova: true },
  "627": { name: "Disodium guanylate", cls: "flavour enhancer", concern: "low", why: "Flavour enhancer, usually paired with MSG. Signals industrial formulation.", src: ["FSSAI"], nova: true },
  "631": { name: "Disodium inosinate", cls: "flavour enhancer", concern: "low", why: "Flavour enhancer, paired with MSG. Signals industrial formulation.", src: ["FSSAI"], nova: true },
  "635": { name: "Disodium ribonucleotides", cls: "flavour enhancer", concern: "low", why: "Flavour enhancer blend. Signals industrial formulation.", src: ["FSSAI"], nova: true },
  "407": { name: "Carrageenan", cls: "thickener", concern: "moderate", why: "Seaweed thickener. Some studies suggest gut inflammation (contested).", src: ["WHO"], nova: true },
  "412": { name: "Guar gum", cls: "thickener", concern: "low", why: "Thickener. Low concern.", src: ["FSSAI"] },
  "951": { name: "Aspartame", cls: "sweetener", concern: "moderate", why: "Artificial sweetener. IARC 'possibly carcinogenic' (2B, 2023). Not for PKU.", src: ["WHO"], nova: true },
  "950": { name: "Acesulfame potassium", cls: "sweetener", concern: "moderate", why: "Artificial sweetener. Ultra-processing marker.", src: ["WHO", "FSSAI"], nova: true },
  "955": { name: "Sucralose", cls: "sweetener", concern: "moderate", why: "Artificial sweetener. WHO advises against non-sugar sweeteners for weight control.", src: ["WHO"], nova: true },
  "500": { name: "Sodium bicarbonate", cls: "raising agent", concern: "none", why: "Baking soda. No concern.", src: ["FSSAI"] },
  "330": { name: "Citric acid", cls: "acidity regulator", concern: "none", why: "Ubiquitous acidity regulator. No safety concern.", src: ["FSSAI"] },
  "965": { name: "Maltitol", cls: "sweetener", concern: "moderate", why: "Sugar alcohol sweetener. Its glycemic impact is generally lower than table sugar's, but not zero — despite 'sugar-free' labelling it can still raise blood glucose somewhat, and larger amounts can cause digestive upset.", src: [], nova: true },
};

const NAMED = {
  aspartame: "951", sucralose: "955", tartrazine: "102", msg: "621",
  "monosodium glutamate": "621", carrageenan: "407", lecithin: "322",
  "sodium benzoate": "211", "potassium sorbate": "202", "guar gum": "412",
  "citric acid": "330", "titanium dioxide": "171", "sodium nitrite": "250",
  maltitol: "965",
};

const SUGAR_ALIASES = new Set([
  "sugar", "sucrose", "cane sugar", "brown sugar", "invert sugar", "invert syrup",
  "glucose", "glucose syrup", "liquid glucose", "dextrose", "fructose",
  "high fructose corn syrup", "hfcs", "maltose", "maltodextrin", "honey",
  "molasses", "malt extract", "jaggery", "gur", "fruit juice concentrate",
]);

const PENALTY = { none: 0, low: 4, moderate: 12, high: 25 };

// ---- engine (ported) ----
function extractIns(t) {
  let m = t.match(/(?:ins|e)[\s\-.]*?(\d{3}[a-z]?)/i);
  if (m) return m[1].toLowerCase();
  m = t.match(/^(\d{3}[a-z]?)$/);
  return m ? m[1].toLowerCase() : null;
}

function tokenize(raw) {
  raw = raw.replace(/allergen[s]?.*$/i, "");
  const parts = raw.split(/[,;.\n]/);
  const out = [];
  for (const p of parts) {
    const inner = [...p.matchAll(/[([]([^)\]]*)[)\]]/g)].map((x) => x[1]);
    const base = p.replace(/[([][^)\]]*[)\]]/g, "");
    for (const chunk of [base, ...inner]) {
      for (const sub of chunk.split(/[,;]/)) {
        const t = sub.trim().toLowerCase().replace(/\s+/g, " ");
        if (t && !/^[\d\s%.]+$/.test(t)) out.push(t);
      }
    }
  }
  return out;
}

// Found via real-product testing on the same "Diabetic Friendly" biscuit —
// "Soya Protein Isolate" (the standard Indian spelling) wasn't matching
// "soy protein isolate" in NOVA_MARKERS at all. Indian labels use "soya"
// almost universally (soya bean oil, soya lecithin, soya chunks, soya
// milk), so this would have silently missed all of them, not just this
// one product. Normalized for matching only — the displayed ingredient
// text keeps the label's original spelling.
function novaFor(t) {
  const norm = t.replace(/\bsoya\b/g, "soy");
  if (NOVA_MARKERS[t]) return NOVA_MARKERS[t];
  if (NOVA_MARKERS[norm]) return NOVA_MARKERS[norm];
  for (const k in NOVA_MARKERS) if (t.includes(k) || norm.includes(k)) return NOVA_MARKERS[k];
  return null;
}

function classify(t) {
  const ins = extractIns(t);
  if (ins && ADDITIVES[ins]) {
    const a = ADDITIVES[ins];
    return { ingredient: t, matched: `INS ${ins} · ${a.name}`, concern: a.concern, why: a.why, src: a.src, verify: a.verify, nova: !!a.nova };
  }
  for (const k in NAMED) {
    if (t === k || t.includes(k)) {
      const a = ADDITIVES[NAMED[k]];
      return { ingredient: t, matched: `${a.name} · INS ${NAMED[k]}`, concern: a.concern, why: a.why, src: a.src, verify: a.verify, nova: !!a.nova };
    }
  }
  if (t.includes("caffeine")) {
    return { ingredient: t, matched: "Caffeine", concern: "low", why: "Stimulant. Not itself an additive concern for most adults, but relevant for children and for anyone on heart-rate or blood-pressure medication.", src: ["FSSAI"], nova: false };
  }
  // Found via real-product testing (Britannia NutriChoice "Diabetic Friendly"
  // biscuits, Sept 2026) — maltodextrin was falling into the generic NOVA
  // "industrial carb" bucket with no glycemic-index framing, which
  // understated the single most relevant fact about it for anyone managing
  // blood sugar. Given its own dedicated fact instead of the generic path.
  if (t.includes("maltodextrin")) {
    return { ingredient: t, matched: "Maltodextrin", concern: "moderate", why: "A rapidly-digested industrial carbohydrate with a glycemic index around 85-105 — higher than table sugar's ~65 — despite not being labelled as 'sugar' on the ingredient list. Commonly used as a cheap filler or thickener. (Atkinson et al., International Tables of Glycemic Index and Glycemic Load Values, Diabetes Care, 2008.)", src: [], nova: true };
  }
  const nv = novaFor(t);
  if (nv) {
    return { ingredient: t, matched: `NOVA marker · ${nv.name}`, concern: nv.cat === "cosmetic additive" ? "low" : "moderate", why: `Ultra-processing marker (${nv.cat}). Rarely used in home cooking; signals industrial formulation.`, src: ["NOVA"], nova: true };
  }
  return null;
}

// ---- age lens (segment layer — reads the SAME flags, never changes them) ----
// Buckets an already-classified flag into a category so age rules can apply
// without a second classification pass. This is deliberately keyword-based
// on the engine's own output, so it can never contradict the ingredient facts.
function bucketOf(f) {
  const s = (f.matched + " " + f.why).toLowerCase();
  if (s.includes("caffeine")) return "stimulant";
  if (s.includes("maltodextrin") || s.includes("glycemic index")) return "highGlycemicCarb";
  if (s.includes("colour") || s.includes("color")) return "colour";
  if (s.includes("sweetener")) return "sweetener";
  if (s.includes("flavour enhancer") || s.includes("flavor enhancer") || s.includes("msg") || s.includes("glutamate")) return "flavourEnhancer";
  if (s.includes("hydrogenated")) return "modifiedFat";
  if (s.includes("hydrolysed") || s.includes("protein isolate") || s.includes("protein hydrolysate")) return "proteinIsolate";
  if (s.includes("preservative") || s.includes("benzoate") || s.includes("nitrite") || s.includes("sorbate")) return "preservative";
  if (s.includes("emulsifier")) return "emulsifierCosmetic";
  if (s.includes("thickener") || s.includes("stabiliser") || s.includes("stabilizer")) return "thickenerCosmetic";
  return "other";
}

// level: 'avoid' | 'caution' | 'ok'. Notes are ingredient-relevance, never
// a prescription — no dosing, no "safe for X condition" claims.
const PROFILES = [
  { id: "toddler", label: "Toddler", sub: "1-3 yrs" },
  { id: "kid", label: "Kids", sub: "4-11" },
  { id: "young", label: "Young", sub: "12-35" },
  { id: "adult", label: "Adult", sub: "36-59" },
  { id: "older", label: "Older Adult", sub: "60+" },
];

// NOTE on "young" (12-35): this is a wide, requested band spanning
// still-growing teens through fully mature adults. Rather than invent
// false precision, it mirrors Adult defaults everywhere EXCEPT caffeine,
// which stays at "caution" (not "ok") because the lower end of the range
// includes minors. If real differentiation is needed later, split into
// Teen (12-17) / Young Adult (18-35) rather than stretching this further.
const AGE_RULES = {
  highGlycemicCarb: {
    toddler: ["avoid", "Rapidly-absorbed carbohydrates like maltodextrin spike blood sugar quickly and offer no nutritional benefit for a toddler — best avoided.", []],
    kid: ["caution", "A quickly-absorbed industrial carbohydrate — not a specific danger, but not a nutritional plus either.", []],
    young: ["caution", "Rapidly absorbed carbohydrate; mainly relevant if managing blood sugar.", []],
    adult: ["caution", "Rapidly absorbed carbohydrate; mainly relevant if managing blood sugar.", []],
    older: ["caution", "Rapidly absorbed carbohydrate — worth noting if managing blood sugar or diabetes risk.", []],
  },
  colour: {
    toddler: ["avoid", "Synthetic colours have no nutritional role and are best kept out of a toddler's diet — early paediatric guidance generally recommends minimising them.", ["Southampton study"]],
    kid: ["avoid", "Synthetic colours are linked to hyperactivity in sensitive children.", ["Southampton study"]],
    young: ["caution", "Permitted; whether to avoid synthetic colour is mostly a personal-preference call.", ["FSSAI"]],
    adult: ["caution", "Permitted; whether to avoid synthetic colour is mostly a personal-preference call for adults.", ["FSSAI"]],
    older: ["caution", "No specific age-related risk beyond general additive load.", ["FSSAI"]],
  },
  sweetener: {
    toddler: ["avoid", "No sweetener, natural or artificial, is considered necessary in a toddler's diet — this is also when taste preferences are forming, so less-sweet defaults matter.", ["ICMR-NIN"]],
    kid: ["avoid", "Children have no nutritional need for artificial sweeteners; naturally sweet whole foods are the better default.", ["ICMR-NIN"]],
    young: ["caution", "Advises against relying on non-sugar sweeteners for weight management.", ["WHO"]],
    adult: ["caution", "Advises against relying on non-sugar sweeteners for weight management.", ["WHO"]],
    older: ["caution", "If managing diabetes, sweetener choice is a case-by-case decision — worth a conversation with a doctor rather than a blanket swap.", []],
  },
  flavourEnhancer: {
    toddler: ["avoid", "Flavour enhancers like MSG are not permitted in food intended for infants, and there's no reason to introduce them to a toddler's palate either.", ["FSSAI"]],
    kid: ["avoid", "Flavour enhancers like MSG are not permitted in food intended for infants; caution is generally advised for young children too.", ["FSSAI"]],
    young: ["ok", "Permitted and well tolerated by most people; a minority report sensitivity.", ["FSSAI"]],
    adult: ["ok", "Permitted and well tolerated by most adults; a minority report sensitivity.", ["FSSAI"]],
    older: ["caution", "Often paired with high sodium in the same product — worth noting if managing blood pressure.", []],
  },
  preservative: {
    toddler: ["avoid", "Toddler guidance generally favours minimally processed, freshly prepared food over preserved packaged food wherever practical.", ["ICMR-NIN"]],
    kid: ["caution", "Some preservatives showed a hyperactivity link when paired with synthetic colours.", ["Southampton study"]],
    young: ["ok", "Permitted; low concern at typical intake.", ["FSSAI"]],
    adult: ["ok", "Permitted; low concern for most adults at typical intake.", ["FSSAI"]],
    older: ["caution", "Preservative intake adds up with frequent packaged-food consumption — worth mentioning at a check-up if that's a regular pattern.", []],
  },
  stimulant: {
    toddler: ["avoid", "Caffeine has no place in a toddler's diet.", ["AAP"]],
    kid: ["avoid", "Caffeine is generally not recommended for children.", ["AAP"]],
    young: ["caution", "Fine in moderation for adults in this range, but this band includes minors, so caution rather than a flat OK.", ["AAP"]],
    adult: ["ok", "Fine in moderation for most adults.", []],
    older: ["caution", "Can interact with heart-rate or blood-pressure medication — worth checking with a doctor if that applies.", []],
  },
  proteinIsolate: {
    toddler: ["caution", "Whole-food protein (dal, milk, egg, curd) is the better everyday default for a toddler over industrial protein isolates.", []],
    kid: ["caution", "A marker of heavy industrial processing rather than a specific safety issue — whole-food protein is the better everyday default for kids.", []],
    young: ["ok", "Common in packaged food; not a specific health concern on its own.", []],
    adult: ["ok", "Common in packaged food; not a specific health concern on its own.", []],
    older: ["ok", "No specific age-related concern beyond general processing level.", []],
  },
  modifiedFat: {
    // India-first: FSSAI's own 2% cap (binding law this product operates
    // under) leads; WHO's global campaign is secondary context.
    toddler: ["avoid", "FSSAI caps industrial trans fat at 2% in Indian food products — hydrogenated oils are still worth avoiding entirely in early childhood regardless of the legal limit, when a child's food choices are most shaped.", ["FSSAI_TRANSFAT", "WHO_TRANSFAT"]],
    kid: ["avoid", "FSSAI caps industrial trans fat at 2% in Indian food products; hydrogenated oils can still carry meaningful trans fat — worth avoiding for growing children where a cleaner option exists.", ["FSSAI_TRANSFAT", "WHO_TRANSFAT"]],
    young: ["caution", "FSSAI caps industrial trans fat at 2% in Indian food products — worth checking the label specifically for trans fat content regardless.", ["FSSAI_TRANSFAT"]],
    adult: ["caution", "FSSAI caps industrial trans fat at 2% in Indian food products — worth checking the label specifically for trans fat content regardless.", ["FSSAI_TRANSFAT"]],
    older: ["avoid", "Trans fats are a recognised cardiovascular risk factor — best minimised even within FSSAI's permitted limit.", ["FSSAI_TRANSFAT", "WHO_TRANSFAT"]],
  },
  emulsifierCosmetic: {
    toddler: ["caution", "Low individual concern, but a signal to prefer simpler, less-processed foods where a fresh alternative exists.", []],
    kid: ["ok", "Common and generally low concern at typical intake.", []],
    young: ["ok", "Common and generally low concern.", []],
    adult: ["ok", "Common and generally low concern.", []],
    older: ["ok", "Common and generally low concern.", []],
  },
  thickenerCosmetic: {
    toddler: ["caution", "Low individual concern, but a signal to prefer simpler, less-processed foods where a fresh alternative exists.", []],
    kid: ["ok", "Common and generally low concern.", []],
    young: ["ok", "Common and generally low concern.", []],
    adult: ["ok", "Common and generally low concern.", []],
    older: ["ok", "Common and generally low concern.", []],
  },
  other: {
    toddler: ["caution", "Signals industrial processing — a good reason to prefer a fresher, simpler alternative for a toddler where one's available.", []],
    kid: ["caution", "Signals industrial processing — worth a second look, even without a specific safety flag.", []],
    young: ["ok", "Generally permitted at typical intake.", []],
    adult: ["ok", "Generally permitted at typical intake.", []],
    older: ["ok", "Generally permitted at typical intake.", []],
  },
};

function lensFor(flag, profileId) {
  const bucket = bucketOf(flag);
  const [level, note, src] = AGE_RULES[bucket][profileId];
  return { bucket, level, note, src: src || [] };
}

// ---- goal lens (weight direction — same architecture, no body metrics) ----
// Deliberately no BMI, no calorie math, no numeric targets anywhere here.
// This re-labels the SAME flags by relevance to a stated direction; it
// never changes the score or the underlying ingredient facts.
// Profile metadata only. There's no defensible ingredient-chemistry reason
// for the additives this engine tracks (colours, preservatives, sweeteners,
// MSG, trans fats, caffeine) to carry a different verdict by gender identity
// — so this field is NOT read by lensFor/goalLensFor and never changes any
// guidance shown below. Kept for your own profile/analytics use. The
// medically-grounded personalization (where real ingredient-avoid guidance
// does exist) is reproductive status — a Pregnancy/Breastfeeding toggle —
// not gender; that's a separate feature, not built here yet.
const GENDERS = [
  { id: "male", label: "Male" },
  { id: "female", label: "Female" },
  { id: "transgender", label: "Transgender" },
  { id: "unspecified", label: "Prefer not to say" },
];

const GOALS = [
  { id: "none", label: "No goal set" },
  { id: "lose", label: "Lose weight" },
  { id: "maintain", label: "Maintain" },
  { id: "gain", label: "Gain weight" },
];

const GOAL_RULES = {
  highGlycemicCarb: {
    lose: ["avoid", "Spikes blood sugar and insulin quickly with little satiety — one of the least useful carbs to include when cutting calories.", []],
    maintain: ["caution", "A rapidly-absorbed carbohydrate; fine occasionally, not a staple.", []],
    gain: ["caution", "Adds quick calories but little nutritional value — whole-food carbs are a better source of the calories you want.", []],
  },
  colour: {
    lose: ["caution", "No calories itself, but tends to mark a processed/packaged choice over a whole-food one.", []],
    maintain: ["caution", "Not calorie-relevant; a marker of processing level.", []],
    gain: ["ok", "Not calorie-relevant either way.", []],
  },
  sweetener: {
    lose: ["caution", "Advises against relying on non-sugar sweeteners for weight control — they haven't been shown to help long-term.", ["WHO"]],
    maintain: ["caution", "Low-calorie, but not a substitute for whole-food eating patterns.", ["WHO"]],
    gain: ["avoid", "Displaces calories and nutrients you'd want from real food when the goal is gaining.", []],
  },
  flavourEnhancer: {
    lose: ["caution", "A marker of processed formulation rather than a calorie concern on its own.", []],
    maintain: ["ok", "Not calorie-relevant.", []],
    gain: ["ok", "Not calorie-relevant.", []],
  },
  modifiedFat: {
    lose: ["avoid", "Calorie-dense, and may carry trans fat even within FSSAI's 2% legal cap — one of the higher-impact things to limit when cutting calories.", ["FSSAI_TRANSFAT"]],
    maintain: ["caution", "Trans fat is worth limiting regardless of weight goal, even within FSSAI's permitted 2% cap.", ["FSSAI_TRANSFAT"]],
    gain: ["caution", "Adds calories, but trans fat is still worth limiting — prefer calorie-dense whole foods (nuts, dairy, oils) instead.", ["FSSAI_TRANSFAT"]],
  },
  proteinIsolate: {
    lose: ["ok", "Protein supports satiety, which can help with a calorie-reduction goal.", ["ICMR-NIN"]],
    maintain: ["ok", "Neutral to helpful — protein is a useful part of a balanced pattern.", []],
    gain: ["ok", "Protein content is generally useful when the goal is gaining.", ["ICMR-NIN"]],
  },
  preservative: {
    lose: ["ok", "Not calorie-relevant.", []],
    maintain: ["ok", "Not calorie-relevant.", []],
    gain: ["ok", "Not calorie-relevant.", []],
  },
  stimulant: {
    lose: ["ok", "Not calorie-relevant on its own.", []],
    maintain: ["ok", "Not calorie-relevant.", []],
    gain: ["ok", "Not calorie-relevant.", []],
  },
  emulsifierCosmetic: {
    lose: ["ok", "Not calorie-relevant.", []],
    maintain: ["ok", "Not calorie-relevant.", []],
    gain: ["ok", "Not calorie-relevant.", []],
  },
  thickenerCosmetic: {
    lose: ["ok", "Not calorie-relevant.", []],
    maintain: ["ok", "Not calorie-relevant.", []],
    gain: ["ok", "Not calorie-relevant.", []],
  },
  other: {
    lose: ["caution", "A general processing marker — worth a second look when prioritising whole foods.", []],
    maintain: ["ok", "Generally fine as part of a balanced pattern.", []],
    gain: ["ok", "Generally fine as part of a balanced pattern.", []],
  },
};

function goalLensFor(flag, goalId) {
  const bucket = bucketOf(flag);
  const [level, note, src] = GOAL_RULES[bucket][goalId];
  return { bucket, level, note, src: src || [] };
}

// General, non-personalized food-category guidance. No calories, no
// macros, no numeric targets — that's a dietitian's job, not this app's.
// Sourced at the level of public dietary guidance (e.g. ICMR-NIN pattern),
// meant to be read once per goal, not generated per scan.
const GOAL_GUIDANCE = {
  lose: {
    eat: ["Whole vegetables, fruit, and legumes", "Minimally processed protein (dal, eggs, curd, fish, chicken)", "Whole grains over refined flour (maida)"],
    avoid: ["Sugary drinks and packaged juices", "Deep-fried packaged snacks", "Products where sugar appears under 2+ names on the label"],
  },
  maintain: {
    eat: ["A balance across food groups — grains, protein, vegetables, dairy", "Home-cooked meals as the default, packaged food as the occasional exception"],
    avoid: ["Frequent ultra-processed snacking between meals", "Sugary beverages as a daily habit"],
  },
  gain: {
    eat: ["Nutrient-dense whole foods: nuts, seeds, dairy, legumes, eggs, meat/fish", "Healthy fats in moderation: ghee, oils, nut butters", "Regular, frequent meals rather than large infrequent ones"],
    avoid: ["Relying on sugary or fried packaged snacks as your main extra calories", "Products high in trans fat (hydrogenated oil) as a calorie source"],
  },
};

// ---- pregnancy / breastfeeding lens ----
// This is the one segment where real, sourced ingredient-level guidance
// exists (unlike gender — see the GENDERS note above). Kept deliberately
// conservative: general public-health guidance only (e.g. the commonly
// cited "keep caffeine under ~200mg/day in pregnancy" figure appears in
// NHS/ACOG-style guidance and is stated as guidance, not a personal
// target). Never a diagnosis, never a numeric meal plan. The "preservative"
// bucket here lumps nitrite-based curing agents (the actual pregnancy
// concern, via nitrosamines) together with benign preservatives like
// potassium sorbate — a known simplification of the starter database;
// worth a dedicated "curing agent" bucket if this ships for real.
const REPRO = [
  { id: "none", label: "Not applicable" },
  { id: "pregnant", label: "Pregnant" },
  { id: "breastfeeding", label: "Breastfeeding" },
];

const REPRO_RULES = {
  highGlycemicCarb: {
    pregnant: ["caution", "A rapidly-absorbed carbohydrate that can spike blood sugar — worth noting particularly if you've been screened for gestational diabetes.", []],
    breastfeeding: ["ok", "Not a specific concern while breastfeeding.", []],
  },
  colour: {
    pregnant: ["caution", "No specific restriction on synthetic colours in pregnancy, but general prenatal guidance favours whole foods over processed/coloured ones where practical.", ["ICMR-NIN"]],
    breastfeeding: ["caution", "No specific restriction while breastfeeding; same general preference for whole foods applies.", ["ICMR-NIN"]],
  },
  sweetener: {
    pregnant: ["caution", "Most non-sugar sweeteners are considered acceptable in moderation during pregnancy; saccharin is the one most commonly singled out for limiting — check with your doctor if you're unsure which sweetener this is.", ["FSSAI", "ACOG"]],
    breastfeeding: ["caution", "Most non-sugar sweeteners are considered compatible with breastfeeding in moderation — check with your doctor for anything specific to you.", ["FSSAI", "CDC"]],
  },
  flavourEnhancer: {
    pregnant: ["caution", "No established pregnancy-specific restriction, but it's a marker of processed food — worth moderating as part of a whole-food-first approach.", []],
    breastfeeding: ["ok", "No established restriction while breastfeeding.", []],
  },
  preservative: {
    // NOTE: "NHS" here is still a bare, unverified institution name — a
    // different claim (nitrite/cured meat) from the NHS caffeine document
    // that IS verified above. It correctly renders as plain text, not a
    // link, until this specific claim is checked against a real document.
    pregnant: ["caution", "Nitrite-based preservatives in cured/processed meats are the specific one prenatal guidance often flags (nitrosamine formation) — worth checking exactly which preservative this is.", ["NHS"]],
    breastfeeding: ["ok", "No established restriction while breastfeeding at typical intake.", []],
  },
  stimulant: {
    // Verified against real sources (checked Sept 2026). India-first
    // ordering: WHO's own antenatal care guideline (a body India directly
    // references) recommends staying under 300mg/day — cited as primary.
    // NHS's stricter 200mg/day is real and current, but it's a single
    // country's health service; kept as clearly-labeled secondary context
    // rather than presented as the default. ACOG's position is softer
    // still — "moderate caffeine (<200mg/day) doesn't appear to be a major
    // factor in miscarriage or preterm birth" — an absence-of-evidence-of-
    // harm framing, not a matching directive, so stated on its own rather
    // than merged into either number.
    pregnant: ["caution", "WHO's antenatal care guideline recommends staying under 300mg of caffeine a day during pregnancy. Some national bodies are stricter — the UK's NHS advises under 200mg/day, while ACOG notes moderate caffeine under 200mg/day doesn't appear to be a major factor in miscarriage or preterm birth. Worth counting this against your other caffeine sources that day.", ["WHO_ANC", "NHS_CAFFEINE"]],
    breastfeeding: ["caution", "Moderate caffeine is generally considered compatible with breastfeeding; still worth tracking total daily intake across sources, as some passes into breast milk.", ["CDC"]],
  },
  proteinIsolate: {
    pregnant: ["ok", "Protein needs increase in pregnancy; whole-food sources are preferable day-to-day, but isolates aren't a specific concern.", ["ICMR-NIN"]],
    breastfeeding: ["ok", "Protein needs remain elevated while breastfeeding; not a specific concern.", ["ICMR-NIN"]],
  },
  modifiedFat: {
    // India-first: FSSAI's own 2% cap leads; WHO's global campaign is secondary.
    pregnant: ["avoid", "FSSAI caps industrial trans fat at 2% in Indian food products; trans fat is broadly advised against during pregnancy regardless, relevant to both cardiovascular health and fetal development.", ["FSSAI_TRANSFAT", "WHO_TRANSFAT"]],
    breastfeeding: ["caution", "Worth limiting as part of general heart-healthy eating, even within FSSAI's permitted 2% cap; no specific lactation mandate beyond that.", ["FSSAI_TRANSFAT"]],
  },
  emulsifierCosmetic: {
    pregnant: ["ok", "Common and generally low concern.", []],
    breastfeeding: ["ok", "Common and generally low concern.", []],
  },
  thickenerCosmetic: {
    pregnant: ["ok", "Common and generally low concern.", []],
    breastfeeding: ["ok", "Common and generally low concern.", []],
  },
  other: {
    pregnant: ["caution", "A general processing marker — worth a second look as part of a whole-food-first prenatal approach.", []],
    breastfeeding: ["ok", "No specific concern while breastfeeding.", []],
  },
};

function reproLensFor(flag, reproId) {
  const bucket = bucketOf(flag);
  const [level, note, src] = REPRO_RULES[bucket][reproId];
  return { bucket, level, note, src: src || [] };
}

// General, non-personalized. No calorie/macro/supplement dosing — an
// obstetrician or lactation consultant is the right source for anything
// individualized, especially if you've been given specific guidance
// (e.g. for gestational diabetes).
const REPRO_GUIDANCE = {
  pregnant: {
    eat: ["Whole foods first: vegetables, fruit, legumes, dairy, whole grains", "Freshly prepared over packaged/cured where practical (relevant to the nitrite point above)", "Iron- and folate-rich foods, as advised by your doctor"],
    avoid: ["Relying on packaged/cured meats as a regular protein source", "High caffeine intake — track it across coffee, tea, and packaged drinks together", "Products high in trans fat (hydrogenated oil)"],
  },
  breastfeeding: {
    eat: ["A varied, whole-food-first diet — most foods are fine in moderation", "Adequate fluids and regular meals"],
    avoid: ["High caffeine intake tracked across all sources in a day", "Products high in trans fat (hydrogenated oil), as part of general heart-healthy eating"],
  },
};

// ---- metabolic health lens (diabetes / fatty liver) ----
// Added because in India these two conditions are largely the same
// underlying problem, not two separate ones: NAFLD prevalence in the
// general Indian population runs ~9-32%, but jumps to ~53-57% in people
// with type 2 diabetes (INASL 2023; multiple Indian cohort studies).
// They share drivers — added sugar/fructose, refined carbs, trans fat —
// which is why this lens reuses the SAME buckets as everything else
// rather than inventing new ingredient categories. Same rule as the
// pregnancy lens: general public-health information, never a diagnosis,
// never a treatment plan, never a dosing number.
const METABOLIC = [
  { id: "none", label: "Not applicable" },
  { id: "diabetes", label: "Diabetes / Prediabetes" },
  { id: "fatty_liver", label: "Fatty Liver (NAFLD)" },
  { id: "both", label: "Both" },
];

const METABOLIC_RULES = {
  // The headline case in this whole lens. Found via real-product testing
  // (Britannia NutriChoice "Diabetic Friendly" biscuits contain this) —
  // maltodextrin has a HIGHER glycemic index than table sugar despite not
  // being labelled as sugar, which is exactly the kind of thing this lens
  // exists to surface.
  highGlycemicCarb: {
    diabetes: ["avoid", "This has a glycemic index that can exceed table sugar's despite not being labelled as 'sugar' — one of the more deceptive ingredients for anyone managing blood glucose, especially in products marketed as diabetic-friendly.", []],
    fatty_liver: ["caution", "Rapidly-absorbed carbohydrates contribute to the same excess-calorie, insulin-spiking pattern implicated in liver fat accumulation, though the evidence is strongest for fructose specifically rather than this ingredient.", []],
    both: ["avoid", "Spikes blood glucose faster than table sugar despite not being labelled as sugar — relevant to both conditions, and one of the highest-value things to notice in this lens.", []],
  },
  colour: {
    diabetes: ["caution", "No established direct link to blood sugar, but a marker of processed food generally worth noticing.", []],
    fatty_liver: ["caution", "No established direct link to liver fat, but a marker of processed food generally worth noticing.", []],
    both: ["caution", "No established direct link to either condition, but a marker of processed food worth noticing.", []],
  },
  sweetener: {
    // WHO's own 2023 review is nuanced and worth stating precisely: trials
    // show short-term reductions in adiposity, but observational (cohort)
    // studies found an ASSOCIATION with higher type 2 diabetes, CVD, and
    // mortality risk — association, not proven causation, and WHO's own
    // recommendation is not to rely on sweeteners for NCD risk reduction.
    diabetes: ["caution", "WHO's 2023 guideline advises against relying on non-sugar sweeteners to reduce NCD risk — trials show short-term benefits, but observational studies found an association (not proven cause) with higher type 2 diabetes risk. 'Sugar-free' isn't automatically the safer choice — worth discussing with your doctor rather than assuming.", ["WHO_NSS"]],
    fatty_liver: ["caution", "Less fatty-liver-specific evidence exists, but WHO's 2023 guideline is a general caution against assuming non-sugar sweeteners are a health-neutral swap.", ["WHO_NSS"]],
    both: ["caution", "WHO's 2023 guideline advises against relying on non-sugar sweeteners for NCD risk reduction — observational studies found an association with higher type 2 diabetes risk. Worth a conversation with your doctor rather than assuming 'sugar-free' is automatically better.", ["WHO_NSS"]],
  },
  flavourEnhancer: {
    diabetes: ["ok", "No established link to blood glucose.", []],
    fatty_liver: ["ok", "No established direct link to liver fat.", []],
    both: ["ok", "No established link to either condition.", []],
  },
  preservative: {
    diabetes: ["caution", "Some studies associate frequent cured/processed meat consumption with higher type 2 diabetes risk — this is about the food pattern more than this specific preservative, and worth checking exactly which one this is.", []],
    fatty_liver: ["caution", "No specific established link to liver fat for most preservatives, but a marker of a processed-meat-heavy pattern worth noticing.", []],
    both: ["caution", "Worth checking exactly which preservative this is — some are linked in observational studies to metabolic risk via the processed-meat pattern rather than the preservative itself.", []],
  },
  stimulant: {
    // Deliberately NOT claiming caffeine here is "protective" — the
    // research suggesting a link between coffee and lower T2D/NAFLD risk
    // is about brewed coffee, not caffeine as a packaged-food additive,
    // and especially not when it's paired with added sugar in the same
    // product (colas, energy drinks) — which is the common real case here.
    diabetes: ["caution", "Some research links brewed coffee to lower diabetes risk — but that doesn't transfer to caffeine added to a packaged drink, especially one that also contains added sugar. Check the rest of this product's ingredients rather than crediting the caffeine.", []],
    fatty_liver: ["caution", "Similarly, research on coffee and liver health is about brewed coffee — not caffeine as a packaged additive, and not when paired with added sugar in the same product.", []],
    both: ["caution", "Don't read this as a health positive — it's about brewed coffee in the research, not caffeine added to a packaged product, especially one that may also contain added sugar.", []],
  },
  proteinIsolate: {
    diabetes: ["ok", "Protein doesn't spike blood glucose the way refined carbs and sugar do, and can support satiety.", []],
    fatty_liver: ["ok", "No established direct concern for liver fat.", []],
    both: ["ok", "Generally neutral to helpful for both — whole-food protein sources remain the better everyday default.", []],
  },
  modifiedFat: {
    // The strongest flag in this lens — trans fat is directly and
    // specifically implicated in both conditions, not just generally
    // "unhealthy". India-first sourcing: FSSAI's own cap, plus INASL
    // (the Indian hepatology body) on the liver-specific mechanism.
    diabetes: ["avoid", "Trans fat is a well-established risk factor for insulin resistance and progression to type 2 diabetes — worth minimising even within FSSAI's permitted 2% cap.", ["FSSAI_TRANSFAT"]],
    fatty_liver: ["avoid", "Trans fat directly drives fat accumulation in the liver and is specifically implicated in NAFLD progression per Indian hepatology guidance — one of the more actionable things to cut.", ["FSSAI_TRANSFAT", "INASL_NAFLD"]],
    both: ["avoid", "Trans fat is directly implicated in both insulin resistance and liver fat accumulation — the single highest-value ingredient to cut in this lens.", ["FSSAI_TRANSFAT", "INASL_NAFLD"]],
  },
  emulsifierCosmetic: {
    // Emerging, NOT settled science — stated with that hedge deliberately.
    diabetes: ["caution", "Early research on some emulsifiers and gut-microbiome disruption suggests a possible link to glucose intolerance — this is emerging, not established, science.", []],
    fatty_liver: ["caution", "Similarly early research explores a gut-liver axis link — not established science yet.", []],
    both: ["caution", "Emerging (not settled) research on gut-microbiome effects — worth knowing about, not worth panicking over.", []],
  },
  thickenerCosmetic: {
    diabetes: ["caution", "Same emerging, unsettled gut-microbiome research as emulsifiers above.", []],
    fatty_liver: ["caution", "Same emerging, unsettled research.", []],
    both: ["caution", "Same emerging, unsettled research.", []],
  },
  other: {
    diabetes: ["caution", "A general marker of processed formulation — worth a second look given the overall pattern matters more than any single ingredient.", []],
    fatty_liver: ["caution", "A general marker of processed formulation — same reasoning.", []],
    both: ["caution", "A general marker of processed formulation.", []],
  },
};

function metabolicLensFor(flag, metabolicId) {
  const bucket = bucketOf(flag);
  const [level, note, src] = METABOLIC_RULES[bucket][metabolicId];
  return { bucket, level, note, src: src || [] };
}

// General, non-personalized. No blood sugar targets, no calorie/macro
// numbers, no medication guidance — a doctor or diabetes educator is the
// right source for anything individualized.
const METABOLIC_GUIDANCE = {
  diabetes: {
    eat: ["Whole foods with fibre: vegetables, legumes, whole grains over refined flour", "Protein at each meal, which slows glucose absorption: dal, eggs, curd, fish, chicken", "Products where sugar isn't hidden under multiple label names"],
    avoid: ["Sugary drinks and packaged fruit juices", "Products where sugar appears under 2+ names on the label", "Refined-flour snacks and sweets as a daily habit"],
  },
  fatty_liver: {
    eat: ["Whole foods low in added sugar and refined carbs", "Unsaturated fats in place of trans fat: nuts, seeds, cold-pressed oils in moderation", "Regular physical activity alongside diet — INASL guidance treats this as central, not optional"],
    avoid: ["Sugary drinks and fruit juice concentrate — fructose specifically is implicated in liver fat build-up", "Products with hydrogenated oil / trans fat", "Frequent ultra-processed snacking"],
  },
  both: {
    eat: ["Whole foods first, prioritising fibre and protein over refined carbs", "Unsaturated fats over trans fat", "Regular physical activity alongside diet"],
    avoid: ["Sugary drinks and packaged fruit juices — a shared driver of both conditions", "Products with hydrogenated oil / trans fat", "Frequent ultra-processed snacking and sweets as a daily habit"],
  },
};

function analyze(raw) {
  const tokens = tokenize(raw);
  const flags = [];
  const sugar = new Set();
  const seen = new Set();
  let nova = false;
  for (const t of tokens) {
    if (SUGAR_ALIASES.has(t)) sugar.add(t);
    const f = classify(t);
    if (f && !seen.has(f.matched)) {
      seen.add(f.matched);
      flags.push(f);
      if (f.nova) nova = true;
    }
  }
  let score = 100;
  for (const f of flags) score -= PENALTY[f.concern] || 0;
  if (sugar.size >= 2) score -= 8;
  score = Math.max(0, Math.min(100, score));

  let band;
  if (score >= 85) band = "clean";
  else if (score >= 70) band = "clean";
  else if (score >= 50) band = "mixed";
  else band = "ultra";
  if (nova && band === "clean") band = "mixed";
  const binary = nova || band === "ultra" ? "ultra" : band;

  const order = { high: 3, moderate: 2, low: 1, none: 0 };
  flags.sort((a, b) => order[b.concern] - order[a.concern]);

  return { binary, score, nova, sugar: [...sugar], flags, count: tokens.length };
}

// ---- presentation ----
const BANDS = {
  clean: { label: "Clean", sub: "Minimal processing", signal: "#1f9e6b", track: "#1f9e6b" },
  mixed: { label: "Caution", sub: "Some processed markers", signal: "#d98a00", track: "#d98a00" },
  ultra: { label: "Ultra-processed", sub: "Avoid where you can", signal: "#d7443e", track: "#d7443e" },
};
const CONCERN = {
  high: { t: "HIGH", c: "#d7443e" },
  moderate: { t: "MOD", c: "#d98a00" },
  low: { t: "LOW", c: "#8a8f98" },
  none: { t: "OK", c: "#1f9e6b" },
};
const LENS_LEVEL = {
  avoid: { t: "AVOID", c: "#d7443e", bg: "#fbf1f0", border: "#f4d9d7" },
  caution: { t: "CAUTION", c: "#9a6a00", bg: "#fdf6ea", border: "#f2e2c4" },
  ok: { t: "OK", c: "#1f9e6b", bg: "#eef8f3", border: "#cfe9dc" },
};

// Citation pinning — the "harder 20%". A bare institution name (e.g. "WHO")
// in a rule's src array is a claim someone SAYS is theirs but that hasn't
// been checked against a live document. A key here (matched exactly, not
// by institution name) means that SPECIFIC claim has been checked: real
// URL, real date. Keys are per-document, not per-institution — WHO has
// two different documents cited in this app (trans fat, antenatal
// caffeine) with two different numbers, so they get two different keys.
// This also means an unverified citation to the same institution for a
// DIFFERENT claim correctly still renders as plain text, not linked.
//
// India-first priority applied here (checked Sept 2026): FSSAI's own
// regulation is cited ahead of WHO's for trans fat, since it's the
// binding standard this product actually operates under and is more
// specific than WHO's campaign page. WHO is used over NHS/ACOG as the
// default international body for the caffeine figure, since it's a body
// India references directly rather than one country's health service.
// NHS/ACOG are kept as secondary, explicitly-labeled context, not the
// lead citation. Only these four are verified so far — the rest of the
// src arrays elsewhere are still bare institution names, i.e. still open.
const REFERENCES = {
  FSSAI_TRANSFAT: {
    label: "FSSAI",
    title: "FSSAI trans-fat limit notification (2% cap effective Jan 1, 2022)",
    url: "https://fssai.gov.in/upload/media/FSSAI_News_TransFat_FNB_18_02_2021.pdf",
    verified: "2026-09",
  },
  WHO_TRANSFAT: {
    label: "WHO",
    title: "REPLACE trans fat — World Health Organization",
    url: "https://www.who.int/teams/nutrition-and-food-safety/replace-trans-fat",
    verified: "2026-09",
  },
  WHO_ANC: {
    label: "WHO",
    title: "WHO recommendations on antenatal care for a positive pregnancy experience (2016) — caffeine under 300mg/day",
    url: "https://www.who.int/publications/i/item/9789241549912",
    verified: "2026-09",
  },
  NHS_CAFFEINE: {
    label: "NHS",
    title: "Should I limit caffeine during pregnancy? — NHS (stricter national guidance: under 200mg/day)",
    url: "https://www.nhs.uk/common-health-questions/pregnancy/should-i-limit-caffeine-during-pregnancy/",
    verified: "2026-09",
  },
  EU_TRANSFAT: {
    label: "EU",
    title: "Commission Regulation (EU) 2019/649 — 2g trans fat per 100g of fat, binding since 1 April 2021",
    url: "https://ehnheart.org/news-events/news/press-releases/eu-trans-fat-free-as-of-1-april-2021/",
    verified: "2026-09",
  },
  US_TRANSFAT: {
    label: "US",
    title: "FDA final determination on partially hydrogenated oils — not GRAS, phased out of the food supply",
    url: "https://www.fda.gov/food/food-additives-petitions/final-determination-regarding-partially-hydrogenated-oils-removing-trans-fat",
    verified: "2026-09",
  },
  EFSA_CAFFEINE: {
    label: "EU (EFSA)",
    title: "EFSA Scientific Opinion on the Safety of Caffeine (2015) — under 200mg/day in pregnancy/breastfeeding",
    url: "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2015.4102",
    verified: "2026-09",
  },
  INASL_NAFLD: {
    label: "INASL",
    title: "INASL Guidance Paper on Nomenclature, Diagnosis and Treatment of NAFLD (2023) — India-specific consensus, ~53% NAFLD prevalence found in Indian type 2 diabetics",
    url: "https://doi.org/10.1016/j.jceh.2022.11.014",
    verified: "2026-09",
  },
  WHO_NSS: {
    label: "WHO",
    title: "WHO guideline: Use of non-sugar sweeteners (2023) — advises against NSS for NCD risk reduction; observational studies found an association with higher type 2 diabetes, CVD, and mortality risk",
    url: "https://www.who.int/news/item/15-05-2023-who-advises-not-to-use-non-sugar-sweeteners-for-weight-control-in-newly-released-guideline",
    verified: "2026-09",
  },
};

// Regional standards comparison — India / EU / US / WHO side by side, for
// the two claims in this app that have been checked against real, current,
// first-party-or-near-first-party documents (Sept 2026). Built India-first:
// the India column is populated FIRST and honestly, including the row where
// no India-specific figure was found, rather than silently defaulting to
// a foreign number. This table is deliberately narrow in scope right now —
// it does NOT cover sweeteners, synthetic colours, nitrites, or MSG across
// regions, because those haven't been individually verified yet. Extend
// row-by-row as each is checked, not by guessing the rest to fill the table.
const REGIONAL_STANDARDS = [
  {
    topic: "Industrial trans fat",
    india: { value: "≤2% of oils/fats in the product (mandatory, since 1 Jan 2022)", src: ["FSSAI_TRANSFAT"] },
    eu: { value: "≤2g per 100g of fat (mandatory, since 1 Apr 2021)", src: ["EU_TRANSFAT"] },
    us: { value: "Partially hydrogenated oils not GRAS — effectively banned as an added ingredient, not a % limit", src: ["US_TRANSFAT"] },
    who: { value: "Global elimination campaign (REPLACE), non-binding", src: ["WHO_TRANSFAT"] },
  },
  {
    topic: "Caffeine in pregnancy",
    india: { value: "No India-specific numeric guideline found in this review — worth confirming directly with FOGSI before publishing a number for India", src: [] },
    eu: { value: "Under 200mg/day (EFSA, 2015)", src: ["EFSA_CAFFEINE"] },
    us: { value: "Under 200mg/day 'does not appear to be a major factor' — a softer, non-binding framing (ACOG)", src: [] },
    who: { value: "Under 300mg/day (2016 antenatal care guideline)", src: ["WHO_ANC"] },
  },
];

const SAMPLES = {
  "Cream biscuit": "Refined wheat flour (maida), Sugar, Edible vegetable oil (palm), Invert syrup, Milk solids, Emulsifiers (INS 322, INS 471), Raising agents (INS 500), Salt, Added flavours (natural and artificial), INS 621",
  "Instant noodles": "Refined wheat flour, Palm oil, Salt, Thickeners (INS 412), Hydrolysed vegetable protein, Flavour enhancers (INS 635, INS 621), Maltodextrin, Colour (INS 150d), Sugar",
  "Roasted peanuts": "Peanuts, Salt",
  "Diet cola": "Carbonated water, Caramel colour (INS 150d), Acidity regulators, Sweeteners (INS 951, INS 950), Preservative (INS 211), Caffeine, Added flavours",
  "\"Diabetic Friendly\" biscuit": "Almonds, Dough Conditioner (INS 223), Emulsifiers (INS 322, INS 471, INS 472e), Flavours (Natural, Nature Identical, Artificial), Foxtail Millet Flour, Inulin, Little Millet Flour, Maltodextrin, Milk Solids, Raising Agents (INS 450, INS 503, INS 500), Refined Palm Oil, Rolled Oats, Soya Protein Isolate, Sweeteners (INS 965, INS 955), Wheat Flour, Oats Fibre, Iodised Salt",
};

// Renders a source citation. Verified ones (present in REFERENCES) become
// a real clickable link to the actual document, with the verification
// date in the tooltip. Unverified ones stay plain text — an institution
// named but not yet pinned to a document, shown honestly as such rather
// than looking identical to a verified one.
function SrcChip({ s, color, bg = "#fff", border }) {
  const ref = REFERENCES[s];
  const base = { font: "700 9px ui-monospace,monospace", color, background: bg, border: `1px solid ${border}`, padding: "2px 6px", borderRadius: 4 };
  if (ref) {
    return (
      <a href={ref.url} target="_blank" rel="noreferrer" title={`${ref.title} — verified ${ref.verified}`}
        style={{ ...base, textDecoration: "underline", cursor: "pointer" }}>
        {ref.label} ↗
      </a>
    );
  }
  return <span style={base} title="Institution cited — not yet pinned to a specific document">{s}</span>;
}

function Ring({ score, band }) {
  const b = BANDS[band];
  const r = 52, c = 2 * Math.PI * r;
  // display: fuller ring = cleaner. score is already 100=clean.
  const filled = (score / 100) * c;
  return (
    <svg viewBox="0 0 140 140" style={{ width: 150, height: 150 }}>
      <circle cx="70" cy="70" r={r} fill="none" stroke="#eceae4" strokeWidth="13" />
      <circle
        cx="70" cy="70" r={r} fill="none" stroke={b.track} strokeWidth="13"
        strokeLinecap="round" strokeDasharray={`${filled} ${c}`}
        transform="rotate(-90 70 70)"
        style={{ transition: "stroke-dasharray .6s cubic-bezier(.2,.8,.2,1)" }}
      />
      <text x="70" y="64" textAnchor="middle" style={{ font: "700 30px ui-monospace,monospace", fill: "#17181a" }}>{score}</text>
      <text x="70" y="84" textAnchor="middle" style={{ font: "600 10px ui-monospace,monospace", fill: "#8a8f98", letterSpacing: ".12em" }}>/ 100</text>
    </svg>
  );
}

export default function App() {
  const [raw, setRaw] = useState(SAMPLES["Cream biscuit"]);
  const [active, setActive] = useState(null);
  const [profile, setProfile] = useState("adult");
  const [goal, setGoal] = useState("none");
  const [gender, setGender] = useState("unspecified"); // profile metadata only — see GENDERS note below
  const [repro, setRepro] = useState("none");
  const [metabolic, setMetabolic] = useState("none");
  const res = useMemo(() => analyze(raw), [raw]);
  const b = BANDS[res.binary];
  const risk = (10 - res.score / 10).toFixed(1);

  const lensed = useMemo(
    () => res.flags.map((f) => ({
      ...f,
      lens: lensFor(f, profile),
      goalLens: goal !== "none" ? goalLensFor(f, goal) : null,
      reproLens: repro !== "none" ? reproLensFor(f, repro) : null,
      metabolicLens: metabolic !== "none" ? metabolicLensFor(f, metabolic) : null,
    })),
    [res.flags, profile, goal, repro, metabolic]
  );
  const avoidList = lensed.filter((f) => f.lens.level === "avoid");
  const cautionList = lensed.filter((f) => f.lens.level === "caution");
  const goalAvoidList = lensed.filter((f) => f.goalLens && f.goalLens.level === "avoid");
  const goalCautionList = lensed.filter((f) => f.goalLens && f.goalLens.level === "caution");
  const reproAvoidList = lensed.filter((f) => f.reproLens && f.reproLens.level === "avoid");
  const reproCautionList = lensed.filter((f) => f.reproLens && f.reproLens.level === "caution");
  const metabolicAvoidList = lensed.filter((f) => f.metabolicLens && f.metabolicLens.level === "avoid");
  const metabolicCautionList = lensed.filter((f) => f.metabolicLens && f.metabolicLens.level === "caution");
  const profileLabel = PROFILES.find((p) => p.id === profile).label;
  const goalLabel = GOALS.find((g) => g.id === goal).label;
  const reproLabel = REPRO.find((r) => r.id === repro).label;
  const metabolicLabel = METABOLIC.find((m) => m.id === metabolic).label;

  return (
    <div style={{ minHeight: "100vh", background: "#f6f5f1", padding: "24px 16px", fontFamily: "'Inter',system-ui,sans-serif", color: "#17181a" }}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        {/* wordmark */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 20 }}>
          <span style={{ font: "800 20px 'Inter',sans-serif", letterSpacing: "-.02em" }}>Inside</span>
          <span style={{ font: "500 20px ui-monospace,monospace", color: b.signal, letterSpacing: "-.02em" }}>Label</span>
          <span style={{ marginLeft: "auto", font: "600 10px ui-monospace,monospace", color: "#8a8f98", letterSpacing: ".14em" }}>PHASE 1 · SCAN RESULT</span>
        </div>

        {/* picker */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
          {Object.keys(SAMPLES).map((k) => {
            const on = raw === SAMPLES[k];
            return (
              <button key={k} onClick={() => { setRaw(SAMPLES[k]); setActive(null); }}
                style={{ padding: "7px 13px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent", color: on ? "#fff" : "#55585e", font: "600 12.5px 'Inter',sans-serif" }}>
                {k}
              </button>
            );
          })}
        </div>

        {/* age profile selector */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            SHOW RELEVANCE FOR
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {PROFILES.map((p) => {
              const on = profile === p.id;
              return (
                <button key={p.id} onClick={() => setProfile(p.id)}
                  style={{ padding: "7px 14px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent", display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={{ font: "600 12.5px 'Inter',sans-serif", color: on ? "#fff" : "#55585e" }}>{p.label}</span>
                  <span style={{ font: "500 10px ui-monospace,monospace", color: on ? "#c7c9cc" : "#b0b3b9" }}>{p.sub}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* gender — profile field only, does NOT change ingredient guidance (see GENDERS note) */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            GENDER (OPTIONAL · PROFILE ONLY)
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {GENDERS.map((g) => {
              const on = gender === g.id;
              return (
                <button key={g.id} onClick={() => setGender(g.id)}
                  style={{ padding: "7px 14px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent" }}>
                  <span style={{ font: "600 12.5px 'Inter',sans-serif", color: on ? "#fff" : "#55585e" }}>{g.label}</span>
                </button>
              );
            })}
          </div>
          <div style={{ marginTop: 6, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.45 }}>
            Stored on your profile only — doesn't change the ingredient guidance below. None of the
            additives this app tracks have a gender-specific safety difference to flag honestly.
          </div>
        </div>

        {/* weight-goal selector — no BMI, no body metrics, no numeric targets */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            YOUR GOAL (OPTIONAL)
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {GOALS.map((g) => {
              const on = goal === g.id;
              return (
                <button key={g.id} onClick={() => setGoal(g.id)}
                  style={{ padding: "7px 14px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent" }}>
                  <span style={{ font: "600 12.5px 'Inter',sans-serif", color: on ? "#fff" : "#55585e" }}>{g.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* pregnancy / breastfeeding selector — real, sourced guidance exists here */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            PREGNANCY / BREASTFEEDING (OPTIONAL)
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {REPRO.map((r) => {
              const on = repro === r.id;
              return (
                <button key={r.id} onClick={() => setRepro(r.id)}
                  style={{ padding: "7px 14px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent" }}>
                  <span style={{ font: "600 12.5px 'Inter',sans-serif", color: on ? "#fff" : "#55585e" }}>{r.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* metabolic health selector — diabetes / fatty liver, India's largest overlapping burden */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            METABOLIC HEALTH (OPTIONAL)
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {METABOLIC.map((m) => {
              const on = metabolic === m.id;
              return (
                <button key={m.id} onClick={() => setMetabolic(m.id)}
                  style={{ padding: "7px 14px", borderRadius: 999, cursor: "pointer", border: on ? "1.5px solid #17181a" : "1.5px solid #dcdad3", background: on ? "#17181a" : "transparent" }}>
                  <span style={{ font: "600 12.5px 'Inter',sans-serif", color: on ? "#fff" : "#55585e" }}>{m.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* verdict card */}
        <div style={{ background: "#fff", borderRadius: 18, padding: "26px 24px", boxShadow: "0 1px 2px rgba(0,0,0,.04),0 8px 30px rgba(0,0,0,.05)", border: "1px solid #eeece6" }}>
          <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
            <Ring score={res.score} band={res.binary} />
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "5px 11px", borderRadius: 999, background: b.signal + "18", marginBottom: 10 }}>
                <span style={{ width: 8, height: 8, borderRadius: 99, background: b.signal }} />
                <span style={{ font: "700 13px 'Inter',sans-serif", color: b.signal, letterSpacing: ".01em" }}>{b.label}</span>
              </div>
              <div style={{ font: "500 14px 'Inter',sans-serif", color: "#55585e", marginBottom: 14 }}>{b.sub}</div>
              <div style={{ display: "flex", gap: 22 }}>
                <div>
                  <div style={{ font: "600 10px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em" }}>RISK INDEX</div>
                  <div style={{ font: "700 20px ui-monospace,monospace" }}>{risk}<span style={{ font: "500 12px ui-monospace,monospace", color: "#9a9ea5" }}> / 10</span></div>
                </div>
                <div>
                  <div style={{ font: "600 10px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em" }}>FLAGGED</div>
                  <div style={{ font: "700 20px ui-monospace,monospace" }}>{res.flags.length}<span style={{ font: "500 12px ui-monospace,monospace", color: "#9a9ea5" }}> / {res.count}</span></div>
                </div>
              </div>
            </div>
          </div>

          {/* NOVA / sugar banners */}
          {res.nova && (
            <div style={{ marginTop: 18, padding: "10px 13px", borderRadius: 10, background: "#fbf1f0", border: "1px solid #f4d9d7", font: "600 12.5px 'Inter',sans-serif", color: "#b03a35" }}>
              Contains a NOVA Group-4 marker — ultra-processed by definition, whatever the score.
            </div>
          )}
          {res.sugar.length >= 2 && (
            <div style={{ marginTop: 10, padding: "10px 13px", borderRadius: 10, background: "#fdf6ea", border: "1px solid #f2e2c4", font: "600 12.5px 'Inter',sans-serif", color: "#9a6a00" }}>
              Sugar appears under {res.sugar.length} names: {res.sugar.join(", ")}.
            </div>
          )}
          {profile === "toddler" && res.sugar.length >= 1 && (
            <div style={{ marginTop: 10, padding: "10px 13px", borderRadius: 10, background: "#fbf1f0", border: "1px solid #f4d9d7", font: "600 12.5px 'Inter',sans-serif", color: "#b03a35" }}>
              Contains added sugar ({res.sugar.join(", ")}) — general paediatric guidance for early childhood favours little to no added sugar, whatever the total amount.
            </div>
          )}
          {metabolic !== "none" && res.sugar.length >= 1 && (
            <div style={{ marginTop: 10, padding: "10px 13px", borderRadius: 10, background: "#fbf1f0", border: "1px solid #f4d9d7", font: "600 12.5px 'Inter',sans-serif", color: "#b03a35" }}>
              Contains added sugar or a sugar-acting ingredient ({res.sugar.join(", ")}) — these spike blood
              sugar, and where fructose specifically is involved, also contribute to liver fat build-up.
              Worth checking the total across everything you eat in a day, not just this one product.
            </div>
          )}
        </div>

        {/* age-relevance summary — a lens on the SAME flags, never a new verdict */}
        {(avoidList.length > 0 || cautionList.length > 0) && (
          <div style={{ marginTop: 16, background: "#fff", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 10 }}>
              RELEVANT FOR {profileLabel.toUpperCase()}
            </div>
            {avoidList.length > 0 && (
              <div style={{ marginBottom: cautionList.length ? 10 : 0 }}>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c }}>Avoid: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {avoidList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            {cautionList.length > 0 && (
              <div>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.caution.c }}>Use caution: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {cautionList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            <div style={{ marginTop: 10, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
              General ingredient guidance, not a medical recommendation. For a specific condition, check with a doctor or paediatrician.
            </div>
          </div>
        )}

        {/* weight-goal relevance summary — same flags, goal-direction lens */}
        {goal !== "none" && (goalAvoidList.length > 0 || goalCautionList.length > 0) && (
          <div style={{ marginTop: 10, background: "#fff", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 10 }}>
              RELEVANT FOR YOUR GOAL — {goalLabel.toUpperCase()}
            </div>
            {goalAvoidList.length > 0 && (
              <div style={{ marginBottom: goalCautionList.length ? 10 : 0 }}>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c }}>Avoid: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {goalAvoidList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            {goalCautionList.length > 0 && (
              <div>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.caution.c }}>Use caution: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {goalCautionList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            <div style={{ marginTop: 10, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
              General relevance to your stated goal, not a calorie or nutrition prescription. No calorie
              counting is done here — for a specific plan, a dietitian can account for your full diet.
            </div>
          </div>
        )}

        {/* general goal guidance — non-personalized, no numbers, read-once panel */}
        {goal !== "none" && (
          <div style={{ marginTop: 10, background: "#fbfaf6", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 12 }}>
              GENERAL EATING PATTERN — {goalLabel.toUpperCase()}
            </div>
            <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.ok.c, marginBottom: 6 }}>Lean toward</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {GOAL_GUIDANCE[goal].eat.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c, marginBottom: 6 }}>Limit</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {GOAL_GUIDANCE[goal].avoid.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            </div>
            <div style={{ marginTop: 12, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
              General dietary guidance, not a personalized plan. No calorie or macro targets are calculated —
              for an individual plan, consult a registered dietitian.
            </div>
          </div>
        )}

        {/* pregnancy/breastfeeding relevance summary — same flags, repro-status lens */}
        {repro !== "none" && (reproAvoidList.length > 0 || reproCautionList.length > 0) && (
          <div style={{ marginTop: 10, background: "#fff", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 10 }}>
              RELEVANT FOR {reproLabel.toUpperCase()}
            </div>
            {reproAvoidList.length > 0 && (
              <div style={{ marginBottom: reproCautionList.length ? 10 : 0 }}>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c }}>Avoid: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {reproAvoidList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            {reproCautionList.length > 0 && (
              <div>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.caution.c }}>Use caution: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {reproCautionList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 8, background: "#fbf1f0", border: "1px solid #f4d9d7", font: "600 11.5px 'Inter',sans-serif", color: "#b03a35", lineHeight: 1.5 }}>
              General public-health guidance, not medical advice or a diagnosis. Always follow your doctor's
              or OB-GYN's specific guidance for you — especially if you've been given individual advice
              (e.g. for gestational diabetes).
            </div>
          </div>
        )}

        {/* general pregnancy/breastfeeding guidance — non-personalized, no numbers or dosing */}
        {repro !== "none" && (
          <div style={{ marginTop: 10, background: "#fbfaf6", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 12 }}>
              GENERAL GUIDANCE — {reproLabel.toUpperCase()}
            </div>
            <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.ok.c, marginBottom: 6 }}>Lean toward</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {REPRO_GUIDANCE[repro].eat.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c, marginBottom: 6 }}>Limit</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {REPRO_GUIDANCE[repro].avoid.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            </div>
            <div style={{ marginTop: 12, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
              General public-health guidance, not a personalized plan, prescription, or diagnosis. No
              supplement dosing or calorie targets are given here — for anything specific to you, your
              doctor, OB-GYN, or a lactation consultant is the right source.
            </div>
          </div>
        )}

        {/* metabolic health relevance summary — same flags, diabetes/fatty-liver lens */}
        {metabolic !== "none" && (metabolicAvoidList.length > 0 || metabolicCautionList.length > 0) && (
          <div style={{ marginTop: 10, background: "#fff", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 10 }}>
              RELEVANT FOR {metabolicLabel.toUpperCase()}
            </div>
            {metabolicAvoidList.length > 0 && (
              <div style={{ marginBottom: metabolicCautionList.length ? 10 : 0 }}>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c }}>Avoid: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {metabolicAvoidList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            {metabolicCautionList.length > 0 && (
              <div>
                <span style={{ font: "700 12.5px 'Inter',sans-serif", color: LENS_LEVEL.caution.c }}>Use caution: </span>
                <span style={{ font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42" }}>
                  {metabolicCautionList.map((f) => f.matched.split(" · ")[f.matched.includes("·") ? 1 : 0]).join(", ")}
                </span>
              </div>
            )}
            <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 8, background: "#fbf1f0", border: "1px solid #f4d9d7", font: "600 11.5px 'Inter',sans-serif", color: "#b03a35", lineHeight: 1.5 }}>
              General public-health information, not a diagnosis, blood-sugar target, or treatment plan.
              Diabetes and fatty liver management should be guided by your doctor — this shows what's in
              the product, not what your numbers should be.
            </div>
          </div>
        )}

        {/* general metabolic health guidance — non-personalized, no numbers or dosing */}
        {metabolic !== "none" && (
          <div style={{ marginTop: 10, background: "#fbfaf6", borderRadius: 14, padding: "16px 18px", border: "1px solid #eeece6" }}>
            <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 12 }}>
              GENERAL GUIDANCE — {metabolicLabel.toUpperCase()}
            </div>
            <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.ok.c, marginBottom: 6 }}>Lean toward</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {METABOLIC_GUIDANCE[metabolic].eat.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ font: "700 12px 'Inter',sans-serif", color: LENS_LEVEL.avoid.c, marginBottom: 6 }}>Limit</div>
                <ul style={{ margin: 0, paddingLeft: 18, font: "500 12.5px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.7 }}>
                  {METABOLIC_GUIDANCE[metabolic].avoid.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            </div>
            <div style={{ marginTop: 12, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
              General public-health guidance, not a personalized treatment plan. No blood-sugar targets,
              calorie counts, or medication guidance are given here — a doctor or diabetes educator is the
              right source for anything specific to you.
            </div>
          </div>
        )}

        {/* the receipts */}
        <div style={{ marginTop: 22 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 10 }}>
            WHY THIS VERDICT — TAP ANY ROW
          </div>
          {res.flags.length === 0 && (
            <div style={{ padding: 18, borderRadius: 12, background: "#fff", border: "1px solid #eeece6", font: "500 13.5px 'Inter',sans-serif", color: "#55585e" }}>
              Nothing flagged. Either genuinely clean, or an ingredient isn't in the starter database yet.
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {lensed.map((f, i) => {
              const c = CONCERN[f.concern];
              const lv = LENS_LEVEL[f.lens.level];
              const open = active === i;
              return (
                <div key={i} onClick={() => setActive(open ? null : i)}
                  style={{ background: "#fff", borderRadius: 12, border: "1px solid #eeece6", padding: "13px 15px", cursor: "pointer", transition: "border-color .15s", borderColor: open ? c.c + "66" : "#eeece6" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 11, flexWrap: "wrap" }}>
                    <span style={{ font: "700 9.5px ui-monospace,monospace", color: "#fff", background: c.c, padding: "3px 6px", borderRadius: 5, letterSpacing: ".06em", minWidth: 30, textAlign: "center" }}>{c.t}</span>
                    <span style={{ font: "600 13.5px 'Inter',sans-serif", flex: 1 }}>{f.matched}</span>
                    <span style={{ font: "700 9.5px ui-monospace,monospace", color: lv.c, background: lv.bg, border: `1px solid ${lv.border}`, padding: "3px 7px", borderRadius: 5, letterSpacing: ".04em" }}>
                      {profileLabel.toUpperCase()}: {lv.t}
                    </span>
                    {f.goalLens && (
                      <span style={{ font: "700 9.5px ui-monospace,monospace", color: LENS_LEVEL[f.goalLens.level].c, background: LENS_LEVEL[f.goalLens.level].bg, border: `1px solid ${LENS_LEVEL[f.goalLens.level].border}`, padding: "3px 7px", borderRadius: 5, letterSpacing: ".04em" }}>
                        GOAL: {LENS_LEVEL[f.goalLens.level].t}
                      </span>
                    )}
                    {f.reproLens && (
                      <span style={{ font: "700 9.5px ui-monospace,monospace", color: LENS_LEVEL[f.reproLens.level].c, background: LENS_LEVEL[f.reproLens.level].bg, border: `1px solid ${LENS_LEVEL[f.reproLens.level].border}`, padding: "3px 7px", borderRadius: 5, letterSpacing: ".04em" }}>
                        {reproLabel.toUpperCase()}: {LENS_LEVEL[f.reproLens.level].t}
                      </span>
                    )}
                    {f.metabolicLens && (
                      <span style={{ font: "700 9.5px ui-monospace,monospace", color: LENS_LEVEL[f.metabolicLens.level].c, background: LENS_LEVEL[f.metabolicLens.level].bg, border: `1px solid ${LENS_LEVEL[f.metabolicLens.level].border}`, padding: "3px 7px", borderRadius: 5, letterSpacing: ".04em" }}>
                        {metabolicLabel.toUpperCase()}: {LENS_LEVEL[f.metabolicLens.level].t}
                      </span>
                    )}
                    {f.verify && <span style={{ font: "600 9px ui-monospace,monospace", color: "#b03a35", border: "1px solid #f4d9d7", padding: "2px 5px", borderRadius: 4 }}>VERIFY vs FSSAI</span>}
                    <span style={{ color: "#c2c5cb", transform: open ? "rotate(90deg)" : "none", transition: "transform .15s", font: "16px monospace", marginLeft: "auto" }}>›</span>
                  </div>
                  {open && (
                    <div style={{ marginTop: 11, paddingTop: 11, borderTop: "1px dashed #e6e4dd" }}>
                      <div style={{ font: "500 13px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.55 }}>{f.why}</div>
                      <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 8, background: lv.bg, border: `1px solid ${lv.border}` }}>
                        <span style={{ font: "700 11.5px 'Inter',sans-serif", color: lv.c }}>For {profileLabel.toLowerCase()}: </span>
                        <span style={{ font: "500 12px 'Inter',sans-serif", color: "#3a3d42" }}>{f.lens.note}</span>
                        {f.lens.src.length > 0 && (
                          <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                            {f.lens.src.map((s) => <SrcChip key={s} s={s} color={lv.c} border={lv.border} />)}
                          </div>
                        )}
                      </div>
                      {f.goalLens && (
                        <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 8, background: LENS_LEVEL[f.goalLens.level].bg, border: `1px solid ${LENS_LEVEL[f.goalLens.level].border}` }}>
                          <span style={{ font: "700 11.5px 'Inter',sans-serif", color: LENS_LEVEL[f.goalLens.level].c }}>For your goal ({goalLabel.toLowerCase()}): </span>
                          <span style={{ font: "500 12px 'Inter',sans-serif", color: "#3a3d42" }}>{f.goalLens.note}</span>
                          {f.goalLens.src.length > 0 && (
                            <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                              {f.goalLens.src.map((s) => <SrcChip key={s} s={s} color={LENS_LEVEL[f.goalLens.level].c} border={LENS_LEVEL[f.goalLens.level].border} />)}
                            </div>
                          )}
                        </div>
                      )}
                      {f.reproLens && (
                        <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 8, background: LENS_LEVEL[f.reproLens.level].bg, border: `1px solid ${LENS_LEVEL[f.reproLens.level].border}` }}>
                          <span style={{ font: "700 11.5px 'Inter',sans-serif", color: LENS_LEVEL[f.reproLens.level].c }}>For {reproLabel.toLowerCase()}: </span>
                          <span style={{ font: "500 12px 'Inter',sans-serif", color: "#3a3d42" }}>{f.reproLens.note}</span>
                          {f.reproLens.src.length > 0 && (
                            <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                              {f.reproLens.src.map((s) => <SrcChip key={s} s={s} color={LENS_LEVEL[f.reproLens.level].c} border={LENS_LEVEL[f.reproLens.level].border} />)}
                            </div>
                          )}
                        </div>
                      )}
                      {f.metabolicLens && (
                        <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 8, background: LENS_LEVEL[f.metabolicLens.level].bg, border: `1px solid ${LENS_LEVEL[f.metabolicLens.level].border}` }}>
                          <span style={{ font: "700 11.5px 'Inter',sans-serif", color: LENS_LEVEL[f.metabolicLens.level].c }}>For {metabolicLabel.toLowerCase()}: </span>
                          <span style={{ font: "500 12px 'Inter',sans-serif", color: "#3a3d42" }}>{f.metabolicLens.note}</span>
                          {f.metabolicLens.src.length > 0 && (
                            <div style={{ marginTop: 5, display: "flex", gap: 5, flexWrap: "wrap" }}>
                              {f.metabolicLens.src.map((s) => <SrcChip key={s} s={s} color={LENS_LEVEL[f.metabolicLens.level].c} border={LENS_LEVEL[f.metabolicLens.level].border} />)}
                            </div>
                          )}
                        </div>
                      )}
                      <div style={{ marginTop: 9, display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {f.src.map((s) => <SrcChip key={s} s={s} color="#6b6f76" bg="#f2f1ec" border="#e2e0d9" />)}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* editable input */}
        <div style={{ marginTop: 22 }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".12em", marginBottom: 8 }}>
            OR PASTE ANY INGREDIENT LIST
          </div>
          <textarea value={raw} onChange={(e) => { setRaw(e.target.value); setActive(null); }}
            rows={3} style={{ width: "100%", boxSizing: "border-box", padding: "12px 14px", borderRadius: 12, border: "1px solid #dcdad3", font: "500 13px ui-monospace,monospace", color: "#17181a", background: "#fff", resize: "vertical", lineHeight: 1.5 }} />
        </div>

        <div style={{ marginTop: 22, padding: "12px 14px", borderRadius: 10, background: "#fbfaf6", border: "1px solid #eeece6" }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 6 }}>
            SOURCE KEY
          </div>
          <div style={{ font: "500 11.5px 'Inter',sans-serif", color: "#55585e", lineHeight: 1.7 }}>
            <b>FSSAI</b> — Food Safety and Standards Authority of India · <b>WHO</b> — World Health Organization ·{" "}
            <b>ICMR-NIN</b> — Indian Council of Medical Research, National Institute of Nutrition ·{" "}
            <b>INASL</b> — Indian National Association for Study of the Liver · <b>AAP</b> — American Academy
            of Pediatrics · <b>NHS</b> — UK National Health Service ·{" "}
            <b>ACOG</b> — American College of Obstetricians and Gynecologists · <b>CDC</b> — US Centers for
            Disease Control and Prevention · <b>Southampton study</b> — McCann et al., <i>Lancet</i> 2007, on
            synthetic colours and hyperactivity in children · <b>NOVA</b> — the Monteiro et al. food-processing
            classification. A note with no source chip is general reasoning from the ingredient facts above
            it, not an external citation — shown as such rather than dressed up with a source it doesn't have.
          </div>
          <div style={{ marginTop: 8, font: "500 11.5px 'Inter',sans-serif", color: "#55585e", lineHeight: 1.6 }}>
            <b>Underlined chips with ↗</b> link to the actual document and were checked in September 2026:
            FSSAI's own trans-fat regulation, WHO's REPLACE trans-fat initiative, WHO's antenatal care
            guideline on caffeine, and NHS's caffeine guidance (kept as explicitly-labeled secondary
            context, not the lead citation — see the note below on why). <b>Plain-text chips</b> name the
            institution but haven't been pinned to a specific document yet — a real gap, shown honestly
            rather than hidden behind an identical-looking chip.
          </div>
          <div style={{ marginTop: 8, font: "500 11.5px 'Inter',sans-serif", color: "#55585e", lineHeight: 1.6 }}>
            <b>Why FSSAI/WHO lead over NHS/ACOG/CDC/AAP:</b> for an India-first product, Indian regulation
            (FSSAI) and bodies India directly references (WHO) are cited first wherever they cover the
            claim — FSSAI's 2% trans-fat cap is the actual binding standard here, and it predates WHO's
            global target. Single-country foreign health services are kept as secondary, clearly-labeled
            context only where no Indian or WHO guidance covers the same point.
          </div>
        </div>

        {/* Regional standards comparison — India first, honest about gaps */}
        <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 10, background: "#fbfaf6", border: "1px solid #eeece6" }}>
          <div style={{ font: "600 11px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".1em", marginBottom: 4 }}>
            REGIONAL STANDARDS — INDIA / EU / US / WHO
          </div>
          <div style={{ font: "500 11.5px 'Inter',sans-serif", color: "#8a8f98", marginBottom: 10, lineHeight: 1.5 }}>
            Only the two claims below have been checked region-by-region against real documents (Sept 2026).
            This is a starting table, not a complete regulatory comparison — sweeteners, synthetic colours,
            nitrites, and MSG aren't compared here yet.
          </div>
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 720 }}>
              {REGIONAL_STANDARDS.map((row, i) => (
                <div key={row.topic} style={{ marginBottom: i < REGIONAL_STANDARDS.length - 1 ? 14 : 0, paddingBottom: i < REGIONAL_STANDARDS.length - 1 ? 14 : 0, borderBottom: i < REGIONAL_STANDARDS.length - 1 ? "1px dashed #e6e4dd" : "none" }}>
                  <div style={{ font: "700 12.5px 'Inter',sans-serif", color: "#17181a", marginBottom: 8 }}>{row.topic}</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                    {[["India", row.india], ["EU", row.eu], ["US", row.us], ["WHO", row.who]].map(([label, cell]) => (
                      <div key={label} style={{ background: "#fff", borderRadius: 8, border: "1px solid #eeece6", padding: "8px 10px" }}>
                        <div style={{ font: "700 10px ui-monospace,monospace", color: "#9a9ea5", letterSpacing: ".06em", marginBottom: 4 }}>{label.toUpperCase()}</div>
                        <div style={{ font: "500 12px 'Inter',sans-serif", color: "#3a3d42", lineHeight: 1.4 }}>{cell.value}</div>
                        {cell.src.length > 0 && (
                          <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                            {cell.src.map((s) => <SrcChip key={s} s={s} color="#6b6f76" bg="#f2f1ec" border="#e2e0d9" />)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ marginTop: 16, font: "500 11px 'Inter',sans-serif", color: "#b0b3b9", lineHeight: 1.5 }}>
          Prototype · starter database (~35 additives). Ingredient facts only. Age, goal, pregnancy/
          breastfeeding, and metabolic-health relevance are general nutrition information, never a
          diagnosis, blood-sugar target, or treatment plan — no calorie, macro, or supplement dosing is
          calculated anywhere in this app. For a specific condition or plan, check with a doctor,
          paediatrician, OB-GYN, lactation consultant, diabetes educator, or registered dietitian. FSSAI
          statuses marked “verify” are unconfirmed and must be checked before any public claim.
        </div>
      </div>
    </div>
  );
}
