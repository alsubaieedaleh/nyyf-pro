import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";

/** District stats: sold prices from Ministry of Justice deals, asking prices from listings. */
export type DistrictProps = {
  id: number;
  name_ar: string;
  name_en: string;
  /** Median sold price per m² of residential deals in the last 12 months (MOJ). */
  ppm2: number | null;
  /** Change of that median against the 12 months before. */
  yoy: number | null;
  deals_12m: number;
  value_12m: number;
  deals_total: number;
  last_deal: string | null;
  /** Average annual apartment rent and rent per m² over the latest four quarters (REGA). */
  rent_apt: number | null;
  rent_apt_m2: number | null;
  // Added in the browser from the offers layer.
  offers: number;
  asking_ppm2: number | null;
  /** Median asking price per m² against the sold median. */
  gap: number | null;
};

export type MarketMeta = {
  city_ar: string;
  city_en: string;
  source: string;
  first_deal: string;
  last_deal: string;
  window_start: string;
  deals: number;
  matched_deals: number;
  districts: number;
  districts_with_price: number;
  median_ppm2_12m: number | null;
  deals_12m: number;
  value_12m: number;
  rent_source?: string;
  rent_quarters?: string[];
};

export type RentType = "apartment" | "villa" | "floor" | "studio" | "duplex" | "shop" | "office" | "showroom";
export type DistrictRent = Partial<Record<RentType, { contracts: number; rent: number; rent_m2: number | null }>>;

export type DistrictDeal = {
  date: string;
  price: number;
  area: number;
  ppm2: number | null;
  class: "residential" | "commercial" | "agricultural" | "industrial" | "other";
  type: string | null;
  plan: string | null;
  count: number;
};

export type DistrictMarket = {
  /** [quarter, median price per m², deal count] */
  trend: [string, number, number][];
  recent: DistrictDeal[];
};

export type OfferProps = {
  id: number;
  price: number;
  area: number;
  ppm2: number;
  district_id: number | null;
  label?: string;
};

export type District = Feature<Polygon | MultiPolygon, DistrictProps>;
export type Offer = Feature<Point, OfferProps>;

export type AreaFilter = "all" | "small" | "medium" | "large";

export const AREA_FILTERS: Record<AreaFilter, [number, number]> = {
  all: [0, Infinity],
  small: [0, 1000],
  medium: [1000, 5000],
  large: [5000, Infinity],
};

const MIN_OFFERS_FOR_STATS = 3;

export async function loadSeed() {
  const [districts, offers, meta] = (await Promise.all([
    fetch("/data/riyadh-districts.geojson").then((r) => r.json()),
    fetch("/data/riyadh-offers.geojson").then((r) => r.json()),
    fetch("/data/market-meta.json").then((r) => r.json()),
  ])) as [FeatureCollection<District["geometry"], DistrictProps>, FeatureCollection<Point, OfferProps>, Record<string, MarketMeta>];

  const asking = new Map<number, number[]>();
  for (const o of offers.features) {
    const id = o.properties.district_id;
    if (id !== null) asking.set(id, [...(asking.get(id) ?? []), o.properties.ppm2]);
  }
  for (const d of districts.features) {
    const values = asking.get(d.properties.id) ?? [];
    const askingPpm2 = values.length >= MIN_OFFERS_FOR_STATS ? median(values) : null;
    d.properties.offers = values.length;
    d.properties.asking_ppm2 = askingPpm2 === null ? null : Math.round(askingPpm2);
    d.properties.gap = askingPpm2 !== null && d.properties.ppm2 ? (askingPpm2 - d.properties.ppm2) / d.properties.ppm2 : null;
  }
  return { districts, offers, meta: meta.riyadh };
}

let rents: Promise<Record<string, DistrictRent>> | null = null;

/** Rent by property type for one district. */
export function loadDistrictRent(id: number) {
  rents ??= fetch("/data/riyadh-rent.json").then((r) => r.json());
  return rents.then((r) => r[String(id)] ?? null);
}

const markets = new Map<number, Promise<DistrictMarket>>();

/** Quarterly prices and recent deals for one district, loaded when its sheet opens. */
export function loadDistrictMarket(id: number) {
  if (!markets.has(id)) markets.set(id, fetch(`/data/riyadh-deals/${id}.json`).then((r) => r.json()));
  return markets.get(id)!;
}

let offerTexts: Promise<Record<string, string>> | null = null;

/** Offer descriptions are large, so they load once, on the first offer opened. */
export function loadOfferText(id: number) {
  offerTexts ??= fetch("/data/riyadh-offers-text.json").then((r) => r.json());
  return offerTexts.then((t) => t[String(id)] ?? "");
}

export function bbox(geometry: District["geometry"]): [number, number, number, number] {
  let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
  const rings = geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
  for (const ring of rings) {
    for (const [x, y] of ring) {
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  return [minX, minY, maxX, maxY];
}

export function median(values: number[]) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
