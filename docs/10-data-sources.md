# 10 · Data sources in the prototype

What the Phase 0 map runs on today, how fresh it is, how well it matches, and what is missing.
Updated 2026-10-29. Rebuild with `data/pipelines/build_all.sh` (see the repo README).
The clean base tables live in the project folder `nyyf-pro/base-data/` (built by `build_base.py`).

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

Updated 2026-11-12. Every external input is pinned in `data/pipelines/sources.lock.json` (URL at a fixed
commit, plus sha256). `fetch_latest.py` lays the newest quarters over the mirror, checks them, and the weekly
workflow builds from that tree.

| Data | Newest period on the map | Where it comes from | Checks |
|---|---|---|---|
| MOJ sale deals | **2026-09-30** (2026-Q3; September is preliminary, late registrations may still arrive) | 2020-Q1..2026-Q1: civillizard mirror. 2026-Q2: two independent republications of the Ministry's public transactions report, cross-checked (34,651 shared refs, no price differences). 2026-Q3: KSA Land Data's free full-quarter file on Hugging Face | Dates in quarter, cross-source agreement, no ref in two quarters, completeness vs the last 4 quarters |
| MOJ 2025-Q2 | **missing** | The mirror's file is a mislabelled 2024-Q2 and is skipped | The report steps back to the newest pair of whole windows (2026-Q1) until it is filled |
| REGA sales by district and type | 2025-Q2 (Madinah 2024-Q4) | civillizard mirror | Unchanged |
| REGA rents (Ejar) | 2025-Q2..2026-Q1 | civillizard mirror | Unchanged |
| GASTAT price index, by region and type | **2026-Q3** | stats.gov.sa tables (`repi.json`) | Every series must reach the same quarter |

**Riyadh:** since 19 May 2026 Riyadh sales are registered only in the Real Estate Registry, which the MOJ files do
not hold. MOJ has 1,676 Riyadh city deals in 2026-Q2 and 1 in 2026-Q3. Riyadh district prices rest on older REGA
type data and on thin, capped-confidence MOJ deals; the GASTAT index (Riyadh region +4.6% on a year to 2026-Q3)
is the only current official signal. `fetch_latest_report.json` flags Riyadh and Yanbu as "thinning".

### What would make it fresher (needs a decision)

| Option | Gives | Cost / approval |
|---|---|---|
| KSA Land Data full file | MOJ 2025-Q2 (the portal's original release), so YoY and the report use whole windows to 2026-Q3 | $49 once, Saudi Open Data License |
| A Saudi machine running `fetch_open_data.py` | Official portal files (2025-Q2, newer REGA rents and district sales) | A small Saudi VPS or self-hosted runner |
| REGA written approval (draft in the project folder) | Registry deals by district and type to 2026-Q3, monthly Ejar rents: fixes Riyadh | Approval from REGA |
| Aqarsas API | Daily MOJ + registry deals | Paid plan |
| MOJ interactive report (Power BI on moj.gov.sa) | Same deals as the open files, weekly | Querying its internal API is not a documented open-data channel; not used |

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

## Plan (مخطط) level data

Price by location needs plan and parcel precision. What exists in open data, checked 2026-10-29:

- **MOJ open sales files name the plan and parcel only for 2023-Q1** (44,091 deals nationwide; 9,765 in Riyadh, 97% with a plan number). Every other quarter, before and after, gives the district only.
- **No open plan or parcel boundaries.** They sit in Balady / Amanah GIS servers, GEOSA and the Real Estate Registry, none of which publish a download. From this build sandbox the government hosts (srem.moj.gov.sa, rei.rega.gov.sa, Balady, Amanah geoportals) are blocked by the network policy.
- **Riyadh is thinning in the MOJ open files since 2025.** Riyadh deals per quarter fell from about 15,000 (2024) to 2,889 (2026-Q1), because sales registered through the Real Estate Registry (السجل العقاري) are not in the MOJ files. Riyadh's last-12-month numbers rest on fewer deals than before.

What the project builds instead (`data/pipelines/build_plans.py`, base table `plans.csv`):

1. Each plan's median **land** price per m² from the 2023-Q1 deals (at least 3 land deals).
2. Carried to today with the district's price change since 2023-Q1 (same definition both ends, capped 0.6–2.5×).
3. Placed on the map where old Riyadh offers name the plan in their text (112 plans placed from 2,639 offers).

| City | Plans | With a land price | With an estimate today | Placed on the map |
|---|---|---|---|---|
| Riyadh | 966 | 424 | 409 | 112 |
| Jeddah | 426 | 160 | 153 | 0 |
| Makkah | 90 | 26 | 24 | 0 |
| Madinah | 153 | 43 | 41 | 0 |
| Dammam | 233 | 58 | 44 | 0 |
| Al Khobar | 115 | 27 | 20 | 0 |

**Does plan precision help?** Leave-one-out test on 2023-Q1 land deals (median absolute error of the
predicted price per m²):

| City | District median | Plan median | Deals tested |
|---|---|---|---|
| Riyadh | 18.3% | **14.9%** | 5,783 |
| Jeddah | 23.6% | **21.6%** | 1,866 |
| Dammam | 23.8% | **20.9%** | 737 |
| Madinah | 32.1% | **25.0%** | 622 |

So the original nyyf idea holds: plan-level location cuts valuation error by a fifth or more. Parcel
coordinates would cut it further.

### Getting current plan and parcel data (ranked)

| Option | Gives | Cost and access | Next step |
|---|---|---|---|
| [Aqarsas API](https://aqarsas.sa/api) | MOJ + Real Estate Registry deals filtered and returned by plan and parcel; coordinates with a spatial add-on | Paid "API Integration" plan, keys from their support | Ask for a quote and a sample for Riyadh |
| SREM public API (prod-srem-api-srem.moj.gov.sa) | Daily market index, per-area aggregates (`Dashboard/GetAreaInfo`), live deal stream; per-deal feed is Nafath-gated | Free, undocumented, behind a bot filter | Allow the host in this environment and map what `GetAreaInfo` returns |
| Balady / Amanah GIS (e.g. Eastern Amanah `webgis.eamana.gov.sa/.../Balady/MapServer`) | Plan and parcel polygons with plan numbers | Public map servers, terms unclear | Allow the hosts, list layers, ask the Amanah about reuse terms |
| Wathq Real Estate Deeds API | Deed lookups by number, parcel identity | Paid, per call | Use for deed checks, not bulk |
| GEOSA / National Address API | Parcel geometry, geocoding | Registration; National Address has a free starter tier | Register |

## Gaps and what fixes them

1. **No deal coordinates, and plan numbers only for 2023-Q1.** Deals show at district level; plans show as a list per district and as points only where offers place them. We do not invent points. Fix: a plan/parcel source from the table above (Q4).
6. **Riyadh coverage is falling in the MOJ files** since sales moved to the Real Estate Registry. Fix: a source that includes registry deals (Aqarsas, SREM).
2. **District names do not always match.** MOJ and REGA use municipal spellings; the polygons use National Address names, and some newer districts are missing from the polygon set. Matching uses normalisation, aliases and unique-prefix rules. Makkah (39%) and Madinah (67%) are weakest. Fix: official Balady / MOMAH district boundaries with municipal names.
3. **Offers are old and Riyadh only.** They are a stand-in for brokers' own listings (Phase 2).
4. **Boundary license.** The polygon mirror is GPL-2.0. Clear it or switch to a licensed source before commercial launch.
5. **No live feed.** Data is rebuilt by hand. Phase 1 adds a scheduled ingest into PostGIS.
