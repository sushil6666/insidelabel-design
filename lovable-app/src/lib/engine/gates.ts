/**
 * Reliability gate. Port of reliability/gates.py (trimmed to what this app
 * collects: no consensus runs or OCR cross-check yet, so those caveats are
 * emitted honestly).
 *
 * A partially-read ingredient list can only ever cause the engine to flag TOO
 * LITTLE. So on a partial read, "ultra-processed" is still true, but "clean"
 * is unsupported.
 */
import type { Verdict } from "./engine";

export interface VisionRead {
  back_status: "read" | "not_found" | "unreadable";
  ingredients_status: "read" | "partial" | "not_found" | "unreadable";
  front_status: "read" | "not_provided" | "unreadable";
  ingredients: string[];
  allergen_statement?: string | null;
  front_claims?: string[];
  image_content?: { back?: string; front?: string };
  confidence?: { ingredients?: number };
  extraction_notes?: string[];
}

export interface Caveat {
  code: string;
  detail: string;
}

export interface Reliability {
  error: string | null;
  detail?: string;
  hint?: string;
  ingredients_complete?: boolean;
  verdict_safe_to_display?: boolean;
  caveats: Caveat[];
  confidence?: Record<string, number | undefined>;
  front_status?: string;
}

const REFUSE: Record<string, string> = {
  not_found: "no_ingredient_list_found",
  unreadable: "ingredient_list_unreadable",
};

export function assess(vision: VisionRead): { proceed: boolean; reliability: Reliability } {
  const { back_status: back, ingredients_status: ing, front_status: front } = vision;

  const seen = vision.image_content?.back;
  if (seen === "screen") {
    return {
      proceed: false,
      reliability: {
        error: "back_is_a_screen",
        detail: "The back photo shows a screen, not the pack itself.",
        hint: "Photograph the physical pack; a listing or a picture on a screen isn't used.",
        caveats: [],
      },
    };
  }
  if (seen === "not_food") {
    return {
      proceed: false,
      reliability: {
        error: "not_a_food_pack",
        detail: "The back photo doesn't show a packaged food.",
        hint: "Photograph the ingredient list on the back of a food pack.",
        caveats: [],
      },
    };
  }

  if (back !== "read") {
    return {
      proceed: false,
      reliability: {
        error: "back_not_read",
        detail: `back_status is ${back}.`,
        hint: "A verdict needs the ingredient list. Retake the back of pack.",
        caveats: [],
      },
    };
  }
  if (REFUSE[ing]) {
    return {
      proceed: false,
      reliability: {
        error: REFUSE[ing],
        detail: `ingredients_status is ${ing}.`,
        hint: "Retake the back of pack with the ingredient list in frame and in focus.",
        caveats: [],
      },
    };
  }
  if (!vision.ingredients?.length) {
    return {
      proceed: false,
      reliability: {
        error: "no_ingredients_extracted",
        detail: "Ingredient array is empty.",
        hint: "An empty list would score 100/100 CLEAN. Refused rather than returned.",
        caveats: [],
      },
    };
  }

  const complete = ing === "read";
  const reliability: Reliability = {
    error: null,
    ingredients_complete: complete,
    verdict_safe_to_display: true,
    caveats: [],
    confidence: vision.confidence ?? {},
    front_status: front,
  };

  if (!complete) {
    reliability.verdict_safe_to_display = false;
    reliability.caveats.push({
      code: "partial_ingredient_list",
      detail:
        "Part of the ingredient list could not be read. Missing ingredients " +
        "can only add flags, never remove them, so a 'clean' or high score " +
        "here is unsupported. Flags that were found are still real.",
    });
  }

  const readingConfidence = vision.confidence?.ingredients;
  if (readingConfidence === undefined || readingConfidence < 0.95) {
    reliability.verdict_safe_to_display = false;
    reliability.caveats.push({
      code: "low_reading_confidence",
      detail: "The ingredient reading could not be confirmed with enough confidence for a reassuring result.",
    });
  }

  // This app reads each photo once; say so honestly.
  reliability.caveats.push({
    code: "single_read",
    detail:
      "Verdict built from one pass over the label. Repeat reads of the same " +
      "image have been observed to differ by a full grade band.",
  });

  if (front !== "read") {
    reliability.caveats.push({
      code: `front_${front}`,
      detail:
        "Front-of-pack claims were not checked. This is not the same as " +
        "finding no contradictions.",
    });
  }

  return { proceed: true, reliability };
}

export function applyDisplayRule(
  verdict: Verdict,
  reliability: Reliability,
): { display_binary: string; display_score: number | null } {
  if (reliability.verdict_safe_to_display !== false) {
    return { display_binary: verdict.binary, display_score: verdict.score };
  }
  // Suppress only the reassuring direction.
  if (verdict.binary === "ultra-processed") {
    return { display_binary: "ultra-processed", display_score: null };
  }
  return { display_binary: "incomplete", display_score: null };
}

const DISCLOSURE_TEXT: Record<string, string> = {
  low_reading_confidence: "The ingredient reading was uncertain. Check the list against your pack or retake the photo.",
  single_read: "The label was read once. A second reading can differ.",
  partial_ingredient_list:
    "Part of the ingredient list could not be read, so this may miss ingredients. Anything flagged is really there.",
  no_independent_verification:
    "The second, independent check of the ingredient list did not run.",
  product_pairing_unverified:
    "These two photos could not be confirmed as the same product, so front-of-pack claims were not checked.",
  front_not_provided: "No front of pack, so marketing claims were not checked.",
  front_unreadable: "The front of pack could not be read, so marketing claims were not checked.",
};

export const ALWAYS_DISCLOSE = [
  "This looks only at the ingredient list. Sugar, salt and fat quantities on the nutrition panel are not part of the score.",
  "Ingredients not yet in the database are not flagged, so an absence of flags is not proof of absence.",
  "Ingredient facts only. This is not advice about whether a food is right for you.",
];

export function disclosures(reliability: Reliability): string[] {
  const out: string[] = [];
  for (const c of reliability.caveats ?? []) {
    const text = DISCLOSURE_TEXT[c.code];
    if (text) out.push(text);
  }
  return [...out, ...ALWAYS_DISCLOSE];
}
