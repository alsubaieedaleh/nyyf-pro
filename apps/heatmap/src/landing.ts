import "./pages.css";
import { STRINGS, fmtNumber, type Locale } from "./i18n";
import { $, analytics, getLocale, renderLeadForm, renderNav, saveLocale, setDocLocale } from "./common";

interface Market {
  cities: Record<string, { types: Record<string, { q: string; deeds: number }[]> }>;
}
interface Meta {
  totals: { districts: number };
  cities: unknown[];
}

let locale: Locale = getLocale();
let stats: { districts: number; deeds: number; cities: number } | null = null;

function render() {
  const s = STRINGS[locale];
  setDocLocale(locale);
  document.title = locale === "ar" ? "نيّف · أسعار العقار في كل حي" : "Nyyf · Real estate prices in every district";
  renderNav($("nav"), locale, "landing");
  const arrow = locale === "ar" ? "←" : "→";
  $("landing").innerHTML = `
    <section class="hero">
      <div class="hero-text">
        <h1>${s.heroTitle}</h1>
        <p class="lead">${s.heroLead}</p>
        <div class="cta">
          <a class="btn primary" href="./map.html?mode=sale">${s.ctaSale} ${arrow}</a>
          <a class="btn rent" href="./map.html?mode=rent">${s.ctaRent} ${arrow}</a>
          <a class="btn ghost" href="./home.html">${s.ctaMarket}</a>
        </div>
        <dl class="hero-stats" id="hero-stats"></dl>
      </div>
      <a class="hero-shot" href="./map.html?mode=sale" aria-label="${s.ctaSale}">
        <img src="./preview.jpg" alt="" width="850" height="770" loading="eager" />
      </a>
    </section>
    <section class="features">
      <article><span class="ic">▦</span><h3>${s.f1t}</h3><p>${s.f1d}</p></article>
      <article><span class="ic">◎</span><h3>${s.f2t}</h3><p>${s.f2d}</p></article>
      <article><span class="ic">↻</span><h3>${s.f3t}</h3><p>${s.f3d}</p></article>
    </section>
    <section class="join" id="join">
      <div class="join-text">
        <h2>${s.joinTitle}</h2>
        <p>${s.joinLead}</p>
      </div>
      <div id="lead-form"></div>
    </section>`;
  renderLeadForm($("lead-form"), locale, "landing");
  $("foot").innerHTML = `<span>${s.footer}</span><span class="muted">${s.disclaimer}</span>`;
  $("lang-btn").addEventListener("click", () => {
    locale = locale === "ar" ? "en" : "ar";
    saveLocale(locale);
    render();
  });
  renderStats();
  if (location.hash === "#join") document.getElementById("join")?.scrollIntoView();
}

function renderStats() {
  const s = STRINGS[locale];
  const el = document.getElementById("hero-stats");
  if (!el || !stats) return;
  el.innerHTML = `
    <div><dt>${fmtNumber(stats.districts, locale)}</dt><dd>${s.stat1}</dd></div>
    <div><dt>${fmtNumber(stats.deeds, locale)}</dt><dd>${s.stat2}</dd></div>
    <div><dt>${fmtNumber(stats.cities, locale)}</dt><dd>${s.stat3}</dd></div>`;
}

async function loadStats() {
  try {
    const [meta, market] = await Promise.all([
      fetch("./data/meta.json").then((r) => r.json() as Promise<Meta>),
      fetch("./data/market.json").then((r) => r.json() as Promise<Market>),
    ]);
    let deeds = 0;
    for (const c of Object.values(market.cities))
      for (const pts of Object.values(c.types)) for (const p of pts.slice(-4)) deeds += p.deeds;
    stats = { districts: meta.totals.districts, deeds, cities: meta.cities.length };
    renderStats();
  } catch {
    /* the page works without the numbers */
  }
}

analytics();
render();
loadStats();
