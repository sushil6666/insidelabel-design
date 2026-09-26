import { createFileRoute, Link } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { scanPhotos, scanText } from "@/lib/scan.functions";
import { ScanResult, type ScanResultData } from "@/components/ScanResult";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "InsideLabel: scan a food label" },
      {
        name: "description",
        content:
          "Photograph the back of a food pack (or paste the ingredients) and see additives, hidden sugars and ultra-processing markers in plain words.",
      },
      { property: "og:title", content: "InsideLabel: scan a food label" },
      {
        property: "og:description",
        content:
          "Photograph the back of a food pack and see additives, hidden sugars and ultra-processing markers in plain words.",
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
    <button
      type="button"
      onClick={() => ref.current?.click()}
      className={`card-pop flex w-full items-center gap-4 rounded-2xl border-2 bg-card p-5 text-left ${
        file ? "border-solid border-primary" : "border-dashed border-foreground/25"
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
          file ? "bg-primary text-primary-foreground" : "bg-primary/15 text-primary"
        }`}
      >
        {file ? "✓" : "📷"}
      </span>
      <span>
        <span className="block text-base font-bold text-card-foreground">
          {file ? file.name : label}
        </span>
        <span className="block text-sm text-muted-foreground">
          {file ? "Tap to change" : hint}
        </span>
      </span>
    </button>
  );
}

function Index() {
  const runScan = useServerFn(scanPhotos);
  const runText = useServerFn(scanText);

  const [mode, setMode] = useState<"photo" | "text">("photo");
  const [back, setBack] = useState<File | null>(null);
  const [front, setFront] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ detail?: string; hint?: string } | null>(null);
  const [result, setResult] = useState<ScanResultData | null>(null);

  async function scanPhoto() {
    if (!back) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    setResult(null);
    try {
      const backImage = await fileToBase64(back);
      const frontImage = front ? await fileToBase64(front) : undefined;
      const res = await runScan({ data: { backImage, frontImage } });
      if (!res.ok) {
        setRefusal(res.reliability);
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
    try {
      const res = await runText({ data: { ingredients: text } });
      setResult(res.result as ScanResultData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-xl items-center justify-between px-4 py-3">
          <span className="flex items-center gap-2 font-display text-xl font-extrabold text-foreground">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-sm text-primary-foreground">
              IL
            </span>
            InsideLabel
          </span>
          <Link
            to="/compare"
            className="btn-press rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-soft"
          >
            Compare packs
          </Link>
        </div>
      </nav>

      <section className="bg-hero">
        <div className="mx-auto max-w-xl px-4 pb-10 pt-10">
          <p className="inline-flex items-center gap-2 rounded-full bg-card/80 px-3 py-1 text-xs font-semibold text-secondary-foreground shadow-soft">
            <span className="h-2 w-2 rounded-full bg-primary" /> For packaged foods
          </p>
          <h1 className="mt-4 font-display text-[2.6rem] font-extrabold leading-[1.02] tracking-tight text-foreground">
            See what’s really <span className="text-primary">inside</span> the pack.
          </h1>
          <p className="mt-3 max-w-md text-base text-muted-foreground">
            Snap the ingredient list. We flag additives, hidden sugars and ultra-processing in plain words, and check the front-of-pack claims.
          </p>
          <div className="mt-5 flex flex-wrap gap-2 text-xs font-semibold">
            <span className="rounded-full bg-clean/30 px-3 py-1 text-clean-foreground">Allergens first</span>
            <span className="rounded-full bg-accent/60 px-3 py-1 text-accent-foreground">Claim checks</span>
            <span className="rounded-full bg-mixed/50 px-3 py-1 text-mixed-foreground">No guessing</span>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-xl px-4 pb-16">
        <div className="-mt-4 rounded-3xl border border-border bg-card p-4 shadow-soft sm:p-5">
          <div className="mb-4 grid grid-cols-2 gap-1 rounded-2xl bg-secondary p-1">
            {(["photo", "text"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`btn-press rounded-xl py-2.5 text-sm font-semibold transition-colors ${
                  mode === m ? "bg-card text-foreground shadow-soft" : "text-muted-foreground"
                }`}
              >
                {m === "photo" ? "Photograph a pack" : "Paste ingredients"}
              </button>
            ))}
          </div>

          {mode === "photo" ? (
            <div className="space-y-3">
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
              <button
                type="button"
                disabled={!back || busy}
                onClick={scanPhoto}
                className="btn-press w-full rounded-2xl bg-primary py-4 text-base font-bold text-primary-foreground shadow-soft disabled:opacity-40"
              >
                {busy ? "Reading the label…" : "Read this label →"}
              </button>
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
              <button
                type="button"
                disabled={text.trim().length < 3 || busy}
                onClick={scanPasted}
                className="btn-press w-full rounded-2xl bg-primary py-4 text-base font-bold text-primary-foreground shadow-soft disabled:opacity-40"
              >
                {busy ? "Checking…" : "Check these ingredients →"}
              </button>
            </div>
          )}
        </div>

        {error && (
          <p className="mt-4 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm font-semibold text-destructive">
            {error}
          </p>
        )}
        {refusal && (
          <div className="mt-4 rounded-2xl border border-mixed bg-mixed/25 p-4 text-sm text-mixed-foreground">
            <p className="font-bold">{refusal.detail ?? "We couldn't read this label."}</p>
            {refusal.hint && <p className="mt-1">{refusal.hint}</p>}
          </div>
        )}

        {result ? (
          <div className="mt-8">
            <ScanResult data={result} />
          </div>
        ) : (
          <section className="mt-10">
            <h2 className="font-display text-2xl font-extrabold text-foreground">How it works</h2>
            <ol className="mt-4 grid gap-3">
              {[
                ["1", "Snap the back", "The ingredient list is the only part we trust.", "bg-clean/30 text-clean-foreground"],
                ["2", "We decode it", "Every INS number and sugar alias, matched against our tables.", "bg-accent/60 text-accent-foreground"],
                ["3", "Plain-words verdict", "Clean, mixed or ultra-processed, with the reasons.", "bg-mixed/50 text-mixed-foreground"],
              ].map(([n, t, d, c]) => (
                <li key={n} className="card-pop flex gap-4 rounded-2xl border border-border bg-card p-4 shadow-soft">
                  <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-display text-lg font-extrabold ${c}`}>
                    {n}
                  </span>
                  <span>
                    <span className="block font-semibold text-foreground">{t}</span>
                    <span className="block text-sm text-muted-foreground">{d}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <footer className="mt-12 border-t border-border pt-4 text-xs text-muted-foreground">
          InsideLabel reads the ingredient list only. It is not medical or dietary advice.{" "}
          <Link to="/admin" className="underline">Admin</Link>
        </footer>
      </main>
    </div>
  );
}
