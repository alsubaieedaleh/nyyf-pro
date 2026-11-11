# Nyyf public price heat map

A free, public map of price per m² by district for Saudi cities. The pipeline tries every city in
`data/pipelines/cities.json` and publishes those where at least 15 districts get a high or medium confidence sale
price for one property type (today: Riyadh, Jeddah, Makkah, Madinah, Dammam, Al Khobar, Taif, Hail, Al Hofuf, Al Kharj,
Hafar Al Batin). Adding a city is one line in that file.
Its job is to bring people in: brokers, buyers and owners check their district, share the link, and later
meet Nyyf Pro. Districts only; plans (مخططات), parcels and the old offers stay in Nyyf Pro.

- Static site: Vite + TypeScript + MapLibre GL, no server and no database.
- Basemap: OpenFreeMap Positron (free, no key, commercial use allowed with attribution).
- Data: `public/data/districts.geojson` (about 1.6 MB), `meta.json` and `market.json` written by
  `data/pipelines/export_public.py`, and `report.json` written by `data/pipelines/build_report.py`.
- Arabic first (RTL), English toggle. Mobile bottom sheet, desktop side panel.

## Pages

| Page | What it is |
|---|---|
| `/` (`index.html`, `src/landing.ts`) | Landing: what Nyyf is, buttons to both maps and the market page, headline numbers, sign-up form |
| `/home.html` (`src/home.ts`) | Market today, per city (Riyadh by default): deals and value last quarter, price per m² for land, villas and apartments with year-on-year change, median rents, the quarterly district report, price trend chart, most expensive and most active districts, sign-up forms |
| `/map.html?mode=sale&type=land` (`src/map.ts`) | Sale map. `type` is `land`, `villa` or `apartment` |
| `/map.html?mode=rent&type=apartment` | Rent map. `type` is `apartment`, `villa` or `floor` |

Deep links: `map.html?mode=sale&type=villa#riyadh/<district id>`. Old links (`/#riyadh/<id>`) redirect to the sale map.

## What the map shows

| Element | Meaning |
|---|---|
| Fill colour | Price per m² for the chosen type, five steps (sale: teal to coral, rent: light to dark blue). Breaks are the quintiles of each city's priced districts for that type |
| Fill strength | Confidence: high is solid, medium lighter, low paler. Sale: 30+ / 10+ / 3+ registry deeds in the last 4 quarters. Rent: 50+ / 15+ / 5+ contracts |
| Grey | No price for this type in this district |
| Panel | Price, confidence and its reason, year-on-year change (sale) or yearly rent (rent), all types side by side (tap one to switch the map), and the MOJ all-residential price to the latest month |

Why two sale sources: MOJ open deals run to the latest month but stopped saying whether a deal was land, a villa or
an apartment after 2023-Q3. The split by type comes from the REGA real estate registry district files, which today
end at 2025-Q3 (Madinah at 2024-Q4, Al Khobar starts 2025). The map labels the window it uses.

## Run it

```bash
pnpm install
pnpm --filter @nyyf/heatmap dev      # http://localhost:5173
pnpm --filter @nyyf/heatmap build    # static site in apps/heatmap/dist
```

## Data pipeline (automatic, about $0)

`.github/workflows/heatmap-data.yml` runs every Sunday at 06:00 Riyadh time (and by hand from the Actions tab):

1. Shallow-clones the MOJ/REGA open data mirror and the district boundaries.
2. Runs `build_all.sh`, `build_base.py` and `build_final.py` (the same scripts as the full dataset; about 3 minutes),
   then `build_rega_sales.py` (sale price per m² by district and type, plus the city series for the market page)
   and, after the export, `build_report.py` (the quarterly district report).
3. Runs `export_public.py`, which keeps district rows only and checks the quality gates against the data
   that is live now, for each type: priced districts may not fall by more than 5% in a city, a city's median
   may not move by more than 15%, and every district needs a name and a sane range. A failed gate fails the run, GitHub
   emails the owner, and the live data stays as it was. `force` on a manual run publishes anyway.
4. Commits `apps/heatmap/public/data` only when the numbers changed, then calls the deploy workflow.

`.github/workflows/heatmap-deploy.yml` builds the site on every change (and checks it on pull requests).
It publishes to GitHub Pages only when the repository variable `HEATMAP_PUBLISH` is `true`.

Cost: GitHub Actions and Pages are free for a public repository, OpenFreeMap is free. A custom domain is the
only optional cost. If traffic outgrows Pages (soft limit 100 GB a month), the same `dist/` folder deploys to
Cloudflare Pages unchanged (`public/_headers` already sets its caching).

## Going live (checklist)

1. Clear the open questions under "Licensing" below.
2. Settings > Pages > Source: **GitHub Actions**.
3. Settings > Secrets and variables > Actions > Variables: `HEATMAP_PUBLISH = true`.
   Optional: `HEATMAP_LEADS_URL` (turns on the sign-up form, see below),
   `HEATMAP_CF_BEACON` (Cloudflare Web Analytics token, cookie-free visitor counts).
4. Run "Heat map deploy" from the Actions tab. The site is at `https://<owner>.github.io/nyyf-pro/`
   (or a custom domain set in Settings > Pages).

## Quarterly district report

On the market page, per city: which districts rose and fell most against the same period a year earlier, the
longest rising streaks (quarters in a row above last year), and the busiest districts. The sources are quarterly,
so the report is too; it refreshes on its own when a new quarter is published.

- Each city uses the source that describes it best. **Registry** (REGA deeds by district and property type, price =
  total value / total area) when its district files are within two quarters of MOJ or when MOJ no longer records
  most of the city's sales (Riyadh since 2025). **MOJ** (median of single-property residential sales, land, villas and
  apartments together, bulk batches left out) where the registry files are old and MOJ still has the usual volume.
  The page says which.
- Windows are half-years (last two quarters against the same two a year earlier), with 20+ deeds or sales on each
  side. Moves beyond 75% a year are left out and counted, because they almost always mean a different mix of plots.

## Data checks in the pipeline

- A MOJ file whose deal dates do not fall in the quarter its name says is skipped with a warning (the mirror's
  `MOJ-Sales-2025-Q2.csv` is really 2024-Q2, so April to June 2025 is missing until the mirror is fixed).
- Bulk batches (10+ deals at one price in one district within 7 days, such as housing programme handovers) stay in
  deal counts but only one of them counts toward prices. A zero-width price range lowers confidence.
- MOJ coverage per city (deals a quarter, last 12 months against the 12 before) caps confidence: under 50% at low,
  under 75% at medium. Riyadh is at about 29% after the move to the Real Estate Registry.
- Windows and the data date come from the latest deal, and confidence falls as the data ages.
- Year-on-year change needs 20+ priced deals in each year.

## Sign-ups (people interested in Nyyf)

The landing and market pages have a form: name, phone or email, role (buyer, owner, broker, developer, investor),
city, what they want, and a consent box. It posts to a Google Apps Script web app that adds a row to a Google Sheet
you own (free, no server). Setup steps are at the top of `leads/google-apps-script.gs`; put the web app's `/exec`
URL in the repository variable `HEATMAP_LEADS_URL` and run "Heat map deploy". Until then the form says sign-up
opens soon. A hidden honeypot field drops most bots.

The market page also has an email-only form for the quarterly report (interest `district_report`). The same Apps
Script can email it: run `setupWeeklyTrigger` once; every Sunday it checks `report.json` and sends each subscriber
their city's report when that city has a new quarter, with a signed one-click unsubscribe link.

## Room for revenue later

The public map is the free tier. Hooks already in place: the sign-up list, the join link in every district
panel, shareable deep links, and analytics. Natural paid steps, all from the Nyyf Pro plan:

- Accounts and a watchlist with price alerts per district (needs a small backend, e.g. Supabase free tier).
- Pro: plan (مخطط) and parcel prices, instant valuation with comparables, deal lists, PDF reports.
- Broker branding on shared links and reports; an API for developers and banks.

## Licensing (check before going public)

| Data | Licence | Status |
|---|---|---|
| MOJ deals | KSA Open Data License: reuse, derivatives and redistribution allowed with attribution to the Ministry of Justice; do not present derived numbers as official | OK with the attribution and disclaimer on the map. MOJ also asks that its raw data is not modified: we publish our own medians, labelled as estimates |
| REGA rents | KSA Open Data License, attribute REGA | OK |
| Source mirror | `civillizard/saudi-real-estate-data` (MIT code, raw government files unchanged) | Works, but a community mirror could stop updating; move the fetch to open.data.gov.sa when possible |
| District polygons | GPL-2.0 repository whose README says it was collected from maps.address.gov.sa (SPL National Address) | **Open question.** GPL lets us republish the derived polygons (credited, same licence), but the original rights sit with SPL, whose terms may not allow redistribution, and a paid tier makes this weigh more. Options: ask SPL, licence the National Address API, or switch to official boundaries |
| Basemap | OpenFreeMap / OpenStreetMap (ODbL) | OK, attribution shown on the map |
| Old offers | Scraped listings, not for republishing | Not used by this map. Note: they are in `apps/web/public/data` in this public repo |
