/** Ingredient classification and NOVA marker detection. Port of core/classify.py. */
import { extractIns } from "./tokenize";

export interface AdditiveRow {
  ins: string;
  name: string;
  class: string;
  concern: string;
  why: string;
  sources: string[];
  flags?: string[];
  verify?: boolean;
}

export interface NovaMarker {
  id: string;
  name: string;
  category: string;
  aliases: string[];
}

export interface Flag {
  ingredient: string;
  matched_as: string;
  type: "additive" | "nova_marker";
  concern: string;
  why: string;
  sources: string[];
  flags: string[];
  verify: boolean;
  nova_group4: boolean;
}

function novaMarker(
  token: string,
  canonical: string,
  novaLookup: Record<string, NovaMarker>,
): NovaMarker | null {
  for (const key of [token, canonical]) {
    if (novaLookup[key]) return novaLookup[key];
  }
  for (const [al, marker] of Object.entries(novaLookup)) {
    if (token.includes(al)) return marker;
  }
  return null;
}

export function isNova(
  token: string,
  canonical: string,
  novaLookup: Record<string, NovaMarker>,
): boolean {
  return novaMarker(token, canonical, novaLookup) !== null;
}

export function classifyToken(
  token: string,
  synonymLookup: Record<string, string>,
  additiveByIns: Record<string, AdditiveRow>,
  novaLookup: Record<string, NovaMarker>,
): Flag | null {
  const canonical = synonymLookup[token] ?? token;
  const ins = extractIns(token);

  if (ins && additiveByIns[ins]) {
    const a = additiveByIns[ins];
    return {
      ingredient: token,
      matched_as: `INS ${ins} (${a.name})`,
      type: "additive",
      concern: a.concern,
      why: a.why,
      sources: a.sources,
      flags: a.flags ?? [],
      verify: a.verify ?? false,
      nova_group4: isNova(token, canonical, novaLookup),
    };
  }

  for (const a of Object.values(additiveByIns)) {
    const nameL = a.name.toLowerCase();
    if (
      canonical === nameL ||
      token === nameL ||
      nameL.split(" (").includes(canonical)
    ) {
      return {
        ingredient: token,
        matched_as: `${a.name} (INS ${a.ins})`,
        type: "additive",
        concern: a.concern,
        why: a.why,
        sources: a.sources,
        flags: a.flags ?? [],
        verify: a.verify ?? false,
        nova_group4: isNova(token, canonical, novaLookup),
      };
    }
  }

  const marker = novaMarker(token, canonical, novaLookup);
  if (marker) {
    return {
      ingredient: token,
      matched_as: `NOVA marker: ${marker.name}`,
      type: "nova_marker",
      concern: marker.category !== "cosmetic_additive" ? "moderate" : "low",
      why:
        `Ultra-processing marker (${marker.category.replace(/_/g, " ")}). ` +
        "Rarely used in home cooking; signals industrial formulation.",
      sources: ["NOVA"],
      flags: ["nova_group4_marker", marker.category],
      verify: false,
      nova_group4: true,
    };
  }

  return null;
}
