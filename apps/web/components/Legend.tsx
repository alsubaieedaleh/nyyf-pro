import { formatCompact, formatPercent } from "@/lib/format";
import type { Locale, Strings } from "@/lib/i18n";
import { METRIC_SCALES, type Metric } from "@/lib/scale";

export function metricLabel(t: Strings, metric: Metric) {
  return { ppm2: t.metricPpm2, yoy: t.metricYoy, volume: t.metricVolume, rent: t.metricRent, asking: t.metricAsking, gap: t.metricGap }[metric];
}

export function Legend({ t, locale, metric }: { t: Strings; locale: Locale; metric: Metric }) {
  const { breaks, colors, percent } = METRIC_SCALES[metric];
  const label = (v: number) => (percent ? formatPercent(v, locale) : formatCompact(v, locale));
  const title = metricLabel(t, metric);
  const unit = metric === "ppm2" || metric === "asking" ? t.perM2 : metric === "rent" ? t.perM2Year : null;

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-xs text-muted">
        <span className="font-medium text-ink">{title}</span>
        {unit && <span>{unit}</span>}
      </div>
      <div className="flex h-2 overflow-hidden rounded-full">
        {colors.map((c) => (
          <span key={c} className="flex-1 transition-colors duration-300" style={{ background: c }} />
        ))}
      </div>
      <div className="tabular mt-1 flex text-[11px] text-muted">
        <span className="flex-1" />
        {breaks.map((b) => (
          <span key={b} className="flex-1 -translate-x-1/2 text-center rtl:translate-x-1/2" style={{ flexBasis: 0 }}>
            {label(b)}
          </span>
        ))}
      </div>
    </div>
  );
}
