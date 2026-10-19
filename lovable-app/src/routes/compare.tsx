import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { compareProducts } from "@/lib/scan.functions";

export const Route = createFileRoute("/compare")({
  head: () => ({
    meta: [
      { title: "InsideLabel: compare packs on the shelf" },
      {
        name: "description",
        content:
          "Paste the ingredient lists of 2 to 4 products and see which one is the cleanest pick, with the flags behind each verdict.",
      },
      { property: "og:title", content: "InsideLabel: compare packs on the shelf" },
      {
        property: "og:description",
        content:
          "Paste the ingredient lists of 2 to 4 products and see which one is the cleanest pick.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Compare,
});

const BINARY_BADGE: Record<string, string> = {
  clean: "bg-clean text-clean-foreground",
  mixed: "bg-mixed text-mixed-foreground",
  "ultra-processed": "bg-gradient-to-br from-alert to-warn text-alert-foreground",
};

interface Row {
  name: string;
  ingredients: string;
}

function Compare() {
  const run = useServerFn(compareProducts);
  const [rows, setRows] = useState<Row[]>([
    { name: "", ingredients: "" },
    { name: "", ingredients: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [out, setOut] = useState<{
    products: Array<{
      name: string;
      verdict: { binary: string; flags: Array<{ matched_as: string; concern: string }> };
    }>;
    best: string | null;
  } | null>(null);

  const update = (i: number, patch: Partial<Row>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function compare() {
    setBusy(true);
    setError(null);
    setOut(null);
    try {
      const res = await run({ data: { products: rows } });
      setOut(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const ready = rows.every((r) => r.name.trim() && r.ingredients.trim().length >= 3);

  return (
    <main className="mx-auto min-h-screen max-w-xl px-4 pb-16">
      <header className="py-8">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="inline-block rounded-full bg-accent px-3 py-1 text-xs font-bold uppercase tracking-widest text-accent-foreground">
              Shelf showdown
            </p>
            <h1 className="mt-3 font-display text-4xl leading-none text-foreground">
              Compare <span className="text-primary">packs</span>
            </h1>
            <p className="mt-2 max-w-xs text-base font-medium text-muted-foreground">
              Two to four products, side by side. Best pick wins on the ingredient list alone.
            </p>
          </div>
          <Link
            to="/"
            className="btn-press mt-1 shrink-0 rounded-full bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground"
          >
            Scan
          </Link>
        </div>
      </header>

      <div className="space-y-4">
        {rows.map((row, i) => (
          <div key={i} className="card-pop rounded-2xl border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-2">
              <input
                value={row.name}
                onChange={(e) => update(i, { name: e.target.value })}
                placeholder={`Product ${i + 1} name`}
                className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm font-bold text-card-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
              />
              {rows.length > 2 && (
                <button
                  type="button"
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  className="shrink-0 rounded-lg px-2 py-1 text-sm font-bold text-muted-foreground hover:text-destructive"
                  aria-label={`Remove product ${i + 1}`}
                >
                  ✕
                </button>
              )}
            </div>
            <textarea
              value={row.ingredients}
              onChange={(e) => update(i, { ingredients: e.target.value })}
              rows={4}
              placeholder="Paste the ingredient list…"
              className="mt-2 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm text-card-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>
        ))}

        {rows.length < 4 && (
          <button
            type="button"
            onClick={() => setRows([...rows, { name: "", ingredients: "" }])}
            className="btn-press w-full rounded-2xl border border-dashed border-foreground/25 py-3.5 text-sm font-bold text-muted-foreground hover:border-primary"
          >
            + Add another product
          </button>
        )}

        <button
          type="button"
          disabled={!ready || busy}
          onClick={compare}
          className="btn-press w-full rounded-2xl bg-primary py-4 text-lg font-bold text-primary-foreground shadow-soft disabled:opacity-40 disabled:shadow-none"
        >
          {busy ? "Comparing…" : "Compare →"}
        </button>

        {error && (
          <p className="rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm font-semibold text-destructive">
            {error}
          </p>
        )}

        {out && (
          <div className="space-y-3 pt-2">
            {out.products.map((p) => (
              <div
                key={p.name}
                className={`rounded-2xl border p-4 ${
                  p.name === out.best
                    ? "border-primary bg-card shadow-soft"
                    : "border-border bg-card"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-display text-lg text-card-foreground">
                    {p.name}
                    {p.name === out.best && (
                      <span className="ml-2 rounded-full bg-accent px-2 py-0.5 align-middle text-xs font-bold text-accent-foreground">
                        Best pick
                      </span>
                    )}
                  </p>
                  <span
                    className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold uppercase ${BINARY_BADGE[p.verdict.binary]}`}
                  >
                    {p.verdict.binary}
                  </span>
                </div>
                {p.verdict.flags.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                    {p.verdict.flags.slice(0, 5).map((f) => (
                      <li key={f.matched_as}>• {f.matched_as}</li>
                    ))}
                    {p.verdict.flags.length > 5 && (
                      <li>…and {p.verdict.flags.length - 5} more</li>
                    )}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm font-medium text-primary">No flags found.</p>
                )}
              </div>
            ))}
            <p className="text-xs font-medium text-muted-foreground">
              Comparison uses the ingredient lists only, not nutrition quantities or price. Food lists only for now.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
