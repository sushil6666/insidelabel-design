import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { scanPhotos, scanText, type PackType } from "@/lib/scan.functions";
import { ScanResult, type ScanResultData } from "@/components/ScanResult";
import { Button } from "@/components/ui/button";
import { Camera, Check, ScanLine, ShieldCheck, Pause, Play, ArrowUpRight, ArrowDown, Diamond, Circle, Hexagon } from "lucide-react";
import labelDetail from "@/assets/home-label-detail.jpg";
import comparePacks from "@/assets/home-compare-packs.jpg";
import decodeLens from "@/assets/home-decode-lens.jpg";
import homeAllPacks from "@/assets/home-all-packs.jpg";
import homeCreamList from "@/assets/home-cream-list.jpg";
import homeMedicineStrip from "@/assets/home-medicine-strip.jpg";
import officialWordmark from "@/assets/insidelabel-wordmark.svg.asset.json";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "InsideLabel: read food, skincare and medicine labels" },
      {
        name: "description",
        content:
          "Photograph the back of a food, skincare or medicine pack (or type the ingredients) and see what is printed, in plain words. Food checks are live today; skincare and medicine checks are being built.",
      },
      { property: "og:title", content: "InsideLabel: read food, skincare and medicine labels" },
      {
        property: "og:description",
        content:
          "Photograph the back of a food, skincare or medicine pack and see what is printed, in plain words. Food checks are live today.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const max = 1280;
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85).split(",")[1]!);
    };
    img.onerror = reject;
    img.src = url;
  });
}

function PhotoButton({
  label,
  hint,
  file,
  onFile,
}: {
  label: string;
  hint: string;
  file: File | null;
  onFile: (f: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <Button
      variant="outline"
      type="button"
      onClick={() => ref.current?.click()}
      className={`flex h-auto w-full items-center justify-start gap-4 whitespace-normal rounded-lg border bg-card p-5 text-left ${
        file ? "border-solid border-border" : "border-dashed border-foreground/25"
      }`}
    >
      <input
        ref={ref}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <span
        className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-2xl ${
          file ? "label-done-icon" : "bg-secondary text-secondary-foreground"
        }`}
      >
        {file ? <Check aria-hidden="true" /> : <Camera aria-hidden="true" />}
      </span>
      <span>
        <span className="block text-base font-bold text-card-foreground">
          {file ? file.name : label}
        </span>
        <span className="block text-sm text-muted-foreground">
          {file ? "Tap to change" : hint}
        </span>
      </span>
    </Button>
  );
}

const PACK_TYPE_LABELS: Record<PackType, string> = {
  food: "Food and drinks",
  personal_care: "Skincare and personal care",
  medicine: "Medicines",
};

type ReadBack = {
  packType: PackType;
  ingredients: string[];
  allergenStatement: string | null;
  extractionNotes: string[];
  readingConfidence: number | null;
  ingredientsComplete: boolean;
  source: "photo" | "typed";
};

/**
 * Skincare, personal-care and medicine checks are not built yet. This shows the
 * printed list exactly as the reader took it and says plainly what is missing.
 */
function ReadOnlyRead({ readBack }: { readBack: ReadBack }) {
  const label = PACK_TYPE_LABELS[readBack.packType].toLowerCase();
  return (
    <section className="mt-8 rounded-lg border border-border bg-card p-5">
      <p className="text-xs font-semibold uppercase text-secondary-foreground">
        {PACK_TYPE_LABELS[readBack.packType]}
      </p>
      <h3 className="font-display text-xl font-extrabold text-foreground">
        We read this list. Checks for {label} are being built.
      </h3>
      <p className="mt-2 text-sm text-muted-foreground">
        The additive, hidden-sugar and processing checks are built for food and are not live for {label} yet. Here is exactly what the reader took from your pack.
      </p>
      <ol className="mt-4 divide-y divide-border border-y border-border">
        {readBack.ingredients.map((ingredient, index) => (
          <li key={`${index}-${ingredient}`} className="flex gap-3 py-2 text-sm text-card-foreground">
            <span className="w-5 shrink-0 text-muted-foreground">{index + 1}.</span>
            <span className="break-words">{ingredient}</span>
          </li>
        ))}
      </ol>
      {readBack.allergenStatement && (
        <p className="mt-3 text-sm text-foreground">
          <strong>Printed warning line:</strong> “{readBack.allergenStatement}”
        </p>
      )}
      {readBack.extractionNotes.length > 0 && (
        <div className="mt-3 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">Reader notes</p>
          <ul className="mt-1 list-disc pl-5">
            {readBack.extractionNotes.map((note, i) => <li key={i}>{note}</li>)}
          </ul>
        </div>
      )}
      {!readBack.ingredientsComplete && (
        <p className="mt-3 text-sm text-muted-foreground">
          Only part of the list was readable. Retake the photo to see the rest.
        </p>
      )}
    </section>
  );
}

const SAMPLE_PAIRS = [
  {
    kind: "avoid",
    icon: Diamond,
    eyebrow: "Example ingredient",
    ingredient: "Wheat flour",
    title: "On your avoid list",
    evidence: "Example label: “wheat flour”",
    explanation:
      "Wheat flour matches wheat on the example avoid list. The red finding is for this match, not a rating of the whole pack.",
  },
  {
    kind: "worth",
    icon: Circle,
    eyebrow: "Example ingredient",
    ingredient: "Sugar",
    title: "Worth a look",
    evidence: "Example label: “sugar”",
    explanation:
      "Sugar is listed as an ingredient. This list does not tell us how much sugar the pack contains; check the nutrition panel for the amount.",
  },
  {
    kind: "info",
    icon: Hexagon,
    eyebrow: "Example ingredient list",
    ingredient: "Oats, wheat flour, sugar, sunflower oil, salt",
    title: "How it's made",
    evidence: "Example label: “oats, wheat flour, sugar, sunflower oil, salt”",
    explanation:
      "These are the ingredients shown in the example. The list alone does not describe every manufacturing step or verify a front-of-pack claim.",
  },
];

function Index() {
  const runScan = useServerFn(scanPhotos);
  const runText = useServerFn(scanText);

  const [mode, setMode] = useState<"photo" | "text">("photo");
  const [motionPaused, setMotionPaused] = useState(false);
  const scannerRef = useRef<HTMLDivElement>(null);
  const [back, setBack] = useState<File | null>(null);
  const [front, setFront] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ detail?: string; hint?: string } | null>(null);
  const [result, setResult] = useState<ScanResultData | null>(null);
  const [activePair, setActivePair] = useState<number | null>(null);
  const [packType, setPackType] = useState<PackType>("food");
  const [readBack, setReadBack] = useState<ReadBack | null>(null);

  function choosePackType(next: PackType) {
    setPackType(next);
    setResult(null);
    setReadBack(null);
    setRefusal(null);
  }

  async function scanPhoto() {
    if (!back) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    setResult(null);
    setReadBack(null);
    try {
      const backImage = await fileToBase64(back);
      const frontImage = front ? await fileToBase64(front) : undefined;
      const res = await runScan({ data: { backImage, frontImage, packType } });
      if (!res.ok) {
        setRefusal(res.reliability);
      } else if (!res.checksAvailable) {
        setReadBack({
          packType: res.packType,
          ingredients: res.ingredients,
          allergenStatement: res.allergen_statement ?? null,
          extractionNotes: res.extraction_notes ?? [],
          readingConfidence: res.reading_confidence ?? null,
          ingredientsComplete: res.ingredients_complete === true,
          source: "photo",
        });
      } else {
        setResult(res.result as ScanResultData);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function scanPasted() {
    setBusy(true);
    setError(null);
    setResult(null);
    setReadBack(null);
    try {
      const res = await runText({ data: { ingredients: text, packType } });
      if (!res.checksAvailable) {
        setReadBack({
          packType: res.packType,
          ingredients: res.ingredients,
          allergenStatement: null,
          extractionNotes: [],
          readingConfidence: null,
          ingredientsComplete: true,
          source: "typed",
        });
      } else {
        setResult(res.result as ScanResultData);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`label-home min-h-screen ${motionPaused ? "label-paused" : ""}`}>
      <nav className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <img src={officialWordmark.url} alt="InsideLabel" width={170} height={34} className="h-[34px] w-[170px] shrink-0" />
          <Button asChild variant="outline" className="rounded-lg bg-card">
          <Link
            to="/compare"
          >
            Compare packs <ArrowUpRight aria-hidden="true" />
          </Link>
          </Button>
        </div>
      </nav>

      <section className="label-hero">
        <img className="label-hero-photo" src={homeAllPacks} width={1264} height={848} alt="Illustrative printed oat drink carton, face cream tube, oat biscuits carton and paracetamol carton" fetchPriority="high" />
        <div className="label-hero-copy">
          <p className="label-eyebrow flex items-center gap-2 text-xs font-semibold uppercase text-secondary-foreground">
            <ScanLine size={16} aria-hidden="true" /> Food, skincare and medicines
          </p>
          <h1 className="font-display text-primary">InsideLabel</h1>
          <h2 className="label-hero-headline font-display text-foreground">See what’s really <span className="text-secondary-foreground">inside</span> the pack.</h2>
          <p className="mt-3 max-w-md text-base text-muted-foreground">
            Snap the ingredient list. Now food, skincare and medicines: what is printed on your pack, read back and explained in plain words, with front-of-pack claims tested against the back.
          </p>
          <Button className="label-hero-cta mt-6 h-12 gap-3 rounded-lg px-6 text-base font-bold" onClick={() => scannerRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })}>Photograph a pack <ArrowDown size={18} aria-hidden="true" /></Button>
          <div className="mt-6 flex flex-wrap gap-4 text-xs font-semibold">
            <span className="label-info-chip"><ShieldCheck size={14} aria-hidden="true" />Allergens first</span>
            <span className="label-info-chip"><ScanLine size={14} aria-hidden="true" />Claim checks</span>
            <span className="label-info-chip">No guessing</span>
          </div>
        </div>
        <div className="label-hero-reading" aria-label="Sample reading">
          <ScanLine size={20} aria-hidden="true" />
          <div><span className="label-mini-head">Sample reading</span><span className="block text-sm text-secondary-foreground">Oats, wheat flour, sugar</span></div>
        </div>
        <Button variant="outline" size="icon" className="label-motion-control bg-card" onClick={() => setMotionPaused((value) => !value)} aria-label={motionPaused ? "Play animation" : "Pause animation"} title={motionPaused ? "Play animation" : "Pause animation"}>
          {motionPaused ? <Play /> : <Pause />}
        </Button>
      </section>

      <main className="mx-auto max-w-6xl px-5 pb-16">
        {!result && !readBack && (
          <section className="label-how border-b border-border pb-8">
            <p className="text-xs font-semibold uppercase text-secondary-foreground">How it works, 3 easy steps</p>
            <h2 className="font-display text-3xl font-extrabold text-foreground">Snap. Decode. Choose better.</h2>
            <ol className="mt-6 grid gap-6 sm:grid-cols-3">
              {[
                ["01", "Snap the back", "The ingredient list is the only part we trust.", "snap"],
                ["02", "We decode it", "Every INS number and sugar alias, matched against our tables.", "decode"],
                ["03", "Plain-words verdict", "Clean, mixed or ultra-processed, with the reasons.", "verdict"],
              ].map(([n, t, d, v]) => (
                <li key={n} className="label-card-step">
                  <div className={`label-step-art label-art-${v}`} aria-hidden="true">
                     <img src={v === "snap" ? labelDetail : v === "decode" ? decodeLens : comparePacks} width={1024} height={1024} alt="" loading="lazy" />
                     {v === "snap" && <div className="label-scan-frame" />}
                  </div>
                  <div className="label-step-caption">
                    <span className="label-step-big font-display">{n}</span>
                    <div><span className="block font-display text-lg font-bold text-foreground">{t}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">{d}</span></div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="label-pack-note mt-5 rounded-lg px-4 py-3 text-sm">
              Food packs get the full verdict today. Skincare and medicine packs get the printed list read back while those checks are built.
            </p>
          </section>
        )}

        <div ref={scannerRef} className="label-scanner border-b border-border py-7">
          <p className="mb-2 text-xs font-semibold uppercase text-secondary-foreground">What are you reading?</p>
          <div className="grid gap-1 rounded-lg bg-secondary p-1 sm:grid-cols-3">
            {(Object.keys(PACK_TYPE_LABELS) as PackType[]).map((t) => (
              <Button
                key={t}
                variant="ghost"
                type="button"
                onClick={() => choosePackType(t)}
                aria-pressed={packType === t}
                className={`h-11 rounded-md text-sm font-semibold transition-colors ${
                  packType === t ? "bg-card text-foreground shadow-soft" : "text-muted-foreground"
                }`}
              >
                {PACK_TYPE_LABELS[t]}
              </Button>
            ))}
          </div>
          {packType !== "food" && (
            <p className="label-pack-note mt-3 rounded-lg px-4 py-3 text-sm">
              We read the printed list and show it back to you. The additive, hidden-sugar and processing checks are built for food and are not live for {PACK_TYPE_LABELS[packType].toLowerCase()} yet.
            </p>
          )}
          <div className="mb-4 mt-4 grid grid-cols-2 gap-1 rounded-lg bg-secondary p-1">
            {(["photo", "text"] as const).map((m) => (
              <Button variant="ghost"
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`h-11 rounded-md text-sm font-semibold transition-colors ${
                  mode === m ? "bg-card text-foreground shadow-soft" : "text-muted-foreground"
                }`}
              >
                {m === "photo" ? "Photograph a pack" : "Paste ingredients"}
              </Button>
            ))}
          </div>

          {mode === "photo" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <PhotoButton
                label="Back of pack (required)"
                hint="The ingredient list, in frame and in focus"
                file={back}
                onFile={setBack}
              />
              <PhotoButton
                label="Front of pack (optional)"
                hint="Lets us check claims like “no added sugar”"
                file={front}
                onFile={setFront}
              />
              <Button
                type="button"
                disabled={!back || busy}
                onClick={scanPhoto}
                className="btn-press h-14 w-full rounded-lg text-base font-bold disabled:opacity-40 sm:col-span-2"
              >
                {busy ? "Reading the label…" : "Read this label →"}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                placeholder="Paste or type the ingredient list, e.g. “Refined wheat flour, sugar, edible vegetable oil (palm), emulsifier (INS 322), raising agent (INS 500(ii))…”"
                className="w-full rounded-2xl border border-input bg-background p-4 text-sm text-card-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/15"
              />
              <Button
                type="button"
                disabled={text.trim().length < 3 || busy}
                onClick={scanPasted}
                className="btn-press h-14 w-full rounded-lg text-base font-bold disabled:opacity-40"
              >
                {busy ? "Checking…" : "Check these ingredients →"}
              </Button>
            </div>
          )}
        </div>

        {error && (
          <p className="label-problem mt-4 rounded-lg p-4 text-sm font-semibold">
            {error}
          </p>
        )}
        {refusal && (
          <div className="label-refusal mt-4 rounded-lg p-4 text-sm">
            <p className="font-bold">{refusal.detail ?? "We couldn't read this label."}</p>
            {refusal.hint && <p className="mt-1">{refusal.hint}</p>}
          </div>
        )}

        {result ? (
          <div className="mt-8">
            <ScanResult data={result} />
          </div>
        ) : readBack ? (
          <ReadOnlyRead readBack={readBack} />
        ) : (
          <>
            <section className="label-feature">
              <div className="label-feature-media">
                <img className="label-feature-photo" src={labelDetail} alt="Illustrative biscuit pack showing its printed ingredient list" width={1024} height={1024} loading="lazy" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-secondary-foreground">Allergens first</p>
                <h3 className="font-display text-2xl font-extrabold text-foreground">Your family's avoid list, checked on every pack.</h3>
                <p className="mt-2 text-muted-foreground">Red only appears when something matches what you told us to avoid. Everything else is explained calmly, in plain words.</p>
                <section className="label-sample-reading" aria-labelledby="sample-result-title">
                  <div className="label-sample-heading"><ScanLine size={18} aria-hidden="true" /><h4 id="sample-result-title">Example scan result</h4><span className="label-example-badge">Illustrative only</span></div>
                  <p className="label-example-note">A made-up example, not a scan of the pictured pack or a result for you.</p>
                  <div className="label-read-evidence">
                    <div className="label-evidence-cell">
                      <h5 className="font-bold">Example ingredients</h5>
                      <p>Oats, wheat flour, sugar, sunflower oil, salt.</p>
                    </div>
                    <div className="label-evidence-cell">
                      <h5 className="font-bold">
                        <strong>Example avoid list:</strong>
                      </h5>
                      <p>Wheat</p>
                    </div>
                  </div>
                  <h5 className="label-findings-title">Flagged findings and explanations</h5>
                  <div className="label-finding-key label-ingredient-pairs" data-active={activePair !== null || undefined}>
                    {SAMPLE_PAIRS.map((pair, i) => {
                      const Icon = pair.icon;
                      return (
                        <div
                          key={pair.title}
                          className={`label-ingredient-pair label-pair-${pair.kind}`}
                          data-active={activePair === i || undefined}
                          tabIndex={0}
                          onPointerEnter={() => setActivePair(i)}
                          onPointerLeave={(e) => {
                            if (e.pointerType === "mouse") setActivePair((c) => (c === i ? null : c));
                          }}
                          onPointerDown={() => setActivePair(i)}
                          onFocus={() => setActivePair(i)}
                          onBlur={() => setActivePair((c) => (c === i ? null : c))}
                        >
                          <div className="label-paired-ingredient">
                            <span>{pair.eyebrow}</span>
                            <strong>{pair.ingredient}</strong>
                          </div>
                          <article className={`label-example-finding label-pill-${pair.kind}`}>
                            <h6>
                              <Icon size={18} aria-hidden="true" />
                              {pair.title}
                            </h6>
                            <p className="label-example-evidence">{pair.evidence}</p>
                            <p>{pair.explanation}</p>
                          </article>
                        </div>
                      );
                    })}
                  </div>
                  <p className="label-example-note">Ingredient evidence only. This example is not medical or dietary advice.</p>
                </section>
              </div>
            </section>

            <section className="label-feature label-feature-flip">
              <div className="label-feature-media">
                <img className="label-feature-photo" src={comparePacks} alt="Two illustrative printed cereal packs side by side" width={1024} height={1024} loading="lazy" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-secondary-foreground">Claim checks</p>
                <h3 className="font-display text-2xl font-extrabold text-foreground">Front-of-pack promises, checked against the back.</h3>
                <p className="mt-2 text-muted-foreground">Photograph the front too and we test claims like “no added sugar” against the real ingredient list. Then compare packs side by side.</p>
                <div className="label-sample-compare">
                  <div className="label-sample-heading">Compare packs</div>
                  <div className="label-compare-options"><span>Pack A</span><span>Pack B</span></div>
                  <div className="label-pill label-pill-info"><Hexagon size={16} aria-hidden="true" />better pick of these</div>
                </div>
                <Button asChild variant="outline" className="mt-4 rounded-lg bg-card"><Link to="/compare">Compare packs <ArrowUpRight aria-hidden="true" /></Link></Button>
              </div>
            </section>

            <section className="label-feature">
              <div className="label-feature-media">
                <img className="label-feature-photo" src={homeCreamList} alt="Illustrative face cream tube showing its printed ingredients list" width={1024} height={1024} loading="lazy" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase text-secondary-foreground">Skincare, personal care and medicines</p>
                <h3 className="font-display text-2xl font-extrabold text-foreground">The printed list, read back word for word.</h3>
                <p className="mt-2 text-muted-foreground">Choose a skincare, personal care or medicine pack and the reader takes the printed list and shows every word back to you, with nothing added.</p>
                <section className="label-sample-reading" aria-labelledby="readback-title">
                  <div className="label-sample-heading"><Hexagon size={18} aria-hidden="true" /><h4 id="readback-title">Example read-back</h4><span className="label-example-badge">Illustrative only</span></div>
                  <p className="label-example-note">A made-up example, not a scan of the pictured tube or a result for you.</p>
                  <div className="label-read-evidence">
                    <div className="label-evidence-cell">
                      <h5 className="font-bold">Example ingredients, skincare and personal care</h5>
                      <p>Aqua, glycerin, cetearyl alcohol, glyceryl stearate, dimethicone, parfum, linalool.</p>
                    </div>
                    <div className="label-evidence-cell">
                      <h5 className="font-bold"><strong>What the reader does:</strong></h5>
                      <p>Shows the list back exactly as printed. No findings are marked.</p>
                    </div>
                  </div>
                  <p className="label-pack-note mt-3 rounded-lg px-4 py-3 text-sm">We read this list. Checks for skincare, personal care and medicines are being built, and none of the food checks apply here.</p>
                </section>
              </div>
            </section>

            <section className="label-band">
              <img src={homeMedicineStrip} alt="Illustrative printed medicine carton and blister strip of tablets" width={1024} height={1024} loading="lazy" />
              <div className="label-band-copy">
              <h3 className="font-display text-2xl font-extrabold">Ready to read your next pack?</h3>
              <Button className="mt-4 h-12 rounded-lg px-6 font-bold" onClick={() => scannerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>Photograph a pack <Camera aria-hidden="true" /></Button>
              </div>
            </section>
          </>
        )}

        <footer className="mt-12 border-t border-border pt-4 text-xs text-muted-foreground">
          InsideLabel reads the printed ingredient list only. Food checks are live today; skincare and medicine checks are being built. It is not medical or dietary advice.{" "}
          <Link to="/admin" className="underline">Admin</Link>
        </footer>
      </main>
    </div>
  );
}
