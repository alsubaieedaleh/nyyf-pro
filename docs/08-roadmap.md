# 08 · Roadmap

Assumes a small team (1 to 2 full-stack developers, 1 part-time data/ML, 1 part-time designer). Durations are estimates and should be revisited at the end of each phase.

## Phase 0 · Foundations (weeks 1 to 3)
**Goal:** safe base, clean data, agreed design.
- Rotate leaked secrets from the old repo (Azure Postgres password, Mapbox token); take `terraform.tfstate` out of git.
- Competitive teardown of Suhail (hands-on, screenshots), plus Aqar, REGA indicators, Paseetah.
- Interview 8 to 10 brokers in Riyadh; validate the jobs in 03 and the MVP scope.
- Confirm data access: MOJ / REGA deals, plan and parcel geometry source (the key unknown).
- Set up monorepo, CI, environments, PostGIS, Martin, PMTiles pipeline.
- Ingest Riyadh deals, districts, and the old land offers; clean and normalise names.
- Design system and map style (light and dark), price colour scale, key screens in Figma.

**Progress (2026-10-29):** monorepo and the Next.js + MapLibre map prototype are up. The map runs on MOJ sold deals and REGA rents for Riyadh, Jeddah, Makkah, Madinah, Dammam and Al Khobar, plus the old Riyadh offers (see 10). Still open: secret rotation in the old repo, broker interviews, PostGIS and tiles, parcel geometry, CI.

**Exit:** Riyadh district tiles and deal tiles served from a CDN; designs signed off; data access confirmed or a fallback chosen.

## Phase 1 · MVP: the map and valuation (weeks 4 to 10)
**Goal:** a broker can explore Riyadh and value any plot.
- Market Map P0: districts choropleth, deal and listing clusters, sheets and cards, search, filters, smooth motion.
- Valuation v2 (comparables + gradient boosted model), range, comparables on map, history.
- Auth (phone OTP), broker profile with FAL licence and branding.
- Valuation report: share link and PDF.
- Watchlists (basic).
- Bilingual RTL UI, responsive web + installable PWA.

**Exit:** 20 to 30 pilot brokers using it weekly; valuation error ≤ 15% on holdout; performance budget in 05 met.

## Phase 2 · Broker workspace (weeks 11 to 18)
**Goal:** brokers run their business in Nyyf Pro.
- Inventory: add listings, statuses, auto price check, REGA ad licence field, public listing pages.
- Clients and requirements, auto-matching, WhatsApp share.
- Deal pipeline (kanban) with commission tracking.
- Alerts (new deals, price moves, under-priced listings).
- Map P1: metric switcher, draw area stats, time slider, plan outlines.
- District and custom-area market reports.

**Exit:** pilot brokers add their real listings; at least 3 reports shared per active broker per week.

## Phase 3 · Offices, mobile, and launch (weeks 19 to 26)
**Goal:** public launch and revenue.
- Office workspaces, roles, shared inventory, office dashboard.
- Subscriptions and billing (Free, Pro broker, Office).
- Native mobile app (React Native + MapLibre Native).
- Parcel layer where data is available.
- Expand to Jeddah and Dammam/Khobar.
- Valuation error target ≤ 12%.

**Exit:** public launch; 500 weekly active brokers within 6 months.

## Phase 4 · Later (P2 backlog)
3D and POI layers, demographics, report view tracking, weekly digest, appraiser tier, Ejar and REGA integrations, API for developers and banks, more cities.

## Pricing hypothesis (to validate in Phase 0 interviews)
| Plan | For | Includes |
|---|---|---|
| Free | Trial | Map, 5 valuations per month, no branding |
| Pro | Individual broker | Unlimited valuations, branded reports, inventory, clients, alerts |
| Office | Brokerage | Pro for each seat, shared inventory, pipeline, office dashboard |

## First two weeks, concretely
1. Rotate secrets and clean the old repo.
2. Create the `nyyf-pro` repo with the monorepo skeleton and these docs in `docs/`.
3. Load Riyadh deals and districts into PostGIS; publish district PMTiles.
4. Build a throwaway map prototype (MapLibre + tiles) to prove the smoothness target on a mid-range phone.
5. Book broker interviews and do the Suhail teardown.
