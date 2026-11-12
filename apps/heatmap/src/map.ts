import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, MapGeoJSONFeature, StyleSpecification } from "maplibre-gl";
import type * as GeoJSON from "geojson";
// MapLibre 6 runs its tile worker from a separate module file; Vite emits it as a hashed asset.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { STRINGS, fmtDate, fmtNumber, fmtPercent, fmtQuarter, fmtShort, fmtWindow, type Locale, type Mode } from "./i18n";
import { $, analytics, esc, getLocale, saveLocale, setDocLocale, toast } from "./common";

// ---------- Types ----------

type Conf = "high" | "medium" | "low" | "none";
type SaleType = "all" | "land" | "villa" | "apartment";
type RentType = "apartment" | "villa" | "floor" | "studio";
/** Rent comes per m² a year (`rent_x`) or per unit a year (`rent_x_year`, the average contract). */
type RentUnit = "unit" | "m2";
type MetricKey = `sale_${SaleType}` | `rent_${RentType}` | `rent_${RentType}_year`;

interface District {
  id: string;
  city: string;
  name_ar: string;
  name_en: string;
  ppm2: number | null;
  conf: Conf;
  deals_12m: number;
  last_deal: string | null;
  lng: number;
  lat: number;
  [k: string]: unknown;
}

interface City {
  slug: string;
  ar: string;
  en: string;
  bounds: [number, number, number, number];
  districts: number;
  sale_window: string | null;
  /** The MOJ 12-month window behind sale_all (every residential deal, to the newest MOJ month). */
  sale_all_window?: string | null;
  rent_window?: string | null;
  match?: number | null;
  metrics: Record<MetricKey, { breaks: number[]; priced: number; median: number | null }>;
}

interface Meta {
  data_as_of: string;
  sale_as_of: string | null;
  cities: City[];
  sources: { id: string; ar: string; en: string; license: string; url: string }[];
}

type Feature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, District>;

// ---------- Constants ----------

maplibregl.setWorkerUrl(workerUrl);

const STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron";

const TYPES: { sale: SaleType[]; rent: RentType[] } = {
  sale: ["all", "land", "villa", "apartment"],
  rent: ["apartment", "studio", "villa", "floor"],
};

// Sale: teal (low) through sand to coral (high). Rent: a blue-violet ramp so the two maps never get confused.
const RAMPS: Record<Mode, string[]> = {
  sale: ["#1f9e8f", "#7ccbb0", "#efe2a8", "#f2a46f", "#d9534f"],
  rent: ["#d7e3f4", "#a9c2e6", "#7c9fd6", "#5a76c0", "#3f4f9c"],
};
const NO_PRICE = "#c9cac4";
const CONF_OPACITY: Record<Conf, number> = { high: 0.8, medium: 0.64, low: 0.46, none: 0.3 };
const DESKTOP = window.matchMedia("(min-width: 820px)");
const PANEL_W = 400;

const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#efeee9" } }],
};

const expr = (e: unknown) => e as ExpressionSpecification;

// ---------- State ----------

const params = new URLSearchParams(location.search);
let locale: Locale = getLocale();
let mode: Mode = params.get("mode") === "rent" ? "rent" : "sale";
let type: SaleType | RentType = (() => {
  const t = params.get("type") as SaleType | RentType | null;
  return t && (TYPES[mode] as string[]).includes(t) ? t : TYPES[mode][0];
})();
let rentUnit: RentUnit = params.get("unit") === "m2" ? "m2" : "unit";
let meta: Meta;
let features: Feature[] = [];
let byId = new Map<string, Feature>();
let cityBySlug = new Map<string, City>();
let activeCity = "riyadh";
let selectedId: string | null = null;
let hoverId: string | null = null;
let textFont: string[] | null = null;
let map: maplibregl.Map;

const t = () => STRINGS[locale];
const metricOf = (m: Mode, ty: string): MetricKey =>
  (m === "rent" && rentUnit === "unit" ? `rent_${ty}_year` : `${m}_${ty}`) as MetricKey;
const metric = (): MetricKey => metricOf(mode, type);
/** The per-m² key behind a metric: deal counts and confidence are stored once per type. */
const baseKey = (key: MetricKey) => key.replace(/_year$/, "");
const unit = (m: Mode = mode) => (m === "sale" ? t().sar_m2 : rentUnit === "unit" ? t().sar_unit_year : t().sar_m2_year);

// ---------- Helpers ----------

function name(d: District) {
  return locale === "ar" ? d.name_ar : d.name_en || d.name_ar;
}

function cityName(slug: string) {
  const c = cityBySlug.get(slug);
  return c ? (locale === "ar" ? c.ar : c.en) : slug;
}

function val(d: District, key: MetricKey = metric()) {
  const v = d[key];
  return typeof v === "number" ? v : null;
}

function conf(d: District, key: MetricKey = metric()): Conf {
  return val(d, key) == null ? "none" : ((d[`${baseKey(key)}_conf`] as Conf) ?? "none");
}

function colorFor(d: District, key: MetricKey = metric()) {
  const v = val(d, key);
  if (v == null) return NO_PRICE;
  const breaks = cityBySlug.get(d.city)?.metrics[key]?.breaks ?? [];
  let i = 0;
  while (i < breaks.length && v >= breaks[i]) i++;
  return RAMPS[key.startsWith("sale") ? "sale" : "rent"][i];
}

function typeLabel(m: Mode, ty: string) {
  return (t().types[m] as Record<string, string>)[ty];
}

function bboxOf(geom: GeoJSON.Polygon | GeoJSON.MultiPolygon): [number, number, number, number] {
  const b: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  const rings = geom.type === "Polygon" ? geom.coordinates : geom.coordinates.flat();
  for (const ring of rings)
    for (const [x, y] of ring) {
      if (x < b[0]) b[0] = x;
      if (y < b[1]) b[1] = y;
      if (x > b[2]) b[2] = x;
      if (y > b[3]) b[3] = y;
    }
  return b;
}

/** Bounds of a city's districts with recent deals, so empty outskirts don't zoom the city out. */
function cityView(slug: string): [number, number, number, number] {
  const fs = features.filter((f) => f.properties.city === slug);
  const active = fs.filter((f) => f.properties.deals_12m >= 5);
  const boxes = (active.length ? active : fs).map((f) => bboxOf(f.geometry));
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}

function padding() {
  if (DESKTOP.matches) {
    const side = PANEL_W + 32;
    return locale === "ar"
      ? { top: 190, bottom: 60, left: 40, right: selectedId ? side : 40 }
      : { top: 190, bottom: 60, right: 40, left: selectedId ? side : 40 };
  }
  return { top: 200, bottom: selectedId ? Math.round(window.innerHeight * 0.48) : 120, left: 24, right: 24 };
}

function normalize(s: string) {
  return s
    .toLowerCase()
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/[ً-ْ]/g, "")
    .replace(/^حي\s+/, "")
    .replace(/\b(al|ar|as|ash|ad|an|at|az)[- ]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

// ---------- Map style expressions ----------

function fillColor() {
  const key = metric();
  const ramp = RAMPS[mode];
  const match: unknown[] = ["match", ["get", "city"]];
  for (const c of meta.cities) {
    const breaks = c.metrics[key]?.breaks ?? [];
    // A city with no breaks for this metric (no priced districts) gets the no-price colour: a "step" with no
    // stops is an invalid expression and MapLibre would drop the whole layer, blanking every city.
    if (!breaks.length) {
      match.push(c.slug, NO_PRICE);
      continue;
    }
    const step: unknown[] = ["step", ["to-number", ["get", key]], ramp[0]];
    breaks.forEach((b, i) => step.push(b, ramp[i + 1]));
    match.push(c.slug, step);
  }
  match.push(NO_PRICE);
  return expr(["case", ["==", ["get", key], null], NO_PRICE, match]);
}

function fillOpacity() {
  const key = metric();
  const base = [
    "case",
    ["==", ["get", key], null],
    CONF_OPACITY.none,
    ["match", ["get", `${baseKey(key)}_conf`], "high", CONF_OPACITY.high, "medium", CONF_OPACITY.medium, CONF_OPACITY.low],
  ];
  const hovered = ["boolean", ["feature-state", "hover"], false];
  if (!selectedId) return expr(["case", hovered, 0.9, base]);
  return expr(["case", ["==", ["get", "id"], selectedId], 0.88, hovered, 0.55, 0.22]);
}

function labelData(): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: features
      .filter((f) => val(f.properties) != null)
      .map((f) => ({
        type: "Feature",
        properties: { id: f.properties.id, price: fmtShort(val(f.properties)!, locale), name: name(f.properties) },
        geometry: { type: "Point", coordinates: [f.properties.lng, f.properties.lat] },
      })),
  };
}

function addLayers() {
  const before = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addSource("districts", { type: "geojson", data: { type: "FeatureCollection", features }, promoteId: "id" });
  map.addLayer(
    {
      id: "district-fill",
      type: "fill",
      source: "districts",
      paint: {
        "fill-color": fillColor(),
        "fill-color-transition": { duration: 300 },
        "fill-opacity": fillOpacity(),
        "fill-opacity-transition": { duration: 220 },
      },
    },
    before,
  );
  map.addLayer(
    {
      id: "district-line",
      type: "line",
      source: "districts",
      paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 14, 1.6], "line-opacity": 0.9 },
    },
    before,
  );
  map.addLayer({
    id: "district-hover",
    type: "line",
    source: "districts",
    paint: { "line-color": "#1d2626", "line-width": 1.5, "line-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.55, 0] },
  });
  map.addLayer({
    id: "district-selected",
    type: "line",
    source: "districts",
    filter: ["==", ["get", "id"], ""],
    paint: { "line-color": "#0f4f4c", "line-width": 2.6 },
  });
  if (textFont) {
    map.addSource("labels", { type: "geojson", data: labelData() });
    map.addLayer({
      id: "price-labels",
      type: "symbol",
      source: "labels",
      minzoom: 11.6,
      layout: {
        "text-field": ["format", ["get", "price"], { "font-scale": 1 }, "\n", {}, ["get", "name"], { "font-scale": 0.78 }],
        "text-font": textFont,
        "text-size": ["interpolate", ["linear"], ["zoom"], 12, 12, 15, 15],
        "text-line-height": 1.15,
        "text-padding": 6,
      },
      paint: { "text-color": "#1d2626", "text-halo-color": "rgba(255,255,255,0.92)", "text-halo-width": 1.6 },
    });
  }
}

/** Switch sale/rent and property type in place: colours fade, no reload. */
function setMetric(m: Mode, ty: string) {
  mode = m;
  type = (TYPES[m] as string[]).includes(ty) ? (ty as SaleType | RentType) : TYPES[m][0];
  document.body.dataset.mode = mode;
  if (map?.getLayer("district-fill")) {
    map.setPaintProperty("district-fill", "fill-color", fillColor());
    map.setPaintProperty("district-fill", "fill-opacity", fillOpacity());
    (map.getSource("labels") as maplibregl.GeoJSONSource | undefined)?.setData(labelData());
  }
  renderModes();
  renderLegend();
  if (selectedId) renderSheet(byId.get(selectedId)!.properties);
  writeUrl();
}

// ---------- Selection ----------

function select(id: string | null, opts: { fly?: boolean } = {}) {
  selectedId = id && byId.has(id) ? id : null;
  map.setFilter("district-selected", ["==", ["get", "id"], selectedId ?? ""]);
  map.setPaintProperty("district-fill", "fill-opacity", fillOpacity());
  const f = selectedId ? byId.get(selectedId)! : null;
  if (f) {
    activeCity = f.properties.city;
    renderCities();
    renderLegend();
    renderSheet(f.properties);
    if (opts.fly !== false) {
      map.fitBounds(bboxOf(f.geometry), { padding: padding(), maxZoom: 14, duration: 650, easing: (x) => 1 - Math.pow(1 - x, 3) });
    }
  } else {
    closeSheet();
  }
  writeUrl();
}

function flyToCity(slug: string, animate = true) {
  activeCity = slug;
  if (selectedId && byId.get(selectedId)?.properties.city !== slug) select(null);
  renderCities();
  renderLegend();
  map.fitBounds(cityView(slug), { padding: padding(), duration: animate ? 900 : 0 });
  writeUrl();
}

function writeUrl() {
  const q = `?mode=${mode}&type=${type}${mode === "rent" && rentUnit === "m2" ? "&unit=m2" : ""}`;
  const h = selectedId ? `#${activeCity}/${selectedId}` : `#${activeCity}`;
  if (location.search !== q || location.hash !== h) history.replaceState(null, "", `${location.pathname}${q}${h}`);
}

function readHash() {
  const [city, id] = location.hash.replace(/^#/, "").split("/");
  return { city: cityBySlug.has(city) ? city : null, id: id && byId.has(id) ? id : null };
}

// ---------- UI ----------

function renderModes() {
  const s = t();
  $("modes").innerHTML = (["sale", "rent"] as Mode[])
    .map((m) => `<button class="seg${m === mode ? " on" : ""}" data-mode="${m}" aria-pressed="${m === mode}">${s.mode[m]}</button>`)
    .join("");
  $("types").innerHTML = TYPES[mode]
    .map((ty) => `<button class="chip type${ty === type ? " on" : ""}" data-type="${ty}" aria-pressed="${ty === type}">${typeLabel(mode, ty)}</button>`)
    .join("");
}

function renderCities() {
  $("cities").innerHTML = meta.cities
    .map((c) => `<button class="chip${c.slug === activeCity ? " on" : ""}" data-city="${c.slug}">${esc(locale === "ar" ? c.ar : c.en)}</button>`)
    .join("");
}

function title(m: Mode = mode) {
  const s = t();
  return m === "sale" ? s.metricTitle.sale : s.rentTitle[rentUnit];
}

/** The rent quarters behind a city's rents; cities share the REGA release, so fall back to another city's. */
function rentWindow(c?: City) {
  return c?.rent_window ?? meta.cities.find((x) => x.rent_window)?.rent_window ?? null;
}

/** The quarters behind the sale prices on the map: MOJ deals for "all", REGA deeds for a property type. */
function saleWindow(c?: City) {
  return (type === "all" ? c?.sale_all_window : c?.sale_window) ?? null;
}

/** Months from the end of a "2024-Q3..2025-Q2" window to today. */
function monthsOld(window?: string | null) {
  const q = window?.split("..").pop();
  if (!q) return 0;
  const end = Date.UTC(Number(q.slice(0, 4)), Number(q.slice(-1)) * 3, 1);
  return Math.floor((Date.now() - end) / (30.4 * 864e5));
}

function asOfText(c?: City) {
  const s = t();
  if (mode === "sale") return `${s.asOf} ${fmtWindow(saleWindow(c), locale).split(" – ")[1] ?? ""}`;
  const rw = rentWindow(c);
  return rw ? `${s.periodRent} ${fmtWindow(rw, locale)}` : `${s.asOf} ${fmtDate(meta.data_as_of, locale)}`;
}

let legendObserver: ResizeObserver | null = null;

function renderLegend() {
  const c = cityBySlug.get(activeCity);
  if (!c) return;
  const s = t();
  const m = c.metrics[metric()];
  const labels = (m?.breaks ?? []).map((x) => fmtShort(x, locale));
  $("legend").innerHTML = `
    <div class="legend-title">${title()} · ${typeLabel(mode, type)} · ${esc(cityName(c.slug))} <span class="unit">${mode === "rent" && rentUnit === "unit" ? s.sar : unit()}</span></div>
    ${
      mode === "rent"
        ? `<div class="unit-switch" role="group">${(["unit", "m2"] as RentUnit[])
            .map((u) => `<button class="${u === rentUnit ? "on" : ""}" data-unit="${u}" aria-pressed="${u === rentUnit}">${s.rentUnit[u]}</button>`)
            .join("")}</div>`
        : ""
    }
    <div class="ramp">${RAMPS[mode].map((col) => `<span style="background:${col}"></span>`).join("")}</div>
    <div class="ticks">${labels.map((l) => `<span>${l}</span>`).join("")}</div>
    <div class="legend-foot">
      <span class="nodata"><i></i>${s.legendNone}</span>
      <span class="muted">${s.legendConf}</span>
    </div>
    <div class="legend-foot"><span class="muted">${esc(s.priced(m?.priced ?? 0, c.districts))}</span></div>
    ${mode === "sale" && c.match != null && c.match < 0.85 ? `<div class="legend-foot"><span class="muted">${esc(s.matchNote(fmtPercent(c.match, locale).replace(/^[+\u200e]+/, "")))}</span></div>` : ""}
    ${mode === "rent" && rentUnit === "unit" ? `<div class="legend-foot"><span class="muted">${s.unitNote}</span></div>` : ""}
    ${mode === "rent" && c.slug === "riyadh" ? `<div class="legend-note">${s.riyadhFreeze}</div>` : ""}
    ${mode === "sale" && type === "all" ? `<div class="legend-foot"><span class="muted">${s.allNote}</span></div>` : ""}
    ${mode === "sale" && monthsOld(saleWindow(c)) > 12 ? `<div class="legend-note warn">${s.saleOld(fmtNumber(monthsOld(saleWindow(c)), locale))}</div>` : ""}
    <button class="asof" id="asof-btn">${asOfText(c)} · ⓘ</button>`;
  // The data date sits under the city chips too, where nobody can miss it.
  const old = mode === "sale" ? monthsOld(saleWindow(c)) : monthsOld(rentWindow(c));
  const pill = $("asof-pill");
  pill.className = `asof-pill${old > 12 ? " warn" : ""}`;
  pill.innerHTML = `<i></i>${esc(mode === "sale" ? (saleWindow(c) ? s.pillSale(fmtQuarter(saleWindow(c)!.split("..")[1], locale)) : s.asOf + " " + fmtDate(meta.data_as_of, locale)) : (rentWindow(c) ? s.pillRent(fmtWindow(rentWindow(c), locale)) : s.asOf + " " + fmtDate(meta.data_as_of, locale)))}${
    old > 6 ? ` · ${esc(s.pillAge(fmtNumber(old, locale)))}` : ""
  }`;
  // The zoom buttons sit just above the legend, whose height changes with its notes (and with web fonts).
  legendObserver ??= new ResizeObserver(() =>
    document.documentElement.style.setProperty("--legend-h", `${$("legend").offsetHeight}px`),
  );
  legendObserver.observe($("legend"));
}

function confBadge(c: Conf) {
  return `<span class="badge c-${c}"><i></i>${t().conf[c]}</span>`;
}

function reason(d: District, key: MetricKey) {
  const s = t();
  const n = Number(d[`${baseKey(key)}_n`] ?? 0);
  if (key === "sale_all") return s.reasonAll(n, fmtWindow(cityBySlug.get(d.city)?.sale_all_window, locale));
  if (key.startsWith("sale")) return s.reasonSale(n, fmtWindow(cityBySlug.get(d.city)?.sale_window, locale));
  return s.reasonRent(n, fmtWindow(rentWindow(cityBySlug.get(d.city)), locale));
}

function renderSheet(d: District) {
  const s = t();
  const key = metric();
  const v = val(d);
  const color = colorFor(d);
  const stats: string[] = [];
  const chg = mode === "sale" ? (d[`${key}_chg`] as number | null) : null;
  if (v != null && chg != null)
    stats.push(
      `<div class="stat"><div class="k">${s.change}</div><div class="v ${chg > 0 ? "up" : chg < 0 ? "down" : ""}">${fmtPercent(chg, locale)}</div><div class="k2">${s.changeNote}</div></div>`,
    );
  if (mode === "rent" && v != null) {
    // The other rent unit beside the one on the map.
    const other = rentUnit === "unit" ? (d[`rent_${type}`] as number | null) : (d[`rent_${type}_year`] as number | null);
    if (other != null)
      stats.push(
        `<div class="stat"><div class="k">${rentUnit === "unit" ? s.rentTitle.m2 : `${s.yearlyRent} · ${s.typeOne[type as keyof typeof s.typeOne]}`}</div><div class="v">${fmtNumber(other, locale)} <small>${rentUnit === "unit" ? s.sar_m2_year : s.sar}</small></div></div>`,
      );
  }

  // Every type in this district, tappable to switch the map.
  const rows = (["sale", "rent"] as Mode[])
    .map((m) => {
      const cells = (TYPES[m] as string[])
        .map((ty) => {
          const k = metricOf(m, ty);
          const x = val(d, k);
          const on = k === key ? " on" : "";
          return `<button class="cell${on}" data-metric="${m}:${ty}"><span class="ct">${typeLabel(m, ty)}</span><span class="cv">${
            x != null ? fmtNumber(x, locale) : "—"
          }</span><i style="background:${colorFor(d, k)}"></i></button>`;
        })
        .join("");
      return `<div class="grid-row"><div class="gh">${s.mode[m]} <small>${unit(m)}</small></div><div class="cells">${cells}</div></div>`;
    })
    .join("");

  const moj =
    typeof d.ppm2 === "number" && !(mode === "sale" && type === "all")
      ? `<p class="moj">${s.mojAll}: <b>${fmtNumber(d.ppm2, locale)}</b> ${s.sar_m2} <span class="muted">· ${s.mojNote(fmtDate(meta.data_as_of, locale))}</span></p>`
      : "";

  $("sheet-body").innerHTML = `
    <div class="eyebrow">${esc(cityName(d.city))} · ${title()} · ${typeLabel(mode, type)}</div>
    <h2>${esc(name(d))}</h2>
    ${
      v != null
        ? `<div class="price"><span class="swatch" style="background:${color}"></span><b>${fmtNumber(v, locale)}</b> <span class="unit">${unit()}</span></div>
           <div class="conf">${confBadge(conf(d))}<span class="reason">${esc(reason(d, key))}</span></div>`
        : `<div class="conf">${confBadge("none")}</div><p class="empty">${s.noPrice}</p>`
    }
    ${stats.length ? `<div class="stats">${stats.join("")}</div>` : ""}
    <h3 class="sub">${s.allTypes}</h3>
    <div class="typegrid">${rows}</div>
    ${moj}
    <div class="actions"><button class="pill primary" id="share-btn">${s.share}</button><a class="pill" href="./#join">${s.navJoin}</a></div>
    <p class="fine">${s.disclaimer}</p>`;
  openSheet();
}

function openSheet() {
  const sheet = $("sheet");
  sheet.dataset.state = DESKTOP.matches ? "open" : "half";
  sheet.style.transform = "";
}

function closeSheet() {
  $("sheet").dataset.state = "closed";
  $("sheet").style.transform = "";
}

function renderAbout() {
  const s = t();
  $("about-body").innerHTML = `
    <h2>${s.aboutTitle}</h2>
    <p>${s.methodSale}</p>
    <p>${s.methodRent}</p>
    <p>${s.methodConf}</p>
    <h3>${s.sources}</h3>
    <ul>${meta.sources
      .map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(locale === "ar" ? x.ar : x.en)}</a> <span class="muted">(${esc(x.license)})</span></li>`)
      .join("")}</ul>
    <p class="muted">${s.licenseNote}</p>
    <p class="fine">${s.disclaimer}</p>`;
}

function applyLocale() {
  const s = t();
  setDocLocale(locale);
  document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    el.textContent = (s as Record<string, unknown>)[el.dataset.i18n!] as string;
  });
  document.querySelectorAll<HTMLInputElement>("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = (s as Record<string, unknown>)[el.dataset.i18nPlaceholder!] as string;
  });
  $("lang-btn").textContent = s.lang;
  document.title = locale === "ar" ? "نيّف · خريطة أسعار الأحياء" : "Nyyf · District price map";
  renderModes();
  renderCities();
  renderLegend();
  renderAbout();
  if (selectedId) renderSheet(byId.get(selectedId)!.properties);
  placeControls();
  (map?.getSource("labels") as maplibregl.GeoJSONSource | undefined)?.setData(labelData());
}

// ---------- Search ----------

let index: { f: Feature; keys: string[] }[] = [];
let results: Feature[] = [];
let cursor = 0;

function buildIndex() {
  index = features.map((f) => ({ f, keys: [normalize(f.properties.name_ar), normalize(f.properties.name_en)] }));
}

function runSearch(q: string) {
  const list = $("results");
  const n = normalize(q);
  if (!n) {
    list.hidden = true;
    results = [];
    return;
  }
  results = index
    .map(({ f, keys }) => ({ f, pos: Math.min(...keys.map((k) => (k.indexOf(n) < 0 ? 99 : k.indexOf(n)))) }))
    .filter((x) => x.pos < 99)
    .sort(
      (a, b) =>
        a.pos - b.pos ||
        Number(b.f.properties.city === activeCity) - Number(a.f.properties.city === activeCity) ||
        b.f.properties.deals_12m - a.f.properties.deals_12m,
    )
    .slice(0, 8)
    .map((x) => x.f);
  cursor = 0;
  list.innerHTML = results.length
    ? results
        .map((f, i) => {
          const d = f.properties;
          const v = val(d);
          const price = v != null ? `${fmtNumber(v, locale)} ${unit()}` : t().legendNone;
          return `<li role="option" data-id="${d.id}" class="${i === cursor ? "on" : ""}"><span class="sw" style="background:${colorFor(d)}"></span><span class="nm">${esc(name(d))}<small>${esc(cityName(d.city))}</small></span><span class="pr">${price}</span></li>`;
        })
        .join("")
    : `<li class="none">—</li>`;
  list.hidden = false;
}

function pickResult(f: Feature | undefined) {
  if (!f) return;
  const input = $<HTMLInputElement>("search");
  input.value = "";
  input.blur();
  $("results").hidden = true;
  select(f.properties.id);
}

// ---------- Events ----------

function wireUi() {
  $("cities").addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-city]");
    if (b) flyToCity(b.dataset.city!);
  });
  $("modes").addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-mode]");
    if (b && b.dataset.mode !== mode) setMetric(b.dataset.mode as Mode, type);
  });
  $("types").addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-type]");
    if (b) setMetric(mode, b.dataset.type!);
  });
  $("lang-btn").addEventListener("click", () => {
    locale = locale === "ar" ? "en" : "ar";
    saveLocale(locale);
    applyLocale();
  });
  const about = $<HTMLDialogElement>("about");
  $("legend").addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest("#asof-btn")) about.showModal();
    const u = (e.target as HTMLElement).closest<HTMLElement>("[data-unit]");
    if (u && u.dataset.unit !== rentUnit) {
      rentUnit = u.dataset.unit as RentUnit;
      setMetric(mode, type);
    }
  });
  about.addEventListener("click", (e) => {
    if (e.target === about) about.close();
  });
  $("close").addEventListener("click", () => select(null));
  $("asof-pill").addEventListener("click", () => about.showModal());

  $("sheet-body").addEventListener("click", async (e) => {
    const target = e.target as HTMLElement;
    const cell = target.closest<HTMLElement>("[data-metric]");
    if (cell) {
      const [m, ty] = cell.dataset.metric!.split(":");
      setMetric(m as Mode, ty);
      return;
    }
    if (!target.closest("#share-btn") || !selectedId) return;
    const d = byId.get(selectedId)!.properties;
    const v = val(d);
    const text = v != null ? `${name(d)} · ${typeLabel(mode, type)}: ${fmtNumber(v, locale)} ${unit()}` : name(d);
    try {
      if (navigator.share) await navigator.share({ title: name(d), text, url: location.href });
      else {
        await navigator.clipboard.writeText(`${text}\n${location.href}`);
        toast(t().copied);
      }
    } catch {
      /* user cancelled */
    }
  });

  const input = $<HTMLInputElement>("search");
  input.addEventListener("input", () => runSearch(input.value));
  input.addEventListener("focus", () => input.value && runSearch(input.value));
  input.addEventListener("keydown", (e) => {
    const list = $("results");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!results.length) return;
      cursor = (cursor + (e.key === "ArrowDown" ? 1 : results.length - 1)) % results.length;
      list.querySelectorAll("li").forEach((li, i) => li.classList.toggle("on", i === cursor));
    } else if (e.key === "Enter") pickResult(results[cursor]);
    else if (e.key === "Escape") {
      input.value = "";
      list.hidden = true;
      input.blur();
    }
  });
  $("results").addEventListener("pointerdown", (e) => {
    const li = (e.target as HTMLElement).closest<HTMLElement>("[data-id]");
    if (li) {
      e.preventDefault();
      pickResult(byId.get(li.dataset.id!));
    }
  });
  input.addEventListener("blur", () => setTimeout(() => ($("results").hidden = true), 120));

  document.addEventListener("keydown", (e) => {
    const typing = (e.target as HTMLElement).matches("input, textarea");
    if (e.key === "/" && !typing) {
      e.preventDefault();
      input.focus();
    } else if (e.key === "Escape" && !typing && selectedId) select(null);
  });

  // Mobile bottom sheet: drag the handle between half, full and closed.
  const sheet = $("sheet");
  const grab = $("grab");
  let startY = 0;
  let dy = 0;
  let dragging = false;
  grab.addEventListener("pointerdown", (e) => {
    if (DESKTOP.matches) return;
    dragging = true;
    startY = e.clientY;
    dy = 0;
    grab.setPointerCapture(e.pointerId);
    sheet.classList.add("dragging");
  });
  grab.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dy = e.clientY - startY;
    sheet.style.transform = `translateY(calc(var(--sheet-y) + ${dy}px))`;
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    sheet.classList.remove("dragging");
    sheet.style.transform = "";
    const state = sheet.dataset.state;
    if (Math.abs(dy) < 6) sheet.dataset.state = state === "full" ? "half" : "full";
    else if (dy < -40) sheet.dataset.state = "full";
    else if (dy > 60) {
      if (state === "full") sheet.dataset.state = "half";
      else select(null);
    }
  };
  grab.addEventListener("pointerup", end);
  grab.addEventListener("pointercancel", end);
}

function wireMap() {
  const tip = $("tooltip");
  const canHover = window.matchMedia("(hover: hover)").matches;
  map.on("mousemove", "district-fill", (e) => {
    const f = e.features?.[0] as MapGeoJSONFeature | undefined;
    if (!f) return;
    const id = String(f.properties.id);
    if (id !== hoverId) {
      if (hoverId) map.setFeatureState({ source: "districts", id: hoverId }, { hover: false });
      hoverId = id;
      map.setFeatureState({ source: "districts", id }, { hover: true });
    }
    map.getCanvas().style.cursor = "pointer";
    if (!canHover) return;
    const d = byId.get(id)!.properties;
    const v = val(d);
    tip.innerHTML = `<b>${esc(name(d))}</b><span>${typeLabel(mode, type)} · ${
      v != null ? `${fmtNumber(v, locale)} ${unit()} · ${t().conf[conf(d)]}` : t().legendNone
    }</span>`;
    tip.hidden = false;
    tip.style.transform = `translate(${e.point.x + 14}px, ${e.point.y + 14}px)`;
  });
  map.on("mouseleave", "district-fill", () => {
    if (hoverId) map.setFeatureState({ source: "districts", id: hoverId }, { hover: false });
    hoverId = null;
    tip.hidden = true;
    map.getCanvas().style.cursor = "";
  });
  map.on("click", (e) => {
    const hit = map.queryRenderedFeatures(e.point, { layers: ["district-fill"] })[0];
    if (hit) {
      const id = String(hit.properties.id);
      select(id === selectedId ? null : id);
    } else if (selectedId) select(null);
  });
  map.on("moveend", () => {
    if (selectedId) return;
    const c = map.getCenter();
    const inView = meta.cities.find((x) => c.lng >= x.bounds[0] && c.lng <= x.bounds[2] && c.lat >= x.bounds[1] && c.lat <= x.bounds[3]);
    if (inView && inView.slug !== activeCity) {
      activeCity = inView.slug;
      renderCities();
      renderLegend();
      writeUrl();
    }
  });
}

// ---------- Boot ----------

const controls = {
  nav: new maplibregl.NavigationControl({ showCompass: false }),
  locate: new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: false }, fitBoundsOptions: { maxZoom: 13 } }),
  attribution: new maplibregl.AttributionControl({ compact: true }),
};

/** Zoom and locate sit on the legend's side (inline end), above it; attribution takes the other corner. */
function placeControls() {
  if (!map) return;
  for (const c of Object.values(controls)) if (map.hasControl(c)) map.removeControl(c);
  const end = locale === "ar" ? "bottom-left" : "bottom-right";
  const start = locale === "ar" ? "bottom-right" : "bottom-left";
  map.addControl(controls.nav, end);
  map.addControl(controls.locate, end);
  map.addControl(controls.attribution, start);
}

async function loadStyle(): Promise<StyleSpecification> {
  try {
    const res = await fetch(STYLE_URL);
    if (!res.ok) throw new Error(String(res.status));
    const style = (await res.json()) as StyleSpecification;
    for (const l of style.layers) {
      const font = l.type === "symbol" ? (l.layout?.["text-font"] as unknown) : null;
      if (Array.isArray(font) && font.every((x) => typeof x === "string")) {
        textFont = font as string[];
        break;
      }
    }
    if (!style.glyphs) textFont = null;
    return style;
  } catch {
    textFont = null;
    return FALLBACK_STYLE;
  }
}

async function boot() {
  analytics();
  document.body.dataset.mode = mode;
  const [style, m, geo] = await Promise.all([
    loadStyle(),
    fetch("./data/meta.json").then((r) => r.json() as Promise<Meta>),
    fetch("./data/districts.geojson").then((r) => r.json() as Promise<GeoJSON.FeatureCollection>),
  ]);
  meta = m;
  features = geo.features as Feature[];
  byId = new Map(features.map((f) => [f.properties.id, f]));
  cityBySlug = new Map(meta.cities.map((c) => [c.slug, c]));
  buildIndex();

  const fromHash = readHash();
  activeCity = fromHash.id ? byId.get(fromHash.id)!.properties.city : (params.get("city") ?? fromHash.city ?? "riyadh");
  if (!cityBySlug.has(activeCity)) activeCity = "riyadh";

  map = new maplibregl.Map({
    container: "map",
    style,
    bounds: cityView(activeCity),
    fitBoundsOptions: { padding: padding() },
    maxBounds: [
      [33.5, 15.5],
      [56.5, 33.5],
    ],
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
    fadeDuration: 200,
  });
  map.touchZoomRotate.disableRotation();
  applyLocale();
  wireUi();

  map.on("load", () => {
    addLayers();
    wireMap();
    document.body.classList.add("ready");
    if (fromHash.id) select(fromHash.id);
    else writeUrl();
  });
}

boot().catch((err) => {
  console.error(err);
  document.body.classList.add("ready");
  $("legend").textContent = "Could not load the map data.";
});
