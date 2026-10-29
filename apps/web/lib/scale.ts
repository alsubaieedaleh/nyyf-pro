// Fixed colour scales: the same colour means the same price everywhere on the map.
// Breaks come from the Riyadh district quintiles (see docs/05-map-experience-spec.md).

export const PRICE_BREAKS = [1500, 2500, 3500, 5000];
export const PRICE_COLORS = ["#1f9e8f", "#7ccbb0", "#efe2a8", "#f2a46f", "#d9534f"];

// Asking price vs. district average: below market is teal, above market is coral.
export const GAP_BREAKS = [-0.2, -0.05, 0.05, 0.2];
export const GAP_COLORS = ["#1f9e8f", "#8fd3c1", "#e4e4de", "#f5b08a", "#d9534f"];

export type Metric = "ppm2" | "asking" | "gap";

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
  if (metric === "ppm2") return stepProperty("ppm2", PRICE_BREAKS, PRICE_COLORS);
  if (metric === "asking") return stepProperty("asking_ppm2", PRICE_BREAKS, PRICE_COLORS);
  return stepProperty("gap", GAP_BREAKS, GAP_COLORS);
}

export type Badge = "below" | "fair" | "above";

/** Compare an asking price per m² with the district average. */
export function priceBadge(askingPpm2: number, marketPpm2: number): Badge {
  const gap = (askingPpm2 - marketPpm2) / marketPpm2;
  if (gap < -0.1) return "below";
  if (gap > 0.1) return "above";
  return "fair";
}
