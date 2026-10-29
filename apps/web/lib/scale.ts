// Fixed colour scales: the same colour means the same price everywhere on the map.
// Price breaks are the quintiles of Riyadh's MOJ district medians, 12 months to March 2026.

export const PRICE_BREAKS = [2000, 3000, 4500, 7000];
export const PRICE_COLORS = ["#1f9e8f", "#7ccbb0", "#efe2a8", "#f2a46f", "#d9534f"];

// Asking price vs. district average: below market is teal, above market is coral.
export const GAP_BREAKS = [-0.2, -0.05, 0.05, 0.2];
export const GAP_COLORS = ["#1f9e8f", "#8fd3c1", "#e4e4de", "#f5b08a", "#d9534f"];

// Year-on-year change of the sold median: falling is teal, rising is coral.
export const YOY_BREAKS = [-0.15, -0.05, 0.05, 0.15];

// Deals in the last 12 months.
export const VOLUME_BREAKS = [10, 40, 100, 250];
export const VOLUME_COLORS = ["#e3f1ee", "#b4dcd3", "#7cc4b6", "#3fa293", "#157d79"];

// Average annual apartment rent per m² (REGA rental indicators).
export const RENT_BREAKS = [175, 210, 260, 340];

export type Metric = "ppm2" | "yoy" | "volume" | "rent" | "asking" | "gap";

export const METRIC_SCALES: Record<Metric, { breaks: number[]; colors: string[]; percent?: boolean }> = {
  ppm2: { breaks: PRICE_BREAKS, colors: PRICE_COLORS },
  yoy: { breaks: YOY_BREAKS, colors: GAP_COLORS, percent: true },
  volume: { breaks: VOLUME_BREAKS, colors: VOLUME_COLORS },
  rent: { breaks: RENT_BREAKS, colors: PRICE_COLORS },
  asking: { breaks: PRICE_BREAKS, colors: PRICE_COLORS },
  gap: { breaks: GAP_BREAKS, colors: GAP_COLORS, percent: true },
};

const METRIC_PROPERTY: Record<Metric, string> = {
  ppm2: "ppm2",
  yoy: "yoy",
  volume: "deals_12m",
  rent: "rent_apt_m2",
  asking: "asking_ppm2",
  gap: "gap",
};

/** MapLibre `step` expression over a numeric input. */
export function stepExpression(input: unknown, breaks: number[], colors: string[]) {
  const step: unknown[] = ["step", input, colors[0]];
  breaks.forEach((b, i) => step.push(b, colors[i + 1]));
  return step;
}

/** Step colours over a feature property that may be missing; missing values are grey. */
function stepProperty(property: string, breaks: number[], colors: string[], fallback = "#d6d6d0") {
  return ["case", ["==", ["get", property], null], fallback, stepExpression(["to-number", ["get", property]], breaks, colors)];
}

export function districtFill(metric: Metric) {
  const { breaks, colors } = METRIC_SCALES[metric];
  return stepProperty(METRIC_PROPERTY[metric], breaks, colors);
}

export type Badge = "below" | "fair" | "above";

/** Compare an asking price per m² with the district's sold median. */
export function priceBadge(askingPpm2: number, marketPpm2: number): Badge {
  const gap = (askingPpm2 - marketPpm2) / marketPpm2;
  if (gap < -0.1) return "below";
  if (gap > 0.1) return "above";
  return "fair";
}
