# 09 · Decisions and open questions

## Decisions made (2026-10-29)
| # | Decision | Reason |
|---|---|---|
| D1 | Rebuild, reusing data, domain knowledge, and brand; do not refactor the old code | Old code has security issues and no broker concepts (see 02) |
| D2 | Map-first: the map is the home screen | User's headline feature; matches the Suhail reference |
| D3 | Brokers are the primary customer, not buyers | User's goal: "very helpful for all real estate brokers" |
| D4 | Riyadh first | Existing data and model are Riyadh-only |
| D5 | Vector tiles, not GeoJSON downloads | Needed for smoothness on mobile |
| D6 | Explainable valuation (range + comparables) replaces the single-number Keras model | Brokers need evidence to show clients |
| D7 | Front end: Next.js (React, TypeScript), not Angular (approved by owner, 2026-10-29) | Map ecosystem, SSR share pages, React Native path |
| D8 | Map library: MapLibre GL, not Mapbox (approved by owner, 2026-10-29) | Open source, no per-load fees |
| D9 | Mobile: installable PWA first, React Native in Phase 3; Flutter retired (approved by owner, 2026-10-29) | One code family with the web |
| D10 | New code lives in a new `nyyf-pro` repo (approved by owner, 2026-10-29) | Clean history, no leaked secrets carried over |

## Decisions pending (need the owner)
| # | Question | Recommendation |
|---|---|---|
| Q4 | Plan and parcel geometry: which source (Balady, Riyadh Royal Commission, licensed provider)? | Investigate in Phase 0; launch with district + plan level if parcels are not obtainable |
| Q5 | Hosting region for PDPL | A Saudi or nearest GCC region; confirm with a legal check |
| Q6 | Team and timeline: who builds, and is the 26-week plan realistic for them? | Owner to confirm |
| Q7 | District boundaries: the current polygons come from a GPL-2.0 repository and miss some municipal districts (Makkah 39% of deals matched) | Get Balady / MOMAH boundaries or a licensed provider before commercial launch |

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| No access to parcel geometry | Map less precise than Suhail | Strong district and plan layers, broker-placed pins, partner with a data provider |
| MOJ / REGA data terms change or lag | Stale market data | Multiple sources, show data date on every number. Today the latest MOJ month is 2026-03 (about 7 months behind) |
| Valuation accuracy not good enough for brokers | Trust loss | Always show range and comparables; feedback loop; avoid false precision |
| Suhail adds broker CRM features | Weaker differentiation | Move fast on workflow depth (matching, pipeline, sharing) and price for individual brokers |
| Scraped listing data terms | Legal | Training and analysis only; brokers' own listings for display |
| REGA advertising rules (FAL licence, ad licence on every listing) | Compliance | Required fields and validation from day one |

## Sources
- Suhail: https://www.suhail.ai/ and https://bouncewatch.com/company/suhail
- REGA Real Estate Indicators: https://rei.rega.gov.sa/en/advanced-search
- MOJ and REGA open data mirror: https://github.com/civillizard/saudi-real-estate-data
- National Address district polygons: https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts
- Old nyyf code: project folder `Real-Estate-App/`
