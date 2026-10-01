// Measures where elements sit inside a scene (camera coordinates), so zooms can be precomputed:
// the paused render can't be trusted to have laid out a scene when its script first runs.
// Needs playwright-core and a Chromium: PLAYWRIGHT_CORE (module path) and CHROMIUM_PATH override the defaults.
const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
import fs from "node:fs";
import path from "node:path";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const jobs = JSON.parse(process.argv[2]);           // {"c3": ["c3-allergen"], ...}
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const out = {};
for (const [c, ids] of Object.entries(jobs)) {
  const src = fs.readFileSync(path.join(root, "compositions", c + ".html"), "utf8");
  const tpl = src.split("<template>")[1].split("</template>")[0].replace(/<script>[\s\S]*?<\/script>/, "");
  const width = +src.match(/data-width="(\d+)"/)[1], height = +src.match(/data-height="(\d+)"/)[1];
  const page = await browser.newPage({ viewport: { width, height } });
  fs.writeFileSync(path.join(root, ".measure.html"),
    `<!doctype html><html><head><meta charset="utf-8"><style>*{margin:0;padding:0;box-sizing:border-box}body{width:${width}px;height:${height}px;position:relative}</style></head><body>${tpl}</body></html>`);
  await page.goto("file://" + path.join(root, ".measure.html"));
  await page.evaluate(() => document.fonts.ready);
  out[c] = await page.evaluate((ids) => Object.fromEntries(ids.map((id) => {
    const r = document.getElementById(id).getBoundingClientRect();
    return [id, [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2), Math.round(r.width), Math.round(r.height)]];
  })), ids);
  await page.close();
}
fs.unlinkSync(path.join(root, ".measure.html"));
console.log(JSON.stringify(out));
await browser.close();
