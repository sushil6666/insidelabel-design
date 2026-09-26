/**
 * Photo scan: AI reads the label, deterministic rules judge it.
 * The AI call streams from the Lovable AI Gateway; the verdict comes from
 * the engine, never from the model.
 */
import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { analyze, tokenize } from "./engine/engine";
import { checkClaims, type ClaimRule } from "./engine/claims";
import { checkAllergens } from "./engine/allergens";
import { assess, applyDisplayRule, disclosures, type VisionRead } from "./engine/gates";

const ALLERGEN_CODES = [
  "gluten", "milk", "egg", "peanut", "tree_nuts",
  "soy", "fish", "crustacean", "sulphite", "sesame", "mustard",
];

const READ_PROMPT = `You are reading an Indian packaged-food label from photo(s). Extract exactly what is printed. Return ONLY JSON with this shape:
{
  "image_content": {"back": "pack" | "screen" | "not_food", "front": "pack" | "screen" | "not_food"},
  "back_status": "read" | "not_found" | "unreadable",
  "ingredients_status": "read" | "partial" | "not_found" | "unreadable",
  "front_status": "read" | "not_provided" | "unreadable",
  "ingredients": ["each ingredient entry verbatim, in printed order"],
  "allergen_statement": "the printed Contains / May contain line, or null",
  "front_claims": ["each marketing claim on the front, verbatim"],
  "confidence": {"ingredients": 0.0-1.0},
  "extraction_notes": ["anything you could not read"]
}
Rules: never invent ingredients; if part of the list is unreadable, set ingredients_status to "partial" and list only what you could read; a photo of a screen or a non-food item must be marked in image_content.`;

async function readLabelWithAI(images: string[]): Promise<VisionRead> {
  const apiKey = process.env["LOVABLE_API_KEY"];
  if (!apiKey) throw new Error("AI reading is not configured on this server.");

  const content: unknown[] = [{ type: "input_text", text: READ_PROMPT }];
  for (const img of images) {
    content.push({ type: "input_image", image_url: `data:image/jpeg;base64,${img}` });
  }

  const response = await fetch("https://ai.gateway.lovable.dev/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      "X-Lovable-AIG-SDK": "fetch",
    },
    body: JSON.stringify({
      model: "openai/gpt-6-astra",
      stream: true,
      store: false,
      reasoning: { effort: "low" },
      input: [{ role: "user", content }],
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    console.error(`AI gateway failed [${response.status}]: ${body}`);
    if (response.status === 402) throw new Error("AI credits are exhausted. Please try again later.");
    if (response.status === 429) throw new Error("Too many scans right now. Please wait a moment and retry.");
    throw new Error(`The label reader is unavailable (${response.status}). Try typing the ingredients instead.`);
  }

  // Consume the SSE stream and accumulate the text.
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          const evt = JSON.parse(payload);
          if (evt.type === "response.output_text.delta" && typeof evt.delta === "string") {
            text += evt.delta;
          } else if (evt.type === "response.completed" && evt.response?.output) {
            for (const item of evt.response.output) {
              for (const part of item.content ?? []) {
                if (part.type === "output_text" && typeof part.text === "string" && !text) {
                  text += part.text;
                }
              }
            }
          }
        } catch {
          // incomplete frame; ignore
        }
      }
    }
  }

  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error("The reader returned nothing usable. Try a sharper photo, or type the ingredients.");
  return JSON.parse(jsonMatch[0]) as VisionRead;
}

function verdictFromIngredients(rawIngredients: string, opts: {
  frontClaims?: string[];
  frontStatus?: "read" | "not_provided" | "unreadable";
  ingredients?: string[];
  allergenStatement?: string | null;
  confidence?: number;
  reliable?: boolean;
  reliability?: ReturnType<typeof assess>["reliability"] | null;
  rules?: ClaimRule[];
  source?: {
    kind: "photo" | "typed";
    ingredients: string[];
    allergenStatement: string | null;
    frontClaims: string[];
    extractionNotes: string[];
    readingConfidence: number | null;
    ingredientsComplete: boolean;
  };
}) {
  const verdict = analyze(rawIngredients);
  const reliability =
    opts.reliability ??
    ({
      error: null,
      ingredients_complete: true,
      verdict_safe_to_display: true,
      caveats: [],
      front_status: opts.frontStatus ?? "not_provided",
    } as ReturnType<typeof assess>["reliability"]);

  const display = applyDisplayRule(verdict, reliability);
  const claims = checkClaims(
    opts.frontClaims ?? [],
    rawIngredients,
    verdict,
    reliability.verdict_safe_to_display === false ? "ingredient_read_uncertain" : opts.frontStatus ?? "not_provided",
    opts.rules,
  );
  const allergens = checkAllergens(
    opts.ingredients ?? tokenize(rawIngredients),
    opts.allergenStatement ?? null,
    ALLERGEN_CODES,
    opts.confidence ?? 1.0,
    opts.reliable ?? true,
  );

  return {
    verdict,
    display,
    claims,
    allergens,
    disclosures: disclosures(reliability),
    reliability: {
      error: reliability.error,
      caveats: reliability.caveats,
      ingredients_complete: reliability.ingredients_complete,
    },
    source: opts.source ?? {
      kind: "typed" as const,
      ingredients: tokenize(rawIngredients),
      allergenStatement: null,
      frontClaims: opts.frontClaims ?? [],
      extractionNotes: [],
      readingConfidence: null,
      ingredientsComplete: true,
    },
  };
}

export const scanPhotos = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z
      .object({
        backImage: z.string().min(100),
        frontImage: z.string().optional(),
      })
      .parse(data),
  )
  .handler(async ({ data }) => {
    const images = [data.backImage];
    if (data.frontImage) images.push(data.frontImage);
    const vision = await readLabelWithAI(images);

    const { proceed, reliability } = assess(vision);
    if (!proceed) {
      return { ok: false as const, reliability };
    }

    const rawIngredients = vision.ingredients.join(", ");
    const frontStatus =
      data.frontImage && vision.front_status === "read" ? ("read" as const) : ("not_provided" as const);

    const { loadApprovedRules, recordUnmatched } = await import("./claim-rules.server");
    const rules = await loadApprovedRules();
    const result = verdictFromIngredients(rawIngredients, {
      frontClaims: vision.front_claims ?? [],
      frontStatus,
      ingredients: vision.ingredients,
      allergenStatement: vision.allergen_statement ?? null,
      confidence: vision.confidence?.ingredients ?? 0,
      reliable: reliability.ingredients_complete === true,
      reliability,
      rules,
      source: {
        kind: "photo",
        ingredients: vision.ingredients,
        allergenStatement: vision.allergen_statement ?? null,
        frontClaims: frontStatus === "read" ? vision.front_claims ?? [] : [],
        extractionNotes: vision.extraction_notes ?? [],
        readingConfidence: vision.confidence?.ingredients ?? null,
        ingredientsComplete: reliability.ingredients_complete === true,
      },
    });
    if (result.claims.status === "checked") await recordUnmatched(result.claims.unmatched_claims);

    return {
      ok: true as const,
      ingredients: vision.ingredients,
      allergen_statement: vision.allergen_statement ?? null,
      front_claims: vision.front_claims ?? [],
      extraction_notes: vision.extraction_notes ?? [],
      result,
    };
  });

export const scanText = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z
      .object({
        ingredients: z.string().min(3),
        frontClaims: z.array(z.string()).optional(),
        avoid: z.array(z.string()).optional(),
      })
      .parse(data),
  )
  .handler(async ({ data }) => {
    const hasFront = (data.frontClaims ?? []).length > 0;
    const avoid = (data.avoid ?? []).filter((c) => ALLERGEN_CODES.includes(c));
    const { loadApprovedRules, recordUnmatched } = await import("./claim-rules.server");
    const rules = await loadApprovedRules();
    const result = verdictFromIngredients(data.ingredients, {
      frontClaims: data.frontClaims ?? [],
      frontStatus: hasFront ? "read" : "not_provided",
      rules,
    });
    if (result.claims.status === "checked") await recordUnmatched(result.claims.unmatched_claims);
    return {
      ok: true as const,
      result,
      allergens: checkAllergens(
        tokenize(data.ingredients),
        null,
        avoid.length ? avoid : ALLERGEN_CODES,
      ),
    };
  });

export const compareProducts = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z
      .object({
        products: z
          .array(z.object({ name: z.string().min(1), ingredients: z.string().min(3) }))
          .min(2)
          .max(4),
      })
      .parse(data),
  )
  .handler(async ({ data }) => {
    const scored = data.products.map((p) => {
      const verdict = analyze(p.ingredients);
      return { name: p.name, verdict };
    });
    // Best pick: highest score; NOVA marker breaks ties downward.
    const ranked = [...scored].sort((a, b) => b.verdict.score - a.verdict.score);
    return {
      products: scored,
      best: ranked[0]?.name ?? null,
    };
  });
