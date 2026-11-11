import "./pages.css";
import { STRINGS, fmtNumber, fmtPercent, fmtQuarter, fmtShort, fmtWindow, type Locale } from "./i18n";
import { $, CITY_NAMES, CITY_SLUGS, analytics, esc, getLocale, renderLeadForm, renderReportForm, renderNav, saveLocale, setDocLocale } from "./common";

type SaleType = "land" | "villa" | "apartment";
interface Point {
  q: string;
  deeds: number;
  value: number;
  ppm2: number | null;
}
interface Top {
  id: string;
  name_ar: string;
  name_en: string;
  value: number;
  n: number;
}
interface CityMarket {
  types: Record<string, Point[]>;
  rent: Record<string, number | null>;
  rent_year?: Record<string, number | null>;
  rent_window?: string | null;
  sale_window?: string | null;
  sale: Record<string, number | null>;
  top_price: Record<SaleType, Top[]>;
  top_active: Record<SaleType, Top[]>;
}
interface Market {
  cities: Record<string, CityMarket>;
}
interface RDistrict {
  id: string;
  name_ar: string;
  name_en: string;
  ppm2: number;
  chg: number;
  qoq: number | null;
  streak: number;
  n: number;
  n_prev_year?: number;
  n_chg?: number | null;
}
interface RSegment {
  compared: number;
  excluded: number;
  bulk?: number;
  wide?: number;
  rising: number;
  falling: number;
  median_chg: number | null;
  risers: RDistrict[];
  fallers: RDistrict[];
  streaks: RDistrict[];
  active: RDistrict[];
}
interface RInsight {
  kind: "top_riser" | "longest_streak" | "top_faller" | "breadth";
  seg: string;
  district?: RDistrict;
  rising?: number;
  falling?: number;
  total?: number;
  median_chg?: number | null;
}
interface RCity {
  source: "rega" | "moj";
  quarter: string;
  from: string;
  vs: string;
  vs_from: string;
  moj_coverage: number;
  segments: Record<string, RSegment>;
  insights: RInsight[];
}
interface Report {
  headline_min?: number;
  headline_max?: number;
  cities: Record<string, RCity>;
}

const SALE_TYPES: SaleType[] = ["land", "villa", "apartment"];
const RESIDENTIAL = ["land", "villa", "apartment", "duplex", "floor"];
// Line colours for the trend chart, one per type (checked against the light background).
const LINE: Record<SaleType, string> = { land: "#1f9e8f", villa: "#d9534f", apartment: "#4b5fb0" };

let locale: Locale = getLocale();
let market: Market | null = null;
let report: Report | null = null;
let seg = "land";
let city = new URLSearchParams(location.search).get("city") ?? "riyadh";
if (!CITY_SLUGS.includes(city)) city = "riyadh";
let topType: SaleType = "apartment";

const t = () => STRINGS[locale];

/** Latest quarter with a price for a type, and the same quarter a year earlier. */
function latest(pts: Point[] | undefined) {
  if (!pts?.length) return null;
  const last = [...pts].reverse().find((p) => p.ppm2 != null) ?? null;
  if (!last) return null;
  const [y, q] = last.q.split("-Q");
  const prev = pts.find((p) => p.q === `${Number(y) - 1}-Q${q}`);
  return { last, yoy: prev?.ppm2 ? last.ppm2! / prev.ppm2 - 1 : null };
}

function lastQuarter(c: CityMarket) {
  const qs = RESIDENTIAL.flatMap((ty) => (c.types[ty] ?? []).map((p) => p.q)).sort();
  return qs[qs.length - 1];
}

function chart(c: CityMarket) {
  const series = SALE_TYPES.map((ty) => ({ ty, pts: (c.types[ty] ?? []).filter((p) => p.ppm2 != null) }));
  // Every quarter from first to last, so a quarter with no data leaves a gap instead of a straight line.
  const qn = (q: string) => Number(q.slice(0, 4)) * 4 + Number(q.slice(-1)) - 1;
  const have = series.flatMap((s) => s.pts.map((p) => qn(p.q)));
  const qs: string[] = [];
  for (let n = Math.min(...have); n <= Math.max(...have); n++) qs.push(`${Math.floor(n / 4)}-Q${(n % 4) + 1}`);
  if (qs.length < 2) return "";
  const vals = series.flatMap((s) => s.pts.map((p) => p.ppm2!));
  const max = Math.max(...vals) * 1.1;
  const W = 640;
  const H = 220;
  const pad = { l: 44, r: 28, t: 12, b: 28 };
  const x = (q: string) => pad.l + (qs.indexOf(q) / (qs.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const grid = [0.25, 0.5, 0.75, 1]
    .map((f) => {
      const v = max * f;
      return `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" class="g"/><text x="${pad.l - 6}" y="${y(v) + 4}" class="yl">${fmtShort(v, locale)}</text>`;
    })
    .join("");
  const xl = qs
    .map((q, i) => (i % Math.ceil(qs.length / 6) === 0 || i === qs.length - 1 ? `<text x="${x(q)}" y="${H - 8}" class="xl">${q.replace("-", " ")}</text>` : ""))
    .join("");
  const lines = series
    .map(({ ty, pts }) => {
      if (pts.length < 2) return "";
      const d = pts
        .map((p, i) => `${i && qn(p.q) - qn(pts[i - 1].q) === 1 ? "L" : "M"}${x(p.q).toFixed(1)},${y(p.ppm2!).toFixed(1)}`)
        .join("");
      const last = pts[pts.length - 1];
      return `<path d="${d}" stroke="${LINE[ty]}" class="ln"/><circle cx="${x(last.q)}" cy="${y(last.ppm2!)}" r="4" fill="${LINE[ty]}"/>`;
    })
    .join("");
  const gap = series.some(({ pts }) => pts.some((p, i) => i && qn(p.q) - qn(pts[i - 1].q) > 1));
  const legend = SALE_TYPES.map((ty) => `<span><i style="background:${LINE[ty]}"></i>${t().types.sale[ty]}</span>`).join("");
  return `<figure class="chart"><figcaption>${t().trend} <span class="muted">(${t().sar_m2})</span></figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${t().trend}" dir="ltr">${grid}${xl}${lines}</svg>
    <div class="chart-legend">${legend}</div>${gap ? `<p class="fine muted">${t().chartGap}</p>` : ""}</figure>`;
}

function reportSection(rc: RCity) {
  const s = t();
  const segs = Object.keys(rc.segments);
  if (!segs.includes(seg)) seg = segs.includes("land") ? "land" : segs[0];
  const sg = rc.segments[seg];
  const segName = (k: string) => (k === "all" ? s.segAll : s.types.sale[k as SaleType]);
  const nm = (d: RDistrict) => esc(locale === "ar" ? d.name_ar : d.name_en || d.name_ar);
  const pct = (v: number) => `<em class="${v > 0 ? "up" : "down"}">${fmtPercent(v, locale)}</em>`;
  const q = (n: number) => s.qtrs(fmtNumber(n, locale));
  const type = seg === "all" ? "land" : seg;
  const href = (d: RDistrict) => `./map.html?mode=sale&type=${type}#${city}/${d.id}`;
  const insights = rc.insights
    .filter((i) => i.seg === seg)
    .map((i) => {
      if (i.kind === "breadth")
        return `<li>${s.ins.breadth(fmtNumber(i.rising!, locale), fmtNumber(i.falling!, locale), fmtNumber(i.total!, locale), i.median_chg != null ? pct(i.median_chg) : "—")}</li>`;
      const d = i.district!;
      return `<li><a href="${href(d)}">${s.ins[i.kind](nm(d), pct(d.chg), q(d.streak))}</a></li>`;
    })
    .join("");
  const table = (title: string, rows: RDistrict[], cell: (d: RDistrict) => string) =>
    `<div class="card"><h3>${title}</h3>${
      rows.length
        ? `<ol>${rows.slice(0, 5).map((d) => `<li><a href="${href(d)}"><span>${nm(d)}</span><b>${cell(d)}</b></a></li>`).join("")}</ol>`
        : `<p class="muted">—</p>`
    }</div>`;
  const streakTag = (d: RDistrict) =>
    `<small class="streak ${d.chg > 0 ? "up" : "down"}" title="${(d.chg > 0 ? s.streakUp : s.streakDown)(q(d.streak))}">${d.chg > 0 ? "▲" : "▼"} ${q(d.streak)}</small>`;
  // Deeds (or deals) behind the move in this period; the same period a year earlier is in the tooltip.
  const deeds = (d: RDistrict) =>
    `<small class="n" title="${d.n_prev_year != null ? s.deedsPrev(fmtNumber(d.n_prev_year, locale)) : ""}">${fmtNumber(d.n, locale)} ${s.deeds}</small>`;
  const age = (q: string) => {
    const end = new Date(Date.UTC(Number(q.slice(0, 4)), Number(q.slice(-1)) * 3, 1));
    return Math.floor((Date.now() - end.getTime()) / (30.4 * 864e5));
  };
  const range = (a: string, b: string) => (a === b ? fmtQuarter(b, locale) : `${fmtQuarter(a, locale)} – ${fmtQuarter(b, locale)}`);
  return `<section class="weekly" id="report">
      <div class="wk-head">
        <h2>${s.wkTitle} · ${esc(CITY_NAMES[city][locale])}</h2>
        <p class="muted">${s.wkLead(range(rc.from, rc.quarter), range(rc.vs_from, rc.vs))}</p>
      </div>
      ${segs.length > 1 ? `<div class="seg-row">${segs.map((k) => `<button class="chip${k === seg ? " on" : ""}" data-seg="${k}">${segName(k)}</button>`).join("")}</div>` : ""}
      <div class="kpis">
        <div class="kpi"><span class="k">${s.wkBreadth} · ${segName(seg)}</span><b><em class="up">${fmtNumber(sg.rising, locale)}</em> / <em class="down">${fmtNumber(sg.falling, locale)}</em></b><span class="d">${fmtNumber(sg.compared, locale)}</span></div>
        <div class="kpi"><span class="k">${s.wkMedian}</span><b>${sg.median_chg != null ? pct(sg.median_chg) : "—"}</b><span class="d">${s.vsLastYearShort}</span></div>
      </div>
      <ul class="insights">${insights}</ul>
      <div class="two four">
        ${table(s.wkRisers, sg.risers, (d) => `${pct(d.chg)} ${streakTag(d)} ${deeds(d)}`)}
        ${table(s.wkStreaks, sg.streaks, (d) => `${streakTag(d)} ${pct(d.chg)} ${deeds(d)}`)}
        ${table(s.wkFallers, sg.fallers, (d) => `${pct(d.chg)} ${streakTag(d)} ${deeds(d)}`)}
        ${table(s.wkActive, sg.active, (d) => `${fmtNumber(d.n, locale)} <small>${s.deeds}</small> ${d.n_chg != null ? pct(d.n_chg) : ""}`)}
      </div>
      ${age(rc.quarter) > 6 ? `<p class="stale">${s.oldData(fmtNumber(age(rc.quarter), locale))}</p>` : ""}
      <p class="fine muted">${s.headlineNote(fmtNumber(report?.headline_min ?? 50, locale), fmtPercent(report?.headline_max ?? 0.4, locale).replace(/^[+\u200e]+/, ""))} ${s.listDeeds}${
        sg.wide ? ` ${s.wideNote(fmtNumber(sg.wide, locale))}` : ""
      }${sg.bulk ? ` ${s.bulkNote(fmtNumber(sg.bulk, locale))}` : ""}</p>
      <p class="fine muted">${rc.source === "rega" ? s.srcRega : s.srcMoj}${sg.excluded ? ` ${s.excluded(fmtNumber(sg.excluded, locale))}` : ""}${
        rc.source === "moj" && rc.moj_coverage < 0.75 ? ` ${s.lowCoverage(fmtPercent(rc.moj_coverage, locale).replace(/^[+\u200e]+/, ""))}` : ""
      }</p>
      <div class="report-box">
        <div><h3>${s.rTitle}</h3><p class="muted">${s.rLead}</p></div>
        <div id="report-form"></div>
      </div>
    </section>`;
}

function render() {
  const s = t();
  setDocLocale(locale);
  document.title = locale === "ar" ? "نيّف · السوق العقاري اليوم" : "Nyyf · The real estate market today";
  renderNav($("nav"), locale, "home");
  $("lang-btn").addEventListener("click", () => {
    locale = locale === "ar" ? "en" : "ar";
    saveLocale(locale);
    render();
  });
  $("foot").innerHTML = `<span>${s.footer}</span><span class="muted">${s.disclaimer}</span>`;

  const shown = market ? CITY_SLUGS.filter((c) => market!.cities[c]) : [city];
  const chips = shown.map(
    (c) => `<button class="chip${c === city ? " on" : ""}" data-city="${c}">${esc(CITY_NAMES[c][locale])}</button>`,
  ).join("");
  const c = market?.cities[city];
  const arrow = locale === "ar" ? "←" : "→";

  let body = `<p class="muted">…</p>`;
  if (c) {
    const lq = lastQuarter(c);
    const inLq = RESIDENTIAL.map((ty) => (c.types[ty] ?? []).find((p) => p.q === lq)).filter(Boolean) as Point[];
    const deeds = inLq.reduce((a, p) => a + p.deeds, 0);
    const value = inLq.reduce((a, p) => a + p.value, 0);
    const kpis = SALE_TYPES.map((ty) => {
      const l = latest(c.types[ty]);
      return `<a class="kpi" href="./map.html?mode=sale&type=${ty}&city=${city}#${city}">
        <span class="k">${s.kPpm2} · ${s.types.sale[ty]}</span>
        <b>${l ? fmtNumber(l.last.ppm2!, locale) : "—"}</b> <span class="u">${s.sar_m2}</span>
        <span class="d">${
          l?.yoy != null ? `<em class="${l.yoy > 0 ? "up" : "down"}">${fmtPercent(l.yoy, locale)}</em> ${s.vsLastYear}` : ""
        }</span>
        ${l ? `<span class="period">${s.periodTo(fmtQuarter(l.last.q, locale))}</span>` : ""}</a>`;
    }).join("");
    // Rent per unit a year (what tenants quote), with per m² beside it.
    const rents = (["apartment", "studio", "villa", "floor"] as const)
      .map((ty) => {
        const y = c.rent_year?.[ty];
        const m2 = c.rent[ty];
        return `<a class="kpi rent" href="./map.html?mode=rent&type=${ty}&city=${city}#${city}">
        <span class="k">${s.kRentUnit} · ${s.types.rent[ty]}</span>
        <b>${y != null ? fmtNumber(y, locale) : m2 != null ? fmtNumber(m2, locale) : "—"}</b> <span class="u">${y != null ? s.sar_unit_year : s.sar_m2_year}</span>
        <span class="d">${s.medianDistrict}${y != null && m2 != null ? ` · ${fmtNumber(m2, locale)} ${s.sar_m2_year}` : ""}</span>
        ${c.rent_window ? `<span class="period">${fmtWindow(c.rent_window, locale)}</span>` : ""}</a>`;
      })
      .join("");
    const list = (rows: Top[], unitLabel: (r: Top) => string) =>
      rows.length
        ? `<ol>${rows
            .map(
              (r) =>
                `<li><a href="./map.html?mode=sale&type=${topType}#${city}/${r.id}"><span>${esc(locale === "ar" ? r.name_ar : r.name_en || r.name_ar)}</span><b>${unitLabel(r)}</b></a></li>`,
            )
            .join("")}</ol>`
        : `<p class="muted">—</p>`;
    body = `
      <section class="kpis">
        <div class="kpi big"><span class="k">${s.kDeals}</span><b>${fmtNumber(deeds, locale)}</b><span class="d">${s.lastQuarter(fmtQuarter(lq, locale))}</span></div>
        <div class="kpi big"><span class="k">${s.kValue}</span><b>${fmtShort(value, locale)}</b> <span class="u">${s.sar}</span><span class="d">${s.lastQuarter(fmtQuarter(lq, locale))}</span></div>
      </section>
      ${report?.cities[city] ? reportSection(report.cities[city]) : ""}
      <section class="kpis three">${kpis}</section>
      <section class="kpis four">${rents}</section>
      ${chart(c)}
      <section class="tops">
        <div class="seg-row">${SALE_TYPES.map((ty) => `<button class="chip${ty === topType ? " on" : ""}" data-top="${ty}">${s.types.sale[ty]}</button>`).join("")}</div>
        <div class="two">
          <div class="card"><h3>${s.topPrice}</h3>${list(c.top_price[topType] ?? [], (r) => `${fmtNumber(r.value, locale)} <small>${s.sar_m2}</small>`)}</div>
          <div class="card"><h3>${s.topActive}</h3>${list(c.top_active[topType] ?? [], (r) => `${fmtNumber(r.n, locale)} <small>${s.deeds}</small>`)}</div>
        </div>
      </section>
      <section class="go">
        <a class="btn primary" href="./map.html?mode=sale&city=${city}#${city}">${s.goSale} ${arrow}</a>
        <a class="btn rent" href="./map.html?mode=rent&city=${city}#${city}">${s.goRent} ${arrow}</a>
      </section>`;
  }

  $("home").innerHTML = `
    <section class="home-head">
      <h1>${s.homeTitle}</h1>
      <p class="lead">${s.homeLead}</p>
      <div class="chips" id="city-chips">${chips}</div>
    </section>
    ${body}
    <section class="join compact" id="join">
      <div class="join-text"><h2>${s.joinTitle}</h2><p>${s.joinLead}</p></div>
      <div id="lead-form"></div>
    </section>`;
  renderLeadForm($("lead-form"), locale, "home");
  const rf = document.getElementById("report-form");
  if (rf) renderReportForm(rf, locale, city, report ? CITY_SLUGS.filter((c) => report!.cities[c]) : CITY_SLUGS);
}

$("home").addEventListener("click", (e) => {
  const el = e.target as HTMLElement;
  const b = el.closest<HTMLElement>("[data-city]");
  if (b) {
    city = b.dataset.city!;
    history.replaceState(null, "", `?city=${city}`);
    render();
    return;
  }
  const sb = el.closest<HTMLElement>("[data-seg]");
  if (sb) {
    seg = sb.dataset.seg!;
    render();
    document.getElementById("report")?.scrollIntoView({ block: "start" });
    return;
  }
  const tb = el.closest<HTMLElement>("[data-top]");
  if (tb) {
    topType = tb.dataset.top as SaleType;
    render();
  }
});

analytics();
render();
fetch("./data/market.json")
  .then((r) => r.json() as Promise<Market>)
  .then((m) => {
    market = m;
    if (!m.cities[city]) city = "riyadh";
    render();
  })
  .catch(() => {
    /* keeps the placeholder */
  });
fetch("./data/report.json")
  .then((r) => r.json() as Promise<Report>)
  .then((w) => {
    report = w;
    render();
  })
  .catch(() => {
    /* the page works without the report */
  });
