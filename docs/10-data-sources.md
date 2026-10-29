# 10 · Data sources in the prototype

What the Phase 0 map runs on today, how fresh it is, how well it matches, and what is missing.
Updated 2026-10-29. Rebuild with `data/pipelines/build_all.sh` (see the repo README).

## Sources

| Data | Source | Mirror used | License and attribution |
|---|---|---|---|
| Sold deals (date, city, district, area, price, class, plan) | Ministry of Justice (MOJ) real estate transactions, open data | [civillizard/saudi-real-estate-data](https://github.com/civillizard/saudi-real-estate-data) `moj/sales/` | KSA Open Data License: attribute "Ministry of Justice" on the map (done in the city summary) |
| Rents by district and property type (contracts, average annual rent, rent per m²) | Real Estate General Authority (REGA) rental indicators, from Ejar contracts | same repo, `rega/quarterlies/rental/` | KSA Open Data License: attribute "REGA" (done) |
| District polygons with Arabic and English names | Saudi National Address districts | [homaily/Saudi-Arabia-Regions-Cities-and-Districts](https://github.com/homaily/Saudi-Arabia-Regions-Cities-and-Districts) | **GPL-2.0 repository.** Fine for the prototype; replace or clear before commercial launch (see 09, Q7) |
| Land offers (asking prices), Riyadh only | Old nyyf scraped listings (`landsOffers`) | old repo assets | Analysis and prototype display only; not for republishing |
| Basemap | OpenFreeMap (OpenStreetMap data) | `NEXT_PUBLIC_MAP_STYLE_URL` | © OpenStreetMap contributors, shown by MapLibre |

The official portals (moj.gov.sa, rei.rega.gov.sa, data.gov.sa) were not reachable from the build
sandbox, so the pipelines read GitHub mirrors of the same files. In Phase 1 the ingest should pull
from the official portals directly on a schedule.

## Freshness

- MOJ deals: through **2026-03-31** (the latest file in the mirror). Window for "last 12 months" is 2025-04-01 to 2026-03-31; YoY compares with the 12 months before.
- REGA rents: four latest quarters, **2025-Q2 to 2026-Q1**.
- Every number on the map shows its data month in the city summary.

## Coverage per city

| City | MOJ deals (all years) | Deals matched to a district | Districts with a 12-month sold price | Districts with rent |
|---|---|---|---|---|
| Riyadh | 326,472 | 93.3% | 136 of 189 | 169 (rent match 98.9%) |
| Jeddah | 162,214 | 81.0% | 102 of 170 | 134 |
| Makkah | 52,905 | 39.3% | 43 of 68 | 60 |
| Madinah | 51,854 | 67.4% | 72 of 118 | 100 |
| Dammam | 37,842 | 83.5% | 57 of 87 | 76 |
| Al Khobar | 32,262 | 73.1% | 34 of 44 | 40 |

A district needs at least 3 residential single-property deals in the window to get a price; rents
need at least 5 contracts per property type.

## How the numbers are made

- **Sold price per m²:** median of residential single-property deals in the last 12 months, after dropping deals more than 5× away from the district median. Multi-parcel deals are kept for counts and value but not for price per m².
- **Trend:** quarterly median, quarters with at least 3 deals.
- **Rent:** contract-weighted average over the four quarters.
- **Asking vs sold gap (Riyadh):** median asking price per m² of offers in the district against the sold median, districts with at least 3 offers.

## Gaps and what fixes them

1. **No deal coordinates.** MOJ publishes district, plan and parcel numbers, not points, so deals show at district level only. We do not invent points. Fix: plan and parcel geometry (Q4).
2. **District names do not always match.** MOJ and REGA use municipal spellings; the polygons use National Address names, and some newer districts are missing from the polygon set. Matching uses normalisation, aliases and unique-prefix rules. Makkah (39%) and Madinah (67%) are weakest. Fix: official Balady / MOMAH district boundaries with municipal names.
3. **Offers are old and Riyadh only.** They are a stand-in for brokers' own listings (Phase 2).
4. **Boundary license.** The polygon mirror is GPL-2.0. Clear it or switch to a licensed source before commercial launch.
5. **No live feed.** Data is rebuilt by hand. Phase 1 adds a scheduled ingest into PostGIS.
