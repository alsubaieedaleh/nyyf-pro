import type { FeatureCollection } from "geojson";
import type { Map as MlMap, ExpressionSpecification } from "maplibre-gl";
import { PRICE_BREAKS, PRICE_COLORS, districtFill, stepExpression, type Metric } from "./scale";

export const DISTRICT_LAYERS = ["district-fill", "district-line", "district-selected", "district-labels"];
export const PLAN_LAYERS = ["plan-points", "plan-labels"];
export const OFFER_LAYERS = ["offer-clusters", "offer-cluster-count", "offer-points", "offer-labels", "offer-selected"];

const expr = (e: unknown) => e as ExpressionSpecification;

/** First symbol layer of the basemap, so district fills sit under its labels. */
function firstSymbolLayer(map: MlMap) {
  return map.getStyle().layers.find((l) => l.type === "symbol")?.id;
}

export function addLayers(
  map: MlMap,
  data: { districts: FeatureCollection; offers: FeatureCollection; plans: FeatureCollection },
  opts: { metric: Metric; nameField: string; hasGlyphs: boolean },
) {
  map.addSource("districts", { type: "geojson", data: data.districts, promoteId: "id" });
  map.addSource("offers", {
    type: "geojson",
    data: data.offers,
    cluster: true,
    clusterRadius: 60,
    clusterMaxZoom: 14,
    clusterProperties: { ppm2_sum: ["+", ["get", "ppm2"]] },
  });

  map.addSource("plans", { type: "geojson", data: data.plans, promoteId: "id" });

  const before = firstSymbolLayer(map);

  map.addLayer(
    {
      id: "district-fill",
      type: "fill",
      source: "districts",
      paint: {
        "fill-color": expr(districtFill(opts.metric)),
        "fill-color-transition": { duration: 300 },
        "fill-opacity": expr([
          "case",
          ["boolean", ["feature-state", "selected"], false], 0.8,
          ["boolean", ["feature-state", "hover"], false], 0.75,
          0.55,
        ]),
        "fill-opacity-transition": { duration: 200 },
      },
    },
    before,
  );
  map.addLayer(
    {
      id: "district-line",
      type: "line",
      source: "districts",
      paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 14, 1.5], "line-opacity": 0.9 },
    },
    before,
  );
  map.addLayer({
    id: "district-selected",
    type: "line",
    source: "districts",
    filter: ["==", ["get", "id"], -1],
    paint: { "line-color": "#0f5c59", "line-width": 2.5 },
  });

  // Plans: larger dots in the estimated price colour with a dark ring, so they read apart from offers.
  map.addLayer({
    id: "plan-points",
    type: "circle",
    source: "plans",
    minzoom: 10.5,
    paint: {
      "circle-color": expr(["case", ["==", ["get", "ppm2_est"], null], "#c9cfcf", stepExpression(["get", "ppm2_est"], PRICE_BREAKS, PRICE_COLORS)]),
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 8, 15, 14],
      "circle-stroke-width": 3,
      "circle-stroke-color": "#0f5c59",
    },
  });

  const avgColor = expr(["/", ["get", "ppm2_sum"], ["get", "point_count"]]);
  map.addLayer({
    id: "offer-clusters",
    type: "circle",
    source: "offers",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": expr(stepExpression(avgColor, PRICE_BREAKS, PRICE_COLORS)),
      "circle-radius": ["step", ["get", "point_count"], 14, 50, 18, 250, 24, 1000, 30],
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
      "circle-opacity": 0.95,
    },
  });
  map.addLayer({
    id: "offer-points",
    type: "circle",
    source: "offers",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": expr(stepExpression(["get", "ppm2"], PRICE_BREAKS, PRICE_COLORS)),
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 16, 8],
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#ffffff",
    },
  });
  map.addLayer({
    id: "offer-selected",
    type: "circle",
    source: "offers",
    filter: ["==", ["get", "id"], -1],
    paint: { "circle-radius": 12, "circle-color": "rgba(0,0,0,0)", "circle-stroke-width": 3, "circle-stroke-color": "#0f5c59" },
  });

  // Plans sit above the offers: there are far fewer of them and they carry the plan price.
  map.moveLayer("plan-points");

  if (!opts.hasGlyphs) return;

  map.addLayer({
    id: "district-labels",
    type: "symbol",
    source: "districts",
    minzoom: 11,
    layout: { "text-field": ["get", opts.nameField], "text-size": 12, "text-max-width": 8 },
    paint: { "text-color": "#1d2626", "text-halo-color": "rgba(255,255,255,0.85)", "text-halo-width": 1.2 },
  });
  map.addLayer({
    id: "plan-labels",
    type: "symbol",
    source: "plans",
    minzoom: 12.5,
    layout: { "text-field": ["get", "label"], "text-size": 11, "text-offset": [0, 1.3], "text-anchor": "top", "text-max-width": 10 },
    paint: { "text-color": "#0f5c59", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  });
  map.addLayer({
    id: "offer-cluster-count",
    type: "symbol",
    source: "offers",
    filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12, "text-allow-overlap": true },
    paint: { "text-color": "#1d2626" },
  });
  map.addLayer({
    id: "offer-labels",
    type: "symbol",
    source: "offers",
    filter: ["!", ["has", "point_count"]],
    minzoom: 14.5,
    layout: { "text-field": ["get", "label"], "text-size": 11, "text-offset": [0, -1.4] },
    paint: { "text-color": "#1d2626", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  });
}

export function setVisible(map: MlMap, layers: string[], visible: boolean) {
  for (const id of layers) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  }
}
