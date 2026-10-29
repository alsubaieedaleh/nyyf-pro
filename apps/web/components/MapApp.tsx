"use client";

import type { Point } from "geojson";
import { Map as MlMap, setWorkerUrl, type GeoJSONSource, type MapGeoJSONFeature, type MapMouseEvent, type StyleSpecification } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AREA_FILTERS, bbox, loadSeed, type AreaFilter, type District, type DistrictProps, type OfferProps } from "@/lib/data";
import { formatCompact } from "@/lib/format";
import { strings, type Locale } from "@/lib/i18n";
import { DISTRICT_LAYERS, OFFER_LAYERS, addLayers, setVisible } from "@/lib/layers";
import { districtFill, type Metric } from "@/lib/scale";
import { BottomSheet } from "./BottomSheet";
import { CitySummary, DistrictDetails, OfferDetails } from "./Details";
import { Legend } from "./Legend";
import { Controls, SearchBox } from "./Controls";

const RIYADH: [number, number] = [46.70, 24.72];
const DEFAULT_STYLE = process.env.NEXT_PUBLIC_MAP_STYLE_URL || "https://tiles.openfreemap.org/styles/positron";
const DESKTOP_PANEL = 416;

setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

// Used when the basemap cannot be reached (offline, blocked network): data still renders.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#eeede8" } }],
};

export type Selection =
  | { kind: "district"; id: number }
  | { kind: "offer"; offer: OfferProps; lngLat: [number, number] }
  | null;

type Seed = Awaited<ReturnType<typeof loadSeed>>;

async function resolveStyle(): Promise<StyleSpecification | string> {
  try {
    const res = await fetch(DEFAULT_STYLE);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as StyleSpecification;
  } catch {
    return FALLBACK_STYLE;
  }
}

function useIsDesktop() {
  const [desktop, setDesktop] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = () => setDesktop(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return desktop;
}

export default function MapApp() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [seed, setSeed] = useState<Seed | null>(null);
  const [locale, setLocale] = useState<Locale>("ar");
  const [metric, setMetric] = useState<Metric>("ppm2");
  const [layers, setLayers] = useState({ districts: true, offers: true });
  const [area, setArea] = useState<AreaFilter>("all");
  const [selection, setSelection] = useState<Selection>(null);
  const [sheetHeight, setSheetHeight] = useState(0);
  const isDesktop = useIsDesktop();
  const t = strings[locale];

  const districtsById = useMemo(() => {
    const m = new Map<number, District>();
    seed?.districts.features.forEach((f) => m.set(f.properties.id, f as District));
    return m;
  }, [seed]);

  const filteredOffers = useMemo(() => {
    if (!seed) return null;
    const [min, max] = AREA_FILTERS[area];
    return {
      ...seed.offers,
      features: seed.offers.features
        .filter((f) => f.properties.area >= min && f.properties.area < max)
        .map((f) => ({ ...f, properties: { ...f.properties, label: formatCompact(f.properties.price, locale) } })),
    };
  }, [seed, area, locale]);

  // Create the map once.
  useEffect(() => {
    let cancelled = false;
    let map: MlMap | null = null;
    (async () => {
      const [style, data] = await Promise.all([resolveStyle(), loadSeed()]);
      if (cancelled || !container.current) return;
      // MapLibre 6 shapes Arabic text natively, so no RTL plugin is needed.
      const instance = new MlMap({
        container: container.current,
        style,
        center: RIYADH,
        zoom: 10.2,
        minZoom: 8,
        maxZoom: 18,
        attributionControl: { compact: true },
        fadeDuration: 200,
      });
      instance.touchZoomRotate.disableRotation();
      instance.dragRotate.disable();
      map = instance;
      mapRef.current = instance;
      instance.on("load", () => {
        const hasGlyphs = typeof style !== "string" && Boolean(style.glyphs);
        addLayers(instance, data, { metric: "ppm2", nameField: "name_ar", hasGlyphs });
        setSeed(data);
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  // Keep page direction and language in sync with the locale.
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    const map = mapRef.current;
    if (ready && map?.getLayer("district-labels")) {
      map.setLayoutProperty("district-labels", "text-field", ["get", locale === "ar" ? "name_ar" : "name_en"]);
    }
  }, [locale, ready]);

  useEffect(() => {
    if (ready) mapRef.current?.setPaintProperty("district-fill", "fill-color", districtFill(metric) as never);
  }, [metric, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setVisible(map, DISTRICT_LAYERS, layers.districts);
    setVisible(map, OFFER_LAYERS, layers.offers);
  }, [layers, ready]);

  useEffect(() => {
    const source = mapRef.current?.getSource("offers") as GeoJSONSource | undefined;
    if (ready && source && filteredOffers) source.setData(filteredOffers);
  }, [filteredOffers, ready]);

  // Keep the selection centred in the part of the map the panel does not cover.
  const padding = useMemo(
    () =>
      isDesktop
        ? { top: 24, bottom: 24, left: locale === "en" ? DESKTOP_PANEL + 24 : 24, right: locale === "ar" ? DESKTOP_PANEL + 24 : 24 }
        : { top: 120, bottom: sheetHeight + 16, left: 16, right: 16 },
    [isDesktop, locale, sheetHeight],
  );

  useEffect(() => {
    mapRef.current?.easeTo({ padding, duration: 300 });
  }, [padding]);

  // Reflect the selection on the map.
  const selectedDistrict = useRef<number | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const districtId = selection?.kind === "district" ? selection.id : null;
    if (selectedDistrict.current !== null) {
      map.setFeatureState({ source: "districts", id: selectedDistrict.current }, { selected: false });
    }
    if (districtId !== null) map.setFeatureState({ source: "districts", id: districtId }, { selected: true });
    selectedDistrict.current = districtId;
    map.setFilter("district-selected", ["==", ["get", "id"], districtId ?? -1]);
    map.setFilter("offer-selected", ["==", ["get", "id"], selection?.kind === "offer" ? selection.offer.id : -1]);
  }, [selection, ready]);

  const selectDistrict = useCallback(
    (id: number) => {
      const district = districtsById.get(id);
      if (!district) return;
      setSelection({ kind: "district", id });
      const [minX, minY, maxX, maxY] = bbox(district.geometry);
      mapRef.current?.fitBounds([minX, minY, maxX, maxY], { padding, duration: 700, maxZoom: 14.5 });
    },
    [districtsById, padding],
  );

  const selectOffer = useCallback(
    (offer: OfferProps, lngLat: [number, number], fly: boolean) => {
      setSelection({ kind: "offer", offer, lngLat });
      const map = mapRef.current;
      if (map && fly) map.flyTo({ center: lngLat, zoom: Math.max(map.getZoom(), 15), padding, duration: 800 });
      else map?.easeTo({ center: lngLat, padding, duration: 400 });
    },
    [padding],
  );

  // Map interactions: hover, click on clusters, offers, and districts.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    let hovered: number | null = null;

    const onMove = (e: MapMouseEvent) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: ["offer-clusters", "offer-points", "district-fill"].filter((l) => map.getLayer(l)) });
      map.getCanvas().style.cursor = hits.length ? "pointer" : "";
      const district = hits.find((h) => h.layer.id === "district-fill");
      const id = district ? (district.properties.id as number) : null;
      if (id === hovered) return;
      if (hovered !== null) map.setFeatureState({ source: "districts", id: hovered }, { hover: false });
      if (id !== null) map.setFeatureState({ source: "districts", id }, { hover: true });
      hovered = id;
    };

    const onClick = async (e: MapMouseEvent) => {
      const visible = ["offer-clusters", "offer-points", "district-fill"].filter(
        (l) => map.getLayer(l) && map.getLayoutProperty(l, "visibility") !== "none",
      );
      const hits: MapGeoJSONFeature[] = map.queryRenderedFeatures(e.point, { layers: visible });
      const cluster = hits.find((h) => h.layer.id === "offer-clusters");
      if (cluster) {
        const source = map.getSource("offers") as GeoJSONSource;
        const zoom = await source.getClusterExpansionZoom(cluster.properties.cluster_id as number);
        map.easeTo({ center: (cluster.geometry as Point).coordinates as [number, number], zoom, duration: 450 });
        return;
      }
      const point = hits.find((h) => h.layer.id === "offer-points");
      if (point) {
        selectOffer(point.properties as OfferProps, (point.geometry as Point).coordinates as [number, number], false);
        return;
      }
      const district = hits.find((h) => h.layer.id === "district-fill");
      if (district) selectDistrict(district.properties.id as number);
      else setSelection(null);
    };

    map.on("mousemove", onMove);
    map.on("click", onClick);
    return () => {
      map.off("mousemove", onMove);
      map.off("click", onClick);
    };
  }, [ready, selectDistrict, selectOffer]);

  const districtOffers = useMemo(() => {
    if (selection?.kind !== "district" || !filteredOffers) return [];
    return filteredOffers.features.filter((f) => f.properties.district_id === selection.id);
  }, [selection, filteredOffers]);


  const districtList = useMemo(() => (seed ? seed.districts.features.map((f) => f.properties as DistrictProps) : []), [seed]);

  let content: React.ReactNode = seed && <CitySummary t={t} locale={locale} meta={seed.meta} />;
  if (selection?.kind === "district") {
    const d = districtsById.get(selection.id);
    if (d)
      content = (
        <DistrictDetails
          t={t}
          locale={locale}
          district={d.properties}
          offers={districtOffers}
          onOffer={(o) => selectOffer(o.properties, o.geometry.coordinates as [number, number], true)}
          onClose={() => setSelection(null)}
        />
      );
  } else if (selection?.kind === "offer") {
    const d = selection.offer.district_id ? districtsById.get(selection.offer.district_id)?.properties : undefined;
    content = (
      <OfferDetails
        t={t}
        locale={locale}
        offer={selection.offer}
        district={d}
        onDistrict={d ? () => selectDistrict(d.id) : undefined}
        onClose={() => setSelection(null)}
      />
    );
  }

  const search = <SearchBox t={t} locale={locale} districts={districtList} onSelect={selectDistrict} />;
  const controls = (
    <Controls
      t={t}
      metric={metric}
      onMetric={setMetric}
      layers={layers}
      onLayers={setLayers}
      area={area}
      onArea={setArea}
    />
  );

  return (
    <main className="relative h-dvh w-full overflow-hidden">
      {/* MapLibre sets position: relative on its container, so it fills a positioned wrapper. */}
      <div className="absolute inset-0">
        <div ref={container} className="h-full w-full" />
      </div>

      {!ready && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="h-1 w-40 overflow-hidden rounded-full bg-black/5">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-brand" />
          </div>
        </div>
      )}

      {isDesktop ? (
        <aside
          className="absolute inset-y-4 start-4 flex flex-col overflow-hidden rounded-2xl bg-surface/95 shadow-xl ring-1 ring-black/5 backdrop-blur"
          style={{ width: DESKTOP_PANEL }}
        >
          <header className="flex items-center justify-between gap-3 px-5 pt-5">
            <Brand t={t} />
            <LangToggle t={t} onToggle={() => setLocale(locale === "ar" ? "en" : "ar")} />
          </header>
          <div className="px-5 pt-4">{search}</div>
          <div className="px-5 pt-3">{controls}</div>
          <div className="mt-4 flex-1 overflow-y-auto border-t border-black/5 px-5 py-4">{content}</div>
          <div className="border-t border-black/5 px-5 py-3">
            <Legend t={t} locale={locale} metric={metric} />
          </div>
        </aside>
      ) : (
        <>
          <div className="absolute inset-x-0 top-0 space-y-2 p-3">
            <div className="flex items-center gap-2">
              <div className="flex-1">{search}</div>
              <LangToggle t={t} onToggle={() => setLocale(locale === "ar" ? "en" : "ar")} />
            </div>
            {controls}
          </div>
          <BottomSheet onHeight={setSheetHeight} expanded={selection !== null}>
            <div className="pb-3">
              <Legend t={t} locale={locale} metric={metric} />
            </div>
            {content}
          </BottomSheet>
        </>
      )}
    </main>
  );
}

function Brand({ t }: { t: { brand: string } }) {
  return (
    <div className="flex items-center gap-2">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-sm font-bold text-white">N</span>
      <span className="text-lg font-semibold tracking-tight">{t.brand}</span>
    </div>
  );
}

function LangToggle({ t, onToggle }: { t: { lang: string }; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-sm font-semibold shadow-md ring-1 ring-black/5 transition hover:bg-canvas"
    >
      {t.lang}
    </button>
  );
}
