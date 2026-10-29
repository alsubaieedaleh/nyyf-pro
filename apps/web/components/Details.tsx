"use client";

import { useEffect, useState } from "react";
import { loadOfferText, median, type DistrictProps, type Offer, type OfferProps } from "@/lib/data";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";
import type { Locale, Strings } from "@/lib/i18n";
import { priceBadge } from "@/lib/scale";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl bg-canvas px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="tabular mt-0.5 text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}

function CloseButton({ t, onClose }: { t: Strings; onClose: () => void }) {
  return (
    <button onClick={onClose} aria-label={t.close} className="grid h-8 w-8 place-items-center rounded-full bg-canvas text-muted hover:text-ink">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <path d="M6 6l12 12M18 6 6 18" />
      </svg>
    </button>
  );
}

const BADGE_STYLE = {
  below: "bg-[#1f9e8f]/12 text-[#137a6e]",
  fair: "bg-black/5 text-muted",
  above: "bg-[#d9534f]/12 text-[#b23b37]",
};

export function CitySummary({
  t,
  locale,
  stats,
}: {
  t: Strings;
  locale: Locale;
  stats: { districts: number; offers: number; medianPpm2: number; medianAsking: number };
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{locale === "ar" ? "الرياض" : "Riyadh"}</h2>
      <p className="tabular text-sm text-muted">
        {formatNumber(stats.medianPpm2, locale)} {t.perM2} · {formatNumber(stats.districts, locale)} {t.districts} ·{" "}
        {formatNumber(stats.offers, locale)} {t.offers}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Stat label={t.avgPpm2} value={`${formatNumber(stats.medianPpm2, locale)}`} sub={t.perM2} />
        <Stat label={t.askingPpm2} value={`${formatNumber(stats.medianAsking, locale)}`} sub={t.perM2} />
      </div>
      <p className="mt-4 text-xs leading-relaxed text-muted">{t.seedNote}</p>
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
  const asking = median(offers.map((o) => o.properties.ppm2));
  const gap = asking ? (asking - district.ppm2) / district.ppm2 : null;
  const best = [...offers].sort((a, b) => a.properties.ppm2 - b.properties.ppm2).slice(0, 5);

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{locale === "ar" ? district.name_ar : district.name_en}</h2>
          <p className="tabular text-sm text-muted">
            {formatNumber(district.ppm2, locale)} {t.perM2}
            {gap !== null && ` · ${t.gap} ${formatPercent(gap, locale)}`}
          </p>
        </div>
        <CloseButton t={t} onClose={onClose} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label={t.avgPpm2} value={formatNumber(district.ppm2, locale)} />
        <Stat label={t.askingPpm2} value={asking ? formatNumber(asking, locale) : "–"} />
        <Stat label={t.activeOffers} value={formatNumber(offers.length, locale)} />
      </div>

      <h3 className="mt-5 text-sm font-semibold">{t.bestOffers}</h3>
      {best.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t.noData}</p>
      ) : (
        <ul className="mt-2 divide-y divide-black/5">
          {best.map((o) => {
            const badge = priceBadge(o.properties.ppm2, district.ppm2);
            return (
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
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${BADGE_STYLE[badge]}`}>
                    {badge === "below" ? t.belowMarket : badge === "above" ? t.aboveMarket : t.fair}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
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

  const estimate = district ? district.ppm2 * offer.area : null;
  const badge = district ? priceBadge(offer.ppm2, district.ppm2) : null;
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
        <span className={`mt-3 inline-block rounded-full px-2.5 py-1 text-xs font-medium ${BADGE_STYLE[badge]}`}>
          {badge === "below" ? t.belowMarket : badge === "above" ? t.aboveMarket : t.fair}
        </span>
      )}

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label={t.area} value={formatNumber(offer.area, locale)} sub={t.m2} />
        <Stat label={t.perM2} value={formatNumber(offer.ppm2, locale)} />
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
