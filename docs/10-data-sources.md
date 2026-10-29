# 10 · Data sources in the prototype

What the Phase 0 map runs on today, how fresh it is, how well it matches, and what is missing.
Updated 2026-10-29 (government layer probe run with full access). Rebuild with `data/pipelines/build_all.sh` (see the repo README).
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

## Plan (مخطط) level data

Price by location needs plan and parcel precision. What exists in open data, checked 2026-10-29:

- **MOJ open sales files name the plan and parcel only for 2023-Q1** (44,091 deals nationwide; 9,765 in Riyadh, 97% with a plan number). Every other quarter, before and after, gives the district only.
- **No open plan or parcel boundaries.** They sit in Balady / Amanah GIS servers, GEOSA and the Real Estate Registry, none of which publish a download. With full network access the MOMAH (Balady) map layers turn out to need a sign-in token, and the Eastern Amanah GIS disallows automated access (probe below).
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
| [Aqarsas API](https://aqarsas.sa/api) | MOJ + Real Estate Registry deals filtered and returned by plan and parcel; coordinates with a spatial add-on | Paid "API Integration" plan, keys from their support | Request in `nyyf-pro/outreach/`; `fetch_aqarsas.py` is ready for the key |
| MOJ (SREM / open data team) | Per-deal feed with plan and parcel (on SREM it is Nafath-gated); the 2023-Q1 open file shows MOJ can publish these fields | Official request; SREM's website blocks automated clients, so we do not scrape it | Send the MOJ data request in `nyyf-pro/outreach/` |
| Balady / Amanah GIS (e.g. Eastern Amanah `webgis.eamana.gov.sa/.../Balady/MapServer`) | Plan and parcel polygons with plan numbers | ArcGIS REST services; MOMAH layers need a sign-in token, Eastern Amanah's robots.txt disallows automated access, no published reuse terms | Send `nyyf-pro/outreach/momah-gis-request.md` for its `MOJ` / `UrbanBoundary` layers (see probe results below) |
| Wathq Real Estate Deeds API | Deed lookups by number, parcel identity | Paid, per call | Use for deed checks, not bulk |
| GEOSA / National Address API | Parcel geometry, geocoding | Registration; National Address has a free starter tier | Register |

### Government map layer probe (2026-10-29, full network access)

`probe_gov_sources.py` ran with full network access (result in `docs/probes/gov-probe-2026-10-29.json`),
plus manual checks. **No مخطط or parcel layer is open for reuse on any of the four hosts**, so no
government plan or parcel data was collected.

| Host | Result | What it means |
|---|---|---|
| `umaps.momah.gov.sa` (Balady map; `umaps.balady.gov.sa` redirects here, its own REST paths answer 406) | ArcGIS Server 11.5. The services root is public but lists **no public services**; all six folders (`EnergyIntensity`, `Hosted`, `MOJ`, `umaps`, `UrbanBoundary`, `Utilities`) answer **499 Token Required**. The portal (`/portal`) is public but its search returns **0 public items**. The viewer app signs in through Balady SSO (`ssoapp.balady.gov.sa`) and its own `Identity.Api`. No terms of use are published. | Layers, fields and plan polygons are for signed-in users only. Using a token taken from the viewer to download in bulk would sidestep that access control, so we did not. The `MOJ` and `UrbanBoundary` folders are the likely home of plan and parcel layers: ask MOMAH for a data-sharing agreement or an API key. |
| `webgis.eamana.gov.sa` (Eastern Amanah) | Unreachable from the cloud environment (gateway 502 on connect, so the host likely refuses non-Saudi networks). Earlier its **robots.txt disallowed automated access** to `/arcgisnew/rest/services`. | Not probed further. Written permission from the Amanah first. |
| `moj.gov.sa` | Reachable. The open data library (`/ar/OpenData/Pages/library.aspx`, 188 datasets) links every real estate dataset to the National Open Data Portal, e.g. **الصفقات العقارية** (quarterly, [dataset 34e1da80](https://open.data.gov.sa/ar/datasets/view/34e1da80-d4cd-4d65-bdc8-a8d48a7e7ee2)) and **العمليات العقارية المسجلة** (monthly). Granularity is region, city and district. | No plan or parcel fields. Reuse: free, cite "Ministry of Justice", no alteration. `open.data.gov.sa` itself drops connections from the cloud environment, so the GitHub mirror stays the build source; the mirror (last updated 2026-09-14) still ends at 2026-Q1 and carries plan numbers only in 2023-Q1. Plan/parcel fields need the [MOJ data request](https://www.moj.gov.sa/ar/OpenData/Pages/Request.aspx). |
| `srem.moj.gov.sa` | Not touched (blocks automated clients). | Official request only. |

Also checked: OpenStreetMap (ODbL) has almost no plans by name (0 features named مخطط in Riyadh,
4 in Jeddah), so it cannot place more plans on the map.

**Conclusion for مخطط-level prices:** unchanged and now confirmed with full access. No government
source gives plan-level prices or plan boundaries openly. The paths are Aqarsas (paid, client ready),
the MOJ data request, and a MOMAH data-sharing request for the `MOJ` / `UrbanBoundary` map layers
(plan boundaries to draw and to place the 2023-Q1 plan prices). `plans.csv` in base-data is still
the best open plan-level price table and was not changed.

## Gaps and what fixes them

1. **No deal coordinates, and plan numbers only for 2023-Q1.** Deals show at district level; plans show as a list per district and as points only where offers place them. We do not invent points. Fix: a plan/parcel source from the table above (Q4).
6. **Riyadh coverage is falling in the MOJ files** since sales moved to the Real Estate Registry. Fix: a source that includes registry deals (Aqarsas, SREM).
2. **District names do not always match.** MOJ and REGA use municipal spellings; the polygons use National Address names, and some newer districts are missing from the polygon set. Matching uses normalisation, aliases and unique-prefix rules. Makkah (39%) and Madinah (67%) are weakest. Fix: official Balady / MOMAH district boundaries with municipal names.
3. **Offers are old and Riyadh only.** They are a stand-in for brokers' own listings (Phase 2).
4. **Boundary license.** The polygon mirror is GPL-2.0. Clear it or switch to a licensed source before commercial launch.
5. **No live feed.** Data is rebuilt by hand. Phase 1 adds a scheduled ingest into PostGIS.
