import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, MapGeoJSONFeature, StyleSpecification } from "maplibre-gl";
import type * as GeoJSON from "geojson";
// MapLibre 6 runs its tile worker from a separate module file; Vite emits it as a hashed asset.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { STRINGS, fmtDate, fmtNumber, fmtPercent, fmtShort, type Locale } from "./i18n";

// ---------- Types ----------

type Conf = "high" | "medium" | "low" | "none";

interface District {
  id: string;
  city: string;
  name_ar: string;
  name_en: string;
  ppm2: number | null;
  low: number | null;
  high: number | null;
  conf: Conf;
  conf_score: number;
  reason_ar: string;
  reason_en: string;
  yoy: number | null;
  deals_12m: number;
  last_deal: string | null;
  rent_m2: number | null;
  rent_year: number | null;
  lng: number;
  lat: number;
}

interface City {
  slug: string;
  ar: string;
  en: string;
  bounds: [number, number, number, number];
  districts: number;
  priced: number;
  high: number;
  median_ppm2: number | null;
  breaks: number[];
}

interface Meta {
  data_as_of: string;
  built_at: string;
  cities: City[];
  sources: { id: string; ar: string; en: string; license: string; url: string }[];
  totals: { districts: number; priced: number; high: number };
}

type Feature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, District>;

// ---------- Constants ----------

maplibregl.setWorkerUrl(workerUrl);

const STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron";
const WAITLIST_URL: string | undefined = import.meta.env.VITE_WAITLIST_URL;
const BEACON_TOKEN: string | undefined = import.meta.env.VITE_CF_BEACON_TOKEN;

// Low (teal) through sand to high (coral). Same hue order as the Nyyf Pro map spec.
const COLORS = ["#1f9e8f", "#7ccbb0", "#efe2a8", "#f2a46f", "#d9534f"];
const NO_PRICE = "#c9cac4";
const CONF_OPACITY: Record<Conf, number> = { high: 0.78, medium: 0.62, low: 0.46, none: 0.32 };
const DESKTOP = window.matchMedia("(min-width: 820px)");
const PANEL_W = 400;

const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#efeee9" } }],
};

const expr = (e: unknown) => e as ExpressionSpecification;
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

// ---------- State ----------

let locale: Locale = (() => {
  try {
    const saved = localStorage.getItem("nyyf-locale");
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage blocked */
  }
  return "ar"; // Arabic first: the audience is Saudi brokers and buyers
})();
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

// ---------- Helpers ----------

function name(d: District) {
  return locale === "ar" ? d.name_ar : d.name_en || d.name_ar;
}

function cityName(slug: string) {
  const c = cityBySlug.get(slug);
  return c ? (locale === "ar" ? c.ar : c.en) : slug;
}

function colorFor(d: District) {
  if (d.ppm2 == null) return NO_PRICE;
  const breaks = cityBySlug.get(d.city)?.breaks ?? [];
  let i = 0;
  while (i < breaks.length && d.ppm2 >= breaks[i]) i++;
  return COLORS[i];
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
      ? { top: 140, bottom: 60, left: 40, right: selectedId ? side : 40 }
      : { top: 140, bottom: 60, right: 40, left: selectedId ? side : 40 };
  }
  return { top: 150, bottom: selectedId ? Math.round(window.innerHeight * 0.48) : 110, left: 24, right: 24 };
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

function toast(msg: string) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.append(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 1800);
}

function esc(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

// ---------- Map style expressions ----------

function fillColor() {
  const match: unknown[] = ["match", ["get", "city"]];
  for (const c of meta.cities) {
    const step: unknown[] = ["step", ["to-number", ["get", "ppm2"]], COLORS[0]];
    c.breaks.forEach((b, i) => step.push(b, COLORS[i + 1]));
    match.push(c.slug, step);
  }
  match.push(NO_PRICE);
  return expr(["case", ["==", ["get", "ppm2"], null], NO_PRICE, match]);
}

function fillOpacity() {
  const base = ["match", ["get", "conf"], "high", CONF_OPACITY.high, "medium", CONF_OPACITY.medium, "low", CONF_OPACITY.low, CONF_OPACITY.none];
  const hovered = ["boolean", ["feature-state", "hover"], false];
  if (!selectedId) return expr(["case", hovered, 0.9, base]);
  return expr(["case", ["==", ["get", "id"], selectedId], 0.88, hovered, 0.55, 0.22]);
}

function labelData(): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: features
      .filter((f) => f.properties.ppm2 != null)
      .map((f) => ({
        type: "Feature",
        properties: { id: f.properties.id, price: fmtShort(f.properties.ppm2!, locale), name: name(f.properties) },
        geometry: { type: "Point", coordinates: [f.properties.lng, f.properties.lat] },
      })),
  };
}

function addLayers() {
  const before = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addSource("districts", {
    type: "geojson",
    data: { type: "FeatureCollection", features },
    promoteId: "id",
  });
  map.addLayer(
    {
      id: "district-fill",
      type: "fill",
      source: "districts",
      paint: {
        "fill-color": fillColor(),
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
      paint: {
        "line-color": "#ffffff",
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 14, 1.6],
        "line-opacity": 0.9,
      },
    },
    before,
  );
  map.addLayer({
    id: "district-hover",
    type: "line",
    source: "districts",
    paint: {
      "line-color": "#1d2626",
      "line-width": 1.5,
      "line-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.55, 0],
    },
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
        "text-allow-overlap": false,
      },
      paint: { "text-color": "#1d2626", "text-halo-color": "rgba(255,255,255,0.92)", "text-halo-width": 1.6 },
    });
  }
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
      map.fitBounds(bboxOf(f.geometry), {
        padding: padding(),
        maxZoom: 14,
        duration: 650,
        easing: (x) => 1 - Math.pow(1 - x, 3),
      });
    }
  } else {
    closeSheet();
  }
  writeHash();
}

function flyToCity(slug: string, animate = true) {
  activeCity = slug;
  if (selectedId && byId.get(selectedId)?.properties.city !== slug) select(null);
  renderCities();
  renderLegend();
  map.fitBounds(cityView(slug), { padding: padding(), duration: animate ? 900 : 0 });
  writeHash();
}

function writeHash() {
  const h = selectedId ? `#${activeCity}/${selectedId}` : `#${activeCity}`;
  if (location.hash !== h) history.replaceState(null, "", h);
}

function readHash() {
  const [city, id] = location.hash.replace(/^#/, "").split("/");
  return { city: cityBySlug.has(city) ? city : null, id: id && byId.has(id) ? id : null };
}

// ---------- UI: cities, legend, sheet ----------

function renderCities() {
  const nav = $("cities");
  nav.innerHTML = meta.cities
    .map(
      (c) =>
        `<button class="chip${c.slug === activeCity ? " on" : ""}" data-city="${c.slug}">${esc(locale === "ar" ? c.ar : c.en)}</button>`,
    )
    .join("");
}

function renderLegend() {
  const c = cityBySlug.get(activeCity);
  if (!c) return;
  const s = t();
  const b = c.breaks;
  const labels = b.map((x) => fmtShort(x, locale));
  $("legend").innerHTML = `
    <div class="legend-title">${s.legendTitle}${esc(cityName(c.slug))} <span class="unit">${s.sar_m2}</span></div>
    <div class="ramp">${COLORS.map((col) => `<span style="background:${col}"></span>`).join("")}</div>
    <div class="ticks">${labels.map((l) => `<span>${l}</span>`).join("")}</div>
    <div class="legend-foot">
      <span class="nodata"><i></i>${s.legendNone}</span>
      <span class="muted">${s.legendConf}</span>
    </div>
    <div class="legend-foot">
      <span class="muted">${esc(s.priced(c.priced, c.districts, c.high))}</span>
    </div>
    <button class="asof" id="asof-btn">${s.asOf} ${fmtDate(meta.data_as_of, locale)} · ⓘ</button>`;
}

function confBadge(conf: Conf) {
  return `<span class="badge c-${conf}"><i></i>${t().conf[conf]}</span>`;
}

function renderSheet(d: District) {
  const s = t();
  const priced = d.ppm2 != null;
  const color = colorFor(d);
  let range = "";
  if (priced && d.low != null && d.high != null && d.high > d.low) {
    const lo = Math.min(d.low, d.ppm2!);
    const hi = Math.max(d.high, d.ppm2!);
    const pos = hi > lo ? ((d.ppm2! - lo) / (hi - lo)) * 100 : 50;
    range = `
      <div class="range">
        <div class="range-label">${s.range}</div>
        <div class="range-bar"><span class="dot" style="inset-inline-start:${pos.toFixed(1)}%;background:${color}"></span></div>
        <div class="range-ends"><span>${fmtNumber(d.low, locale)}</span><span>${fmtNumber(d.high, locale)}</span></div>
      </div>`;
  }
  const stats: string[] = [];
  if (priced && d.yoy != null)
    stats.push(
      `<div class="stat"><div class="k">${s.yoy}</div><div class="v ${d.yoy > 0 ? "up" : d.yoy < 0 ? "down" : ""}">${fmtPercent(d.yoy, locale)}</div></div>`,
    );
  stats.push(`<div class="stat"><div class="k">${s.deals12}</div><div class="v">${fmtNumber(d.deals_12m, locale)}</div></div>`);
  if (d.last_deal) stats.push(`<div class="stat"><div class="k">${s.lastDeal}</div><div class="v sm">${fmtDate(d.last_deal, locale)}</div></div>`);
  if (d.rent_m2 != null)
    stats.push(
      `<div class="stat"><div class="k">${s.rent}</div><div class="v">${fmtNumber(d.rent_m2, locale)} <small>${s.rentUnit}</small></div></div>`,
    );

  const pro = WAITLIST_URL
    ? `<a class="pro" href="${esc(WAITLIST_URL)}" target="_blank" rel="noopener"><span>${s.pro}</span><b>${s.proCta} ${locale === "ar" ? "←" : "→"}</b></a>`
    : "";

  $("sheet-body").innerHTML = `
    <div class="eyebrow">${esc(cityName(d.city))}</div>
    <h2>${esc(name(d))}</h2>
    ${
      priced
        ? `<div class="price"><span class="swatch" style="background:${color}"></span><b>${fmtNumber(d.ppm2!, locale)}</b> <span class="unit">${s.sar_m2}</span></div>
           <div class="conf">${confBadge(d.conf)}<span class="reason">${esc(locale === "ar" ? d.reason_ar : d.reason_en)}</span></div>
           ${range}`
        : `<div class="conf">${confBadge("none")}</div><p class="empty">${s.noPrice}</p>`
    }
    <div class="stats">${stats.join("")}</div>
    <div class="actions"><button class="pill primary" id="share-btn">${s.share}</button></div>
    ${pro}
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
    <p>${s.aboutLead}</p>
    <p class="muted">${esc(s.priced(meta.totals.priced, meta.totals.districts, meta.totals.high))} · ${s.asOf} ${fmtDate(meta.data_as_of, locale)}</p>
    <p>${s.method}</p>
    <h3>${s.sources}</h3>
    <ul>${meta.sources
      .map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(locale === "ar" ? x.ar : x.en)}</a> <span class="muted">(${esc(x.license)})</span></li>`)
      .join("")}</ul>
    <p class="muted">${s.licenseNote}</p>
    <p class="fine">${s.disclaimer}</p>`;
}

function applyLocale() {
  const s = t();
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
  document.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    el.textContent = (s as Record<string, unknown>)[el.dataset.i18n!] as string;
  });
  document.querySelectorAll<HTMLInputElement>("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = (s as Record<string, unknown>)[el.dataset.i18nPlaceholder!] as string;
  });
  $("lang-btn").textContent = s.lang;
  document.title = locale === "ar" ? "نيّف · خريطة أسعار الأحياء" : "Nyyf · District price map";
  renderCities();
  renderLegend();
  renderAbout();
  if (selectedId) renderSheet(byId.get(selectedId)!.properties);
  placeControls();
  const labels = map?.getSource("labels") as maplibregl.GeoJSONSource | undefined;
  labels?.setData(labelData());
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
  const scored = index
    .map(({ f, keys }) => {
      const pos = Math.min(...keys.map((k) => (k.indexOf(n) < 0 ? 99 : k.indexOf(n))));
      return { f, pos };
    })
    .filter((x) => x.pos < 99)
    .sort(
      (a, b) =>
        a.pos - b.pos ||
        Number(b.f.properties.city === activeCity) - Number(a.f.properties.city === activeCity) ||
        (b.f.properties.deals_12m - a.f.properties.deals_12m),
    )
    .slice(0, 8);
  results = scored.map((x) => x.f);
  cursor = 0;
  list.innerHTML = results.length
    ? results
        .map((f, i) => {
          const d = f.properties;
          const price = d.ppm2 != null ? `${fmtNumber(d.ppm2, locale)} ${t().sar_m2}` : t().legendNone;
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
  $("lang-btn").addEventListener("click", () => {
    locale = locale === "ar" ? "en" : "ar";
    try {
      localStorage.setItem("nyyf-locale", locale);
    } catch {
      /* storage blocked */
    }
    applyLocale();
  });
  const about = $<HTMLDialogElement>("about");
  $("about-btn").addEventListener("click", () => about.showModal());
  $("legend").addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest("#asof-btn")) about.showModal();
  });
  about.addEventListener("click", (e) => {
    if (e.target === about) about.close();
  });
  $("close").addEventListener("click", () => select(null));

  $("sheet-body").addEventListener("click", async (e) => {
    if (!(e.target as HTMLElement).closest("#share-btn") || !selectedId) return;
    const d = byId.get(selectedId)!.properties;
    const text = d.ppm2 != null ? `${name(d)}: ${fmtNumber(d.ppm2, locale)} ${t().sar_m2}` : name(d);
    const url = location.href;
    try {
      if (navigator.share) await navigator.share({ title: name(d), text, url });
      else {
        await navigator.clipboard.writeText(`${text}\n${url}`);
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
    } else if (e.key === "Enter") {
      pickResult(results[cursor]);
    } else if (e.key === "Escape") {
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
    tip.innerHTML = `<b>${esc(name(d))}</b><span>${
      d.ppm2 != null ? `${fmtNumber(d.ppm2, locale)} ${t().sar_m2} · ${t().conf[d.conf]}` : t().legendNone
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
  // Keep the legend on the city in view.
  map.on("moveend", () => {
    if (selectedId) return;
    const c = map.getCenter();
    const inView = meta.cities.find((x) => c.lng >= x.bounds[0] && c.lng <= x.bounds[2] && c.lat >= x.bounds[1] && c.lat <= x.bounds[3]);
    if (inView && inView.slug !== activeCity) {
      activeCity = inView.slug;
      renderCities();
      renderLegend();
      writeHash();
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
  if (BEACON_TOKEN) {
    const s = document.createElement("script");
    s.defer = true;
    s.src = "https://static.cloudflareinsights.com/beacon.min.js";
    s.dataset.cfBeacon = JSON.stringify({ token: BEACON_TOKEN });
    document.head.append(s);
  }

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
  activeCity = fromHash.id ? byId.get(fromHash.id)!.properties.city : fromHash.city ?? "riyadh";

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
    else writeHash();
  });
}

boot().catch((err) => {
  console.error(err);
  document.body.classList.add("ready");
  $("legend").textContent = "Could not load the map data.";
});
