"use client";

import { useMemo, useState } from "react";
import type { AreaFilter, DistrictProps } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import type { Locale, Strings } from "@/lib/i18n";
import type { Metric } from "@/lib/scale";

const normalise = (s: string) =>
  s
    .toLowerCase()
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/^حي\s+/, "")
    .replace(/\s+dist\.?$/, "")
    .trim();

export function SearchBox({
  t,
  locale,
  districts,
  onSelect,
}: {
  t: Strings;
  locale: Locale;
  districts: DistrictProps[];
  onSelect: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const results = useMemo(() => {
    const q = normalise(query);
    if (!q) return [];
    return districts.filter((d) => normalise(d.name_ar).includes(q) || normalise(d.name_en).includes(q)).slice(0, 6);
  }, [query, districts]);

  return (
    <div className="relative">
      <div className="flex h-11 items-center gap-2 rounded-full bg-surface px-4 shadow-md ring-1 ring-black/5 focus-within:ring-2 focus-within:ring-brand/40">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 text-muted">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={t.search}
          className="w-full bg-transparent text-[15px] outline-none placeholder:text-muted"
        />
      </div>
      {open && results.length > 0 && (
        <ul className="absolute inset-x-0 top-12 z-10 overflow-hidden rounded-2xl bg-surface py-1 shadow-xl ring-1 ring-black/5">
          {results.map((d) => (
            <li key={d.id}>
              <button
                className="flex w-full items-center justify-between px-4 py-2.5 text-start hover:bg-canvas"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onSelect(d.id);
                  setQuery("");
                  setOpen(false);
                }}
              >
                <span>{locale === "ar" ? d.name_ar : d.name_en}</span>
                <span className="tabular text-sm text-muted">
                  {formatNumber(d.ppm2, locale)} {t.perM2}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`h-8 shrink-0 rounded-full px-3 text-[13px] font-medium shadow-sm ring-1 transition ${
        active ? "bg-brand text-white ring-brand" : "bg-surface text-ink ring-black/10 hover:bg-canvas"
      }`}
    >
      {children}
    </button>
  );
}

export function Controls({
  t,
  metric,
  onMetric,
  layers,
  onLayers,
  area,
  onArea,
}: {
  t: Strings;
  metric: Metric;
  onMetric: (m: Metric) => void;
  layers: { districts: boolean; offers: boolean };
  onLayers: (l: { districts: boolean; offers: boolean }) => void;
  area: AreaFilter;
  onArea: (a: AreaFilter) => void;
}) {
  const areaLabels: Record<AreaFilter, string> = {
    all: `${t.area}: ${t.all}`,
    small: `< 1,000 ${t.m2}`,
    medium: `1,000–5,000 ${t.m2}`,
    large: `> 5,000 ${t.m2}`,
  };
  return (
    <div className="space-y-2">
      <div className="flex gap-1 rounded-full bg-surface/85 p-1 shadow-sm ring-1 ring-black/5 backdrop-blur">
        {(["ppm2", "asking", "gap"] as Metric[]).map((m) => (
          <button
            key={m}
            onClick={() => onMetric(m)}
            className={`h-8 flex-1 rounded-full px-2 text-[12.5px] font-medium transition ${
              metric === m ? "bg-brand text-white shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {m === "ppm2" ? t.metricPpm2 : m === "asking" ? t.metricAsking : t.metricGap}
          </button>
        ))}
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        <Chip active={layers.districts} onClick={() => onLayers({ ...layers, districts: !layers.districts })}>
          {t.districts}
        </Chip>
        <Chip active={layers.offers} onClick={() => onLayers({ ...layers, offers: !layers.offers })}>
          {t.offers}
        </Chip>
        <span className="mx-1 w-px shrink-0 bg-black/10" />
        {(Object.keys(areaLabels) as AreaFilter[]).map((a) => (
          <Chip key={a} active={area === a} onClick={() => onArea(a)}>
            <span className="tabular">{areaLabels[a]}</span>
          </Chip>
        ))}
      </div>
    </div>
  );
}
