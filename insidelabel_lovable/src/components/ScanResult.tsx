import { useState } from "react";
import type { Verdict, Flag } from "@/lib/engine/engine";
import type { ClaimCheckResult } from "@/lib/engine/claims";
import type { AllergenResult } from "@/lib/engine/allergens";
import { allergenText } from "@/lib/engine/allergens";
import { Button } from "@/components/ui/button";

export interface ScanResultData {
  verdict: Verdict;
  display: { display_binary: string; display_score: number | null };
  claims: ClaimCheckResult;
  allergens: Record<string, AllergenResult>;
  disclosures: string[];
  reliability: {
    error: string | null;
    caveats: Array<{ code: string; detail: string }>;
    ingredients_complete?: boolean;
  };
  source?: {
    kind: "photo" | "typed";
    ingredients: string[];
    allergenStatement: string | null;
    frontClaims: string[];
    extractionNotes: string[];
    readingConfidence: number | null;
    ingredientsComplete: boolean;
  };
}

const BINARY_STYLE: Record<string, { bg: string; label: string; blurb: string }> = {
  clean: {
    bg: "bg-clean text-clean-foreground",
    label: "Clean",
    blurb: "Nothing in the ingredient list raised a flag.",
  },
  mixed: {
    bg: "bg-mixed text-mixed-foreground",
    label: "Mixed",
    blurb: "Some ingredients are worth knowing about.",
  },
  "ultra-processed": {
    bg: "bg-gradient-to-br from-alert to-warn text-alert-foreground",
    label: "Ultra-processed",
    blurb: "Industrial-formulation markers found in the ingredient list.",
  },
  incomplete: {
    bg: "bg-muted text-muted-foreground",
    label: "Incomplete read",
    blurb: "Part of the ingredient list could not be read, so a clean result can't be supported.",
  },
};

const CONCERN_BADGE: Record<string, string> = {
  high: "bg-alert text-alert-foreground",
  moderate: "bg-warn text-warn-foreground",
  low: "bg-secondary text-secondary-foreground",
  none: "bg-secondary text-secondary-foreground",
};

function FlagCard({ flag }: { flag: Flag }) {
  const [open, setOpen] = useState(false);
  return (
    <Button
      variant="outline"
      type="button"
      onClick={() => setOpen(!open)}
      className={`card-pop h-auto w-full flex-col items-stretch whitespace-normal rounded-lg border bg-card p-4 text-left ${
        flag.concern === "high"
          ? "border-alert/60 border-l-4 border-l-alert"
          : flag.concern === "moderate"
            ? "border-warn/60 border-l-4 border-l-warn"
            : "border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-bold text-card-foreground">{flag.matched_as}</p>
          <p className="text-sm text-muted-foreground">found as “{flag.ingredient}”</p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-wide ${CONCERN_BADGE[flag.concern] ?? CONCERN_BADGE["low"]}`}
        >
          {flag.concern}
        </span>
      </div>
      {open && (
        <div className="mt-3 space-y-2 border-t-2 border-border pt-3 text-sm text-card-foreground">
          <p>{flag.why}</p>
          {flag.sources.length > 0 && (
            <p className="text-xs font-medium text-muted-foreground">Sources: {flag.sources.join(", ")}</p>
          )}
          {flag.verify && (
            <p className="text-xs font-bold text-muted-foreground">
              This entry is marked for human verification.
            </p>
          )}
        </div>
      )}
    </Button>
  );
}

export function ScanResult({ data }: { data: ScanResultData }) {
  const { verdict, display, claims, allergens, disclosures, source } = data;
  const style = BINARY_STYLE[display.display_binary] ?? BINARY_STYLE["mixed"]!;

  const allergenRows = Object.values(allergens);
  const hits = allergenRows.filter((a) => a.state === "contains" || a.state === "may_contain");
  const uncertain = allergenRows.filter((a) => a.state === "uncertain");
  const contradicted = claims.checked.filter((c) => c.contradicted);
  const unreadable = source?.kind === "photo" && (!source.ingredientsComplete || source.readingConfidence === null || source.readingConfidence < 0.95);

  return (
    <div className="space-y-6">
      {/* Verdict banner */}
      <div className={`rounded-3xl p-6 shadow-soft ${style.bg}`}>
        <p className="font-display text-4xl leading-none">{style.label}</p>
        <p className="mt-2 text-sm font-semibold opacity-90">{style.blurb}</p>
        {verdict.hidden_sugar_names.length >= 2 && (
          <p className="mt-3 rounded-xl bg-card px-3 py-2 text-sm font-bold text-alert">
            Sugar appears under {verdict.hidden_sugar_names.length} different names:{" "}
            {verdict.hidden_sugar_names.join(", ")}.
          </p>
        )}
      </div>

      {/* Allergens first */}
      {(hits.length > 0 || uncertain.length > 0) && (
        <section className="border-b border-border pb-5">
          <h2 className="font-display text-lg">Allergens</h2>
          <ul className="mt-3 space-y-2">
            {[...hits, ...uncertain].map((a) => (
              <li
                key={a.code}
                className={`rounded-xl px-3 py-2 text-sm font-bold ${
                  a.state === "uncertain"
                    ? "bg-mixed/40 text-mixed-foreground"
                    : "bg-alert-soft text-alert border-l-4 border-alert"
                }`}
              >
                {allergenText(a, "you")}
                {a.evidence && <span className="mt-1 block font-normal">On label: “{a.evidence}”</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {source && (
        <section className="border-b border-border pb-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-lg">What we read</h2>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${unreadable ? "bg-warn text-warn-foreground" : "bg-secondary text-secondary-foreground"}`}>
              {source.kind === "typed" ? "You entered this" : unreadable ? "Check against the pack" : "Reader marked complete"}
            </span>
          </div>
          {source.kind === "photo" && (
            <p className="mt-2 text-sm text-muted-foreground">
              {source.ingredientsComplete ? "The reader reported a complete list, but this is not independently verified." : "Only part of the list was readable. Missing items may change this result."}{" "}
              {source.readingConfidence === null ? "Reading confidence was not reported." : source.readingConfidence < 0.95 ? "Reading confidence was low. Retake the photo to confirm." : "Check the wording below against your pack."}
            </p>
          )}
          <ol className="mt-3 divide-y divide-border border-y border-border">
            {source.ingredients.map((ingredient, index) => (
              <li key={`${index}-${ingredient}`} className="flex gap-3 py-2 text-sm text-card-foreground">
                <span className="w-5 shrink-0 text-muted-foreground">{index + 1}.</span>
                <span className="break-words">{ingredient}</span>
              </li>
            ))}
          </ol>
          {source.allergenStatement && <p className="mt-3 text-sm text-foreground"><strong>Allergen line:</strong> “{source.allergenStatement}”</p>}
          {source.extractionNotes.length > 0 && (
            <div className="mt-3 text-sm text-muted-foreground">
              <p className="font-semibold text-foreground">Reader notes</p>
              <ul className="mt-1 list-disc pl-5">{source.extractionNotes.map((note, i) => <li key={i}>{note}</li>)}</ul>
            </div>
          )}
        </section>
      )}

      {/* Claim contradictions */}
      {contradicted.length > 0 && (
        <section className="border-b border-border pb-5">
          <h2 className="font-display text-lg">⚠️ Front of pack vs. ingredient list</h2>
          <ul className="mt-3 space-y-3">
            {contradicted.map((c) => (
              <li key={c.claim} className="rounded-xl border-l-4 border-alert bg-alert-soft p-3 text-sm">
                <p className="font-bold text-alert">“{c.claim}”</p>
                <ul className="mt-1 space-y-1 text-muted-foreground">
                  {c.contradicted_by.map((f, i) => (
                    <li key={i}>• {f.fact}{f.evidence && <span className="block pl-3 text-xs">On label: “{f.evidence}”</span>}</li>
                  ))}
                  {c.verify && <li className="mt-2 text-xs font-semibold">Ingredient evidence only. Check the nutrition panel before treating this as a labelling breach.</li>}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}

      {source?.frontClaims && source.frontClaims.length > 0 && (
        <section className="border-b border-border pb-5 text-sm">
          <h2 className="font-display text-lg">Front claims read</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-foreground">{source.frontClaims.map((claim, i) => <li key={i}>“{claim}”</li>)}</ul>
          {claims.status === "not_checked" ? <p className="mt-2 text-muted-foreground">Claims were not checked because the ingredient reading needs confirmation.</p> : claims.unmatched_claims.length > 0 && <p className="mt-2 text-muted-foreground">No rule yet for: {claims.unmatched_claims.join(", ")}. These claims were not checked.</p>}
          {claims.status === "checked" && claims.checked.length > 0 && contradicted.length === 0 && <p className="mt-2 text-muted-foreground">No ingredient-level conflicts found for the claims we can check. This does not verify the claims.</p>}
        </section>
      )}

      {/* Flags */}
      <section>
        <h2 className="font-display text-lg">
          {verdict.flags.length
            ? `What we found (${verdict.flags.length})`
            : "What we found"}
        </h2>
        {verdict.flags.length === 0 ? (
          <p className="mt-2 rounded-2xl border border-border bg-card p-4 text-sm font-medium text-muted-foreground">
            No additives or ultra-processing markers from our tables appear in this
            ingredient list. That is a finding about this list, not a guarantee.
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {verdict.flags.map((f) => (
              <FlagCard key={f.matched_as} flag={f} />
            ))}
          </div>
        )}
      </section>

      {/* Honest disclosures */}
      <section className="rounded-2xl bg-secondary p-5">
        <h2 className="text-sm font-bold uppercase tracking-widest text-secondary-foreground">
          Worth knowing
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm font-medium text-muted-foreground">
          {disclosures.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
