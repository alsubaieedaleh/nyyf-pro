import { formatCompact, formatPercent } from "@/lib/format";
import type { Locale, Strings } from "@/lib/i18n";
import { GAP_BREAKS, GAP_COLORS, PRICE_BREAKS, PRICE_COLORS, type Metric } from "@/lib/scale";

export function Legend({ t, locale, metric }: { t: Strings; locale: Locale; metric: Metric }) {
  const gap = metric === "gap";
  const colors = gap ? GAP_COLORS : PRICE_COLORS;
  const breaks = gap ? GAP_BREAKS : PRICE_BREAKS;
  const label = (v: number) => (gap ? formatPercent(v, locale) : formatCompact(v, locale));
  const title = metric === "ppm2" ? t.metricPpm2 : metric === "asking" ? t.metricAsking : t.metricGap;

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-xs text-muted">
        <span className="font-medium text-ink">{title}</span>
        {!gap && <span>{t.perM2}</span>}
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
