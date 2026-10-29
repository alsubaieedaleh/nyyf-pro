import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";
export type DistrictProps = {
  id: number;
  name_ar: string;
  name_en: string;
  ppm2: number;
  offers: number;
  asking_ppm2: number | null;
  gap: number | null;
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

export async function loadSeed() {
  const [districts, offers] = await Promise.all([
    fetch("/data/riyadh-districts.geojson").then((r) => r.json()),
    fetch("/data/riyadh-offers.geojson").then((r) => r.json()),
  ]);
  return {
    districts: districts as FeatureCollection<District["geometry"], DistrictProps>,
    offers: offers as FeatureCollection<Point, OfferProps>,
  };
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
