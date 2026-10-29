# 06 · Data model

## Data sources

| Source | What it gives | How | Status |
|---|---|---|---|
| Ministry of Justice (MOJ) real estate deals / REGA Real Estate Indicators (rei.rega.gov.sa) | Sold deals: date, city, district, plan, parcel, area, price | Open data download, scheduled ingest | **In the prototype** for 6 cities, deals through 2026-03-31 (see 10) |
| REGA rental indicators (Ejar) | Rent by district and property type, quarterly | Open data download | **In the prototype**, 2025-Q2 to 2026-Q1 (see 10) |
| District boundaries | Polygons with names AR/EN | National Address districts (homaily mirror, GPL-2.0) now; Balady / MOMAH later | Have 6 cities; license to clear (Q7) |
| Plans (مخططات) and parcels (قطع) | Plan outlines, parcel geometry, numbers, dimensions | Balady / municipal plan data, Riyadh Royal Commission, or a licensed provider | **Biggest data gap.** Needs investigation (see 09) |
| Listings (asking prices) | Offers with price, area, text, location | Brokers' own inventory (primary); old scraped land offers (~30k, seed only) | Have seed |
| National Address | Geocoding of addresses and short codes | API (paid) | Later |
| POIs and demographics | Schools, mosques, metro, population | OpenStreetMap, GASTAT | P2 |

Note on scraped listings: the old `landsOffers` data came from public listings. Use it for model training and analysis only, not for republishing, unless terms allow.

## Core entities

```
Office 1─* Member(User, role)
User 1─* Listing, Client, Valuation, Watchlist, Report
Listing *─1 Parcel? ; Listing *─1 District
Deal (MOJ) *─1 District ; Deal *─1 Plan? ; Deal *─1 Parcel?
Client 1─* Requirement ; Requirement *─* Listing (Match)
Deal pipeline: Opportunity *─1 Client, *─1 Listing
Valuation *─* Deal (comparables)
```

## Schema (PostgreSQL 16 + PostGIS)

```sql
-- Geography
city        (id, name_ar, name_en, region_ar, region_en, geom MultiPolygon)
district    (id, city_id, name_ar, name_en, geom MultiPolygon)
plan        (id, district_id, plan_no, name_ar, geom MultiPolygon)          -- مخطط
parcel      (id, plan_id, parcel_no, area_m2, dims jsonb, street_widths int[],
             land_use text, geom Polygon)                                   -- قطعة

-- Market data
deal        (id, source text, source_ref text, deal_date date, city_id, district_id,
             plan_id NULL, parcel_id NULL, property_type text, area_m2 numeric,
             price numeric, price_per_m2 numeric GENERATED, geom Point,
             geo_precision text)  -- 'parcel' | 'plan' | 'district_centroid'
market_stats_monthly (district_id, plan_id NULL, property_type, month date,
             deal_count, median_ppm2, p25_ppm2, p75_ppm2, total_value)      -- materialised

-- Broker workspace
office      (id, name, fal_licence_no, logo_url, brand_color, plan_tier)
app_user    (id, phone, email, name, fal_licence_no, locale, created_at)
membership  (office_id, user_id, role)   -- owner | manager | agent
listing     (id, office_id, owner_user_id, status, property_type, purpose,  -- sale | rent
             price, area_m2, price_per_m2 GENERATED, parcel_id NULL, district_id,
             geom Point, title, description, photos jsonb, rega_ad_licence_no,
             seller_client_id NULL, created_at, updated_at)
client      (id, office_id, owner_user_id, name, phone, type, notes, created_at)
requirement (id, client_id, property_types text[], purpose, min_price, max_price,
             min_area, max_area, area_geom MultiPolygon NULL, district_ids int[])
match       (requirement_id, listing_id, score, notified_at, dismissed bool)
opportunity (id, office_id, assignee_id, client_id, listing_id NULL, stage,
             expected_value, commission_pct, closed_at)
valuation   (id, user_id, office_id, geom Point, parcel_id NULL, inputs jsonb,
             estimate, low, high, confidence, model_version, created_at)
valuation_comparable (valuation_id, deal_id, similarity, adjusted_ppm2)
valuation_feedback (valuation_id, rating, comment, actual_price NULL)
watchlist   (id, user_id, name) ; watch_item (watchlist_id, kind, ref_id, geom NULL)
alert_rule  (id, user_id, watch_item_id, kind, threshold) ; alert_event (...)
report      (id, user_id, kind, params jsonb, public_slug, pdf_url, views int)
```

Every table with `office_id` is protected by row-level security so an office only sees its own data. Market tables (`deal`, `district`, `plan`, `parcel`, stats) are shared and read-only for users.

## Indexing
- GIST on every `geom`.
- `deal (district_id, deal_date)`, `deal (plan_id, deal_date)`, `listing (office_id, status)`.
- H3 index column (resolution 8 and 10) on `deal` and `listing` for fast hex aggregation and comparables search.

## Data quality rules
- Drop or flag deals with price per m² outside the district's 1st to 99th percentile, zero area, or duplicate `source_ref`.
- Normalise Arabic names (أ/ا/إ, ة/ه, ى/ي, spaces, "حي " prefix, "مخطط " prefix). The old feature list shows duplicates such as "مربعات الأمير سطام" and "مربعات الامير سطام".
- Keep `geo_precision` honest: never draw a district-centroid deal as if it were on a parcel.

## Mapping from old nyyf tables
| Old | New |
|---|---|
| `RealEstates` (ReportMaster) | `deal` |
| `ValuationsHistory` | `valuation` |
| `Feedback` | `valuation_feedback` |
| `TrackList`, `TrackListRecords`, `RealEstate` | `watchlist`, `watch_item` (and `listing` where it was a real property) |
| users table | `app_user` + `office` + `membership` |
