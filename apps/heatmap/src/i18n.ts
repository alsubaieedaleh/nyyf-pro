export type Locale = "ar" | "en";

export const STRINGS = {
  ar: {
    brand: "نيّف",
    search: "ابحث عن حي",
    close: "إغلاق",
    lang: "EN",
    ppm2: "سعر المتر",
    sar_m2: "ر.س/م²",
    range: "النطاق المعتاد",
    conf: { high: "ثقة عالية", medium: "ثقة متوسطة", low: "ثقة منخفضة", none: "لا يوجد سعر" },
    noPrice: "لا توجد صفقات كافية في هذا الحي لتقدير سعر.",
    yoy: "التغير السنوي",
    deals12: "صفقات آخر 12 شهرًا",
    lastDeal: "آخر صفقة",
    rent: "إيجار الشقق السنوي",
    rentUnit: "ر.س/م² سنويًا",
    share: "مشاركة",
    copied: "تم نسخ الرابط",
    legendTitle: "سعر المتر · ",
    legendNone: "لا يوجد سعر",
    legendConf: "اللون الباهت = ثقة أقل",
    asOf: "البيانات حتى",
    method:
      "السعر هو وسيط سعر المتر لكل الصفقات السكنية (أراضٍ وشقق وفلل) المسجلة في الحي خلال آخر 12 شهرًا، أو 24 شهرًا إذا قلّت الصفقات. النطاق المعتاد هو الربع الأدنى إلى الربع الأعلى. الثقة تعتمد على عدد الصفقات وتقارب الأسعار وحداثتها.",
    disclaimer:
      "تقديرات استرشادية من بيانات حكومية مفتوحة، وليست تقييمًا عقاريًا معتمدًا ولا بيانات رسمية. تحقق دائمًا قبل اتخاذ أي قرار.",
    aboutTitle: "عن الخريطة",
    aboutLead: "خريطة مجانية لسعر المتر في أحياء ست مدن سعودية، تُحدَّث تلقائيًا من البيانات المفتوحة.",
    sources: "المصادر",
    licenseNote: "صفقات وزارة العدل ومؤشرات الإيجار من الهيئة العامة للعقار منشورة برخصة البيانات المفتوحة للمملكة. الخريطة الأساسية © OpenStreetMap و OpenFreeMap.",
    priced: (p: number, t: number, h: number) => `${p} حيًا مسعّرًا من ${t}، منها ${h} بثقة عالية`,
    pro: "نيّف برو للوسطاء: تقييم فوري ومخططات وقطع",
    proCta: "سجّل اهتمامك",
    perYear: "سنويًا",
  },
  en: {
    brand: "Nyyf",
    search: "Search a district",
    close: "Close",
    lang: "عربي",
    ppm2: "Price per m²",
    sar_m2: "SAR/m²",
    range: "Typical range",
    conf: { high: "High confidence", medium: "Medium confidence", low: "Low confidence", none: "No price" },
    noPrice: "Not enough deals in this district to estimate a price.",
    yoy: "Year on year",
    deals12: "Deals, last 12 months",
    lastDeal: "Last deal",
    rent: "Apartment rent",
    rentUnit: "SAR/m² a year",
    share: "Share",
    copied: "Link copied",
    legendTitle: "Price per m² · ",
    legendNone: "No price",
    legendConf: "Paler = lower confidence",
    asOf: "Data to",
    method:
      "The price is the median price per m² of all residential sales (land, apartments, villas) registered in the district in the last 12 months, or 24 when deals are few. The typical range is the 25th to 75th percentile. Confidence reflects how many deals there are, how close their prices are, and how recent they are.",
    disclaimer:
      "Indicative estimates from government open data. Not a certified valuation and not official data. Always check before you decide.",
    aboutTitle: "About this map",
    aboutLead: "A free map of price per m² by district in six Saudi cities, refreshed automatically from open data.",
    sources: "Sources",
    licenseNote: "Ministry of Justice deals and REGA rental indicators are published under the KSA Open Data License. Basemap © OpenStreetMap contributors, OpenFreeMap.",
    priced: (p: number, t: number, h: number) => `${p} of ${t} districts priced, ${h} with high confidence`,
    pro: "Nyyf Pro for brokers: instant valuations, plans and plots",
    proCta: "Join the waitlist",
    perYear: "a year",
  },
} as const;

export type Strings = (typeof STRINGS)[Locale];

export function fmtNumber(n: number, locale: Locale, opts: Intl.NumberFormatOptions = {}) {
  return new Intl.NumberFormat(locale === "ar" ? "ar-SA-u-nu-latn" : "en-US", { maximumFractionDigits: 0, ...opts }).format(n);
}

export function fmtShort(n: number, locale: Locale) {
  return new Intl.NumberFormat(locale === "ar" ? "ar-SA-u-nu-latn" : "en-US", {
    notation: "compact",
    maximumFractionDigits: n >= 10000 ? 0 : 1,
  }).format(n);
}

export function fmtPercent(n: number, locale: Locale) {
  return new Intl.NumberFormat(locale === "ar" ? "ar-SA-u-nu-latn" : "en-US", {
    style: "percent",
    maximumFractionDigits: 0,
    signDisplay: "exceptZero",
  }).format(n);
}

export function fmtDate(iso: string, locale: Locale) {
  const d = new Date(iso + "T00:00:00Z");
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", {
    year: "numeric",
    month: "long",
    day: locale === "ar" ? undefined : "numeric",
    timeZone: "UTC",
  }).format(d);
}
