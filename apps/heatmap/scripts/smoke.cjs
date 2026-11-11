// Opens every page and every map mode/type of the built site and fails on a script or map error.
// A broken colour expression (for example a city with no breaks) makes MapLibre drop the fill layer and
// log an error while the page still "works", so the check also waits for the district fill to render.
// Usage: node scripts/smoke.cjs [base url]   (default http://localhost:4173/, a running `vite preview`)
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://localhost:4173/";
const PAGES = [
  "index.html",
  "home.html",
  ...["land", "villa", "apartment"].map((t) => `map.html?mode=sale&type=${t}`),
  ...["apartment", "studio", "villa", "floor"].flatMap((t) => [
    `map.html?mode=rent&type=${t}`,
    `map.html?mode=rent&type=${t}&unit=m2`,
  ]),
];
// Network noise (basemap tiles, analytics) is not a site bug.
const IGNORE = /Failed to load resource|net::ERR_|AJAXError|tiles\.openfreemap|cloudflareinsights/i;

(async () => {
  // In CI, use the Google Chrome the runner already has (SMOKE_CHANNEL=chrome) instead of downloading one.
  const browser = await chromium.launch(process.env.SMOKE_CHANNEL ? { channel: process.env.SMOKE_CHANNEL } : {});
  const failures = [];
  for (const path of PAGES) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error" && !IGNORE.test(m.text())) errors.push(m.text());
    });
    await page.goto(BASE + path, { waitUntil: "load" });
    if (path.startsWith("map.html")) {
      // The legend renders once the data and the style are in; give the map a moment to paint.
      await page.waitForSelector("#legend .ramp", { timeout: 20000 }).catch(() => errors.push("legend never rendered"));
    }
    await page.waitForTimeout(2500);
    console.log(`${errors.length ? "FAIL" : "ok  "}  ${path}`);
    errors.forEach((e) => console.log(`      ${e.slice(0, 300)}`));
    if (errors.length) failures.push(path);
    await page.close();
  }
  await browser.close();
  if (failures.length) {
    console.error(`${failures.length} page(s) failed`);
    process.exit(1);
  }
})();
