import type { Locale } from "./i18n";

const tag = (locale: Locale) => (locale === "ar" ? "ar-SA-u-nu-latn" : "en-US");

export function formatNumber(value: number, locale: Locale) {
  return new Intl.NumberFormat(tag(locale), { maximumFractionDigits: 0 }).format(value);
}

/** Short form for map labels and chips: 1.2M, 850K. */
export function formatCompact(value: number, locale: Locale) {
  return new Intl.NumberFormat(tag(locale), { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function formatPercent(value: number, locale: Locale) {
  return new Intl.NumberFormat(tag(locale), { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" }).format(value);
}
