"use client";

import { useEffect, useState } from "react";
import {
  loadDistrictMarket,
  loadDistrictRent,
  type DistrictRent,
  type RentType,
  loadOfferText,
  median,
  type DistrictMarket,
  type DistrictProps,
  type MarketMeta,
  type Offer,
  type OfferProps,
} from "@/lib/data";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";
import type { Locale, Strings } from "@/lib/i18n";
import { priceBadge, type Badge } from "@/lib/scale";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  const toneClass = tone === "up" ? "text-[#b23b37]" : tone === "down" ? "text-[#137a6e]" : "";
  return (
    <div className="rounded-2xl bg-canvas px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`tabular mt-0.5 text-lg font-semibold ${toneClass}`}>{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}

function CloseButton({ t, onClose }: { t: Strings; onClose: () => void }) {
  return (
    <button onClick={onClose} aria-label={t.close} className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-canvas text-muted hover:text-ink">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <path d="M6 6l12 12M18 6 6 18" />
      </svg>
    </button>
  );
}

const BADGE_STYLE: Record<Badge, string> = {
  below: "bg-[#1f9e8f]/12 text-[#137a6e]",
  fair: "bg-black/5 text-muted",
  above: "bg-[#d9534f]/12 text-[#b23b37]",
};

function BadgeChip({ t, badge }: { t: Strings; badge: Badge }) {
  return (
    <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${BADGE_STYLE[badge]}`}>
      {badge === "below" ? t.belowMarket : badge === "above" ? t.aboveMarket : t.fair}
    </span>
  );
}

const RENT_ORDER: RentType[] = ["apartment", "villa", "floor", "duplex", "studio", "shop", "office", "showroom"];

const tone = (v: number | null) => (v === null ? undefined : v > 0.02 ? "up" : v < -0.02 ? "down" : undefined);

function formatMonth(iso: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { month: "long", year: "numeric" }).format(new Date(iso));
}

function formatDay(iso: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}

export function CitySummary({
  t,
  locale,
  meta,
}: {
  t: Strings;
  locale: Locale;
  meta: MarketMeta;
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{locale === "ar" ? meta.city_ar : meta.city_en}</h2>
      <p className="tabular text-sm text-muted">
        {t.dataThrough} {formatMonth(meta.last_deal, locale)} · {formatNumber(meta.districts, locale)} {t.districts}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Stat label={t.soldPpm2} value={meta.median_ppm2_12m ? formatNumber(meta.median_ppm2_12m, locale) : "–"} sub={t.soldNote} />
        <Stat label={t.deals12m} value={formatNumber(meta.deals_12m, locale)} sub={`${formatCompact(meta.value_12m, locale)} ${t.sar}`} />
      </div>
      <p className="mt-4 text-xs leading-relaxed text-muted">{t.source}</p>
    </div>
  );
}

/** Quarterly median price per m² as a small line, newest on the reading end. */
function Sparkline({ points, locale }: { points: [string, number, number][]; locale: Locale }) {
  const data = points.slice(-12);
  if (data.length < 2) return null;
  const values = data.map((p) => p[1]);
  const [min, max] = [Math.min(...values), Math.max(...values)];
  const w = 320;
  const h = 72;
  const x = (i: number) => (i / (data.length - 1)) * (w - 8) + 4;
  const y = (v: number) => h - 8 - ((v - min) / (max - min || 1)) * (h - 20);
  const d = data.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const last = data[data.length - 1];
  return (
    <div dir="ltr">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-20 w-full" style={{ transform: locale === "ar" ? "scaleX(-1)" : undefined }}>
        <path d={`${d} L${x(data.length - 1)},${h} L${x(0)},${h} Z`} fill="#157d79" opacity="0.08" />
        <path d={d} fill="none" stroke="#157d79" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(data.length - 1)} cy={y(last[1])} r="3.5" fill="#157d79" />
      </svg>
      <div className={`tabular flex justify-between text-[11px] text-muted ${locale === "ar" ? "flex-row-reverse" : ""}`}>
        <span>{data[0][0]}</span>
        <span>{last[0]}</span>
      </div>
    </div>
  );
}

export function DistrictDetails({
  t,
  locale,
  district,
  offers,
  onOffer,
  onClose,
}: {
  t: Strings;
  locale: Locale;
  district: DistrictProps;
  offers: Offer[];
  onOffer: (o: Offer) => void;
  onClose: () => void;
}) {
  const [market, setMarket] = useState<DistrictMarket | null>(null);
  const [rent, setRent] = useState<DistrictRent | null>(null);
  useEffect(() => {
    let live = true;
    setMarket(null);
    setRent(null);
    loadDistrictMarket(district.id).then((m) => live && setMarket(m));
    loadDistrictRent(district.id).then((r) => live && setRent(r));
    return () => {
      live = false;
    };
  }, [district.id]);

  const asking = median(offers.map((o) => o.properties.ppm2));
  const gap = asking && district.ppm2 ? (asking - district.ppm2) / district.ppm2 : null;
  const best = district.ppm2 ? [...offers].sort((a, b) => a.properties.ppm2 - b.properties.ppm2).slice(0, 5) : [];

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{locale === "ar" ? district.name_ar : district.name_en}</h2>
          <p className="tabular text-sm text-muted">
            {district.ppm2 ? `${formatNumber(district.ppm2, locale)} ${t.perM2}` : t.noSales}
            {district.yoy !== null && ` · ${t.yoy} ${formatPercent(district.yoy, locale)}`}
          </p>
        </div>
        <CloseButton t={t} onClose={onClose} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Stat label={t.soldPpm2} value={district.ppm2 ? formatNumber(district.ppm2, locale) : "–"} sub={t.soldNote} />
        <Stat
          label={t.yoy}
          value={district.yoy !== null ? formatPercent(district.yoy, locale) : "–"}
          tone={tone(district.yoy)}
        />
        <Stat
          label={t.deals12m}
          value={formatNumber(district.deals_12m, locale)}
          sub={district.value_12m ? `${formatCompact(district.value_12m, locale)} ${t.sar}` : undefined}
        />
        <Stat
          label={t.askingPpm2}
          value={asking ? formatNumber(asking, locale) : "–"}
          sub={gap !== null ? `${t.gap} ${formatPercent(gap, locale)}` : `${formatNumber(offers.length, locale)} ${t.activeOffers}`}
        />
      </div>

      {market && market.trend.length > 1 && (
        <section className="mt-5">
          <h3 className="mb-1 text-sm font-semibold">{t.trend}</h3>
          <Sparkline points={market.trend} locale={locale} />
        </section>
      )}

      {rent && (
        <section className="mt-5">
          <h3 className="text-sm font-semibold">{t.rentTitle}</h3>
          <p className="text-xs text-muted">{t.rentNote}</p>
          <ul className="mt-1 divide-y divide-black/5">
            {RENT_ORDER.filter((k) => rent[k]).map((k) => {
              const r = rent[k]!;
              return (
                <li key={k} className="flex items-center justify-between gap-3 py-2">
                  <span className="text-sm">{t[k]}</span>
                  <span className="tabular text-end text-sm">
                    <span className="font-medium">
                      {formatNumber(r.rent, locale)} {t.perYear}
                    </span>
                    <span className="block text-xs text-muted">
                      {r.rent_m2 ? `${formatNumber(r.rent_m2, locale)} ${t.perM2} · ` : ""}
                      {formatNumber(r.contracts, locale)} {t.contracts}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {market && market.recent.length > 0 && (
        <section className="mt-5">
          <h3 className="text-sm font-semibold">{t.recentDeals}</h3>
          <ul className="mt-1 divide-y divide-black/5">
            {market.recent.slice(0, 8).map((d, i) => (
              <li key={i} className="flex items-center justify-between gap-3 py-2.5">
                <span>
                  <span className="tabular block font-medium">
                    {formatCompact(d.price, locale)} {t.sar}
                    {d.count > 1 && <span className="text-xs font-normal text-muted"> · {d.count} {t.multi}</span>}
                  </span>
                  <span className="tabular text-xs text-muted">
                    {formatNumber(d.area, locale)} {t.m2}
                    {d.ppm2 && ` · ${formatNumber(d.ppm2, locale)} ${t.perM2}`}
                    {d.plan && ` · ${t.plan} ${d.plan}`}
                  </span>
                </span>
                <span className="shrink-0 text-end text-xs text-muted">
                  <span className="block">{formatDay(d.date, locale)}</span>
                  <span>{d.type ?? t[d.class]}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {best.length > 0 && (
        <section className="mt-5">
          <h3 className="text-sm font-semibold">{t.bestOffers}</h3>
          <ul className="mt-1 divide-y divide-black/5">
            {best.map((o) => (
              <li key={o.properties.id}>
                <button onClick={() => onOffer(o)} className="flex w-full items-center justify-between gap-3 py-2.5 text-start">
                  <span>
                    <span className="tabular block font-medium">
                      {formatCompact(o.properties.price, locale)} {t.sar}
                    </span>
                    <span className="tabular text-xs text-muted">
                      {formatNumber(o.properties.area, locale)} {t.m2} · {formatNumber(o.properties.ppm2, locale)} {t.perM2}
                    </span>
                  </span>
                  <BadgeChip t={t} badge={priceBadge(o.properties.ppm2, district.ppm2!)} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function OfferDetails({
  t,
  locale,
  offer,
  district,
  onDistrict,
  onClose,
}: {
  t: Strings;
  locale: Locale;
  offer: OfferProps;
  district?: DistrictProps;
  onDistrict?: () => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  useEffect(() => {
    let live = true;
    setText("");
    loadOfferText(offer.id).then((s) => live && setText(s));
    return () => {
      live = false;
    };
  }, [offer.id]);

  const marketPpm2 = district?.ppm2 ?? null;
  const estimate = marketPpm2 ? marketPpm2 * offer.area : null;
  const badge = marketPpm2 ? priceBadge(offer.ppm2, marketPpm2) : null;
  const districtName = district ? (locale === "ar" ? district.name_ar : district.name_en) : t.outsideDistricts;
  const share = `${districtName}\n${t.price}: ${formatNumber(offer.price, locale)} ${t.sar}\n${t.area}: ${formatNumber(offer.area, locale)} ${t.m2}\n${formatNumber(offer.ppm2, locale)} ${t.perM2}`;

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="tabular text-2xl font-semibold">
            {formatNumber(offer.price, locale)} <span className="text-base font-medium text-muted">{t.sar}</span>
          </div>
          <button onClick={onDistrict} disabled={!onDistrict} className="text-sm text-brand disabled:text-muted">
            {districtName}
          </button>
        </div>
        <CloseButton t={t} onClose={onClose} />
      </div>

      {badge && (
        <div className="mt-3">
          <BadgeChip t={t} badge={badge} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label={t.area} value={formatNumber(offer.area, locale)} sub={t.m2} />
        <Stat label={t.perM2} value={formatNumber(offer.ppm2, locale)} sub={marketPpm2 ? `${t.soldPpm2}: ${formatNumber(marketPpm2, locale)}` : undefined} />
        <Stat label={t.estimate} value={estimate ? formatCompact(estimate, locale) : "–"} sub={t.sar} />
      </div>

      {text && <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-ink/80" dir="rtl">{text}</p>}

      <a
        href={`https://wa.me/?text=${encodeURIComponent(share)}`}
        target="_blank"
        rel="noreferrer"
        className="mt-5 flex h-11 items-center justify-center rounded-full bg-brand font-medium text-white transition hover:bg-brand/90"
      >
        {t.share}
      </a>
    </div>
  );
}
